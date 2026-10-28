# Tunable dimensions at the infrastructure layer, in cloud-native/serverless DBs, OLAP warehouses and lakehouses (for a holistic, budgeted, LLM-agent optimization harness)

Provenance legend (important for the report writer):
- **[V]** = verified this session through search results or a page fetch of the cited URL.
- **[K]** = canonical vendor or paper URL whose content I am stating from prior knowledge (cutoff mid-2026) and did not re-fetch this session. Treat [K] numbers as "check before quoting". Lines with no tag are [V].

Scope: OS/kernel, storage/hardware/instances/pricing, cloud-native/serverless OLTP, OLAP warehouses, lakehouse table formats, data lifecycle, and cost as an objective. In-engine OLTP physical design, statistics, pooling and caching are covered by a sibling researcher.

---

## Q1. What is a principled, engine-agnostic umbrella taxonomy for these layers?

### Takeaway
The levers fall into eight families: (A) host OS/kernel, (B) storage and hardware provisioning, (C) compute shape and purchasing model, (D) elasticity/autoscaling policy, (E) topology and placement, (F) data layout (physical organization of data in files/blocks/micro-partitions), (G) table/metadata maintenance, (H) data lifecycle/tiering. Two cross-cutting layers sit on top: (X1) engine/format choice and (X2) the cost-metering model, which sets what "cheaper" means. The families differ most on two axes: **reversibility** and **who pays for the change**. Some changes are cheap knobs that apply instantly (sysctl, warehouse size, auto-suspend). Others are data rewrites that cost real compute and are slow to undo (re-clustering, re-partitioning, compaction, format upgrades). Commitments (RIs, slot commitments) are financial actions that cannot be undone.

