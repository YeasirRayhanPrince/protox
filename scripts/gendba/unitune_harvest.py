#!/usr/bin/env python3
"""
unitune_harvest.py -- harvest UniTune's META-DECISION as Gen-DBA episodes.

Every episode in the corpus so far optimizes ONE fixed problem: "given this workload
and this budget, pick indexes". The policy searches within that. It never chooses
WHAT KIND of problem to work on.

UniTune's TopAdvisor does. Each trial it picks an arm -- knob or index -- by Thompson
sampling over per-arm Beta posteriors, holding the other arms' current best
configuration as context. That is a decision one level up, and nothing else we run
produces it.

WHAT WE HOOK
    optimize_ts()   the arm choice: sampled value per arm, the argmax, and the
                    Beta (S+1, F+1) posteriors that produced it  -> MOVE 4
    block_do_next() the chosen arm's inner run and its measured outcome -> MOVE 5/6

The inner tuners (OtterTune BO for knobs, DBA-Bandit for indexes) are opaque by
nature -- a configuration appears and is measured. We record that honestly as an
outcome rather than inventing a rationale for it, exactly as we do for Proto-X.

The query and view arms need a JVM and Maven; they are stubbed (unitune_patches.py)
and excluded from `components`.
"""
from __future__ import annotations

import os as _os
GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")
GENDBA_BUILD = _os.environ.get("GENDBA_BUILD", "/mnt/protox")
GENDBA_DATA = _os.environ.get("GENDBA_DATA", "/data/protox")

import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
sys.path.insert(0, GENDBA_REPO + "/unitune/UniTune")

import unitune_patches
unitune_patches.apply()                    # must precede any MultiTune import

import psycopg2  # noqa: E402
from record import Episode, ESTIMATED, MEASURED, DERIVED, DECLARED  # noqa: E402
import validate as gate  # noqa: E402


def build_episode(db, args_tune, args_db, benchmark):
    ep = Episode(
        task={"id": f"unitune-{benchmark}-{args_tune.get('task_id')}",
              "benchmark": benchmark,
              "task": "multi_component_tuning",
              "n_queries": 0,
              "objective": "workload_latency",
              "budget_mb": 0, "max_index_width": 0,
              "constraint_kind": "tuning_budget_s",
              "constraint_value": float(args_tune.get("tuning_budget", 0)),
              "seed": 0},
        policy={"name": "unitune_topadvisor",
                "kind": "meta-policy (bandit over sub-tuners)",
                "source": "unitune/UniTune",
                "constraint_honoured": "tuning_budget_s",
                "arm_method": args_tune.get("arm_method"),
                "meta_decision_rule": args_tune.get("arm_method"),
                "components": str(args_tune.get("components")),
                "params": {"sub_budget": args_tune.get("sub_budget"),
                           "block_runs": args_tune.get("block_runs"),
                           "init_runs": args_tune.get("init_runs"),
                           "window_size": args_tune.get("window_size"),
                           "context": args_tune.get("context"),
                           "output_file": args_tune.get("output_file")}},
        collector="scripts/gendba/unitune_harvest.py")
    conn = psycopg2.connect(
        f"host={args_db['host']} port={args_db['port']} dbname={args_db['dbname']} "
        f"user={args_db['user']} password={args_db.get('passwd','')}")
    conn.autocommit = True
    # UniTune tunes the live cluster in place: it applies knobs and builds indexes
    # and does NOT restore between runs, so an episode starts from whatever the
    # previous one left behind. That is materially different from the index-selection
    # episodes, which reset by DDL, and anyone training on this corpus has to be able
    # to see the difference -- so it is declared here rather than left unrecorded.
    ep.fingerprint_environment(conn, snapshot={
        "kind": "live_cluster_no_restore",
        "data_directory": _os.environ.get(
            "GENDBA_UNITUNE_PGDATA", GENDBA_BUILD + "/pg15/bin/pgdata5492"),
        "database": args_db.get("dbname"),
        "resets_between_episodes": False,
        "note": "state carries over between UniTune runs; initial_state below records "
                "what was actually present when this episode started",
        "provenance": DECLARED})
    ep.set_initial_state(conn)
    ep.header["workload"] = {"n_queries": 0, "grouping_key": "template",
                             "n_groups": 0, "groups": [], "queries": [],
                             "split_warning": "workload is driven by UniTune's own "
                                              "query list; see policy.params"}
    conn.close()
    return ep


