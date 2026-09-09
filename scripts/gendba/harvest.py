#!/usr/bin/env python3
"""
harvest.py -- the ISE harvest driver.

Runs index_selection_evaluation algorithms across the task distribution and writes
one validated training record per episode.

Two things this adds over rollout.py:

  1. THE SEARCH IS RECORDED, not just its answer. A generic wrapper on
     CostEvaluation.calculate_cost captures every configuration the algorithm
     evaluated and what the cost model said about it -- which works for every
     algorithm, not just the one whose internals we instrumented. Extend gets
     additional per-iteration decision events (proposed / accepted / rejected with
     the discriminating margin).

  2. TOP-K ADJUDICATION. Most rejections are the cost model's opinion, and we have
     measured that model understating benefit by ~2x. So for the k rejected
     candidates that came closest to being accepted, we swap each into the final
     configuration in place of its accepted counterpart and MEASURE the result.
     That turns k estimated-negatives per episode into measured ones.

Every record is gated by validate.py before it lands; failures are quarantined with
their reasons, never dropped and never admitted.
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
import random
import re
import sys
import time
import traceback

sys.path.insert(0, GENDBA_REPO + "/scripts/gendba")
sys.path.insert(0, GENDBA_REPO + "/index_selection_evaluation")

from env import IndexTuningEnv, Task, ToolError  # noqa: E402
from record import ESTIMATED, MEASURED, DERIVED  # noqa: E402
import validate as gate  # noqa: E402

from selection.workload import Column, Query, Table, Workload  # noqa: E402
from selection.index import Index  # noqa: E402
from selection.dbms.postgres_dbms import PostgresDatabaseConnector  # noqa: E402
from selection.algorithms.extend_algorithm import ExtendAlgorithm  # noqa: E402
from selection.algorithms.auto_admin_algorithm import AutoAdminAlgorithm  # noqa: E402
from selection.algorithms.relaxation_algorithm import RelaxationAlgorithm  # noqa: E402
from selection.algorithms.drop_heuristic_algorithm import DropHeuristicAlgorithm  # noqa: E402
from selection.algorithms.anytime_algorithm import AnytimeAlgorithm  # noqa: E402
from selection.algorithms.db2advis_algorithm import DB2AdvisAlgorithm  # noqa: E402
# Deliberately NOT included:
#   dexter        -- an adapter that shells out to the Ruby `dexter` tool, not installed
#   cophy_input   -- returns [] ; it emits MIP solver input files, not a configuration,
#                    so there is nothing to apply or measure

# Not every algorithm is constrained the same way. extend/relaxation take a storage
# budget; auto_admin/drop take a COUNT of indexes and ignore budget entirely. Sweeping
# budget for the latter two would produce identical searches at every budget -- near-

# duplicate records, which is exactly the pollution the grouping-key rule warns about.
# So the sweep axis is mapped to whatever constraint the algorithm actually honours.
BUDGET_TO_MAX_INDEXES = {50: 2, 100: 3, 250: 5, 500: 8, 1000: 10, 2500: 13}


def _max_indexes_for(t):
    return BUDGET_TO_MAX_INDEXES.get(int(t.budget_mb),
                                     max(2, min(20, int(t.budget_mb // 100) + 2)))


ALGORITHMS = {
    "extend": (ExtendAlgorithm, lambda t: {"budget_MB": t.budget_mb,
                                           "max_index_width": t.max_index_width},
               "budget_MB"),
    "relaxation": (RelaxationAlgorithm, lambda t: {"budget_MB": t.budget_mb,
                                                   "max_index_width": t.max_index_width},
                   "budget_MB"),
    "auto_admin": (AutoAdminAlgorithm, lambda t: {"max_indexes": _max_indexes_for(t),
                                                  "max_indexes_naive": 1,
                                                  "max_index_width": t.max_index_width},
                   "max_indexes"),
    "drop": (DropHeuristicAlgorithm, lambda t: {"max_indexes": _max_indexes_for(t)},
             "max_indexes"),
    # anytime carries a RUNTIME budget alongside storage -- the only algorithm here
    # constrained by time, which is a task dimension the corpus otherwise lacks.
    "anytime": (AnytimeAlgorithm, lambda t: {"budget_MB": t.budget_mb,
                                             "max_index_width": t.max_index_width,
                                             "max_runtime_minutes": _runtime_for(t)},
                "budget_MB"),
    "db2advis": (DB2AdvisAlgorithm, lambda t: {"budget_MB": t.budget_mb,
                                               "max_index_width": t.max_index_width,
                                               "try_variations_seconds": 10},
                 "budget_MB"),
}


def _runtime_for(t):
    """Scale anytime's search budget with the storage budget it is exploring."""
    return {50: 1, 100: 2, 250: 3, 500: 5, 1000: 8, 2500: 10}.get(int(t.budget_mb), 5)


