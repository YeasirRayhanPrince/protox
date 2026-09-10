#!/usr/bin/env python3
"""
unitune_compare.py -- what did the meta-decision rule actually change?

The sweep runs the same arms, sub-tuners and workload under three different
arm-selection rules, so the difference between the episodes is attributable to the
rule. This reports that difference along the axes the rules can actually differ on:
how they spent their pulls, how close their choices were, and what it bought.

Read-only. Safe to run while the sweep is still in flight; runs that have not
finished are reported as such rather than omitted.
"""
from __future__ import annotations

import os as _os
GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")

import argparse
import collections
import glob
import json
import statistics
import sys

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")


def load(records):
    out = []
    for f in sorted(glob.glob(_os.path.join(records, "episodes", "unitune-*.json"))):
        out.append((f, json.load(open(f))))
    return out


def summarise(rec):
    m = rec["terminal"]["measured"]
    ds = [e["payload"] for e in rec["events"] if e["kind"] == "decision"]
    # A "comparison" is a pull where the rule actually weighed the arms against each
    # other. A forced warm-up sweep is a pull, but it is not a decision about
    # anything, and counting the two together would flatter every rule equally.
    comps = [d for d in ds if "warm-up" not in (d.get("selection_rule") or "")]
    margins = [abs(x["margin"]) for d in comps for x in d.get("rejected") or []
               if x.get("margin") is not None]
    seq = m.get("action_sequence") or []
    ev = [e for e in (m.get("evaluations") or [])
          if e.get("kind") == "evaluation" and e.get("workload_ms")]
    base = m.get("workload_ms_before")
    return {
        "rule": rec["policy"].get("meta_decision_rule") or rec["policy"].get("arm_method"),
        "pulls": len(ds),
        "comparisons": len(comps),
        "arm_share": dict(collections.Counter(seq)),
        "speedup": m.get("speedup"),
        "before_s": None if base is None else round(base / 1000, 1),
        "after_s": None if m.get("workload_ms_after") is None
        else round(m["workload_ms_after"] / 1000, 1),
        "budget_s": rec["terminal"]["constraint"].get("value"),
        "observed_s": rec["terminal"]["constraint"].get("observed"),
        "evaluations": len(ev),
        "wins": sum(1 for e in ev if base and e["workload_ms"] < base),
        "regressions": sum(1 for e in ev if base and e["workload_ms"] > base),
        "worst_regression_x": (round(max(e["workload_ms"] for e in ev) / base, 2)
                               if ev and base else None),
        "tightest_margin": round(min(margins), 4) if margins else None,
        "median_margin": round(statistics.median(margins), 4) if margins else None,
        "noise_floor": (m.get("noise_floor") or {}).get("max_relative_spread"),
        "policy_error": rec["terminal"].get("policy_error"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=GENDBA_REPO + "/gendba_records")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    eps = load(a.records)
    if not eps:
        print("no unitune episodes yet"); return
    rows = [summarise(r) for _, r in eps]
    order = {"ts": 0, "rb": 1, "alter": 2}
    rows.sort(key=lambda r: order.get(r["rule"], 9))

    print(f"=== UniTune meta-decision sweep === {len(rows)} episode(s)\n")
    hdr = (f"{'rule':6s} {'pulls':>5} {'cmp':>4} {'knob/index':>12} {'speedup':>8} "
           f"{'before':>8} {'after':>8} {'evals':>6} {'win':>4} {'reg':>4} "
           f"{'worst':>6} {'tight':>7} {'median':>7}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        share = f"{r['arm_share'].get('knob',0)}/{r['arm_share'].get('index',0)}"
        f = lambda v, w, p="": "-".rjust(w) if v is None else f"{v:{w}{p}}"
        print(f"{str(r['rule']):6s} {r['pulls']:>5} {r['comparisons']:>4} {share:>12} "
              f"{f(r['speedup'],8,'.3f')} {f(r['before_s'],8,'.1f')} "
              f"{f(r['after_s'],8,'.1f')} {r['evaluations']:>6} {r['wins']:>4} "
              f"{r['regressions']:>4} {f(r['worst_regression_x'],6,'.2f')} "
              f"{f(r['tightest_margin'],7,'.4f')} {f(r['median_margin'],7,'.4f')}")
        if r["policy_error"]:
            print(f"       policy_error: {r['policy_error'][:100]}")

    print("\nnotes")
    print("  cmp    = pulls where the rule actually weighed the arms; a forced warm-up")
    print("           sweep is a pull but not a decision, so the two are kept apart.")
    print("  tight  = smallest margin by which an arm was rejected. A near-zero margin")
    print("           is a coin flip that the posteriors alone would not reveal.")
    print("  alter  = round-robin: 0 comparisons BY DESIGN. It is the floor case --")
    print("           same arms, same budget, evidence ignored.")
    print("  Episodes do NOT start from a common state: UniTune tunes the live cluster")
    print("  and does not restore between runs, so speedup is comparable only with")
    print("  that caveat. The decision traces are comparable; the end states are not.")

    if a.json:
        json.dump(rows, open(a.json, "w"), indent=2)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
