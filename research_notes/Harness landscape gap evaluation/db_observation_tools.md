# High-level database observation and diagnosis tooling for an agent harness (MCP servers, agent toolkits, triage checklists)

Scope note: 16 tool calls were spent (searches and page fetches). The URLs marked **[fetched]** were read in this session. The URLs marked **[canonical, not fetched]** are stable vendor or engine documentation pages, cited from prior knowledge so the writer has a pointer. Verify those before quoting them verbatim. Popularity and version facts are as observed on 2026-10-26.

## Q1. Which MCP servers and agent toolkits exist for databases, and which observation primitives do they expose?

### Takeaway
Many database MCP servers exist, but almost all are "query + schema" servers. Only a few expose diagnostic primitives:
- **Postgres MCP Pro (Crystal DBA):** a single health-check call plus top-queries and index tuning.
- **Google MCP Toolbox:** Postgres and MySQL active queries, locks, pg_settings, replication and query stats, plus a separate Database Insights wait-event integration.
- **pganalyze MCP:** about 30 read tools over pganalyze's already-collected history.
- **Neon MCP:** slow queries plus branch-based tuning.

Cloud control-plane servers (AWS, Azure) mostly cover inventory and configuration rather than workload diagnosis. Read-only modes are common, but they are implemented differently: read-only transactions, tool filtering, or flags.

### Cited Findings

**Postgres MCP Pro (Crystal DBA). Open source, MIT, about 3.4k stars.**
- It has nine tools: `list_schemas`, `list_objects`, `get_object_details`, `execute_sql`, `explain_query`, `get_top_queries`, `analyze_workload_indexes`, `analyze_query_indexes`, `analyze_db_health` — [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) [fetched]
- `analyze_db_health` checks buffer cache hit rate, connection health, constraint validation, index health (duplicate, unused, invalid), sequence limits and vacuum health. The technical notes also mention bloated-index checks and replication health — [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) [fetched]
- It has two access modes:
  - "Unrestricted" mode gives full read/write and is meant for development.
  - "Restricted" mode uses read-only transactions plus execution-time limits and is meant for production.
  - SQL is parsed with pglast, and statements containing COMMIT or ROLLBACK are rejected.
  - The project warns that unsafe stored-procedure languages could circumvent the protections.
  - Source: [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) [fetched]
- It uses `pg_stat_statements` for workload statistics and `hypopg` for hypothetical indexes. The experimental LLM index tuning needs an OpenAI key. Testing covers PG 15–17, there are 52 open issues and 42 open PRs, and the roadmap is listed as "TBD" — [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) [fetched]