### Cited Findings
- Lakehouse framing: open file formats on object storage plus a transactional metadata layer, with the engine doing caching, auxiliary data structures and data layout optimization. Armbrust et al., CIDR 2021 — [CIDR 2021 paper](https://www.cidrdb.org/cidr2021/papers/cidr2021_paper17.pdf) [K]
- Vendors are folding several families (F, G, D) into managed "autonomous" services. In 2025 Databricks Predictive Optimization changed from opt-in to default platform behavior, and Automatic Liquid Clustering reached GA — [Databricks blog](https://www.databricks.com/blog/predictive-optimization-scale-year-innovation-and-whats-next). Snowflake Adaptive Warehouses remove warehouse size, multi-cluster, QAS and suspend/resume settings from the user's control — [Snowflake docs](https://docs.snowflake.com/user-guide/warehouses-adaptive). Redshift Serverless AI-driven scaling takes a price-performance target in place of a fixed RPU count — [AWS docs](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-capacity.html).

### Inferences
- In 2026 an agent often does not set a knob directly. It sets a *policy or target* for a managed optimizer (a price-performance slider, max performance level, compaction target size, clustering = AUTO), then checks whether that optimizer's spend is worth it. The taxonomy should therefore have a dimension "direct knob vs. delegated-to-managed-optimizer".
- Per-category attributes the harness should model: granularity (host / volume / cluster / warehouse / table / partition / file), reversibility (instant / restart / rewrite / irreversible-financial), change cost ($ and downtime), risk, observability signals, interactions. The sections below fill these in.

### Gaps
- I found no published, vendor-neutral taxonomy that covers infra, warehouse and lakehouse levers together. The taxonomy above is my own synthesis.

---

## Q2. OS / kernel / filesystem / network (family A)

### Takeaway
These are cheap, host-scoped and mostly reversible (sysctl at runtime; some need a reboot or DB restart). Payoff depends on the engine and is version-sensitive. The THP advice changed for MongoDB 8.0, so "best practice" must be looked up per engine and version, not hard-coded. On managed services (RDS, Aurora, Snowflake, BigQuery) this family is mostly **not accessible**.

### Cited Findings
- Redis, PostgreSQL and MongoDB ≤7.0: disable THP. Redis warns about copy-on-write overhead during background saves. PostgreSQL's random buffer access pattern gets little from 2 MB THP and pays compaction overhead. PostgreSQL's `huge_pages` uses explicitly reserved huge pages, which is a separate mechanism — [StackHarbor KB](https://stackharbor.com/en/knowledge-base/transparent-huge-pages-database-latency/); [Netdata MongoDB guide](https://www.netdata.cloud/guides/mongodb/mongodb-disable-transparent-huge-pages/)
- MongoDB 8.0 reverses this: enable THP on x86_64 because of its upgraded TCMalloc. These are secondary sources and the official doc was not checked — [Netdata](https://www.netdata.cloud/guides/mongodb/mongodb-disable-transparent-huge-pages/)
- `madvise` is a middle setting that lets each process opt in — [Cloudron forum thread](https://forum.cloudron.io/topic/2721/please-disable-transparent-hugepage/11) (forum, weak source)
- PostgreSQL `huge_pages` (try/on/off) and `shared_memory_type` are server parameters that need a restart — [PostgreSQL docs](https://www.postgresql.org/docs/current/runtime-config-resource.html) [K]

### Inferences
- Example actions: THP mode (never/madvise/always) and defrag mode; explicit hugepages (vm.nr_hugepages); vm.swappiness and vm.dirty_ratio/dirty_background_ratio; I/O scheduler (none/mq-deadline for NVMe); NUMA policy (numactl --interleave, zone_reclaim_mode=0); filesystem (XFS/ext4), mount options (noatime), readahead; network (somaxconn, TCP buffer sizes, IRQ affinity/RSS); CPU governor/C-states. I did not re-verify the per-knob guidance this session, so the report should cite engine docs per knob.
- Granularity: host. Reversibility: high (runtime sysctl), but hugepage reservation and DB shared-memory changes need a restart, which means downtime. $-cost: about zero, apart from experiment time. Risk: a host-wide side effect on co-located processes; reserved hugepages that go unused waste RAM; failures show up as latency tails, not as errors. Observability: /proc/meminfo (AnonHugePages, HugePages_Free), khugepaged CPU, compaction stalls, iostat await/util, numastat, p99 latency. Interactions: memory sizing (C) and engine buffer settings.

### Gaps
- I did not fetch authoritative 2026 kernel or vendor docs for the I/O scheduler, NUMA or network-stack tuning of databases. Those need primary sources.

---

## Q3. Storage & hardware & purchasing (families B, C)

### Takeaway
On AWS, storage performance is now mostly *provisioned separately from capacity* (gp3, io2). That makes IOPS and throughput first-class, fairly reversible knobs with direct $ cost. Instance family, architecture and size are the biggest $ lever. Purchasing model (on-demand / reserved / savings plan / spot) is a financial lever with no performance effect, except that spot capacity can be interrupted.

### Cited Findings
- gp3: 3,000 IOPS and 125 MiB/s baseline included with storage. It can be provisioned up to 80,000 IOPS and 2,000 MiB/s for an extra fee, with no burst credits — [AWS EBS gp3 docs](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.md). (The 80k/2,000 figures reflect a recent limit increase. Older third-party pages say 16k/1,000.)
- io2 Block Express: up to 256,000 IOPS and 4,000 MiB/s per volume on Nitro instances, designed for sub-500 µs average latency at 16 KiB — [AWS EBS provisioned IOPS docs](https://docs.amazonaws.cn/en_us/ebs/latest/userguide/provisioned-iops.md); [AWS EBS volume types](https://aws.amazon.com/tr/ebs/volume-types/). AWS advises io2 when you need more IOPS than gp3, low latency or consistent performance — [AWS EBS details](https://aws.amazon.com/ebs/details/)
- Anecdotal: a 16-volume gp3 LVM stripe performed about the same as io2 BX for DB writes, with roughly 2x read latency (2023, a single region) — [InterSystems community](https://community.intersystems.com/node/549321)
- Graviton4 (RDS): up to 40% higher performance and up to 29% better price-performance than Graviton3. db.m8g.xlarge costs $0.341/h vs $0.342/h for m7g (vendor benchmark) — [AWS Database Blog](https://aws.amazon.com/blogs/database/leveling-up-amazon-rds-with-aws-graviton4-benchmarks/)
- EBS volume modifications (type/size/IOPS/throughput) can be applied while the volume is in use. After a modification there is a cooldown (historically 6 hours) before the same volume can be modified again — [AWS EBS modify volume docs](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html) [K]
- Spot Instances get a two-minute interruption notice — [AWS EC2 spot interruption notices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html) [K]

### Inferences
- Example actions: volume type swap (gp2→gp3, gp3↔io2), provision IOPS/throughput, stripe volumes, local NVMe instance-store (fast but ephemeral, so it needs replication or rebuild), instance family (memory-optimized r*, compute c*, storage-optimized i*), architecture (x86→ARM, which requires binary/extension compatibility), right-size up or down, purchasing (RI/Savings Plans for the steady baseline, spot for stateless or retryable analytics workers, on-demand for bursts).
- Reversibility: EBS changes happen online but the modification cooldown makes them *rate-limited*. That matters for an agent trying rapid A/B tests. Instance resize = restart or failover (seconds to minutes of downtime; Multi-AZ failover shrinks this). Commitments are irreversible financial actions, so the harness should gate them behind human approval or very high confidence.
- Observability: VolumeQueueLength, read/write IOPS vs provisioned, throughput vs cap, CPU credit balance (for burstable t-family), memory pressure/swap, cache hit ratio, EBS-optimized instance bandwidth cap (an instance-level ceiling that can hide behind volume provisioning).
- Interactions: memory size ↔ buffer pool/working set ↔ IOPS demand (more RAM can replace provisioned IOPS); the instance-level EBS bandwidth cap bounds volume throughput; ARM migration interacts with OS-level tuning and extensions.

### Gaps
- No primary source fetched for the current RI/Savings Plan discount levels or the exact EBS modification cooldown in 2026.
- No independent (non-vendor) Graviton4 DB benchmark found.

---

## Q4. Cloud-native / serverless operational databases (families C, D, E)

### Takeaway
Serverless engines turn sizing into an *autoscaling policy*: min/max capacity, scale-to-zero/auto-pause delay, and sometimes a billing mode (Aurora Standard vs I/O-Optimized). Trade-offs: cold-start or resume latency vs idle cost, and per-I/O pricing vs a bundled premium. Research such as Moneyball shows that proactive (predictive) pause/resume beats reactive policies.

### Cited Findings
- Aurora Serverless v2 can scale to 0 ACUs (since Nov 2024). It pauses after inactivity and resumes on the next connection. Supported on Aurora PostgreSQL 13.15+/14.12+/15.7+/16.3+ and Aurora MySQL 3.08+ — [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-aurora-serverless-v2-scaling-zero-capacity)
- Resume takes about 15 s and storage is still billed while paused (third-party) — [The Stack](https://www.thestack.technology/aws-aurora-serverless-v2-finally-lives-up-to-its-name/); [usage.ai](https://www.usage.ai/blogs/aws/rds/aurora-serverless-v2/)
- Aurora Standard vs I/O-Optimized is chosen per cluster for price-performance and price predictability. I/O-Optimized bundles I/O into higher compute and storage prices — [Aurora pricing (China mirror)](https://www.amazonaws.cn/en/rds/aurora/pricing/); [Binadox](https://www.binadox.com/blog/aurora-serverless-v2-cost-increase-2/). A cited ACU-hour price of $0.12 (standard) vs $0.16 (I/O-Opt, us-east-1) comes from third parties and is unverified — [Neon blog](https://neon.tech/blog/postgres-autoscaling-aurora-serverless-v2-vs-neon). AWS has stated I/O-Optimized pays off when I/O is more than about 25% of Aurora spend — [AWS Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/) [K]
- Neon / Databricks Lakebase: autoscaling within a user-set CU range (1 CU = 2 GB RAM; autoscaling up to 32 CU), scale-to-zero after 5 min idle by default, and copy-on-write branches ready in about 1 s regardless of size — [Databricks Lakebase autoscaling docs](https://docs.databricks.com/aws/en/oltp/projects/autoscaling); [Neon Lakebase page](https://neon.com/lakebase); [Neon vs Lakebase](https://neon.com/docs/introduction/neon-and-lakebase)
- Moneyball (PVLDB 15, 2022) predicts per-database pause/resume patterns in Azure SQL DB Serverless. It resumes resources ahead of demand and skips reclaiming them during short idle gaps, balancing QoS against cost. It is used in production — [VLDB paper](https://www.vldb.org/pvldb/vol15/p1279-poppe.pdf); [MSR page](https://www.microsoft.com/en-us/research/publication/moneyball-proactive-auto-scaling-in-microsoft-azure-sql-database-serverless/). A follow-up appeared at SIGMOD 2024 ("Proactive Resume and Pause of Resources for Microsoft Azure SQL Database Serverless") — [DBScholar](https://rmarcus.info/dbscholar/papers/12637)
- Azure SQL Hyperscale separates compute from page servers and log service and supports named replicas and fast scale — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/service-tier-hyperscale) [K]
- AlloyDB has a columnar engine and read pools — [Google Cloud AlloyDB docs](https://cloud.google.com/alloydb/docs/overview) [K]
- Distributed SQL placement: CockroachDB range splits, leaseholder and replica placement through zone configs / multi-region table localities (REGIONAL BY ROW, GLOBAL) — [CockroachDB multi-region docs](https://www.cockroachlabs.com/docs/stable/multiregion-overview) [K]. Spanner automatic load-based splitting and instance configuration (regional/multi-region), with compute in nodes/processing units and managed autoscaler options — [Spanner docs](https://cloud.google.com/spanner/docs/schema-and-data-model) [K]

### Inferences
- Example actions: min/max ACU/CU/vCore, auto-pause delay, billing mode (Standard↔I/O-Optimized; AWS allows the switch with limits on how often), add/remove read replicas or named replicas, replica autoscaling policy, Multi-AZ on/off, region placement (leaders, follower reads, table locality), branching for safe experiments (Neon/Lakebase branches are an ideal **experiment substrate** for an agent).
- Granularity: cluster/instance/replica; region/table/row for distributed SQL. Reversibility: autoscaling bounds are instant; the billing-mode switch is frequency-limited [K]; re-homing data across regions means data movement (slow, $ egress).
- Risk: scale-to-zero + SLO means cold-start p99 violations. A max-capacity cap too low causes throttling; too high causes runaway spend. Minimum capacity also bounds the buffer pool, so scaling down evicts cache and post-scale latency spikes.
- Observability: ACU/CU utilization, scaling events, resume latency, I/O request counts (to pick a billing mode), replica lag, per-region latency, hot-range/hot-split metrics.
- Interactions: connection pooling (sibling scope) interacts with pause/resume; buffer-cache warmth ↔ min capacity; cross-region topology ↔ egress cost (H/X2).

### Gaps
- I did not verify current official Aurora ACU prices, the I/O-Optimized switch limits, or Hyperscale/AlloyDB 2026 feature specifics.

---

## Q5. OLAP warehouses (families C, D, F, G)

### Takeaway
Warehouse levers split into **compute provisioning** (size, cluster count, slots/RPUs, auto-suspend, serverless targets) and **data layout** (cluster/sort/distribution/partition keys, plus accelerators such as search optimization, materialized views, BI Engine, projections). Compute levers are instant and reversible but drive the bill linearly. Layout levers need background rewrites that are billed separately (automatic clustering credits, compaction).

### Cited Findings
- **Snowflake Gen2**: QAS is on by default for new Gen2 standard warehouses (max scale factor 2). Converting Gen1→Gen2 does not enable QAS — [Snowflake Gen2 docs](https://docs.snowflake.com/en/user-guide/warehouses-gen2). Gen2 pricing was reported as 1.35 credits/h for XS on AWS (1.25 on Azure), doubling per size; this figure is older and unverified — [iTWire](https://itwire.com/business-it-news/data/snowflake-warehouses-add-more-power-more-cost-control).
- **Snowflake Adaptive Warehouses** (GA, Enterprise+, select regions): users no longer manage size, multi-cluster, QAS or suspend/resume. Billing is per query by resources used. The remaining knobs are MAX_QUERY_PERFORMANCE_LEVEL (default XLARGE), QUERY_THROUGHPUT_MULTIPLIER (default 2; 0 = unlimited), statement queue/run timeouts, and budgets/resource monitors — [Snowflake Adaptive Compute docs](https://docs.snowflake.com/user-guide/warehouses-adaptive)
- Snowflake classic knobs: warehouse size, multi-cluster min/max and scaling policy (Standard/Economy), AUTO_SUSPEND/AUTO_RESUME. Billing is per second with a 60-second minimum each time a warehouse starts — [Snowflake compute cost docs](https://docs.snowflake.com/en/user-guide/cost-understanding-compute) [K]. Clustering keys with Automatic Clustering consume serverless credits — [Snowflake automatic clustering](https://docs.snowflake.com/en/user-guide/tables-auto-reclustering) [K]. Search Optimization Service adds storage and compute cost — [Snowflake SOS](https://docs.snowflake.com/en/user-guide/search-optimization-service) [K]
- **BigQuery**: on-demand (per TiB scanned) and Editions (Standard/Enterprise/Enterprise Plus) slot capacity can be mixed per project. Reservations autoscale; Enterprise and Enterprise Plus support baseline slots; commitments are optional (1-yr/3-yr discounts listed as 20%/40%) — [BigQuery editions docs](https://docs.cloud.google.com/bigquery/docs/editions-intro). On-demand is quoted at $6.25/TiB with the first TiB free; slot-hour rates are quoted at $0.04/$0.06/$0.10 by edition (third-party, check against pricing) — [DoiT](https://www.doit.com/blog/bigquery-cost-optimization). Partitioning and clustering reduce bytes scanned, which directly reduces on-demand cost — [BigQuery partitioned tables](https://cloud.google.com/bigquery/docs/partitioned-tables) [K]
- **Redshift Serverless**: base capacity is set in RPUs (1 RPU = 16 GB memory). The alternative is AI-driven scaling with a per-workgroup price-performance target (1 = cost … 50 = balanced … 100 = performance). AWS advises setting a max capacity for cost predictability — [AWS Redshift Serverless capacity](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-capacity.html); [AWS re:Post](https://www.repost.aws/articles/ARPo2EYjL6ST-Cr9ysyPp07w/how-should-i-size-amazon-redshift-for-my-project). AWS claims up to 10x better price-performance for variable workloads (internal testing) — [AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-redshift-adds-new-ai-capabilities-to-boost-efficiency-and-productivity). Provisioned Redshift: distribution style (AUTO/EVEN/KEY/ALL), sort keys, Automatic Table Optimization, WLM queues, concurrency scaling — [Redshift distribution docs](https://docs.aws.amazon.com/redshift/latest/dg/t_Distributing_data.html) [K]
- **ClickHouse**: MergeTree ORDER BY/primary key (sparse index, index_granularity), PARTITION BY, TTL, projections, skip indexes — [ClickHouse MergeTree docs](https://clickhouse.com/docs/engines/table-engines/mergetree-family/mergetree) [K]
- Research: rule-based managed clustering (e.g., Snowflake) vs workload-driven, instance-optimized layouts. Qd-tree (SIGMOD 2020) learns workload-aware block partitioning and reports more than 10x speedups over existing blocking schemes — [arXiv 2004.10898](https://arxiv.org/pdf/2004.10898). MTO (SIGMOD 2021) handles multi-table layouts through join-induced predicates and partial reorganization, with up to 93% fewer blocks accessed and 75% faster queries — [MSR MTO paper](https://microsoft.com/en-us/research/uploads/prod/2021/04/msr-mto-sigmod.pdf)

### Inferences
- Granularity: warehouse/workgroup/reservation (compute); table/column (layout). Reversibility: compute = instant; layout key change = background rewrite (hours, credits); dropping an accelerator is instant but rebuilding it is not.
- Cost-performance shape: a larger warehouse costs proportionally more per second, but a query that parallelizes well finishes proportionally sooner, so per-query cost stays roughly flat while latency drops. The win from upsizing therefore depends on parallel efficiency, and auto-suspend tail time adds cost. (Inference from the linear per-size credit doubling; the agent should measure it.)
- Risk: auto-suspend that is too short drops the local cache and triggers repeated 60-s minimums; multi-cluster max caps runaway spend; layout services can silently burn credits on high-churn tables.
- Observability: query history (bytes scanned, partitions pruned/total, spill to local/remote, queued time), warehouse load/credit metering views, slot utilization (INFORMATION_SCHEMA.JOBS), Redshift SYS_* views, ClickHouse system.query_log/system.parts.

### Gaps
- Databricks SQL warehouse specifics (serverless vs pro, cluster size, min/max scaling, IWM) were not fetched.
- Current official list prices (Snowflake, BigQuery slots) were not verified on the primary pricing pages.

---

## Q6. Lakehouses: Iceberg / Delta / Hudi (families F, G, X1)

### Takeaway
Lakehouse tuning is mostly about **file and metadata hygiene** (file size, compaction, manifests, snapshots, delete files) and **layout** (partition spec, sort/cluster/Z-order/Hilbert/liquid). It is increasingly delegated to managed maintenance (Databricks Predictive Optimization, S3 Tables, Snowflake auto-clustering). Each action is a *billed data rewrite* that creates new snapshots. Because the format is open and multiple engines share it, compatibility (format version, engine support) becomes a constraint on what the agent may change.

### Cited Findings
- **Compaction**: Iceberg `rewrite_data_files` (binpack/sort/z-order) with `target-file-size-bytes`. Official examples use about 500 MB — [Iceberg 1.8 maintenance docs](https://iceberg.apache.org/docs/1.8.0/maintenance). Iceberg's default `write.target-file-size-bytes` is 512 MB [K, not verified this session] — [Iceberg configuration](https://iceberg.apache.org/docs/latest/configuration/)
- **Snapshot expiry**: expiring snapshots removes time travel to them. Data files are deleted only once no retained snapshot references them. `write.metadata.delete-after-commit.enabled` + `previous-versions-max` bound metadata JSON growth. Manifests act as the planning index for file pruning, and `rewrite_manifests` reorganizes them — [Iceberg maintenance docs](https://iceberg.apache.org/docs/1.8.0/maintenance)
- **Delete files / MoR vs CoW**: Iceberg v3 replaces v2 positional delete files with deletion vectors (compressed bitmaps of deleted positions, stored in Puffin files, at most one per data file). v2 delete files stay readable and are converted on the next write. v3 adds row lineage (`_row_id`, `_last_updated_sequence_number`). Downgrade v3→v2 is unsupported, and v2 readers cannot read v3 — [AWS Redshift Iceberg v3 docs](https://docs.aws.amazon.com/redshift/latest/dg/iceberg-v3-features.html); [Atlan](https://atlan.com/know/snowflake/apache-iceberg-v3/); [Google OSS blog](https://opensource.googleblog.com/2025/08/whats-new-in-iceberg-v3.html). Starburst warns to check that every engine that accesses a table supports v3 before upgrading — [Starburst](https://www.starburst.io/blog/iceberg-v3/)
- **S3 Tables managed maintenance**: compaction is on by default with a 512 MB target (configurable 64–512 MB). Strategy Auto picks sort if a sort order exists, else binpack. Z-order needs the maintenance API plus a sort order. Sort and Z-order cost more than binpack — [S3 Tables maintenance docs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-maintenance.html). Compaction prices were cut on July 1 2025 (per-object −50%; per-byte −90% binpack, −80% sort/z-order) — [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-s3-tables-reduce-compaction-costs). Sort/z-order compaction launched June 2025 — [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/06/amazon-s3-sort-z-order-compaction-apache-iceberg-tables/)
- **Databricks**: Predictive Optimization (default since 2025) runs OPTIMIZE, VACUUM and ANALYZE on Unity Catalog managed tables. Automatic Liquid Clustering (`CLUSTER BY AUTO`, GA 2025) chooses keys from query telemetry with a cost-benefit check and adapts them as workload changes — [Databricks PO blog](https://www.databricks.com/blog/predictive-optimization-scale-year-innovation-and-whats-next); [Automatic Liquid Clustering announcement](https://www.databricks.com/blog/announcing-automatic-liquid-clustering); [Databricks community](https://community.databricks.com/t5/community-articles/databricks-performance-optimization-what-changed-what-still/td-p/163324). Liquid clustering is recommended over partitioning + Z-order for most new tables (community article).
- Delta OSS: OPTIMIZE (bin-packing), Z-ORDER BY, VACUUM retention, data skipping stats on the first N columns (default 32) — [Delta optimizations](https://docs.delta.io/latest/optimizations-oss.html) [K]
- Hudi: table types COPY_ON_WRITE vs MERGE_ON_READ, clustering and compaction services (inline/async), cleaner policies — [Hudi table types](https://hudi.apache.org/docs/table_types) [K]
- **Online layout research**: OREO (ICDE 2024) decides when to switch layouts using Metrical Task Systems, with worst-case guarantees and no workload assumptions. It reports up to 32% lower combined query+reorg time vs one static optimized layout, and uses Z-order/sort/Qd-tree candidates — [arXiv 2405.04984](https://arxiv.org/pdf/2405.04984); [ICDE slides](https://cs.stanford.edu/people/paulliu/files/icde-2024-slides.pdf)

### Inferences
- Example actions: set target file size; schedule or trigger compaction (binpack/sort/zorder); change sort order; evolve partition spec (Iceberg partition evolution is metadata-only for new data, but old data keeps its old layout until rewritten); switch CoW↔MoR write mode per operation (delete/update/merge); expire snapshots / set retention; rewrite manifests; remove orphan files; collect column stats/NDV (Puffin) and bloom filters; tune Parquet row-group size, page size, compression codec (zstd/snappy) and dictionary encoding; choose catalog (Unity/Polaris/Glue/Nessie, which affects commit throughput and governance) and query engine (Spark/Trino/Dremio/DuckDB/StarRocks, which differ in pruning and delete-file support); add a cache layer (Databricks disk cache, Alluxio).
- Reversibility: table properties are instant but affect only *future* writes. Rewrites are reversible only through time travel until snapshots expire. **Snapshot expiry/VACUUM is destructive and irreversible** (it removes time-travel/rollback ability) and should be gated. A format-version upgrade is one-way.
- $-cost: compaction is a compute job (engine cluster time, or managed per-object/per-byte fees); object-store request costs (GET/LIST) scale with file count, so the small-file problem raises both latency and cost; retained snapshots raise storage cost.
- Risk: commit conflicts between compaction and streaming writers (optimistic concurrency retries/failures); compaction that rewrites hot partitions; layouts tuned for one engine regress another engine; MoR read amplification when delete files accumulate.
- Observability: files per partition and size histogram (Iceberg `files`/`partitions` metadata tables, Delta DESCRIBE DETAIL), delete-file count, manifest count/size, snapshot count, planning time vs execution time, files scanned/pruned per query, object-store request metrics, compaction job cost.
- Interactions: layout ↔ engine pruning capability; compaction cadence ↔ ingest pattern (streaming creates small files); retention ↔ compliance/time-travel needs; catalog ↔ concurrency.

### Gaps
- Jigsaw and other "learned layout" papers were not fetched. Learned partitioning beyond Qd-tree/MTO/OREO is not covered here.
- No 2026 primary docs fetched for Snowflake-managed Iceberg tables, Glue auto-compaction, Polaris/Nessie or Alluxio.
- No quantitative independent benchmark of liquid clustering vs Z-order was found.

---

## Q7. Data lifecycle and cost/FinOps as an objective (families H, X2)

### Takeaway
Cost metering differs fundamentally between systems: per second of provisioned compute (Snowflake warehouses, EC2), per byte scanned (BigQuery on-demand), per slot-hour/RPU-hour (BigQuery editions, Redshift Serverless), per query by resources used (Snowflake Adaptive), per I/O request (Aurora Standard), per object/byte compacted (S3 Tables). The *same* action (e.g., clustering) can cut cost under per-byte-scanned billing yet barely move it under provisioned billing. So the harness has to model cost per platform's meter.

### Cited Findings
- BigQuery on-demand bills per TiB processed; editions bill slot capacity; the two can be combined per project — [BigQuery editions docs](https://docs.cloud.google.com/bigquery/docs/editions-intro)
- Snowflake Adaptive bills per query by compute/software resources used, with QAS included — [Snowflake Adaptive docs](https://docs.snowflake.com/user-guide/warehouses-adaptive)
- Aurora Standard charges per I/O, while I/O-Optimized bundles it — [Aurora pricing](https://www.amazonaws.cn/en/rds/aurora/pricing/)
- S3 Tables compaction is billed per object and per byte processed — [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-s3-tables-reduce-compaction-costs)
- Lifecycle tools: S3 storage classes and lifecycle rules (Standard→IA→Glacier; Intelligent-Tiering) — [S3 lifecycle docs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html) [K]; ClickHouse TTL moves/deletes and storage-policy volumes (hot/cold disks) — [ClickHouse MergeTree TTL](https://clickhouse.com/docs/engines/table-engines/mergetree-family/mergetree) [K]; BigQuery long-term storage pricing for tables/partitions unmodified for 90 days and partition expiration — [BigQuery storage pricing](https://cloud.google.com/bigquery/pricing) [K]; Iceberg snapshot expiry (above).

### Inferences
- Lifecycle actions: retention/TTL, partition expiration, tiering (hot SSD → object store → archive), archival with restore latency, deleting unused tables/MVs/indexes/snapshots. Reversibility: deletion is irreversible; archival is reversible, but restores cost money and time (hours for deep archive). Interactions: compliance, time travel, query SLOs on cold data.
- For the harness's budget, three cost streams should be accounted separately: (1) steady-state run-rate change from the action ($/h or $/month), (2) one-time change cost (rewrite compute, compaction fees, data movement/egress, downtime), (3) experiment cost (shadow clusters, branches, replays, plus agent tokens). Payback period = (2)+(3) divided by the reduction in (1), which gives a natural accept/reject rule under a fixed dollar budget.
- Managed optimizers (PO, auto-clustering, S3 Tables, Adaptive, AI-driven scaling) shift cost into opaque background line items. The agent needs per-service metering views to judge them.

### Gaps
- No academic paper fetched on cloud instance selection or cost-aware configuration (e.g., CherryPick, Ernest-style systems). These are worth adding from primary sources.
- No FinOps Foundation or independent case study with measured savings was fetched.
