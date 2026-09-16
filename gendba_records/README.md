# gendba_records — the Gen-DBA training corpus

**If you are an agent or human seeing this directory for the first time, read this
file end to end.** It describes what every file here is, the schema of the episode
JSON, how records are produced (lineage), and the traps. The authoritative format spec
is `../docs/training_record.md`; the vocabulary (the "six moves") is `../docs/dba_loop.md`;
the project goal is `../docs/cidr27_gendba.md`. This README is the practical index.

`/proj/pmoss-PG0/` is the only filesystem that survives a CloudLab allocation, which is
why this data lives here. **The whole directory is git-ignored** (it is data, ~19 GB) —
only this README is force-tracked so the description travels with the repo.

---

## 1. What this corpus is

Training data for **Gen-DBA**, a single general-purpose LLM agent for optimizing
databases. We produce it by running existing DB-tuning systems (scripted heuristics, a
bandit meta-policy, and the Proto-X RL agent) against sandboxed databases and recording,
**losslessly and with strict provenance**, everything each system observed and decided —
so the model can learn the *loop*, not just the answer.

Four rules the data obeys (do not violate them when adding records):

* **Capture losslessly, project later.** An episode is a superset. `tool_sft`,
  `preference_pairs`, `cardinality` and `outcome` are recomputed from it, never stored.
* **Provenance is never mixed.** `estimated` / `measured` / `derived` / `declared` are
  separate fields. A derived or estimated number never sits in a measured one.
* **Absent is not inferred.** A move a system does not perform is recorded absent, with a
  reason — never synthesised (contradictory supervision poisons the mix).
* **Both directions are data.** Regressions are kept, not filtered (a policy must not
  learn "changes always help").

---

## 2. Directory layout

| path | what it is |
|---|---|
| `episodes/` | **the dataset** — one JSON per episode. Flat dir, all benchmarks/policies mixed. |
| `quarantine/` | records that FAILED the gate, each with a sibling `<id>.failures.json` giving the reason. Also two legacy subdirs (`failed_auth_5493/`, `pre_snapshot_fix/`) from earlier bugs. |
| `protox_trials/` | **raw Proto-X traces** — the Ray trial directories the `protox-*` episodes were harvested from. Kept so a parser fix can re-derive without re-running (see §5). |
| `checkpoints/` | partial UniTune runs, recoverable via `../scripts/gendba/unitune_recover.py`. |
| `logs/` | harvest run logs (provenance). |
| `final_report.txt` / `.json` | corpus summary from `../scripts/gendba/report.py`. **STALE — pre-Proto-X (says 290).** Re-run `report.py` to refresh (see §8). |
| `final_validation.txt` | last full gate pass (`../scripts/gendba/validate.py`). Also pre-Proto-X. |

### Current counts (verified 2026-09-16)
**293 episodes**, **10 quarantined**, **2 raw Proto-X trials**. The 3 newest episodes
are the first RL trajectories (`protox-*`); the other 290 are single-shot.

---

## 3. The episode JSON schema (`schema_version 1.0`)

Every episode has the same top-level shape (built by `../scripts/gendba/record.py`):

```
{
  schema_version, episode_id, created_utc, collector, git_commit,   # identity/provenance
  task, policy, environment, workload, initial_state,               # HEADER (the setup)
  events: [ ... ],                                                  # the ordered, lossless stream
  terminal: { ... },                                                # final config + measured outcome
  event_count, moves_present                                        # convenience
}
```

**Header blocks:**
* `task` — `benchmark`, `task` (index_selection | query_optimization | multi_component_tuning),
  `objective`, `budget_mb`, `max_index_width`, `constraint_kind`, `constraint_value`, `seed`.
* `policy` — `name`, `kind`, `source`, `constraint_honoured`, `params` (+ policy-specific
  fields, e.g. `arm_method` for UniTune, `trajectory`/`n_steps` for Proto-X).
* `environment` — `engine` (pg version, knobs, extensions), `hardware`, `snapshot`,
  `concurrency`, `statistics`. Without this a measured latency is uninterpretable.
* `workload` — `queries` (full SQL + `sql_sha1`), and the **`grouping_key`** (must be
  `template`) + `groups`. *Train/eval splits MUST be taken on `template`, never `id`* —
  query families (`1.sql`,`1b.sql`,…) are near-duplicates.
