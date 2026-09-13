#!/usr/bin/env python3
"""
protox_harvest.py -- turn a Proto-X Ray trial into a Gen-DBA training record.

WHY THIS EXISTS
    Every one of the 290 episodes collected so far is SINGLE-SHOT: a policy is asked
    once for a configuration, it answers, we measure. Proto-X is an RL agent: it takes
    a SEQUENCE of actions against a live database, sees the reward of each, and adapts.
    That produces multi-step trajectories with intermediate rewards -- the shape that
    matters for RL with tool calls, and the shape nothing in the corpus currently has.
    It also tunes knobs and indexes in ONE action space.

THE SCHEMA DECISION, which HANDOVER.md §7 flagged as the thing to settle first:

    An RL trajectory is N decisions in ONE episode, not N episodes.

    Splitting a trajectory into N episodes would destroy exactly what makes it
    valuable. Step k's action is conditioned on the state that steps 0..k-1 produced;
    as standalone episodes each step would claim a starting state it did not start
    from, and the credit assignment between them -- the reason to collect an RL
    trace at all -- would be unrecoverable. So: one trial, one episode, N steps.

    record.py already supports this without modification: `events` is an ordered,
    lossless stream, so N steps are N x (decide, apply, verify) event groups. What
    this file adds is a `step` field on trajectory events, and per-step MEASURED
    reward -- rather than a single terminal outcome.

    The task kind is `multi_component_tuning`: the same task UniTune performs (knobs
    + indexes), reached by a different method. The method lives in `policy`, not in
    the task -- otherwise a consumer cannot compare a bandit and an RL agent on the
    same task, which is one of the more interesting comparisons the corpus enables.

MOVES (docs/dba_loop.md)
    Move 3 SCREEN CHEAPLY is recorded ABSENT with a reason: Proto-X performs no
    what-if screening -- every action is really applied and really measured. That is
    the same treatment the ISE algorithms get for Move 2, and it is recorded rather
    than inferred, per the corpus's third rule.

    Move 2 HYPOTHESIZE is likewise absent: the agent emits an action from a policy
    network, not a stated hypothesis about why a change should help.

TRACE FORMATS -- all verified against the writers, not guessed
    stdout          `HPO Configuration: {...}`            hpo.py:58 (a python dict repr)
    output.log      `Baseilne Metric: {m}. Baseline Reward: {r}`      tune.py:128
                    NOTE the misspelling. It is in the source; match it exactly.
    output.log      `Benchmark iteration with metric {m} (reward: {r}) (q_timeout: {q})`
                                                                  envs/workload.py:773
    output.log      a following line containing `mv` and `repository` names the
                    directory that evaluation's artifacts were moved into.
                    This pairing is how a metric is attached to a configuration;
                    it is the same pairing scripts/replay_mythril.py:63-88 relies on.
    repository/<ts>/act_sql.txt      CREATE INDEX, blank line, then `knob = value`
                                                                 envs/repository.py:39
    repository/<ts>/run.raw.csv      per-query latency, µs      envs/workload.py:672
    repository/<ts>/run.plans        qid / prefix+knobs / EXPLAIN JSON, blank, blank
                                                                 envs/workload.py:637
    repository/<ts>/run.metrics.json flattened pg_stat_* state   envs/workload.py:651
    repository/baseline/             the untuned reference run     envs/pg_env.py:366

CENSORING
    A query whose measured latency equals the per-query timeout did not fail, it was
    CUT OFF: the true value is >= the limit. replay_mythril.py:100 detects this the
    same way. Recorded as censored with the limit as a lower bound, never as a
    failure and never as a missing value.
"""
from __future__ import annotations

import os as _os

GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")
GENDBA_BUILD = _os.environ.get("GENDBA_BUILD", "/mnt/protox")
GENDBA_DATA = _os.environ.get("GENDBA_DATA", "/data/protox")

import argparse
import ast
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
import yaml

import record as rec
from record import Episode, ESTIMATED, MEASURED, DERIVED, DECLARED

REPO = GENDBA_REPO
PG_BIN = f"{GENDBA_BUILD}/pg15/bin"


# ===================================================================== log parsing
class TraceError(Exception):
    """The trial's trace is not parseable. Never guessed around -- raised."""


def _hpo_config(trial: Path) -> dict:
    """
    hpo.py:58 prints `HPO Configuration: {...}` as a python dict repr, so it is
    read with ast.literal_eval. Not json: the repr carries single quotes and None.
    """
    for name in ("stdout", "output.log", "stderr"):
        p = trial / name
        if not p.exists():
            continue
        for line in p.read_text(errors="replace").splitlines():
            if "HPO Configuration: " in line:
                raw = line.split("HPO Configuration: ", 1)[1].strip()
                try:
                    return ast.literal_eval(raw)
                except Exception:
                    # A dict repr containing non-literals (numpy scalars, objects)
                    # is not worth a bespoke parser; the fields we need are read
                    # from mythril_args in the trial config instead.
                    return {}
    return {}


