#!/usr/bin/env python3
"""
qo_harvest.py -- query-optimization episodes, driven by us rather than by a learned policy.

We are the policy. For one query we force PostgreSQL to produce plans other than the
one it chose, measure them, and record which was actually fastest. That is the same
data Bao and Auto-Steer collect; the learning is theirs, the collection is ours, and
`pg_hint_plan` is already installed on every cluster so it needs no new environment.

WHY THIS SHAPE. The paper's QO output is a plan injected through pg_hint_plan
(cidr27_gendba.md §2.2 INJECT, §5). So an episode's target here is
⟨query, plan-in-hint-grammar, measured latency⟩ -- the training pair in its deployed
form, not a proxy for it.

ENUMERATION. The 12 enable_* flags give 2^12 combinations, almost all irrelevant to
any given query. Auto-Steer's insight is that only a handful actually change a given
query's plan, so:

    1. probe each flag alone   -- does turning it off change the plan?   (12 EXPLAINs)
    2. keep only the flags that did                                       ("effective")
    3. enumerate subsets of those, capped                                 (estimated)
    4. MEASURE the default plan plus the top-k distinct candidates        (wall clock)

Steps 1-3 are estimated and cost ~4 ms each. Step 4 is the only expensive part, and it
is the only part the reward is taken from -- the same estimated/measured split the
index-selection harvest uses, for the same reason: we have measured this cost model
understating benefit by ~2x.

Move 2 (hypothesize) is GROUNDED here rather than absent. A node where the planner
expected 1 row and got 785,477 is a real, measured reason to distrust the join order it
chose -- unlike the ISE algorithms, which form no hypothesis at all.
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

import argparse
import hashlib
import itertools
import json
import os
import sys
import time

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")

import psycopg2  # noqa: E402
import record as rec  # noqa: E402
from record import Episode, ESTIMATED, MEASURED  # noqa: E402
from env import BENCHMARKS, REPO, DATA, _statements, _explainable, _misestimates  # noqa: E402
import validate as gate  # noqa: E402

# The rules Auto-Steer probes for PostgreSQL (Auto-Steer/knobs/postgres.txt).

RULES = ["enable_bitmapscan", "enable_gathermerge", "enable_hashagg", "enable_hashjoin",
         "enable_indexonlyscan", "enable_indexscan", "enable_material",
         "enable_mergejoin", "enable_nestloop", "enable_parallel_hash",
         "enable_seqscan", "enable_sort"]


def plan_shape(node) -> str:
    """
    Structural fingerprint of a plan: node types and scanned relations, ignoring costs
    and row estimates. Two plans with the same shape are the same strategy.
    """
    parts = [node.get("Node Type", "")]
    if node.get("Relation Name"):
        parts.append(node["Relation Name"])
    for s in node.get("Plans", []):
        parts.append(plan_shape(s))
    return "(" + " ".join(parts) + ")"


def shape_hash(node) -> str:
    return hashlib.sha1(plan_shape(node).encode()).hexdigest()[:12]


class QOEnv:
    def __init__(self, benchmark, port=5492, dbname="benchbase", query_timeout_s=60):
        cfg, qdir, qorder, snap = BENCHMARKS[benchmark]
        self.benchmark, self.snapshot = benchmark, snap
        self.port, self.dbname = port, dbname
        self.query_timeout_s = query_timeout_s
        self.queries = self._load(qdir, qorder)
        self.conn = psycopg2.connect(f"host=localhost port={port} dbname={dbname}")
        self.conn.autocommit = True
        with self.conn.cursor() as c:
            c.execute("SET lock_timeout='120s'")
            c.execute("LOAD 'pg_hint_plan'")

    def _load(self, qdir, qorder):
        out = []
        for line in open(f"{REPO}/{qorder}"):
            if not line.strip():
                continue
            qid, fname = line.strip().split(",")[:2]
            out.append({"id": qid, "file": fname,
                        "text": open(f"{REPO}/{qdir}/{fname}").read().strip().rstrip(";")})
        return out

    # ---- primitives -----------------------------------------------------
    def _with_flags(self, c, off):
        for r in RULES:
            c.execute(f"SET {r} = {'off' if r in off else 'on'}")

    def explain(self, q, off=(), analyze=False):
        """EXPLAIN the query's SELECT with the given rules disabled."""
        stmts = _statements(q["text"])
        i = _explainable(stmts)
        mode = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"
        with self.conn.cursor() as c:
            c.execute(f"SET statement_timeout='{int(self.query_timeout_s*1000)}'")
            self._with_flags(c, set(off))
            try:
                for st in stmts[:i]:
                    c.execute(st)
                c.execute(f"EXPLAIN ({mode}) " + stmts[i])
                root = c.fetchone()[0][0]
                for st in stmts[i+1:]:
                    c.execute(st)
                return root
            except Exception as e:
                self.conn.rollback()
                return {"explain_failed": {
                    "outcome": "timeout" if "statement timeout" in str(e).lower() else "error",
                    "limit_s": self.query_timeout_s,
                    "detail": str(e).strip().splitlines()[0][:200]}}
            finally:
                try:
                    self._with_flags(c, set())
                    c.execute("SET statement_timeout=0")
                except Exception:
                    pass

    def measure(self, q, off=(), repeats=3):
        """Median wall clock over `repeats` executions with the given rules disabled."""
        stmts = _statements(q["text"])
        runs, failed = [], None
        with self.conn.cursor() as c:
            c.execute(f"SET statement_timeout='{int(self.query_timeout_s*1000)}'")
            self._with_flags(c, set(off))
            for _ in range(repeats):
                t = time.time()
                try:
                    for st in stmts:
                        c.execute(st)
                        if c.description is not None:
                            c.fetchall()
                    runs.append((time.time() - t) * 1000)
                except Exception as e:
                    self.conn.rollback()
                    failed = {"outcome": "timeout" if "statement timeout" in str(e).lower()
                              else "error",
                              "limit_s": self.query_timeout_s,
                              "detail": str(e).strip().splitlines()[0][:200],
                              "censored_at_ms": self.query_timeout_s * 1000}
                    break
            try:
                self._with_flags(c, set())
                c.execute("SET statement_timeout=0")
            except Exception:
                pass
        if runs:
            return round(sorted(runs)[len(runs)//2], 1), failed
        return round(self.query_timeout_s * 1000, 1), failed   # censored, not missing


def run_episode(env, q, out_dir, quarantine_dir, max_candidates=12, measure_k=4,
                repeats=3):
    ep = Episode(
        task={"id": f"qo-{env.benchmark}-{q['id']}", "benchmark": env.benchmark,
              "task": "query_optimization", "query": q["id"], "n_queries": 1,
              "objective": "query_latency", "budget_mb": 0, "max_index_width": 0,
              "constraint_kind": "plan_only", "constraint_value": 0, "seed": 0},
        policy={"name": "self_driven_hintset", "kind": "enumeration",
                "source": "scripts/gendba/qo_harvest.py",
                "constraint_honoured": "plan_only",
                "params": {"rules": len(RULES), "max_candidates": max_candidates,
                           "measure_k": measure_k, "repeats": repeats}},
        collector="scripts/gendba/qo_harvest.py")
    ep.fingerprint_environment(env.conn, snapshot=f"{DATA}/{env.snapshot}")
    ep.set_workload([q])
    ep.set_initial_state(env.conn)

    # ---- MOVE 1: orient -- the default plan, measured -------------------
    t0 = time.time()
    base_plan = env.explain(q, analyze=True)
    if "explain_failed" in base_plan:
        ep.tool_call("PROBE", {"what": "explain_analyze", "query": q["id"]},
                     base_plan, time.time()-t0, "orient", MEASURED, "postgresql-executor",
                     ok=False, error=str(base_plan["explain_failed"])[:200])
        ep.finish(configuration=[], measured=None,
                  policy_error=f"baseline EXPLAIN ANALYZE failed: {base_plan['explain_failed']}")
        return ep, None
    nodes = _misestimates(base_plan["Plan"])
    nodes.sort(key=lambda n: -n["misestimate_factor"])
    ep.tool_call("PROBE", {"what": "explain_analyze", "query": q["id"]},
                 {"query": q["id"], "plan": base_plan["Plan"],
                  "execution_ms": round(base_plan.get("Execution Time", 0), 1),
                  "shape": shape_hash(base_plan["Plan"]),
                  "worst_misestimates": nodes[:5], "measured": True},
                 time.time()-t0, "orient", MEASURED, "postgresql-executor")

    # ---- MOVE 2: hypothesize -- GROUNDED, not absent ---------------------
    findings = [{"node": n["node"], "relation": n["relation"],
                 "estimated_rows": n["estimated_rows"], "actual_rows": n["actual_rows"],
                 "misestimate_factor": n["misestimate_factor"], "direction": n["direction"],
                 "observation": (f"planner expected {n['estimated_rows']} rows at "
                                 f"{n['node']}" + (f" on {n['relation']}" if n['relation'] else "")
                                 + f", got {n['actual_rows']} ({n['misestimate_factor']}x "
                                   f"{n['direction']})")}
                for n in nodes if n["misestimate_factor"] >= 10][:6]
    ep.add("hypothesize", "note",
           payload={"emitted_by_policy": True,
                    "derived_from_measurement": True,
                    "provenance": "EXPLAIN ANALYZE estimate-vs-actual on the default plan",
                    "n_findings": len(findings), "findings": findings,
                    "reasoning": ("row misestimates of this magnitude mean the join order "
                                  "and methods were chosen on bad information, so plans the "
                                  "planner ranked worse are worth measuring")
                                 if findings else "planner estimates look sound for this query"},
           provenance=MEASURED, produced_by="self_driven_hintset")

    # ---- MOVE 3: screen -- which rules actually matter here --------------
    base_shape = shape_hash(base_plan["Plan"])
    base_cost = base_plan["Plan"]["Total Cost"]
    effective, probes = [], []
    for r in RULES:
        t0 = time.time()
        p = env.explain(q, off=(r,))
        if "explain_failed" in p:
            continue
        sh = shape_hash(p["Plan"])
        changed = sh != base_shape
        probes.append({"rule": r, "changes_plan": changed, "shape": sh,
                       "estimated_cost": p["Plan"]["Total Cost"], "seconds": round(time.time()-t0, 4)})
        if changed:
            effective.append(r)
    ep.tool_call("PROBE", {"what": "rule_probe", "rules": RULES},
                 {"base_shape": base_shape, "base_estimated_cost": base_cost,
                  "probes": probes, "effective_rules": effective,
                  "note": "a rule that does not change the plan alone cannot change it in "
                          "combination either, for this query",
                  "estimated": True},
                 sum(p["seconds"] for p in probes), "screen", ESTIMATED,
                 "postgresql-cost-model")

    # ---- MOVE 3b: enumerate subsets of the rules that matter -------------
    combos, seen = [], {base_shape}
    subsets = []
    for k in range(1, min(len(effective), 4) + 1):
        subsets.extend(itertools.combinations(effective, k))
    for off in subsets:
        if len(combos) >= max_candidates:
            break
        t0 = time.time()
        p = env.explain(q, off=off)
        if "explain_failed" in p:
            continue
        sh = shape_hash(p["Plan"])
        if sh in seen:            # same strategy reached another way -- not a new plan
            continue
        seen.add(sh)
        combos.append({"disabled": list(off), "shape": sh,
                       "estimated_cost": p["Plan"]["Total Cost"],
                       "estimated_vs_default_pct": round((1 - p["Plan"]["Total Cost"]/base_cost)*100, 3),
                       "hint": "/*+ " + " ".join(f"Set({r} off)" for r in off) + " */",
                       "seconds": round(time.time()-t0, 4)})
    ep.tool_call("PROBE", {"what": "enumerate_plans", "from_rules": effective},
                 {"n_subsets_tried": len(subsets), "n_distinct_plans": len(combos),
                  "candidates": combos, "estimated": True},
                 sum(c["seconds"] for c in combos), "screen", ESTIMATED,
                 "postgresql-cost-model")

    # ---- MOVE 4: decide which to actually run ----------------------------
    ranked = sorted(combos, key=lambda c: c["estimated_cost"])[:measure_k]
    ep.decision(iteration=1, n_proposed=len(combos),
                selected_for_measurement=[c["disabled"] for c in ranked],
                rejected=[{"disabled": c["disabled"], "shape": c["shape"],
                           "estimated_cost": c["estimated_cost"],
                           "margin": c["estimated_cost"] - (ranked[-1]["estimated_cost"] if ranked else 0),
                           "margin_provenance": ESTIMATED,
                           "reason": "estimated cost outside the top-k chosen for measurement"}
                          for c in combos if c not in ranked][:20],
                criterion="lowest estimated cost, distinct plan shapes only",
                provenance=ESTIMATED)

    # ---- MOVE 5: verify -- measure the default and the shortlist ---------
    t0 = time.time()
    default_ms, default_fail = env.measure(q, off=(), repeats=repeats)
    measured = [{"disabled": [], "shape": base_shape, "measured_ms": default_ms,
                 "is_default": True, "failed": default_fail}]
    for c in ranked:
        ms, fail = env.measure(q, off=tuple(c["disabled"]), repeats=repeats)
        measured.append({"disabled": c["disabled"], "shape": c["shape"],
                         "estimated_cost": c["estimated_cost"],
                         "measured_ms": ms, "is_default": False, "failed": fail})
    ep.tool_call("PROBE", {"what": "measure_plans", "n": len(measured)},
                 {"results": measured, "repeats": repeats, "statistic": "median",
                  "measured": True},
                 time.time()-t0, "verify", MEASURED, "postgresql-executor")

    best = min(measured, key=lambda m: m["measured_ms"])
    speedup = default_ms / best["measured_ms"] if best["measured_ms"] else 1.0
    # Did the cost model rank the true winner first? This is the QO analogue of the
    # index harvest's top-k adjudication.
    est_rank = ([m["shape"] for m in sorted([m for m in measured if not m["is_default"]],
                                            key=lambda m: m["estimated_cost"])]
                or [])
    ep.finish(
        configuration=[{"query": q["id"], "disabled_rules": best["disabled"],
                        "hint": "/*+ " + " ".join(f"Set({r} off)" for r in best["disabled"]) + " */"
                                if best["disabled"] else None,
                        "plan_shape": best["shape"]}],
        measured={"default_ms": default_ms, "best_ms": best["measured_ms"],
                  "speedup": round(speedup, 4),
                  "best_is_default": bool(best["is_default"]),
                  "all_measured": measured,
                  "failed_queries": {q["id"]: default_fail} if default_fail else {},
                  "provenance": MEASURED,
                  "protocol": {"repeats": repeats, "statistic": "median",
                               "query_timeout_s": env.query_timeout_s}},
        constraint={"kind": "plan_only", "value": 0, "observed": 0, "violated": False,
                    "note": "query optimization is unconstrained by storage; the "
                            "action is a plan, not a physical design"},
        cost_model_picked_winner=bool(est_rank and est_rank[0] == best["shape"]),
        n_effective_rules=len(effective), n_distinct_plans=len(combos),
        reward=round(speedup - 1.0, 4))
    return ep, speedup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="job")
    ap.add_argument("--queries", type=int, default=0, help="0 = all")
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--query-timeout", type=float, default=60)
    ap.add_argument("--measure-k", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", default=GENDBA_REPO + "/gendba_records")
    args = ap.parse_args()

    out_dir = os.path.join(args.out, "episodes")
    quarantine = os.path.join(args.out, "quarantine")
    os.makedirs(out_dir, exist_ok=True)

    env = QOEnv(args.benchmark, port=args.port, query_timeout_s=args.query_timeout)
    qs = env.queries[:args.queries] if args.queries else env.queries
    print(f"qo harvest: {len(qs)} queries on {args.benchmark}")

    n_ok = n_fail = 0
    t_start = time.time()
    for i, q in enumerate(qs, 1):
        t0 = time.time()
        try:
            ep, sp = run_episode(env, q, out_dir, quarantine,
                                 measure_k=args.measure_k, repeats=args.repeats)
        except Exception as e:
            print(f"[{i}/{len(qs)}] {q['id']:>6} EPISODE ERROR {type(e).__name__}: {e}")
            n_fail += 1
            continue
        path = os.path.join(out_dir, f"{ep.header['episode_id']}.json")
        ep.write(path)
        findings = gate.validate(json.load(open(path)))
        fails = [f for f in findings if f.level == "fail"]
        status = "FAIL" if fails else "ok"
        if fails:
            os.makedirs(quarantine, exist_ok=True)
            os.replace(path, os.path.join(quarantine, os.path.basename(path)))
            json.dump([f.__dict__ for f in findings],
                      open(os.path.join(quarantine, os.path.basename(path)+".failures.json"), "w"),
                      indent=2)
            n_fail += 1
        else:
            n_ok += 1
        t = ep.terminal.get("measured") or {}
        print(f"[{i}/{len(qs)}] {q['id']:>6} {t.get('default_ms',0):8.1f}ms -> "
              f"{t.get('best_ms',0):8.1f}ms  {t.get('speedup',0):6.3f}x  "
              f"rules={ep.terminal.get('n_effective_rules',0):2d} "
              f"plans={ep.terminal.get('n_distinct_plans',0):2d} "
              f"{time.time()-t0:5.0f}s {status}")
        for f in fails:
            print(f"      [{f.check}] {f.detail}")
    print(f"\n{n_ok} ok, {n_fail} failed in {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
