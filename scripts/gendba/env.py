#!/usr/bin/env python3
"""
env.py -- the Gen-DBA index-tuning environment.

This is the artifact RL consumes: a tool surface, a verifiable reward, and a task
distribution. Harvested traces (see ise_trace.py) are cold-start and reference
material; the policy generates its own trajectories in here.

DESIGN COMMITMENTS (each of these is a decision, not an accident)

1. The cost model is a TOOL, never the reward.
   Measured across two runs, PostgreSQL's estimator understated the benefit of the
   same index set by ~2x (-17.8% vs -41.6%; -18.1% vs -35.7%). Rewarding estimated
   cost would teach the policy to game a proxy we have already proven biased.
   PROBE/whatif is cheap and available; the reward is wall-clock only.

2. Tool time is charged.
   A what-if evaluation is ~4 ms; a workload measurement is ~15 s -- about 4000x.
   If diagnosis were free the policy would measure everything. Every call returns
   its own duration and decrements a budget, so *how to spend the measurement
   budget* becomes learnable behaviour rather than an assumption.

3. Reset is DDL, not snapshot restore.
   Dropping the episode's indexes costs ~1 s against ~7.8 s to untar 7.8 GB, and it
   keeps the page cache stable between rollouts (which matters -- see 4).
   restore_snapshot() exists for periodic drift correction.

4. Measurement protocol is fixed and explicit.
   Run-to-run variance sets the floor on what reward differences mean anything.
   Two earlier runs of a similar configuration measured 1.711x and 1.556x, largely
   because one warmed the cache differently. So: an explicit warmup, median of N,
   and the protocol recorded in the trajectory.

5. Tool names are the DEPLOYED harness verbs (cidr27_gendba.md §2.2), not internal
   ones. Training on a vocabulary we later discard wastes the cold-start.

Verbs: CONNECT, HARVEST, OBSERVE, PROBE, REALIZE  (+ terminal SCORE)
"""
from __future__ import annotations

import os as _os
# Three roots, overridable so the harness is not welded to one machine layout.
# Defaults match what scripts/cloudlab/provision.sh builds.
#   GENDBA_REPO   the repo (persists: CloudLab project dir)
#   GENDBA_BUILD  postgres build, conda envs, logs   (node-local, rebuilt)
#   GENDBA_DATA   snapshots and generated data        (node-local, rebuilt)
GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")
GENDBA_BUILD = _os.environ.get("GENDBA_BUILD", "/mnt/protox")
GENDBA_DATA = _os.environ.get("GENDBA_DATA", "/data/protox")

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

import psycopg2
import yaml

import record as rec
from record import Episode, ESTIMATED, MEASURED, DERIVED, DECLARED


REPO = GENDBA_REPO
DATA = GENDBA_DATA + "/data"
PGBIN = GENDBA_BUILD + "/pg15/bin"

BENCHMARKS = {
    "job":  ("configs/benchmark/job_full.yaml", "queries/job_full", "queries/job_full/order.txt",
             "job_base.tgz"),
    "tpch": ("configs/benchmark/tpch.yaml", "queries/tpch", "queries/tpch/order.txt",
             "tpch_sf10_base.tgz"),
    "dsb":  ("configs/benchmark/dsb_s10.yaml", "queries/dsb_10", "queries/dsb_10/d_order.txt",
             "dsb_sf10_base.tgz"),
    "tpcc": ("configs/benchmark/tpcc.yaml", "queries/tpcc", "queries/tpcc/txn.txt",
             "tpcc_base.tgz"),
}

# Workloads that MUTATE. Every other benchmark in this harness is read-only, which is
# what lets us measure, change the configuration, and measure again against the same
# database. TPC-C writes -- and its statements carry literal primary keys, so running
# the workload twice is a duplicate-key violation, not merely a drift.
#
# The protocol for these is: run the whole workload inside a transaction and ROLL IT
# BACK. Index maintenance is still paid (the index tuples are written before the
# rollback), so an index's cost on a write workload becomes visible for the first
# time, while the database does not drift and before/after remain comparable.
#
# What this protocol does NOT capture, and what any consumer has to be told:
#   * no commit, so WAL flush / fsync cost is understated
#   * rolled-back tuples are still dead tuples that a real system must vacuum
#   * one long transaction holds a snapshot, so it does not model concurrency
# It is declared in the episode rather than left for a reader to infer.
MUTATING = {"tpcc"}

IDX_PREFIX = "gendba_"


class ToolError(Exception):
    """A tool call the policy got wrong. Returned to the policy, not raised to RL."""


@dataclass
class Task:
    """One point in the task distribution. This is what we vary, not trace volume."""
    benchmark: str = "job"
    n_queries: int = 25
    budget_mb: float = 500.0
    max_index_width: int = 2
    objective: str = "workload_latency"     # or p95_latency
    tool_budget_s: float = 300.0
    seed: int = 0
    # Which constraint the POLICY actually receives and is judged against.
    # extend/relaxation honour a storage budget; auto_admin/drop honour a count of
    # indexes and ignore budget entirely. Penalising a count-constrained policy for
    # exceeding a budget it was never given produces a reward that means nothing.
    constraint_kind: str = "budget_MB"       # budget_MB | max_indexes
    constraint_value: float = 500.0
    query_select: str = "head"               # head | one-per-shape

    def id(self) -> str:
        return (f"{self.benchmark}-q{self.n_queries}-b{int(self.budget_mb)}"
                f"-w{self.max_index_width}-{self.objective}-s{self.seed}")


