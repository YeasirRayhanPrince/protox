# U1: Agent DB traffic as seen in platform/vendor telemetry

Searched 2026-10-27. Scope: published numbers from data platforms that can see agent traffic on their own service. No design advice.

**Bottom line:** Only **one** public source, MotherDuck, gives query-level statistics that separate agent traffic from human traffic: inter-arrival time, rows scanned and volume ratio. Every other vendor publishes **provisioning-level** numbers (databases or branches created by agents, compute lifetime) or **adoption** numbers (users, tokens). No vendor has published read/write mix, retry rates, schema-probe share, error rates, per-agent concurrency or query duration for agent traffic.

## (a) Per-source blocks

**S1. MotherDuck, "Agents Don't Query Like Humans Do"** ([post](https://motherduck.com/blog/agents-dont-query-like-humans-do/); dated 2026-09-02 per the [API Evangelist repost](https://blogs.apievangelist.com/blogs/motherduck-2026-09-02-agents-don-t-query-like-humans-do/); no byline in the text)
- **How agent traffic was identified:** by channel. Queries sent through MotherDuck's **MCP server** count as "agent"; queries written in the **MotherDuck web UI** count as "human". The post calls this "the most consistent way to segment with a high degree of confidence."
  - Queries from the API, CLI, JDBC, BI tools and so on are in neither group.
  - Agents that connect without the MCP server are therefore counted as neither agent nor human.
- **Window:** "a two week period" for the distribution stats. The volume ratios are per month, for "the last month" and the two months before it.
- **Sample size:** no absolute query, user or org counts are given.
- **Numbers:**
  - Agents ran **29× more queries** than humans last month. The monthly ratio went **6× → 16× → 29×**.
  - Humans issued more queries than agents in January; agents overtook them in **February**.
  - Orgs have on average **2× as many agent users as human users**. What counts as an "agent user" is not defined.
  - The org with the most agent users has **7×** as many agents as the org with the most humans has humans.
  - **Median delay between queries: 4 s for agents vs 60 s for humans.** The post does not say whether this is per user, per session or global.
  - **Median rows scanned: 7,000 for agents vs 200,000 for humans.** The post notes a tail of large agent queries but gives no percentiles.
  - **Schema reads:** "many agent queries are acquiring context and metadata by reading table schemas." This is qualitative; no share is given.
  - **Concurrency:** agents are called "highly parallel", but no number is given.
- **Not reported:** read/write mix, errors, retries, query duration, connections.
- **Grade:** **B−**. It is vendor telemetry and the segmentation method is stated, but there are no sample sizes, no metric definitions and no percentiles. MotherDuck sells an agent-facing product.

**S2. Databricks/Neon acquisition blog** ([2025-05-14](https://www.databricks.com/blog/databricks-neon))
- 30% of Neon databases were created by agents at Neon's GA (2024). This later rose to over 80%, described as "4× more" than humans.
- The method is only that Neon "looked at their stats." The way agent-created databases were attributed is not described. Neon's [use-case page](https://neon.com/use-cases%2Fai-agents) repeats "80%".
- **Grade:** **C**.

**S3. Databricks, "State of AI Agents 2026"** ([PDF](https://www.databricks.com/sites/default/files/2026-01/State-of-AI-Agents-2026-Final.pdf); summarized by [SaaStr](https://www.saastr.com/databricks-only-19-of-organizations-have-deployed-ai-agents-but-theyre-already-creating-97-of-databases/))
- **Numbers:**
  - 80% of databases are built by agents. SaaStr reports this as 0.1% of Neon databases in Oct 2023 rising to 80% in Oct 2025.
  - 97% of "testing and dev environments" are built by agents. SaaStr calls these "branches."
- **Window:** 2024-11-01 to 2025-10-31.
- **Sample:** "20,000+ organizations." It is unclear whether the Neon figures come from that same sample.
- **Classification:** how databases were classified as agent-created is not stated.
- **Grade:** **C**.
- I could not text-extract the PDF; the figures are confirmed via the search summary and SaaStr.

**S4. Lakebase VLDB paper** ([PVLDB vol. 19, p. 4385](https://www.vldb.org/pvldb/vol19/p4385-pandis.pdf), Databricks authors)
- **Numbers:**
  - "more than 10 million databases daily," with agents "creating roughly 4× more databases than human users."
  - Fig. 1, compute lifetime: "many production database instances stay active for under 10 seconds."
  - Fig. 2, branch depth: "some exceeding 500 branches."
  - Compute startup is "typically under a second." The paper also says agents "may create many branches per prompt" and that "the agent platform starts a new compute in response to each user prompt."
- **Not agent-segmented:** the lifetime and branch-depth figures cover the whole fleet; they are not split by agent vs human.
- **Grade:** **B−**. It is a peer-reviewed venue, but the data is the vendor's own and the attribution method is not given.

**S5. Supabase**
- **[Wrapped 2025](https://supabase.com/wrapped)**
  - The top MCP tools, ranked by usage: `execute_sql` > `apply_migration` > `list_tables` > `list_migrations`. The percentages did not render.
  - Cursor plus Claude Code make up 50% of MCP users.
- **[Turso acquisition post](https://supabase.com/blog/supabase-is-acquiring-turso.md)** (2026-10-02): over 1M databases launched per week; "agents are spinning up millions of databases."
- **Unconfirmed agent shares:**
  - "60%+ of new databases" spun up by AI coding agents is a [Sacra](https://sacra.com/research/supabase-170m-year-growing-221-yoy/) estimate.
  - "~70%" appears only in [Tech Insider](https://tech-insider.org/supabase-150m-turso-acquisition-agent-database-2026/).
  - Neither number appears in Supabase's own post.
- **Grade:** **C** for the tool ranking (MCP is how agents are identified, but no values are shown). **D** for the 60% and 70% figures.

**S6. ClickHouse**
- **[Agents beta](https://clickhouse.com/blog/clickhouse-agents-beta)** (2026-06-09):
  - Agents produce "10 to 100× the volume of queries a human analyst would," arriving "in bursts". No method is given. The [Open House Day 1 post](https://clickhouse.com/blog/open-house-2026-day-1) says the same.
  - Internal LibreChat: about 80% of employees use it daily; about 70% of internal warehouse queries go through it; more than 45M tokens a day.
- **[Data platform for agents](https://clickhouse.com/blog/building-a-data-platform-for-agents)** (Al Brown, 2026):
  - DWAINE has more than 250 users and more than 200 messages a day, and handles about 70% of warehouse questions.
  - Agents are described qualitatively as "sometimes runs unnecessarily expensive queries."
- **Grade:** **C**.

**S7. Snowflake**
- Snowflake Intelligence is used by over 2,500 accounts ([Q4 FY26 call](https://www.roic.ai/quote/SNOW/transcripts/2026-year/4-quarter)). That is adoption only.
- **Grade:** **C**.

**S8. Databricks Genie**
- Over 1.5M Genie Spaces have been created in 2026, per a secondary source ([Refonte](https://www.refontelearning.com/blog/databricks-genie-upgrade-business-analysts)).
- **Grade:** **D**.

**S9. Other sources**
- **Turso:** CTO.new runs "tens of thousands" of databases, one per project ([Turso](https://turso.tech/blog/cto-new-coordinates-tens-of-thousands-of-ai-agents)). The "trillions of databases" figure is a forecast ([AI Council talk](https://www.aicouncil.com/talks/agents-will-need-trillions-of-databases-lets-give-it-to-them)). **Grade:** C/D.
- **Xata:** one developer now runs "50+ environments instead of 3" ([Xata](https://xata.io/solutions/ai-teams)). **Grade:** C.
- **Neon blogs:** the [agent-platforms](https://neon.com/blog/neon-for-agent-platforms) and [invisible-database](https://neon.com/blog/the-invisible-database-running-postgres-at-runtime) posts state requirements such as "thousands of DBs/day" and "sub-second" provisioning. These are not measurements.
- **Tinybird:** MCP requests are tagged `from=mcp` in `pipe_stats_rt` ([docs](https://www.tinybird.co/docs/forward/analytics-agents/mcp)). That is an identification mechanism, but no data has been published.
- **Datadog** ["State of AI Engineering 2026"](https://investors.datadoghq.com/news-releases/news-release-details/ai-hitting-operational-limits-companies-rush-scale-datadog):
  - About 5% of LLM requests fail, about 60% of those because of capacity limits.
  - These are *model* calls, not database queries.
  - **Grade:** B for LLM calls; not applicable to databases.
- **DataDome** ([Q2 2026](https://datadome.co/threat-research/ai-traffic-report-q2-2026/)): MCP traffic peaks near 500k requests per day. This is web traffic, not database traffic.
- **Searched with no agent-DB numbers found:** PlanetScale, Convex, Cloudflare D1/Hyperdrive, BigQuery Conversational Analytics, MongoDB, Redis, Elastic, Pinecone, pganalyze, Grafana, New Relic.

## (b) Tables by dimension

**Read/write mix**
| Data point | Source | Grade |
|---|---|---|
| Top Supabase MCP tools: execute_sql > apply_migration > list_tables > list_migrations (rank only; `apply_migration` = DDL write) | [Supabase Wrapped](https://supabase.com/wrapped) | C |
| No agent read/write ratio published by any vendor | n/a | n/a |

**Retries / failed-then-retried**
| Data point | Source | Grade |
|---|---|---|
| None published for DB queries | n/a | n/a |
| ~5% of LLM (model) requests fail; ~60% of those are capacity failures. Adjacent, not database data | [Datadog](https://investors.datadoghq.com/news-releases/news-release-details/ai-hitting-operational-limits-companies-rush-scale-datadog) | B (for LLM calls) |

**Schema / catalog probes**
| Data point | Source | Grade |
|---|---|---|
| "many agent queries are… reading table schemas" (no share given) | [MotherDuck](https://motherduck.com/blog/agents-dont-query-like-humans-do/) | C |
| `list_tables` is the #3 Supabase MCP tool (rank only) | [Supabase Wrapped](https://supabase.com/wrapped) | C |

**Concurrency / agents per DB**
| Data point | Source | Grade |
|---|---|---|
| 2× agent users vs human users per org; top org has 7× | MotherDuck | B− |
| A new compute per user prompt; "many branches per prompt" | [Lakebase PVLDB](https://www.vldb.org/pvldb/vol19/p4385-pandis.pdf) | B− (qualitative) |
| Per-agent parallel sessions or connections | none | n/a |

**Volume / burstiness / provisioning churn**
| Data point | Source | Grade |
|---|---|---|
| Median inter-query gap: 4 s (agent) vs 60 s (human) | MotherDuck | B− |
| Agent:human query ratio 6× → 16× → 29× per month | MotherDuck | B− |
| Agents issue 10–100× the queries of a human analyst, "in bursts" | [ClickHouse](https://clickhouse.com/blog/clickhouse-agents-beta) | C |
| More than 10M databases a day; agents create about 4× more than humans | Lakebase PVLDB | B− |
| Many instances are active for under 10 s; some have more than 500 branches (fleet-wide, not agent-only) | Lakebase PVLDB | B− |
| 30% → over 80% of Neon databases agent-created | [Databricks](https://www.databricks.com/blog/databricks-neon) | C |
| 80% of databases and 97% of dev/test environments built by agents | [State of AI Agents](https://www.databricks.com/sites/default/files/2026-01/State-of-AI-Agents-2026-Final.pdf) | C |
| Over 1M Supabase databases a week | [Supabase](https://supabase.com/blog/supabase-is-acquiring-turso.md) | C |

**Query size / duration**
| Data point | Source | Grade |
|---|---|---|
| Median rows scanned: 7,000 (agent) vs 200,000 (human) | MotherDuck | B− |
| Agents "sometimes run unnecessarily expensive queries" | [ClickHouse](https://clickhouse.com/blog/building-a-data-platform-for-agents) | D |
| Query duration | none | n/a |

**Errors**
| Data point | Source | Grade |
|---|---|---|
| None published for agent database queries | n/a | n/a |

No source reaches Grade A, meaning an independent or peer-reviewed measurement of agent traffic itself. The Lakebase paper went through peer review, but its data is the vendor's own and it is not split by agent vs human.

## (c) What remains unmeasured (in public vendor telemetry)

1. **Read/write/DDL mix** of agent queries. Supabase gives only a rank order of tools, with no values.
2. **Error rate and retry chains**, meaning the same intent re-issued after a SQL error. This is not published by anyone.
3. **Share of metadata/catalog queries.** Only MotherDuck's qualitative claim exists.
4. **Concurrency:**
   - parallel connections or sessions per agent;
   - number of agents sharing one database at the same moment;
   - peak in-flight queries.
5. **Distributions beyond the median.** There are no p90/p99 figures for inter-arrival time or rows scanned, and no query-duration figures at all.
6. **Connection behaviour.** How long connections live, pooling, and the churn of connecting and disconnecting are not measured. Lakebase compute lifetime is the nearest proxy, but it is not split by agent.
7. **Attribution validity.** Each method has a blind spot:
   - MotherDuck's MCP-vs-UI split leaves out agents that connect over the API or a driver.
   - Neon and Databricks never state how they decide a database is "agent-created."
   - No vendor reports a false-positive or false-negative rate for its classification.
8. **Absolute sample sizes.** No vendor discloses query counts, user counts or org counts behind its ratios. The exception is Databricks' 20,000+ orgs, which is for the report as a whole, not the database statistics.
9. **OLTP query patterns.** Every query-level statistic comes from analytics (OLAP) engines: MotherDuck and ClickHouse. There are none for agent-driven OLTP queries on Postgres, MySQL or document stores, even though the provisioning statistics come from Postgres platforms (Neon, Lakebase, Supabase).
