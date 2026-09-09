# Running Proto-X on CloudLab

Findings from a source-level audit of this repo (branch `vldb24`), oriented toward a
CloudLab deployment. Every claim below is anchored to a `file:line` in the repo so it
can be re-checked.

**Bottom line:** the repo ships the tuner, the query sets, the starting configurations,
and pre-trained embeddings for all four benchmarks. It does **not** ship a Postgres
build, any schema DDL, or any data loader — you supply those. On CloudLab the two
things that will actually bite you are (a) the default 16-hour experiment expiry versus
30-hour tuning runs against **no working checkpointing**, and (b) putting a 13 GB pgdata
tarball anywhere near the NFS home directory.

---

## 1. What Proto-X does at runtime

`hpo.py` → `tune.py` → `envs/pg_env.py:PostgresEnv`. The env **owns the whole Postgres
lifecycle**; it never attaches to a server you started. Per trial it:

1. `rm -rf`s a pgdata dir and untars a snapshot into it — `restore_pristine_snapshot`, `envs/pg_env.py:262`
2. writes `postgresql.auto.conf`, force-appending `shared_preload_libraries='pg_hint_plan'` — `envs/pg_env.py:107`
3. starts/stops the server via `pg_ctl` on a port it picks itself — `envs/pg_env.py:133`, `envs/pg_env.py:237`
4. runs the workload, applies index DDL + knob changes, repeats for `horizon` steps, resets

Consequences: you need **binaries plus a tarball**, not a running cluster; and each
concurrent trial gets its own full copy of the data directory.

---

## 2. Supported databases

### DBMS: PostgreSQL only

There is no abstraction layer. One gym env is registered — `Postgres-v0`
(`envs/__init__.py:5`) — and it shells out to `pg_ctl` / `psql` / `pg_isready` directly.
The knob space, the `pg_stat_*` state representation, and the `pg_hint_plan` action
encoding are all Postgres-specific.

### Workloads: four

| Benchmark | Type | Configs in `configs/benchmark/` | Queries |
|---|---|---|---|
| **JOB** (IMDb) | OLAP | `job_full`, `job_a`, `job_ab`, `job_c_a`, `job_c_ab` | 113 full / 33 / 66 |
| **TPC-H** | OLAP | `tpch` (SF10 in the paper) | 24 |
| **DSB** (TPC-DS derivative) | OLAP | `dsb_s1`, `dsb_s2`, `dsb_s5`, `dsb_s10`, `dsb_revise` | 490 in `queries/dsb_10`, subset per order file |
| **TPC-C** | OLTP | `tpcc` | 33 txn templates |

`.yaml.bao` / `.yaml.as` / `.yaml.hintset` / `.yaml.complex` siblings are variants for the
**baseline** systems (Bao, Auto-Steer), not for Proto-X.

**TPC-C is different in kind.** `configs/benchmark/tpcc.yaml:3,6` set `oltp_workload: True`
and `benchbase: True`, routing execution through `envs/workload.py:261` →
`java -jar benchbase.jar`. It therefore additionally needs a built **BenchBase** and a real
BenchBase XML, and it tars a snapshot between steps (`envs/pg_env.py:118`) because writes
mutate data. The three OLAP benchmarks run queries directly over psycopg and need only a
*dummy parseable* XML.

**Recommendation: start with JOB.** Largest shipped artifact set, no BenchBase, no OLTP
snapshot churn, and it is the benchmark this group already has IMDb data for.

---

## 3. What the repo does NOT give you

`README.md:19-26` is the entire guidance on obtaining and loading a database:

> 1. Create/Load the initial database contents and the initial starting configuration.
> 2. Clean the database by optionally running `VACUUM FULL` followed by `VACUUM` and `ANALYZE`.
> 3. Shutdown Postgres and navigate to the directory containing the database data (i.e., pgdata)
> 4. `tar cf pgdata.tgz <database data>`

Step 1 — the whole thing — is left to you. Verified by grep across the repo:

- **No Postgres build/install instructions and no version stated anywhere.**
  `configs/config.yaml:6` just points at the author's `/mnt/nvme0n1/wz2/noisepage`.