@dataclass
class Call:
    """One tool call, recorded so the trajectory is replayable."""
    i: int
    verb: str
    args: dict
    duration_s: float
    move: str                 # which of the six moves this verb serves
    ok: bool = True
    error: str | None = None
    result_digest: dict = field(default_factory=dict)


class IndexTuningEnv:
    # Protocol defaults chosen from measurement, not intuition (noise.py):
    #   warmup=0,repeats=1  cv 0.34%  18.3s   <- default
    #   warmup=1,repeats=3  cv 0.21%  73.9s
    # The expensive protocol costs 4x for a 0.13pp improvement. Full build/measure/
    # drop cycles reproduce a speedup to cv 0.757% (reset_fidelity.py), so the
    # effective reward floor is ~1.015x either way.
    def __init__(self, task: Task, port: int = 5492, dbname: str = "benchbase",
                 measure_repeats: int = 1, measure_warmup: int = 0, verbose: bool = False,
                 policy_meta: dict | None = None, query_timeout_s: float = 300.0):
        self.task = task
        self.port = port
        self.dbname = dbname
        self.measure_repeats = measure_repeats
        self.measure_warmup = measure_warmup
        self.verbose = verbose
        self.policy_meta = policy_meta or {"name": "unspecified", "kind": "scripted"}
        self.query_timeout_s = query_timeout_s

        cfg, qdir, qorder, snap = BENCHMARKS[task.benchmark]
        self.snapshot = snap
        # configs/benchmark/dsb_*.yaml write web_returns's column list with "_" instead
        # of "-" as the list marker, so PyYAML parses 24 column names into one string.
        # Recover them rather than dropping the table: the exclusion would only be
        # right for Proto-X, whose pre-trained embedder has no web_returns columns in
        # its action space. The ISE algorithms never touch that embedder, and the
        # paper's own DSB baseline indexes web_returns (load_dsb.py, index10). Do NOT
        # fix the YAML itself -- that would break Proto-X's embedder compatibility.
        self._attrs, self._malformed = rec.indexable_columns(f"{REPO}/{cfg}")
        self.queries = self._load_queries(qdir, qorder, task.n_queries,
                                          select=task.query_select)

        # Name the role explicitly. Without a user in the DSN libpq falls back to the
        # OS user, so this only ever worked because the callers happened to export
        # PGUSER -- and a caller that did not (run_tpcc.sh) failed every episode with
        # 'role "yrayhan" does not exist'. Environment still wins, so nothing that
        # already sets PGUSER changes behaviour.
        _user = _os.environ.get("PGUSER", "admin")
        self.conn = psycopg2.connect(
            f"host=localhost port={port} dbname={dbname} user={_user}")
        self.conn.autocommit = True
        with self.conn.cursor() as c:
            c.execute("SET lock_timeout = '120s'")

        self.episode: Episode | None = None
        self._tool_s = 0.0
        self._applied: list[dict] = []
        self._baseline_ms: dict | None = None
        self._episode_id = None
        self._closed = False
        self._primed = False

    # ------------------------------------------------------------------ helpers
    def _q(self, sql, fetch=True):
        with self.conn.cursor() as c:
            c.execute(sql)
            return c.fetchall() if fetch else None

    def _load_queries(self, qdir, qorder, limit, select="head"):
        """
        select="head"          first N in workload order (JOB, TPC-H)
        select="one-per-shape" one query per distinct SHAPE, for workloads that ship
                               many parameter variants of the same template. DSB has
                               489 queries over 34 templates x {aggregate, _spj} = 67
                               shapes; taking the head would sample a handful of
                               templates 10x over instead of covering the workload.
                               Grouping stays on `template` (coarser), so variants of
                               one template can never split across a train/eval line.
        """
        rows = []
        for line in open(f"{REPO}/{qorder}"):
            if line.strip():
                rows.append(line.strip().split(",")[:2])

        if select == "one-per-shape":
            seen, picked = set(), []
            for qid, fname in rows:
                b = re.sub(r"\.sql$", "", fname)
                m = re.match(r"^query(\d+)(?:s\d+)?(_.*)?$", b)
                shape = (m.group(1), m.group(2) or "") if m else (b, "")
                if shape in seen:
                    continue
                seen.add(shape)
                picked.append((qid, fname))
            rows = picked

        out = []
        for qid, fname in rows[:limit] if limit else rows:
            text = open(f"{REPO}/{qdir}/{fname}").read().strip().rstrip(";")
            out.append({"id": qid, "file": fname, "text": text})
        return out

    def _record(self, verb, args, t0, move, payload=None, ok=True, error=None,
                provenance=None, produced_by=None):
        """
        The FULL payload is stored, never a digest. An earlier version of this method
        summarised responses to scalars to keep trajectories small; that would have
        silently discarded the per-node estimated-vs-actual rows inside EXPLAIN
        ANALYZE payloads, which are cardinality-estimation training data in their own
        right. See docs/training_record.md rule 2.
        """
        d = time.time() - t0
        self._tool_s += d
        self.episode.tool_call(verb=verb, args=args, payload=payload, duration_s=d,
                               move=move, provenance=provenance,
                               produced_by=produced_by, ok=ok, error=error)
        if self.verbose:
            i = len(self.episode.events) - 1
            print(f"  [{i:3d}] {verb:9s} {move:11s} {d:7.3f}s "
                  f"{'' if ok else 'ERR ' + str(error)}")
        return self.episode.events[-1]

    @property
    def trajectory(self):
        return self.episode.events

    @property
    def tool_budget_remaining(self) -> float:
        return round(self.task.tool_budget_s - self._tool_s, 2)

    # -------------------------------------------------------------------- reset
    def reset(self, restore_snapshot: bool = False) -> dict:
        """
        Drop this episode's indexes and clear state. DDL reset by default (~1 s);
        snapshot restore (~8 s) only when explicitly asked, to correct drift.
        """
        if restore_snapshot:
            self.restore_snapshot()
        else:
            for (name,) in self._q(
                    f"SELECT indexname FROM pg_indexes WHERE schemaname='public' "
                    f"AND indexname LIKE '{IDX_PREFIX}%'"):
                self._q(f"DROP INDEX IF EXISTS {name}", fetch=False)
        self._tool_s, self._applied = 0.0, []
        self._baseline_ms = None
        self._closed = False

        # A fresh record per episode. The header is heavy on purpose: a measured
        # latency is uninterpretable without the engine, knobs, hardware, snapshot
        # and statistics state it was produced under.
        self.episode = Episode(task={**asdict(self.task), "id": self.task.id()},
                               policy=self.policy_meta,
                               collector="scripts/gendba/env.py")
        self.episode.fingerprint_environment(self.conn, snapshot=f"{DATA}/{self.snapshot}")
        self.episode.set_workload(self.queries)
        self.episode.set_initial_state(self.conn)
        self.episode.header["action_space"] = {
            "source": "benchmark config `attributes`",
            "n_tables": len(self._attrs),
            "n_indexable_columns": sum(len(c) for c in self._attrs.values()),
            "recovered_from_malformed_yaml": self._malformed,
            "note": ("web_returns' column list uses '_' as its YAML list marker and was "
                     "recovered by hand; the shipped Proto-X embedder does NOT contain "
                     "these columns, so a Proto-X harvest must restrict the space")
                    if self._malformed else None,
        }
        self._episode_id = self.episode.header["episode_id"]
        return self.observe_state()

    def restore_snapshot(self):
        """Cold reset. Stops the cluster, re-extracts pgdata, restarts."""
        pgd = fGENDBA_DATA + "/pgdata_ise"
        self.conn.close()
        subprocess.run([f"{PGBIN}/pg_ctl", "-D", pgd, "-m", "fast", "-w", "stop"],
                       capture_output=True)
        subprocess.run(["rm", "-rf", pgd], check=True)
        os.makedirs(pgd, mode=0o700)
        subprocess.run(["tar", "xf", f"{DATA}/{self.snapshot}", "-C", pgd,
                        "--strip-components", "1"], check=True)
        conf = f"{pgd}/postgresql.conf"
        body = [l for l in open(conf) if not re.match(r"^\s*port\s*=", l)]
        open(conf, "w").write("".join(body) + f"\nport = {self.port}\n")
        subprocess.run([f"{PGBIN}/pg_ctl", "-D", pgd, "-l", "/data/protox/pg_ise.log",
                        "-w", "-t", "300", "start"], check=True, capture_output=True)
        self.conn = psycopg2.connect(f"host=localhost port={self.port} dbname={self.dbname}")
        self.conn.autocommit = True
        self._primed = False        # cold restore drops the cache

    def observe_state(self) -> dict:
        """What the policy sees between actions (move 6)."""
        size = sum(a["size_bytes"] for a in self._applied)
        return {
            "episode_id": self._episode_id,
            "task": self.task.id(),
            "applied_indexes": [a["spec"] for a in self._applied],
            "storage_used_mb": round(size / 1024 / 1024, 1),
            "storage_budget_mb": self.task.budget_mb,
            "storage_remaining_mb": round(self.task.budget_mb - size / 1024 / 1024, 1),
            "tool_seconds_used": round(self._tool_s, 2),
            "tool_seconds_remaining": self.tool_budget_remaining,
            "n_calls": len(self.trajectory),
        }

    # ------------------------------------------------------------------- verbs
    def call(self, verb: str, args: dict | None = None) -> dict:
        """Single entry point. Mirrors how the policy will emit tool calls."""
        args = args or {}
        fn = {
            "CONNECT": self._connect, "HARVEST": self._harvest, "OBSERVE": self._observe,
            "PROBE": self._probe, "REALIZE": self._realize,
        }.get(verb.upper())
        if fn is None:
            raise ToolError(f"unknown verb {verb!r}; expected one of "
                            "CONNECT HARVEST OBSERVE PROBE REALIZE")
        if self.tool_budget_remaining <= 0:
            return {"ok": False, "error": "tool budget exhausted",
                    "state": self.observe_state()}
        t0 = time.time()
        try:
            out, move = fn(args)
            self._record(verb.upper(), args, t0, move, payload=out,
                         provenance=_provenance(out), produced_by=_producer(verb, out))
            return {"ok": True, "result": out, "state": self.observe_state()}
        except ToolError as e:
            self._record(verb.upper(), args, t0, "error", ok=False, error=str(e),
                         produced_by="environment")
            return {"ok": False, "error": str(e), "state": self.observe_state()}

    # CONNECT -- engine identity and knobs (move 1)
    def _connect(self, args):
        v = self._q("SELECT version()")[0][0]
        knobs = dict(self._q(
            "SELECT name, setting FROM pg_settings WHERE name IN "
            "('shared_buffers','work_mem','effective_cache_size','max_parallel_workers_per_gather',"
            "'random_page_cost','seq_page_cost')"))
        return {"engine": v.split(" on ")[0], "knobs": knobs,
                "extensions": [r[0] for r in self._q("SELECT extname FROM pg_extension")]}, "orient"

    # HARVEST -- schema and workload (move 1)
    def _harvest(self, args):
        what = args.get("what", "schema")
        if what == "schema":
            rows = self._q("""
                SELECT c.relname, c.reltuples::bigint, pg_relation_size(c.oid)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.reltuples DESC""")
            return {"tables": [{"table": r[0], "rows": r[1], "bytes": r[2],
                                "indexable_columns": self._attrs.get(r[0], [])}
                               for r in rows if r[0] in self._attrs]}, "orient"
        if what == "queries":
            qid = args.get("query")
            qs = [q for q in self.queries if qid is None or q["id"] == qid]
            return {"queries": [{"id": q["id"], "text": q["text"]} for q in qs]}, "orient"
        raise ToolError("HARVEST.what must be 'schema' or 'queries'")

    # OBSERVE -- statistics and current physical design (move 1)
    def _observe(self, args):
        what = args.get("what", "indexes")
        if what == "indexes":
            rows = self._q("""
                SELECT i.indexrelname, i.relname, i.idx_scan, pg_relation_size(i.indexrelid)
                FROM pg_stat_user_indexes i ORDER BY i.indexrelname""")
            return {"indexes": [{"index": r[0], "table": r[1], "scans": r[2],
                                 "bytes": r[3]} for r in rows]}, "orient"
        if what == "stats":
            tbl = args.get("table")
            where = f"AND tablename='{tbl}'" if tbl else ""
            rows = self._q(f"""
                SELECT tablename, attname, n_distinct, correlation, null_frac
                FROM pg_stats WHERE schemaname='public' {where}
                ORDER BY abs(n_distinct) DESC LIMIT 40""")
            return {"stats": [{"table": r[0], "column": r[1], "n_distinct": float(r[2]),
                               "correlation": float(r[3]) if r[3] is not None else None,
                               "null_frac": float(r[4])} for r in rows]}, "orient"
        raise ToolError("OBSERVE.what must be 'indexes' or 'stats'")

    # PROBE -- ask the engine a counterfactual (move 3), or measure reality (move 5)
    def _probe(self, args):
        what = args.get("what", "explain")
        if what == "explain":
            q = self._query(args.get("query"))
            _r = self._explain(q, analyze=False)
            if "explain_failed" in _r:
                return {"query": q["id"], "explain_failed": _r["explain_failed"],
                        "estimated": True, "measured": False}, "screen"
            plan = _r["Plan"]
            return {"query": q["id"], "total_cost": plan["Total Cost"],
                    "node": plan["Node Type"],
                    "estimated": True, "measured": False}, "screen"

        if what == "explain_analyze":
            q = self._query(args.get("query"))
            root = self._explain(q, analyze=True)
            if "explain_failed" in root:
                return {"query": q["id"], "explain_failed": root["explain_failed"],
                        "estimated": False, "measured": True}, "orient"
            nodes = _misestimates(root["Plan"])
            nodes.sort(key=lambda n: -n["misestimate_factor"])
            # The RAW plan is kept, not just the summary. Its per-node Plan Rows vs
            # Actual Rows is cardinality-estimation training data; a digest here would
            # silently throw that away (docs/training_record.md rule 2).
            return {"query": q["id"],
                    "plan": root["Plan"],
                    "execution_ms": round(root["Execution Time"], 1),
                    "planning_ms": round(root.get("Planning Time", 0), 3),
                    "worst_misestimates": nodes[:5],
                    "nodes_off_by_10x_or_more": sum(1 for n in nodes
                                                    if n["misestimate_factor"] >= 10),
                    "estimated": False, "measured": True}, "orient"

        if what == "whatif":
            # Hypothetical index + cost, session-local. This is the cheap tool the
            # reward deliberately does NOT use.
            specs = args.get("indexes") or []
            if not specs:
                raise ToolError("PROBE.whatif needs 'indexes': [{table, columns}]")
            with self.conn.cursor() as c:
                c.execute("SELECT hypopg_reset()")
                c.execute("SET hypopg.use_real_oids = on")
                created = []
                for s in specs:
                    self._validate(s)
                    ddl = f"CREATE INDEX ON {s['table']} ({','.join(s['columns'])})"
                    c.execute("SELECT indexrelid, indexname FROM hypopg_create_index(%s)", (ddl,))
                    oid, name = c.fetchone()
                    c.execute("SELECT hypopg_relation_size(%s)", (oid,))
                    created.append({"spec": s, "hypopg_name": name,
                                    "est_size_bytes": c.fetchone()[0]})
                per_q, total = [], 0.0
                for q in self._targets(args):
                    c.execute("EXPLAIN (FORMAT JSON) " + q["text"])
                    p = c.fetchone()[0][0]
                    txt = json.dumps(p)
                    used = [x["hypopg_name"] for x in created if x["hypopg_name"] in txt]
                    cost = p["Plan"]["Total Cost"]
                    total += cost
                    per_q.append({"query": q["id"], "total_cost": cost,
                                  "indexes_used": used})
                c.execute("SELECT hypopg_reset()")
            return {"candidates": created, "per_query": per_q,
                    "total_estimated_cost": round(total, 2),
                    "estimated": True, "measured": False,
                    "caveat": "PostgreSQL cost model; measured benefit has run "
                              "~2x larger than estimated on this workload"}, "screen"

        if what == "measure":
            per_q, protocol = self._measure(self._targets(args))
            total = round(sum(per_q.values()), 1)
            return {"per_query_ms": per_q, "workload_ms": total,
                    "protocol": protocol,
                    "estimated": False, "measured": True}, "verify"

        raise ToolError("PROBE.what must be 'explain', 'explain_analyze', 'whatif' or 'measure'")

    # REALIZE -- change the physical design for real (move 5/6)
    def _realize(self, args):
        action = args.get("action", "create_index")
        if action == "create_index":
            spec = {"table": args.get("table"), "columns": args.get("columns")}
            self._validate(spec)
            size = sum(a["size_bytes"] for a in self._applied) / 1024 / 1024
            name = (IDX_PREFIX + spec["table"] + "_" + "_".join(spec["columns"]))[:63]
            if any(a["name"] == name for a in self._applied):
                raise ToolError(f"index {name} already applied")
            with self.conn.cursor() as c:
                c.execute(f"CREATE INDEX {name} ON {spec['table']} "
                          f"({','.join(spec['columns'])})")
                c.execute("SELECT pg_relation_size(%s)", (name,))
                b = c.fetchone()[0]
            new_total = size + b / 1024 / 1024
            over = new_total > self.task.budget_mb
            self._applied.append({"name": name, "spec": spec, "size_bytes": b})
            return {"created": name, "size_mb": round(b / 1024 / 1024, 1),
                    "storage_used_mb": round(new_total, 1),
                    "over_budget": over}, "verify"

        if action == "drop_index":
            name = args.get("name")
            hit = [a for a in self._applied if a["name"] == name]
            if not hit:
                raise ToolError(f"{name} is not an index this episode created")
            self._q(f"DROP INDEX IF EXISTS {name}", fetch=False)
            self._applied.remove(hit[0])
            return {"dropped": name}, "verify"

        raise ToolError("REALIZE.action must be 'create_index' or 'drop_index'")

    # -------------------------------------------------------------- terminal
    def score(self, reference_speedup: float | None = None) -> dict:
        """
        Terminal, verifiable reward: measured wall-clock only.

        reward = speedup over this episode's own no-index baseline, with a hard
        penalty for exceeding the storage budget. When a reference policy's speedup
        on the same task is supplied (e.g. ISE Extend at the same budget), the
        advantage is relative to it -- which is what group-relative RL wants and
        what makes scores comparable across tasks of different difficulty.
        """
        if self._baseline_ms is None:
            raise ToolError("call baseline() before score()")
        after, protocol = self._measure(self.queries)
        before_total = round(sum(self._baseline_ms.values()), 1)
        after_total = round(sum(after.values()), 1)
        speedup = before_total / after_total if after_total else 0.0

        size_mb = sum(a["size_bytes"] for a in self._applied) / 1024 / 1024
        if self.task.constraint_kind == "max_indexes":
            over = len(self._applied) > self.task.constraint_value
        else:
            over = size_mb > self.task.constraint_value
        regressions = {q: round(after[q] - self._baseline_ms[q], 1)
                       for q in after if after[q] > self._baseline_ms[q] * 1.05}

        reward = 0.0 if over else speedup - 1.0
        out = {
            "episode_id": self._episode_id,
            "task": self.task.id(),
            "workload_ms_before": before_total,
            "workload_ms_after": after_total,
            "speedup": round(speedup, 4),
            "storage_used_mb": round(size_mb, 1),
            "over_budget": over,
            "reward": round(reward, 4),
            "per_query_regressions_ms": regressions,
            "n_indexes": len(self._applied),
            "indexes": [a["spec"] for a in self._applied],
            "tool_seconds_used": round(self._tool_s, 2),
            "protocol": protocol,
        }
        if reference_speedup:
            out["reference_speedup"] = reference_speedup
            out["advantage"] = round(speedup - reference_speedup, 4)
            out["normalized_reward"] = round((speedup - reference_speedup)
                                             / max(reference_speedup - 1.0, 1e-6), 4)
        # Terminal is measured, and says so. `reward` is a RECORDED FIELD here, not an
        # objective the collection is shaped around (docs/training_record.md §4).
        self.episode.finish(
            configuration=[a["spec"] for a in self._applied],
            measured={"workload_ms_before": before_total,
                      "workload_ms_after": after_total,
                      "speedup": round(speedup, 4),
                      "per_query_ms_before": self._baseline_ms,
                      "per_query_ms_after": after,
                      "per_query_regressions_ms": regressions,
                      "failed_queries": protocol.get("failed", {}),
                      "provenance": MEASURED,
                      "protocol": protocol},
            storage={"used_mb": round(size_mb, 1),
                     "n_indexes": len(self._applied),
                     "provenance": MEASURED},
            constraint={"kind": self.task.constraint_kind,
                        "value": self.task.constraint_value,
                        "observed": (len(self._applied)
                                     if self.task.constraint_kind == "max_indexes"
                                     else round(size_mb, 1)),
                        "violated": over,
                        "sweep_budget_mb_declared": self.task.budget_mb,
                        "note": "reward is penalised only against the constraint the "
                                "policy actually received"},
            reward=out.get("reward"),
            reference_speedup=reference_speedup,
            advantage=out.get("advantage"),
            tool_seconds_used=round(self._tool_s, 2))
        self._closed = True
        return out

    def prime(self):
        """
        Warm the cache once per cluster, before any baseline is taken.

        Without this the first measurement after a snapshot restore is cold while
        every later one is warm, which credits ~10% of free 'speedup' to doing
        nothing -- measured: a no-op episode scored 1.0967x on a freshly restored
        cluster versus 1.011x on a warm one. noise.py did not catch this because it
        ran against an already-warm cluster.

        Priming once per cluster (not per measurement) keeps episodes cheap: DDL
        reset leaves the cache warm, so the cost is paid only after a cold restore.
        """
        if self._primed:
            return
        # Priming RUNS the workload, so on a write workload it mutates too -- and it
        # runs before the baseline, meaning anything it left behind would be measured
        # as part of the starting state. Same protocol as _measure: do it inside a
        # transaction and throw the transaction away.
        mutating = self.task.benchmark in MUTATING
        with self.conn.cursor() as c:
            c.execute(f"SET statement_timeout = '{int(self.query_timeout_s * 1000)}'")
            if mutating:
                c.execute("BEGIN")
            for q in self.queries:
                try:
                    if mutating:
                        c.execute("SAVEPOINT gendba_prime")
                    _run(c, q["text"])
                    if mutating:
                        c.execute("RELEASE SAVEPOINT gendba_prime")
                except Exception:
                    try:
                        if mutating:
                            c.execute("ROLLBACK TO SAVEPOINT gendba_prime")
                        else:
                            self.conn.rollback()
                    except Exception:
                        raise      # connection is gone; priming cannot continue
            if mutating:
                c.execute("ROLLBACK")
            c.execute("SET statement_timeout = 0")
        self._primed = True

    def baseline(self) -> dict:
        """Measure the starting state. Charged to the tool budget like anything else."""
        self.prime()
        t0 = time.time()
        self._baseline_ms, protocol = self._measure(self.queries)
        total = round(sum(self._baseline_ms.values()), 1)
        self._record("PROBE", {"what": "measure", "scope": "baseline"}, t0, "orient",
                     payload={"per_query_ms": self._baseline_ms, "workload_ms": total,
                              "protocol": protocol, "measured": True},
                     provenance=MEASURED, produced_by="postgresql-executor")
        return {"workload_ms": total, "per_query_ms": self._baseline_ms,
                "protocol": protocol}

    # ------------------------------------------------------------------ internals
    def _explain(self, q, analyze):
        """
        EXPLAIN the query's SELECT. Multi-statement entries (TPC-H Q15 creates a view,
        selects from it, then drops it) need the setup run first and the teardown run
        after, or the SELECT has nothing to read and the view leaks into later queries.
        """
        stmts = _statements(q["text"])
        i = _explainable(stmts)
        mode = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"
        # EXPLAIN ANALYZE executes the statement, so on a write workload it is itself a
        # mutation -- and _explainable falls through to the last statement when there is
        # no SELECT, which for TPC-C means we would be EXPLAIN ANALYZEing an INSERT with
        # a literal primary key. Confine it to a transaction that is thrown away.
        # Plain EXPLAIN does not execute, so it needs no such protection.
        wrap = analyze and self.task.benchmark in MUTATING
        with self.conn.cursor() as c:
            # EXPLAIN ANALYZE actually EXECUTES the query, so it needs the same cap as
            # a measurement. Without it this path ran DSB Q23 for 363s against a 30s
            # timeout -- a third of the episode -- and left uncapped orient cost in the
            # record, corrupting the tool-time signal we deliberately collect.
            c.execute(f"SET statement_timeout = '{int(self.query_timeout_s * 1000)}'")
            if wrap:
                c.execute("BEGIN")
            try:
                for st in stmts[:i]:
                    c.execute(st)
                c.execute(f"EXPLAIN ({mode}) " + stmts[i])
                root = c.fetchone()[0][0]
                for st in stmts[i + 1:]:
                    c.execute(st)
                if wrap:
                    c.execute("ROLLBACK")
            except Exception as e:
                self.conn.rollback()
                timed_out = "statement timeout" in str(e).lower()
                # a labelled outcome, never a silent gap
                return {"Plan": {"Node Type": "NotExplained"},
                        "explain_failed": {
                            "outcome": "timeout" if timed_out else "error",
                            "limit_s": self.query_timeout_s,
                            "detail": str(e).strip().splitlines()[0][:200]}}
            finally:
                try:
                    c.execute("SET statement_timeout = 0")
                except Exception:
                    pass
        return root

    def _targets(self, args):
        qids = args.get("queries")
        if not qids:
            return self.queries
        sel = [q for q in self.queries if q["id"] in set(qids)]
        if not sel:
            raise ToolError(f"no such queries: {qids}")
        return sel

    def _query(self, qid):
        if qid is None:
            raise ToolError("needs 'query': <query id>")
        for q in self.queries:
            if q["id"] == qid:
                return q
        raise ToolError(f"no such query {qid!r}")

    def _validate(self, spec):
        t, cols = spec.get("table"), spec.get("columns")
        if not t or not cols:
            raise ToolError("index spec needs {'table':..., 'columns':[...]}")
        if t not in self._attrs:
            raise ToolError(f"unknown table {t!r}")
        if len(cols) > self.task.max_index_width:
            raise ToolError(f"index width {len(cols)} exceeds max "
                            f"{self.task.max_index_width}")
        bad = [c for c in cols if c not in self._attrs[t]]
        if bad:
            raise ToolError(f"columns not indexable on {t}: {bad}")
        if len(set(cols)) != len(cols):
            raise ToolError("duplicate columns in index")

    def _measure(self, queries):
        """
        Fixed protocol: warmup, then median of N, with a per-query statement timeout.

        A query that times out or errors is recorded as a LABELLED OUTCOME in
        `failed`, never as a missing value -- otherwise a later reader cannot tell
        "genuinely slow" from "broke mid-measurement" without re-running everything.
        """
        out, failed = {}, {}
        mutating = self.task.benchmark in MUTATING
        with self.conn.cursor() as c:
            c.execute(f"SET statement_timeout = '{int(self.query_timeout_s * 1000)}'")
            if mutating:
                c.execute("BEGIN")
                # The warmup writes too, and its rows stay visible to the measured
                # passes unless undone -- which is how the first measured pass hit a
                # duplicate key on the very rows the warmup had just inserted.
                c.execute("SAVEPOINT gendba_warmpass")
            for _ in range(self.measure_warmup):
                for q in queries:
                    try:
                        if mutating:
                            c.execute("SAVEPOINT gendba_warm")
                        _run(c, q["text"])
                        if mutating:
                            c.execute("RELEASE SAVEPOINT gendba_warm")
                    except Exception:
                        # A failed statement aborts the WHOLE transaction in
                        # PostgreSQL, so on a mutating workload one bad statement
                        # would poison the remaining 32. The savepoint confines it.
                        if mutating:
                            c.execute("ROLLBACK TO SAVEPOINT gendba_warm")
                        else:
                            self.conn.rollback()
            if mutating:
                c.execute("ROLLBACK TO SAVEPOINT gendba_warmpass")
            def note_failure(qid, e, t):
                timed_out = "statement timeout" in str(e).lower()
                failed[qid] = {
                    "outcome": "timeout" if timed_out else "error",
                    "limit_s": self.query_timeout_s,
                    "elapsed_ms": round((time.time() - t) * 1000, 1),
                    "detail": str(e).strip().splitlines()[0][:200],
                    "censored_at_ms": self.query_timeout_s * 1000,
                }

            runs_by_q = {q["id"]: [] for q in queries}
            if mutating:
                # PASS-outer, not query-outer. A mutating workload's repeats must each
                # start from the same state: TPC-C's statements carry literal primary
                # keys, so running one twice in a row is a duplicate-key violation --
                # the workload conflicts with ITSELF. Rolling back to a pass savepoint
                # makes every pass identical.
                #
                # The order within a pass is preserved rather than isolating each
                # statement, because these are transaction FRAGMENTS with real
                # dependencies (new_order references the row oorder inserts), and
                # measuring them independently would model a workload nobody runs.
                for _ in range(max(1, self.measure_repeats)):
                    c.execute("SAVEPOINT gendba_pass")
                    for q in queries:
                        t = time.time()
                        try:
                            c.execute("SAVEPOINT gendba_q")
                            _run(c, q["text"])
                            runs_by_q[q["id"]].append((time.time() - t) * 1000)
                            c.execute("RELEASE SAVEPOINT gendba_q")
                        except Exception as e:
                            c.execute("ROLLBACK TO SAVEPOINT gendba_q")
                            note_failure(q["id"], e, t)
                    c.execute("ROLLBACK TO SAVEPOINT gendba_pass")
            else:
                for q in queries:
                    for _ in range(self.measure_repeats):
                        t = time.time()
                        try:
                            _run(c, q["text"])
                            runs_by_q[q["id"]].append((time.time() - t) * 1000)
                        except Exception as e:
                            self.conn.rollback()
                            note_failure(q["id"], e, t)
                            break

            for q in queries:
                runs = runs_by_q[q["id"]]
                if runs:
                    out[q["id"]] = round(sorted(runs)[len(runs) // 2], 1)
                elif failed.get(q["id"], {}).get("outcome") == "timeout":
                    # censored, not missing: keeps before/after over one query set.
                    # The limit is a genuine LOWER BOUND -- the query really did run
                    # at least that long.
                    out[q["id"]] = round(self.query_timeout_s * 1000, 1)
                else:
                    # An error is not a timeout. Crediting the timeout limit to a
                    # statement that failed in a millisecond invents workload that
                    # never ran: three TPC-C errors became 900s of a 900s "workload",
                    # swamping every real measurement in it. Charge what it actually
                    # cost before failing, and let `failed` carry the reason.
                    out[q["id"]] = round(
                        failed.get(q["id"], {}).get("elapsed_ms", 0.0), 1)
            if mutating:
                # Undo everything this measurement did. Without it the database drifts
                # between the before and after measurement and the speedup is not a
                # speedup -- which is the entire reason a write workload needs its own
                # protocol.
                c.execute("ROLLBACK")
            c.execute("SET statement_timeout = 0")
        return out, {"warmup": self.measure_warmup, "repeats": self.measure_repeats,
                     "statistic": "median", "cache": "warm",
                     "query_timeout_s": self.query_timeout_s,
                     "censoring": "queries that time out contribute query_timeout_s "
                                  "to the workload total and are listed in `failed`; "
                                  "totals are therefore lower bounds on the true cost",
                     "censored_queries": sorted(failed),
                     "failed": failed}

    def dump(self, path, extra=None):
        if extra:
            self.episode.terminal.update(extra)
        self.episode.header["tool_vocabulary"] = [
            "CONNECT", "HARVEST", "OBSERVE", "PROBE", "REALIZE"]
        return self.episode.write(path)


def _statements(text):
    """Split a workload entry into individual SQL statements."""
    return [p.strip() for p in text.split(";") if p.strip()]


def _explainable(stmts):
    """Index of the statement EXPLAIN should target: the last SELECT/WITH."""
    for i in range(len(stmts) - 1, -1, -1):
        if re.match(r"^\s*(select|with)\b", stmts[i], re.I):
            return i
    return len(stmts) - 1


def _run(cur, text):
    """
    Execute a workload entry. psycopg2 runs every statement in the string, and
    `description` describes the LAST one -- which is None for a trailing DROP VIEW.
    Fetch only when there is a result set to fetch.
    """
    cur.execute(text)
    if cur.description is not None:
        cur.fetchall()


def _provenance(out):
    """
    Read provenance off the payload rather than guessing. Tool handlers set explicit
    `estimated` / `measured` flags; anything else is a factual read of catalog state.
    """
    if isinstance(out, dict):
        if out.get("measured"):
            return MEASURED
        if out.get("estimated"):
            return ESTIMATED
    return MEASURED


def _producer(verb, out):
    if isinstance(out, dict) and out.get("estimated"):
        return "postgresql-cost-model"
    return {"CONNECT": "postgresql-catalog", "HARVEST": "postgresql-catalog",
            "OBSERVE": "postgresql-statistics", "PROBE": "postgresql",
            "REALIZE": "postgresql-executor"}.get(verb.upper(), "postgresql")


def _misestimates(plan, acc=None):
    if acc is None:
        acc = []
    est, act = plan.get("Plan Rows"), plan.get("Actual Rows")
    loops = plan.get("Actual Loops", 1) or 1
    if est is not None and act is not None:
        a = act * loops
        f = (max(est, 1) / max(a, 1)) if est >= a else (max(a, 1) / max(est, 1))
        acc.append({"node": plan.get("Node Type"), "relation": plan.get("Relation Name"),
                    "estimated_rows": est, "actual_rows": a,
                    "misestimate_factor": round(f, 1),
                    "direction": "over" if est > a else ("under" if est < a else "exact")})
    for s in plan.get("Plans", []):
        _misestimates(s, acc)
    return acc