def _trace_file(trial: Path) -> Path:
    """
    utils/logger.py writes both; which one carries the DEBUG `mv` lines depends on
    how the trial was launched. Pick the one that actually contains the pairing we
    need rather than hardcoding, and say so if neither does.
    """
    best, best_n = None, -1
    for name in ("output.log", "stderr", "stdout"):
        p = trial / name
        if not p.exists():
            continue
        n = sum(1 for ln in p.read_text(errors="replace").splitlines()
                if "Benchmark iteration with metric" in ln)
        if n > best_n:
            best, best_n = p, n
    if best is None or best_n <= 0:
        raise TraceError(
            f"no 'Benchmark iteration with metric' lines in {trial}/"
            "{output.log,stderr,stdout} -- the trial produced no evaluation")
    return best


# A float, bounded -- not a character class. A class like [-\d.eE+]+ also matches a
# following sentence period, and float() then raises on "123.5.".
_FLOAT = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

_METRIC_RE = re.compile(
    rf"Benchmark iteration with metric\s+(?P<metric>{_FLOAT})\s+"
    rf"\(reward:\s*(?P<reward>{_FLOAT}|nan|None)\)\s+"
    r"\(q_timeout:\s*(?P<qt>[^)]*)\)")

# tune.py:133. One Ray trial contains SEVERAL RL episodes: envs/pg_env.py:520 ends an
# episode at `current_step >= horizon`, and the env then resets. Steps either side of
# that boundary are NOT one continuous trajectory -- pg_env.reset() either restores
# the pristine snapshot or shifts the database to a requested configuration, so step
# k+1 is not conditioned on step k's state across a boundary.
#
# Recording the boundary is the whole point: without it a consumer reads N*horizon
# steps as one trajectory and the conditioning it infers is false.
_EPISODE_RE = re.compile(r"Starting episode:\s*(?P<ep>\d+),\s*iteration:\s*(?P<it>\d+)")


def parse_steps(trial: Path) -> tuple[dict | None, list[dict]]:
    """
    Walk the trace once, pairing each evaluation with the repository directory its
    artifacts were moved into.

    The pairing is positional: a `Benchmark iteration with metric` line, then the
    next `mv ... repository ...` line. Both the shipped replayers rely on exactly
    this, so a change to it would break them too and would be noticed.
    """
    path = _trace_file(trial)
    baseline = None
    steps: list[dict] = []
    pending = None
    cur_episode = cur_iteration = None

    # ORDERING, verified against a real trial -- it is not what it looks like.
    #
    #   01:24:12  Benchmark iteration with metric 102.684367 (reward: ...)
    #   01:24:12  Running ['/usr/bin/mv', ..., 'repository//baseline']
    #   01:24:19  Baseilne Metric: 102.684367. Baseline Reward: 2.0
    #
    # The FIRST evaluation is the baseline run itself, and the `Baseilne Metric`
    # marker is logged AFTER it, not before. So a parser that starts collecting
    # immediately records the baseline as RL step 0 -- a step with no action and no
    # act_sql.txt, which shifts every subsequent step index and can win best_step.
    #
    # Everything before the marker is therefore skipped. scripts/replay_mythril.py:66
    # guards this with `start_found` for the same reason; that guard is the point of
    # the structure, not just a way to grab a start timestamp.
    for line in path.read_text(errors="replace").splitlines():
        if baseline is None and "Baseilne Metric" in line:
            # The misspelling is in tune.py:128. Matching "Baseline" finds nothing.
            try:
                # The value is followed by a sentence-ending '.', so a character-class
                # float pattern swallows it and float() then raises -- which the
                # except below would silently turn into "no baseline recorded".
                # Match a real float and stop.
                m = float(re.search(rf"Baseilne Metric:\s*({_FLOAT})", line).group(1))
                r = re.search(rf"Baseline Reward:\s*({_FLOAT}|nan|None)", line)
                baseline = {"metric": m,
                            "reward": float(r.group(1)) if r and r.group(1) not in ("nan", "None") else None,
                            "line": line.strip()}
            except Exception:
                baseline = {"metric": None, "reward": None, "line": line.strip()}
            continue

        if baseline is None:
            # Pre-marker: the baseline evaluation and its mv. Not a step.
            continue

        e = _EPISODE_RE.search(line)
        if e:
            cur_episode = int(e.group("ep"))
            cur_iteration = int(e.group("it"))
            continue

        m = _METRIC_RE.search(line)
        if m:
            try:
                qt = ast.literal_eval(m.group("qt").strip())
            except Exception:
                qt = m.group("qt").strip()
            try:
                reward = float(m.group("reward"))
            except ValueError:
                reward = None
            pending = {"metric": float(m.group("metric")), "reward": reward,
                       "q_timeout": qt, "line": line.strip(),
                       "rl_episode": cur_episode, "rl_iteration": cur_iteration}
            continue

        if pending is not None and "mv" in line and "repository" in line:
            folder = None
            if "Running " in line:
                try:
                    argv = ast.literal_eval(line.split("Running ", 1)[1].strip())
                    folder = str(argv[-1]).rstrip("/").split("/")[-1]
                except Exception:
                    folder = None
            if folder is None:
                m2 = re.search(r"repository/([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9\-]+)", line)
                folder = m2.group(1) if m2 else None
            # Belt and braces: `repository/baseline` is the reference run, never an
            # action. If it ever appears after the marker, it is still not a step.
            if folder and folder != "baseline":
                pending["folder"] = folder
                steps.append(pending)
                pending = None
            elif folder == "baseline":
                pending = None

    return baseline, steps