def patch_ise_prepare_query(conn):
    """
    Work around an upstream bug in index_selection_evaluation.

    DatabaseConnector._prepare_query (database_connector.py:44) picks the statement to
    EXPLAIN by substring-matching the query text, and its `elif "set" in
    query_statement.lower()` branch is tested BEFORE the `select` branch. Any query
    containing "set" inside a word therefore has its SELECT executed as a side-effect
    statement and the method returns None, producing `explain (format json) None`.

    Five of DSB's 67 query shapes trip it, all on TPC-DS columns whose names contain
    the substring: ca_gmt_offset, web_gmt_offset, w_gmt_offset.

    Patched on the connector instance rather than in the submodule, so the checkout
    stays clean and the fix travels with this harness.
    """
    import re as _re

    def _prepare(query):
        stmts = [x for x in query.text.split(";") if x.strip()]
        for st in stmts:                       # run setup first (e.g. create view)
            # "create OR REPLACE view" -- TPC-H Q15 uses that form, and matching only
            # "create view" meant the view was never created, so every cost evaluation
            # on Q15 raised UndefinedTable and the whole search aborted.
            if _re.search(r"\bcreate\s+(or\s+replace\s+)?(temp\w*\s+)?view\b", st, _re.I):
                try:
                    conn.exec_only(st)
                except Exception:
                    pass
        for st in stmts:                       # then the statement to be explained
            if _re.match(r"^\s*(select|with)\b", st, _re.I):
                return st
            if _re.match(r"^\s*(insert|update|delete)\b", st, _re.I):
                return st
        return stmts[-1] if stmts else query.text

    conn._prepare_query = _prepare
    return conn


def spec_of(idx) -> dict:
    return {"table": str(idx.table()), "columns": [c.name for c in idx.columns]}


def build_ise_workload(env) -> Workload:
    """
    Indexable columns come from the benchmark config (the same list the shipped
    embedder was trained against), not from WorkloadParser's substring match -- JOB
    has a table called `name` and columns called `name`/`id`/`info`, which would
    inflate the candidate set badly.
    """
    tables, queries = {}, []
    for t, cols in env._attrs.items():
        tab = Table(t)
        tab.add_columns([Column(c) for c in cols])
        tables[t] = tab
    for q in env.queries:
        refs = []
        for tname, tab in tables.items():
            if not re.search(rf"\b{re.escape(tname)}\b", q["text"], re.I):
                continue
            for col in tab.columns:
                if re.search(rf"\b{re.escape(col.name)}\b", q["text"], re.I):
                    refs.append(col)
        queries.append(Query(q["id"], q["text"], refs))
    return Workload(queries)


def instrument_cost_evaluation(algo, env):
    """
    Record every configuration the search evaluated. Generic: works for any ISE
    algorithm because they all go through CostEvaluation.calculate_cost.
    """
    ce = algo.cost_evaluation
    orig = ce.calculate_cost
    log = []

    def traced(workload, indexes, store_size=False):
        t0 = time.time()
        cost = orig(workload, indexes, store_size=store_size)
        log.append({"i": len(log),
                    "configuration": [spec_of(i) for i in indexes],
                    "n_indexes": len(list(indexes)),
                    "estimated_cost": round(cost, 2),
                    "seconds": round(time.time() - t0, 5)})
        return cost

    ce.calculate_cost = traced
    return log