def _discriminants(advisor, rule):
    """
    What the meta-rule actually compares, per arm, at the moment of choice.

    Each of UniTune's four arm-selection rules ranks the arms by a different
    quantity. Recording "the arm chosen" without the quantity that chose it makes
    the decision unlearnable, so each rule contributes its own discriminant, named
    for what it is rather than flattened into a common "score" field.
    """
    arms = list(advisor.arms)
    if rule == "ts" and hasattr(advisor, "S"):
        return [{"arm": arms[i],
                 "criterion": "beta_posterior",
                 "alpha": float(advisor.S[i] + 1),
                 "beta": float(advisor.F[i] + 1),
                 "posterior_mean": float((advisor.S[i] + 1) /
                                         (advisor.S[i] + advisor.F[i] + 2)),
                 "successes": float(advisor.S[i]), "failures": float(advisor.F[i])}
                for i in range(len(arms))]
    if rule == "rb":
        # ema is defined in alternative_adviser.py itself, not in a utils module;
        # take it from the advisor's own module so we call the exact function the
        # rule calls rather than a same-named reimplementation.
        ema = getattr(sys.modules[type(advisor).__module__], "ema", None)
        if ema is None:                      # subclass defined elsewhere
            from MultiTune.advisor.alternative_adviser import ema
        out = []
        for a in arms:
            r = advisor.rewards.get(a) or []
            try:
                v = float(ema(r, 2, advisor.sliding_window_size)[-1]) if (r and ema) else None
            except Exception:
                v = None
            out.append({"arm": a, "criterion": "ema_of_past_rewards",
                        "ema": v, "n_rewards": len(r),
                        "recent_rewards": [float(x) for x in r[-5:]]})
        return out
    if rule == "alter":
        n = len(arms)
        return [{"arm": arms[i], "criterion": "round_robin_position",
                 "turn_distance": (i - advisor.pull_cnt % n) % n} for i in range(n)]
    return [{"arm": a, "criterion": "unrecorded"} for a in arms]


def _safe_discriminants(advisor, rule):
    try:
        return _discriminants(advisor, rule)
    except Exception as e:
        print(f"discriminant capture failed for {rule} (continuing): "
              f"{type(e).__name__}: {e}")
        return [{"arm": a, "criterion": "unavailable",
                 "capture_error": f"{type(e).__name__}: {e}"} for a in advisor.arms]


