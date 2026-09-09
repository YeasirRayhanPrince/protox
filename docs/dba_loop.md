# The Six Moves: a DBA's tuning loop as the spine for Gen-DBA training data

This document fixes the *vocabulary* we use to collect training data for Gen-DBA's
`/optimize [tpch | job | dsb]` command. It deliberately does **not** fix a record
format. The format should fall out of what the systems we run actually emit; the
six moves are what we insist those emissions be *separable into*.

The premise: when you ask a DBA to tune a system, they do not emit an answer. They
run a loop, and the loop has legible structure. Gen-DBA has to learn the loop, not
just the answer — so the training data has to preserve the loop.

---

## 1. The six moves

### Move 1 — ORIENT
*What am I working with, and what is slow?*

Context construction. Explicit, cheap calls to the database that establish the
situation before any hypothesis exists.

| Concretely (PostgreSQL) | Emits |
|---|---|
| schema: tables, columns, types, PK/FK | the object namespace the policy may act on |
| `pg_class.reltuples`, `pg_relation_size` | table cardinalities and physical size |
| `pg_stats` — `n_distinct`, `most_common_vals`, `correlation` | column selectivity and clustering |
| `pg_stat_user_tables` — `n_ins_since_vacuum`, `last_analyze` | are the statistics even trustworthy |
| `EXPLAIN (FORMAT JSON)` per query | current plan shape, estimated cost |
| `EXPLAIN ANALYZE` (when affordable) | **estimate vs. actual rows** — the single richest orient signal |
| existing indexes, `pg_stat_user_indexes` | what is already there, and what is unused |

**Failure mode if skipped:** the model proposes indexes on columns that do not
exist, or on tables of 4 rows. Orient is what makes the action space *real*.

### Move 2 — HYPOTHESIZE
*Why is it slow?*

The interpretive step, and the one no existing baseline emits explicitly. It is the
bridge between an observation and a candidate action:

- "seq scan on `cast_info` (36.2M rows) filtered to 0.3% — missing index"
- "estimate 4 rows, actual 1.4M — correlated predicates, the planner is blind here"
- "hash join spilling — `work_mem` too small for this join"
- "join order forced by a bad selectivity estimate three levels down"

**This is the move that most distinguishes a DBA from a search algorithm.** Extend,
AutoAdmin and Relaxation never form a hypothesis — they enumerate candidates and let
the cost model rank them. Auto-Steer comes closest: probing which optimizer rule
changes a query's plan *is* an implicit hypothesis about what is wrong with it.

Where a baseline cannot emit this move, we should say so in the record rather than
fabricate it. Synthesised rationale is exactly the contradictory supervision that
degrades a training mix (cf. `cidr27_gendba.md` §3d, self-consistency).

### Move 3 — SCREEN CHEAPLY
*Which candidate fixes are worth real money?*

Screening without paying for execution. This is what makes the search tractable and
it is a first-class part of the trace, not an implementation detail.

| Concretely | Emits |
|---|---|
| `hypopg_create_index()` — hypothetical index | a candidate that costs nothing to try |
| `hypopg_relation_size()` | the price of that candidate |
| `EXPLAIN` under hypothetical indexes | estimated cost delta |
| *which* hypothetical indexes the plan actually used | **what mattered** — most candidates are ignored |
| hint sets / `enable_*` toggles | counterfactual plans without DDL |

The "which indexes were actually used" signal is the sharpest thing in this move:
it separates *proposed* from *relevant*, and it is already implemented in
`index_selection_evaluation/selection/cost_evaluation.py:39`
(`which_indexes_utilized_and_cost`).

**Screening is estimated, not measured.** Everything decided here inherits the
PostgreSQL cost model's errors. That is acceptable — provided Move 5 is not also the
cost model. See §2.

### Move 4 — DECIDE UNDER CONSTRAINT
*Given what I can afford, what do I do?*

Selection under a budget. The constraint is what makes the decision interesting;
without it, "add every index" is optimal.

- storage budget (`budget_MB`)
- write/maintenance overhead
- index width limits, count limits
- risk: a plan change that helps p50 and destroys p99 is a bad trade

Emits: the chosen action, the alternatives considered, and **why this one over
those** — benefit/size ratio, marginal cost improvement, budget exhaustion.

The rejected alternatives are not waste. They are correctly-labeled negatives with a
real cost delta attached, which is exactly the ⟨preferred, rejected⟩ shape SimPO
needs (`cidr27_gendba.md` §3, stage 3).

### Move 5 — APPLY AND MEASURE
*Did it actually work?*

Real DDL, real knobs, real execution, real wall-clock time.

```
CREATE INDEX ...;  ALTER SYSTEM SET ...;  -- then run the workload
```

**Move 5 must not be the cost model.** If screening decides *and* verifies, the loop
is self-certifying: it learns to reproduce the PostgreSQL optimizer's beliefs,
including its mistakes — the very thing Gen-DBA's QO result claims to beat. Cheap
diagnostics propose; real measurement adjudicates.

