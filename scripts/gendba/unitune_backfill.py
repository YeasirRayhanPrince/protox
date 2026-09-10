#!/usr/bin/env python3
"""
unitune_backfill.py -- attach a UniTune run's measured evaluations to its episode.

The producer captures these inline, but a run already in flight when that was added
has the older recorder in memory and writes an episode without them. Rather than
leave one episode structurally different from its siblings -- which would look like
a property of the arm-selection rule rather than of when the code changed -- this
reattaches them from the run's own history file after the fact.

Idempotent: an episode that already carries evaluations is left alone unless --force.
The episode is re-gated before it is rewritten, and never rewritten if it would fail.
"""
from __future__ import annotations

import os as _os
GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")

import argparse
import json
import sys

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
sys.path.insert(0, GENDBA_REPO + "/unitune/UniTune")

import unitune_patches
unitune_patches.apply()

import unitune_harvest as UH  # noqa: E402
import validate as gate  # noqa: E402


def backfill(episode_path, res_path, force=False, dry_run=False):
    rec = json.load(open(episode_path))
    m = rec.get("terminal", {}).get("measured") or {}
    if m.get("evaluations") and not force:
        return "already has evaluations; skipped"

    evals = UH._load_evaluations(res_path)
    if not evals:
        return f"no evaluations parsed from {res_path}"

    m["evaluations"] = evals
    m["n_evaluations"] = len(evals)
    m["noise_floor"] = UH._repeat_noise(evals)
    m.setdefault("backfilled_from", res_path)
    rec["terminal"]["measured"] = m

    findings = gate.validate(rec)
    fails = [f for f in findings if f.level == "fail"]
    if fails:
        return "REFUSED, would not gate: " + "; ".join(
            f"{f.check}: {f.detail[:80]}" for f in fails)
    if dry_run:
        return (f"would attach {len(evals)} evaluations, "
                f"noise floor {m['noise_floor'].get('max_relative_spread')}")

    tmp = episode_path + ".partial"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2, default=str)
        f.flush(); _os.fsync(f.fileno())
    _os.replace(tmp, episode_path)
    return (f"attached {len(evals)} evaluations; noise floor "
            f"{m['noise_floor'].get('max_relative_spread')} over "
            f"{m['noise_floor'].get('repeated_configurations')} repeated configs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True)
    ap.add_argument("--res", required=True, help="the run's UniTune .res history file")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(backfill(a.episode, a.res, a.force, a.dry_run))


if __name__ == "__main__":
    main()
