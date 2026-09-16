# Gen-DBA harvest — handover

Written 2026-09-11, at the end of the CloudLab allocation that produced episodes
215–283. Read this first on a new machine; it is meant to get you productive without
re-deriving anything.

`/proj/pmoss-PG0/` is the ONLY filesystem that survives an allocation. `/mnt` and
`/data` are node-local and will be empty. Everything below assumes that.

---

## 1. What this is

We are collecting training data for Gen-DBA (`docs/cidr27_gendba.md`) by running
Proto-X and its baselines and recording, losslessly, what each system looked at and
decided. The record format and its rationale are in `docs/training_record.md`; the
six moves a DBA makes are in `docs/dba_loop.md`. Read both before changing the schema.

The guiding commitments, which have survived contact with the data:

* **Capture losslessly, project later.** An episode is a superset; `tool_sft`,
  `preference_pairs`, `cardinality` and `outcome` are recomputed from it, never stored.
* **Provenance is never mixed.** `estimated` / `measured` / `derived` / `declared`
  are separate fields. A derived number never sits in a measured one.
* **Absent is not inferred.** A move a system does not perform is recorded absent,
  with the reason. 214 of 283 episodes declare Move 2 (HYPOTHESIZE) absent because
  the scripted baselines genuinely do not hypothesise.
* **Both directions.** Regressions are data. TPC-H `configured` contributes 34 of
  them and is worth keeping for exactly that reason.

## 2. Current state — 290 episodes, all gate clean

| benchmark | n | task kinds | start | median | regressions |
|---|---|---|---|---|---|
| job  | 91 | 66 index_selection, 23 query_optimization, 2 multi_component | pk_only | 1.673x | 3 |
| tpcc | 67 | index_selection | configured | 24.954x | 8 |
| tpch | 66 | index_selection | configured | 1.000x | **34** |
| dsb  | 66 | index_selection | pk_only | 1.173x | 3 |

Four genuinely different regimes, which is the point: TPC-C has one dominant fixable
scan, JOB is real index selection, DSB is moderate, and TPC-H `configured` is an
already-tuned system where 34 of 66 episodes make things WORSE. A policy trained on
this cannot learn "indexes always help".

The 7 episodes the guard restored were all DSB (59 -> 66).

Re-gated by the deadline guard at 02:00 on the final day: **238 passed, 52 suspect,
zero failures**, and 7 episodes RESTORED from quarantine. Those 7 had been rejected
by a running harvest holding an older copy of the gate in memory; against the current
gate they pass. Re-gate at the end of every allocation for this reason.

The 52 suspects are all TPC-C and all confirmed real: six independent algorithms find
`stock(s_i_id)` (45 of 52), and Q16 accounts for 104.4 of the 105ms gain.

Projections at the end: 26,110 tool-call/response turns, 3,382 preference pairs (86
measured-adjudicated), 290 measured outcomes.

The headline measurement, unchanged all session: of 86 rejected near-misses that were
actually measured, **37 (43%) were wrong to reject**, the best 59% faster than the
accepted choice. That is a labelled cost-model error rate on close calls.

## 3. Rebuilding a machine

```bash
# ~3h, idempotent, resumable. --list shows phases, --from N resumes.
scripts/cloudlab/provision.sh
```
It builds PostgreSQL 15, the conda envs `protox` and `ise`, and loads JOB, TPC-H and
DSB. It does NOT set up TPC-C — that is `scripts/gendba/tpcc_setup.sh`, which is
self-sufficient (creates its own `jvm` env, clones and builds BenchBase, initdbs a
cluster on 5493, loads 100 warehouses).

**It does NOT create the `unitune` env**, despite an earlier revision of this file
saying it builds three. `scripts/gendba/run_tpcc.sh` and `unitune_run.sh` both
`conda activate unitune` and will fail on a freshly provisioned node. Everything else
in `scripts/gendba/` uses `ise`.

**Never edit `provision.sh` while it is running.** Bash reads a script incrementally
by byte offset, so an in-place edit makes the live process resume mid-token; this
killed a run at phase 5 on 2026-09-13 with `ure_logdir: command not found` while the
file on disk was perfectly valid.

Verify before harvesting: `scripts/gendba/monitor.sh` and a single smoke episode.

## 4. How to run each harvest

```bash
scripts/gendba/run_all.sh        # ISE across job/tpch/dsb
scripts/gendba/run_phase2.sh     # anytime + db2advis
scripts/gendba/run_tpcc.sh       # TPC-C: loads if needed, derives protocol, harvests
scripts/gendba/unitune_chain.sh  # meta-decision sweep (ts, rb; alter optional)
scripts/cloudlab/run_protox.sh   # Proto-X itself: preflight | smoke | full
scripts/gendba/protox_harvest.py # a finished Ray trial -> one trajectory episode
scripts/gendba/report.py         # corpus summary
scripts/gendba/validate.py       # the gate
scripts/gendba/unitune_compare.py # what the arm-selection rule changed
```
Everything resumes: `already_collected()` skips episodes already on disk, and writes
are atomic, so a killed harvest is safe to relaunch.

