#!/usr/bin/env python3
"""
reset_fidelity.py -- is DDL reset sound?

noise.py measures variance of repeated measurement in a FIXED state (~0.3%). That
is not the variance that matters. Between rollouts the environment creates and
drops indexes, which churns the page cache and touches the catalog. If the baseline
drifts across that cycle, then rewards from different rollouts are not comparable
and DDL reset (design commitment 3 in env.py) is wrong -- we would need snapshot
restore, at ~8 s plus a cold cache, which changes rollout economics substantially.

Protocol: measure baseline, build indexes, measure, drop them, measure baseline
again. Repeat. Drift is (B_n - B_1) / B_1.
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
import time

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
from env import IndexTuningEnv, Task  # noqa: E402

# A configuration close to what Extend picks, so the cache churn is representative.

INDEXES = [
    {"table": "movie_keyword", "columns": ["keyword_id"]},
    {"table": "keyword", "columns": ["keyword"]},
    {"table": "movie_companies", "columns": ["movie_id"]},
    {"table": "person_info", "columns": ["person_id"]},
    {"table": "aka_name", "columns": ["person_id"]},
    {"table": "movie_info_idx", "columns": ["movie_id"]},
    {"table": "title", "columns": ["production_year"]},
    {"table": "movie_keyword", "columns": ["movie_id"]},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=4)
    ap.add_argument("--queries", type=int, default=25)
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--warmup", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--out", default=GENDBA_BUILD + "/traces/reset_fidelity.json")
    args = ap.parse_args()

    env = IndexTuningEnv(Task(benchmark="job", n_queries=args.queries, budget_mb=100000),
                         port=args.port, measure_warmup=args.warmup,
                         measure_repeats=args.repeats)
    env.reset()

    baselines, withidx, cycle_s = [], [], []
    for c in range(args.cycles):
        t0 = time.time()
        b, _ = env._measure(env.queries)
        baselines.append(sum(b.values()))

        for spec in INDEXES:
            env.call("REALIZE", {"action": "create_index", **spec})
        w, _ = env._measure(env.queries)
        withidx.append(sum(w.values()))
        for a in list(env._applied):
            env.call("REALIZE", {"action": "drop_index", "name": a["name"]})

        cycle_s.append(time.time() - t0)
        print(f"cycle {c}: baseline={baselines[-1]:9.1f}ms  "
              f"with_indexes={withidx[-1]:9.1f}ms  "
              f"speedup={baselines[-1]/withidx[-1]:.4f}x  "
              f"({cycle_s[-1]:.1f}s)")

    b0 = baselines[0]
    drift = [(b - b0) / b0 * 100 for b in baselines]
    speedups = [b / w for b, w in zip(baselines, withidx)]
    res = {
        "baselines_ms": [round(b, 1) for b in baselines],
        "with_indexes_ms": [round(w, 1) for w in withidx],
        "baseline_drift_pct": [round(d, 3) for d in drift],
        "max_abs_drift_pct": round(max(abs(d) for d in drift), 3),
        "baseline_cv_pct": round(statistics.stdev(baselines) / statistics.mean(baselines) * 100, 3)
        if len(baselines) > 1 else 0.0,
        "speedups": [round(s, 4) for s in speedups],
        "speedup_cv_pct": round(statistics.stdev(speedups) / statistics.mean(speedups) * 100, 3)
        if len(speedups) > 1 else 0.0,
        "seconds_per_cycle": round(statistics.mean(cycle_s), 1),
        "protocol": {"warmup": args.warmup, "repeats": args.repeats},
    }
    print()
    print(f"baseline drift across cycles: max {res['max_abs_drift_pct']}%  "
          f"cv {res['baseline_cv_pct']}%")
    print(f"speedup reproducibility:      cv {res['speedup_cv_pct']}%  "
          f"-> rewards below ~{1 + 2*res['speedup_cv_pct']/100:.3f}x are noise")
    json.dump(res, open(args.out, "w"), indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
