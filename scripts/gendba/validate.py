#!/usr/bin/env python3
"""
validate.py -- the harvest-time gate.

Every record passes through here BEFORE it enters the corpus. A record that fails is
quarantined with the reason attached, never silently dropped and never admitted.

Why a gate at all: the expensive part of a bad record is not the bug, it is that
every downstream artifact already consumed it before anyone noticed. Checks are cheap
here and ruinous later. When a defect is found, it is fixed at the PRODUCER and the
whole corpus is re-gated -- records are never patched in place, or the bad values
survive in whatever was already built from them.

Two rules this file takes seriously:

  * INDEPENDENT ORACLE. A check derived from the same output it is checking passes on
    corrupted data. So invariants here are anchored to things the record did not
    produce: the benchmark's declared indexable columns, the SQL text's own hash, the
    catalog, published row counts, and control episodes whose answer is known a priori
    (a no-op policy must score ~1.0x).

  * CAN'T PROVE IT => QUARANTINE. Absent evidence is not a pass. A surprising
    magnitude is treated as a suspected measurement bug until independently confirmed,
    not as a finding.
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
import json
import os
import shutil
import sys
from dataclasses import dataclass

import yaml


REPO = GENDBA_REPO
NOISE_FLOOR = 1.015          # reset_fidelity.py: speedup cv 0.757%
SUSPECT_SPEEDUP = 20.0       # above this, treat as measurement-bug suspect
KNOWN_SCHEMA = {"1.0"}

BENCH_CFG = {"job": "configs/benchmark/job_full.yaml",
             "tpch": "configs/benchmark/tpch.yaml",
             "dsb": "configs/benchmark/dsb_s10.yaml"}


@dataclass
class Finding:
    level: str        # fail | suspect
    check: str
    detail: str


def _sha1(s):
    import hashlib
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def _indexable(benchmark):
    """
    INDEPENDENT ORACLE: the benchmark config, not anything the episode emitted.

    Uses record.indexable_columns() so the gate and the producer agree on the action
    space. They did not, briefly: env.py recovered DSB's malformed web_returns column
    list while this function still dropped it, so every DSB episode that legitimately
    indexed web_returns was quarantined as "index on unknown table".
    """
    import record as _rec
    cols, _ = _rec.indexable_columns(f"{REPO}/{BENCH_CFG[benchmark]}")
    return {t: set(c) for t, c in cols.items()}


def validate(rec: dict) -> list[Finding]:
    f: list[Finding] = []
    add = lambda lvl, chk, d: f.append(Finding(lvl, chk, d))

    # ---- structure -------------------------------------------------------
    if rec.get("schema_version") not in KNOWN_SCHEMA:
        add("fail", "schema_version", f"unknown: {rec.get('schema_version')!r}")
    for k in ("episode_id", "task", "policy", "environment", "workload",
              "initial_state", "events", "terminal"):
        if k not in rec:
            add("fail", "structure", f"missing top-level key {k!r}")
    if f:
        return f

    task, env, wl, term = rec["task"], rec["environment"], rec["workload"], rec["terminal"]

    # ---- environment completeness ---------------------------------------
    for path in (("engine", "version"), ("engine", "knobs"), ("hardware", "cores"),
                 ("snapshot",), ("concurrency",), ("statistics",)):
        node = env
        for p in path:
            node = (node or {}).get(p) if isinstance(node, dict) else None
        if node in (None, {}, []):
            add("fail", "environment", f"missing environment.{'.'.join(path)}")
    knobs = env.get("engine", {}).get("knobs", {})
    for k in ("shared_buffers", "effective_cache_size", "work_mem",
              "max_parallel_workers_per_gather", "random_page_cost"):
        if k not in knobs:
            add("fail", "knobs", f"knob {k!r} not recorded")

    # ---- grouping key (leakage prevention) -------------------------------
    if wl.get("grouping_key") != "template":
        add("fail", "grouping_key", "workload.grouping_key must be 'template'")
    if any("template" not in q for q in wl.get("queries", [])):
        add("fail", "grouping_key", "some queries carry no template")

    # ---- workload integrity: hash is an independent check on the SQL -----
    if wl.get("n_queries") != len(wl.get("queries", [])):
        add("fail", "workload", "n_queries disagrees with len(queries)")
    for q in wl.get("queries", []):
        if _sha1(q["sql"]) != q["sql_sha1"]:
            add("fail", "workload", f"sql_sha1 mismatch for {q['id']}")

    # ---- provenance ------------------------------------------------------
    for e in rec["events"]:
        if e["kind"] == "tool_call" and e.get("ok", True):
            if e.get("provenance") not in ("estimated", "measured", "derived", "declared"):
                add("fail", "provenance", f"event {e['i']} has provenance "
                                          f"{e.get('provenance')!r}")
            if not e.get("produced_by"):
                add("fail", "provenance", f"event {e['i']} has no produced_by")
    m = term.get("measured") or {}
    if m and m.get("provenance") != "measured":
        add("fail", "provenance", "terminal.measured is not labelled measured")

    # ---- failures must be labelled outcomes, not gaps --------------------
    before = (m.get("per_query_ms_before") or {})
    after = (m.get("per_query_ms_after") or {})
    if before and after:
        labelled = set((m.get("failed_queries") or {}))
        unexplained = (set(before) - set(after)) - labelled
        if unexplained:
            add("fail", "labelled_outcomes",
                f"queries measured before but absent after with no outcome: "
                f"{sorted(unexplained)}")
        # the reverse matters just as much: a query that appears only AFTER means the
        # two totals cover different workloads and the speedup is not a speedup
        appeared = (set(after) - set(before)) - labelled
        if appeared:
            add("fail", "labelled_outcomes",
                f"queries present after but absent before: {sorted(appeared)} -- "
                "before/after cover different query sets")
        # internal consistency: the total must be the sum it claims to be
        for tag, per_q, total in (("before", before, m.get("workload_ms_before")),
                                  ("after", after, m.get("workload_ms_after"))):
            if total is not None and abs(sum(per_q.values()) - total) > max(1.0, total * 0.001):
                add("fail", "consistency",
                    f"workload_ms_{tag}={total} != sum(per_query)={sum(per_q.values()):.1f}")

    # ---- configuration legality, against the benchmark config ------------
    bench = task.get("benchmark")
    if bench in BENCH_CFG:
        allowed = _indexable(bench)
        for idx in term.get("configuration", []):
            t, cols = idx.get("table"), idx.get("columns", [])
            if t not in allowed:
                add("fail", "configuration", f"index on unknown table {t!r}")
            else:
                bad = [c for c in cols if c not in allowed[t]]
                if bad:
                    add("fail", "configuration", f"non-indexable columns on {t}: {bad}")
            if len(cols) > task.get("max_index_width", 99):
                add("fail", "configuration",
                    f"index width {len(cols)} exceeds task max "
                    f"{task.get('max_index_width')}")

    # ---- constraint: judged against what the policy actually received --------
    con = term.get("constraint") or {}
    if not con:
        add("fail", "constraint", "terminal.constraint missing")
    else:
        kind, val, obs, viol = (con.get("kind"), con.get("value"),
                                con.get("observed"), con.get("violated"))
        if kind not in ("budget_MB", "max_indexes"):
            add("fail", "constraint", f"unknown constraint kind {kind!r}")
        elif obs is not None and val is not None and (obs > val) != bool(viol):
            add("fail", "constraint",
                f"observed {obs} vs {kind} limit {val} disagrees with violated={viol}")
        pol_con = (rec.get("policy") or {}).get("constraint_honoured")
        if pol_con and kind and pol_con != kind:
            add("fail", "constraint",
                f"policy honours {pol_con} but episode judged on {kind}")

    # ---- control episodes: an oracle whose answer is known a priori ------
    policy = (rec.get("policy") or {}).get("name")
    sp = m.get("speedup")
    if policy == "none" and sp is not None:
        if abs(sp - 1.0) > (NOISE_FLOOR - 1.0):
            add("fail", "control",
                f"no-op policy scored {sp}x, outside the {NOISE_FLOOR}x noise floor -- "
                "the measurement, not the policy, is wrong")
    if term.get("configuration") == [] and sp is not None and abs(sp - 1.0) > (NOISE_FLOOR - 1.0):
        add("fail", "control", f"empty configuration scored {sp}x")

    # ---- magnitude: suspect until independently confirmed ----------------
    if sp is not None and sp > SUSPECT_SPEEDUP:
        add("suspect", "magnitude",
            f"speedup {sp}x exceeds {SUSPECT_SPEEDUP}x; treat as a measurement-bug "
            "suspect until reproduced independently")
    if sp is not None and sp <= 0:
        add("fail", "magnitude", f"non-positive speedup {sp}")

    # ---- did the POLICY actually run? -------------------------------------
    # An aborted search records configuration=[] and a ~1.0x speedup, which is
    # internally consistent and therefore invisible to every other check here. That
    # is how 31 TPC-H episodes passed while their search had thrown UndefinedTable on
    # the first cost evaluation. Look at the recorded error directly.
    perr = term.get("policy_error")
    if perr:
        add("fail", "policy_error",
            f"the policy raised and produced no result: {str(perr).splitlines()[0][:120]}")
    pol = (rec.get("policy") or {}).get("name")
    # A query-optimization episode always emits a configuration (possibly "keep the
    # default plan"), so an empty list there still means the search produced nothing.
    if pol and pol != "none" and term.get("configuration") == []:
        add("fail", "empty_configuration",
            f"policy {pol!r} selected no indexes -- an aborted search looks identical "
            "to a legitimate 'nothing helps', so it is refused rather than admitted")

    # ---- did anything actually happen ------------------------------------
    if not rec["events"]:
        add("fail", "events", "no events recorded")
    if term.get("measured") is None:
        add("fail", "terminal", "no measured outcome")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="record .json files or directories")
    ap.add_argument("--quarantine", default=None,
                    help="move failing records here (with a .failures.json alongside)")
    ap.add_argument("--strict", action="store_true",
                    help="treat 'suspect' as failure too")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files += [os.path.join(p, x) for x in sorted(os.listdir(p)) if x.endswith(".json")]
        else:
            files.append(p)

    n_ok = n_fail = n_suspect = 0
    for path in files:
        try:
            rec = json.load(open(path))
        except Exception as e:
            print(f"FAIL  {os.path.basename(path)}: unreadable ({e})")
            n_fail += 1
            continue
        findings = validate(rec)
        fails = [x for x in findings if x.level == "fail"]
        suspects = [x for x in findings if x.level == "suspect"]
        if args.strict:
            fails, suspects = fails + suspects, []
        name = os.path.basename(path)
        if fails:
            n_fail += 1
            print(f"FAIL  {name}")
            for x in fails:
                print(f"        [{x.check}] {x.detail}")
            if args.quarantine:
                os.makedirs(args.quarantine, exist_ok=True)
                shutil.move(path, os.path.join(args.quarantine, name))
                json.dump([x.__dict__ for x in findings],
                          open(os.path.join(args.quarantine, name + ".failures.json"), "w"),
                          indent=2)
        elif suspects:
            n_suspect += 1
            print(f"SUSPECT {name}")
            for x in suspects:
                print(f"        [{x.check}] {x.detail}")
        else:
            n_ok += 1

    print(f"\n{n_ok} passed, {n_suspect} suspect, {n_fail} failed"
          + (f" (quarantined to {args.quarantine})" if args.quarantine and n_fail else ""))
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
