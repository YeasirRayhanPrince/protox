# A. Vendor-shipped DB agents: DB interaction (Oct 2026)

Lines: 1 who · 2 interface · 3 guardrails · 4 agent→DB · 5 DB→agent · 6 aftermath · 7 loop/autonomy. `[n]` = reference list; [S] = secondary. Extends `../Harness landscape gap evaluation/` notes (MCP tool lists there).

## (a) Systems

**Oracle Select AI Agent**
1 in-DB agent "teams"; privileges undocumented [6] · 2 NL2SQL, RAG, PL/SQL, REST/email tools [6] · 3 DB auditing; HITL = chat confirmations, not a gate [6] · 4 reads; PL/SQL tools = their grants [6] · 5 into "Reflection" [6] · 6 long-term memory across sessions/teams [6] · 7 ReAct per request [6]

**Oracle SQLcl MCP**
1 user's saved connection · 3 every call logged to DBTOOLS$MCP_LOG; V$SESSION tagged with client/LLM; SQL comment-marked [7] · 4 arbitrary SQL · 5–7 unknown

**Azure SQL Copilot**
1 user's permissions [3] · 2 NL · 4 suggests indexes, doesn't create · 7 advise

**SSMS GitHub Copilot agent mode (preview)**
1 user login or CONSTITUTION.md user [2] · 2 T-SQL · 3 per-query approval; "always" persists across sessions; "permissions are the boundary" [2] · 4 reads, DML, DDL [2] · 5 unknown · 6 changes + standing approvals [2] · 7 session; act-with-approval

**Fabric data agent**
1 caller's Entra identity; multi-agent node [1] · 2 NL→SQL/DAX/KQL, ≤5 sources [1] · 3 read-only enforced; Purview DLP, RLS/CLS [1] · 4 schema, reads · 5 capped 25×25, summarized; cap contaminates follow-ups [1] · 6 audited; history may vanish [1] · 7 per question; read

**Azure SRE Agent**
1 own managed identity, zero perms by default, OBO elevation to act [4] · 2 control plane/logs · 3 Review vs Autonomous [5] · 4 no SQL data-plane path documented · 7 continuous, incident-driven

**AWS DevOps Agent**
1 per-account IAM role, read-only managed policy [9][10] · 3 IAM is the only boundary [9] · 4 rds:Describe*, CloudWatch, PI; lock holders need separate query MCP [11][S] · 7 investigates, writes specs for others [12]

**Bedrock KB (Redshift NL2SQL)**
1 service role or DB user [13] · 3 read-only only *advised* [13] · 7 per query

**Google Database Observability Agent**
1 IAM undocumented [15] · 2 Cloud Assist + Insights/Database Center MCP [15] · 3 approval per remediation [15] · 4 telemetry reads; index creation (preview) [15] · 5 rationale + expected impact [15] · 7 act-with-approval; simulate-first agent "coming soon" [16]

**BigQuery Conversational Analytics**
3 dry-run then block above `big_query_max_billed_bytes`; project/user quotas [17] · 7 per question

**AlloyDB AI NL**
2 `get_sql()` · 3 parameterized secure views confine generated SQL [18]

**Databricks Genie**
1 author's compute, user's UC perms/masks [20] · 3 SQL "always read-only" [20] · 7 per question

**Databricks Genie Code agent mode**
1 user's UC perms [21] · 2 runs code, pipelines [21] · 3 AI classifier auto-approves by default [21] · 7 session; autonomous by default

**Snowflake Cortex Agents / Intelligence**
1 caller's *default* role + warehouse; inaccessible tools now skipped with warning [25][26] · 2 Analyst, Search, sandboxed Python, procs, MCP [24][46] · 3 RBAC; orchestration/credit budgets [24] · 4 SELECT-only undocumented; writes "depend on SQL" [27][28][S] · 6 persisted threads; warehouse cost [24] · 7 plan→tool→reflect per request [24]

**MongoDB** assistant tools read-only, each confirmed [29]; MCP writes by default [30]
**Supabase MCP** destructive-SQL confirm needs client elicitation; detection incomplete [31]; injection via `service_role` [32][S]
**Neon** agents provision claimable projects [34]; >80% DBs agent-created [35]; MCP tunes on temp branch, READ ONLY txn mode [33]
**PlanetScale** nightly LLM index → HypoPG → deploy request, 30-min revert [36]
**pganalyze** MCP on collected stats, no DB access, 100 req/h [38] · **Aiven** advise [37] · **DBtune** closed-loop knobs, guardrail abort [39][S] · **Xata** preset SQL; archived [40]
**SingleStore Aura Analyst** per-domain DB user; SQL shown [41] · **ClickHouse Cloud MCP** includes service/backup/billing tools [42] · **TiDB Cloud Lake MCP** writes confined to session sandbox prefix [43]
**Deterministic (not LLM):** Oracle auto-indexing [8], Azure auto-tuning [45], Databricks Predictive Optimization [22] act autonomously.

## (b) Patterns

