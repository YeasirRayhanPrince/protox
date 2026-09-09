#!/usr/bin/env python3
"""
noise.py -- quantify measurement variance, which sets the floor on reward.

Reward differences smaller than run-to-run noise teach the policy nothing. Before
committing to a measurement protocol we need to know what that floor is, and how
much it costs to lower it (warmup passes, repeat count).
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
import statistics
import sys

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
from env import IndexTuningEnv, Task  # noqa: E402



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="job")
    ap.add_argument("--queries", type=int, default=25)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--out", default=GENDBA_BUILD + "/traces/noise.json")
    args = ap.parse_args()

    results = {}
    for warmup, repeats in [(0, 1), (1, 1), (1, 3), (2, 3)]:
        env = IndexTuningEnv(Task(benchmark=args.benchmark, n_queries=args.queries),
                             port=args.port, measure_warmup=warmup,
                             measure_repeats=repeats)
        env.reset()
        totals, secs = [], []
        for _ in range(args.trials):
            import time
            t0 = time.time()
            per_q, _ = env._measure(env.queries)
            secs.append(time.time() - t0)
            totals.append(sum(per_q.values()))
        mean = statistics.mean(totals)
        cv = statistics.stdev(totals) / mean * 100 if len(totals) > 1 else 0.0
        key = f"warmup={warmup},repeats={repeats}"
        results[key] = {
            "totals_ms": [round(t, 1) for t in totals],
            "mean_ms": round(mean, 1),
            "stdev_ms": round(statistics.stdev(totals), 1) if len(totals) > 1 else 0.0,
            "cv_pct": round(cv, 2),
            "seconds_per_measurement": round(statistics.mean(secs), 1),
            "min_detectable_speedup": round(1 + 2 * cv / 100, 4),
        }
        print(f"{key:22s} mean={mean:9.1f}ms  cv={cv:5.2f}%  "
              f"cost={statistics.mean(secs):5.1f}s  "
              f"min detectable speedup ~{1 + 2 * cv / 100:.3f}x")
        env.conn.close()

    json.dump(results, open(args.out, "w"), indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
