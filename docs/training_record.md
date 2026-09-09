# The Gen-DBA training record

**Purpose of this document:** fix the *record*, not the recipe. We are collecting
training data for Gen-DBA over a long period. We do not yet know which post-training
recipes it will feed, so the record has to be a superset that any of them can be
projected out of — without re-running the collection.

Collection is expensive and the systems we harvest from (baselines, Proto-X) will be
retired or changed. Anything not captured at collection time is gone.

---

## 1. The principle

> **Capture losslessly. Project later.**

Three rules follow, and they are the whole design.

### Rule 1 — Provenance on every value

Every number says where it came from:

| provenance | meaning | example |
|---|---|---|
| `measured` | wall clock, or actually-returned rows | query latency, `Actual Rows`, real index size |
| `estimated` | a model's opinion | PostgreSQL `Total Cost`, `Plan Rows`, `hypopg_relation_size` |
| `derived` | computed from other recorded values | speedup, benefit/size ratio |
| `declared` | from configuration, not observed | storage budget, max index width |

This is not bookkeeping pedantry. We measured PostgreSQL's cost model understating
the benefit of the same index set by roughly 2× — twice:

| run | estimated | measured |
|---|---|---|
| v1 | −17.8% | −41.6% |
| v2 | −18.1% | −35.7% |

A corpus that conflates the two teaches Gen-DBA to reproduce that error. Keeping them
in separate fields lets a consumer *choose*, and makes "when is the cost model wrong?"
a learnable question rather than an invisible assumption.

### Rule 2 — Raw payloads are kept

Full `EXPLAIN` JSON, full tool responses, full SQL text. A digest is a guess about
what a future consumer needs.

The clearest illustration: the `EXPLAIN ANALYZE` payloads we collect for *index
selection* contain per-node estimated-vs-actual rows — which is **cardinality
estimation training data**. One collection run, two learning tasks. That is only
true if the raw plan is stored. (An earlier iteration of the harness digested tool
responses down to scalars; it would have thrown this away silently.)

### Rule 3 — Absent is not inferred

A move a system does not perform is recorded as absent, with a reason:

```json
{"move": "hypothesize", "kind": "note", "produced_by": "extend",
 "payload": {"emitted": false,
             "reason": "extend enumerates candidates and ranks them by cost-model
                        delta; it forms no explicit hypothesis"}}
```

Never a plausible-sounding rationale we made up. Even a small fraction of
contradictory supervision degrades a training mix disproportionately
(`cidr27_gendba.md` §3d).

---

## 2. Layout

```
header
  schema_version, episode_id, created_utc, collector, git_commit
  task         the five dimensions + constraints
  policy       who decided: name, kind, version, hyperparameters
  environment  engine version + extensions + knobs, hardware, snapshot, stats state
  workload     every query: id, full SQL, sha1
  initial_state  physical design and table sizes at t=0
events[]       ordered, lossless
terminal       final configuration and measured outcome
```

### Why the header is this heavy

A measured latency is uninterpretable without it. `shared_buffers`, the CPU, whether
statistics were fresh, and which snapshot was loaded all change the number. Two
episodes are only comparable if their environments are — and a year from now nobody
will remember what this machine was.

`initial_state` in particular: the ISE algorithms select an index set *from scratch*
and never read existing indexes, while Proto-X starts from the paper's baseline
configuration. Both are valid, but without `initial_state` stamped, their traces look
contradictory to a model trained on both.

### Events

Each event is attributed to exactly one of the six moves (`docs/dba_loop.md`) and
carries its own cost:

```json
{"i": 12, "move": "screen", "kind": "tool_call", "verb": "PROBE",
 "args": {"what": "whatif", "indexes": [{"table": "title", "columns": ["production_year"]}]},
 "payload": { ...full response... },
 "provenance": "estimated", "produced_by": "postgresql-cost-model",
 "duration_s": 0.0041, "t_offset_s": 12.83, "ok": true}
```

`duration_s` matters: a what-if evaluation is ~4 ms and a workload measurement ~18 s,
about 4000×. Recording the cost of each call is what lets a downstream recipe learn
*budgeted* diagnosis rather than assuming information is free.

`kind` is one of `tool_call`, `decision`, `state`, `note`.

Decisions keep the three roles separate:

```json
{"kind": "decision", "payload": {
   "iteration": 4,
   "proposed": [ ... every candidate considered ... ],
   "accepted": {"index": "...", "discriminant": {...}},
   "rejected": [{"index": "...", "reason": "benefit/size ratio not better than incumbent",
                 "margin": -0.00172, "margin_provenance": "estimated"}]}}
```

Flattening these loses the alternatives; recording them all as decisions is
self-contradictory. Kept apart, the rejects are correctly-labelled negatives.

---

## 3. Projections

None of these are stored. All are recomputable from the record — which is the test of
whether the record is complete. Implemented in `scripts/gendba/record.py`.

| projection | consumes | produces |
|---|---|---|
| `project_tool_sft` | `tool_call` events in order | ⟨prompt, tool-call, tool-response, …, output⟩ |
| `project_preference_pairs` | `decision` events | ⟨preferred, rejected⟩ + margin + **margin provenance** |
| `project_cardinality` | `measured` EXPLAIN payloads | ⟨query, node, filter, estimated_rows, actual_rows⟩ |
| `project_outcome` | `terminal` | measured result, for evaluation and RL reward replay |
| Base-SFT | header + terminal | ⟨prompt, final configuration⟩ |
| RL replay | header + events | environment fingerprint, seed, re-executable calls |

`project_preference_pairs` carries `margin_provenance` deliberately: most margins are
`estimated`, and a consumer that wants only measured-adjudicated pairs must be able to
filter. Silently mixing them would reintroduce the cost-model bias through the back
door.