1. **Borrowed identity.** Data agents run as the user [1][2][21][25]; ops agents own an identity but stay on the control plane [4][9].
2. **Read-only lives in different layers**: product promise [1][20], READ ONLY txn [33], flag [30], or mere advice [13]; bypasses exist [44].
3. **Approval gates erode**: persistent [2], AI-classified [21], or silently absent [31].
4. **Lossy, undisclosed result shaping** [1].
5. **Cost guards, no regression guards** [17][24][38].
6. **LLMs act only behind humans; autonomous actors are deterministic** [8][45][22]; LLM-act paths are preview [2][15].
7. **Branch-first** is the emerging substrate [33][23][36][43].
8. **Memory = chat context**, not a change/effect record [24][6].

## (c) Holes

- Workload-level no-regression proof before apply [16][33].
- Agent-scoped, expiring DB identity with capability manifest.
- Quarantine of DB-returned text [32].
- Explicit truncation metadata [1].
- Change ledger joined to per-query before/after effect (only deterministic tuners) [45][8].
- Multi-agent concurrency/lease semantics on one DB [6].
- Load budgets for agent probes on prod [8].
- Evidence-based approval replacing the click [2][21].

## References
[1] https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent
[2] https://learn.microsoft.com/en-us/ssms/github-copilot/agent-mode
[3] https://learn.microsoft.com/en-us/azure/azure-sql/copilot/copilot-azure-sql-faq?view=azuresql
[4] https://learn.microsoft.com/azure/sre-agent/permissions
[5] https://learn.microsoft.com/azure/sre-agent/run-modes
[6] https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/about-select-ai-agents.html
[7] https://docs.oracle.com/en/database/oracle/sql-developer-command-line/25.3/sqcug/monitoring-sqlcl-mcp-server.html
[8] https://oracle.com/docs/tech/database/technical-brief-optimizer-with-oracledb-19c.pdf
[9] https://docs.aws.amazon.com/de_de/devopsagent/latest/userguide/security-and-access-control-limiting-agent-access-in-an-aws-account.html
[10] https://docs.aws.eu/awssupport/latest/user/support-devops-agent-resources.html
[11] https://aws.github.io/tools-for-devops-agent/skills/database-rds-devops/ [S]
[12] https://aws.amazon.com/blogs/aws/aws-devops-agent-helps-you-accelerate-incident-response-and-improve-system-reliability-preview
[13] https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-prereq-structured.html
[14] https://github.com/awslabs/mcp
[15] https://cloud.google.com/blog/products/databases/deep-dive-on-new-ai-powered-database-agents
[16] https://cloud.google.com/blog/products/databases/database-center-improvements-from-next26
[17] https://docs.cloud.google.com/gemini/docs/conversational-analytics-api/manage-costs
[18] https://docs.cloud.google.com/alloydb/docs/ai/secure-app-data-parameterized-secure-views
[19] https://github.com/googleapis/genai-toolbox
[20] https://docs.databricks.com/gcp/en/genie/concepts
[21] https://docs.databricks.com/aws/en/genie-code/agent-mode
[22] https://docs.databricks.com/aws/en/optimizations/predictive-optimization
[23] https://docs.databricks.com/aws/en/oltp/projects/about
[24] https://docs.snowflake.com/user-guide/snowflake-cortex/cortex-agents
[25] https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-setup
[26] https://docs.snowflake.com/release-notes/bcr-bundles/un-bundled/bcr-2425
[27] https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
[28] https://docs.glean.com/agents/actions/datasource/snowflake/search-snowflake-with-cortex [S]
[29] https://www.mongodb.com/docs/atlas/atlas-ui/query-with-natural-language/data-explorer-ai-assistant/
[30] https://www.mongodb.com/docs/mcp-server/local-mcp/security-best-practices/
[31] https://supabase.com/docs/guides/troubleshooting/sql-confirmations-do-not-appear-in-your-mcp-client-sQf7Kp
[32] https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/ [S]
[33] https://github.com/neondatabase/mcp-server-neon
[34] https://neon.com/blog/an-agent-provisions-a-neon-backend-a-human-claims-it-later
[35] https://databricks.com/company/newsroom/press-releases/databricks-agrees-acquire-neon-help-developers-deliver-ai-systems
[36] https://planetscale.com/docs/postgres/monitoring/schema-recommendations
[37] https://aiven.io/docs/products/postgresql/howto/ai-insights
[38] https://pganalyze.com/docs/mcp
[39] https://dev.to/floriansuchan/how-we-used-dbtune-to-cut-our-postgres-query-time-by-50-on-aws-rds-2a5e [S]; https://itbrief.co.uk/story/dbtune-4-0-adds-index-tuning-to-postgresql-optimisation [S]
[40] https://github.com/xataio/agent
[41] https://docs.singlestore.com/cloud/ai/aura-analyst
[42] https://clickhouse.com/docs/cloud/features/ai-ml/remote-mcp
[43] https://docs.pingcap.com/tidbcloudlake/mcp-client-integration
[44] https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/
[45] https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview
[46] https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp

Verification note: I fetched and read [1], [6], [15], [21] and [24]. Claims from [2], [4], [7], [9]–[13], [17], [18], [20], [25]–[31], [34], [41] and [43] rest on search-result extracts. The rest are carried over from the earlier notes without re-checking. [29] (the MongoDB per-tool confirmation) came from a search snippet whose exact source page is uncertain.