The disagreements are themselves a training signal: *when was the cost model wrong?*
is a question a good DBA has calibrated intuitions about, and it can only be learned
from traces where both numbers are recorded.

### Move 6 — KEEP OR REVERT
*Does this become part of the world?*

The accepted configuration becomes the state that Move 1 of the next iteration
observes. A rejected one is rolled back and the state is unchanged — but the
*attempt* stays in the trace.

This is what makes the data a trajectory rather than a set of independent
(problem, answer) pairs, and it is what teaches the model that optimization is
incremental and path-dependent.

---

## 2. Why separability is the whole point

The moves are useful only if a trace keeps them apart. Three consequences:

**Proposed ≠ accepted.** A greedy algorithm evaluates many candidates per iteration
and takes one. Flattened into "the decision", the alternatives are lost; recorded all
as decisions, the supervision contradicts itself. Keep the roles distinct and both
problems disappear — and the rejects become preference pairs for free.

**Estimated ≠ measured.** Move 3 is cost-model estimate; Move 5 is wall-clock. A
record that conflates them cannot express "the cost model was wrong here", which is
one of the more valuable things in the corpus.

**Absent ≠ inferred.** Where a system does not perform a move (most baselines never
do Move 2), the record should be silent, not synthesised.

---

## 3. Which system emits which move

| System | Task | 1 Orient | 2 Hypothesize | 3 Screen | 4 Decide | 5 Measure | 6 State |
|---|---|---|---|---|---|---|---|
| **index_selection_evaluation** (`extend`, `auto_admin`, `relaxation`, `drop`) | index selection | ✅ | ❌ | ✅ HypoPG | ✅ explicit, budgeted | ⚠️ optional (`actual_runtimes`) | ✅ |
| **Auto-Steer** | query optimization | ✅ per-query rule probing | ⚠️ implicit | ✅ hint sets | ✅ | ✅ | ➖ per-query |
| **Proto-X** | index + knob (RL) | ✅ `pg_stat_*` state vector | ❌ | ❌ | ❌ neural policy | ✅ | ✅ |
| **UDO** | index + knob (MCTS) | ⚠️ | ❌ | ⚠️ | ⚠️ MCTS tree | ✅ | ✅ |
| **UniTune** | multi-component | ⚠️ | ❌ | ⚠️ | ⚠️ BO acquisition | ✅ | ✅ |
| **Bao** | query optimization | — | — | — | — | — | — |

Reading of that table:

- **The white-box heuristics teach the loop.** They are the only systems whose Move 4
  states a reason. Four algorithms with genuinely different decision styles — grow
  (`extend`), enumerate (`auto_admin`), shrink-from-large (`relaxation`),
  remove-from-all (`drop`) — give reasoning diversity, not merely more rows.
- **Auto-Steer is the QO diagnostic.** Probing 12 `enable_*` rules per query answers
  "which optimizer decision matters for *this* query", which is Move 1–3 for query
  optimization rather than index selection.
- **Proto-X supplies ground truth, not reasoning.** Its policy is a network; there is
  no stated why. What it produces is the (config → plan → latency) corpus:
  `act_sql.txt`, `run.plans`, `run.raw.csv`, `run.metrics.json` per evaluated
  configuration. The heuristics say how a decision is reached; Proto-X says what
  actually pays off.
- **Bao is not runnable on this build.** `scripts/replay_bao_utils.py:46` replays logs
  from an external Bao run; real Bao needs the `pg_bao` patched PostgreSQL. (The JOB
  dump we restored was taken from a PG 12.5 that had `pg_bao` and `cuckoo` installed;
  both were filtered out during restore into vanilla PG 15.7.)

---

## 4. What this implies for the record

Not a schema — a set of invariants any record format must satisfy:

1. Every emission is attributed to exactly one move.
2. Move 3 values carry that they are **estimates**; Move 5 values carry that they are
   **measurements**. Never the same field.
3. Move 4 records proposed, accepted, and rejected as distinct roles, with the
   quantity that discriminated them.
4. Move 6 state is explicit and carried forward, so a trajectory can be replayed.
5. A move a system does not perform is **absent**, never inferred.
6. The five optimization dimensions (`cidr27_gendba.md` §2.1: task, hardware, engine,
   workload, objective) are stamped on every episode — they are what makes a record
   transferable across the landscape rather than specific to this machine.

---

## 5. Open questions

- **Move 2 has no source.** No baseline emits a hypothesis. Options: derive it
  post-hoc from Move 1 + Move 3 evidence (risks fabrication); harvest it from
  `EXPLAIN ANALYZE` estimate-vs-actual gaps (grounded but narrow); or leave it absent
  in v1 and let the model learn it implicitly from what follows. Unresolved.
- **How much Move 5 can we afford?** Real measurement is the expensive move. The
  budget split between estimated screening and measured verification sets both the
  cost and the quality of the corpus.
- **Bao:** drop, replay from existing logs, or side-build PG 12/13.