# ================================================================ step artifacts
def read_act_sql(d: Path) -> dict:
    """
    envs/repository.py:39 writes the index DDL, a blank line, then `knob = value`
    lines. Both halves are kept: the index is the physical-design half of the action
    and the knobs are the configuration half, and the corpus has to be able to tell
    them apart.
    """
    p = d / "act_sql.txt"
    if not p.exists():
        return {"index_sql": None, "knobs": {}, "raw": None}
    raw = p.read_text(errors="replace")
    idx_part, _, knob_part = raw.partition("\n\n")
    knobs = {}
    for line in knob_part.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            knobs[k.strip()] = v.strip()
    idx_sql = idx_part.strip() or None
    return {"index_sql": idx_sql, "knobs": knobs, "raw": raw}


def read_raw_csv(d: Path, q_timeout_s: float | None) -> dict:
    """
    Per-query latency in MICROSECONDS (envs/workload.py:672), converted to ms once,
    here, so no consumer has to guess the unit.

    A query at exactly the per-query timeout was CENSORED, not failed: its true
    latency is >= the limit. Conflating the two once turned a 108 ms TPC-C workload
    into a measured 900,112 ms, so the distinction is carried explicitly.
    """
    p = d / "run.raw.csv"
    if not p.exists():
        return {}
    per_q, censored = {}, {}
    penalty_ms = 0.0
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            qid = row.get("Transaction Name")
            lat = row.get("Latency (microseconds)")
            if not qid or lat in (None, ""):
                continue
            ms = float(lat) / 1000.0

            # The PENALTY row (envs/workload.py:699) is written as qid "P" with phase
            # PENALTY. It is NOT a query: it is a synthetic 3 s (or computed) penalty
            # added when the workload was cut off early. Recording it among the
            # per-query latencies would invent a query that does not exist and
            # corrupt any per-query analysis, so it is kept separately.
            if (row.get("Phase Id (index in config file)") or "").strip() == "PENALTY" \
                    or qid == "P":
                penalty_ms += round(ms, 4)
                continue

            per_q[qid] = round(ms, 4)
            if q_timeout_s and abs(ms - q_timeout_s * 1000.0) < 1e-6:
                censored[qid] = {"limit_ms": q_timeout_s * 1000.0,
                                 "reason": "per-query timeout reached; true latency >= limit"}

    workload_ms = round(sum(per_q.values()), 4)
    return {"per_query_ms": per_q,
            # The sum of REAL query latencies. Proto-X's own metric is this plus the
            # penalty; both are kept so its metric stays reconstructible without
            # putting a non-measurement into a measured per-query field.
            "workload_ms": workload_ms,
            "penalty_ms": round(penalty_ms, 4),
            "protox_metric_ms": round(workload_ms + penalty_ms, 4),
            "stopped_early": penalty_ms > 0,
            "censored": censored}


def read_plans(d: Path) -> list[dict]:
    """
    envs/workload.py:637 writes, per query: a qid line, a `{prefix}: {knobs}` line,
    the EXPLAIN JSON, then two blank lines. The full plan is kept -- per-node
    estimated-vs-actual rows are what make cardinality estimation recoverable from
    this corpus, and a digest would discard exactly that.
    """
    p = d / "run.plans"
    if not p.exists():
        return []
    out, lines, i = [], p.read_text(errors="replace").splitlines(), 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        qid = lines[i].strip()
        i += 1
        prefix = lines[i].strip() if i < len(lines) else ""
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip():
            buf.append(lines[i])
            i += 1
        try:
            plan = json.loads("\n".join(buf))
        except Exception:
            plan = {"unparsed": "\n".join(buf)[:20000]}
        out.append({"query": qid, "prefix": prefix, "plan": plan})
    return out


def read_metrics(d: Path) -> dict | None:
    p = d / "run.metrics.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(errors="replace"))
    except Exception:
        return None