## 5. Traps that cost real time — do not rediscover these

**Measurement**
* An ERROR is not a TIMEOUT. Timeouts contribute the limit (a true lower bound);
  errors contribute what they cost before failing. Conflating them once turned a
  108ms TPC-C workload into a measured 900,112ms.
* A write workload needs its own protocol: measure inside a transaction and roll it
  back, PASS-outer (not query-outer) so repeats start from identical state, with a
  per-statement SAVEPOINT because one error aborts the whole transaction in
  PostgreSQL. TPC-C's statements carry literal primary keys — the workload conflicts
  with itself otherwise.
* `conn.rollback()` is a NO-OP against a `BEGIN` issued via `execute()` while the
  connection is in autocommit. Use `execute("ROLLBACK")`.
* Verify rollback by asserting row counts either side of a measurement. A missing
  rollback is invisible in the code — it looked correct and was not.
* `warmup=0, repeats=1` was derived for an ~18s analytic pass. It is wrong for a
  millisecond OLTP pass. `noise.py --suggest-repeats` picks the cheapest protocol
  that resolves a target floor.

**Environment**
* BenchBase needs EXACTLY JDK 23, and `-Dfmt.skip=true`.
* ISE hardcodes `port=5492` in `postgres_dbms.py:27`; patched at runtime by
  `harvest.py:patch_ise_connection`. Never edit the submodule.
* ISE's `_prepare_query` tests `"set" in stmt` before `select`, breaking 5 DSB
  queries; patched at runtime too.
* Name the DB role explicitly. Relying on ambient `PGUSER` failed 36 episodes.
* Proto-X paths: `config`, `benchmark_config`, `model_config`, `data_snapshot_path`
  are RELATIVE (prefixed with `mythril_dir`); `execute_query_*` must be ABSOLUTE.

**Operational**
* `pkill -f <pattern>` will match your own shell and kill the session. Build the
  pattern at runtime and skip every ancestor PID. This cost three shells, one of them
  killing a 6h run 16 minutes early.
* A monitor watching several runs of the same program must key its dedupe on the
  SOURCE FILE. Identical progress lines otherwise make it go silent while looking
  healthy.
* Long runs must checkpoint. `unitune_recover.py` rebuilt a killed run's episode from
  its checkpoint — 26 pulls, gate PASS, stamped `truncated`.

## 6. What is NOT possible without implementation work

* **UniTune on TPC-C.** Its OLTP path is disabled: `MultiTune/database/base.py:337`
  routes tpcc to a BenchBase execution path, `:529` is a bare `assert False`, and
  `:597` scores tpcc by THROUGHPUT from BenchBase's `summary.json`, not query latency.
  Config is committed at `unitune_run/tpcc_knob_index.ini`.
* **UDO.** Patched and importable (`udo_patches.py` fixes a hardcoded author path in
  `set_system_parameter`) but never run. It has no what-if screening, so every
  candidate is a real measurement — expensive, and its traces lack the
  estimated-vs-measured contrast that produced our strongest signal.
* **`acq` arm-selection.** `TopAdvisor.run()` dispatches only alter/rb/ts/udo;
  `optimize_acq` exists but is unreachable and would spin the budget doing nothing.
* **Bao, dexter, cophy_input.** Need a patched PostgreSQL, a Ruby binary, and a MIP
  solver respectively. See the roadmap memory.

## 7. NEXT STEP: run Proto-X itself

**We ran Proto-X's baselines all allocation and never ran Proto-X.** All 290 episodes
come from scripted algorithms (ISE x6) plus a bandit meta-policy (UniTune) plus a
hand-written QO policy. The paper's own system produced none of them. That is the
single biggest hole in the corpus, and it is the next thing to do.

### Why it matters more than another baseline

Every episode we have is **single-shot**: a policy is asked once for a configuration,
it answers, we measure. Proto-X is an RL agent that takes a SEQUENCE of actions
against a live database, sees the reward of each, and adapts — so it produces
**multi-step trajectories with intermediate rewards**, which is the shape that
matters for RL with tool calls and which nothing in the corpus currently has. It also
tunes knobs and indexes together in one action space, and its action embeddings are
themselves a learned artifact worth recording.

### It is already set up and was verified on this hardware