- **No schema DDL.** Zero `CREATE TABLE` in any `.sql`, `.py`, or `.md`.
- **No data generation or download.** No `dbgen`, no `dsdgen`, no IMDb fetch, no
  `COPY ... FROM`, no loader.
- The only downloading `.sh` is `sqlean-extensions/download.sh`, which grabs a **SQLite**
  extension for the Auto-Steer baseline — unrelated to Postgres.

### The `load_*.py` scripts are not loaders

`scripts/experiments/{job_full,tpch_sf10,dsb_sf10}/load_*.py` all begin with
`env.restore_pristine_snapshot()`, i.e. they assume your `.tgz` already exists. What they
encode is the **"initial starting configuration"** from step 1 above, and that is
genuinely valuable — it is the paper's untuned baseline:

- `load_tpch.py` — pgtune-style knobs (`shared_buffers=32GB`, `random_page_cost=1.1`, …),
  3 indexes, the `revenue0_PID` view that TPC-H Q15 needs, then `pg_prewarm` on every table
- `load_job_full.py` — 6 IMDb foreign-key indexes (`cast_info`, `movie_companies`,
  `movie_info`, `movie_keyword`) + `--omit-index` to skip them
- `load_dsb.py` — index set selected per `--sf` (1/10/20) and `--stream`

Run them **after** you have loaded data yourself and produced a first snapshot.

---

## 4. Postgres: version, extensions, layout

### Version window: PG 13-16. Use PG 15.

The README never says, but the code pins it:

| Constraint | Bound | Where |
|---|---|---|
| `autovacuum_vacuum_insert_threshold`, `autovacuum_vacuum_insert_scale_factor` | PG 13+ | `configs/config.yaml` knob space |
| `maintenance_io_concurrency` | PG 13+ | `configs/config.yaml` knob space |
| `n_ins_since_vacuum` — part of the **agent's state vector** | PG 13+ | `envs/spaces/utils.py:71` |
| `pg_stat_bgwriter.{buffers_backend, buffers_backend_fsync, maxwritten_clean, checkpoint_write_time}` | **≤ PG 16** | `envs/spaces/utils.py:46` |

PG 17 moved those bgwriter columns to `pg_stat_checkpointer`, so 17 breaks the state
space. PG 12 fails the lower bound on both the knob space and the state space. **PG 15**
matches the paper's build and has a well-supported `pg_hint_plan` branch.

### Required extensions

| Extension | When | Note |
|---|---|---|
| **`pg_hint_plan`** | Always | `envs/pg_env.py:107` appends it to `shared_preload_libraries` on *every* restart. Must match the PG major version. |
| **`HypoPG`** | Only to train new embeddings | `embeddings/gen_index_data.py:243`. Skippable — see §5. |
| `pg_prewarm` | Only for TPC-H | created by `load_tpch.py` |

### Directory layout the code assumes

`postgres_path` must be a **flat directory containing `pg_ctl`, `psql`, `pg_isready`,
`postgres`** — *not* a prefix with a `bin/` subdir (`envs/spec.py:78`, `envs/pg_env.py:133`).
So either configure `postgres_path` as `<prefix>/bin`, or symlink. Data directories are
created as `$postgres_path/pgdata<port>`, and port-claim `.signal` files are written into
the same directory (`agents/hpo.py:get_free_port`), so **`postgres_path` must be writable
and on a big local disk.**

Ports are auto-allocated in **5434-5500** (`agents/hpo.py:get_free_port`).

### Snapshot semantics

`--data-snapshot-path` is untarred with `--strip-components 1` (`envs/pg_env.py:268`), so
the archive's first path component is discarded:

```bash
cd <parent-of-pgdata> && tar cf job.tgz pgdata     # correct
```

`envs/pg_env.py:270` then appends `port=<port>` to the extracted `postgresql.conf`.

### Credentials

`configs/config.yaml` hardcodes db `benchbase`, user `admin`, password `password`. Either
match those when loading, or edit the config. `envs/pg_env.py:190` also runs
`SET maintenance_work_mem = '4GB'` for DDL, so the role needs to be able to do that.