def instrument(advisor, ep, rule, checkpoint=None):
    """
    Wrap the arm-selection rule and the sub-tuner run. Control flow is untouched:
    each wrapper calls through to the original and records what it saw.

    All four rules (alter / rb / ts / acq) are wrapped through the same path, so the
    same episode shape describes any of them and they stay comparable -- the only
    thing that differs between two such episodes is HOW the meta-choice was made.
    """
    state = {"pull": 0, "pending": None, "baseline_cost": None,
             "current_iter": 0}

    def record_choice(rule_name, picked, seconds, draws=None, snapshot=None):
        arms = list(advisor.arms)
        # Thompson mutates S/F inside the call (ts_update), so its posteriors must be
        # the ones snapshotted BEFORE the choice; the other rules read state the call
        # does not disturb, so recomputing after is equivalent and simpler.
        disc = {d["arm"]: d for d in (snapshot or _safe_discriminants(advisor, rule_name))}
        # Mirror UniTune's own warm-up predicates exactly (strict <, and ts uses a
        # hardcoded 3 rather than the sliding window). Getting this off by one would
        # label a genuine comparison as a forced sweep, which is the opposite of what
        # the record is for. When draws exist, they settle it outright.
        warm = (draws is None
                and rule_name in ("ts", "rb", "acq")
                and advisor.pull_cnt < len(arms) * (3 if rule_name == "ts"
                                                    else advisor.sliding_window_size))
        chosen = disc.get(picked)

        def margin(other):
            """Signed gap on the rule's own scale; None when the rule has no scale."""
            if draws is not None and picked in draws and other["arm"] in draws:
                return float(draws[other["arm"]] - draws[picked])
            for k in ("ema", "posterior_mean"):
                if chosen and k in other and other.get(k) is not None \
                        and chosen.get(k) is not None:
                    return float(other[k] - chosen[k])
            return None

        ep.decision(
            iteration=state["pull"],
            n_proposed=len(arms),
            selection_rule=(f"{rule_name}: forced warm-up sweep (every arm pulled "
                            f"before any is compared)" if warm else {
                "ts": "argmax over one draw per arm from its Beta(S+1, F+1)",
                "rb": "argmax of EMA over each arm's recent rewards",
                "alter": "round-robin: pull_cnt mod n_arms, no comparison at all",
                "acq": "argmax of each sub-tuner's own acquisition value",
            }.get(rule_name, rule_name)),
            accepted={"arm": picked, "discriminant": chosen,
                      "sampled_value": (draws or {}).get(picked),
                      "provenance": ESTIMATED},
            rejected=[{"arm": d["arm"], "discriminant": d,
                       "sampled_value": (draws or {}).get(d["arm"]),
                       "margin": margin(d), "margin_provenance": ESTIMATED,
                       "reason": ("not this arm's turn in the sweep" if warm
                                  else f"lower {d.get('criterion')} than the chosen arm")}
                      for d in disc.values() if d["arm"] != picked],
            all_discriminants=list(disc.values()),
            sampled_values=draws,
            last_reward_per_arm={a: ((advisor.rewards.get(a) or [])[-1]
                                     if (advisor.rewards.get(a) or []) else None)
                                 for a in arms},
            seconds=round(seconds, 2),
            note=("the arms are sub-problems, not candidate actions: this is a "
                  "decision about WHICH PROBLEM to spend the next trial on"))
        # Remember the iteration this decision carries. The counter is bumped right
        # after, and the state event that follows must label itself with the SAME
        # pull as the decision it belongs to -- otherwise joining state to decision,
        # which is the obvious thing a consumer does, misaligns them by one.
        state["current_iter"] = state["pull"]
        state["pull"] += 1

    def wrap_rule(name, orig):
        def traced(*a, **kw):
            pre_disc = _safe_discriminants(advisor, name) if name == "ts" else None
            # Staged for traced_block, which fires inside orig() below and emits the
            # decision there -- so the record's order matches the real order of
            # events rather than reporting the choice after its consequence.
            state["pending"] = {"rule": name, "snapshot": pre_disc, "draws": None,
                                "t0": time.time()}
            if name == "ts":
                # Thompson's decision IS the sample, not the posterior. Intercept the
                # draws so we record the values that actually produced the argmax
                # rather than re-sampling and getting different ones.
                # Take the module the advisor actually lives in rather than
                # re-importing by name: the name is only correct for one class, and
                # a fresh import here can fail on side effects the real run already
                # paid for at start-up.
                adv_mod = sys.modules[type(advisor).__module__]
                arms = list(advisor.arms)
                real_rvs, calls = adv_mod.ss.beta.rvs, []

                def spy(*aa, **kk):
                    v = real_rvs(*aa, **kk)
                    calls.append(float(v))
                    # ts_update draws nothing in the non-Bernoulli path, so the first
                    # n calls are the arm samples; a warm-up pull draws none at all.
                    if len(calls) == len(arms) and state["pending"]:
                        state["pending"]["draws"] = dict(zip(arms, calls[:len(arms)]))
                    return v
                adv_mod.ss.beta.rvs = spy
                try:
                    orig(*a, **kw)
                finally:
                    adv_mod.ss.beta.rvs = real_rvs
            else:
                orig(*a, **kw)

        return traced

    for name in ("alter", "rb", "ts", "acq"):
        meth = getattr(advisor, f"optimize_{name}", None)
        if meth is not None:
            setattr(advisor, f"optimize_{name}", wrap_rule(name, meth))

    orig_block = advisor.block_do_next

    def traced_block(arm):
        # best_result['all'] is UniTune's running best workload cost, seeded from the
        # default configuration at initialize(). At the first pull nothing has
        # improved yet, so it still IS the default -- capture it there, because that
        # is the only moment the baseline is observable from outside.
        if state["baseline_cost"] is None:
            state["baseline_cost"] = (getattr(advisor, "best_result", {}) or {}).get("all")
        pend = state["pending"] or {}
        state["pending"] = None
        if pend:
            record_choice(pend["rule"], arm,
                          time.time() - pend["t0"],
                          pend.get("draws"), snapshot=pend.get("snapshot"))
        t0 = time.time()
        best_before = json.loads(json.dumps(
            getattr(advisor, "best_result", {}).get(arm, {}), default=str))
        try:
            orig_block(arm)
            err = None
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        best_after = json.loads(json.dumps(
            getattr(advisor, "best_result", {}).get(arm, {}), default=str))
        ep.tool_call("REALIZE", {"arm": arm, "action": "run_sub_tuner"},
                     {"arm": arm,
                      "sub_tuner": str((advisor.args_tune.get("components") or {})),
                      "best_before": best_before, "best_after": best_after,
                      "improved": best_before != best_after,
                      "error": err, "measured": True},
                     time.time() - t0, "verify", MEASURED, f"unitune:{arm}")
        ep.add("state", "state",
               payload={"pull": state.get("current_iter", state["pull"]), "arm": arm,
                        "best_per_arm": json.loads(json.dumps(
                            getattr(advisor, "best_result", {}), default=str))},
               provenance=MEASURED, produced_by="unitune_topadvisor")
        if checkpoint:
            # The run is hours long and the machine has a hard cutoff. Persist after
            # every pull so an interrupted run still yields everything up to the
            # interruption, rather than nothing.
            try:
                ep.write(checkpoint)
            except Exception as e:
                print(f"checkpoint failed (continuing): {type(e).__name__}: {e}")

    advisor.block_do_next = traced_block
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-ini", required=True)
    ap.add_argument("--benchmark", default="job")
    ap.add_argument("--out", default=GENDBA_REPO + "/gendba_records")
    ap.add_argument("--dry-run", action="store_true",
                    help="construct everything and exit without tuning")
    args = ap.parse_args()

    from MultiTune.utils.parser import parse_args as ut_parse
    from MultiTune.database.postgresdb import PostgresDB
    from MultiTune.advisor.alternative_adviser import TopAdvisor

    args_db, args_tune = ut_parse(args.config_ini)
    print(f"arms/components: {args_tune.get('components')}  "
          f"arm_method={args_tune.get('arm_method')}")

    db = PostgresDB(args_tune["task_id"], **args_db)
    advisor = TopAdvisor(db, args_tune)
    print(f"TopAdvisor built. arms = {advisor.arms}")

    ep = build_episode(db, args_tune, args_db, args.benchmark)
    ckpt = os.path.join(args.out, "checkpoints", f"{ep.header['episode_id']}.json")
    state = instrument(advisor, ep, args_tune['arm_method'], checkpoint=ckpt)

    if args.dry_run:
        print("dry run: constructed successfully, not tuning")
        return

    t0 = time.time()
    err = None
    try:
        advisor.run(args_tune["arm_method"])
    except KeyboardInterrupt:
        err = "interrupted"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    observed = round(time.time() - t0, 1)
    limit = float(args_tune.get("tuning_budget", 0))
    evals = _load_evaluations(args_tune.get("output_file"))
    best = json.loads(json.dumps(getattr(advisor, "best_result", {}), default=str))
    ep.finish(configuration=[{"arm": a, "config": (best.get(a) or {}).get("config")}
                             for a in advisor.arms],
              measured={"workload_ms_before": _ms(state.get("baseline_cost")),
                        "workload_ms_after": _ms((getattr(advisor, "best_result", {})
                                                  or {}).get("all")),
                        "speedup": _speedup(state.get("baseline_cost"),
                                            (getattr(advisor, "best_result", {})
                                             or {}).get("all")),
                        "best_per_arm": best,
                        "evaluations": evals,
                        "n_evaluations": len(evals),
                        "noise_floor": _repeat_noise(evals),
                        "action_sequence": list(getattr(advisor, "action_sequence", [])),
                        "pulls": state_pulls(advisor),
                        "provenance": MEASURED,
                        "protocol": {"workload_timeout_s": args_db.get("workload_timeout"),
                                     "arm_method": args_tune.get("arm_method")}},
              constraint={"kind": "tuning_budget_s",
                          "value": float(args_tune.get("tuning_budget", 0)),
                          "observed": observed,
                          # UniTune stops when the budget is spent, so overrun is
                          # bounded by one sub-run; record it rather than assert it.
                          "violated": observed > limit * 1.10,
                          "overrun_s": round(max(0.0, observed - limit), 1)},
              policy_error=err,
              wall_clock_s=observed)

    os.makedirs(os.path.join(args.out, "episodes"), exist_ok=True)
    path = os.path.join(args.out, "episodes", f"{ep.header['episode_id']}.json")
    ep.write(path)
    findings = gate.validate(json.load(open(path)))
    fails = [f for f in findings if f.level == "fail"]
    print(f"wrote {path}")
    print(f"  events={len(ep.events)}  arms pulled="
          f"{len(getattr(advisor,'action_sequence',[]))}  "
          f"{'FAIL' if fails else 'ok'}")
    for f in findings:
        print(f"    [{f.level}:{f.check}] {f.detail}")


