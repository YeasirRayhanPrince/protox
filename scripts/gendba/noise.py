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
    ap.add_argument("--suggest-repeats", action="store_true",
                    help="print ONLY the cheapest protocol whose noise floor is "
                         "under --target-floor, as a repeat count, for a script to "
                         "consume. Everything else goes to stderr.")
    ap.add_argument("--target-floor", type=float, default=1.02,
                    help="the smallest speedup the protocol must be able to "
                         "distinguish from noise (default 1.02 = 2%%)")
    args = ap.parse_args()
    # In suggest mode stdout carries one number and nothing else, so a caller can
    # read it directly; the human-readable table still goes somewhere visible.
    out = sys.stderr if args.suggest_repeats else sys.stdout

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
              f"min detectable speedup ~{1 + 2 * cv / 100:.3f}x", file=out)
        env.conn.close()

    json.dump(results, open(args.out, "w"), indent=2)
    print(f"\nwrote {args.out}", file=out)

    if args.suggest_repeats:
        # Cheapest protocol that can actually see the effect we care about. Sorting
        # by cost rather than by noise matters: the lowest-noise protocol is usually
        # also the most expensive, and on a workload where a pass is milliseconds
        # the cheapest adequate one may still be many repeats.
        ok = [(v["seconds_per_measurement"], k, v) for k, v in results.items()
              if v["min_detectable_speedup"] <= args.target_floor]
        if ok:
            _, key, v = min(ok)
            print(f"chose {key}: floor {v['min_detectable_speedup']}x "
                  f"<= target {args.target_floor}x at "
                  f"{v['seconds_per_measurement']}s/measurement", file=sys.stderr)
        else:
            # Nothing reached the target: take the quietest available and say so,
            # rather than silently returning a protocol that cannot see the effect.
            key, v = min(results.items(), key=lambda kv: kv[1]["min_detectable_speedup"])
            print(f"WARNING no protocol reached {args.target_floor}x; best is {key} "
                  f"at {v['min_detectable_speedup']}x -- effects smaller than that "
                  f"are not measurable here", file=sys.stderr)
        print(int(key.split("repeats=")[1]))


if __name__ == "__main__":
    main()