---

## 5. Embeddings — skip the expensive stage

The README's whole "Generating Embeddings" section (which is what needs HypoPG) is only
for training *new* latent spaces. **Trained embeddings ship for all four benchmarks**, each
complete with the `config` file that `envs/spec.py:70` loads from the same directory:

| Benchmark | Shipped at | Expected relative path in the config |
|---|---|---|
| JOB | `results/latent_spaces/spaces/job/model6/` | `job2_models/model6/embedder_19.pth` |
| TPC-H | `results/latent_spaces/spaces/tpch/model0/` | `tpch2_models/model0/embedder_20.pth` |
| DSB | `results/latent_spaces/spaces/dsb/model0/` | `dsb_data_models/curated/model0/embedder_22.pth` |
| TPC-C | `results/latent_spaces/spaces/tpcc/model0/` | `tpcc_worlds/model0/embedder_15.pth` |

The right-hand column is what `results/<bench>/us/*/params.json` references, resolved
relative to `--mythril-dir` (`agents/hpo.py:127`). So for JOB:

```bash
mkdir -p job2_models && cp -r results/latent_spaces/spaces/job/model6 job2_models/
```

`envs/spec.py:69-71` reads `embedder_19.pth` **and** the sibling `config` — copy the whole
directory, not just the `.pth`.

The git submodules (`UDO`, `Auto-Steer`, `index_selection_evaluation`, `unitune/*`) are all
uninitialized and are **baselines only** — irrelevant unless you want the comparisons.

---

## 6. Path patching — nothing works unmodified

Every config still points at the original author's machine.

| File | Line | Fix |
|---|---|---|
| `configs/config.yaml` | 3 | `benchbase_path` → your BenchBase (or any path, if not TPC-C) |
| `configs/config.yaml` | 4 | `benchbase_config_path` |
| `configs/config.yaml` | 6 | `postgres_path` → your flat PG bin dir |
| `configs/config.yaml` | 7-13 | `postgres_data`, port, db/user/password if you didn't match them |
| `configs/benchmark/job_full.yaml` | 9, 10 | `query_directory`, `query_order` |

**Subtle trap:** `agents/hpo.py:_mutate_common_config` prefixes `mythril_dir` onto
`query_directory`/`query_order` **only when the path is relative**. The shipped values are
absolute (`/home/wz2/mythril/...`), so they silently stay broken. Change them to relative:

```yaml
query_directory: "queries/job_full"
query_order: "queries/job_full/order.txt"
```

`--benchbase-config-path` must be a **parseable XML file even for JOB** —
`_mutate_common_config` calls `ET.parse` unconditionally and then sets `root.find("url").text`.
A minimal stub is **not** enough. Once per-query knobs are on (`allow_per_query: True`,
which every OLAP config sets), `envs/spaces/utils.py:319` does
`root.find("transactiontypes")` and iterates the result unconditionally — a missing
element is `TypeError: 'NoneType' object is not iterable`, thrown only after the
baseline workload has already run. The element must exist; empty is correct for the
OLAP benchmarks, because per-query knobs reach the queries as `/*+ ... */` hints via
`envs/workload.py:595`, not through this file.

```xml
<?xml version="1.0"?>
<parameters>
  <url></url>
  <transactiontypes></transactiontypes>
</parameters>
```

### `--initial-configs` needs a JSON **array**

`hpo.py:203` does `json.load(f)` then iterates and asserts `"mythril_args" in config`.
`results/<bench>/us/*/params.json` is a single **object**, so passing it directly makes the
loop iterate over string keys and trip the assert. Wrap it:

```bash
python3 -c 'import json,sys; json.dump([json.load(open(sys.argv[1]))], open(sys.argv[2],"w"), indent=2)' \
  results/job/us/TuneOpt_f5769_00000_0_2024-05-08_20-17-14/params.json initial_job.json
```