`docs/cloudlab_setup.md` section 8 has the exact commands and section 12 records the
verified deployment on the Clemson r650. Smoke test first — it is not optional, it
exercises the whole DB lifecycle (untar, start, run, index DDL, restart, reset) in
~30 minutes and is where every path mistake surfaces:

```bash
scripts/cloudlab/run_protox.sh job preflight   # checks only, launches nothing
scripts/cloudlab/run_protox.sh job smoke       # ~30 min
scripts/cloudlab/run_protox.sh job full        # 30 h, 1000 iterations
```

**Do not hand-write the `hpo.py` invocation.** Earlier revisions of this file carried
one and it was wrong in three of four path flags — it passed `$PWD/`-absolute values
for `--config`, `--benchmark-config` and `--data-snapshot-path`, all three of which
`agents/hpo.py` prefixes with `mythril_dir` unconditionally, producing
`/proj/…/protox//proj/…/protox/configs/…`. It also pointed `--config` at
`configs/config.yaml`, which is deliberately left as the pristine author template;
the machine-local ones are `configs/config_cloudlab_{job,tpch,dsb}.yaml`. And it
named a snapshot path that does not exist on a provisioned node.

`run_protox.sh` is that invocation written down once, with a preflight that refuses
to launch rather than fail 30 h in. Note there are two JOB snapshots and they are not
interchangeable: `job_base.tgz` is the PK-only base, `job.tgz` has the paper's
baseline indexes applied and is the one Proto-X starts from.

### Proto-X traps, all of which cost time before

* **Paths are relative or absolute, never both.** `config`, `benchmark_config`,
  `model_config` and `data_snapshot_path` are prefixed with `mythril_dir`
  unconditionally, so they must be RELATIVE. `execute_query_*` must be ABSOLUTE.
* **`agents/hpo.py:60` overwrites the YAML's `query_spec` from `params.json`.**
  Editing the YAML alone silently does nothing.
* **The stub benchbase XML needs `<transactiontypes>`.** Without it you get a
  TypeError *after* the baseline has already run — minutes of work thrown away.
* **Ray writes to the NFS home by default.** Set `TUNE_RESULT_DIR` and symlink to
  `/mnt/protox/ray_results`, or the run is both slow and lost on teardown.
* **Do NOT install hypopg on the Proto-X cluster.** It adds
  `pg_stat_user_tables_..._hypopg_hidden_indexes` to the snapshot and breaks
  Proto-X's state space with a KeyError. This is why 5492 has hypopg dropped.

### The harness work to turn its output into episodes

Proto-X does not emit our record format, so this is the real task — budget for it
rather than assuming the run is the work. Per Ray trial you get
(`docs/cloudlab_setup.md` section 9): `output.log` with every action and every
`Benchmark iteration with metric` line (this is the tuning trace), `tboard/` scalars
plus action embeddings, and `repository/<timestamp>/act_sql.txt` holding the exact
`CREATE INDEX` and `knob = value` for each evaluated configuration.

Map those onto the six moves: each RL step is a DECIDE (the action, with the
embedding as its discriminant) plus an APPLY AND MEASURE (act_sql.txt and the
measured metric). Move 3 (SCREEN CHEAPLY) is **absent** — Proto-X measures every
action for real — and must be recorded absent with that reason, exactly as the ISE
algorithms record Move 2 absent.

### DONE (2026-09-13): `scripts/gendba/protox_harvest.py` and the schema decision

**Settled: an RL trajectory is N decisions in ONE episode, not N episodes.** Splitting
it would destroy the only thing that makes it valuable — step *k*'s action is
conditioned on the state steps 0..*k*-1 produced, so as standalone episodes each step
would claim a starting state it did not start from and the credit assignment between
them becomes unrecoverable.

`record.py` needed **no change**: `events` is already an ordered lossless stream, so N
steps are N × (decide, apply, verify) groups carrying a step index and a per-step
measured reward. The task kind stays `multi_component_tuning` — the same task UniTune
performs, reached by a different method. Method lives in `policy`, not `task`, or a
consumer cannot compare a bandit against an RL agent on equal terms.

That forced one change in `validate.py`. The `meta_decision` checks demand an accepted
arm and a rejected set, which is right for a bandit choosing among enumerated
alternatives and wrong for an agent emitting a point in a continuous space — requiring
it would make the producer fabricate alternatives that were never scored. Those checks
now key on the method, and trajectory episodes get their own invariants: contiguous
step indices, a measured verify per step, terminal counts that agree with the event
stream, and a `best_step` **recomputed** from the per-step measurements rather than
restated. Verified against seven mutations of a real record.

Parsing traps, verified against the writers rather than guessed:
* The baseline marker is **misspelled** `Baseilne Metric` (`tune.py:128`). Grepping
  for `Baseline` finds nothing.
