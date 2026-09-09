#!/usr/bin/env python3
"""
sweep.py -- build the reference table across the task distribution.

For group-relative RL, what matters is a diverse set of tasks each with a known
strong-baseline score, not a large pile of trajectories. This sweeps the budget
axis (the constraint that actually makes index selection interesting) and records,
per task, what each scripted policy achieves under one measurement protocol.

Output feeds two things:
  * reward normalisation  -- advantage = policy_speedup - reference_speedup
  * task screening        -- a task where extend ~= random is uninformative;
                             one where extend >> random has headroom to learn.
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
import os
import random
import sys
import time

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
sys.path.insert(0, GENDBA_REPO + "/index_selection_evaluation")

from env import IndexTuningEnv, Task  # noqa: E402
from rollout import POLICIES  # noqa: E402



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="job")
    ap.add_argument("--queries", type=int, default=25)
    ap.add_argument("--budgets", default="50,100,250,500,1000,2500")
    ap.add_argument("--policies", default="extend,whatif,random")
    ap.add_argument("--width", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--out", default=GENDBA_BUILD + "/traces/reference_table.json")
    ap.add_argument("--trace-dir", default=GENDBA_BUILD + "/traces/rollouts")
    args = ap.parse_args()

    budgets = [float(b) for b in args.budgets.split(",")]
    policies = args.policies.split(",")
    table, t_start = [], time.time()

    for b in budgets:
        for pname in policies:
            task = Task(benchmark=args.benchmark, n_queries=args.queries,
                        budget_mb=b, max_index_width=args.width, seed=args.seed)
            env = IndexTuningEnv(task, port=args.port)
            env.reset()
            env.baseline()
            rng = random.Random(args.seed)
            t0 = time.time()
            try:
                meta = POLICIES[pname](env, rng) or {}
            except Exception as e:                      # a policy failing is data
                meta = {"policy_error": f"{type(e).__name__}: {e}"}
            wall = round(time.time() - t0, 2)
            score = env.score()
            row = {"task": task.id(), "benchmark": args.benchmark,
                   "budget_mb": b, "policy": pname, "policy_wall_s": wall, **score}
            row.update(meta)
            table.append(row)
            os.makedirs(args.trace_dir, exist_ok=True)
            env.dump(f"{args.trace_dir}/{task.id()}_{pname}.json", extra={"score": score})
            print(f"{args.benchmark:5s} b={b:7.0f}MB {pname:8s} "
                  f"{score['speedup']:6.3f}x  {score['n_indexes']:2d} idx  "
                  f"{score['storage_used_mb']:7.1f}MB  "
                  f"{'OVER ' if score['over_budget'] else ''}"
                  f"({wall}s policy, {score['tool_seconds_used']}s tools)")
            env.conn.close()

    # Reference = extend. Attach advantage for every other policy on the same task.
    ref = {r["task"]: r["speedup"] for r in table if r["policy"] == "extend"}
    for r in table:
        if r["task"] in ref:
            r["reference_speedup"] = ref[r["task"]]
            r["advantage"] = round(r["speedup"] - ref[r["task"]], 4)

    summary = {"generated_s": round(time.time() - t_start, 1),
               "protocol": {"warmup": 0, "repeats": 1, "statistic": "median"},
               "reward_floor_speedup": 1.015,
               "rows": table}
    json.dump(summary, open(args.out, "w"), indent=2)

    print("\n=== reference table ===")
    print(f"{'budget_MB':>10} " + " ".join(f"{p:>9}" for p in policies) + "   headroom")
    for b in budgets:
        cells, byp = [], {r["policy"]: r for r in table if r["budget_mb"] == b}
        for p in policies:
            cells.append(f"{byp[p]['speedup']:8.3f}x" if p in byp else "        -")
        head = (byp["extend"]["speedup"] - byp.get("random", byp["extend"])["speedup"]
                if "extend" in byp else 0)
        print(f"{b:>10.0f} " + " ".join(cells) + f"   {head:+.3f}")
    print(f"\nwrote {args.out}  ({summary['generated_s']}s)")


if __name__ == "__main__":
    main()