Then edit the embedded `mythril_args` in that file — per `README.md:101-103` its values
**take precedence over the command line**. At minimum fix `mythril_dir` (ships as
`~/mythril`), `data_snapshot_path` (`data/job.tgz`), `benchbase_config_path`, and
`config`/`benchmark_config`.

---

## 7. CloudLab specifics

### 7.1 Experiment expiry vs. run length — the biggest risk

A faithful run is `--duration 30.0` hours (see the shipped `params.json`). CloudLab
experiments default to **16 hours** and must be extended through the portal; long
extensions need justification and are not guaranteed.

**And checkpointing does not work.** `hpo.py:130-137`:

```python
def save_checkpoint(self, checkpoint_dir):
    # We can't actually do anything about this right now.
    pass
```

Both `save_checkpoint` and `load_checkpoint` are no-ops, so a Ray Tune trial killed by
experiment expiry is **lost entirely**. There is a `--dump 1` / `--load 1` pickle path
(`tune.py:pickle`/`unpickle`, reachable because `_construct_common_config` does not pop
those args), but it only fires in `cleanup()` at the *end* of a trial — it does not survive
a hard kill either.

Mitigations, in order of preference:

1. **Extend the experiment before you start**, to 40+ hours, and say in the justification
   that it is a single long-running DBMS tuning experiment.
2. **Shorten `--duration`** to fit inside the window (e.g. `--duration 12.0`) and treat it
   as a truncated run. The per-step artifacts in `repository/` are written continuously, so
   a shorter run still yields a usable trace — just a shallower one.
3. Run trials **sequentially in separate experiments**, one `--duration` block each.

Whatever you choose, **rsync `artifacts/` off the node continuously** — see §7.4.

### 7.2 Node selection

Requirements to satisfy: `configs/config.yaml` lets the agent set `shared_buffers` up to
32 GB and `work_mem` up to 4 GB, so **≥ 64 GB RAM** is a floor and 128-192 GB is
comfortable. Local NVMe/SSD matters more than core count — the workload is I/O- and
planner-bound, and the RL nets are tiny (`pi 128,128`, `qf 1024` in the shipped params), so
**no GPU is needed**; install CPU-only torch.

Reasonable candidates (confirm current specs on the CloudLab hardware page, these change):

| Type | Cluster | Rough spec | Notes |
|---|---|---|---|
| `c220g5` | Wisconsin | 2×10-core Xeon Silver, ~192 GB, SSD + HDD | plentiful; good default |
| `c6525-25g` | Utah | 24-core EPYC, ~128 GB, SSD + NVMe | NVMe is a real win here |
| `r650` | Clemson | 2×36-core Xeon, ~256 GB, NVMe | best if available |
| `xl170` | Utah | 10-core, ~64 GB, SSD | workable but RAM-tight |

Ubuntu 22.04 image, matching `README.md:9`.

### 7.3 Disk layout — do not use the NFS home

`/users/<username>` on CloudLab is **NFS-mounted with a small quota**. Untarring a 13 GB
pgdata onto it, repeatedly, per trial, will be catastrophic for both you and the cluster.

Provision local storage first:

```bash
sudo /usr/local/etc/emulab/mkextrafs.pl /mnt        # formats the spare local disk onto /mnt
sudo mkdir -p /mnt/protox && sudo chown $USER /mnt/protox
```

Then keep **all** of these on `/mnt`:

- the Postgres install prefix (because `pgdata<port>` dirs are created inside `postgres_path`)
- the snapshot tarball
- `artifacts/` (log, tboard, repository)

**Disk budget:** each concurrent trial untars its own full copy. JOB ≈ 13 GB, so
`--max-concurrent 4` ≈ 55 GB live plus the archive plus per-step index growth. Size the
`/mnt` filesystem accordingly, and prefer NVMe.

### 7.4 Getting data onto an ephemeral node

CloudLab nodes are wiped between experiments. Options for the pgdata tarball, best first:

1. **A CloudLab dataset (persistent blockstore)** holding the finished `job.tgz`, mounted
   into the experiment via the profile. Build it once, reuse forever. This is the right
   answer if you will run more than twice.
