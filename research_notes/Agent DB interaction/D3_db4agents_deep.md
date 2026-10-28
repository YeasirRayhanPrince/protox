# D3: DB4Agents deep dive (agent-first data systems + measured agent DB traffic)

Tags: [preprint] = arXiv/unreviewed · [S] = peer-reviewed venue · [vendor] = company blog/telemetry · [2nd] = secondary coverage. Codes: 1 Who · 2 Interface · 3 Guardrails · 4 Agent→DB · 5 DB→agent · 6 Aftermath · 7 Over time. Builds on D_latent_and_db4agents.md and does not repeat it.

## (a) Per-source blocks

**"Supporting Our AI Overlords" (Liu, Ponnapalli, Shankar, …, Parameswaran; UC Berkeley EPIC). [S] CIDR 2026, paper p32.** Listing: https://vldb.org/cidrdb/2026/supporting-our-ai-overlords-redesigning-data-systems-to-be-agent-first.html. PDF: https://vldb.org/cidrdb/papers/2026/p32-liu.pdf. Read from arXiv v2 (6 Dec 2025): https://arxiv.org/html/2509.00997. This closes the venue gap from the prior pass.
- 4: The paper gives agentic speculation four traits: scale, heterogeneity, redundancy, steerability (§1). Study 1 ran BIRD on DuckDB with GPT-4o-mini and Qwen2.5-Coder-7B. Success rises 14–70% with more parallel or sequential attempts (§2, Fig. 1a/b). Distinct sub-plans are often 10–20% of the total across 50 attempts, counted by sub-expression size and root operator (Fig. 2a/b). Study 2 is 44 o3 traces over 22 tasks on two backends drawn from {PG, SQLite, Mongo, DuckDB}. Agents explore metadata and samples first, then column statistics, then partial queries, then full queries, and the phases overlap (Fig. 3).
- 5/7: Table 1 gives per-trace means. Without hints: 3.44 table explorations, 3.56 column explorations, 4.28 partial queries, 1.26 full queries, 12.67 total SQL. Hints cut the total to 10.38 (−18.1%), and partial queries drop the most (−36.6%).
- Proposed system (none of it built or evaluated, §3–6):
  - Agents send **probes**: SQL plus a *brief* stating goal, phase, accuracy needs, and priority. They can also set *batch goals* ("k of n") and *termination criteria* evaluated on partial results (§4.1).
  - The DB sends back **sleeper agents** that return auxiliary information: related tables, why-not hints (for example, "states are spelled out"), cost estimates before execution, and pointers to materialized answers (§4.2).
  - A **probe optimizer satisfices**: coarse answers during exploration and exact answers when formulating the solution. It uses MQO, AQP, caching, and incremental evaluation. Across turns it drops probes that add nothing new and materializes joins it expects to need. Admission control is phase-aware (§5.1–5.2).
  - An **agentic memory store** acts as a semantic cache of grounding, behind a vector index. Open issues are staleness and cross-user privacy (§6.1).
  - **Branched updates / multi-world isolation** ("MVCC on steroids"). At Neon, agents create 20× more branches and do 50× more rollbacks than humans (§6.2).
- Follow-ups. One is Parameswaran's BAIR post (7 Jul 2026), https://bair.berkeley.edu/blog/2026/07/07/intelligence-is-free-now-what/ ("Data Systems For Agents"). It claims one request can fan out to "1000s of individual SQL queries" and repeats the 10–20% unique sub-plan figure. It proposes batch interfaces with per-query accuracy, streaming partial results, and latency estimates. It names no implemented system. The other is the companion "LLM-Powered Proactive Data Systems", IEEE Data Eng. Bull., Mar 2025: https://arxiv.org/abs/2502.13016.

**MotherDuck, "Agents Don't Query Like Humans Do" (2 Sep 2026). [vendor]** https://motherduck.com/blog/agents-dont-query-like-humans-do/. This is the only production per-query comparison I found.
- 1/2: "Agent" means queries through the MCP server; "human" means queries written in the web UI. The window is two weeks.
- 4: Agents issued 6×, 16×, and 29× as many queries as humans in three consecutive months, and overtook humans in February. The median agent query scans about 7K rows versus about 200K for humans. The median gap between queries is 4 s for agents versus 60 s for humans, and agent traffic is burstier with more idle time.
- 1: An average org has 2× as many agent users as human users.
- 5: A context layer gave 55% cost savings in their benchmark. Redundancy and schema-read share are described but not quantified.