class TracedExtend(ExtendAlgorithm):
    """
    Mirrors ExtendAlgorithm._calculate_best_indexes / _evaluate_combination
    (extend_algorithm.py:38-142) with recording hooks. Control flow is unchanged, so
    the selected configuration is what upstream would produce; cost is computed once,
    not twice.
    """

    def attach(self, episode, task):
        self.ep = episode
        self._task = task
        self._proposals = []
        self.decision_log = []          # for top-k adjudication

    def _evaluate_combination(self, index_combination, best, current_cost, old_index_size=0):
        cost = self.cost_evaluation.calculate_cost(self.workload, index_combination,
                                                   store_size=True)
        cand = index_combination[-1]
        rec = {"index": str(cand), "spec": spec_of(cand),
               "width": len(cand.columns),
               "est_size_bytes": cand.estimated_size,
               "est_cost_with": round(cost, 2),
               "est_cost_without": round(current_cost, 2),
               "cost_reduction_pct": round((1 - cost / current_cost) * 100, 4)}

        if (cost * self.min_cost_improvement) >= current_cost:
            rec.update(outcome="rejected", benefit_to_size_ratio=None, margin=None,
                       reason=f"cost reduction below min_cost_improvement "
                              f"({self.min_cost_improvement})")
            self._proposals.append(rec)
            return

        benefit = current_cost - cost
        size_diff = cand.estimated_size - old_index_size
        assert size_diff != 0, "Index size difference should not be 0!"
        ratio = benefit / size_diff
        total = sum(i.estimated_size for i in index_combination)
        rec.update(benefit=round(benefit, 2), size_diff_bytes=size_diff,
                   benefit_to_size_ratio=ratio, combination_size_bytes=int(total))

        if total > self.budget:
            rec.update(outcome="rejected", margin=None,
                       reason="combination exceeds storage budget")
        elif ratio <= best["benefit_to_size_ratio"]:
            rec.update(outcome="rejected",
                       reason="benefit/size ratio not better than incumbent",
                       incumbent_ratio=best["benefit_to_size_ratio"],
                       margin=ratio - best["benefit_to_size_ratio"],
                       margin_provenance=ESTIMATED)
        else:
            rec.update(outcome="new_incumbent",
                       previous_incumbent_ratio=best["benefit_to_size_ratio"],
                       margin=ratio - best["benefit_to_size_ratio"],
                       margin_provenance=ESTIMATED)
            best["combination"] = index_combination
            best["benefit_to_size_ratio"] = ratio
            best["cost"] = cost
        self._proposals.append(rec)

    def _calculate_best_indexes(self, workload):
        self.workload = workload
        single = self.workload.potential_indexes()
        ext_candidates = single.copy()
        combination, size = [], 0
        best = {"combination": [], "benefit_to_size_ratio": 0, "cost": None}

        current_cost = self.cost_evaluation.calculate_cost(self.workload, combination,
                                                           store_size=True)
        self.initial_cost = current_cost
        self.ep.add("screen", "note", payload={"no_index_estimated_cost": round(current_cost, 2)},
                    provenance=ESTIMATED, produced_by="postgresql-cost-model")

        it = 0
        while True:
            it += 1
            self._proposals = []
            single = self._get_candidates_within_budget(size, single)
            for cand in single:
                if cand not in combination:
                    self._evaluate_combination(combination + [cand], best, current_cost)
            for attr in ext_candidates:
                self._attach_to_indexes(combination, attr, best, current_cost)

            if best["benefit_to_size_ratio"] <= 0:
                self.ep.decision(iteration=it, n_proposed=len(self._proposals),
                                 accepted=None,
                                 stop_reason="no candidate yields a positive "
                                             "benefit/size ratio",
                                 proposed=self._proposals)
                break

            state_before = [spec_of(i) for i in combination]
            accepted_specs = [spec_of(i) for i in best["combination"]]
            new = [s for s in accepted_specs if s not in state_before]
            rejects = [p for p in self._proposals if p["outcome"] == "rejected"]
            rejects.sort(key=lambda p: (p.get("margin") is None, -(p.get("margin") or -1e9)))

            accepted = {"spec": new[0] if new else None,
                        "discriminant": {
                            "benefit_to_size_ratio": best["benefit_to_size_ratio"],
                            "est_cost_before": round(current_cost, 2),
                            "est_cost_after": round(best["cost"], 2),
                            "cost_reduction_pct": round((1 - best["cost"] / current_cost) * 100, 4),
                            "cumulative_reduction_pct": round(
                                (1 - best["cost"] / self.initial_cost) * 100, 4)},
                        "provenance": ESTIMATED}
            self.ep.decision(iteration=it, n_proposed=len(self._proposals),
                             state_before=state_before,
                             accepted=accepted,
                             rejected=rejects[:20],
                             rejection_reasons=_tally(p["reason"] for p in rejects),
                             constraint={"budget_bytes": self.budget,
                                         "min_cost_improvement": self.min_cost_improvement},
                             proposed=self._proposals)
            self.decision_log.append({"iteration": it, "accepted": accepted["spec"],
                                      "rejected": rejects[:20]})

            combination = best["combination"]
            size = sum(i.estimated_size for i in combination)
            self.ep.add("state", "state",
                        payload={"iteration": it,
                                 "indexes": [spec_of(i) for i in combination],
                                 "size_bytes": int(size),
                                 "budget_used_pct": round(100 * size / self.budget, 2),
                                 "estimated_cost": round(best["cost"], 2)},
                        provenance=ESTIMATED, produced_by="policy")
            best["benefit_to_size_ratio"] = 0
            current_cost = best["cost"]
        return combination