def read_prior_state(d: Path) -> dict | None:
    """
    prior_state.txt (envs/repository.py:36) is the state the agent OBSERVED before it
    acted -- a python repr of (knob_dict, indexes). This is Move 1 ORIENT for the
    step: the DBA's "what am I working with" look, taken from the configuration the
    previous step left in place. dba_loop.md Move 6->Move 1: the accepted config
    becomes the state Move 1 of the next iteration observes.
    """
    p = d / "prior_state.txt"
    if not p.exists():
        return None
    raw = p.read_text(errors="replace")
    try:
        val = ast.literal_eval(raw)
        knobs, indexes = (val[0], val[1]) if isinstance(val, tuple) and len(val) >= 2 \
            else (val, None)
        return {"knobs": knobs, "indexes": indexes}
    except Exception:
        # Kept whole rather than dropped: an unparsed prior state is still the
        # orient signal, and a future parser fix can recover it (persist raw).
        return {"raw": raw[:200000]}


# ================================================================ initial state
class Snapshot:
    """
    Fingerprint the environment and the starting state from the SNAPSHOT the trial
    actually started from.

    A measured latency with no record of the machine and server it was measured on is
    an uninterpretable number, and the starting state is what every speedup in the
    episode is relative to. Restoring costs a few minutes once per episode; guessing
    costs the episode's interpretability.
    """

    def __init__(self, tgz: str, port: int = 5448, keep: bool = False):
        self.tgz, self.port, self.keep = tgz, port, keep
        self.pgd = f"{GENDBA_DATA}/_protox_harvest_{port}"
        self.conn = None
        self._started = False

    def __enter__(self):
        if not os.path.exists(self.tgz):
            raise TraceError(f"snapshot not found: {self.tgz}")
        shutil.rmtree(self.pgd, ignore_errors=True)
        os.makedirs(self.pgd, mode=0o700, exist_ok=True)
        subprocess.run(["tar", "xf", self.tgz, "-C", self.pgd, "--strip-components", "1"],
                       check=True)
        with open(f"{self.pgd}/postgresql.conf", "a") as f:
            f.write(f"\nport={self.port}\n")
        subprocess.run([f"{PG_BIN}/pg_ctl", "-D", self.pgd, "-l",
                        f"{self.pgd}/pg.log", "-w", "start"],
                       check=True, capture_output=True)
        self._started = True
        user = os.environ.get("PGUSER", "admin")
        self.conn = psycopg2.connect(
            f"host=localhost port={self.port} dbname=benchbase user={user}")
        self.conn.autocommit = True
        return self

    def __exit__(self, *exc):
        try:
            if self.conn:
                self.conn.close()
        finally:
            if self._started:
                subprocess.run([f"{PG_BIN}/pg_ctl", "-D", self.pgd, "-w", "stop"],
                               capture_output=True)
            if not self.keep:
                shutil.rmtree(self.pgd, ignore_errors=True)
        return False


# ====================================================================== workload
def load_workload(trial: Path, benchmark: str) -> list[dict]:
    """
    Read the benchmark yaml the TRIAL used, not the repo's copy: agents/hpo.py:60
    overwrites query_spec from params.json, so the repo yaml can disagree with what
    the trial actually ran. The trial's copy has absolute query paths already.
    """
    cand = [trial / f"{benchmark}.yaml"] + sorted(trial.glob("*.yaml"))
    spec = None
    for p in cand:
        if p.name in ("config.yaml", "config.yaml2", "model_params.yaml"):
            continue
        try:
            y = yaml.safe_load(p.read_text())
        except Exception:
            continue
        if isinstance(y, dict) and "mythril" in y and "query_spec" in y.get("mythril", {}):
            spec = y["mythril"]["query_spec"]
            break
    if spec is None:
        raise TraceError(f"no benchmark yaml with a query_spec in {trial}")

    qdir, qorder = spec.get("query_directory"), spec.get("query_order")
    if not qdir or not qorder:
        raise TraceError("query_spec names no query_directory/query_order")
    if not os.path.isabs(qdir):
        qdir = f"{REPO}/{qdir}"
    if not os.path.isabs(qorder):
        qorder = f"{REPO}/{qorder}"

    out = []
    for line in open(qorder):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")[:2]
        if len(parts) < 2:
            continue
        qid, fname = parts
        fp = os.path.join(qdir, fname)
        if not os.path.exists(fp):
            continue
        out.append({"id": qid, "file": fname,
                    "text": open(fp).read().strip().rstrip(";")})
    if not out:
        raise TraceError(f"no queries resolved from {qorder} / {qdir}")
    return out


