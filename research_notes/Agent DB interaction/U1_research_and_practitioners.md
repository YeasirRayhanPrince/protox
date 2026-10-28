# U1. What LLM-agent DB traffic looks like: research and practitioner evidence (checked 2026-10-27)

Scope: read/write mix, retries, schema-probe share, concurrency, plus volume, burstiness, runaway queries and error rates. **Grades:** A = independent measurement; B = company-reported with a stated method; C = claim with no method; D = anecdote or a single issue. This note adds to D2/D3 and does not repeat their design material.

## (a) Research findings

- **Berkeley "Supporting Our AI Overlords"** (arXiv 2509.00997, CIDR 2026; https://arxiv.org/html/2509.00997)
  - **Table 1:** per-trace means over 44 sequential o3 traces (22 tasks × 2, two backends drawn from PG/SQLite/Mongo/DuckDB), without vs. with hints:
    - table exploration 3.44→2.95
    - column exploration 3.56→2.57
    - partial queries 4.28→2.71
    - full queries 1.26→1.05
    - **total SQL 12.67→10.38 (−18.1%)**
  - **Derived from Table 1 (my arithmetic, not stated in the paper):** table and column exploration make up **7.0/12.67 = 55%** of SQL per trace. Full queries are only 10%.
  - **Fig. 3** is a heatmap with independently normalized rows over normalized trace position. It has no numeric proportions. Metadata and sample probing comes first, then column statistics, then partial and full attempts. The phases overlap and every phase shows up across the whole trace.
  - About half the traces were correct.
  - **Not reported:** errors, retries, read/write mix.
  - **Parallel attempts (§2, BIRD on DuckDB, 50 attempts per problem):** distinct sub-plans are often under 10–20% of the total, and success rises 14–70% with more attempts.
  - **Throughput:** the "hundreds or thousands of requests a second" per agent figure in §1 is theoretical.
  - **Branches and rollbacks:** "20× more branches, 50× more rollbacks than humans" at Neon (§6.2) is cited to a Databricks talk, with no method.
- **BranchBench** (Columbia, 19 Apr 2026; https://arxiv.org/html/2604.17180)
  - The workloads are synthetic and parameterized. No real traces are used.
  - Table 3 implies these mutate:read ratios: Software-Dev 1:1, Data-Cleaning 2:1, MCTS 1:1, Failure-Repro and MC-Simulation 50:1.
  - Concurrency runs up to 1,000 branches, and depth up to 25.
  - Neon caps live branches at 20 and completed only 25/100 to 348/1000 steps. TigerData hit undocumented rate limits. PG CLONE blocks when the source has active connections.
- **2608.15127** (https://arxiv.org/html/2608.15127v1, §7)
  - A one-day production trace from an unnamed company: 178,799 sessions across coding (35,037), search-QA (141,376) and OpenClaw-like (2,386) agents.
  - Search-QA averages about 2.6 search calls per session.
  - 27% of distinct search queries recur, and they account for 67.3% of calls.
  - Idle gaps are mostly 1–10 minutes.
  - **No SQL tool appears, and errors, retries and concurrency are not reported.**
- **2509.02121** (Shen, Wadlom, Lu; v2 Jan 2026; https://arxiv.org/abs/2509.02121)
  - Batch LLM-plus-query optimization: up to 3.6× faster batch inference and 2.6× online throughput.
  - The abstract quantifies no agent query workload. I could not access the full text.
- **Production NL2SQL reports** carry almost no traffic metrics:
  - **LinkedIn SQL Bot** (Dec 2024; https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics) reports "hundreds" of users and that "Fix with AI" is 80% of sessions. That is an error→fix share per session, and the closest thing to a retry signal. It gives no query counts.
  - **Uber QueryGPT** (https://www.uber.com/blog/query-gpt/) gives 1.2M interactive queries/month on the platform, which is human traffic and not QueryGPT's.
  - **Vercel d0** (22 Dec 2025; https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools): about 12 steps per question with the old 17-tool agent and about 7 with bash. Its worst case was **100 steps, 724 s and 145k tokens, then failure**. The benchmark has only 5 questions.
  - **ClickHouse DWAINE** (27 Mar 2026; https://clickhouse.com/blog/building-a-data-platform-for-agents) handles about 70% of internal DWH questions for more than 250 users and over 200 messages a day. Those are messages, not SQL.
  - **OpenAI's data agent** page returned 403.
- **The only production agent-vs-human SQL comparison** is MotherDuck, "Agents Don't Query Like Humans Do" (2026; https://motherduck.com/blog/agents-dont-query-like-humans-do/).
  - **Method:** agent = queries written through the MCP server, human = queries written in the UI. Volume covers 3 months and segmentation 2 weeks. N is not given.
  - **Volume:** agents ran 6×, 16× and 29× as many queries as humans in successive months, and orgs have about 2× as many agents as humans.
  - **Gaps and size:** the median inter-query gap is **4 s for agents vs. 60 s for humans**, and agent traffic is "far burstier", unquantified. The median query scans **7K rows for agents vs. 200K for humans**.
  - **Schema reads:** "many" agent queries read schemas, with **no share given**.

## (b) Practitioner findings, by symptom

**Query floods and loops**
- A Copilot agent session made 224 identical `view` calls in one turn. The same issue reports agents re-running identical SQL within a turn because results were not cached. (https://github.com/github/app/issues/594, 31 May 2026)
- Percona's CEO (Percona Live, via The Register/Stacker News; https://stacker.news/items/1575981) gave an example of about 150 attempts before a winner is picked. That is an illustration, not a measurement.
- ClickHouse says "Agents fire 10 to 100x the volume of queries a human analyst would, in bursts" (9 Jun 2026; https://clickhouse.com/blog/clickhouse-agents-beta). No method is given.

**Retries**
- In nao, one agent-written BigQuery join with `OR` in its ON clause ran for **78 minutes and about 1,500 slot-hours**. It blocked the async handler, every later `execute_sql` timed out, and "the model retries" until the 300 s request cap. (https://github.com/getnao/nao/issues/1896, 13 Oct 2026)
- In one week of logs from a non-DB MCP gateway, **27.6% of 1,579 calls** errored, mostly from argument validation and upstream 429s (r/mcp, May 2026; https://reddit.sentinel-team.org/posts/1t9h2fp/snapshots/2026-05-15T23%3A42%3A01.04912Z).

**Connection and pool exhaustion.** The main cause is leaked MCP server processes. Agent query rate is not what drives it.
- **postgres-mcp:**
  - #98 (Jul 2025): a new pool per SSE client, with numbering reaching pool-67.
  - PR #177 (Jun 2026): orphaned stdio servers each pin `min_size=1` and exhaust the role limit, "FATAL: too many connections for role".
  - #175 (May 2026): 88 orphaned containers after a few weeks.
  - #194 (Aug 2026): the server does not exit on stdin EOF.
  - (https://github.com/crystaldba/postgres-mcp/issues/98, /pull/177, /issues/175, /issues/194)
- **mongodb-mcp-server** PR #1528 (Sep 2026): the sessionless redesign left pools with no bound, so an idle reaper was added. (https://github.com/mongodb-js/mongodb-mcp-server/pull/1528)
- **mcp-toolbox** #2243 (Dec 2025): a hardcoded pool size blocks "Agentic AI concurrency". (https://github.com/googleapis/mcp-toolbox/issues/2243)
- **sql-fs** #123 (Jun 2026): pool max 2 per session with no global cap means about 48 concurrent agent sandboxes exhaust `max_connections=100`. (https://github.com/Hazzng/sql-fs/issues/123)

**Schema-introspection storms**
- The typical tool sequence is list_schemas → list_tables → describe_table.
- A user with a 120+ table SaaS says discovery cost is the bottleneck (https://community.openai.com/t/what-do-you-use-to-keep-your-coding-agent-oriented-in-a-big-postgres-schema/1384057).
- AWS Redshift MCP PR #4552 (Aug 2026) paginated "discovery" tools and capped them at 1,000 rows (https://github.com/awslabs/mcp/pull/4552).
- I found no counts.

**Runaway queries**
- The nao 78-minute case above.
- Mongo MCP #829 (Jan 2026) asks for a `maxTimeMS` default of 30 s because "AI-generated queries may unintentionally cause collection scans" (https://github.com/mongodb-js/mongodb-mcp-server/issues/829).
- dbhub PR #465 adds a server-side `query_timeout` (https://github.com/bytebase/dbhub/pull/465).

**Write surprises and state leaks**
- In dbhub's read-only mode, `SELECT set_config('statement_timeout','0',false)` is allowed and persists on the pooled connection (#448, Oct 2026; https://github.com/bytebase/dbhub/issues/448).
- In postgres-mcp, session GUCs and HypoPG indexes leak across requests through the pool (#203, Aug 2026; https://github.com/crystaldba/postgres-mcp/issues/203).
- Destructive incidents (Replit, PocketOS) are covered in C_orgs and came through the control plane, not SQL volume.

**DBA blogs (Brent Ozar, Percona, Crunchy, pganalyze)**
- I found no measured report of agent traffic.
- pganalyze's webinar argues against giving agents live DB connections (https://pganalyze.com/webinars/optimizing-postgres-with-claude-code-and-mcp-server).
- Databricks Storex rate-limits agent query bursts so they cannot starve alerting (https://www.databricks.com/blog/how-we-debug-1000s-databases-ai-databricks). That is a stated control with no figures.

## (c) Evidence tables

**1. Read/write mix**

| Data point | Context | Grade |
|---|---|---|
| Full queries 10%, exploration 55%, all reads (Table 1; my arithmetic) | Lab, 44 traces | A (small n) |
| Mutate:read 1:1 to 50:1 | BranchBench, synthetic parameters | C (assumed, not observed) |
| BIRD-Interact 68% BI / 32% DM tasks (see D_latent) | Benchmark design | C |
| "Read early, write late" (2605.26297 abstract) | Lab | A/C (abstract only) |
| Production read/write mix | none found | — |

**2. Retries and failed-then-retried**

| Data point | Context | Grade |
|---|---|---|
| "Fix with AI" in 80% of sessions | LinkedIn production | B (session share, not retry rate) |
| Worst case 100 steps → fail; mean 12 steps | Vercel, 5-question benchmark | B (tiny n) |
| Model retried after timeouts until the 300 s cap | nao issue #1896 | D |
| 27.6% call error rate (non-DB MCP) | r/mcp gateway logs | D |
| About 150 attempts per task | Percona CEO | C |
| Retries/errors in 2509.00997 and 2608.15127 | not reported | — |

**3. Schema/catalog probe share**

| Data point | Context | Grade |
|---|---|---|
| 7.0 of 12.67 SQL per trace are table or column exploration (55%) | 2509.00997 Table 1, lab | A (small n, one model) |
| Hints cut column exploration 27.7% and table exploration 14.2% | same | A |
| "Many" agent queries read schemas | MotherDuck production | B (no share) |
| list_schemas→list_tables→describe as the norm; large-schema pain | practitioners | D |

**4. Concurrency and pools**

| Data point | Context | Grade |
|---|---|---|
| About 2× as many agents as humans per org; one org's agent count is 7× the largest human headcount | MotherDuck production | B |
| 88 orphaned MCP containers; role connection limit exhausted | postgres-mcp #175/#177 | D |
| About 48 sandboxes exhaust 100 connections | sql-fs #123 stress test | D |
| Hardcoded pools block agent concurrency | mcp-toolbox #2243 | D |
| "Thousands of concurrent queries" | ClickHouse | C |
| 1,000 concurrent branches; Neon caps at 20 | BranchBench | A (synthetic) |

**5. Volume, burstiness, runaway queries, errors**

| Data point | Context | Grade |
|---|---|---|
| 6→16→29× human query volume; 4 s vs 60 s median gap; 7K vs 200K rows | MotherDuck production | B |
| "10–100× human volume, in bursts" | ClickHouse | C |
| 67.3% of search calls are repeats (non-SQL) | 2608.15127 production | A/B (unnamed company) |
| 10–20% distinct sub-plans across 50 attempts | 2509.00997 lab | A |
| 78-minute, 1,500 slot-hour runaway | nao #1896 | D |
| 20× branches, 50× rollbacks vs humans | Neon via 2509.00997 | C |

## (d) What remains unmeasured

1. **No production read/write mix** for agent SQL from any source.
2. **No retry rate or error rate** for agent SQL in production. LinkedIn's 80% is a session-level feature share, not an error rate.
3. **No production schema-probe share.** The only number, 55%, comes from 44 lab traces on small schemas, so it may grow with schema size, and that is untested.
4. **No connection-count or pool-occupancy measurements under agent load.** All the exhaustion evidence is leak bugs, not query pressure.
5. **No multi-agent-per-DB contention data** (locks, conflicts, interference).
6. **No distributions** (p99 runtime, burst peak QPS, queries per session) from any production DB. MotherDuck gives medians only, and N is undisclosed.
7. **No company NL2SQL report** (Uber, LinkedIn, Pinterest, OpenAI, Airbnb, Grab, Shopify) gives SQL statements per question, timeouts, or cancelled queries.
8. **I found no MCP usage-log study of DB servers.** 2608.15127 has no SQL tools.