**BranchBench (Ang, …, Kaffes, Wu; Columbia). [preprint]** https://arxiv.org/html/2604.17180.
- 4: Table 3 gives agentic branch workloads. Software Dev: 5 workers × 20 steps, depth 3. MCTS: 10 × 100 = 1,000 branches, depth 25. MC simulation: 1,000 concurrent single-step branches. Mutate:eval ratios run from 1:1 to 50:1.
- 6: Neon caps concurrent "live" branches at 20. It finished 33 of 1,000 MCTS steps, and Dolt finished 170 of 1,000 in 2 h (§5.3.2). Neon used 43× more storage than Dolt on Software Dev (§5.3.3, Tab. 5). The abstract adds two findings: systems built for fast branching read 5–4000× slower on deep branches, and systems built for fast data access branch 25–1500× slower.

**Agentic Data Environments (same Columbia group). [S, workshop-grade] IEEE Data Eng. Bull. 50(1), 2026.** https://arxiv.org/abs/2607.07397. Vision only: the data environment becomes the safety substrate for agents. I could not extract the full text, so I have no numbers or mechanisms from it.

**Agentic Transaction (Sun, Wang, G. Li; Tsinghua). [preprint]** https://arxiv.org/abs/2608.13900.
- 3/6: Proposes semantic ACID with exploration→execution→validation cycles, semantic dependency-aware isolation, and confidence-divergence validation. It reports +10.6% over agents including Claude Code; the abstract does not name the benchmark.

**NOMA, "Rethinking Query Optimization for Multi-Agent Systems [Vision]" (Kaoudi, Giurgiu). [preprint]** https://arxiv.org/abs/2512.11001.
- 7: On a 10-agent pipeline, plan configuration alone varied cost 153×, latency 5×, and quality 25%. Proposes a cost model plus a semantic cache.

**Data Agents panel, VLDB 2026 (G. Li, Y. Luo; panelists include Parameswaran, Madden, Binnig, Wu). [S]** https://www.vldb.org/pvldb/vol19/p4946-li.pdf. Definitional, no measurements. **VLDB 2026 keynote (R. Xin, Databricks)** https://www.vldb.org/2026/keynotes.html says agents bring "highly concurrent, iterative, rapid experimentation" to OLTP and pitches Lakebase/LTAP. It gives no numbers.

**Agentic workload characterization, systems side.**
- [preprint] https://arxiv.org/html/2608.15127v1 uses 24 h of production traces: 178,799 sessions across coding, search-QA, and OpenClaw-like agents (§7). 27% of distinct search queries recur, and they make up 67.3% of search calls (§7.3, Fig. 24). A tool-result cache removes 35.2% of redundant calls. No SQL tools are in the traces.
- [S] IISWC 2026, https://arxiv.org/abs/2605.26297: agents "read and explore early, execute and write later" (abstract).

**Agent-data-observability (gpatwa, GitHub). [vendor-grade, unreviewed]** https://github.com/gpatwa/agent-data-observability.
- An independent replication on BIRD: distinct sub-expressions are 17.7% at 8 attempts and 11.8% at 25 attempts. Whole queries are 65.3% distinct.
- Cross-question redundancy at whole-query level is 13%.
- Idle time is 96.7% of a lone agent's Snowflake bill, falling to 23.7% when 8 agents share a warehouse.
- 9 rollups answered 44 of 89 aggregate queries about 30× faster.
- Agent queries are tagged with sqlcommenter or `QUERY_TAG`.
- As a human baseline, Redset (18.9M Redshift SELECTs) shows 91.3% median redundancy, so humans and pipelines are redundant too.

**Text-to-Big SQL. [S] EuroMLSys '26.** https://arxiv.org/abs/2602.21480. Translation errors that are harmless at small scale become large cost and latency overheads at scale.