* A metric line is paired with the **following** `mv … repository …` line; that
  pairing is how a measurement is attached to a configuration. Both shipped replayers
  rely on it.
* Parse floats with a bounded float pattern, not a character class: the baseline value
  is followed by a sentence period, so `[-\d.eE+]+` captures `123.5.` and `float()`
  raises — which silently became "no baseline recorded" until a synthetic-trial test
  caught it.
* A query whose latency **equals** the per-query timeout was CENSORED, not failed:
  its true value is ≥ the limit (`replay_mythril.py:100` detects it the same way).

Still to do: run it against a real trial end to end. The synthetic-trial test covers
the parsers and the gate; only a real Ray trial exercises `Snapshot` (which restores
the starting snapshot to fingerprint the environment and initial state) and the
workload loader.

## 8. Then, in priority order

1. **A second write workload, or TPC-C with a less concentrated query mix.** Q16 is
   96% of the current TPC-C workload, so the 67 episodes test one decision well
   rather than many. This is the cheapest way to strengthen the newest and most
   valuable part of the corpus.
2. **Revert episodes.** Move 6 (KEEP OR REVERT) has **zero** events across all 283
   episodes. Nothing in the corpus ever applies something, measures it, and rolls it
   back. We have measured failures to revert from (a 3.75x knob regression).
3. **Statistics objects.** Move 2 is declared absent in 214 of 283 episodes. We have
   measured that all 25 JOB queries carry >=10x row misestimates and have never once
   acted on them; the fix for a misestimate is often `CREATE STATISTICS`, not an index.
   This is the only cheap path to hypothesis-bearing traces.
4. **Partitioning.** A genuine expansion — it changes the plan space (pruning,
   partition-wise joins), not just access paths. Needs a new harness.
5. **Storage layout / Parquet.** The paper's third task, still at zero episodes.

## 9. Where things are

```
/proj/pmoss-PG0/protox/
  gendba_records/episodes/      283 episodes (gitignored — data, not source)
  gendba_records/quarantine/    12 rejected, each with a .failures.json
  gendba_records/checkpoints/   partial runs, recoverable via unitune_recover.py
  node_artifacts/traces/        measured experiments (noise floor, reset drift,
                                reference table) — each cost real machine time
  node_artifacts/logs/          61 harvest logs
  node_artifacts/final_report.txt, final_regate.txt, unitune_sweep.txt
  scripts/gendba/               the harness
  docs/                         dba_loop.md, training_record.md, cloudlab_setup.md
/proj/pmoss-PG0/claude_sessions/latest/   transcripts + memory (no secrets)
```

Branch `gendba-harvest`. The repo lives on `/proj`, so its history survives a node
dying even unpushed.

---

## 10. Proto-X harvest — RESULTS (2026-09-16)

Proto-X ran for the first time. **3 trajectory episodes** landed (corpus 290 -> 293):

| episode | steps | speedup | notes |
|---|---|---|---|
| job (00000) | 921 | **5.50x** | full 30h run; 2.4GB JSON (383M on ZFS) |
| job (00001) | 154 | 4.73x | 2nd config, truncated when the run was capped |
| tpch (00000) | 440 | 2.69x | full 30h run, not truncated |

Each is one multi_component_tuning trajectory with the six-move spine
(orient/decide/apply/measure/keep-revert per step; hypothesize+screen absent).

### Traps hit and fixed
* **`--num-trials 1` does not cap the run.** initial_*.json has 4 configs, each a
  points_to_evaluate trial, so Ray runs 4 x `duration`. `run_protox.sh` now trims to
  the first config -> one trial per benchmark.
* **dsb needed two yaml keys** (`index_space_aux_brin`, `index_space_aux_md`) hpo.py
  reads unconditionally. Added (committed).

### dsb via Proto-X is BLOCKED (not done)
After the yaml keys, dsb dies loading the pretrained embedder
(`dsb_data_models/curated/model0/embedder_22.pth`):

    size mismatch VAE encoder: checkpoint [256,432] vs current model [256,408]

The checkpoint is for a schema whose index space is 432-dim; the repo's dsb config
yields 408. Fixing the web_returns list-marker typo (24 cols -> 425) does NOT bridge
it -- the dim is not the plain column count, and IndexSpace still builds 408. This
needs the matching embedder or a regenerated one, out of scope here. The earlier
training_record claim that the dsb embedder "does not contain web_returns" is wrong;
the checkpoint was trained WITH more columns than the repo now produces.

**To finish dsb later:** reconcile the dsb embedder with the index space dim --
either locate the embedder that matches the 408-dim repo schema, or regenerate the
embedder (embeddings/gen_index_data.py) against the current dsb attributes.