* `initial_state` — `indexes`, `tables`, and `kind` (`pk_only` = greenfield, `configured`
  = paper's baseline indexes already present). Every speedup is relative to this.

**`events[]`** — one entry per thing that happened, each attributed to exactly one move:
```
{ i, move, kind, t_offset_s, duration_s, verb, args, payload, provenance, produced_by, ok, error, note }
```
* `move` ∈ orient | hypothesize | screen | decide | apply | verify | state | error
  (the six DBA moves — see `../docs/dba_loop.md`).
* `kind` ∈ tool_call | decision | state | note.
* `provenance` ∈ **estimated** (cost model / hypopg) | **measured** (wall clock) |
  **derived** | **declared**. Never conflated.
* `payload` is the FULL response (e.g. complete EXPLAIN JSON with per-node
  estimated-vs-actual rows — this is what makes cardinality recoverable), not a digest.
* A move a system does not perform is a `kind:"note"` with `payload.emitted:false` and a
  reason (e.g. ISE never `hypothesize`s; Proto-X never `screen`s).

**`terminal`** — `configuration` (the chosen indexes/knobs/plan), `measured` (the outcome:
`speedup`, `workload_ms_before/after`, per-query latencies, censoring), `constraint`
(honoured vs violated), `policy_error`, `wall_clock_s`.

---

## 4. Lineage — who produced what

An episode is `⟨header, events, terminal⟩` where the events are one system's actual tuning
loop. Producers in this corpus:

| policy name(s) | task | producer script | notes |
|---|---|---|---|
| `extend`, `auto_admin`, `relaxation`, `drop`, `anytime`, `db2advis` | index_selection | `harvest.py` (via `env.py`, driving `index_selection_evaluation`) | 6 white-box heuristics × job/tpch/dsb/tpcc; do orient+screen(HypoPG)+decide, no hypothesize |
| `self_driven_hintset` | query_optimization | `qo_harvest.py` | 23 job episodes; per-query optimizer-rule plans |
| `unitune_topadvisor` | multi_component_tuning | `unitune_harvest.py` | 2 job episodes; a bandit meta-policy choosing arms (knob/index) |
| `protox_wolp` | multi_component_tuning **(trajectory)** | `protox_harvest.py` | 3 episodes (2 job, 1 tpch); the RL agent — see §5 |

`report.py` breaks the 290 single-shot records down by benchmark × policy; run it for the
current table.

---

## 5. Proto-X episodes — the trajectory records (read this before using them)

The `protox-*` episodes are different in kind from the rest and are documented fully in
`../docs/training_record.md §7`. Key facts:

* **One Ray trial → one episode → N steps.** An RL trajectory is N decisions in ONE
  episode, not N episodes (splitting would destroy the step-to-step conditioning, which is
  the whole point). A 30 h run is one episode with hundreds of steps.
* Per step the events run **ORIENT → [hypothesize absent] → [screen absent] → DECIDE →
  APPLY → MEASURE → KEEP/REVERT**. `hypothesize`/`screen` are absent (Proto-X emits a
  neural-policy action and measures everything for real — no what-if).
* A trial contains several **RL episodes** (horizon-length, reset between); these are
  recorded as `state` boundary events *inside* the one Gen-DBA episode (`n_rl_episodes`),
  NOT as separate episodes.
* **They are large.** The 921-step job episode is **2.4 GB** JSON (383 MB on ZFS). It
  loads and gates on a big-RAM node; a consumer that can't hold it needs a projection that
  drops per-step `run.plans`. Capture-losslessly-project-later applies.
* **`protox_trials/` holds the raw traces.** Each trial dir has `output.log` (the tuning
  trace) + `repository/<timestamp>/` per step (`act_sql.txt`, `run.raw.csv`, `run.plans`,
  `run.metrics.json`). To re-derive an episode: `python ../scripts/gendba/protox_harvest.py
  --trial protox_trials/<dir> --benchmark <b>`. Six parser bugs were found and fixed this
  way — keep the raw trials.

The Proto-X episodes currently present:
| file | steps | speedup |
|---|---|---|
| `protox-job-…57d14_00000…` | 921 | 5.50× |
| `protox-job-…57d14_00001…` | 154 | 4.73× (truncated) |
| `protox-tpch-…0165d_00000…` | 440 | 2.69× |

**dsb has no Proto-X episode** — it is blocked on an embedder/config dimension mismatch
(see `../OFFLOAD.md §5`).

---

## 6. Filename conventions

* ISE: `<bench>-q<N>-b<budget_mb>-w<index_width>-<policy>-s<seed>-<hash>.json`
  (e.g. `dsb-q67-b1000-w1-extend-s0-aa0d62ee.json`).
* UniTune: `unitune-<bench>-<run>-<hash>.json`.
* Proto-X: `protox-<bench>-<RayTrialId>-<hash>.json`.
* Quarantined records keep their id and gain a sibling `<id>.failures.json`.
The `episode_id` inside the JSON matches the filename stem.

---

## 7. Traps for a consumer

* **Split on `template`, not query id** — or near-duplicate queries leak across train/eval.
* **Respect provenance** — for a deploy-time policy, the MEASURED outcome is a *label*, not
  a decision input (deploy is non-destructive; the agent decides from orient+screen only).
* **Episode sizes are wildly skewed** — median a few MB, but DSB `relaxation` runs reach
  >1 GB and the Proto-X job episode is 2.4 GB. Loading one needs several GB of RAM;
  `report.py` takes minutes on these.
* **`configured` vs `pk_only` starting state changes what a speedup means** — do not
  compare across them blindly.

---

## 8. Refreshing the summaries (do this after adding records)

```bash
cd ..                                             # repo root
python scripts/gendba/report.py                   # regenerates final_report.{txt,json}
python scripts/gendba/validate.py gendba_records/episodes    # re-gate (writes failures)
python scripts/gendba/validate.py gendba_records/quarantine  # re-check quarantined
```
`final_report.txt` and `final_validation.txt` here are the **pre-Proto-X** snapshots
(290 episodes); re-run the above for current numbers (293).