def _tally(items):
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def adjudicate(env, decision_log, final_specs, k):
    """
    Measure the k rejected candidates that came closest to being accepted.

    Definition: take the final configuration, swap the rejected candidate in for the
    accepted index from the same iteration, and measure. Compared against the final
    configuration's own measured latency, this says whether the cost model's
    rejection was right -- in wall clock, not in estimate.

    Cost is k measurements (~15 s each), which is why this is top-k per EPISODE
    rather than per iteration.
    """
    cands = []
    for d in decision_log:
        for r in d["rejected"]:
            if r.get("margin") is None or not d["accepted"]:
                continue
            cands.append({"iteration": d["iteration"], "accepted": d["accepted"],
                          "rejected": r["spec"], "margin": r["margin"],
                          "reason": r["reason"],
                          "est_cost_with": r.get("est_cost_with")})
    cands.sort(key=lambda c: -c["margin"])          # closest to acceptance first
    picked, seen = [], set()
    for c in cands:
        key = (c["rejected"]["table"], tuple(c["rejected"]["columns"]))
        if key in seen or c["rejected"] in final_specs:
            continue
        seen.add(key)
        picked.append(c)
        if len(picked) >= k:
            break

    results = []
    for c in picked:
        acc, rej = c["accepted"], c["rejected"]
        applied_names = {(a["spec"]["table"], tuple(a["spec"]["columns"])): a["name"]
                         for a in env._applied}
        acc_name = applied_names.get((acc["table"], tuple(acc["columns"])))
        try:
            if acc_name:
                env.call("REALIZE", {"action": "drop_index", "name": acc_name})
            r = env.call("REALIZE", {"action": "create_index", **rej})
            if not r["ok"]:
                raise ToolError(r["error"])
            per_q, protocol = env._measure(env.queries)
            swapped_ms = round(sum(per_q.values()), 1)
            results.append({"iteration": c["iteration"], "swapped_out": acc,
                            "swapped_in": rej,
                            "estimated_margin": c["margin"],
                            "estimated_margin_provenance": ESTIMATED,
                            "measured_workload_ms": swapped_ms,
                            "per_query_ms": per_q,
                            "provenance": MEASURED,
                            "protocol": protocol})
            env.call("REALIZE", {"action": "drop_index", "name": r["result"]["created"]})
            if acc_name:
                env.call("REALIZE", {"action": "create_index", **acc})
        except Exception as e:                      # a failed adjudication is data
            results.append({"iteration": c["iteration"], "swapped_out": acc,
                            "swapped_in": rej, "outcome": "error",
                            "detail": str(e)[:200], "provenance": MEASURED})
    return results