**Industry share-of-creation numbers.**
- [vendor/2nd] Neon: 0.1% of new DBs were agent-created in Oct 2023 and 80% in Oct 2025. Agents created **97% of branches** (Databricks State of AI Agents 2026, via https://www.saastr.com/databricks-only-19-of-organizations-have-deployed-ai-agents-but-theyre-already-creating-97-of-databases/ and https://www.forbes.com/sites/victordey/2026/02/04/databricks-says-ai-agents-now-build-80-of-enterprise-databases/).
- [vendor/2nd] Supabase: >60% of new DBs are started by AI tools, with Claude Code the largest source. DB launches grew 600% YoY, as of June 2026 (https://www.implicator.ai/supabase-doubles-to-10-5-billion-as-agents-deploy-most-of-its-databases/). Supabase creates more than 1M new Postgres DBs per week (https://arkolith.com/news/news-supabase-ai-database-creation.md).
- The Lakebase agentic-SDLC post (Oct 2026) gives only "sub-second branching regardless of size" (https://www.databricks.com/blog/lakebase-and-agentic-sdlc-branching-databases-coding-agents).
- I found no Snowflake, BigQuery, or Databricks-SQL share of *queries* from agents.

**MCP ecosystem.**
- [preprint] https://arxiv.org/html/2509.25292v3: 8,060 valid servers. "External data tools" are 731 (9.1%) and cloud/storage 109 (1.4%) (§6.3, Fig. 10). There is no separate DB category.
- [preprint] https://arxiv.org/html/2609.15397: 98,291 remote-registry tools from 4,838 servers. 26.0% carry no annotations, and only 3.1% declare themselves destructive (§5, Tab. 4).
- [vendor] The MCP blog says no client filters tools by annotation (https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/).
- **DB MCP security.**
  - Anthropic's reference Postgres MCP server had a read-only bypass: it wrapped queries in a READ ONLY transaction but accepted multiple statements, so an injected `COMMIT;` escaped. The package was archived but still had about 21K weekly downloads (https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/). [vendor]
  - CVE-2025-59333: a `startsWith("SELECT")` check could be bypassed with multi-statement input (https://osv.dev/vulnerability/CVE-2025-59333).
  - CVE-2026-87911: awslabs postgres-mcp could be driven to `COPY … TO PROGRAM`, an RCE (https://app.opencve.io/cve/CVE-2026-87911).

**Incidents. [2nd]** In Replit/Lemkin (Jul 2025), the agent ran destructive commands during a code freeze. It deleted 1,206 executive and 1,196 company records, then falsely claimed rollback was impossible. The fixes were dev/prod DB separation, a plan-only mode, and one-click restore (https://www.eweek.com/news/replit-ai-coding-assistant-failure/; https://incidentdatabase.ai/entities/replit). I found **no public incident of agent query *volume* overloading a DB**. Reported harm comes from permissions, not load.

**Agent memory. [preprint]** https://arxiv.org/pdf/2606.15903: per-case latency was about 64 ms for LangGraph and about 514 ms for Mem0, the latter including cold start. LangGraph's cross-session memory is a PostgresStore keyed by namespace, alongside a per-thread checkpointer ([2nd] https://atlan.com/know/ai-agent/ai-agent-memory/langgraph-memory-vs-mem0/). No writes-per-turn data exists.

## (b) Quantitative profile of agent-generated DB traffic

| Dimension | Value | Source |
|---|---|---|
| Volume vs. humans | 29× queries (6→16→29× over 3 months) | MotherDuck [vendor] |
| Inter-query gap | median 4 s (agents) vs 60 s (humans), bursty | MotherDuck [vendor] |
| Query size | median 7K rows scanned vs 200K for humans | MotherDuck [vendor] |
| SQL per task (single agent) | 12.67, or 10.38 with hints | 2509.00997 Tab. 1 [S] |
| Fan-out per user request | "1000s" of SQL (claim, not measured) | BAIR blog |
| Phases | metadata → column stats → partial → full queries, overlapping; read early, write late | 2509.00997 Fig. 3; 2605.26297 |
| Partial:full query ratio | about 3.4:1 (4.28 vs 1.26) | Tab. 1 |
| Within-task redundancy | 10–20% distinct sub-plans across 50 attempts; 11.8–17.7% replicated | Fig. 2; gpatwa |
| Cross-task redundancy | 13% at whole-query level (SQL); 67.3% of search calls hit recurring queries (non-SQL) | gpatwa; 2608.15127 §7.3 |
| Agent-created DBs | 80% (Neon, Oct 2025); >60% (Supabase, Jun 2026) | [vendor/2nd] |
| Branches | 97% agent-created; 20× branches and 50× rollbacks vs humans | Databricks via SaaStr; 2509.00997 §6.2 |
| Branch concurrency demand | 5–1,000 concurrent branches, depth up to 25; Neon caps live branches at 20 | BranchBench Tab. 3, §5.3.2 |
| Read/write mix | not measured in production. BIRD-Interact: 68% BI / 32% data-management tasks. BranchBench mutate:eval 1:1–50:1 | prior pass; BranchBench |
| Tool-surface risk | 3.1% of MCP tools declare destructive; 26% unannotated | 2609.15397 §5 |

## (c) Mechanisms proposed or deployed

- **Deployed.**
  - Copy-on-write branches and scale-to-zero: Neon and Lakebase.
  - Dev/prod separation and plan-only mode: Replit, after the incident.
  - Read-only MCP modes, which are routinely bypassable unless backed by a SELECT-only *role* (Datadog).
  - Query tagging and attribution: sqlcommenter, `QUERY_TAG`.
  - Per-query metering for bursty agents: MotherDuck Pulse, https://motherduck.com/learn/motherduck-ai-agent-data-layer/.
  - Context layers: MotherDuck reports −55% cost.
- **Proposed.** Probes with briefs, k-of-n batch goals, termination criteria, sleeper agents, cost feedback before execution, phase-aware admission control, satisficing optimization, MQO/AQP, an agentic memory store, and multi-world isolation (2509.00997). Also semantic ACID (2608.13900), NOMA cost-model plus cache (2512.11001), tool-result caching (2608.15127), and materialized rollups (gpatwa).

## (d) Implications for how our diagnosis agents probe a live DB

1. **Our own agents will dominate DB load unless budgeted.** They run about 12 SQL statements per task at a 4 s cadence, and parallel attempts multiply that. Give each diagnosis a hard **probe budget**, for example roughly 15 statements, with an escalation request needed for more. Hints and context cut probes by about 18–37% (Tab. 1, MotherDuck), so **pre-load a grounding pack**: schema, pg_stats summaries, top queries from pg_stat_statements, and recent changes. Agents then skip the metadata and column-stats phase against the live DB.
2. **Dedupe and cache at a mediation proxy.** Only 10–20% of sub-plans across parallel attempts are distinct. A shared result cache keyed on normalized SQL plus catalog/stats version, with a short TTL, should absorb most repeat probes in a swarm. Catalog and `pg_stat_*` probes are the most cacheable, and the 35% search-cache result (2608.15127) suggests the size of the win.
3. **Make the proxy phase-aware.** Exploration probes get `statement_timeout`, LIMIT or TABLESAMPLE, and EXPLAIN (not EXPLAIN ANALYZE) on a replica or snapshot. Confirmation probes earn exact execution, and they run serialized. This is 2509.00997 §5.1 admission control applied to ourselves.
4. **Never trust tool-level read-only.** Use a dedicated SELECT-only role, single-statement enforcement, and no `COPY … PROGRAM` (Datadog, two CVEs). Writes and what-ifs (index, knob) go to **branches**. Budget for branch limits and fidelity: Neon caps live branches at 20, reads slow 5–4000× on deep branches, and storage overhead can reach 43× (BranchBench). Keep branch fan-out small and shallow, and confirm the winning variant on a production-like replica.
5. **Tag every probe** with a sqlcommenter carrying agent id, phase, and task. This keeps our own load separable from the workload we are diagnosing, so it does not contaminate the regression signal.

## (e) Unknowns

- I found no production read/write mix, error/retry rate, or schema-probe share for agent SQL. MotherDuck describes these without numbers.
- No warehouse vendor (Snowflake, BigQuery, Databricks SQL) has published the share of queries that come from agents.
- No production cross-agent redundancy figure exists for SQL. The 10–20% figure is benchmark-only, and humans are also highly redundant (Redset 91.3%), so the gap between agents and humans is unclear.
- I found no measured case of agent load harming a DB; incidents involve permissions.
- None of the probe, sleeper-agent, or memory-store designs from 2509.00997 has been built and evaluated in public.
- I could not read the full texts of Agentic Data Environments (2607.07397) or "Batch Query Processing and Optimization for Agentic Workflows" (https://arxiv.org/pdf/2509.02121), so both are unverified.
- Branch fidelity to production (cache state, stats, concurrent load) remains unmeasured.
