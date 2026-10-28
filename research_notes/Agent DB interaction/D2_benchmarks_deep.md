# D2: Agent benchmarks that use the database as the tool (deep pass)

Builds on `D_latent_and_db4agents.md` and does not repeat it. [preprint] means arXiv or not yet reviewed. Codes: 1 Who · 2 Interface · 3 Guardrails · 4 Agent→DB · 5 DB→agent · 6 Aftermath · 7 Over time. "n/r" means the paper does not report it.

## 0. DBA-Bench numbers, resolved

Source: https://arxiv.org/html/2607.22165 [preprint]. Safe Pass means Outcome Pass with zero safety risk. It is the paper's primary endpoint (§5.2, §6.1.1).

- **27.1% is the best automated Safe Pass on PostgreSQL**, from DBAIOps (§1, §6.2). Opus 4.8 has 26.2% and GPT-5.5 ReAct has 22.4%. **The TiDB best is 21.0%** (Opus 4.8). The paper gives no single number pooled across engines.
- **The human DBA scores 92.5% on PostgreSQL (99/107) and 91.9% on TiDB (114/124)** (§6.2). Table 2 splits this as PG 94.7/90.0 and TiDB 95.5/90.0 for Easy/Hard. **93.4% does not appear in the paper.** Pooled, the human figure is 213/231 = 92.2%.
- **17.9% does not appear in the paper.** The nearby numbers are 17.3% (PG) and 16.1% (TiDB). These are the **shares of outcome-passing runs that then fail Safe Pass**, so they are safety failure rates, not Safe Pass rates (§6.4). A second, unrelated figure is the pooled automated Safe Pass, which falls from 20.6% to 10.0% on PG and from 18.5% to 8.6% on TiDB going from Easy to Hard (§6.2, Table 2).
- **Correction to the prior note's "72%":** 72.2% (PG) and 71.6% (TiDB) of diagnosis-passing runs fail Outcome Pass (§6.2).

## (a) Per-benchmark blocks

