#!/usr/bin/env python3
"""
unitune_recover.py -- complete an episode whose run was interrupted.

Checkpoints exist precisely so an interrupted run is not a total loss: the events are
all there, only the terminal block is missing because finish() never ran. This
reconstructs that block from the last recorded state plus the run's own history file.

It does NOT pretend the run completed. The episode is stamped `truncated` with the
reason, the pull it reached, and the budget it did not spend, so nobody can mistake a
6h interrupted run for a 6h finished one. `policy_error` is deliberately left unset:
the policy did not fail, it was stopped from outside, and conflating the two would
teach a reader that this rule is less reliable than it is.
"""
from __future__ import annotations

import os as _os
GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")

import argparse
import glob
import json
import sys

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
sys.path.insert(0, GENDBA_REPO + "/unitune/UniTune")

import unitune_patches
unitune_patches.apply()

import unitune_harvest as UH  # noqa: E402
import validate as gate  # noqa: E402
from record import MEASURED  # noqa: E402


def recover(ckpt_path, res_path, reason, out_dir, dry_run=False):
    rec = json.load(open(ckpt_path))
    if rec.get("terminal"):
        return "checkpoint already has a terminal; nothing to recover"

    states = [e["payload"] for e in rec["events"] if e["kind"] == "state"]
    decisions = [e["payload"] for e in rec["events"] if e["kind"] == "decision"]
    if not states:
        return "no state events; nothing measurable to recover"

    best = states[-1]["best_per_arm"]
    evals = UH._load_evaluations(res_path)
    # The baseline is the FIRST state's running best, which at pull 0 is still the
    # default configuration's cost -- the same definition the live producer uses.
    before = states[0]["best_per_arm"].get("all")
    after = best.get("all")
    seq = [d["accepted"]["arm"] for d in decisions]
    arms = [a for a in ("knob", "index", "query", "view") if a in best]
    budget = float((rec.get("task") or {}).get("constraint_value") or 0)

    rec["terminal"] = {
        "configuration": [{"arm": a, "config": (best.get(a) or {}).get("config")}
                          for a in arms],
        "measured": {
            "workload_ms_before": UH._ms(before),
            "workload_ms_after": UH._ms(after),
            "speedup": UH._speedup(before, after),
            "best_per_arm": json.loads(json.dumps(best, default=str)),
            "action_sequence": seq,
            "pulls": len(decisions),
            "evaluations": evals,
            "n_evaluations": len(evals),
            "noise_floor": UH._repeat_noise(evals),
            "provenance": MEASURED,
            "protocol": {"arm_method": (rec.get("policy") or {}).get("arm_method"),
                         "recovered_from_checkpoint": True},
        },
        "constraint": {"kind": "tuning_budget_s", "value": budget,
                       "observed": None, "violated": False,
                       "note": "the run was stopped before its budget elapsed; "
                               "elapsed time is not recorded because finish() "
                               "never ran"},
        # Stated loudly, because the difference between "ran 6h" and "was killed at
        # 5.8h" is invisible in every other field.
        "truncated": {"reason": reason, "pulls_completed": len(decisions),
                      "budget_s": budget,
                      "note": "events up to this pull are complete and measured; "
                              "the run simply did not continue"},
        "policy_error": None,
        "wall_clock_s": None,
    }

    findings = gate.validate(rec)
    fails = [f for f in findings if f.level == "fail"]
    if fails:
        return "REFUSED, would not gate: " + "; ".join(
            f"{f.check}: {f.detail[:100]}" for f in fails)
    if dry_run:
        return (f"would recover {len(decisions)} pulls, "
                f"speedup {rec['terminal']['measured']['speedup']}, "
                f"{len(evals)} evaluations")

    _os.makedirs(out_dir, exist_ok=True)
    path = _os.path.join(out_dir, f"{rec['episode_id']}.json")
    tmp = path + ".partial"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2, default=str)
        f.flush(); _os.fsync(f.fileno())
    _os.replace(tmp, path)
    return (f"recovered {len(decisions)} pulls, speedup "
            f"{rec['terminal']['measured']['speedup']}, {len(evals)} evaluations "
            f"-> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--res", required=True)
    ap.add_argument("--reason", required=True,
                    help="why the run stopped; recorded verbatim in the episode")
    ap.add_argument("--out", default=GENDBA_REPO + "/gendba_records/episodes")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(recover(a.checkpoint, a.res, a.reason, a.out, a.dry_run))


if __name__ == "__main__":
    main()