2. **Rebuild in-experiment** from a source you control — copy the tarball from this machine
   (`/ssd_root/yrayhan/`) over `scp`/`rsync` at experiment start. 13 GB over a decent link
   is a few minutes.
3. Regenerate from scratch on the node (IMDb download + load + vacuum + analyze). Slowest;
   only worth it the first time.

Symmetrically, **stream results off the node**: `artifacts/` is the entire scientific
output and dies with the experiment.

```bash
while true; do rsync -az /mnt/protox/artifacts/ you@host:~/protox-results/$(hostname)/; sleep 300; done
```

### 7.5 Things CloudLab makes easy

- **Passwordless sudo is available**, which the replay path requires: `envs/pg_env.py:126`
  runs `sudo sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"` between steps for cold-cache
  fairness. Verify with `sudo -n true` before a long replay, or it will hang.
- Root access for `sysctl` (shared memory limits for a 32 GB `shared_buffers`), and for
  building Postgres from source.

### 7.6 Ray

`hpo.py:172` hard-connects to `localhost:6379`, so Ray must already be up:

```bash
OMP_NUM_THREADS=<threads-per-trial> ray start --head --num-cpus=<parallel-trials>
```

Single-node only, as written. `ray stop -f` when done.

---

## 8. Setup sequence

```bash
# --- 0. local storage ---
sudo /usr/local/etc/emulab/mkextrafs.pl /mnt
sudo mkdir -p /mnt/protox && sudo chown $USER /mnt/protox
cd /mnt/protox

# --- 1. Postgres 15 + pg_hint_plan, flat layout ---
sudo apt-get update && sudo apt-get install -y build-essential libreadline-dev zlib1g-dev \
    flex bison libxml2-dev libxslt1-dev libssl-dev libicu-dev pkg-config
# build postgres 15 with --prefix=/mnt/protox/pg15
# build pg_hint_plan (PG15 branch) against /mnt/protox/pg15/bin/pg_config
#   -> postgres_path in config.yaml is /mnt/protox/pg15/bin

# --- 2. python env (CPU-only torch; no GPU on these nodes) ---
conda create -n protox python=3.9 -y
conda activate protox
conda env config vars set PYTHONNOUSERSITE=1
conda deactivate && conda activate protox
grep -v '^nvidia-' requirements.txt > /tmp/req-cpu.txt     # drop ~2 GB of cu11 wheels
pip install -r /tmp/req-cpu.txt

# --- 3. data ---
#   load IMDb into PG 15 as db=benchbase user=admin
#   VACUUM FULL; VACUUM; ANALYZE;  then stop the server
#   cd <parent-of-pgdata> && tar cf /mnt/protox/data/job.tgz pgdata
#   python3 scripts/experiments/job_full/load_job_full.py --config-file configs/config.yaml
#     (applies the paper's baseline indexes; re-tar afterwards for the starting snapshot)

# --- 4. repo prep ---
mkdir -p job2_models && cp -r results/latent_spaces/spaces/job/model6 job2_models/
# patch configs/config.yaml (lines 3,4,6) and configs/benchmark/job_full.yaml (lines 9,10)
# write a stub benchbase XML
# build initial_job.json as a JSON *array* (see §6)

# --- 5. smoke test BEFORE the long run ---
ray start --head --num-cpus=1
python3 hpo.py --config $PWD/configs/config.yaml --agent wolp \
  --model-config $PWD/configs/wolp_params.yaml \
  --benchmark-config $PWD/configs/benchmark/job_full.yaml \
  --mythril-dir $PWD --num-trials 1 --max-concurrent 1 \
  --max-iterations 20 --horizon 5 --duration 0.5 --target latency \
  --data-snapshot-path /mnt/protox/data/job.tgz \
  --workload-timeout 600 --timeout 15 \
  --benchbase-config-path $PWD/stub_benchbase.xml \
  --initial-configs initial_job.json --initial-repeats 1

# --- 6. full run: same command with --duration 30.0 --max-iterations 1000 ---
```

The smoke test is not optional — it exercises the whole DB lifecycle (untar, start, run,
index DDL, restart, reset) and the artifact writer in ~30 minutes, which is where every
path-patching mistake surfaces.