# ======================================================================= episode
def build_episode(trial: Path, benchmark: str, snapshot_tgz: str,
                  probe_port: int, duration_h: float | None,
                  workload_timeout_s: float | None,
                  truncated: bool = False) -> Episode:
    baseline, steps = parse_steps(trial)
    if not steps:
        raise TraceError(f"{trial}: no evaluations with a repository folder")

    hpo = _hpo_config(trial)
    ma = (hpo.get("mythril_args") or {}) if isinstance(hpo, dict) else {}
    horizon = ma.get("horizon") or hpo.get("horizon")
    q_timeout = ma.get("timeout")
    if duration_h is None:
        duration_h = ma.get("duration")
    if workload_timeout_s is None:
        workload_timeout_s = ma.get("workload_timeout")

    task = {
        "id": f"protox-{benchmark}-{trial.name}",
        "benchmark": benchmark,
        "task": "multi_component_tuning",
        "n_queries": 0,                      # filled from the workload below
        "objective": "workload_latency",
        "budget_mb": 0,
        "max_index_width": 0,
        # Proto-X is bounded by WALL CLOCK and an iteration count, never by storage.
        # Judging it against a budget_MB it never received would produce a constraint
        # verdict that means nothing.
        "constraint_kind": "tuning_budget_s",
        "constraint_value": float(duration_h) * 3600.0 if duration_h else None,
        "seed": ma.get("seed", 0),
        "horizon": horizon,
        "per_query_timeout_s": q_timeout,
        "workload_timeout_s": workload_timeout_s,
    }
    policy = {
        "name": "protox_wolp",
        "kind": "rl_agent (Wolpertinger DDPG over a joint index+knob action space)",
        "source": "Proto-X (this repo): hpo.py / agents/wolp",
        "constraint_honoured": "tuning_budget_s",
        "method": "reinforcement_learning",
        "trajectory": True,
        "action_space": "joint(index, knob)",
        "n_steps": len(steps),
        "params": {k: ma.get(k) for k in
                   ("horizon", "duration", "workload_timeout", "timeout",
                    "max_iterations", "target", "reward") if k in ma},
    }

    ep = Episode(task=task, policy=policy, collector="protox_harvest.py", repo=REPO)

    queries = load_workload(trial, benchmark)
    ep.set_workload(queries)
    task["n_queries"] = len(queries)

    with Snapshot(snapshot_tgz, port=probe_port) as snap:
        ep.fingerprint_environment(snap.conn, snapshot=snapshot_tgz)
        ep.set_initial_state(snap.conn)

    # Header blocks the ISE episodes carry (223 of 265 do); brought in for format
    # parity so a trajectory record is comparable field-for-field to a single-shot one.
    # The action space is JOINT here -- indexes AND knobs -- which is what makes
    # Proto-X's task multi_component rather than pure index selection.
    first_act = read_act_sql(trial / "repository" / steps[0]["folder"])
    ep.header["action_space"] = {
        "source": "Proto-X joint index+knob action space (agents/wolp)",
        "kind": "joint(index, knob)",
        "n_knob_dimensions": len(first_act["knobs"]),
        "n_indexable_tables": len(ep.header.get("initial_state", {}).get("tables", [])),
        "note": "a Proto-X action sets one index plus every tunable knob at once; the "
                "index half is drawn from the pre-trained embedder's column space, "
                "not the full indexable-column set the ISE algorithms use",
    }
    ep.header["tool_vocabulary"] = ["OBSERVE", "REALIZE", "PROBE"]

    # ---- Move 1 ORIENT (episode start): the baseline run is the agent's first look.
    base_dir = trial / "repository" / "baseline"
    base_meas = read_raw_csv(base_dir, q_timeout) if base_dir.exists() else {}
    ep.add("orient", "tool_call", verb="OBSERVE",
           args={"source": "repository/baseline", "scope": "baseline"},
           payload={"baseline_metric": (baseline or {}).get("metric"),
                    "baseline_reward": (baseline or {}).get("reward"),
                    "per_query_ms": base_meas.get("per_query_ms"),
                    "workload_ms": base_meas.get("workload_ms"),
                    "censored": base_meas.get("censored"),
                    "state": read_metrics(base_dir) if base_dir.exists() else None},
           duration_s=0.0, provenance=MEASURED, produced_by="protox:pg_env.baseline")

    # ---- Moves 2 and 3: absent, with the reason. Recorded, never invented.
    ep.absent("hypothesize",
              "Proto-X emits an action from a policy network; it states no hypothesis "
              "about why a change should help, so there is nothing to record here.",
              produced_by="protox_wolp")
    ep.absent("screen",
              "Proto-X performs no what-if screening: every action is really applied "
              "to a live database and really measured. There is no estimated cost to "
              "contrast with the measurement, unlike the ISE algorithms.",
              produced_by="protox_wolp")

    # ---- The trajectory: N x (decide, apply, verify), each tagged with its step.
    best = {"i": None, "metric": None}
    prev_rl_episode = None
    for i, st in enumerate(steps):
        d = trial / "repository" / st["folder"]
        act = read_act_sql(d)
        meas = read_raw_csv(d, q_timeout)
        plans = read_plans(d)
        state = read_metrics(d)

        boundary = (st.get("rl_episode") is not None
                    and st["rl_episode"] != prev_rl_episode)

        # ---- Move 6 KEEP OR REVERT (recorded BEFORE this step's orient, because it
        # is what set up the state this step observes). Proto-X DOES perform Move 6
        # (dba_loop.md 3 gives it a checkmark): within a horizon the accepted config
        # is KEPT and becomes the next step's orient; at the horizon it is REVERTED --
        # envs/pg_env.py:300 resets the database from the snapshot. Recording it is
        # what makes this a trajectory rather than independent (problem, answer) pairs.
        if i > 0:
            if boundary:
                ep.add("state", "state",
                       payload={"event": "revert",
                                "rl_episode": st["rl_episode"],
                                "first_step": i,
                                "note": "horizon reached: the previous RL episode's "
                                        "configuration was REVERTED (database reset to "
                                        "the snapshot). Steps before and after this "
                                        "point are SEPARATE trajectories; the action "
                                        "below is not conditioned on the earlier state"},
                       provenance=DERIVED, produced_by="protox:pg_env.reset")
            else:
                ep.add("state", "state",
                       payload={"event": "keep",
                                "step": i - 1,
                                "rl_episode": st.get("rl_episode"),
                                "note": "the previous step's configuration was KEPT and "
                                        "is the state this step observes"},
                       provenance=DERIVED, produced_by="protox:pg_env")
        if boundary:
            prev_rl_episode = st["rl_episode"]

        # ---- Move 1 ORIENT (per step): the pg_stat_* state + config the agent saw
        # before choosing this action. Sourced from prior_state.txt, which is exactly
        # the pre-action state (envs/repository.py:36).
        # prior_state.txt is the PRE-action state (config + indexes). The pre-action
        # pg_stat_* vector is the previous step's MEASURED result, already recorded in
        # its verify event, so it is referenced rather than duplicated (it is 490 keys
        # per step) -- and read_metrics(d) is deliberately NOT used here, since that is
        # the POST-action vector and belongs to Move 5, not Move 1.
        prior = read_prior_state(d)
        ep.add("orient", "tool_call", verb="OBSERVE",
               args={"step": i, "scope": "pre_action", "source": "prior_state.txt"},
               payload={"prior_config": prior,
                        "prior_state_vector_ref":
                            ("baseline" if i == 0
                             else f"verify event of step {i - 1}")},
               duration_s=0.0, provenance=MEASURED, produced_by="protox:pg_stat")

        ep.add("decide", "decision",
               payload={"step": i,
                        "rl_episode": st.get("rl_episode"),
                        "rl_iteration": st.get("rl_iteration"),
                        "accepted": {"index_sql": act["index_sql"],
                                     "n_knobs": len(act["knobs"])},
                        # An RL action is a point sampled from a continuous space:
                        # there is no enumerated set of alternatives that were
                        # considered and rejected. Recording a fabricated `rejected`
                        # list would be contradictory supervision, so the absence is
                        # stated instead.
                        "rejected": None,
                        "rejected_absent_reason":
                            "an RL action is a point in a continuous space, not a "
                            "choice among enumerated candidates; no alternatives were "
                            "scored, so none are recorded",
                        "repository": st["folder"]},
               produced_by="protox_wolp")

        ep.tool_call("REALIZE",
                     {"step": i, "repository": st["folder"]},
                     {"index_sql": act["index_sql"], "knobs": act["knobs"],
                      "act_sql_raw": act["raw"]},
                     0.0, "apply", DECLARED, "protox:repository.add")

        ep.tool_call("PROBE",
                     {"step": i, "repository": st["folder"]},
                     {"metric": st["metric"],
                      "reward": st["reward"],
                      "q_timeout": st["q_timeout"],
                      "per_query_ms": meas.get("per_query_ms"),
                      "workload_ms": meas.get("workload_ms"),
                      "penalty_ms": meas.get("penalty_ms"),
                      "protox_metric_ms": meas.get("protox_metric_ms"),
                      "stopped_early": meas.get("stopped_early"),
                      "censored": meas.get("censored"),
                      "plans": plans,
                      "state": state},
                     0.0, "verify", MEASURED, "protox:workload.execute")

        # Rank by Proto-X's OWN metric, not by the sum of executed queries. A step cut
        # off early has a smaller query sum purely because it ran fewer queries, so
        # ranking on that would make the worst configurations win. Proto-X's metric
        # includes the early-kill penalty precisely so that a cut-off run scores
        # badly, which is the comparison the agent itself optimises.
        rank = meas.get("protox_metric_ms")
        if rank is not None:
            if best["metric"] is None or rank < best["metric"]:
                best = {"i": i, "metric": rank, "folder": st["folder"],
                        "act": act, "meas": meas}

    # Move 6 is NOT recorded here: it is emitted per step in the loop above (keep
    # within a horizon, revert at a boundary), which is where the keep/revert
    # decision actually happens. The final step's configuration is left in place by
    # the run; whether it is ultimately kept is the terminal outcome below.

    # ---- terminal ----------------------------------------------------------
    before = base_meas.get("per_query_ms") or {}
    after = (best.get("meas") or {}).get("per_query_ms") or {}
    wl_before = base_meas.get("workload_ms")
    wl_after = (best.get("meas") or {}).get("workload_ms")

    # A speedup with no baseline to be relative to is not a weak result, it is an
    # uninterpretable one. Refuse rather than emit an episode whose outcome cannot be
    # computed -- "can't prove it" is quarantine, not accept.
    if not before or wl_before is None:
        raise TraceError(
            f"{trial}: repository/baseline has no measured run, so no outcome can be "
            "computed. The trial did not complete its reference run.")

    # A query measured before but absent after (or the reverse) makes the two totals
    # cover different workloads, and their ratio is then not a speedup at all. The
    # gate refuses that outright unless the difference is a LABELLED outcome, so
    # label it here -- with what is actually known, which is only that the query does
    # not appear in that configuration's run.raw.csv.
    # When the workload is cut off (envs/workload.py:614, early_workload_kill), the
    # queries after the cut-off simply NEVER RAN. Their latency is unknown -- not
    # zero, not a failure. That is a censored observation at the WORKLOAD level, and
    # it is the dominant censoring mode here, well ahead of a per-query timeout.
    stopped_early = bool((best.get("meas") or {}).get("stopped_early"))
    failed = {}
    for q in set(before) - set(after):
        failed[q] = {
            "outcome": "not_executed" if stopped_early else "absent_after",
            "reason": ("the workload was cut off before this query ran "
                       "(early_workload_kill); its latency is UNKNOWN, not zero and "
                       "not a failure") if stopped_early else
                      ("measured in the baseline run but absent from the best step's "
                       "run.raw.csv"),
            "censored": bool(stopped_early),
            "baseline_ms": before[q]}
    for q in set(after) - set(before):
        failed[q] = {"outcome": "absent_before",
                     "reason": "measured at the best step but absent from the "
                               "baseline run.raw.csv",
                     "after_ms": after[q]}
    # THE SPEEDUP MUST BE LIKE-FOR-LIKE.
    #
    # When a step is cut off early the baseline covers 113 queries and the step covers
    # 108, so before/after sums describe DIFFERENT workloads and their ratio is not a
    # speedup -- it would report an improvement produced entirely by running fewer
    # queries, and it would be largest exactly when the configuration was worst. That
    # is the most dangerous kind of wrong number: it looks like a great result.
    #
    # So the headline speedup is computed over the queries BOTH runs actually
    # measured, and the set it covers is recorded alongside it. Proto-X's own metric
    # comparison is kept too -- that is what the agent optimised, penalty included --
    # but it is labelled separately rather than conflated with a measured speedup.
    common = sorted(set(before) & set(after))
    before_common = round(sum(before[q] for q in common), 4) if common else None
    after_common = round(sum(after[q] for q in common), 4) if common else None
    speedup = (round(before_common / after_common, 4)
               if before_common and after_common and after_common > 0 else None)

    protox_before = base_meas.get("protox_metric_ms")
    protox_after = (best.get("meas") or {}).get("protox_metric_ms")
    protox_speedup = (round(protox_before / protox_after, 4)
                      if protox_before and protox_after and protox_after > 0 else None)

    configuration = []
    if best.get("act"):
        if best["act"]["index_sql"]:
            configuration.append({"arm": "index", "config": best["act"]["index_sql"]})
        if best["act"]["knobs"]:
            configuration.append({"arm": "knob", "config": best["act"]["knobs"]})

    censored = dict(base_meas.get("censored") or {})
    censored.update((best.get("meas") or {}).get("censored") or {})

    elapsed = None
    try:
        elapsed = round(os.path.getmtime(trial / "repository" / steps[-1]["folder"])
                        - os.path.getmtime(trial / "repository" / "baseline"), 2)
    except Exception:
        pass

    budget = task["constraint_value"]
    ep.finish(
        configuration=configuration,
        measured={
            "workload_ms_before": wl_before,
            "workload_ms_after": wl_after,
            "per_query_ms_before": before,
            "per_query_ms_after": after,
            "speedup": speedup,
            # What the speedup is actually a ratio of. Without this a consumer
            # reasonably assumes workload_ms_before / workload_ms_after.
            "speedup_basis": {
                "kind": "common_query_set",
                "n_queries": len(common),
                "queries": common,
                "workload_ms_before": before_common,
                "workload_ms_after": after_common,
                "provenance": DERIVED,
                "note": "computed over the queries BOTH runs measured. When a run is "
                        "cut off early the two totals cover different workloads and "
                        "their ratio is not a speedup.",
            },
            # Proto-X's own objective: its metric includes the early-kill penalty.
            # Kept because it is what the agent actually optimised, and labelled so it
            # is never mistaken for a measured like-for-like speedup.
            "protox_metric_ms_before": protox_before,
            "protox_metric_ms_after": protox_after,
            "protox_speedup": protox_speedup,
            "penalty_ms_before": base_meas.get("penalty_ms"),
            "penalty_ms_after": (best.get("meas") or {}).get("penalty_ms"),
            "stopped_early_after": stopped_early,
            "censored_queries": censored,
            "failed_queries": failed,
            "best_step": best.get("i"),
            "n_steps": len(steps),
            # The trajectory, projected for consumers that want the reward curve
            # without walking the event stream. Derived from the events above, and
            # labelled as such.
            "step_metrics": [{"step": i, "metric": s["metric"], "reward": s["reward"],
                              "rl_episode": s.get("rl_episode"),
                              "repository": s["folder"]} for i, s in enumerate(steps)],
            # One Ray trial contains several RL episodes (horizon-length trajectories
            # separated by an environment reset). Both projections are recoverable
            # from the event stream; this says how many there were without walking it.
            "n_rl_episodes": len({s.get("rl_episode") for s in steps
                                  if s.get("rl_episode") is not None}) or None,
            "horizon": horizon,
            "baseline_metric": (baseline or {}).get("metric"),
            "provenance": MEASURED,
            "protocol": {
                "measured_by": "proto-x internal workload execution",
                "per_query_timeout_s": q_timeout,
                "workload_timeout_s": workload_timeout_s,
                "note": "latencies are Proto-X's own per-query measurements from "
                        "run.raw.csv (microseconds), converted to ms here; they are "
                        "NOT re-measured by this harness",
            },
        },
        constraint={"kind": "tuning_budget_s", "value": budget,
                    "observed": elapsed,
                    "violated": bool(elapsed and budget and elapsed > budget * 1.10),
                    "note": "wall clock from the baseline run to the last evaluation"},
        trajectory=True,
        # A run stopped by hand or by the clock did not reach its horizon, so its
        # last trajectory is incomplete. Saying so is the difference between "the
        # agent stopped improving here" and "we stopped watching here" -- a consumer
        # cannot tell them apart from the step count alone.
        truncated=truncated,
        policy_error=None,
    )
    return ep


