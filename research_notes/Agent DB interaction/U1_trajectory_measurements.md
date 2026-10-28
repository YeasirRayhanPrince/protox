# U1 — Measuring LLM-agent DB traffic from public trajectory datasets

Date: 2026-10-27. All numbers below were computed by us from downloaded trajectories, except where a line says otherwise. Script: `/tmp/claude-20001/-users-yrayhan-protox/25be943d-7410-404d-8dc2-a8f7d1959d14/scratchpad/u1_scripts/analyze.py` (run with `python3 -I`; the scratchpad is temporary). Raw outputs are in `out_*.json` in the same directory.

## (a) Datasets

**Used:**

| ID | Source | What it is | Trajectories | Model(s) |
|---|---|---|---|---|
| BIRD | [experiential-labs/wmo-bird-sql-traces](https://huggingface.co/datasets/experiential-labs/wmo-bird-sql-traces) (`traces.otel.jsonl`, 11 MB) | Real runs of BIRD mini-dev text-to-SQL. The agent has a bash tool, runs `sqlite3 database.db "<SQL>"`, and gets the schema as a `schema.sql` file. | 1,993 | Claude Opus 4.8 (988), Opus 4.7 (988), Opus 4.6 (17). Mean reward 0.675 |
| PTBR | [Boakpe/pt-br-agentic-text-to-sql-distilled-trajectories](https://huggingface.co/datasets/Boakpe/pt-br-agentic-text-to-sql-distilled-trajectories) (332 MB) | Tool-calling agent on PostgreSQL with tools `get_table_schema`, `execute_sql` and `final_answer`. Two databases: `analise_dados` (6,659) and `compras_publicas` (783). **Only trajectories an LLM judge marked correct are kept**, and the teacher model is not named. | 7,442 | unstated teacher |
| TAU | [sierra-research/tau-bench historical_trajectories](https://github.com/sierra-research/tau-bench/tree/main/historical_trajectories) (52 MB) | Customer-service agent calling typed tools over a JSON "database" (retail, airline). **These are API calls, not SQL.** Tools are classified by name: `get_*`, `find_*` and `search_*` are reads; `cancel_*`, `modify_*`, `exchange_*`, `return_*`, `book_*`, `update_*` and `send_*` are writes. `think`, `calculate` and `transfer_to_human_agents` are excluded. | 1,980 (multiple trials per task) | GPT-4o, Claude 3.5 Sonnet (new) |
| SPTC | [Spider2 spider-agent-tc results](https://github.com/xlang-ai/Spider2/tree/main/methods/spider-agent-tc/results) | Spider 2.0-Snow on real Snowflake. Only **one** trajectory has been released. | 1 | Claude 3.7 Sonnet (from the directory name) |

**Checked but not usable:**
- [xlangai/spider2v-trajs](https://huggingface.co/datasets/xlangai/spider2v-trajs): a 29 GB zip of GUI-agent runs, well over the size limit.
- Spider-Agent lite, snow and dbt `output/` directories: contain only a README.
- [BIRD-Interact repo](https://github.com/bird-bench/BIRD-Interact): no trajectory or log files in the tree.
- BIRD-Critic HF datasets: task data only.
- [whfeLingYu/AgentBench-MAS_DB](https://huggingface.co/datasets/whfeLingYu/AgentBench-MAS_DB): tasks and tables, not traces.
- [mackenzietechdocs/…etl-sql-traces](https://huggingface.co/datasets/mackenzietechdocs/repro-beyond-text-to-sql-can-llms-really-debug-enterprise-etl-sql-traces): one Claude Code session that calls an LLM through curl. It contains no DB traffic.
- DBA-Bench ([2607.22165](https://www.alphaxiv.org/abs/2607.22165)) and "Supporting Our AI Overlords" ([2509.00997](https://arxiv.org/html/2509.00997v2)): searched for released run logs or traces and found none.
- Not examined: SWE-agent/OpenHands dumps, DA-Code and ELT-Bench.

## Method

**Classification.** Every DB-touching tool call is split into statements and each statement is labelled with one of:
- `select` (user data)
- `catalog` (information_schema, pg_*, sqlite_master, PRAGMA, SHOW, DESCRIBE, sqlite dot-commands)
- `sample` (`SELECT * … LIMIT` with no WHERE or JOIN)
- `distinct_probe` (single-table `SELECT DISTINCT` with no WHERE)
- `dml`, `ddl`, `explain`, `other`

Metadata obtained outside SQL is counted separately: `schema_file` is a cat/grep/sed of a schema file, and `schema_tool` is a `get_table_schema` call. "Metadata" means `catalog`, `sample`, `distinct_probe`, `schema_file` and `schema_tool` together.

**Errors.**
- BIRD: sqlite `Error:` or `Parse error` in the output.
- PTBR: output starts with `SQL_ERROR`.
- TAU: output starts with `Error`.

**Retry.** An errored call that is followed by another DB call. We also report the subset where the next call is similar to the failed one (difflib ratio ≥ 0.6 on normalized text).

**Concurrency.** More than one DB tool call in a single assistant turn, meaning parallel tool calls.

## (b) Results

### 1. Read/write mix (share of SQL statements or DB calls)

| | BIRD | PTBR | TAU (API) |
|---|---|---|---|
| SQL statements / DB calls | 2,245 | 35,989 | 13,370 |
| Reads (select + probes) | 2,239 (99.7%) | 35,985 (~100%) | 10,608 (79.3%) |
| DML / writes | 0 | 0 | **2,762 (20.7%)** |
| DDL | 0 | 2 (`CREATE TEMP TABLE`) | n/a |
| Trajectories with ≥1 write | 0 | 0 | 1,542 / 1,980 (77.9%) |

- In TAU, writes per trajectory are 0: 438, 1: 808, 2: 403, 3: 219, and ≥4: 112.
- The first write comes after a median of 5 reads (mean 5.2).
- Writes sit late in the trajectory, at a mean relative position of 0.87 versus 0.40 for reads.

### 2. Errors and retries

| | BIRD | PTBR | TAU | SPTC (n=1) |
|---|---|---|---|---|
| DB-call error rate | 8 / 4,096 = **0.2%** | 3,087 / 60,711 = **5.1%** | 923 / 13,370 = **6.9%** | 6 / 25 |
| Trajectories with ≥1 error | 8 / 1,993 (0.4%) | 2,055 / 7,442 (27.6%) | 628 / 1,980 (31.7%) | 1/1 |
| Error followed by another DB call | 8/8 | 3,081 / 3,087 (99.8%) | 789 / 923 (85.5%) | 6/6 |
| …followed by a *similar* call | 6/8 | 1,696 / 3,087 (54.9%) | 352 / 923 (38.1%) | 4/6 |
| Error was the last DB call | 0 | 6 (0.2%) | 134 (14.5%) | 0 |
| Statement timeouts | 0 | 83 | — | — |

- **Error types in PTBR:**
  - column does not exist: 1,288 + 34
  - `round(double precision,…)` type error: 483
  - ambiguous column: 272
  - syntax error: 151
  - missing FROM entry: 83
  - statement timeout: 83

  These are almost all schema-hallucination or dialect errors, not engine faults. BIRD's 8 errors are all `no such column`.
- **Error types in TAU:** 530 of 923 errors are `user not found` lookups. Writes fail more often than reads: 357 / 2,762 = 12.9% versus 566 / 10,608 = 5.3%. The write failures are business-rule rejections such as "non-delivered order cannot be exchanged".
- **Per model in TAU:** GPT-4o has error rates of 7.9% (airline) and 8.8% (retail). Sonnet 3.5 has 3.4% (airline) and 7.2% (retail).

### 3. Schema/metadata probes

| | BIRD | PTBR | TAU |
|---|---|---|---|
| Metadata ops / all DB ops | 2,245 / 4,257 = **52.7%** (schema_file 47.3%, distinct_probe 5.0%, catalog 0.3%, sample 0.1%) | 29,969 / 60,732 = **49.3%** (schema_tool 40.7%, catalog-SQL 6.3%, distinct 1.5%, sample 0.8%) | 208 / 13,370 = 1.6% (`list_all_*` reference lookups) |
| Catalog SQL / SQL statements only | 14 / 2,245 = 0.6% | 3,826 / 35,989 = **10.6%** (3,772 information_schema, 54 pg_*) | n/a |
| First DB op is metadata | 1,932 / 1,992 = **97.0%** | 7,041 / 7,101 = **99.2%** | 33 / 1,945 = 1.7% |
| All metadata precedes the first data query (trajectories with both) | 1,354 / 1,378 = 98.3% | 4,527 / 6,351 = 71.3% | — |
| Mean relative position, metadata vs select | 0.07 vs 0.83 | 0.30 vs 0.69 | — |

- Where catalog traffic ends up depends on the harness. In BIRD and Spider-Agent-TC the schema is shipped as files, and the Spider-TC prompt tells the agent not to query INFORMATION_SCHEMA. Exploration therefore hits the filesystem rather than the DB: 47% of BIRD ops and 24 of 25 SPTC calls.
- When the schema is a tool or must be queried (PTBR), about 10% of the SQL itself is catalog queries, on top of a 41% share of schema-tool calls.

### 4. Concurrency (within one agent)

| | BIRD | PTBR | TAU |
|---|---|---|---|
| Assistant turns with >1 parallel DB call | 0 / 4,096 | **11,840 / 39,613 = 29.9%** | 0 / 13,370 |
| Batch-size histogram | all 1 | 1: 27,773; 2: 5,912; 3: 3,867; 4: 1,275; 5: 488; 6–11: 298 | all 1 |
| Composition of parallel turns | — | schema-only 7,004; SQL-only 4,372; mixed 464 | — |
| Calls packing >1 SQL statement | 139 / 4,096 (3.4%) | 19 | 0 |

### 5. Queries per task and redundancy

| | BIRD | PTBR | TAU |
|---|---|---|---|
| SQL per trajectory: mean / median / p90 / max | 1.13 / 1 / 2 / 11 | 4.84 / 4 / 10 / 40 | 6.75 / 7 / 11 / 24 (calls) |
| All DB ops per trajectory: mean / median | 2.15 / 2 | 8.16 / 7 | 6.75 / 7 |
| Trajectories with zero SQL | 541 / 1,993 (27%) | 341 / 7,442 (4.6%) | — |
| Exact-duplicate SQL within a trajectory | 3 / 2,245 (0.1%) | 2,765 / 35,989 (7.7%) | 239 / 13,370 (1.8%) |

- In BIRD the zero-SQL trajectories are mostly Opus 4.7 (423 of its 988), which submitted an answer after reading only the schema file. Opus 4.8 had 118. SQL per trajectory is 0.90 for Opus 4.7 and 1.36 for Opus 4.8.
- PTBR by database: `analise_dados` averages 4.76 SQL per trajectory with a 5.5% error rate; `compras_publicas` averages 5.47 with 2.1%.

### Phases (observed)

- **Text-to-SQL** follows explore, then query and refine, then answer. Metadata comes first in 97–99% of runs, and in PTBR about 29% of runs go back to metadata after their first data query.
- **Transactional agent (TAU)** follows identify the user, then read the entities (about 5 reads), then perform 1–2 writes at the end.

## (c) Caveats

- **Benchmarks, not production.** Every environment is reset per task, single-user and single-agent. There is no cross-agent or cross-session concurrency, and the databases are small.
- **Harness determines the numbers.** Schema-as-file versus schema-as-tool moves catalog traffic between the filesystem and the DB. Tool-call parallelism exists only where the API and harness allow it. We do not know whether PTBR's parallel calls actually ran concurrently against PostgreSQL.
- **Selection bias.** PTBR keeps only LLM-judged-correct trajectories, so its error and retry rates are lower bounds. BIRD consists of strong frontier models on an easy benchmark, so 0.2% errors is not general.
- **TAU is not SQL.** Its "reads" and "writes" are typed API calls over JSON state, so it is only a proxy for OLTP-style agent traffic.
- **SPTC has n=1**, so it is anecdotal only.
- **Heuristic labels.** The probe and retry labels are heuristics: "similar" means a difflib ratio ≥ 0.6. BIRD bash parsing misses about 9 piped `| sqlite3` forms.
- **No timing data.** Timestamps in BIRD are synthetic ordinals, so latency and inter-arrival times cannot be measured.

## (d) What remains unmeasured

- Real **multi-agent or multi-session concurrency** and contention (locks, conflicts) against a shared DB.
- **Write-heavy SQL agents** (DBA, ETL, migration). No DBA-Bench, ELT-Bench or Spider2-DBT run logs with SQL were found.
- **Query cost and latency:** rows scanned, plans, duration, timeouts beyond PTBR's 83.
- DDL, index and config changes made by operations agents.
- Session lifetime, connection patterns and transaction boundaries. None of the traces record BEGIN/COMMIT.
- Production telemetry of any kind.
- Retry behaviour of weak or open models on hard tasks without success filtering. The released Spider 2.0 and BIRD-Interact runs, which would cover this, are not published.