---

## 9. Traces you get

Per Ray trial directory:

| Artifact | Written by | Contents |
|---|---|---|
| `output.log` / `stderr` | `utils/logger.py:20` | full DEBUG stream: every action, every `Benchmark iteration with metric`, every repository `mv`. **This is the tuning trace** and is what `replay_mythril.py` parses. |
| `tboard/` | `utils/logger.py:29` | tensorboard scalars — reward, policy/critic loss, `instr_time/*` — plus action **embeddings** with metadata |
| `repository/<timestamp>/` | `envs/repository.py:29` | one directory **per evaluated configuration** |
| ↳ `act_sql.txt` | `envs/repository.py:39` | the exact `CREATE INDEX` plus every `knob = value` for that step |
| ↳ `run.raw.csv` | `envs/workload.py:672` | per-query latency in µs, in workload order |
| ↳ `run.plans` | `envs/workload.py:637` | **per-query `EXPLAIN (FORMAT JSON)` plans** + the per-query knobs that were active |
| ↳ `run.metrics.json` | `envs/workload.py:651` | flattened `pg_stat_*` delta vector — the agent's state |
| ↳ `pg.conf`, `prior_state.txt` | `envs/repository.py:32,36` | resulting server config; preceding state |
| `pg.log.<n>` | `envs/pg_env.py:114` | server log, rotated per restart |
| `repository/baseline/` | `envs/pg_env.py:363` | the untuned reference run |

`configs/config.yaml:31` already has `no_trace: False`, which is what enables the
tensorboard writer (`utils/logger.py:11`). Leave it.

### Optimization-vs-effect analysis

`scripts/replay_mythril.py` re-reads `output.log`, re-applies each configuration in order
to a fresh database, and re-measures. Output:

- `out.csv` — `step, orig_cost, time_since_start, runtime0..N`, exactly the format of the
  shipped `results/job/us/*/out.csv`
- with `--output-artifacts <dir>`: `step<N>.plans.old` / `step<N>.plans.new` — the plans
  **before and after** each action. This is the direct "what did this optimization do to
  the query plans" trace (`scripts/replay_mythril.py:167,317`).

It expects a Ray trial directory containing `config.yaml`, `benchmark.xml`, `stdout`,
`stderr`, and `repository/` (`scripts/replay_mythril.py:35-99`), and needs
`--pg-path` pointed at your flat PG bin dir. Budget a full workload replay per step.

---

## 10. Verification checklist

Before the long run:

- [ ] `postgres_path` is flat and contains `pg_ctl`, `psql`, `pg_isready`, `postgres`
- [ ] `postgres_path` is on `/mnt` (local disk) and writable — `pgdata<port>` and `.signal` files land there
- [ ] `SELECT * FROM pg_stat_bgwriter` returns `buffers_backend` (fails on PG 17)
- [ ] `SELECT n_ins_since_vacuum FROM pg_stat_user_tables LIMIT 1` works (fails on PG 12)
- [ ] `pg_hint_plan.so` present and loadable for the exact PG major version
- [ ] snapshot untars with `--strip-components 1` to a valid pgdata
- [ ] `psql "host=localhost port=<p> dbname=benchbase user=admin password=password"` connects
- [ ] `configs/benchmark/job_full.yaml` query paths are **relative**
- [ ] `initial_job.json` is a JSON **array**, and its inner `mythril_args` paths are yours
- [ ] `job2_models/model6/` contains both `embedder_19.pth` **and** `config`
- [ ] `sudo -n true` succeeds (needed by replay's `drop_caches`)
- [ ] `ray status` shows a head node at `localhost:6379`
- [ ] experiment extended past `--duration`, given checkpointing is a no-op
- [ ] `artifacts/` rsync loop running to an off-node destination

## 11. Time and resource budget

- JOB full = 113 queries; `--workload-timeout 600`, `--timeout 15`, `--horizon 5`
- One faithful trial = **30 hours**; the paper repeats trials
- ~13 GB of local disk per concurrent trial, plus the archive, plus index growth
- No GPU required

---

## 12. Verified deployment (Clemson `r650`, 2026-09-07)

Everything below was executed and verified on
`node0.yrayhan-314821.pmoss-pg0.clemson.cloudlab.us` — 64 cores, 188 GB RAM, two
745 GB NVMe. This section records what actually happened, including several points
where the sections above turned out to be wrong or incomplete.

### 12.1 Storage

`mkextrafs.pl` claims the free space on the **boot** disk (`nvme1n1p4` → `/mnt`,
628 GB). The second NVMe (`nvme0n1`) is untouched and must be formatted by hand;
it was mounted at `/data` (733 GB). Keeping snapshots on `/data` and the per-trial
`pgdata<port>` copies on `/mnt` puts them on separate devices.

| Path | Contents |
|---|---|
| `/mnt/protox/pg15/bin` | `postgres_path` — per-trial `pgdata<port>` dirs are created *inside* it |
| `/mnt/protox/miniconda3/envs/protox` | Python 3.9 env |
| `/mnt/protox/ray_results` | Ray trial output (see §12.5) |
| `/data/protox/data/*.tgz` | snapshots |
| `/data/protox/gen/` | raw generator output |

### 12.2 Build recipe that worked

PostgreSQL **15.7** from source, `--prefix=/mnt/protox/pg15`, plus `pg_hint_plan`
(branch `PG15`), `HypoPG`, and contrib `pg_prewarm`. All four checklist probes in §10
pass. Note `postgres_path` is `<prefix>/bin`, and that directory must be writable.

### 12.3 Python environment — three gaps in `requirements.txt`

- **`pglast==3.8` is gone from PyPI** (only ≥5.0 remains), and 5.x removed the
  `pglast.node` API that `envs/workload_utils.py` depends on. Build 3.8 from source:
  `git clone --recursive -b v3.8 https://github.com/lelit/pglast && pip install .`
- **`psutil` is missing** from `requirements.txt` but imported by `envs/pg_env.py:1`.
- `agents/common/env_checker.py` imports legacy `gym`, but nothing imports
  `env_checker` — it is dead code. Do **not** install `gym`.
- Miniconda now refuses `defaults` without accepting Anaconda ToS; use
  `-c conda-forge --override-channels`.

### 12.4 Paths must be RELATIVE — this is the main trap

`agents/hpo.py` and `agents/wolp/config.py` prefix `mythril_dir` **unconditionally**
onto four fields. Absolute values silently become `/repo//abs/path` and fail:

| Field | Site | Must be |
|---|---|---|
| `config` | `agents/hpo.py:71` | relative |
| `benchmark_config` | `agents/hpo.py:49` | relative |
| `model_config` | `agents/wolp/config.py:80` | relative |
| `data_snapshot_path` | `agents/hpo.py:101` | relative |
| `vae_metadata.embeddings` | `agents/hpo.py:127` | relative (ships correct) |
| `query_directory` / `query_order` | `agents/hpo.py:63,65` | relative (prefixed only if relative) |
| `execute_query_directory` / `execute_query_order` (DSB only) | `envs/workload.py:200` | **absolute** — never prefixed |
| `benchbase_config_path` | used as-is | absolute |

Because snapshots must be reachable relative to the repo, symlink the data directory
into it: `ln -s /data/protox/data /proj/pmoss-PG0/protox/data`, then
`data_snapshot_path: data/job.tgz` — which is exactly why the shipped `params.json`
reads that way.

**Also:** `agents/hpo.py:60` overwrites the benchmark YAML's entire `query_spec` with
`mythril_query_spec` from `params.json`, which still holds the author's
`/home/wz2/mythril/...` paths. Patching `configs/benchmark/*.yaml` alone is not enough —
the `initial_*.json` must be patched too.

### 12.5 Ray writes to the NFS home by default

`hpo.py:247`'s `RunConfig` sets no `local_dir`, so results land in `~/ray_results`,
i.e. the NFS home — and since `agents/hpo.py:102-105` redirects `repository/`,
`tboard/` and the log into the trial dir, **the entire scientific output** goes there.
Set `TUNE_RESULT_DIR=/mnt/protox/ray_results` (honoured at
`ray/tune/result.py:125`) and symlink `~/ray_results` to local disk as a backstop.

### 12.6 Data generation

TPC-H and DSB need no external dump — both generate locally.

- **TPC-H** (`electrum/tpch-dbgen`, `-s 10 -C 16`): parallel generation is fine, but
  `dbgen` writes some chunk files mode `--x-----x`. `chmod 644` them or COPY fails on
  a subset and you get a **silently partial load**. Rows end with a trailing `|`, so
  strip it (`COPY ... FROM PROGRAM 'sed -e ''s/|$//'' <file>'`).
- **DSB** (`microsoft/dsb`): the tools need `-fcommon` to build on GCC 11 — without it
  `dsqgen` fails to link (`multiple definition of 'yydebug'`) and `dsdgen` segfaults.
  Even rebuilt, **`-PARALLEL`/`-CHILD` segfaults for every child but 1**; DSB's own
  `scripts/generate_dsb_db_files.py` runs it serially, so do that (~35 min at SF10).
  With `-TERMINATE N` there is **no** trailing separator, so unlike TPC-H you must
  *not* strip the last `|` — doing so silently drops each row's final column.
  Load with `FORMAT csv, DELIMITER '|', NULL '', QUOTE E'\b'`.
  DDL comes from DSB's own `scripts/create_tables.sql` (25 tables, 24 PKs).

Load into heap-only tables and add primary keys afterwards; then `VACUUM (FULL, ANALYZE)`.

Verified counts: TPC-H SF10 `lineitem` 59,986,052 / `orders` 15,000,000;
DSB SF10 `inventory` 133,110,000 / `store_sales` 28,800,991 / `catalog_sales` 14,397,492.

### 12.7 Shrink the snapshot before tarring

A freshly loaded cluster carries ~17 GB of recycled WAL segments, and `CHECKPOINT`
will not release them. After a clean shutdown, `pg_resetwal -D <pgdata>` drops
`pg_wal` to ~17 MB — TPC-H went 31 GB → 15 GB. This matters twice over, since every
trial untars its own copy.

### 12.8 `load_*.py` quirks

- `load_tpch.py` ends with `CREATE EXTENSION pg_prewarm`; it aborts if the extension
  already exists in your base snapshot. Only cache warming follows, which a snapshot
  does not preserve — so the failure is harmless if the indexes and the
  `revenue0_PID` view were created.
- `load_dsb.py` ends by opening a **hardcoded** `/mnt/nvme0n1/wz2/noisepage/...`
  path. The result is assigned to a local and never used — dead code at the end of
  the file. The 12 indexes and the knob changes complete before it.
- `load_dsb.py` hardcodes `configs/benchmark/dsb_s1.yaml`, so run it from the repo root.

### 12.9 A real bug in the DSB configs — do NOT fix it

All five `configs/benchmark/dsb_*.yaml` write `web_returns`'s column list with `_`
instead of `-` as the YAML list marker, so its 23 columns parse as a single string
rather than a list. It is tempting to correct.

**Don't.** The shipped DSB embedder's `class_mapping`
(`dsb_data_models/curated/model0/config`) has 136 entries and contains **no
`web_returns` columns at all** — the typo is baked into the pre-trained artifact.
Fixing the YAML changes the index action space and breaks compatibility with
`embedder_22.pth`. JOB, TPC-H and TPC-C configs are unaffected.

### 12.10 End-to-end validation

TPC-H SF10 smoke run (`--horizon 5`, `--duration 0.35`), single trial:

| Step | Workload latency | Reward |
|---|---|---|
| baseline | 92.52 s | 0.000 |
| 1 | 51.39 s | 0.445 |
| 2 | 45.33 s | 0.510 |
| 3 | 38.52 s | 0.584 |
| 4 | 38.24 s | 0.587 |

**2.4× in four steps**, confirming snapshot restore, index DDL, knob application,
workload execution, reward, and the shipped embedding all work together.