**Google MCP Toolbox for Databases. Open source, Apache-2.0. Formerly "Gen AI Toolbox for Databases"; the repository `genai-toolbox` was renamed `mcp-toolbox`.**
- Supported sources: AlloyDB, BigQuery, Cloud SQL (PG, MySQL, SQL Server), Spanner, Firestore, PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, MongoDB, Redis, Elasticsearch, CockroachDB, ClickHouse, Couchbase, Neo4j, Snowflake, Trino and others — [googleapis/genai-toolbox → mcp-toolbox](https://github.com/googleapis/genai-toolbox) [fetched]
- Prebuilt toolsets are loaded with `--prebuilt=<db>` or `--prebuilt=<db>/<toolset>`. The README shows install version 1.15.0 but a Docker example tagged 0.24.0, so the page is inconsistent — [googleapis/genai-toolbox](https://github.com/googleapis/genai-toolbox) [fetched]
- PostgreSQL tools include:
  - `postgres-database-overview`, `-list-active-queries`, `-list-locks`, `-long-running-transactions`
  - `-list-pg-settings`, `-list-query-stats`, `-list-database-stats`, `-list-table-stats`
  - `-replication-stats`, `-list-roles`, `-list-available-extensions`, `-list-installed-extensions`
  - `-list-sequences`, `-get-column-cardinality` and others
  - No bloat, vacuum or wait-event tool is listed.
  - Source: [MCP Toolbox prebuilt configs](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- MySQL tools: `mysql-list-active-queries`, `mysql-list-all-locks`, `mysql-list-table-fragmentation`, `mysql-list-tables-missing-unique-indexes`, `mysql-show-query-stats`, `mysql-get-query-plan`. SQL Server has only execute and list-tables tools. BigQuery tools are analytics-oriented, with none for monitoring — [MCP Toolbox prebuilt configs](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- Wait events and system metrics for Google Cloud come from separate integrations:
  - Database Insights: `databaseinsights-get-advanced-aggregated-wait-event-stats`, `...-time-series-query-stats`, `...-get-index-recommendations`.
  - Cloud Monitoring: `cloud-monitoring-query-prometheus`, with "Observability" prebuilt configs for AlloyDB, Cloud SQL PG, MySQL and SQL Server.
  - Cloud SQL Admin includes `postgres-upgrade-precheck`.
  - Source: [MCP Toolbox prebuilt configs](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]

**DBHub (Bytebase). Open source, MIT.**
- Supports PostgreSQL, MySQL, SQL Server, MariaDB, Oracle and SQLite — [bytebase/dbhub](https://github.com/bytebase/dbhub) [fetched]
- Default tools are `execute_sql` and `search_objects`. Opt-in tools are `explain_sql` and `health_check`; the health check reports only connection pool state and buffer cache hit ratio. Custom parameterised SQL tools can be defined in `dbhub.toml` — [bytebase/dbhub](https://github.com/bytebase/dbhub) [fetched]
- Guardrails are read-only mode, row limiting and query timeout. It requires Node ≥ 22.5 — [bytebase/dbhub](https://github.com/bytebase/dbhub) [fetched]

**pganalyze MCP server. Commercial SaaS, public preview, hosted at `https://app.pganalyze.com/mcp`.**
- It gives curated access to statistics pganalyze already collects, so it needs no direct database access. New organisations have it enabled by default — [pganalyze blog](https://pganalyze.com/blog/mcp-server-public-preview) [search snippet]; [pganalyze docs](https://pganalyze.com/docs/mcp) [fetched]
- It has 30 tools. The read tools are:
  - `get_postgres_settings`, `get_query_stats`, `get_query_details`
  - `get_query_explains` / `get_query_explain` (EXPLAIN plans from the last 7 days), `get_query_explain_from_trace` (OpenTelemetry)
  - `get_backend_counts`, `get_backends`, `get_backend_details`
  - `get_issues`, `get_checkup_status`, `get_log_stats`, `get_log_lines` (7 days)
  - `get_system_stats` (CPU, memory, storage, network, WAL)
  - `get_table_stats` (time series), `get_index_selection`, `run_index_selection`
  - Source: [pganalyze docs](https://pganalyze.com/docs/mcp) [fetched]
- The write tools are Workbooks: `create_workbook`, `create_workbook_variant` and related tools that run EXPLAIN ANALYZE through the collector. They need the `write_workbooks` permission and collector 0.64.0 or later. The preview rate limit is 100 requests per billable server per hour — [pganalyze docs](https://pganalyze.com/docs/mcp) [fetched]

**Neon MCP server. Open source, MIT; the backing service is commercial.**
- `list_slow_queries` requires pg_stat_statements. `explain_sql_statement` returns plans. `prepare_query_tuning` and `complete_query_tuning` test optimisations on a temporary branch, then apply or discard them. Branch tools include create, delete, reset_from_parent and restore_snapshot — [neondatabase/mcp-server-neon](https://github.com/neondatabase/mcp-server-neon) [fetched]
- Read-only mode is enabled with `?readonly=true` or by unchecking "Allow writes" in OAuth. In that mode, `run_sql` runs in a READ ONLY transaction, tuning tools are unavailable, and `run_sql_transaction` is removed — [neondatabase/mcp-server-neon](https://github.com/neondatabase/mcp-server-neon) [fetched]

**Supabase MCP. Open source, Apache-2.0.**
- `read_only=true` excludes mutating tools, `project_ref` scopes the server to one project, and `features=` selects tool groups. The README points to supabase.com/mcp for the tool list and to security best-practices docs about the risks of connecting LLMs — [supabase-community/supabase-mcp](https://github.com/supabase-community/supabase-mcp) [fetched]

**AWS MCP servers (awslabs/mcp). Open source.**
- Database servers include Aurora PostgreSQL and Aurora MySQL (via the RDS Data API), Aurora DSQL, Redshift, RDS Oracle, RDS Db2, RDS MSSQL, DynamoDB, DocumentDB, Neptune, Keyspaces, Timestream for InfluxDB and S3 Tables — [awslabs/mcp](https://github.com/awslabs/mcp) [fetched]
- Observability and cost servers include CloudWatch ("Metrics, Alarms, and Logs analysis and operational troubleshooting"), AWS Billing and Cost Management, and AWS Pricing — [awslabs/mcp](https://github.com/awslabs/mcp) [fetched]
- Read-only defaults vary by server:
  - Aurora MySQL and MSSQL install configs pass `--readonly True`.
  - DynamoDB sets `DDB-MCP-READONLY=true`.
  - ECS sets `ALLOW_WRITE=false`.
  - No explicit read-only flag is shown for Aurora PG, Redshift or CloudWatch.
  - The Cloud Control API server is deprecated.
  - SSE transport was removed on 2025-05-26.
  - Source: [awslabs/mcp](https://github.com/awslabs/mcp) [fetched]

**Azure MCP Server (Microsoft, open source).** The Postgres flexible-server tools list servers, retrieve server configuration, read specific server parameter values and list databases, as of a May 2025 announcement — [Microsoft Tech Community](https://techcommunity.microsoft.com/blog/adforpostgresql/-/4413744) [search snippet]. A separate Azure-Samples Postgres MCP server lists databases and tables, runs queries and can write (insert, update, create and drop tables) — [Tech Community 4404360](https://techcommunity.microsoft.com/blog/adforpostgresql/-/4404360) [search snippet]; [Azure-Samples/azure-postgres-mcp-demo](https://github.com/Azure-Samples/azure-postgres-mcp-demo).

**Snowflake-managed MCP server. Commercial, built in.** It exposes Cortex Analyst, Cortex Search, Cortex Agents, custom tools and SQL execution. It uses OAuth and is governed by RBAC — [Snowflake docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp) [search snippet]. A third party reports preview in October 2025 and GA in November 2025 — [Atlan](https://atlan.com/know/mcp/mcp-server-for-snowflake/) [secondary].

**ClickHouse.**
- The managed remote MCP in ClickHouse Cloud has 13 tools covering querying, schema, service management, backups, ClickPipes and billing, with OAuth 2.0 — [ClickHouse docs](https://clickhouse.com/docs/cloud/features/ai-ml/remote-mcp) [search snippet]
- The open-source `mcp-clickhouse` server has `run_select_query`, `list_databases` and `list_tables` — [ClickHouse docs](https://clickhouse.com/docs/cloud/features/ai-ml/remote-mcp) [search snippet]. A third party describes four tools, including chDB — [chatforest review](https://chatforest.com/reviews/data-warehouse-lakehouse-mcp-servers) [secondary; conflicts with vendor].

### Inferences
- Postgres MCP Pro's `analyze_db_health` comes closest to a one-call triage. Google's Toolbox has the broadest set of primitive observation tools across engines (active queries, locks, settings, replication, query stats). pganalyze is the only one with history (time series, logs, plan samples), but it requires a paid collector already deployed. An agent harness could wrap or borrow from all three, but none spans more than one engine family at a diagnostic depth.
- No server above exposes setting provenance in the sense the target design means (default vs. set, reload vs. restart, managed-service modifiability). Toolbox's `postgres-list-pg-settings` probably returns pg_settings columns, but the fetched page does not confirm which columns.
- None of these "read-only" modes is a capability probe. They restrict the tool, but they do not tell the agent what its DB role could do.
- Warehouse MCP servers (Snowflake, BigQuery, ClickHouse OSS) are query and semantic-layer oriented, not diagnosis oriented. ClickHouse Cloud's billing tool is the one notable cost primitive.

### Gaps
- I could not fetch exact tool lists for the BigQuery remote MCP server, Databricks or Unity Catalog MCP, MotherDuck/DuckDB MCP, the Datadog/Grafana MCP servers, the current Azure MCP `postgres`/`sql` subcommands, or the AWS RDS control-plane or Performance Insights MCP server. The awslabs page was truncated in the region where these would be listed. The Anthropic reference Postgres server's status (archived, read-only query only) was not verified this session.
- No release date or version was found for Postgres MCP Pro.

## Q2. Which classic diagnostic sources should the high-level tools wrap, per engine?

### Takeaway
Each engine has a well-known set of views that maps onto the target tool categories (workload, waits/locks, configuration with provenance, maintenance, replication, history). The harness tool layer should be a thin, normalised wrapper over these. Existing MCP servers cover only a subset.

### Cited Findings
- **Postgres workload:** `pg_stat_statements` gives normalised per-query cumulative stats — [PG docs](https://www.postgresql.org/docs/current/pgstatstatements.html) [canonical, not fetched]. Postgres MCP Pro, Neon `list_slow_queries` and Toolbox `postgres-list-query-stats` all depend on it — [postgres-mcp](https://github.com/crystaldba/postgres-mcp); [Neon MCP](https://github.com/neondatabase/mcp-server-neon); [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- **Postgres activity, waits, locks and I/O:** `pg_stat_activity` (including `wait_event_type`/`wait_event`), `pg_locks` and `pg_stat_io` (PG16+) are documented in the cumulative statistics chapter — [PG monitoring stats](https://www.postgresql.org/docs/current/monitoring-stats.html) [canonical, not fetched]. Sampled waits require the `pg_wait_sampling` extension — [postgrespro/pg_wait_sampling](https://github.com/postgrespro/pg_wait_sampling) [canonical, not fetched]
- **Postgres configuration with provenance:** `pg_settings` has `source`, `sourcefile`, `boot_val`, `reset_val`, `context` (postmaster = restart, sighup = reload, user/superuser = session) and `pending_restart` — [PG pg_settings](https://www.postgresql.org/docs/current/view-pg-settings.html) [canonical, not fetched]
- **Postgres bloat and maintenance:** `pgstattuple` gives exact tuple-level bloat, and `pg_stat_user_tables` gives last (auto)vacuum/analyze timestamps and dead tuples — [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html); [monitoring stats](https://www.postgresql.org/docs/current/monitoring-stats.html) [canonical, not fetched]
- **Postgres plans:** `auto_explain` logs plans of slow statements — [auto_explain](https://www.postgresql.org/docs/current/auto-explain.html) [canonical, not fetched]
- **Postgres extras:** `pg_stat_kcache` gives OS-level CPU and I/O per query, and `pg_qualstats` gives predicate statistics; both are PoWA components — [PoWA docs](https://powa.readthedocs.io/) [canonical, not fetched]
- **Managed Postgres and MySQL on Google Cloud:** Database Insights exposes aggregated and time-series query and wait-event statistics through Toolbox — [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- **MySQL:** `performance_schema` and the `sys` schema (statement digests, waits, locks) — [MySQL sys schema](https://dev.mysql.com/doc/refman/8.0/en/sys-schema.html) [canonical, not fetched]. Toolbox wraps active queries, all locks, table fragmentation, query stats and missing unique indexes — [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- **SQL Server:** DMVs (`sys.dm_exec_requests`, `sys.dm_os_wait_stats`, `sys.dm_exec_query_stats`) and Query Store — [MS Learn Query Store](https://learn.microsoft.com/en-us/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store) [canonical, not fetched]. sp_BlitzFirst samples DMVs, wait stats, Perfmon counters and the plan cache — [First Responder Kit](https://github.com/BrentOzarULTD/SQL-Server-First-Responder-Kit) [fetched]
- **Oracle:** AWR, ASH and ADDM (requires the Diagnostics Pack licence) — [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) [canonical, not fetched]
- **Snowflake:** `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` and `WAREHOUSE_METERING_HISTORY`. ACCOUNT_USAGE has latency of up to hours — [Snowflake ACCOUNT_USAGE](https://docs.snowflake.com/en/sql-reference/account-usage) [canonical, not fetched]
- **BigQuery:** `INFORMATION_SCHEMA.JOBS` (bytes billed, slot ms, per job) — [BigQuery JOBS view](https://cloud.google.com/bigquery/docs/information-schema-jobs) [canonical, not fetched]
- **Iceberg (Trino):** metadata tables `$snapshots`, `$files`, `$manifests`, `$history` and `$partitions` — [Trino Iceberg connector](https://trino.io/docs/current/connector/iceberg.html) [canonical, not fetched]. **Delta:** `DESCRIBE DETAIL` and `DESCRIBE HISTORY` — [Delta docs](https://docs.delta.io/latest/delta-utility.html) [canonical, not fetched]
- **Managed parameter semantics:** Azure Flexible Server parameters are static (restart), dynamic (new connections) or read-only — [Azure docs](https://docs.azure.cn/en-us/postgresql/flexible-server/concepts-server-parameters) [search snippet]

### Inferences
- A cross-engine "workload snapshot" tool should normalise on these columns: digest/query id, calls, total/mean time, rows, and shared/physical reads (or bytes billed for warehouses). `pg_stat_statements`, `events_statements_summary_by_digest`, Query Store, QUERY_HISTORY and JOBS all provide these fields under different names.
- Cumulative counters need two-point sampling, the sp_BlitzFirst `@Seconds` pattern, to give a "now" view inside a short triage budget.

### Gaps
- None of the canonical engine-doc URLs in this section was fetched this session. Verify the exact column names (such as `pg_settings.pending_restart`) before citing them in the final report.

## Q3. Which one-shot health-check tools exist, and what do their checks imply as a triage checklist?

### Takeaway
sp_Blitz/sp_BlitzFirst for SQL Server is the most explicit precedent for anytime triage. It runs a prioritised health check plus a time-bounded delta sample, with separate deep-dive procedures for cache, index, locks and running sessions. Postgres equivalents (Postgres MCP Pro health, pghero, pganalyze check-ups) cover index health, vacuum and wraparound, sequences, connections, cache hit rate and replication.

### Cited Findings
- **SQL Server First Responder Kit (open source, MIT):**
  - `sp_Blitz` returns a prioritised list of server issues.
  - `sp_BlitzFirst` gives real-time advice by sampling DMVs, waits, Perfmon and the plan cache over `@Seconds` (default 5 s; two samples are diffed).
  - `sp_BlitzCache` finds top resource queries by reads, CPU, executions, memory grant or writes.
  - `sp_BlitzIndex` covers missing, unused and problematic indexes.
  - `sp_BlitzLock` parses deadlock XML.
  - `sp_BlitzWho` shows running queries with memory grants, DOP and plans.
  - `sp_BlitzPlanCompare` diffs a plan's environment (stats, indexes, config, parameters) across servers.
  - `sp_BlitzBackups` estimates RPO and RTO.
  - `sp_kill` is read-only by default.
  - Source: [BrentOzarULTD/SQL-Server-First-Responder-Kit](https://github.com/BrentOzarULTD/SQL-Server-First-Responder-Kit) [fetched]
- **Postgres MCP Pro health:** cache hit rate, connections, constraints, duplicate/unused/invalid indexes, sequence limits, vacuum, bloated indexes, replication — [postgres-mcp](https://github.com/crystaldba/postgres-mcp) [fetched]
- **pganalyze:** "check-up" issues and alerts, exposed via `get_issues` and `get_checkup_status` — [pganalyze docs](https://pganalyze.com/docs/mcp) [fetched]
- **pghero:** "A performance dashboard for Postgres", MIT. The fetched page did not list its checks — [ankane/pghero](https://github.com/ankane/pghero) [fetched]
- **Plan-sandbox precedents:**
  - Neon tests tuning on a throwaway branch — [Neon MCP](https://github.com/neondatabase/mcp-server-neon) [fetched]
  - pganalyze Workbooks run EXPLAIN ANALYZE variants with planner settings via the collector — [pganalyze docs](https://pganalyze.com/docs/mcp) [fetched]
  - Toolbox exposes `postgres-upgrade-precheck` — [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]

### Inferences
Combined across these tools, the triage checklist is:
1. Running sessions, waits and blockers.
2. Top queries (delta over N seconds).
3. Index health: missing, unused, duplicate, invalid.
4. Vacuum, bloat and wraparound/sequence exhaustion.
5. Connections and pool usage.
6. Cache hit ratio and I/O.
7. Replication lag and slots.
8. Backups and RPO.
9. Configuration anomalies.
10. Log-error classes.

The sp_Blitz split (fast "first" sample plus slower deep dives) maps directly onto the anytime requirement.

### Gaps
- The checks run by pgMustard, pg_activity, postgres_dba, pgwatch, PoWA, check_postgres, Percona Toolkit (pt-summary, pt-mysql-summary), MySQLTuner and Oracle ADDM were not fetched within the tool budget. These are well-known tools, but no claims about their exact checks are made here.

## Q4. How can the agent probe its action space?

### Takeaway
The probe needs three things:
- **Engine-level introspection:** role attributes and privileges, setting context, available and installed extensions.
- **Managed-service control-plane introspection:** which parameters are modifiable and whether a change needs a reboot.
- **Billing access.**

Primitives for each exist piecemeal: Toolbox `list-roles` and `list-available-extensions`, Azure parameter types, AWS billing and pricing servers. No tool combines them.

### Cited Findings
- **Toolbox role and extension tools:** `postgres-list-roles`, `postgres-list-available-extensions`, `postgres-list-installed-extensions`, `postgres-list-pg-settings` — [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- **Postgres privilege functions:** `has_table_privilege`, `has_database_privilege` and related functions report effective privileges, and `pg_roles` exposes rolsuper, rolcreaterole and similar attributes — [PG system info functions](https://www.postgresql.org/docs/current/functions-info.html); [pg_roles](https://www.postgresql.org/docs/current/view-pg-roles.html) [canonical, not fetched]. `pg_settings.context` tells which knobs need a restart — [pg_settings](https://www.postgresql.org/docs/current/view-pg-settings.html) [canonical, not fetched]
- **RDS:** `rds_superuser` is not a true superuser, and server parameters are changed through DB parameter groups. Each parameter carries `IsModifiable` and `ApplyType` (static/dynamic) in DescribeDBParameters — [RDS DescribeDBParameters API](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_DescribeDBParameters.html) [canonical, not fetched]
- **Azure:** Flexible Server parameters are typed static, dynamic or read-only — [Azure docs](https://docs.azure.cn/en-us/postgresql/flexible-server/concepts-server-parameters) [search snippet]. The Azure MCP Server can read server configuration and specific parameter values — [Tech Community](https://techcommunity.microsoft.com/blog/adforpostgresql/-/4413744) [search snippet]
- **Cost access:** AWS Billing and Cost Management and AWS Pricing MCP servers exist — [awslabs/mcp](https://github.com/awslabs/mcp) [fetched]. The ClickHouse Cloud remote MCP includes billing — [ClickHouse](https://clickhouse.com/docs/cloud/features/ai-ml/remote-mcp) [search snippet]
- **Scoping in managed MCP servers is by grant, not probe:**
  - Snowflake MCP is governed by RBAC — [Snowflake](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp) [search snippet]
  - Supabase is scoped with `project_ref`, and `read_only` removes tools — [Supabase MCP](https://github.com/supabase-community/supabase-mcp) [fetched]
  - Neon write ability depends on the OAuth "Allow writes" choice — [Neon MCP](https://github.com/neondatabase/mcp-server-neon) [fetched]

### Inferences
A single `probe_capabilities()` call should return:
- Engine, version and deployment flavour (self-managed, RDS, Aurora, Cloud SQL, Azure, Neon/Supabase, warehouse).
- Role attributes and effective privileges on key objects.
- Per-knob `{current, default, source, apply = session/reload/restart/control-plane-only/immutable}`.
- Installed and installable extensions, and which diagnostic extensions are missing (pg_stat_statements, pg_wait_sampling, hypopg).
- Control-plane permissions: can it modify the parameter group, reboot, or create a branch or clone?
- Whether billing is readable.

Today an agent would have to assemble this from three to five servers or from raw SQL plus cloud CLIs.

### Gaps
- No existing MCP tool was found that returns RDS parameter-group modifiability or Cloud SQL modifiable flags as a tool. The AWS RDS control-plane MCP server was not confirmed in the fetched excerpt.

## Q5. Gaps: what does no existing tool provide?

### Takeaway
The surveyed tools lack seven things:
1. A unified action-space and capability probe.
2. Configuration provenance joined with managed-service modifiability.
3. Time-bounded or anytime triage semantics (only sp_BlitzFirst's `@Seconds` is a precedent).
4. Cross-engine normalisation of the diagnostic views.
5. A cost/billing join with per-query workload.
6. Run-history memory independent of a SaaS collector.
7. Safety that relies only on read-only transactions or flags, which do not reason about action consequences.

### Cited Findings
- Restricted-mode safety is limited:
  - Postgres MCP Pro's restricted mode currently limits only execution time on top of read-only transactions, and it warns that unsafe procedural languages can bypass it — [postgres-mcp](https://github.com/crystaldba/postgres-mcp) [fetched]
  - DBHub guardrails are read-only mode, row limit and timeout — [dbhub](https://github.com/bytebase/dbhub) [fetched]
  - Neon read-only wraps `run_sql` in a READ ONLY transaction — [Neon MCP](https://github.com/neondatabase/mcp-server-neon) [fetched]
- History is available only through a vendor's collector: pganalyze keeps 7-day plans and logs plus time-series statistics, but only after its collector is deployed — [pganalyze docs](https://pganalyze.com/docs/mcp) [fetched]. Google's history comes from Database Insights and Cloud Monitoring, which only cover Google Cloud services — [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- Diagnostic depth is uneven across engines in the broadest multi-engine toolkit: Toolbox SQL Server and BigQuery tools have no monitoring primitives, while Postgres and MySQL do — [Toolbox](https://mcp-toolbox.dev/documentation/configuration/prebuilt-configs/) [fetched]
- Billing servers are separate from database servers: AWS Billing and Pricing are standalone MCP servers — [awslabs/mcp](https://github.com/awslabs/mcp) [fetched]

### Inferences
- The defensible contribution space for the harness is the parts no tool has:
  - The capability probe with apply-mode tagging.
  - A provenance tag on every observation: source view, sampled vs. cumulative, staleness (for example ACCOUNT_USAGE lag), and the privilege needed.
  - Budget-aware triage tiers (for example a 30 s, 2 min or 10 min plan).
  - A normalised schema across engines.
  - A local run-history store.
- Existing servers can be wrapped for raw primitives rather than rebuilt: Toolbox for multi-engine SQL primitives, Postgres MCP Pro's health and hypopg logic, Neon or Aurora clones for sandboxed what-if testing.

### Gaps
- I did not verify whether Datadog or Grafana MCP servers expose database-monitoring (DBM) query samples or wait data. If they do, they would partially fill the history and cross-engine gap for shops that already run those agents.