---

## 4. What this does *not* commit us to

- No reward shaping. Reward is a recorded field, not an objective.
- No fixed prompt template. Prompts are rendered at training time from the header.
- No choice of post-training recipe.
- No filtering. Regressions and failed actions are kept — a corpus of only successes
  cannot teach what a bad decision looks like.

---

## 5. Open

- **Move 2 (hypothesize) has no source.** No baseline emits one. Currently recorded as
  absent, with grounded observations (`EXPLAIN ANALYZE` misestimates) stored separately
  and labelled by provenance. Whether a model should be trained to produce hypotheses
  from that evidence is unresolved.
- **Preference-pair adjudication.** Most rejected candidates are labelled by the cost
  model. Measuring a sample of them would give measured-adjudicated pairs; the cost is
  ~18 s each.
- **Schema evolution.** `schema_version` is `1.0`. Additive changes only; a consumer
  must tolerate unknown fields.

---

## 6. Measurement integrity

Everything above concerns what the record *contains*. This section concerns whether
the numbers in it mean anything. Each item below cost us a re-harvest.

### 6.1 Every path to the database needs a timeout

Not just the obvious one. We applied `statement_timeout` to the measurement path,
then had to add it to priming, then to `EXPLAIN ANALYZE` — one incident at a time:

| path | symptom before the fix |
|---|---|
| `_measure` | — (had it from the start) |
| `prime()` | TPC-H Q17 ran **81 minutes** unbounded; the harvest looked healthy and produced nothing |
| `_explain()` | DSB Q23 took **363.6 s** against a 30 s cap — `EXPLAIN ANALYZE` *executes* the query |

An uncapped path is worse than slow: it leaves uncapped tool costs in the record,
which corrupts the per-call `duration_s` signal we deliberately collect so a consumer
can learn budgeted diagnosis.

Timeouts follow the paper's own settings (`results/*/us/*/params.json`): **15 s** per
query for JOB, **30 s** for TPC-H and DSB.

### 6.2 A timed-out query is censored, not missing

If a query times out in the baseline and completes once indexes exist, dropping it
from one side makes `workload_ms_before` and `workload_ms_after` cover **different
query sets** — the "speedup" then compares two different workloads.

So a failed query contributes its timeout limit to the total and is listed in
`failed_queries` with `{outcome, limit_s, elapsed_ms, censored_at_ms, detail}`.
Totals containing a censored query are **lower bounds**, and the protocol says so.
The gate checks the set both ways: a query present on one side only is a failure.

This is not hypothetical — TPC-H Q17 on a PK-only base is exactly this case, because
it needs `lineitem(l_partkey)`, the index the paper's baseline creates up front.

### 6.3 Judge a policy on the constraint it was actually given

`extend` and `relaxation` honour a storage budget; `auto_admin` and `drop` honour a
count of indexes and ignore budget entirely. Sweeping budget for the latter two
produced episodes where `auto_admin` used 900 MB against a "50 MB budget", was flagged
over-budget, and scored reward 0 — for violating a constraint it never received, while
actually achieving 2.345×.

`policy.constraint_honoured` and `terminal.constraint.kind` must agree, and the gate
enforces it. The declared sweep value is still recorded as
`sweep_budget_mb_declared` so episodes stay cross-referenceable.

It also means the sweep axis must map to the constraint each algorithm honours, or the
six budget levels produce six identical searches — near-duplicate records.

### 6.4 The starting state is part of the question

The ISE algorithms select an index set **from scratch**; their cost evaluation never
reads existing indexes. Run them against a snapshot that already has indexes and they
re-propose what is there — our first JOB trace scored 1.03× for exactly this reason.

So ISE runs on `*_base.tgz` (PK-only). Proto-X starts from the paper's baseline
instead. `initial_state.kind` (`pk_only` / `configured`) is stamped on every record so
the two can never be silently mixed.

TPC-H is harvested from **both** states deliberately: `pk_only` is greenfield selection,
`configured` is the realistic case of tuning an already-tuned system — a scenario the
corpus otherwise would not contain at all.

### 6.5 Upstream bugs we work around, and where

- **`index_selection_evaluation` `_prepare_query`** (`database_connector.py:57`) picks
  the statement to EXPLAIN by substring match, testing `"set" in stmt.lower()` *before*
  the `select` branch. Any query containing "set" inside a word has its SELECT executed
  as a side-effect and the method returns `None`, producing
  `explain (format json) None`. Five of DSB's 67 query shapes trip it, on the TPC-DS
  columns `ca_gmt_offset`, `web_gmt_offset`, `w_gmt_offset`. Patched on the connector
  instance in `harvest.py`, not in the submodule.
- **Multi-statement workload entries.** TPC-H Q15 is `CREATE VIEW; SELECT; DROP VIEW`.
  Measurement must execute all three (that is what Q15's latency means) and fetch only
  where there is a result set; `EXPLAIN` must run the setup, explain the SELECT, and
  run the teardown, or the view leaks into later queries.
- **DSB `web_returns`.** The YAML list marker typo hides 24 indexable columns. They are
  recovered for the ISE harvest (`action_space.recovered_from_malformed_yaml`), because
  the exclusion is only correct for Proto-X, whose pre-trained embedder does not contain
  them. The YAML itself is left untouched.

### 6.6 Watch for stalls, not completion

A hung query keeps the driver process alive and busy; waiting on process exit cannot
tell that apart from healthy work. `scripts/gendba/monitor.sh` polls episode count,
idle time, log errors and the longest-running query in `pg_stat_activity`, and exits
with distinct codes for stalled / errored / died-early. Every harvest stage runs under
one.