def already_collected(out_dir, quarantine_dir, task, algo_name, initial_kind):
    """
    Has this exact (benchmark, policy, budget, width, starting-state) already been
    harvested? The CloudLab node is temporary and this campaign continues on the next
    allocation, so a restart must skip completed work rather than redo 150+ episodes.

    Matching is on the recorded header, not on the filename, because episode ids carry
    a random suffix. Quarantined records count as collected: they exist and can be
    re-gated, so recollecting them would just duplicate.
    """
    import glob as _glob
    want = (task.benchmark, algo_name, float(task.budget_mb),
            int(task.max_index_width), initial_kind)
    for d in (out_dir, quarantine_dir):
        for f in _glob.glob(os.path.join(d, f"{task.benchmark}-*.json")):
            if f.endswith(".failures.json"):
                continue
            try:
                with open(f) as fh:
                    r = json.load(fh)
            except Exception:
                continue                      # unreadable -- treat as not collected
            t, p = r.get("task", {}), r.get("policy", {})
            got = (t.get("benchmark"), p.get("name"), float(t.get("budget_mb", -1)),
                   int(t.get("max_index_width", -1)),
                   (r.get("initial_state") or {}).get("kind"))
            if got == want:
                return os.path.basename(f)
    return None


def apply_constraint(task, algo_name):
    """Point the task's evaluated constraint at whatever the algorithm honours."""
    _, params_fn, kind = ALGORITHMS[algo_name]
    task.constraint_kind = kind
    task.constraint_value = (task.budget_mb if kind == "budget_MB"
                             else params_fn(task)["max_indexes"])
    return task


