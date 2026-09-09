#!/usr/bin/env python3
"""
rollout.py -- run a policy in the Gen-DBA environment and score it.

Policies here are all scripted; they exist to (a) prove the tool surface is usable,
(b) produce the reference score that RL advantage is measured against, and
(c) generate cold-start trajectories in the deployed tool vocabulary.

    extend    ISE's Extend heuristic, driven through the env's tools.
              This is the REFERENCE policy.
    whatif    Greedy: repeatedly PROBE.whatif over single-column candidates and
              REALIZE the best, until nothing helps or the budget is gone.
              Same information as extend, much dumber search -- a floor.
    random    Random legal indexes within budget. The true floor.
    none      Do nothing. Sanity check that speedup == 1.0.

Critically, every policy is scored through env.score(), so all of them share one
measurement protocol. A reference number measured differently is worthless as a
baseline.
"""
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
import json
import random
import sys
import time

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
sys.path.insert(0, GENDBA_REPO + "/index_selection_evaluation")

from env import IndexTuningEnv, Task  # noqa: E402


# ------------------------------------------------------------------- policies

def policy_none(env, rng):
    return


def policy_random(env, rng, max_steps=8):
    schema = env.call("HARVEST", {"what": "schema"})["result"]["tables"]
    for _ in range(max_steps):
        t = rng.choice([x for x in schema if x["indexable_columns"]])
        k = rng.randint(1, env.task.max_index_width)
        cols = rng.sample(t["indexable_columns"], min(k, len(t["indexable_columns"])))
        r = env.call("REALIZE", {"action": "create_index",
                                 "table": t["table"], "columns": cols})
        if r["ok"] and r["result"]["over_budget"]:
            env.call("REALIZE", {"action": "drop_index",
                                 "name": r["result"]["created"]})
            break


def policy_whatif(env, rng, max_steps=10):
    """
    Greedy over what-if cost. Deliberately uses only the cheap estimated tool, so
    its gap to `extend` shows what the smarter search buys, and its gap to measured
    reward shows what trusting the cost model costs.
    """
    schema = env.call("HARVEST", {"what": "schema"})["result"]["tables"]
    candidates = [{"table": t["table"], "columns": [c]}
                  for t in schema for c in t["indexable_columns"]]
    base = env.call("PROBE", {"what": "whatif", "indexes": []})
    current = None
    applied = []
    for _ in range(max_steps):
        best, best_cost = None, current
        for cand in candidates:
            if cand in applied:
                continue
            r = env.call("PROBE", {"what": "whatif", "indexes": applied + [cand]})
            if not r["ok"]:
                continue
            c = r["result"]["total_estimated_cost"]
            if best_cost is None or c < best_cost:
                best, best_cost = cand, c
            if env.tool_budget_remaining <= 0:
                break
        if best is None:
            break
        r = env.call("REALIZE", {"action": "create_index", **best})
        if not r["ok"]:
            break
        if r["result"]["over_budget"]:
            env.call("REALIZE", {"action": "drop_index", "name": r["result"]["created"]})
            break
        applied.append(best)
        current = best_cost
        if env.tool_budget_remaining <= 0:
            break


def policy_extend(env, rng):
    """
    ISE's Extend, run against the same live database, then its chosen configuration
    is REALIZEd through the env so it is scored on identical terms.
    """
    from selection.workload import Column, Query, Table, Workload
    from selection.dbms.postgres_dbms import PostgresDatabaseConnector
    from selection.algorithms.extend_algorithm import ExtendAlgorithm

    tables, queries = {}, []
    for t, cols in env._attrs.items():
        tab = Table(t)
        tab.add_columns([Column(c) for c in cols])
        tables[t] = tab
    import re
    for q in env.queries:
        refs = []
        for tname, tab in tables.items():
            if not re.search(rf"\b{re.escape(tname)}\b", q["text"], re.I):
                continue
            for col in tab.columns:
                if re.search(rf"\b{re.escape(col.name)}\b", q["text"], re.I):
                    refs.append(col)
        queries.append(Query(q["id"], q["text"], refs))
    workload = Workload(queries)

    conn = PostgresDatabaseConnector(env.dbname)
    algo = ExtendAlgorithm(conn, {"budget_MB": env.task.budget_mb,
                                  "max_index_width": env.task.max_index_width})
    t0 = time.time()
    indexes = algo.calculate_best_indexes(workload)
    search_s = time.time() - t0
    conn.commit()
    conn.close()

    for idx in indexes:
        env.call("REALIZE", {"action": "create_index",
                             "table": str(idx.table()),
                             "columns": [c.name for c in idx.columns]})
    return {"search_seconds": round(search_s, 2), "n_selected": len(indexes)}


POLICIES = {"none": policy_none, "random": policy_random,
            "whatif": policy_whatif, "extend": policy_extend}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="extend", choices=list(POLICIES))
    ap.add_argument("--benchmark", default="job")
    ap.add_argument("--queries", type=int, default=25)
    ap.add_argument("--budget-mb", type=float, default=500)
    ap.add_argument("--max-index-width", type=int, default=2)
    ap.add_argument("--tool-budget-s", type=float, default=600)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--reference-speedup", type=float, default=None)
    ap.add_argument("--restore", action="store_true",
                    help="cold reset from snapshot instead of dropping indexes")
    ap.add_argument("--out", default=None)
    ap.add_argument("--measure-warmup", type=int, default=0)
    ap.add_argument("--measure-repeats", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    task = Task(benchmark=args.benchmark, n_queries=args.queries,
                budget_mb=args.budget_mb, max_index_width=args.max_index_width,
                tool_budget_s=args.tool_budget_s, seed=args.seed)
    env = IndexTuningEnv(task, port=args.port, verbose=args.verbose,
                         measure_warmup=args.measure_warmup,
                         measure_repeats=args.measure_repeats)
    env.reset(restore_snapshot=args.restore)
    print(f"task: {task.id()}   policy: {args.policy}")

    base = env.baseline()
    print(f"  baseline {base['workload_ms']:.1f}ms  protocol={base['protocol']}")

    rng = random.Random(args.seed)
    t0 = time.time()
    meta = POLICIES[args.policy](env, rng) or {}
    wall = round(time.time() - t0, 2)

    result = env.score(reference_speedup=args.reference_speedup)
    result["policy"] = args.policy
    result["policy_wall_s"] = wall
    result.update(meta)

    print(f"  applied  {result['n_indexes']} indexes, "
          f"{result['storage_used_mb']}MB / {task.budget_mb}MB"
          f"{'  OVER BUDGET' if result['over_budget'] else ''}")
    print(f"  measured {result['workload_ms_before']}ms -> "
          f"{result['workload_ms_after']}ms  ({result['speedup']}x)")
    print(f"  reward   {result['reward']}"
          + (f"   advantage {result['advantage']:+.4f} vs ref "
             f"{result['reference_speedup']}x" if args.reference_speedup else ""))
    if result["per_query_regressions_ms"]:
        print(f"  regressions: {result['per_query_regressions_ms']}")
    print(f"  tool time {result['tool_seconds_used']}s of {task.tool_budget_s}s, "
          f"{len(env.trajectory)} calls")

    out = args.out or fGENDBA_BUILD + "/traces/rollout_{task.id()}_{args.policy}.json"
    # env.score() already wrote the terminal. Passing `result` back in would declare
    # the same facts twice, which drifts apart silently -- one source of truth per
    # fact. Only genuinely new fields (policy timing/metadata) go in here.
    env.dump(out, extra={"policy_wall_s": wall,
                         **{k: v for k, v in meta.items()}})
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
