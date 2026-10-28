# DB vendor autonomous-tuning designs (as of Oct 2026), through a zero-regression lens

Key: [P] primary (vendor docs, blog, or paper), [S] secondary. Format: loop / regression guard / autonomy / what to take.

**Oracle (Auto Indexing + SPM). Achieves no-regression without apply-then-revert.**
Loop: capture SQL → create candidates *unusable + invisible* (metadata only) → verify by compiling, then test-executing captured SQL against the invisible indexes → make visible only on net benefit. Statements that would regress get SQL plan baselines pinning their old plan. Non-beneficial indexes go unusable after 24h. [P] https://oracle.com/docs/tech/database/technical-brief-optimizer-with-oracledb-19c.pdf. The SPM Evolve Advisor test-executes unaccepted plans against the best accepted plan and accepts only those "sufficiently better" [P] https://docs.oracle.com/en/database/oracle/oracle-database/26/tdppt/evolving-sql-plans.html. No LLM in the loop. Autonomy: modes are IMPLEMENT, REPORT ONLY (built and tested, never exposed) and OFF [P] blog above; [S] https://www.syntax.com/?p=58105. Caveat: test execution still uses prod CPU/IO. Take: **stage → prove on hidden structure → expose**, plus a per-query plan pin as a guard on every exposure.

**Microsoft (Azure SQL automatic tuning). Apply-then-revert.**
Loop: Query Store telemetry → recommend CREATE/DROP INDEX → apply at low CPU/IO → validate for 30 min to 72 h → revert "immediately" on regression [P] https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview. FORCE_LAST_GOOD_PLAN is itself detect-then-revert to the last good plan [P] same URL. Das et al. describe the validation and large-scale production experimentation [P] https://www.microsoft.com/en-us/research/uploads/prod/2019/02/autoindexing_azuredb.pdf. A Microsoft patent covers tuning on a cloned DB with replayed workload [P] https://patents.justia.com/patent/11182360. Defaults: FORCE_LAST_GOOD_PLAN on, CREATE/DROP_INDEX off; Fabric turns CREATE_INDEX on [P] docs. Real revert seen in the field: index write overhead on bulk inserts [S] https://virtual-dba.com/?p=243188. LLMs: SSMS Copilot is advisory and documented as possibly inaccurate [P] https://learn.microsoft.com/ms-my/ssms/github-copilot/overview. Azure SRE Agent is in preview with no Azure SQL tuning scenario found [S] https://learn.microsoft.com/en-us/answers/a/12498076. Take: Query Store-style per-query before/after stats and resource-aware apply windows. Validate on a clone, not prod.

**AWS. Advisory plus plan pinning.**
Aurora PG Query Plan Management: the first plan is Approved (the baseline), new plans are captured Unapproved, and evolve_plan_baselines verifies a plan is faster before approving it [P] https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Optimize.Start.html. DevOps Guru for RDS: ML anomaly detection on DB load, proactive and reactive insights, recommendations only [P] https://docs.aws.amazon.com/devops-guru/latest/userguide/working-with-rds.overview.definitions.html. LLM agents appear only as MCP servers and builder demos [P] https://aws.amazon.com/products/databases/agentic-ai. Take: plan baselines as a zero-regression primitive on PG.

**Google (Cloud SQL / AlloyDB). Moving toward simulate-before-apply.**
The Gemini Database Observability Agent does LLM root-cause analysis over Insights, Logging and Trace [S] https://infoq.com/news/2026/08/google-database-operation-agents. A "Testing agent" simulates the latency/IOPS impact of indexes or machine upgrades *before applying*. It is labelled "coming soon" and is user-triggered [P] https://cloud.google.com/blog/products/databases/database-center-improvements-from-next26. The AlloyDB index advisor is recommend-only [P] https://cloud.google.com/alloydb/docs/index-advisor-overview. Take: an LLM for diagnosis, with a separate simulation gate.

**Databricks.**
Predictive Optimization autonomously runs OPTIMIZE, VACUUM and ANALYZE on UC managed tables. It is on by default for new accounts, and every action is logged to a system table [P] https://docs.databricks.com/aws/en/optimizations/predictive-optimization. These are layout and maintenance actions that leave query semantics and plans' correctness intact. Lakebase offers copy-on-write branches as agent sandboxes [P] https://docs.databricks.com/aws/en/oltp/projects/about. Take: a cheap CoW clone is the right validation substrate. Branching *is* "clone, not prod".

**Snowflake.**
Automatic Clustering reclusters only "if it will benefit" [P] https://docs.snowflake.com/en/user-guide/tables-auto-reclustering. Optima Indexing creates *hidden* search indexes for recurring point lookups, best-effort and fully autonomous [P] https://docs.snowflake.com/en/user-guide/snowflake-optima. No validation method is published. Take: restrict autonomy to additive, semantics-neutral actions that the optimizer may ignore.

**TiDB. Proves without building.**
RECOMMEND INDEX uses hypothetical (what-if) indexes scored by optimizer cost, and is recommend-only [P] https://docs.pingcap.com/tidb/dev/index-advisor/. Take: a what-if pre-filter costs nothing on prod.

**Alibaba DAS.**
Two modes: diagnose only, or auto-create indexes with online DDL in the maintenance window [P] https://help.aliyun.com/en/das/user-guide/automatic-sql-optimization. "Effect tracking, rollback" is listed [S] https://platform.softwareone.com/product/database-autonomy-service-das/PCP-4997-5628, which suggests apply-then-revert.

**MongoDB Atlas.**
Performance Advisor ranks suggested indexes, and a human creates them [S] https://oneuptime.com/blog/post/2026-03-31-mongodb-atlas-performance-advisor/markdown.

## Who gets "no regression" without apply-then-revert on prod?
- **Oracle**: invisible indexes are test-executed, SPM baselines are attached to regressing statements before exposure, and evolve accepts a plan only after a test run. This is the only shipped, end-to-end example.
- **Aurora QPM**: new plans stay unapproved until verified, but this covers plans only.
- **TiDB**: what-if cost only, with no autonomous apply.
- **Google**: pre-apply simulation is announced, not yet shipped.
- **Azure SQL and Alibaba DAS** rely on apply → monitor → revert. **Snowflake and Databricks** limit themselves to semantics-neutral actions and publish no validation.

## Takeaways for us
1. Pipeline: what-if cost filter (TiDB) → replay on a CoW clone (Lakebase/patent) → hidden exposure (Oracle invisible/REPORT ONLY) → one commit.
2. Every commit carries a **plan pin** (SPM or Aurora QPM approved plans) so that no other query's plan can change at exposure time.
3. Verification must include **write-path cost**, because Azure's real revert came from bulk-insert overhead, and invisible indexes still pay DML maintenance.
4. Use LLMs for diagnosis and hypothesis generation only (Google, Azure SRE). No vendor lets an LLM decide on an apply.
5. Apply only in low-utilization windows, and use online DDL (Azure, DAS) so the act of applying cannot regress the workload either.