def run_episode(task, algo_name, port, out_dir, quarantine_dir, adjudicate_k,
                restore=False, query_timeout_s=300.0):
    task = apply_constraint(task, algo_name)
    AlgoCls, params_fn, constraint_kind = ALGORITHMS[algo_name]
    policy_meta = {"name": algo_name, "kind": "white-box heuristic",
                   "source": "index_selection_evaluation",
                   "constraint_honoured": constraint_kind,
                   "params": params_fn(task)}
    env = IndexTuningEnv(task, port=port, policy_meta=policy_meta,
                         query_timeout_s=query_timeout_s)
    env.reset(restore_snapshot=restore)
    ep = env.episode
    base = env.baseline()

    # ORIENT: per-query EXPLAIN ANALYZE. This is the diagnostic a DBA leads with, and
    # its payload carries per-node estimated-vs-actual rows -- i.e. cardinality
    # estimation training data, free from an index-selection harvest. Without this
    # call project_cardinality() finds nothing, which is exactly what it reported.
    for q in env.queries:
        env.call("PROBE", {"what": "explain_analyze", "query": q["id"]})

    workload = build_ise_workload(env)
    conn = patch_ise_prepare_query(PostgresDatabaseConnector(env.dbname))
    params = params_fn(task)
    if algo_name == "extend":
        algo = TracedExtend(conn, params)
        algo.attach(ep, task)
    else:
        algo = AlgoCls(conn, params)
    search_log = instrument_cost_evaluation(algo, env)

    err = None
    t0 = time.time()
    try:
        indexes = algo.calculate_best_indexes(workload)
    except Exception as e:
        indexes, err = [], f"{type(e).__name__}: {e}"
        traceback.print_exc()
    search_s = round(time.time() - t0, 2)
    conn.commit(); conn.close()

    ep.add("screen", "note",
           payload={"search_seconds": search_s,
                    "configurations_evaluated": len(search_log),
                    "cost_requests": algo.cost_evaluation.cost_requests,
                    "cache_hits": algo.cost_evaluation.cache_hits,
                    "evaluations": search_log,
                    "policy_error": err},
           provenance=ESTIMATED, produced_by="postgresql-cost-model")

    # The algorithms never read existing indexes, so this is recorded explicitly.
    ep.absent("hypothesize",
              f"index_selection_evaluation/{algo_name} enumerates candidates and ranks "
              "them by cost-model delta; it forms no explicit hypothesis",
              produced_by=algo_name)

    for idx in indexes:
        env.call("REALIZE", {"action": "create_index", **spec_of(idx)})
    final_specs = [a["spec"] for a in env._applied]

    adj = []
    if adjudicate_k and algo_name == "extend" and getattr(algo, "decision_log", None):
        adj = adjudicate(env, algo.decision_log, final_specs, adjudicate_k)
        ep.add("verify", "decision",
               payload={"kind": "top_k_adjudication", "k": adjudicate_k,
                        "note": "rejected candidates measured by swapping them into the "
                                "final configuration in place of their accepted "
                                "counterpart; compare against terminal.measured",
                        "results": adj},
               provenance=MEASURED, produced_by="postgresql-executor")

    score = env.score()
    path = os.path.join(out_dir, f"{ep.header['episode_id']}.json")
    env.dump(path, extra={"search_seconds": search_s, "policy_error": err,
                          "adjudicated_count": len(adj)})
    env.conn.close()

    rec = json.load(open(path))
    findings = gate.validate(rec)
    fails = [f for f in findings if f.level == "fail"]
    status = "FAIL" if fails else ("SUSPECT" if findings else "ok")
    if fails:
        os.makedirs(quarantine_dir, exist_ok=True)
        os.replace(path, os.path.join(quarantine_dir, os.path.basename(path)))
        json.dump([f.__dict__ for f in findings],
                  open(os.path.join(quarantine_dir,
                                    os.path.basename(path) + ".failures.json"), "w"),
                  indent=2)
    return score, status, findings, len(adj)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmarks", default="job")
    ap.add_argument("--algorithms", default="extend,auto_admin,relaxation,drop")
    ap.add_argument("--budgets", default="50,100,250,500,1000,2500")
    ap.add_argument("--queries", type=int, default=25)
    ap.add_argument("--query-select", default="head", choices=["head", "one-per-shape"])
    # 30s matches what the paper shipped for TPC-H and DSB (params.json); JOB used 15s.
    ap.add_argument("--query-timeout", type=float, default=300.0)
    ap.add_argument("--initial-kind", default="pk_only",
                    help="starting state label to match when resuming (pk_only|configured)")
    ap.add_argument("--widths", default="2")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--adjudicate-k", type=int, default=5)
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--out", default=GENDBA_REPO + "/gendba_records")
    ap.add_argument("--limit", type=int, default=0, help="stop after N episodes")
    ap.add_argument("--no-resume", action="store_true",
                    help="recollect episodes even if the corpus already has them")
    args = ap.parse_args()

    out_dir = os.path.join(args.out, "episodes")
    quarantine = os.path.join(args.out, "quarantine")
    os.makedirs(out_dir, exist_ok=True)

    plan = [(b, a, float(bu), int(w), int(s))
            for b in args.benchmarks.split(",")
            for bu in args.budgets.split(",")
            for a in args.algorithms.split(",")
            for w in args.widths.split(",")
            for s in args.seeds.split(",")]
    if args.limit:
        plan = plan[:args.limit]

    print(f"harvest: {len(plan)} episodes -> {out_dir}")
    t_start = time.time()
    n_ok = n_fail = n_suspect = n_skip = 0
    for i, (bench, algo, budget, width, seed) in enumerate(plan, 1):
        task = Task(benchmark=bench, n_queries=args.queries, budget_mb=budget,
                    max_index_width=width, seed=seed, tool_budget_s=3600,
                    query_select=args.query_select)
        if not args.no_resume:
            prior = already_collected(out_dir, quarantine, task, algo, args.initial_kind)
            if prior:
                n_skip += 1
                print(f"[{i}/{len(plan)}] {bench} b={budget:6.0f} {algo:11s} "
                      f"SKIP - already collected ({prior})")
                continue
        # id keeps the sweep point distinct even when the honoured constraint differs
        task.id = (lambda t=task, a=algo: f"{t.benchmark}-q{t.n_queries}-b{int(t.budget_mb)}"
                   f"-w{t.max_index_width}-{a}-s{t.seed}")
        t0 = time.time()
        try:
            score, status, findings, n_adj = run_episode(
                task, algo, args.port, out_dir, quarantine, args.adjudicate_k,
                query_timeout_s=args.query_timeout)
        except Exception as e:
            print(f"[{i}/{len(plan)}] {task.id()} {algo:11s} EPISODE ERROR {e}")
            traceback.print_exc()
            n_fail += 1
            continue
        n_ok += status == "ok"
        n_fail += status == "FAIL"
        n_suspect += status == "SUSPECT"
        print(f"[{i}/{len(plan)}] {bench} b={budget:6.0f} {algo:11s} "
              f"{score['speedup']:6.3f}x {score['n_indexes']:2d}idx "
              f"{score['storage_used_mb']:7.1f}MB adj={n_adj} "
              f"{time.time()-t0:5.0f}s {status}")
        for f in findings:
            print(f"      [{f.level}:{f.check}] {f.detail}")

    print(f"\n{n_ok} ok, {n_suspect} suspect, {n_fail} failed/quarantined, "
          f"{n_skip} skipped (already collected) in {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