def _load_evaluations(path):
    """
    Every configuration UniTune actually measured, from its own history file.

    Each pull runs several real evaluations -- build the indexes or apply the knobs,
    then time the whole workload -- but the episode otherwise keeps only the best
    before and after each pull. That discards most of what was measured. These are
    <configuration, measured latency, storage cost> triples, which is the same shape
    the rest of the corpus trades in, so they are captured rather than summarised.
    """
    import ast
    out = []
    if not path or not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        kind, body = "evaluation", line
        if "|" in line[:20]:
            kind, body = line.split("|", 1)
        try:
            d = ast.literal_eval(body)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(d, dict):
            continue
        out.append({"kind": kind,
                    "arm": d.get("arm"),
                    "configuration": d.get("configuration") or d.get("config"),
                    "workload_ms": _ms(d.get("time_cost")),
                    "storage_mb": d.get("space_cost"),
                    "seconds_spent": d.get("time_spent"),
                    "provenance": MEASURED})
    return out


def _repeat_noise(evals):
    """
    The noise floor, measured rather than assumed: the spread across evaluations of
    the SAME configuration. UniTune re-measures a configuration it has already tried,
    and those repeats bound what a latency difference has to exceed before it means
    anything. Derived, so it is labelled as such and never mixed with the measurements
    it is computed from.
    """
    import statistics
    groups = {}
    for e in evals:
        if e["kind"] != "evaluation" or e["workload_ms"] is None or not e["configuration"]:
            continue
        groups.setdefault(json.dumps(e["configuration"], sort_keys=True), []).append(
            e["workload_ms"])
    spreads = [(max(v) - min(v)) / min(v) for v in groups.values() if len(v) > 1]
    if not spreads:
        return {"repeated_configurations": 0, "provenance": DERIVED,
                "note": "no configuration was measured twice; noise floor unknown"}
    return {"repeated_configurations": len(spreads),
            "max_relative_spread": round(max(spreads), 4),
            "median_relative_spread": round(statistics.median(spreads), 4),
            "provenance": DERIVED,
            "note": "a latency difference smaller than this is not distinguishable "
                    "from re-measuring the same configuration"}


def _ms(cost):
    """
    UniTune carries workload cost in seconds; the corpus records milliseconds.

    Some history records carry the cost as a one-element tuple rather than a scalar,
    so unwrap before converting and return None on anything else -- an unparseable
    cost is an absent measurement, not a zero.
    """
    if isinstance(cost, (tuple, list)):
        cost = cost[0] if cost else None
    if cost is None:
        return None
    try:
        return round(float(cost) * 1000.0, 1)
    except (TypeError, ValueError):
        return None


def _speedup(before, after):
    """
    before / after, the same definition every other episode in the corpus uses, so a
    UniTune outcome is comparable with an index-selection one. None rather than a
    fabricated 1.0 when either side is missing -- an absent measurement is not a
    null result.
    """
    if isinstance(before, (tuple, list)):
        before = before[0] if before else None
    if isinstance(after, (tuple, list)):
        after = after[0] if after else None
    if before is None or after is None:
        return None
    try:
        before, after = float(before), float(after)
    except (TypeError, ValueError):
        return None
    return round(before / after, 4) if after > 0 else None


def state_pulls(advisor):
    return int(getattr(advisor, "pull_cnt", 0))


if __name__ == "__main__":
    main()