**DBA-Bench** [preprint] (https://arxiv.org/html/2607.22165)
- 2 Interface: five tools (§3.3.2). Metrics, logs and KB calls only observe. `execute_sql` and `manage_instance` change state.
- 3 Guardrails: safety is **scored after the run, not enforced during it**. S1 is protected objects, S2 is intervention scope, S3 is operational safeguards (§3.3.2, §6.4).
- Contract: 231 bounded tasks on live PG and TiDB. The dirty snapshot is restored after each run (§3.2, §4.1). Turn caps are 50 for ReAct and DBAIOps and 150 for D-Bot. The context window is about 262K tokens with compaction. There is no per-run cost cap. D-Bot costs 9.6× ReAct on PG (§6.1, §6.5).
- 6 Aftermath: S1 is the dominant violation on PG (137/168 S-labelled runs). On TiDB S2 dominates (81/136) (§6.4). The two largest failure labels are "incomplete required actions" (21.7% PG, 25.0% TiDB) and "omitted decisive evidence" (20.3%, 24.9%) (§6.3.1, Fig. 5).
- 7 Over time: in 1–2 h persistent sessions, Safe Pass is 2/40 and Outcome Pass is 3/40 (§6.6). "Earlier verification does not establish completion after the later event." In one run a later release re-broke a placement policy, and another run reported completion while deadlines were missed (§6.6.2).
- The paper reports no trajectory statistics such as call counts or write share.

**BIRD-Interact** (https://arxiv.org/html/2510.05318)
- 2 Interface: 9 priced actions (App. J). These are `execute`, `get_schema`, and `get_all_column_meanings` at cost 1, column-meaning and knowledge lookups at 0.5–1, `ask` at 2, and `submit` at 3. The budget is B = 6 + 2·m_amb + 2·λ_pat (§4.2).
- 4 Agent→DB: 600 Full tasks, 410 BI and 190 data-management (DM, i.e. writes) (Table 1). A fresh PG14 Docker is used per run (Reproducibility).
- 7 Over time: about 7.5–7.8 turns on average (Table 4). Actions mix differently by model (App. J.3). GPT-5 splits about 47% probes and 52% ask+submit. O3-mini sends about 91% of actions to the user and only 4% to `execute`. **Execute share correlates negatively with success (r≈−0.52).** Strong agents explore and clarify early, then execute and submit (App. J.3).
- Failures: over 80% of 50 sampled failures come from incomplete ambiguity resolution. Agents ask about once per task while tasks contain about 4 ambiguities (App. M). DM (write) tasks score higher than BI, for example 56.2% vs 22.1% on Lite (Table 10).
- Results: best end-to-end is ≤17.0% (aa-Interact) (§5.1, Table 2).

**BIRD-Critic / SWE-SQL** (https://arxiv.org/html/2506.18951v2, NeurIPS'25)
- 4 Agent→DB: 530 PG tasks taken from StackOverflow bug-fix threads. 291 are query, 88 management, and 151 personalization (Table 1). One Docker container per DB (App. A.1).
- 2 Interface: in SQL-Act, each action is arbitrary SQL. Tool-Act offers schema, sample, and solution (§5.1, App. H.3).
- 6 Aftermath: success requires passing all test scripts. Query tasks are checked by result-set comparison, management tasks by expert state checks (App. C, D).
- Failures over 100 PG fails, overlapping (§ error analysis): incorrect logic 44.5%, syntax 29.3%, **chain of errors 27.3%**, projection mismatch 26.9%. Adding file read/write workflows cut success from about 30% to 10% (App. I).
- Results: O3-mini scores 38.87% on PG and 33.33% on Multi.

**Spider 2.0** (https://arxiv.org/html/2411.07763)
- 2 Interface: Spider-Agent has BASH, CreateFile, EditFile, ExecuteSQL, GetTables, GetTabInfo, SampleRows, FAIL, and Terminate (Table 18).
- Contract: 30 steps max. A run stops after 3 identical outputs or after any action longer than 120 s (App. C.1).
- 7 Over time: solved tasks average **9.0 steps (range 6–17)** (App. C). In the case studies the agent debugs a DATE-vs-INT64 error until the query runs (App. C.6).
- Failures (300 samples, Fig. 5): erroneous data analysis 35.5% (dialect 10.3, calculation 7.5, planning 17.7). Wrong schema linking is 27.6% (column 16.6, table 10.1). JOIN errors are 8.3%.
- Results: SR is 21.36% for o1-preview (Table 5). Nested columns drop SR to 10.3% and external docs to 11.5% (Tables 6–7).

**DA-Code** (https://arxiv.org/html/2410.07331v2, EMNLP'24)
- 2 Interface: Bash, Python, SQL(file), and Terminate (§4.2).
- Contract: 20 steps, a 15-step history window, and a 300 s timeout per action (§5.1). Data Wrangling, including SQLite loads, is 100 of 500 tasks (Table 2). Scoring compares output files (§3.3).
- 7 Over time: agents follow an **Exploration → Execution → Evaluation → Adjustment** pattern. Success plateaus after 5–10 steps (Fig. 5–6).
- Failures (no percentages): hallucinated file names or SQL run without exploring, format errors, debug loops, and premature termination (§5.4).
- Results: GPT-4 scores 30.5%.

**AgentBench DB** (https://arxiv.org/html/2308.03688)
- 2 Interface: one single-line SQL statement per round, then `Action: Answer` (App. C.3). MySQL runs in Docker, initialized from an SQL script per problem (App. C.1).
- 6 Aftermath: SELECT tasks are scored on the answer. **INSERT and UPDATE tasks are scored by hashing the resulting table** against the gold execution (App. C.1). About 5 rounds are expected per task (Table 2).
- Failures: Invalid Format 53.3%, Completed 37.9%, Task Limit 8.0% (Table 4).
- Results: Claude-3 Opus 51.7 and GPT-4 32.0 (Table 3).

**τ-bench / τ²-bench** (https://arxiv.org/html/2406.12045; https://arxiv.org/html/2506.07982 [preprint])
- 2 Interface: domain APIs over a hidden JSON database. Retail has 7 write and 8 read tools. Telecom has 6/7 for the agent and 15/15 for the user (Table 1 in each paper).
- 6 Aftermath: reward is (final DB equals goal DB) × (required info was output) (§3). The authors note r=1 is necessary but not sufficient, because a confirmation-policy breach can still match the goal DB.
- Failures (τ, gpt-4o retail, 36 failures; §5.2): wrong decision or rule-following about 25%, partial resolution of compound writes about 19%, and wrong argument/info as the remainder (the percentage is garbled in the HTML). **Failures rise with the number of gold write actions** (Fig. 6).
- 7 Over time: gpt-4o's pass^8 is below 25% against pass^1 of 61.2% (§5.1). In τ², when the user also mutates state, pass^1 drops about 18–25% (§4.2). Telecom tasks need 2.3–6.0 actions on average (Table 4).

**ELT-Bench** [preprint] (https://arxiv.org/html/2504.04808)
- Interface: Snowflake + Airbyte (Terraform) + dbt, with PG, Mongo, and S3 sources (§2.3). Spider-Agent gets 100 steps and SWE-Agent a $6 budget (§3.2).
- Results: best SRDT is **3.9% at 89.3 steps and $4.30** (Table 4).
- Trajectories:
  - Agents that read docs first succeed 78.8% of the time, against 9.6% for those that write config first (Fig. 7).
  - **Re-triggering the same sync inflated row counts in 12 tasks** (Fig. 9).
  - Stage-2 failures break down as excessive iterations 28.7%, wrong SQL logic 24.3%, and invalid actions 21.7% (§5).
  - Spider-Claude's semantic errors are mostly "incorrect schema" (15 of 26) (§4.3).
  - pass@5 is 57% while pass^5 is 0 (§6).

**Terminal-Bench 2.0** [preprint] (https://arxiv.org/html/2601.11868v1)
- 89 tasks. Tests check the final container state (§2.1). The best result is 62.9% (Codex/GPT-5.2) (Table 2).
- Only one DB task appears in the visible list: `db-wal-recovery`, which recovers 11 records from a corrupt SQLite WAL (App. H). An unsolved "database migration" frontier category is also mentioned (Fig. 11).
- Failures: command error rates run 9.2–26.7%. The top cause is a missing executable (24.1%) (§4.5). Taxonomy labels include "no/irrelevant verification" and "premature termination", without per-category rates (App. C).

**SWE-bench-style DB work:** no benchmark-wide failure analysis of DB or migration tasks was found. Anecdotes include RigorBench DBB-1 (raw SQL → ORM; https://arxiv.org/pdf/2606.22678 [preprint]) and a paraphrase making django-16819 flip from pass to fail (https://arxiv.org/pdf/2605.10516 [preprint]).

**LLM index tuning on SQL Server (VLDB'26)** (https://arxiv.org/html/2603.09181v1)
- Not an agent loop: there is one prompt with SQL, schema, and showplan, and no what-if calls (§2.3.1).
- Validation is 5 runs × 300 s cap, taking the median (§2.2.2). Validation cost exceeds tuning cost, mainly from index builds (§6.2).
- **Worst-of-5 runs regress or time out** on TPC-H q20 and on Real-D/R/M (§3.4).
- Adding LLM candidates to DTA degraded **44/127 queries (35%) by at least 5%** (Table 3).

## (b) Interaction statistics across benchmarks

| Benchmark | Turn budget | Observed turns/steps | DB calls per task | Write share | Best success |
|---|---|---|---|---|---|
| DBA-Bench | 50 / 150 | n/r | n/r | writes allowed (2 of 5 tools) | 27.1% PG / 21.0% TiDB Safe Pass; human 92.5 / 91.9 |
| BIRD-Interact | cost budget B | 7.5–7.8 turns | about 47% probes (GPT-5) | 32% DM tasks | ≤17.0% end-to-end |
| BIRD-Critic | n/r | n/r | n/r | 45% mgmt + personalization | 38.9% PG |
| Spider 2.0 | 30 | 9.0 (solved) | n/r | dbt/file writes | 21.4% |
| DA-Code | 20 | plateau at 5–10 | n/r | 20% DW | 30.5% |
| AgentBench DB | n/r | about 5 rounds | 1 SQL per round | INSERT and UPDATE subsets | 51.7 |
| τ-bench retail | n/r | n/r | n/r | 7 of 15 tools | 61.2 pass^1, <25 pass^8 |
| ELT-Bench | 100 / $6 | 89.3 | n/r | all (load + dbt) | 3.9% |
| Terminal-Bench 2 | time limit | n/r | n/r | n/a | 62.9% |
| 2509.00997 (prior) | n/a | n/a | 12.7 SQL per trace | n/a | n/a |

## (c) Consolidated failure taxonomy, agent–DB

1. **Grounding: wrong schema, table, or column.**
   - Spider 2.0: 27.6% wrong schema linking.
   - ELT-Bench: "incorrect schema" is 15 of 26 failures.
   - BIRD-Critic: projection mismatch 26.9%.
   - DA-Code: hallucinated files and SQL run without exploring, no percentage.
2. **Logic and dialect.** Spider 2.0 erroneous analysis is 35.5% (dialect 10.3%). BIRD-Critic incorrect logic is 44.5% and syntax 29.3%.
3. **Under-exploration or under-clarification.** BIRD-Interact attributes over 80% of failures to unresolved ambiguity. DBA-Bench "omitted decisive evidence" is 20–25%.
4. **Incomplete action, stopping early.** DBA-Bench incomplete actions are 22–25%. τ-bench partial resolution is about 19%. In DBA-Bench, 72% of correct diagnoses do not yield a fix.
5. **Policy or safety violation.** DBA-Bench: 16–17% of successful runs are unsafe, with S1 dominant on PG and S2 on TiDB. τ-bench rule-following is about 25%.
6. **Non-idempotent or repeated writes.** ELT-Bench double sync inflated counts in 12 tasks. τ-bench has one-shot write locks.
7. **Error cascades and loops.** BIRD-Critic chain of errors 27.3%. ELT-Bench excessive iterations 28.7%. DA-Code debug loops, no percentage.
8. **Protocol or format.** AgentBench DB Invalid Format 53.3%. ELT-Bench unparsable actions 47% for Spider-Claude-3.5.
9. **Not verifying, regression over time.** DBA-Bench "unclosed verification loop" and persistent Safe Pass 2/40. Terminal-Bench "no/irrelevant verification", no percentage.
10. **Unreliability across runs.** τ pass^8 is below 25%. ELT-Bench pass^5 is 0. LLM index-tuning worst-of-5 runs regress.

## (d) Patterns

- **Phases are consistent across benchmarks.** Agents explore metadata and docs, then execute, evaluate, and adjust (DA-Code Fig. 6; BIRD-Interact App. J.3; ELT-Bench Fig. 7). Order matters: docs-first succeeds 78.8% vs 9.6% for config-first, and too much early `execute` hurts (r≈−0.52).
- **Diagnosis is easier than repair, and repair is easier than safe repair.** DBA-Bench shows a 72% drop from diagnosis to outcome, then a further 17% loss to safety.
- **Success is judged by final state almost everywhere:** table hash (AgentBench), goal DB (τ), test scripts (BIRD, Terminal-Bench), and outcome plus safety (DBA-Bench). No benchmark scores the path the agent took. τ notes that a matching final state can hide policy breaches.
- **pass@k and pass^k diverge sharply,** which is the reliability gap: ELT-Bench 57% vs 0, τ 61% vs <25%.
- **Each extra required write lowers success** (τ Fig. 6; τ² Fig. 5).

## (e) What benchmarks do not capture, compared with production

1. **Resets are always available.** Every benchmark resets per task with Docker, snapshot, or fresh PG. Production is one live, fixed system with no reset. Only DBA-Bench's 10 persistent runs test without resets, and they score 2/40.
2. **Full observability is assumed.** Benchmarks give the whole schema and data, or a bounded scenario. None models partial workload visibility, such as only sampled queries or telemetry lag.
3. **Zero regression is never the objective.** Success is "target reached". DBA-Bench's safety rules cover protected objects and scope, not performance regressions on other queries. The SQL Server study shows that is where LLM tuning hurts: 35% of queries degraded, and worst-of-5 runs time out.
4. **No gate before execution.** Safety is scored afterwards, and destructive actions actually run.
5. **No concurrent or competing workload at scale,** and no swarms of agents sharing one DB.
6. **No cost of validation.** Index builds dominate in the SQL Server study, but benchmarks charge only for tokens.
7. **Short horizons.** Budgets are 20–150 steps. Drift over days or weeks and model updates are untested.
8. **No trajectory-level DB statistics.** No benchmark reports DB calls per task or read/write mix. The only figure is the 12.7 SQL per trace from 2509.00997.
