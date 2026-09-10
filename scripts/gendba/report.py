#!/usr/bin/env python3
"""
report.py -- summarise the harvested corpus.

Reports what the corpus contains, what it yields under each projection, and the
health signals worth checking before anyone trains on it: censoring, regressions,
duplicate trajectories, adjudication hit-rate, and template coverage.

Read-only: safe to run while a harvest is in flight.
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
import collections
import glob
import hashlib
import json
import os
import statistics
import sys

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
import record as R  # noqa: E402



def load(d):
    out = []
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        try:
            out.append((f, json.load(open(f))))
        except Exception as e:
            print(f"  UNREADABLE {os.path.basename(f)}: {e}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=GENDBA_REPO + "/gendba_records")
    ap.add_argument("--json", default=None, help="also write the summary as JSON")
    args = ap.parse_args()

    eps = load(os.path.join(args.records, "episodes"))
    quar = glob.glob(os.path.join(args.records, "quarantine", "*.json"))
    quar = [q for q in quar if not q.endswith(".failures.json")]
    if not eps:
        print("no episodes found"); return

    size_mb = sum(os.path.getsize(f) for f, _ in eps) / 1024 / 1024
    print(f"=== CORPUS ===  {len(eps)} episodes · {size_mb:.0f} MB · "
          f"{len(quar)} quarantined")

    # --- composition -----------------------------------------------------
    by = collections.Counter()
    starts = collections.Counter()
    for _, r in eps:
        by[(r["task"]["benchmark"], r["policy"]["name"])] += 1
        starts[(r["task"]["benchmark"], r["initial_state"]["kind"])] += 1
    print("\n--- episodes by benchmark x policy ---")
    benches = sorted({b for b, _ in by})
    pols = sorted({p for _, p in by})
    print(f"  {'':12s}" + "".join(f"{p:>12s}" for p in pols))
    for b in benches:
        print(f"  {b:12s}" + "".join(f"{by.get((b, p), 0):>12d}" for p in pols))
    kinds = collections.Counter((r["task"]["benchmark"],
                                 r["task"].get("task", "index_selection")) for _, r in eps)
    print("\n--- task kinds ---")
    for (b, k), n in sorted(kinds.items()):
        print(f"  {b:6s} {k:24s} {n}")

    print("\n--- starting states ---")
    for (b, k), n in sorted(starts.items()):
        print(f"  {b:6s} {k:12s} {n}")

    # --- outcomes --------------------------------------------------------
    print("\n--- measured outcomes ---")
    for b in benches:
        sp = [s for _, r in eps if r["task"]["benchmark"] == b
              for s in [(r["terminal"].get("measured") or {}).get("speedup")]
              if s is not None]
        if not sp:
            print(f"  {b:6s} no episode reports a speedup"); continue
        regr = [s for s in sp if s < 1.0]
        print(f"  {b:6s} n={len(sp):3d}  median={statistics.median(sp):.3f}x  "
              f"best={max(sp):.3f}x  worst={min(sp):.3f}x  regressions={len(regr)}")

    # --- censoring: totals are lower bounds when queries time out --------
    cens_eps, cens_q = 0, collections.Counter()
    for _, r in eps:
        c = r["terminal"]["measured"].get("protocol", {}).get("censored_queries") or []
        if c:
            cens_eps += 1
            for q in c:
                cens_q[(r["task"]["benchmark"], q)] += 1
    print(f"\n--- censoring ---\n  {cens_eps}/{len(eps)} episodes contain a censored query")
    for (b, q), n in cens_q.most_common(6):
        print(f"    {b:6s} {q:>6s} censored in {n} episodes")

    # --- adjudication ----------------------------------------------------
    tot = right = wrong = 0
    gains = []
    for _, r in eps:
        # Not every episode type has a workload total. A query-optimization episode
        # is scored per query, and a multi-component one reports its own. Adjudication
        # compares a rejected candidate against the accepted workload, so an episode
        # without that total simply has nothing to adjudicate -- skip it rather than
        # crash the whole report on the first one.
        fin = (r["terminal"].get("measured") or {}).get("workload_ms_after")
        if fin is None:
            continue
        for e in r["events"]:
            p = e.get("payload") or {}
            if p.get("kind") == "top_k_adjudication":
                for a in p.get("results", []):
                    if a.get("outcome") == "error":
                        continue
                    tot += 1
                    if a["measured_workload_ms"] > fin:
                        right += 1
                    else:
                        wrong += 1
                        gains.append((fin - a["measured_workload_ms"]) / fin * 100)
    if tot:
        print(f"\n--- adjudication (cost model audited by measurement) ---")
        print(f"  {tot} near-misses measured")
        print(f"    right to reject: {right} ({right/tot*100:.0f}%)")
        print(f"    WRONG to reject: {wrong} ({wrong/tot*100:.0f}%)")
        if gains:
            print(f"    best missed gain: {max(gains):.1f}% faster than the accepted choice")

    # --- duplicate trajectories -----------------------------------------
    sig = collections.Counter()
    for _, r in eps:
        ev = [e for e in r["events"]
              if e["move"] == "screen" and "evaluations" in (e.get("payload") or {})]
        n = len(ev[0]["payload"]["evaluations"]) if ev else 0
        sig[(r["task"]["benchmark"], r["policy"]["name"],
             r["task"]["budget_mb"], n)] += 1
    dups = sum(v - 1 for v in sig.values() if v > 1)
    print(f"\n--- redundancy ---\n  duplicate trajectories: {dups}")

    # --- grouping key ----------------------------------------------------
    print("\n--- grouping key (leakage prevention) ---")
    for b in benches:
        r = next(r for _, r in eps if r["task"]["benchmark"] == b)
        wl = r["workload"]
        print(f"  {b:6s} {wl['n_queries']:3d} queries over {wl['n_groups']:3d} "
              f"{wl['grouping_key']} groups")

    # --- projections -----------------------------------------------------
    tsft = pref = meas_pref = card = 0
    for _, r in eps:
        tsft += len(R.project_tool_sft(r)["turns"])
        pp = R.project_preference_pairs(r)
        pref += len(pp)
        meas_pref += sum(1 for p in pp if p.get("margin_provenance") == "measured")
        card += len(R.project_cardinality(r))
    print("\n=== PROJECTIONS (recomputed, never stored) ===")
    print(f"  tool_sft          {tsft:8d} tool-call/response turns")
    print(f"  preference_pairs  {pref:8d} pairs ({meas_pref} measured-adjudicated)")
    print(f"  cardinality       {card:8d} <query,node,filter,est_rows,act_rows>")
    print(f"  outcome           {len(eps):8d} measured outcomes")

    if args.json:
        json.dump({"episodes": len(eps), "size_mb": round(size_mb, 1),
                   "quarantined": len(quar),
                   "by_benchmark_policy": {f"{b}/{p}": n for (b, p), n in by.items()},
                   "adjudication": {"n": tot, "right": right, "wrong": wrong},
                   "duplicate_trajectories": dups,
                   "projections": {"tool_sft": tsft, "preference_pairs": pref,
                                   "measured_pairs": meas_pref, "cardinality": card}},
                  open(args.json, "w"), indent=2)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
