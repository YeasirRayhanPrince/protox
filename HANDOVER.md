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

## 2. Current state — 283 episodes, all gate clean

| benchmark | n | task kinds | starting state | median speedup |
|---|---|---|---|---|
| job  | 91 | 66 index_selection, 23 query_optimization, 2 multi_component | pk_only | 1.673x |
| tpcc | 67 | index_selection | configured | 24.954x |
| tpch | 66 | index_selection | configured | 1.000x (34 regressions) |
| dsb  | 59 | index_selection | pk_only | 1.171x |

Re-gated at the end: **zero failures**, 52 suspect-for-magnitude (all TPC-C, all
confirmed real — six independent algorithms find `stock(s_i_id)`, and Q16 accounts
for 104.4 of the 105ms gain).

The headline measurement, unchanged all session: of 86 rejected near-misses that were
actually measured, **37 (43%) were wrong to reject**, the best 59% faster than the
accepted choice. That is a labelled cost-model error rate on close calls.

## 3. Rebuilding a machine

```bash
# ~3h, idempotent, resumable. --list shows phases, --from N resumes.
scripts/cloudlab/provision.sh
```
It builds PostgreSQL 15, the conda envs (`protox`, `ise`, `unitune`), and loads JOB,
TPC-H and DSB. It does NOT set up TPC-C — that is `scripts/gendba/tpcc_setup.sh`,
which is self-sufficient (creates its own `jvm` env, clones and builds BenchBase,
initdbs a cluster on 5493, loads 100 warehouses).

Verify before harvesting: `scripts/gendba/monitor.sh` and a single smoke episode.

## 4. How to run each harvest

```bash
scripts/gendba/run_all.sh        # ISE across job/tpch/dsb
scripts/gendba/run_phase2.sh     # anytime + db2advis
scripts/gendba/run_tpcc.sh       # TPC-C: loads if needed, derives protocol, harvests
scripts/gendba/unitune_chain.sh  # meta-decision sweep (ts, rb; alter optional)
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

## 7. What to do next, in priority order

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

## 8. Where things are

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