# ========================================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trial", required=True,
                    help="a Ray trial directory (contains repository/, output.log)")
    ap.add_argument("--benchmark", default="job", choices=["job", "tpch", "dsb"])
    ap.add_argument("--snapshot", default=None,
                    help="snapshot the trial started from; default: the benchmark's")
    ap.add_argument("--out-dir", default=f"{REPO}/gendba_records/episodes")
    ap.add_argument("--quarantine-dir", default=f"{REPO}/gendba_records/quarantine")
    ap.add_argument("--probe-port", type=int, default=5448)
    ap.add_argument("--duration-h", type=float, default=None)
    ap.add_argument("--workload-timeout-s", type=float, default=None)
    ap.add_argument("--truncated", action="store_true",
                    help="the run was stopped before its horizon/budget (killed by "
                         "hand, the clock, or a node going away). Stamps the episode "
                         "so 'the agent stopped improving' is not confused with 'we "
                         "stopped watching'.")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report; write nothing")
    args = ap.parse_args()

    trial = Path(args.trial).resolve()
    if not trial.is_dir():
        sys.exit(f"not a directory: {trial}")

    default_snap = {"job": "job.tgz", "tpch": "tpch_sf10.tgz", "dsb": "dsb_sf10.tgz"}
    snap = args.snapshot or f"{GENDBA_DATA}/data/{default_snap[args.benchmark]}"

    try:
        ep = build_episode(trial, args.benchmark, snap, args.probe_port,
                           args.duration_h, args.workload_timeout_s,
                           truncated=args.truncated)
    except TraceError as e:
        sys.exit(f"TRACE ERROR: {e}")

    d = ep.to_dict()
    m = d["terminal"]["measured"]
    print(f"episode {d['episode_id']}")
    print(f"  steps        {m['n_steps']}  (best at step {m['best_step']})")
    print(f"  events       {d['event_count']}  moves={','.join(d['moves_present'])}")
    print(f"  before/after {m['workload_ms_before']} -> {m['workload_ms_after']} ms")
    print(f"  speedup      {m['speedup']}")
    print(f"  censored     {len(m['censored_queries'])}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    # The gate runs BEFORE the record enters the corpus, never after.
    import validate as val
    findings = val.validate(d)
    fails = [f for f in findings if f.level == "fail"]
    dest = Path(args.quarantine_dir if fails else args.out_dir) / f"{d['episode_id']}.json"
    ep.write(str(dest))
    for f in findings:
        print(f"  {f.level.upper():8} [{f.check}] {f.detail}")
    if fails:
        with open(str(dest).replace(".json", ".failures.json"), "w") as fh:
            json.dump([f.__dict__ for f in findings], fh, indent=2)
        print(f"\nQUARANTINED -> {dest}")
        sys.exit(1)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
