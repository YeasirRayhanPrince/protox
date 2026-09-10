#!/usr/bin/env python3
"""
record.py -- the Gen-DBA training record.

PRINCIPLE: capture losslessly, project later.

We do not know which post-training recipe these episodes will feed. They must serve
Base-SFT, Tool-SFT, preference optimisation, RL replay, and analysis -- and, because
EXPLAIN ANALYZE payloads carry per-node estimated-vs-actual rows, cardinality
estimation as well. So the record is a superset: a header, a lossless event stream,
and a terminal summary. Every downstream format is a projection of it (see
docs/training_record.md), and no projection is baked in at collection time.

Three rules the schema enforces:

  1. PROVENANCE ON EVERY VALUE. Nothing is stored without saying where it came from:
     `estimated` (a model's opinion -- e.g. PostgreSQL's cost model, which we have
     measured understating benefit by ~2x) vs `measured` (wall clock), and which
     component produced it. Conflating these is the single most damaging thing we
     could do to the corpus.

  2. RAW PAYLOADS ARE KEPT. Full EXPLAIN JSON, full tool responses. A digest is a
     guess about what a future consumer needs.

  3. ABSENT IS NOT INFERRED. A move a system does not perform is recorded as absent
     with a reason, never synthesised. Contradictory supervision degrades a mix out
     of proportion to its share of it.

Layout:
    header      identity, environment fingerprint, task, policy, workload
    events[]    ordered, lossless: tool calls, decisions, state transitions
    terminal    final configuration and measured outcome
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

import hashlib
import json
import os
import platform
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"

# The six moves (docs/dba_loop.md). Every event is attributed to exactly one.
MOVES = ("orient", "hypothesize", "screen", "decide", "apply", "verify", "state", "error")

# Provenance of a value. Never mix these in one field.

ESTIMATED = "estimated"    # a model's opinion: cost model, hypopg size, planner rows
MEASURED = "measured"      # wall clock, actual rows, real index size
DERIVED = "derived"        # computed from other recorded values; carries its inputs
DECLARED = "declared"      # supplied by configuration, not observed


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def _git_commit(repo: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


@dataclass
class Event:
    """One thing that happened. Payload is stored whole."""
    i: int
    move: str
    kind: str                        # tool_call | decision | state | note
    t_offset_s: float                # since episode start
    duration_s: float | None = None  # cost of this event, for tool calls
    verb: str | None = None          # CONNECT/HARVEST/OBSERVE/PROBE/REALIZE
    args: dict = field(default_factory=dict)
    payload: Any = None              # FULL response, not a digest
    provenance: str | None = None    # ESTIMATED / MEASURED / DERIVED / DECLARED
    produced_by: str | None = None   # which component asserted this
    ok: bool = True
    error: str | None = None
    note: str | None = None


class Episode:
    def __init__(self, task: dict, policy: dict, collector: str,
                 repo: str = GENDBA_REPO):
        self.t0 = time.time()
        self.repo = repo
        self.header = {
            "schema_version": SCHEMA_VERSION,
            "episode_id": f"{task.get('id', 'episode')}-{uuid.uuid4().hex[:8]}",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "collector": collector,
            "git_commit": _git_commit(repo),
            "task": task,
            "policy": policy,
            "environment": {},
            "workload": {},
            "initial_state": {},
        }
        self.events: list[Event] = []
        self.terminal: dict = {}

    # ------------------------------------------------------------------ header
    def fingerprint_environment(self, conn, snapshot=None):
        """
        Everything needed to interpret -- or reproduce -- this episode. Without it a
        measured latency is an uninterpretable number.
        """
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        cur.execute("SELECT extname, extversion FROM pg_extension ORDER BY extname")
        exts = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("""SELECT name, setting, unit FROM pg_settings WHERE name IN
            ('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
             'max_parallel_workers','max_parallel_workers_per_gather','random_page_cost',
             'seq_page_cost','jit','max_wal_size','autovacuum','effective_io_concurrency')""")
        knobs = {r[0]: (f"{r[1]}{r[2] or ''}") for r in cur.fetchall()}
        cur.execute("""SELECT count(*), coalesce(max(last_analyze), max(last_autoanalyze))
                       FROM pg_stat_user_tables""")
        ntab, last_analyze = cur.fetchone()

        # A caller with no restore tarball may pass a descriptor instead of a path,
        # so "which state did this episode start from" is answered explicitly rather
        # than left as a bare None that reads as "not recorded".
        snap = None
        if isinstance(snapshot, dict):
            snap = snapshot
        elif snapshot and os.path.exists(snapshot):
            st = os.stat(snapshot)
            snap = {"path": snapshot, "size_bytes": st.st_size,
                    "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()}

        self.header["environment"] = {
            "engine": {"name": "postgresql",
                       "version": version.split()[1],
                       "version_string": version,
                       "extensions": exts,
                       "knobs": knobs},
            "hardware": {"cpu_model": _cpu_model(), "cores": os.cpu_count(),
                         "memory_gb": _mem_gb(), "kernel": platform.release(),
                         "os": _os_pretty()},
            "snapshot": snap,
            "concurrency": {"episodes_in_parallel": _int_env("GENDBA_PARALLEL", 1),
                            "isolation": os.environ.get("GENDBA_ISOLATION",
                                                        "dedicated_cluster_sequential"),
                            "loadavg_1m_at_start": _loadavg()},
            "statistics": {"tables": ntab,
                           "last_analyze_utc": last_analyze.isoformat() if last_analyze else None},
        }

    def set_workload(self, queries: list[dict], grouping_key: str = "template"):
        """
        Full SQL text is kept -- a query id is meaningless to a future consumer.

        GROUPING KEY, decided before harvest and stamped on every query. JOB ships
        query families: 1.sql / 1b.sql / 1c.sql / 1d.sql share joins and tables and
        differ only in predicate constants. Splitting train/eval per QUERY leaks
        near-duplicates across the split; the unit that must not be split is the
        TEMPLATE. Our 25-query JOB workload is really 7 templates -- a fact a
        consumer cannot recover later unless we record it now.
        """
        qs = []
        for q in queries:
            tmpl = _template_of(q.get("file") or q["id"])
            qs.append({"id": q["id"], "file": q.get("file"),
                       "template": tmpl, "sql": q["text"],
                       "sql_sha1": _sha1(q["text"])})
        self.header["workload"] = {
            "n_queries": len(qs),
            "grouping_key": grouping_key,
            "n_groups": len({q["template"] for q in qs}),
            "groups": sorted({q["template"] for q in qs}),
            "split_warning": ("queries sharing a template are near-duplicates; "
                              "train/eval splits MUST be taken on `template`, not `id`"),
            "queries": qs,
        }

    def set_initial_state(self, conn):
        cur = conn.cursor()
        # public only: pg_hint_plan keeps its own catalog in the hint_plan schema,
        # and counting those indexes mislabels a PK-only base as "configured".
        cur.execute("""
            SELECT i.indexrelname, i.relname, pg_relation_size(i.indexrelid), pg_get_indexdef(i.indexrelid)
            FROM pg_stat_user_indexes i WHERE i.schemaname='public'
            ORDER BY i.indexrelname""")
        idx = [{"index": r[0], "table": r[1], "bytes": r[2], "definition": r[3]}
               for r in cur.fetchall()]
        cur.execute("""
            SELECT c.relname, c.reltuples::bigint, pg_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname""")
        tabs = [{"table": r[0], "rows": r[1], "bytes": r[2]} for r in cur.fetchall()]
        self.header["initial_state"] = {
            "indexes": idx,
            "n_primary_keys": sum(1 for i in idx if i["index"].endswith("_pkey")),
            "n_secondary": sum(1 for i in idx if not i["index"].endswith("_pkey")),
            "kind": "pk_only" if all(i["index"].endswith("_pkey") for i in idx) else "configured",
            "tables": tabs,
        }

    # ------------------------------------------------------------------ events
    def add(self, move: str, kind: str, **kw) -> Event:
        assert move in MOVES, f"unknown move {move!r}"
        e = Event(i=len(self.events), move=move, kind=kind,
                  t_offset_s=round(time.time() - self.t0, 4), **kw)
        self.events.append(e)
        return e

    def tool_call(self, verb, args, payload, duration_s, move, provenance,
                  produced_by, ok=True, error=None):
        return self.add(move, "tool_call", verb=verb, args=args, payload=payload,
                        duration_s=round(duration_s, 4), provenance=provenance,
                        produced_by=produced_by, ok=ok, error=error)

    def decision(self, move="decide", **payload):
        """
        A decision keeps proposed / accepted / rejected as distinct roles, each with
        the quantity that discriminated it. Flattening them loses the alternatives;
        recording them all as decisions is self-contradictory.
        """
        return self.add(move, "decision", payload=payload, produced_by="policy")

    def absent(self, move: str, reason: str, produced_by: str):
        """A move the system genuinely does not perform. Recorded, never invented."""
        return self.add(move, "note", payload={"emitted": False, "reason": reason},
                        produced_by=produced_by)

    # ---------------------------------------------------------------- terminal
    def finish(self, **payload):
        payload.setdefault("wall_clock_s", round(time.time() - self.t0, 2))
        self.terminal = payload
        return payload

    # ------------------------------------------------------------------- write
    def to_dict(self):
        return {**self.header,
                "events": [asdict(e) for e in self.events],
                "terminal": self.terminal,
                "event_count": len(self.events),
                "moves_present": sorted({e.move for e in self.events})}

    def write(self, path):
        """
        Write atomically: serialise to a temp file in the same directory, fsync, then
        rename. A harvest killed at the deadline (or by any other signal) must leave
        either a complete record or none -- never a truncated one that the gate would
        report as UNREADABLE and a consumer might half-parse.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".partial"
        with open(tmp, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # atomic on the same filesystem
        return path


# ------------------------------------------------------------------ helpers
def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _loadavg():
    """Contention on a shared host changes the numbers; record it or isolate."""
    try:
        return round(os.getloadavg()[0], 2)
    except Exception:
        return None


def _template_of(fname: str) -> str:
    """JOB: '1b.sql' -> '1'. TPC-H/DSB ids are already one query per template."""
    import re as _re
    base = fname.rsplit("/", 1)[-1]
    base = _re.sub(r"\.sql$", "", base)
    m = _re.match(r"^(\d+)[a-z]*$", base)
    if m:
        return m.group(1)
    m = _re.match(r"^query(\d+)", base)
    return m.group(1) if m else base


def _cpu_model():
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def _mem_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                return round(int(line.split()[1]) / 1024 / 1024, 1)
    except Exception:
        return None


def _os_pretty():
    try:
        for line in open("/etc/os-release"):
            if line.startswith("PRETTY_NAME"):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        return platform.platform()


# ===========================================================================
# PROJECTIONS -- derived views. None of these are stored; all are recomputable.
# They exist to prove the record is a superset of what each recipe needs.
# ===========================================================================
def project_tool_sft(ep: dict) -> dict:
    """⟨prompt, tool-call, tool-response, ..., output⟩ for Tool-SFT."""
    turns = []
    for e in ep["events"]:
        if e["kind"] == "tool_call" and e["ok"]:
            turns.append({"role": "tool_call", "verb": e["verb"], "args": e["args"]})
            turns.append({"role": "tool_response", "content": e["payload"],
                          "provenance": e["provenance"]})
    return {"episode_id": ep["episode_id"],
            "task": ep["task"], "turns": turns,
            "output": ep["terminal"].get("configuration")}


def project_preference_pairs(ep: dict) -> list[dict]:
    """
    ⟨preferred, rejected⟩ from decision events. Each pair carries the discriminating
    quantity AND its provenance, so a consumer can filter to measured-only pairs --
    which matters, because estimated margins come from a cost model we have measured
    to be systematically off.
    """
    # Adjudicated near-misses live in their own event (one source of truth); index
    # them by (iteration, index spec) so a rejected candidate can be upgraded from an
    # ESTIMATED margin to a MEASURED verdict.
    adj = {}
    final_ms = ((ep.get("terminal") or {}).get("measured") or {}).get("workload_ms_after")
    for e in ep["events"]:
        pl = e.get("payload") or {}
        if e["kind"] == "decision" and pl.get("kind") == "top_k_adjudication":
            for a in pl.get("results", []):
                if a.get("outcome") == "error":
                    continue
                key = (a["iteration"], a["swapped_in"]["table"],
                       tuple(a["swapped_in"]["columns"]))
                adj[key] = a

    pairs = []
    for e in ep["events"]:
        if e["kind"] != "decision":
            continue
        p = e["payload"]
        if p.get("kind") == "top_k_adjudication":
            continue
        acc = p.get("accepted")
        if not acc:
            continue
        for rej in p.get("rejected", []):
            spec = rej.get("spec") or {}
            key = (p.get("iteration"), spec.get("table"), tuple(spec.get("columns", [])))
            a = adj.get(key)
            pair = {
                "episode_id": ep["episode_id"], "iteration": p.get("iteration"),
                "context": {"state": p.get("state_before"), "task": ep["task"]},
                "preferred": acc, "rejected": rej,
                "discriminant": rej.get("discriminant") or p.get("discriminant"),
                "margin": rej.get("margin"),
                "margin_provenance": rej.get("margin_provenance", ESTIMATED),
            }
            if a and final_ms:
                # Measured verdict overrides the cost model's opinion. A positive
                # measured_margin_ms means rejecting really was right.
                pair["measured_margin_ms"] = round(a["measured_workload_ms"] - final_ms, 1)
                pair["margin_provenance"] = MEASURED
                pair["cost_model_was_right"] = a["measured_workload_ms"] > final_ms
                pair["measured"] = {"swapped_in_workload_ms": a["measured_workload_ms"],
                                    "accepted_workload_ms": final_ms,
                                    "protocol": a.get("protocol")}
            pairs.append(pair)
    return pairs


def project_cardinality(ep: dict) -> list[dict]:
    """
    Cardinality-estimation examples, free of charge: any EXPLAIN ANALYZE payload
    holds per-node estimated vs actual rows. This is why raw payloads are kept.
    """
    out = []
    for e in ep["events"]:
        if e["kind"] != "tool_call" or e["provenance"] != MEASURED:
            continue
        payload = e["payload"]
        if not isinstance(payload, dict) or "plan" not in payload:
            continue
        for node in _walk(payload["plan"]):
            if node.get("Plan Rows") is not None and node.get("Actual Rows") is not None:
                loops = node.get("Actual Loops", 1) or 1
                out.append({
                    "episode_id": ep["episode_id"],
                    "query": payload.get("query"),
                    "node_type": node.get("Node Type"),
                    "relation": node.get("Relation Name"),
                    "filter": node.get("Filter") or node.get("Index Cond")
                              or node.get("Hash Cond") or node.get("Join Filter"),
                    "estimated_rows": node["Plan Rows"],
                    "actual_rows": node["Actual Rows"] * loops,
                })
    return out


def project_outcome(ep: dict) -> dict:
    """Measured result only -- for evaluation and for RL reward replay."""
    t = ep["terminal"]
    return {"episode_id": ep["episode_id"], "task": ep["task"],
            "policy": ep["policy"], "measured": t.get("measured"),
            "configuration": t.get("configuration")}


def _walk(plan, acc=None):
    if acc is None:
        acc = []
    acc.append(plan)
    for s in plan.get("Plans", []):
        _walk(s, acc)
    return acc


# ===========================================================================
# ONE SOURCE OF TRUTH for the indexable action space.
#
# configs/benchmark/dsb_*.yaml write web_returns' column list with "_" instead of "-"
# as the YAML list marker, so PyYAML yields one string instead of 24 column names.
# Both the producer (env.py) and the gate (validate.py) must recover them the same
# way -- when only the producer did, the gate quarantined every DSB episode whose
# policy legitimately chose a web_returns index.
#
# Do NOT fix the YAML: the shipped Proto-X embedder's action space excludes these
# columns, and changing the file would break its compatibility.
# ===========================================================================
def indexable_columns(benchmark_config_path):
    """{table: [columns]} for a benchmark, with malformed YAML lists recovered."""
    import yaml as _yaml
    attrs = _yaml.safe_load(open(benchmark_config_path))["mythril"]["attributes"]
    out, recovered = {}, []
    for t, c in attrs.items():
        if isinstance(c, str):
            recovered.append(t)
            out[t] = [x for x in c.split() if x != "_"]
        else:
            out[t] = list(c)
    return out, sorted(recovered)
