#!/usr/bin/env python3
"""
ise_trace.py -- run an index_selection_evaluation algorithm against a live database
and record its decision procedure as a Gen-DBA training episode.

This is the harvesting harness for `/optimize <benchmark>`. It does not invent
reasoning: every field below is something the algorithm actually did. Where a move
has no source in the algorithm (notably HYPOTHESIZE), the record says so rather
than fabricating it -- see docs/dba_loop.md §5.

Moves emitted (docs/dba_loop.md):
  1 ORIENT     schema, table sizes, stats, baseline plans
  2 HYPOTHESIZE   -- absent: Extend forms no hypothesis, it enumerates
  3 SCREEN     hypopg what-if: simulate, size, cost-under, which-were-used
  4 DECIDE     proposed / accepted / rejected, with the discriminating quantity
  5 VERIFY     real CREATE INDEX + measured workload latency
  6 STATE      the configuration carried into the next iteration

Usage:
  python ise_trace.py --benchmark job --algorithm extend --budget-mb 500 \
      --queries 10 --out /mnt/protox/traces/job_extend_500.json
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
import os
import re
import sys
import time
from datetime import datetime, timezone

REPO = GENDBA_REPO
ISE = f"{REPO}/index_selection_evaluation"
sys.path.insert(0, ISE)

import psycopg2  # noqa: E402
import yaml  # noqa: E402

from selection.workload import Column, Query, Table, Workload  # noqa: E402
from selection.index import Index  # noqa: E402
from selection.cost_evaluation import CostEvaluation  # noqa: E402
from selection.dbms.postgres_dbms import PostgresDatabaseConnector  # noqa: E402
from selection.algorithms.extend_algorithm import ExtendAlgorithm  # noqa: E402
from selection.algorithms.drop_heuristic_algorithm import DropHeuristicAlgorithm  # noqa: E402
from selection.algorithms.auto_admin_algorithm import AutoAdminAlgorithm  # noqa: E402
from selection.algorithms.relaxation_algorithm import RelaxationAlgorithm  # noqa: E402


ALGORITHMS = {
    "extend": ExtendAlgorithm,
    "drop": DropHeuristicAlgorithm,
    "auto_admin": AutoAdminAlgorithm,
    "relaxation": RelaxationAlgorithm,
}

BENCHMARKS = {
    # benchmark -> (proto-x benchmark config, query dir, query order file)
    "job":  ("configs/benchmark/job_full.yaml", "queries/job_full", "queries/job_full/order.txt"),
    "tpch": ("configs/benchmark/tpch.yaml",     "queries/tpch",     "queries/tpch/order.txt"),
    "dsb":  ("configs/benchmark/dsb_s10.yaml",  "queries/dsb_10",   "queries/dsb_10/d_order.txt"),
}


# --------------------------------------------------------------------- recorder
class Trace:
    """Accumulates the episode. Every append is attributed to exactly one move."""

    def __init__(self, meta):
        self.rec = dict(meta)
        self.rec["moves"] = []
        self._t0 = time.time()

    def add(self, move, tool, args=None, obs=None, **extra):
        entry = {
            "i": len(self.rec["moves"]),
            "move": move,
            "t_ms": round((time.time() - self._t0) * 1000, 1),
        }
        if tool: entry["tool"] = tool
        if args is not None: entry["args"] = args
        if obs is not None: entry["obs"] = obs
        entry.update(extra)
        self.rec["moves"].append(entry)
        return entry

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.rec, f, indent=2, default=str)
        return path


# ------------------------------------------------------------------ move 1: orient
def orient(conn, trace, tables, queries):
    """Explicit calls that construct context, before any candidate exists."""
    cur = conn.cursor()

    cur.execute("""
        SELECT c.relname, c.reltuples::bigint, pg_relation_size(c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.reltuples DESC""")
    sizes = [{"table": r[0], "rows": r[1], "bytes": r[2]} for r in cur.fetchall()]
    trace.add("orient", "table_sizes", {}, {"tables": sizes[:10], "n_tables": len(sizes)})

    cur.execute("""
        SELECT indexrelname, idx_scan FROM pg_stat_user_indexes ORDER BY indexrelname""")
    idx = [{"index": r[0], "scans": r[1]} for r in cur.fetchall()]
    trace.add("orient", "existing_indexes", {}, {"n": len(idx), "indexes": idx})

    cur.execute("""
        SELECT tablename, attname, n_distinct, correlation FROM pg_stats
        WHERE schemaname='public' AND n_distinct IS NOT NULL
        ORDER BY abs(n_distinct) DESC LIMIT 15""")
    trace.add("orient", "column_stats", {},
              {"note": "n_distinct<0 is a ratio of table rows",
               "stats": [{"table": r[0], "column": r[1], "n_distinct": float(r[2]),
                          "correlation": float(r[3]) if r[3] is not None else None}
                         for r in cur.fetchall()]})

    # Baseline plan per query, no candidate indexes present.
    plans = []
    for q in queries:
        cur.execute("EXPLAIN (FORMAT JSON) " + q.text)
        p = cur.fetchone()[0][0]["Plan"]
        plans.append({"query": q.nr, "total_cost": p["Total Cost"],
                      "node": p["Node Type"],
                      "seq_scans": _count_node(p, "Seq Scan")})
    trace.add("orient", "explain_baseline", {"queries": [q.nr for q in queries]},
              {"plans": plans,
               "total_estimated_cost": round(sum(p["total_cost"] for p in plans), 2)})

    # Where is the planner actually wrong? Estimate-vs-actual per node.
    worst = []
    for q in queries:
        cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + q.text)
        root = cur.fetchone()[0][0]
        nodes = _worst_misestimates(root["Plan"])
        nodes.sort(key=lambda n: -n["misestimate_factor"])
        worst.append({
            "query": q.nr,
            "execution_ms": round(root.get("Execution Time", 0), 1),
            "planning_ms": round(root.get("Planning Time", 0), 2),
            "worst_node": nodes[0] if nodes else None,
            "nodes_off_by_10x_or_more": sum(1 for n in nodes if n["misestimate_factor"] >= 10),
        })
    conn.rollback()
    trace.add("orient", "explain_analyze", {"queries": [q.nr for q in queries]},
              {"per_query": worst,
               "note": "misestimate_factor is max(est,act)/min(est,act) at that node; "
                       "'under' means the planner expected fewer rows than it got",
               "queries_with_10x_misestimate": [w["query"] for w in worst
                                                if w["nodes_off_by_10x_or_more"] > 0]})
    return {"plans": plans, "misestimates": worst, "table_sizes": sizes}


def _tally(items):
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def _worst_misestimates(plan, acc=None):
    """
    Walk an EXPLAIN ANALYZE tree and collect per-node estimate-vs-actual row ratios.
    This is the richest ORIENT signal there is: it is how a DBA discovers that the
    planner is blind somewhere, and it is the only grounded basis we have for the
    HYPOTHESIZE move (docs/dba_loop.md §5).
    """
    if acc is None:
        acc = []
    est = plan.get("Plan Rows")
    act = plan.get("Actual Rows")
    loops = plan.get("Actual Loops", 1) or 1
    if est is not None and act is not None:
        act_total = act * loops
        ratio = (max(est, 1) / max(act_total, 1)) if est >= act_total else (max(act_total, 1) / max(est, 1))
        acc.append({
            "node": plan.get("Node Type"),
            "relation": plan.get("Relation Name"),
            "estimated_rows": est,
            "actual_rows": act_total,
            "misestimate_factor": round(ratio, 1),
            "direction": "over" if est > act_total else ("under" if est < act_total else "exact"),
            "actual_ms": round(plan.get("Actual Total Time", 0) * loops, 1),
        })
    for sub in plan.get("Plans", []):
        _worst_misestimates(sub, acc)
    return acc


def _starting_state(conn):
    """Which indexes already exist when the episode begins."""
    cur = conn.cursor()
    cur.execute("""
        SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY indexname""")
    names = [r[0] for r in cur.fetchall()]
    pk = [n for n in names if n.endswith("_pkey")]
    sec = [n for n in names if not n.endswith("_pkey")]
    return {"primary_keys": len(pk), "secondary_indexes": sec,
            "kind": "pk_only" if not sec else "baseline_configured"}


def _count_node(plan, node_type):
    n = 1 if plan.get("Node Type") == node_type else 0
    for sub in plan.get("Plans", []):
        n += _count_node(sub, node_type)
    return n


# ------------------------------------------------- move 3+4: instrumented Extend
class TracedExtend(ExtendAlgorithm):
    """
    Mirrors ExtendAlgorithm._calculate_best_indexes (extend_algorithm.py:38-88)
    exactly, with recording hooks added. The control flow is unchanged; only
    trace.add() calls are inserted, so the selected configuration is identical to
    what upstream would produce.
    """

    def attach_trace(self, trace):
        self.trace = trace
        self._proposals = []

    def _evaluate_combination(self, index_combination, best, current_cost,
                              old_index_size=0):
        """
        Mirrors extend_algorithm.py:120-142 exactly, but records the quantity that
        discriminated EVERY candidate -- not just the winner. Upstream returns early
        for candidates below min_cost_improvement, so those never get a ratio; the
        rejection reason names which branch the candidate fell out of.

        Reimplemented rather than wrapped so cost is computed once, not twice.
        """
        cost = self.cost_evaluation.calculate_cost(
            self.workload, index_combination, store_size=True)
        cand = index_combination[-1]
        rec = {
            "index": str(cand),
            "columns": [f"{c.table}.{c.name}" for c in cand.columns],
            "width": len(cand.columns),
            "est_size_bytes": cand.estimated_size,
            "est_cost_with": round(cost, 2),
            "est_cost_without": round(current_cost, 2),
            "cost_reduction_pct": round((1 - cost / current_cost) * 100, 4),
        }

        if (cost * self.min_cost_improvement) >= current_cost:
            rec.update(outcome="rejected",
                       reason=f"cost reduction below min_cost_improvement "
                              f"({self.min_cost_improvement})",
                       benefit_to_size_ratio=None)
            self._proposals.append(rec)
            return

        benefit = current_cost - cost
        size_diff = cand.estimated_size - old_index_size
        assert size_diff != 0, "Index size difference should not be 0!"
        ratio = benefit / size_diff
        total_size = sum(i.estimated_size for i in index_combination)
        rec.update(benefit=round(benefit, 2), size_diff_bytes=size_diff,
                   benefit_to_size_ratio=ratio,
                   combination_size_bytes=int(total_size))

        if total_size > self.budget:
            rec.update(outcome="rejected", reason="combination exceeds storage budget")
        elif ratio <= best["benefit_to_size_ratio"]:
            rec.update(outcome="rejected",
                       reason="benefit/size ratio not better than incumbent",
                       incumbent_ratio=best["benefit_to_size_ratio"],
                       margin=ratio - best["benefit_to_size_ratio"])
        else:
            rec.update(outcome="new_incumbent",
                       previous_incumbent_ratio=best["benefit_to_size_ratio"],
                       margin=ratio - best["benefit_to_size_ratio"])
            best["combination"] = index_combination
            best["benefit_to_size_ratio"] = ratio
            best["cost"] = cost
        self._proposals.append(rec)

    def _calculate_best_indexes(self, workload):
        self.workload = workload
        single = self.workload.potential_indexes()
        extension_candidates = single.copy()
        index_combination, index_combination_size = [], 0
        best = {"combination": [], "benefit_to_size_ratio": 0, "cost": None}

        current_cost = self.cost_evaluation.calculate_cost(
            self.workload, index_combination, store_size=True)
        self.initial_cost = current_cost
        self.trace.add("screen", "cost_workload", {"indexes": []},
                       {"estimated_cost": round(current_cost, 2),
                        "note": "no-index baseline, PostgreSQL cost model"})

        it = 0
        while True:
            it += 1
            self._proposals = []
            single = self._get_candidates_within_budget(index_combination_size, single)
            self.trace.add("screen", "candidates_within_budget",
                           {"budget_bytes": self.budget,
                            "used_bytes": int(index_combination_size)},
                           {"n_candidates": len(single)})

            for candidate in single:
                if candidate not in index_combination:
                    self._evaluate_combination(index_combination + [candidate],
                                               best, current_cost)
            for attribute in extension_candidates:
                self._attach_to_indexes(index_combination, attribute, best, current_cost)

            if best["benefit_to_size_ratio"] <= 0:
                self.trace.add("decide", None, None,
                               {"iteration": it, "accepted": None,
                                "stop_reason": "no candidate yields a positive "
                                               "benefit/size ratio"})
                break

            accepted = [str(i) for i in best["combination"]]
            new_index = [i for i in accepted if i not in [str(x) for x in index_combination]]

            # Near-misses, not the biggest losers: rank rejects by how close they came.
            # A reject that fell out before getting a ratio sorts last.
            rejects = [p for p in self._proposals if p["outcome"] == "rejected"]
            rejects.sort(key=lambda p: (p.get("benefit_to_size_ratio") is None,
                                        -(p.get("benefit_to_size_ratio") or 0)))
            rejected = rejects[:10]

            # MOVE 3, the "what matters" signal: which of the hypothesised indexes
            # does the planner actually pick, and what does each query now cost?
            # (cost_evaluation.py:39). This is also the per-query attribution --
            # without it the record says the workload got cheaper but not which
            # queries paid for it.
            per_query = []
            for q in self.workload.queries:
                used, qcost = self.cost_evaluation.which_indexes_utilized_and_cost(
                    q, best["combination"])
                per_query.append({"query": q.nr, "est_cost": round(qcost, 2),
                                  "indexes_used": sorted(str(i) for i in used)})
            attributed = sorted(per_query, key=lambda x: -x["est_cost"])
            self.trace.add("screen", "which_indexes_utilized",
                           {"configuration": accepted},
                           {"per_query": attributed,
                            "queries_using_any": sum(1 for p in per_query if p["indexes_used"]),
                            "queries_using_none": [p["query"] for p in per_query
                                                   if not p["indexes_used"]]})

            self.trace.add(
                "decide", None, None,
                {"iteration": it,
                 "n_proposed": len(self._proposals),
                 "accepted": new_index[0] if new_index else None,
                 "accepted_because": {
                     "benefit_to_size_ratio": best["benefit_to_size_ratio"],
                     "cost_before": round(current_cost, 2),
                     "cost_after": round(best["cost"], 2),
                     "cost_reduction_pct": round((1 - best["cost"] / current_cost) * 100, 3),
                     "cumulative_reduction_pct": round((1 - best["cost"] / self.initial_cost) * 100, 3),
                 },
                 "rejected_sample": rejected,
                 "rejection_reasons": _tally(p["reason"] for p in self._proposals
                                             if p["outcome"] == "rejected"),
                 "attribution": {
                     "queries_helped_most": [
                         {"query": p["query"], "est_cost": p["est_cost"],
                          "indexes_used": p["indexes_used"]}
                         for p in attributed[:5]],
                     "queries_using_none": [p["query"] for p in per_query
                                            if not p["indexes_used"]]},
                 "constraint": {"budget_bytes": self.budget,
                                "min_cost_improvement": self.min_cost_improvement}})

            index_combination = best["combination"]
            index_combination_size = sum(i.estimated_size for i in index_combination)
            self.trace.add("state", None, None,
                           {"iteration": it,
                            "indexes": [str(i) for i in index_combination],
                            "size_bytes": int(index_combination_size),
                            "budget_used_pct": round(100 * index_combination_size / self.budget, 2),
                            "estimated_cost": round(best["cost"], 2)})

            best["benefit_to_size_ratio"] = 0
            current_cost = best["cost"]

        return index_combination


# ---------------------------------------------------------------- move 5: verify
def verify(conn, trace, queries, indexes, baseline_ms):
    """
    Real DDL + real execution. This is deliberately NOT the cost model: if screening
    both decides and verifies, the loop only learns to reproduce PostgreSQL's
    estimates, including their errors (docs/dba_loop.md, Move 5).
    """
    cur = conn.cursor()
    created = []
    t0 = time.time()
    for idx in indexes:
        cols = ",".join(c.name for c in idx.columns)
        name = f"gendba_{idx.table()}_{'_'.join(c.name for c in idx.columns)}"[:63]
        cur.execute(f"CREATE INDEX {name} ON {idx.table()} ({cols})")
        created.append({"name": name, "table": str(idx.table()), "columns": cols})
    conn.commit()
    build_s = round(time.time() - t0, 2)
    trace.add("verify", "create_index", {"n": len(created)},
              {"created": created, "build_seconds": build_s})

    after_ms, plans_changed = _measure(cur, queries)
    for name in [c["name"] for c in created]:
        cur.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()

    total_before = round(sum(baseline_ms.values()), 1)
    total_after = round(sum(after_ms.values()), 1)
    trace.add("verify", "measure_workload", {"mode": "actual_execution"},
              {"per_query_ms_before": baseline_ms,
               "per_query_ms_after": after_ms,
               "workload_ms_before": total_before,
               "workload_ms_after": total_after,
               "speedup": round(total_before / total_after, 3) if total_after else None,
               "queries_using_new_index": plans_changed})
    return total_before, total_after, plans_changed


def _measure(cur, queries, repeat=2):
    """Median-of-repeat execution time per query, in ms."""
    out = {}
    for q in queries:
        runs = []
        for _ in range(repeat):
            t = time.time()
            cur.execute(q.text)
            cur.fetchall()
            runs.append((time.time() - t) * 1000)
        out[q.nr] = round(sorted(runs)[len(runs) // 2], 1)
    used = []
    for q in queries:
        cur.execute("EXPLAIN (FORMAT JSON) " + q.text)
        if "gendba_" in json.dumps(cur.fetchone()[0]):
            used.append(q.nr)
    return out, used


# ----------------------------------------------------------------------- driver
def build_workload(conn, benchmark, limit):
    """
    Indexable columns come from Proto-X's curated attribute list rather than
    WorkloadParser's naive substring match. Two reasons: JOB has a table called
    `name` and columns called `name`/`id`/`info`, so substring matching produces a
    badly inflated candidate set; and using the same column space as Proto-X keeps
    the two systems' traces comparable.
    """
    cfg_path, qdir, qorder = BENCHMARKS[benchmark]
    attrs = yaml.safe_load(open(f"{REPO}/{cfg_path}"))["mythril"]["attributes"]

    tables, cols_by_table = {}, {}
    for tname, cols in attrs.items():
        if isinstance(cols, str):        # the dsb web_returns YAML typo; see docs
            continue
        t = Table(tname)
        t.add_columns([Column(c) for c in cols])
        tables[tname] = t
        cols_by_table[tname] = {c.name: c for c in t.columns}

    order = [l.strip().split(",") for l in open(f"{REPO}/{qorder}") if l.strip()]
    queries = []
    for qid, fname in order[:limit]:
        text = open(f"{REPO}/{qdir}/{fname}").read().strip().rstrip(";")
        refs = []
        for tname, t in tables.items():
            if not re.search(rf"\b{re.escape(tname)}\b", text, re.I):
                continue
            for cname, col in cols_by_table[tname].items():
                if re.search(rf"\b{re.escape(cname)}\b", text, re.I):
                    refs.append(col)
        queries.append(Query(qid, text, refs))
    return Workload(queries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="job", choices=list(BENCHMARKS))
    ap.add_argument("--algorithm", default="extend", choices=list(ALGORITHMS))
    ap.add_argument("--budget-mb", type=float, default=500)
    ap.add_argument("--max-index-width", type=int, default=2)
    ap.add_argument("--queries", type=int, default=10)
    ap.add_argument("--db", default="benchbase")
    ap.add_argument("--port", type=int, default=5492)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conn = psycopg2.connect(f"host=localhost port={args.port} dbname={args.db}")
    conn.autocommit = False
    # Fail loudly instead of blocking forever if anything else holds a table lock.
    with conn.cursor() as c:
        c.execute("SET lock_timeout = '120s'")
    conn.commit()

    workload = build_workload(conn, args.benchmark, args.queries)

    trace = Trace({
        "episode_id": f"{args.benchmark}-{args.algorithm}-b{int(args.budget_mb)}",
        "command": f"/optimize {args.benchmark}",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        # the five optimization dimensions (cidr27_gendba.md §2.1)
        "profiles": {
            "task": "index_selection",
            "engine": "postgresql-15.7",
            "hardware": "intel-skylake-x-64c-188gb-nvme",
            "workload": f"{args.benchmark}:{len(workload.queries)}q",
            "objective": "workload_latency",
        },
        "policy": {
            "source": f"index_selection_evaluation/{args.algorithm}",
            "kind": "white-box heuristic",
            "constraints": {"budget_MB": args.budget_mb,
                            "max_index_width": args.max_index_width},
        },
        "search_signal": "postgresql cost model via hypopg (estimated)",
        "verify_signal": "measured wall-clock execution",
        # The ISE algorithms select an index set FROM SCRATCH -- their cost
        # evaluation never reads existing indexes. Run against a snapshot that
        # already carries baseline indexes and they re-propose what is already
        # there. Proto-X, by contrast, starts from the paper's baseline
        # configuration. Both are valid but they are different questions, so the
        # starting state is stamped here; without it the two systems' traces look
        # contradictory to a model trained on both.
        "starting_state": _starting_state(conn),
    })

    # ---- move 1
    obs = orient(conn, trace, None, workload.queries)

    # ---- move 2
    # The ALGORITHM still forms no hypothesis -- that fact is recorded verbatim.
    # What we can honestly add are observations DERIVED from Move 1 measurements:
    # a seq scan on a large table, or a node where the planner's row estimate was
    # off by >=10x. These are grounded in EXPLAIN ANALYZE, not invented, and they
    # are labelled by provenance so the distinction survives into training.
    big = {t["table"]: t["rows"] for t in obs["table_sizes"]}
    findings = []
    for w in obs["misestimates"]:
        n = w["worst_node"]
        if n and n["misestimate_factor"] >= 10:
            findings.append({
                "query": w["query"],
                "observation": (f"planner estimated {n['estimated_rows']} rows at "
                                f"{n['node']}"
                                + (f" on {n['relation']}" if n["relation"] else "")
                                + f", actual {n['actual_rows']} "
                                  f"({n['misestimate_factor']}x {n['direction']})"),
                "node": n["node"], "relation": n["relation"],
                "misestimate_factor": n["misestimate_factor"],
                "direction": n["direction"],
                "node_ms": n["actual_ms"],
                "relation_rows": big.get(n["relation"]),
            })
    findings.sort(key=lambda f: -f["misestimate_factor"])
    trace.add("hypothesize", None, None,
              {"emitted_by_policy": False,
               "policy_note": f"index_selection_evaluation/{args.algorithm} enumerates "
                              "candidates and ranks them by cost-model delta; it forms "
                              "no explicit hypothesis (docs/dba_loop.md §5).",
               "derived_from_measurement": True,
               "provenance": "EXPLAIN ANALYZE estimate-vs-actual, Move 1",
               "n_findings": len(findings),
               "findings": findings[:10]})

    baseline_ms = {}
    if not args.no_verify:
        cur = conn.cursor()
        baseline_ms, _ = _measure(cur, workload.queries)
        trace.add("orient", "measure_baseline", {"mode": "actual_execution"},
                  {"per_query_ms": baseline_ms,
                   "workload_ms": round(sum(baseline_ms.values()), 1)})

    # ---- moves 3 + 4
    ise_conn = PostgresDatabaseConnector(args.db)
    ise_conn.db_name = args.db
    algo_cls = ALGORITHMS[args.algorithm]
    params = {"budget_MB": args.budget_mb, "max_index_width": args.max_index_width}
    if args.algorithm == "extend":
        algo = TracedExtend(ise_conn, params)
        algo.attach_trace(trace)
    else:
        algo = algo_cls(ise_conn, params)

    t0 = time.time()
    indexes = algo.calculate_best_indexes(workload)
    search_s = round(time.time() - t0, 2)

    ce = algo.cost_evaluation
    trace.add("screen", "search_summary", {},
              {"seconds": search_s,
               "cost_requests": ce.cost_requests,
               "cache_hits": ce.cache_hits,
               "simulated_indexes": ise_conn.simulated_indexes})

    final = [{"index": str(i), "table": str(i.table()),
              "columns": [c.name for c in i.columns],
              "est_size_bytes": i.estimated_size} for i in indexes]
    trace.rec["output"] = {
        "indexes": final,
        "n_indexes": len(final),
        "total_size_mb": round(sum((i.estimated_size or 0) for i in indexes) / 1024 / 1024, 1),
        "search_seconds": search_s,
    }

    # ISE's connector runs with autocommit=False and leaves an open transaction
    # holding locks from hypopg_drop_index. Verify issues CREATE/DROP INDEX, which
    # need ACCESS EXCLUSIVE and would block on it forever. Release it before Move 5.
    ise_conn.commit()
    ise_conn.close()

    # ---- move 5
    if not args.no_verify and indexes:
        before, after, used = verify(conn, trace, workload.queries, indexes, baseline_ms)
        trace.rec["output"]["measured"] = {
            "workload_ms_before": before, "workload_ms_after": after,
            "speedup": round(before / after, 3) if after else None,
            "queries_using_new_index": used,
        }

    p = trace.write(args.out)
    print(f"wrote {p}")
    print(f"  moves={len(trace.rec['moves'])} indexes={len(final)} search={search_s}s")
    if "measured" in trace.rec["output"]:
        m = trace.rec["output"]["measured"]
        print(f"  measured {m['workload_ms_before']}ms -> {m['workload_ms_after']}ms "
              f"({m['speedup']}x)")


if __name__ == "__main__":
    main()
