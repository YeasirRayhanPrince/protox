# Taxonomy of optimization dimensions inside the engine, in middleware, and on the application side (beyond indexes, knobs, hints)

How to read the citations. Pages marked [fetched] were retrieved or searched in this session, and the claim was checked against what came back. Pages marked [doc] are stable official documentation URLs cited from prior knowledge and not re-fetched in this session. A report writer should spot-check [doc] items if exact wording matters. Every claim that has no URL is either in an Inferences section or in a Gaps section.

## Q0. What do existing taxonomies (self-driving DBMS, AI4DB, root-cause diagnosis) say about the action space?

### Takeaway
The academic literature still frames the action space mostly as knobs, indexes/views, partition keys and query rewrite/hints. The diagnosis literature (D-Bot, iSQUAD, DBSherlock) is organized around root causes, not actions: workload concurrency, operators, plans, data, schema/settings, background tasks, and external resource contention. Neither covers middleware (pooling, routing, caching) or application-side levers. A holistic umbrella has to add those layers explicitly.

### Cited Findings
- **Pavlo et al., CIDR 2017 (Peloton).** The paper argues that earlier advisors still depended on humans to approve changes and only reacted after problems appeared. It proposes workload clustering, then forecasting, then planning that picks an action sequence via tree search, plus measuring each action's effect so its deployment can be scheduled well. Its listed open problems include OLTP vs OLAP prioritization, interference between self-driving components, and human interaction — [Pavlo et al. PDF](https://web.eecs.umich.edu/~linmacse/publications/2017.self-driving.cidr.pdf) [fetched via search]; [CIDR slides](https://www.cidrdb.org/cidr2017/slides/p42-pavlo-cidr17-slides.pdf); [summary, Morning Paper](https://blog.acolyer.org/2017/01/17/self-driving-database-management-systems/)
- **Zhou, Chai, Li, Sun, "Database Meets Artificial Intelligence: A Survey" (TKDE 2022).** For AI4DB it groups work into learned configuration tuning, optimizer, index/view advisor, and security — [AI4DB survey PDF](https://www.cs.arizona.edu/~caolei/papers/AI4DB.pdf); [BIT repository](https://pure.bit.edu.cn/en/publications/database-meets-artificial-intelligence-a-survey/)
- **Li, Zhou, Cao, ML4DB tutorial (VLDB 2021).** Offline NP-hard optimization covers knob space exploration, index/view selection, and partition-key recommendation. Online optimization covers query rewrite and join order selection. Regression and prediction problems (e.g., cost/cardinality estimation) form separate groups — [ML4DB tutorial](https://www.vldb.org/pvldb/volumes/14/paper/Machine%20Learning%20for%20Databases); [PDF](https://www.cs.arizona.edu/~caolei/papers/ML4DB.pdf)
- **Zhao, Zhou, Li, "Automatic Database Knob Tuning: A Survey".** The pipeline is knob selection, then feature selection, then tuning method (heuristic, Bayesian optimization, deep learning, reinforcement learning), then transfer — [tuning survey PDF](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/tuning-survey.pdf)
- **D-Bot (PVLDB 17, 2024).**
  - Anomaly types: "Slow Query Execution", "Full Resource Usage", "Database Hanging", "Database Crashing".
  - Root-cause categories: "Concurrency Workloads", "Query Operator Issues", "Planning and Execution", "Data-specific Issues", "Database Schema and Settings", "Harmful Background Tasks".
  - Micro-benchmark root causes include highly concurrent commits, highly concurrent updates, large data fetch, poor joins, correlated subquery, redundant index, missing index, and insert/delete-heavy cases.
  - The evaluation uses 539 anomalies across 6 applications: IoT 83, e-commerce 211, financial 31, BI 20, file sharing 47, social media 147.
  - Its optimization tools are only "Query Rewrite", "Knob Tuning" and "Index Tuning", plus monitoring and query-hint tools.
  - Sources: [D-Bot arXiv HTML](https://ar5iv.labs.arxiv.org/html/2312.01454) [fetched]; [PVLDB](https://www.vldb.org/pvldb/vol17/p2514-li.pdf)
- **iSQUAD (VLDB 2020).** It separates intermittent slow queries caused by external factors (instance CPU-intensive workload, host I/O bottleneck) from internal causes (query complexity, missing indexes, poorly written SQL). One summary reports 80.4% F1 on Alibaba OLTP data — [iSQUAD talk slides](https://users.cs.utah.edu/~lifeifei/papers/isql-talk.pdf); [paper](https://users.cs.utah.edu/~lifeifei/papers/slowsql.pdf)
- **DBSherlock (SIGMOD 2016).** It combines outlier detection with causality analysis over OLTP telemetry. DBAs label abnormal periods, and the confirmed causes feed an evolving causal model. It has no fixed action taxonomy — [DBSherlock paper](https://web.eecs.umich.edu/~mozafari/php/data/uploads/sigmod_2016.pdf); [summary](https://blog.acolyer.org/2016/07/14/dbsherlock-a-performance-diagnostic-tool-for-transactional-databases/)

### Inferences
- The gap between diagnosis categories and action categories is the main opening for a problem definition. D-Bot can *diagnose* "Harmful Background Tasks" or "Concurrency Workloads", but its action set (rewrite, knob, index) cannot *fix* them by changing vacuum schedules, pool modes, admission control, or app batching.
- A principled umbrella organizes levers along two axes: *where the lever lives* (engine physical/logical, engine runtime, middleware, application), and *what it acts on*:
  - data layout (what is stored, and how)
  - information to the optimizer (statistics, plans)
  - background work (maintenance)
  - concurrency (transactions, locks)
  - connections and routing
  - admission and scheduling (who runs when)
  - request shape (what the app asks for)
  - platform version and features
- Suggested top-level categories (C1 to C10), each detailed below:
  - C1 Physical data layout
  - C2 Logical schema and data model
  - C3 Optimizer information and plan stability
  - C4 Maintenance and background work
  - C5 Concurrency and transaction design
  - C6 Connection management and routing middleware
  - C7 Caching and result reuse
  - C8 Workload management and admission control
  - C9 Application request shape (queries, ORM, batching, pagination, retries)
  - C10 Platform features, extensions and versions
  - Indexes, knobs and hints stay as the "classic trio" that interacts with all of them.

### Gaps
- I could not get the full D-Bot Table 1 column labels (the PDF extraction was garbled), so the full list of 10 micro-benchmark causes is incomplete.
- I did not find a survey that explicitly taxonomizes middleware or application-side tuning as autonomous-DB actions. This looks like a genuine literature gap, not just a search miss, but that is unconfirmed.

## Q1. Physical design beyond indexes (C1): partitioning, sharding, materialized views, storage format, compression, fillfactor, clustering, TOAST, tablespaces

### Takeaway
Physical layout levers have the highest payoff and the highest change cost. Most require a data rewrite or a long online migration. Their reversibility ranges from easy (fillfactor for future pages) to effectively one-way (sharding). An agent must treat them as planned, staged, flag-gated migrations, not instant actions.

### Cited Findings
- **Declarative partitioning (PostgreSQL).** It supports range, list and hash partitioning. Partition pruning lets the planner skip partitions. Dropping or detaching a partition replaces bulk DELETE and avoids the VACUUM overhead of mass deletes. ATTACH/DETACH PARTITION, including DETACH CONCURRENTLY, gives near-online lifecycle changes — [PG docs: partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) [doc]
- **Vertical partitioning, then horizontal sharding (Figma).**
  - Figma first moved groups of related tables into separate databases, which the post calls "a relatively easy and very impactful scaling lever". There were about a dozen vertically partitioned DBs by end of 2022. The limit is that a single table is the smallest unit.
  - Horizontal sharding grouped tables into "colos" that share a shard key (UserID, FileID, OrgID). Keys are hashed to avoid auto-increment hotspots.
  - Logical sharding was separated from physical sharding: per-shard Postgres views on the unsharded DB came first, rolled out by percentage behind feature flags with rollback in seconds, at under 10% overhead in the worst measured cases.
  - The first sharded table took about 9 months and shipped in Sept 2023, with about 10 s of partial primary availability during failover.
  - Stated risks: loss of FK and global-unique enforcement, partial commits across shards, scatter-gather queries scaling like unsharded load, less efficient range scans under hash routing, and views changing query plans.
  - Source: [Figma: How Figma's databases team lived to tell the scale](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]
- **Application-level sharding (Notion).** Notion sharded its Postgres monolith into a horizontally partitioned fleet (32 physical servers at the time). The switchover ran in a five-minute scheduled maintenance window — [Notion: Herding elephants](https://www.notion.com/blog/sharding-postgres-at-notion) [fetched via search]; [pganalyze summary](https://pganalyze.com/blog/5mins-postgres-figma-dbproxy-sharding-postgres)
- **Distributed SQL key design (CockroachDB).**
  - Sequential keys concentrate inserts in one range. Cockroach Labs advises against indexing on sequential keys and recommends hash-sharded indexes, which remove single-range hotspots "at a small cost to read performance". UUIDs spread inserts at random keyspace positions.
  - Queue-like "moving hotspots" are not fixed by load-based splitting.
  - Source: [CockroachDB: Understand hotspots](https://www.cockroachlabs.com/docs/dev/understand-hotspots) [fetched via search]
- **ID generation as physical design (Instagram).** Instagram generates 64-bit IDs that embed timestamp, logical shard ID and sequence, produced inside Postgres via PL/pgSQL — [Instagram Engineering: Sharding & IDs](https://instagram-engineering.com/sharding-ids-at-instagram-1cf5a71e5a5c) [doc]
- **Materialized views (PostgreSQL).** REFRESH MATERIALIZED VIEW recomputes fully. CONCURRENTLY avoids blocking readers but needs a unique index and is slower — [PG docs: REFRESH MATERIALIZED VIEW](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html) [doc]. Indexed views (SQL Server) and Oracle MVs with query rewrite are maintained automatically, which shifts cost onto writes — [SQL Server indexed views](https://learn.microsoft.com/en-us/sql/relational-databases/views/create-indexed-views) [doc]
- **Fillfactor (PostgreSQL).** A fillfactor below 100 leaves room in each page so UPDATEs can stay on the same page (HOT updates), which reduces index maintenance. Changing it affects only newly written pages until the table is rewritten — [PG docs: CREATE TABLE storage parameters](https://www.postgresql.org/docs/current/sql-createtable.html) [doc]
- **Clustering (PostgreSQL).** CLUSTER physically reorders a table by an index once. It takes an ACCESS EXCLUSIVE lock, and the order is not maintained afterwards — [PG docs: CLUSTER](https://www.postgresql.org/docs/current/sql-cluster.html) [doc]. pg_repack does the rewrite or reorder online with only brief locks — [pg_repack](https://github.com/reorg/pg_repack) [doc]
- **TOAST.** Large values are compressed and/or moved out of line. Per-column STORAGE (PLAIN/EXTERNAL/EXTENDED/MAIN) and the compression method (pglz/lz4, PG14+) are tunable — [PG docs: TOAST](https://www.postgresql.org/docs/current/storage-toast.html) [doc]
- **Write amplification as a storage-engine choice (Uber).** Uber cited Postgres write amplification on secondary indexes and replication behavior as reasons for moving to MySQL/InnoDB. Engine choice is itself a physical-design lever — [Uber: Why Uber Engineering switched from Postgres to MySQL](https://www.uber.com/blog/postgres-to-mysql-migration/) [doc]
- **Online schema change tooling (MySQL).**
  - InnoDB online DDL supports many ALTERs with ALGORITHM=INSTANT/INPLACE and LOCK=NONE. Others need a table copy — [MySQL online DDL](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl.html) [doc]
  - gh-ost does triggerless online migrations driven by the binlog, with throttling — [gh-ost](https://github.com/github/gh-ost) [doc]

### Inferences
- **Granularity.** Mostly per table or per partition. Sharding and vertical partitioning act per database or service.
- **Cost and downtime, cheapest first:**
  - fillfactor or storage parameter: metadata only, affects future pages
  - add partition, or detach for old-data lifecycle: near-online
  - MV creation or refresh: CPU/IO, can be scheduled
  - CLUSTER, VACUUM FULL, data type change, or a compression change that requires a rewrite: blocking, unless done online via pg_repack or gh-ost
  - repartitioning an existing large table, sharding, or an engine switch: weeks to months, needs dual-write or backfill
- **Reversibility.** It falls off sharply in that same order. Figma's view-based logical sharding is an explicit pattern for making a one-way door reversible, using feature flags and percentage rollout.
- **Observability.** Table and index size and growth, seq scans on large tables, partition pruning in EXPLAIN, the HOT update ratio (pg_stat_user_tables n_tup_hot_upd vs n_tup_upd), write IOPS per table, and range or leaseholder hotspot dashboards (CockroachDB).
- **Interactions.**
  - Partitioning changes which indexes are useful: local indexes, and no global unique constraints in PG.
  - Partitioning makes vacuum cheaper and statistics per-partition.
  - MVs substitute for indexes or caches.
  - Sharding removes FKs and global uniqueness, and moves routing into middleware (C6) or the app (C9).

### Gaps
- No quantitative cross-engine data on typical downtime per DDL class. This is engine- and version-specific.
- Lakehouse and columnar storage choice was left to the sibling researcher.

## Q2. Statistics, cardinality and plan stability (C3)

### Takeaway
Between knobs and hints sits a distinct lever class: changing *what the optimizer knows* (statistics) and *pinning what it chooses* (plan baselines). These are cheap, online, per-table/column or per-query, and very reversible. That makes them good first actions for an agent. The main risk is freezing a plan that later goes stale.

### Cited Findings
- **PostgreSQL.**
  - CREATE STATISTICS builds extended statistics on column groups: functional dependencies, n-distinct, MCV lists, and expressions (PG14+). They fix estimation errors from correlated columns — [PG docs: CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html) [doc]
  - default_statistics_target and per-column ALTER TABLE ... SET STATISTICS control histogram and MCV sizes — [PG docs: planner config](https://www.postgresql.org/docs/current/runtime-config-query.html) [doc]
- **MySQL 8.** ANALYZE TABLE ... UPDATE HISTOGRAM creates column histograms without an index. innodb_stats_persistent_sample_pages controls sampling depth — [MySQL optimizer statistics](https://dev.mysql.com/doc/refman/8.0/en/optimizer-statistics.html) [doc]
- **Aurora PostgreSQL Query Plan Management (apg_plan_mgmt).**
  - Captures plans keyed by a normalized SQL hash with literals removed, and stores them in apg_plan_mgmt.plans / dba_plans with status and enabled flags plus an outline.
  - Plans are promoted via evolve_plan_baselines or set_plan_status. copy_outline copies plans between statements (v2.3+).
  - Version 3.0 shipped for Aurora PG 18.3 on June 10, 2026.
  - Sources: [Aurora QPM docs](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Optimize.html) [fetched via search]; [QPM release notes](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/auroraqpm.updates.html)
- **SQL Server.**
  - Query Store persists query text, plans and runtime stats over time and allows plan forcing — [Query Store](https://learn.microsoft.com/en-us/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store) [doc]
  - Automatic tuning (FORCE_LAST_GOOD_PLAN) detects plan-choice regressions and forces the last good plan automatically — [SQL Server automatic tuning](https://learn.microsoft.com/en-us/sql/relational-databases/automatic-tuning/automatic-tuning) [doc]
- **Oracle SQL Plan Management.** Plan baselines accept only verified plans, and new plans are evolved after verification — [Oracle SPM overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/overview-of-sql-plan-management.html) [doc]
- **pg_hint_plan.** Supports a hint table that attaches hints to normalized query text without changing the app — [pg_hint_plan](https://github.com/ossc-db/pg_hint_plan) [doc]

### Inferences
- **Granularity.**
  - Statistics: per column or column group, per table.
  - Sampling target: global or per column.
  - Baselines and Query Store forcing: per query (normalized statement).
- **Cost and reversibility.** ANALYZE is online and cheap to moderate. A higher statistics target raises ANALYZE time and planning time. Baselines are instantly reversible: unforce, or set the plan status to rejected.
- **Risks.**
  - A forced plan becomes wrong as data distribution shifts, or forcing fails after schema changes. Forcing also suppresses better new plans unless an evolve process runs.
  - Extended statistics only help predicates the planner can match.
- **Observability.**
  - EXPLAIN ANALYZE estimated vs actual rows (q-error).
  - pg_stat_statements mean/stddev of time, and per-query plan-hash changes (Query Store regressed-queries report).
  - Statistics staleness: last_analyze, and modifications since analyze.
- **Interactions.**
  - Better statistics can make hints unnecessary.
  - Adding an index (classic trio) invalidates baselines, or is ignored by them.
  - Partitioning (C1) multiplies the stats objects.
  - Analyze scheduling belongs to maintenance (C4).

### Gaps
- No source fetched this session on CockroachDB/Neon/AlloyDB plan stability features. AlloyDB and Cockroach have their own plan-management features, but I did not verify them.

## Q3. Maintenance and background work (C4): vacuum/autovacuum, bloat, analyze, reindex, checkpoints/WAL, backups

### Takeaway
Background work is both a lever and a root cause (D-Bot's "Harmful Background Tasks"). For MVCC engines, the dominant production failure modes are:
- vacuum that cannot keep up, or is blocked by long transactions or replication slots
- the resulting bloat
- in the extreme, transaction-ID wraparound, which forces the DB to stop accepting writes

### Cited Findings
- **PostgreSQL vacuum and wraparound.** Postgres must VACUUM to reclaim dead tuples, update the visibility map, and freeze XIDs. Without freezing, it eventually refuses new XIDs to prevent wraparound data loss — [PG docs: Routine vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) [doc]
- **GitLab.**
  - Anti-wraparound autovacuum launches when a table's oldest unfrozen XID age reaches autovacuum_freeze_max_age, and "cannot be skipped and won't auto-cancel" — [GitLab issue: wraparound & freeze-age monitoring](https://gitlab.com/gitlab-org/gitlab/-/issues/602137) [fetched via search]
  - GitLab's 2021-05-18 production incident: "Long-running CREATE INDEX blocking vacuum", with wraparound monitoring added as a follow-up — [GitLab production issue 4633](https://gitlab.com/gitlab-com/gl-infra/production/-/issues/4633)
  - GitLab notes that large self-managed instances often run overly conservative default autovacuum settings — [GitLab issue 600630](https://gitlab.com/gitlab-org/gitlab/-/issues/600630)
  - GitLab runbook query for transactions older than half the max age — [GitLab runbook: pg_xid_wraparound_alert](https://runbooks.gitlab.com/patroni/pg_xid_wraparound_alert/)
- **Other wraparound outages.** Mandrill (Mailchimp) and Sentry have public wraparound postmortems — [Mailchimp: Mandrill outage](https://mailchimp.com/what-we-learned-from-the-recent-mandrill-outage/) [fetched via search]; [Sentry: Transaction ID wraparound in Postgres](https://blog.sentry.io/transaction-id-wraparound-in-postgres/) [doc]
- **Figma.** Vacuum operations became a reliability problem at multi-TB table sizes. This was one motivation for sharding — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]
- **OpenAI.** Query refinements were made to reduce interference with autovacuum, along with stricter timeouts on idle and long-running transactions — [InfoQ on OpenAI's Postgres](https://www.infoq.com/news/2026/02/openai-runs-chatgpt-postgres) [fetched]
- **Reindex.** REINDEX CONCURRENTLY (PG12+) rebuilds bloated indexes without blocking writes, at the cost of extra I/O and time — [PG docs: REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) [doc]
- **Checkpoints and WAL.** checkpoint_timeout and max_wal_size trade crash-recovery time and full-page-write volume against I/O spikes — [PG docs: WAL configuration](https://www.postgresql.org/docs/current/wal-configuration.html) [doc]

### Inferences
- **Granularity.** Autovacuum thresholds and cost limits are global, but also settable per table via storage parameters (autovacuum_vacuum_scale_factor, etc.). Manual VACUUM, ANALYZE and REINDEX run per table or index.
- **Cost and downtime.**
  - VACUUM and REINDEX CONCURRENTLY are online, but consume I/O and can hurt foreground latency.
  - VACUUM FULL and CLUSTER take exclusive locks.
  - Killing a blocking long transaction is instant but user-visible.
- **Risks.**
  - Too-aggressive vacuum steals I/O.
  - Too-lax vacuum causes bloat, plan degradation and wraparound.
  - Anti-wraparound vacuum cannot be cancelled and blocks DDL.
  - Backups and logical-replication slots pin xmin or WAL and silently block cleanup.
- **Observability.** n_dead_tup, last_autovacuum, age(datfrozenxid), relfrozenxid per table, backend_xmin / oldest xact in pg_stat_activity, pg_replication_slots, bloat estimates, pg_stat_progress_vacuum, checkpoint and WAL rates.
- **Interactions.**
  - Long transactions (C5) and replicas with hot_standby_feedback (C6) block vacuum.
  - Partitioning (C1) makes vacuum tractable.
  - Fillfactor/HOT (C1) reduces vacuum work.
  - Index count (classic trio) multiplies vacuum cost.
  - These are knob-like but need *scheduling* decisions, e.g., running batch maintenance off-peak (C8).
- **MySQL/InnoDB analog.** Purge lag and the history list length, caused by long transactions. SQL Server analog: version-store growth under snapshot isolation. I did not fetch sources for these, so treat them as unsourced pointers.

### Gaps
- No sourced quantitative guidance on backup and snapshot interference with foreground latency was gathered this session.
- InnoDB purge and SQL Server tempdb version-store sources were not fetched.

## Q4. Concurrency and transaction design (C5): isolation, locks, hot rows, long transactions, deadlocks, ID hotspots

### Takeaway
Contention problems are rarely fixed by knobs. The fixes are changes to *transaction shape*:
- shorter transactions, timeouts, and different isolation
- SKIP LOCKED queues and sharded counters
- non-sequential keys, and lock_timeout on DDL

These span the engine and application layers, which makes them a natural cross-layer category.

### Cited Findings
- **Isolation levels (PostgreSQL).** PG offers Read Committed, Repeatable Read and Serializable (SSI). Higher levels raise the rate of serialization failures that apps must retry — [PG docs: transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html) [doc]
- **Timeouts (PostgreSQL).** statement_timeout, lock_timeout and idle_in_transaction_session_timeout can be set globally, per role or database, or per session/transaction — [PG docs: client connection defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) [doc]
- **Lock modes (PostgreSQL).** Lock modes and their conflicts explain why a queued ACCESS EXCLUSIVE lock (e.g., from ALTER TABLE) blocks all later readers — [PG docs: explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html) [doc]
- **Hot rows (MySQL 8).** NOWAIT and SKIP LOCKED let queue-style workers avoid waiting on hot rows — [Percona: MySQL 8 hot rows with NOWAIT/SKIP LOCKED](https://www.percona.com/blog/mysql8-hot-rows-with-nowait-skip-locked/) [fetched via search]
- **Lock-wait diagnosis (MySQL).** Watch Innodb_row_lock_current_waits, Innodb_row_lock_waits and Innodb_row_lock_time, and confirm with performance_schema.data_lock_waits / sys.innodb_lock_waits because of MySQL Bug #94775 — [Netdata: MySQL row lock contention](https://www.netdata.cloud/guides/mysql/mysql-row-lock-contention/) [fetched via search] (secondary source)
- **Hot rows in distributed SQL (CockroachDB).** Single-row hotspots (global counters) are not fixed by range splitting or hash sharding. They need app-level redesign — [CockroachDB: Understand hotspots](https://www.cockroachlabs.com/docs/dev/understand-hotspots) [fetched via search]. The "sharded counter" remedy comes from secondary guides, e.g. [OneUptime](https://oneuptime.com/blog/post/2026-03-31-mysql-how-to-minimize-lock-contention-in-mysql/markdown) (low-authority)
- **ID hotspots.** Auto-increment IDs create hotspots in sharded or distributed layouts. Figma hashes shard keys and Instagram embeds the shard in the ID — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]; [Instagram IDs](https://instagram-engineering.com/sharding-ids-at-instagram-1cf5a71e5a5c) [doc]
- **OpenAI.** Stricter idle and long-running transaction timeouts, and rate-limited backfills and high-volume updates — [InfoQ](https://www.infoq.com/news/2026/02/openai-runs-chatgpt-postgres) [fetched]

### Inferences
- **Granularity.**
  - Isolation and timeouts: per transaction, session, role or database.
  - Hot-row fixes: per table or per code path.
  - Key-scheme changes: per table, and they need a data rewrite.
- **Reversibility.** Timeouts and isolation are instantly reversible, but can break app correctness (e.g., more serialization failures). Key and ID scheme changes are one-way.
- **Risks.** A timeout that is too tight kills legitimate batch jobs (cf. innodb_lock_wait_timeout set too low for batch jobs causing Error 1205 — [Pulse KB](https://pulse.support/kb/mysql-innodb-lock-wait-timeout-exceeded), secondary). Lowering isolation can introduce anomalies.
- **Observability.** pg_locks + pg_blocking_pids, wait events (Lock:transactionid, LWLock), the deadlock count (pg_stat_database.deadlocks), xact age, serialization-failure rate, and InnoDB lock waits.
- **Interactions.**
  - Long transactions block vacuum (C4).
  - Session-level locks and SET are incompatible with transaction pooling (C6).
  - Retries (C9) amplify load under contention.
  - DDL lock queues interact with schema change (C1/C2).

### Gaps
- No primary engineering-blog source was found this session for a hot-row incident fix at Shopify or GitHub. The search returned only vendor tutorials.

## Q5. Connection management, routing and replication middleware (C6)

### Takeaway
Middleware is a first-class optimization layer. It covers:
- pool mode and size
- multiplexing that breaks session semantics
- read/write splitting with lag-awareness
- proxy-level sharding and routing
- load shedding

Its levers are cheap and online, but they carry semantic risk: features incompatible with transaction pooling, and stale reads from replicas.

### Cited Findings
- **PgBouncer pooling modes.** Session mode supports all PG features. Transaction mode assigns a server connection only for the duration of a transaction. Statement mode forbids multi-statement transactions.
  - Never supported in transaction mode: SET/RESET, LISTEN, WITH HOLD cursors, SQL PREPARE/DEALLOCATE, PRESERVE/DELETE ROWS temp tables, LOAD, and session-level advisory locks.
  - Protocol-level prepared statements work only when max_prepared_statements > 0.
  - Startup parameters are tracked: client_encoding, DateStyle, IntervalStyle, TimeZone, standard_conforming_strings, application_name.
  - Source: [PgBouncer features](https://www.pgbouncer.org/features.html) [fetched]
- **RDS Proxy pinning.** RDS Proxy multiplexes connections but "pins" a client to a DB connection when session state is changed (e.g., SET, temp tables, some prepared statements), which defeats multiplexing — [AWS: Avoiding pinning with RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-pinning.html) [doc]
- **OpenAI.** PgBouncer runs in transaction-pooling mode to cap connections, reduce connection setup latency and absorb client spikes. Scale-out uses nearly 50 geo-distributed read replicas with p99 in the "low double-digit ms". Cascading replication is under test to cut WAL fan-out from the primary — [InfoQ](https://www.infoq.com/news/2026/02/openai-runs-chatgpt-postgres) [fetched]. The original post returned 403 to this session: [OpenAI: Scaling PostgreSQL](https://openai.com/index/scaling-postgresql/)
- **Figma DBProxy.** A Go service between the app and PgBouncer: query parser, logical/physical planner, scatter-gather, load-shedding, observability, topology management. The supported query subset covers about 90% of queries, and topology updates propagate in under 1 s — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]
- **Routing placement trade-off.** Proxy-layer routing (Figma) vs app-level routing (Notion) — [pganalyze 5mins](https://pganalyze.com/blog/5mins-postgres-figma-dbproxy-sharding-postgres) [fetched via search]
- **Other poolers and proxies.**
  - ProxySQL provides MySQL query rules (routing, rewriting, caching, blocking by regex/digest), read/write split and connection multiplexing — [ProxySQL documentation](https://proxysql.com/documentation/) [doc]
  - pgcat (sharding/load-balancing pooler) — [pgcat](https://github.com/postgresml/pgcat) [doc]
  - Odyssey (Yandex multi-threaded pooler) — [Odyssey](https://github.com/yandex/odyssey) [doc]

### Inferences
- **Granularity.** Pool size and mode are per (database, user) pool. Routing rules are per query pattern or per endpoint. Replica choice is per request.
- **Cost and reversibility.** Pooler config reloads online, and so do ProxySQL rules. Inserting a proxy into the path is a deployment change, not a DB change.
- **Risks.**
  - Switching to transaction mode silently breaks session features (above).
  - Replica reads return stale data under lag (read-your-writes violations).
  - Pools that are too small queue requests. Too large overwhelms the backend (context switching, memory).
  - Proxy bugs become a single point of failure.
  - Failover settings (DNS TTL, health-check intervals) govern downtime.
- **Observability.** Pooler SHOW POOLS/STATS (cl_waiting, avg wait), connection counts vs max_connections, replication lag (pg_stat_replication replay_lag, Seconds_Behind_Source), RDS Proxy pinning metrics, per-replica load.
- **Interactions.**
  - Prepared statements (C9) are bounded by pool mode.
  - Per-session SET-based tuning (knobs!) is unavailable under transaction pooling, so knob changes must be moved to role or database level.
  - Replicas with hot_standby_feedback hold back vacuum (C4).
  - Routing is the enabler of sharding (C1).

### Gaps
- Failover-configuration specifics (Patroni, Aurora failover timing, RDS Multi-AZ) were not sourced this session. Parts may overlap with the sibling infra researcher.

## Q6. Caching and result reuse (C7)

### Takeaway
External caches (Redis/memcached), engine result caches and MVs are all "reuse" levers. Their dominant failure mode is the cache-miss storm or thundering herd that slams the database after expiry or a cache restart.

### Cited Findings
- **OpenAI.** Cache-miss storms are listed as a failure mode for their Postgres — [InfoQ](https://www.infoq.com/news/2026/02/openai-runs-chatgpt-postgres) [fetched]
- **Figma.** Caching sits alongside read replicas in the 2022 architecture — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]
- **Discord.** Discord built Rust "data services" with request coalescing between the API and the database, so concurrent identical reads hit the DB once. This was part of its move to ScyllaDB — [Discord: How Discord stores trillions of messages](https://discord.com/blog/how-discord-stores-trillions-of-messages) [doc]
- **Engine-side result caches.** MySQL 8.0 removed the query cache. Oracle offers a server result cache (RESULT_CACHE hint and modes) — [MySQL 8.0: query cache removed](https://dev.mysql.com/doc/refman/8.0/en/query-cache.html) [doc]; [Oracle result cache](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/tuning-result-cache.html) [doc]

### Inferences
- **Granularity.** Per key, endpoint or query pattern. TTL and invalidation policy are app-defined.
- **Reversibility and cost.** Usually online and reversible, but cache removal is a load-shock risk.
- **Interactions.** Caching hides query inefficiency (C9) and can mask index needs. Coalescing and leases mitigate storms. MVs (C1) are DB-side caches with refresh cost (C4).

### Gaps
- No primary-source quantitative data on cache-hit-rate vs DB-load trade-offs gathered.

## Q7. Workload management and admission control (C8)

### Takeaway
Most engines have explicit admission and resource-governance features that classic tuners ignore. Production teams also practise "workload hygiene": isolating critical from non-critical traffic, rate-limiting backfills, and scheduling batch work off-peak.

### Cited Findings
- **SQL Server Resource Governor.** Classifies sessions into workload groups mapped to resource pools with CPU, memory and IO limits — [Resource Governor](https://learn.microsoft.com/en-us/sql/relational-databases/resource-governor/resource-governor) [doc]
- **MySQL 8 resource groups.** Bind threads to CPU sets and thread priorities, per session or via an optimizer hint — [MySQL resource groups](https://dev.mysql.com/doc/refman/8.0/en/resource-groups.html) [doc]
- **Oracle Database Resource Manager.** Consumer groups and plans for CPU, parallelism and session limits — [Oracle Resource Manager](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-resources-with-oracle-database-resource-manager.html) [doc]
- **Redshift WLM.** Queues with concurrency/memory, query monitoring rules, and automatic WLM with priorities. This is warehouse-side; details are for the sibling researcher — [Redshift WLM](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-implementing-workload-management.html) [doc]
- **PostgreSQL.** There is no built-in resource governor. Available proxies are statement_timeout, per-role settings, connection limits (ALTER ROLE ... CONNECTION LIMIT) and pool sizes — [PG docs: client defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) [doc]
- **OpenAI.** Isolates critical from non-critical workloads to avoid noisy neighbours at peak, and rate-limits backfills and high-volume updates — [InfoQ](https://www.infoq.com/news/2026/02/openai-runs-chatgpt-postgres) [fetched]
- **Load shedding in middleware.** Figma's DBProxy does load shedding — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]
- **Peloton.** Lists prioritizing OLTP vs OLAP clusters as an open problem — [Pavlo et al.](https://web.eecs.umich.edu/~linmacse/publications/2017.self-driving.cidr.pdf)

### Inferences
- **Granularity.** Per role, user or app (classification), per query class, per time window (scheduling).
- **Cost and reversibility.** Config-only and online on most engines. Reversible.
- **Risks.** Starving or killing important batch jobs. Mis-classification. Timeouts converting slowness into errors, which then triggers retries (C9).
- **Observability.** Per-class latency and throughput, queue depth, wait time, CPU per group, rate of timeouts and cancellations.
- **Interactions.** Pool size is a de-facto admission control (C6). Maintenance scheduling (C4) competes for the same windows. Parallel query (C10) needs worker limits per class.

### Gaps
- No sourced data on Aurora/AlloyDB/Neon-specific workload management features (e.g., AlloyDB's own admission controls). Not verified this session.

## Q8. Application request shape (C9): query rewriting at the source, ORM anti-patterns, batching, prepared statements, transaction boundaries, pagination, retries, schema/API changes

### Takeaway
Many of the largest wins in production engineering posts come from changing what the application asks for:
- removing redundant writes
- moving compute out of the DB
- fixing ORM-generated joins and N+1 queries
- batching and rate-limiting bulk operations
- keyset pagination

These need code changes and deploys. They are the slowest to enact for an agent, but often the most decisive.

### Cited Findings
- **OpenAI.** ORM-generated multi-table joins were a failure mode. They removed redundant writes, used lazy writes, moved some computation to the app layer, and moved shardable write-heavy workloads to Azure Cosmos DB — [InfoQ](https://www.infoq.com/news/2026/02/openai-runs-chatgpt-postgres) [fetched]
- **D-Bot root causes at the request level.** Large data fetch, poor joins, correlated subqueries, and highly concurrent commits/updates — [D-Bot](https://ar5iv.labs.arxiv.org/html/2312.01454) [fetched]
- **N+1 queries (Rails).** Eager loading (includes/preload) is the standard N+1 fix — [Rails guides: eager loading](https://guides.rubyonrails.org/active_record_querying.html#eager-loading-associations) [doc]
- **Keyset pagination.** Avoids OFFSET scans that grow with page depth — [Use The Index, Luke: no offset](https://use-the-index-luke.com/no-offset) [doc]
- **Prepared statements under pooling.** Protocol-level prepared statements behind PgBouncer require max_prepared_statements; SQL-level PREPARE is unsupported in transaction mode — [PgBouncer features](https://www.pgbouncer.org/features.html) [fetched]
- **Batching hot updates.** Breaking hot-row updates into batches with pauses — [OneUptime](https://oneuptime.com/blog/post/2026-03-31-mysql-track-innodb-row-lock-waits/view) (secondary, low authority). Throttled online migrations (gh-ost) — [gh-ost](https://github.com/github/gh-ost) [doc]
- **Correctness costs of distribution.** Sharding forces product logic to tolerate partial cross-shard commits — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]

### Inferences
- **Granularity.** Per endpoint, query or code path.
- **Cost.** Needs code change, review and deploy. Reversible by revert, but there is coordination latency (hours to days). An agent under a wall-clock limit may only be able to *recommend* these, or act via middleware substitutes: ProxySQL query rewrite rules, pg_hint_plan hint tables, rate limits.
- **Risks.** Semantic changes: stale reads, ordering differences, or lost writes under lazy writes. Retries without backoff or jitter amplify overload.
- **Observability.** pg_stat_statements / performance_schema digests (calls per request, rows per call), APM traces linking endpoint to SQL, query-tag comments (sqlcommenter-style), connection idle-in-transaction time.
- **Interactions.** Shapes everything downstream: index needs, cache efficacy, lock contention, pooling compatibility.

### Gaps
- No sourced primary data on retry-storm incidents or on the prevalence of ORM anti-patterns.
- The GitLab/Shopify app-side query-review practices (e.g., GitLab's database review guidelines) were not fetched.

## Q9. Platform features, extensions and version upgrades (C10)

### Takeaway
Engine version, enabled features and extensions are a lever class in their own right:
- JIT
- parallel query
- new optimizer features
- storage engines
- managed-service-specific extensions such as Aurora QPM

They range from session-level toggles (JIT, parallel workers) to major-version upgrades with downtime or replication-based cutover.

### Cited Findings
- **JIT (PostgreSQL).** Compiles expressions and tuple deforming. It is controlled by jit and jit_above_cost, and can hurt short queries through compile overhead — [PG docs: JIT](https://www.postgresql.org/docs/current/jit.html) [doc]
- **Parallel query (PostgreSQL).** Controlled by max_parallel_workers_per_gather and related settings, and not used in many cases (e.g., writes in older versions, cursors) — [PG docs: parallel query](https://www.postgresql.org/docs/current/parallel-query.html) [doc]
- **Major upgrades (PostgreSQL).** pg_upgrade (--link) performs in-place major upgrades with downtime. Logical replication enables near-zero-downtime cutover. Statistics must be regenerated after pg_upgrade (pre-PG18) — [PG docs: pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) [doc]
- **Managed-service extensions.** Aurora QPM is an engine-specific extension for plan stability (see Q2) — [Aurora QPM](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Optimize.html) [fetched via search]
- **Engine switch.** Uber's Postgres to MySQL switch is an example of a lever at this level — [Uber blog](https://www.uber.com/blog/postgres-to-mysql-migration/) [doc]

### Inferences
- **Granularity.** JIT and parallelism: per session or query. Extensions: per database. Version: per cluster.
- **Reversibility.** Toggles are instant. Major versions are effectively one-way without a rollback replica.
- **Risks.** Plan regressions after upgrade. This is why plan baselines (C2/C3) and Query Store are typical upgrade safety nets.
- **Observability.** Per-query plan diffs before and after, JIT timing in EXPLAIN ANALYZE, parallel worker launch vs plan.

### Gaps
- Neon, AlloyDB and CockroachDB-specific feature levers (e.g., AlloyDB columnar engine, Neon branching for safe experimentation) were not verified this session. Branching or cloning as an *experimentation substrate* for the agent is likely relevant but unsourced here.

## Q10. Logical schema and data model (C2): denormalization, data types, constraints, schema/API changes

### Takeaway
Logical design levers trade write amplification and integrity for read performance. Typical moves:
- denormalize or precompute
- right-size data types
- drop or relax constraints (FKs under sharding)
- split hot and cold columns

They usually require coordinated app changes and online migration tooling.

### Cited Findings
- **Constraints under sharding.** Sharding forced Figma to drop FK and global unique-index enforcement — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]
- **Data model as root cause.** D-Bot lists "Data-specific Issues" and "Database Schema and Settings" as root-cause categories — [D-Bot](https://ar5iv.labs.arxiv.org/html/2312.01454) [fetched]
- **Type changes rewrite tables.** In Postgres, changing a column type usually requires a full table rewrite under ACCESS EXCLUSIVE, unless the change is binary-coercible — [PG docs: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) [doc]. In MySQL, ALGORITHM=INSTANT covers only some changes (e.g., adding columns) — [MySQL online DDL](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl.html) [doc]

### Inferences
- **Granularity.** Per table or column.
- **Cost.** Rewrite plus app change.
- **Risks.** Integrity loss and drift between denormalized copies.
- **Interactions.** Denormalization substitutes for joins and indexes. Wider rows affect TOAST and fillfactor (C1).

### Gaps
- No sourced comparative data on the performance impact of data-type choices (e.g., int4 vs int8, UUIDv4 vs UUIDv7 index locality). UUIDv7 locality is a commonly cited lever but was not verified this session.

## Q11. Cross-cutting attributes for the problem definition (synthesis)

### Takeaway
For an agent working under a dollar budget and a wall-clock limit, each action is best described by these attributes:
- the layer
- the target object and its granularity
- the change mechanism (config reload / DDL online / DDL blocking / data rewrite / code deploy / topology change)
- the reversibility class (instant / cheap revert / costly revert / one-way)
- blast radius
- the semantic risk (correctness vs performance-only)
- time-to-effect
- the observability signals used to verify it

### Cited Findings
- Peloton explicitly calls for measuring each action's effect so its deployment can be scheduled, and names interference between autonomous components as an open problem — [Pavlo et al.](https://web.eecs.umich.edu/~linmacse/publications/2017.self-driving.cidr.pdf)
- Industrial practice for one-way changes is staged rollout with rollback: Figma's percentage rollout behind feature flags, with rollback in seconds — [Figma blog](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) [fetched]

### Inferences
Summary matrix (my synthesis from the sections above):

| Category | Typical granularity | Change mechanism | Reversibility | Semantic risk |
|---|---|---|---|---|
| C1 Physical layout | table / partition / DB | DDL, rewrite, migration | low to one-way | low to high (sharding) |
| C2 Logical schema | table / column | DDL + app deploy | low | high |
| C3 Stats & plan stability | column / query | ANALYZE, baseline API | instant | low |
| C4 Maintenance | global / table | config, scheduled jobs | instant | low (wraparound if neglected) |
| C5 Concurrency/txn | session / txn / code path | config + app change | instant to low | medium to high (isolation) |
| C6 Pooling/routing | pool / route / request | proxy config, deployment | instant | medium (session features, stale reads) |
| C7 Caching | key / endpoint | app/infra config | instant | medium (staleness, storms) |
| C8 Workload mgmt | role / class / time window | config | instant | low to medium |
| C9 App request shape | endpoint / query | code deploy | revert | medium |
| C10 Features/versions | session to cluster | toggle to upgrade | instant to one-way | medium (plan regressions) |

- **Key cross-category interactions an agent must model:**
  - long transactions (C5) block vacuum (C4), which causes bloat (C1), which degrades plans (C3)
  - transaction pooling (C6) rules out session-level SET knobs and SQL PREPARE (C9)
  - partitioning (C1) changes index and statistics granularity
  - replicas (C6) plus hot_standby_feedback hold back vacuum (C4)
  - plan baselines (C3) can mask or ignore new indexes
  - caching (C7) hides query inefficiency until a miss storm
  - retries (C9) plus timeouts (C8) amplify overload
- **Safest first actions for a budgeted agent:** C3, C4 and C8 config levers (online, instantly reversible). **Needs human gate or staged rollout:** C1, C2, C9 and C10 major changes.

### Gaps
- No empirical source quantifies the frequency of each category among real production incidents. D-Bot's 539-anomaly distribution is by application, not by category, in what I could extract.
