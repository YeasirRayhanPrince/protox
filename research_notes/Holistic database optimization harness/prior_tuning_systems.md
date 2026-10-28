# Prior (non-LLM) Automatic Database Tuning Systems: What Each Covers and Leaves Out

Scope: academic ML/RL tuners and commercial cloud autotuners, excluding LLM-based tuners (covered by a sibling note). Compiled 2026-10-26.

Method note: most findings come from paper abstracts, vendor documentation, and search-engine summaries of primary pages. I could not extract the full text of several PDFs (Van Aken et al. VLDB 2021, Das et al. SIGMOD 2019, Proto-X VLDB 2024) because no PDF tooling was available in this environment and bash had no network. Claims marked **[prior knowledge, unverified]** come from my background knowledge and have no fetched source. The report writer should treat them as leads, not as citable facts.

---

## Q1. Knob tuners: what they tune, how they search, what signal they use, where they run, cost, safety, transfer

### Takeaway
Academic knob tuners optimize runtime configuration parameters, and only those, using measured execution of a fixed (usually replayed or benchmark) workload. The search methods are Bayesian optimization with Gaussian processes, deep RL (DDPG), genetic algorithms, or contextual BO. Research since 2019 has gone after the cost of samples: knob pruning, reusing past tuning data (meta-learning or workload mapping), using a clone, and safe online exploration. The real-world study (Van Aken 2021) and the commercial failure of OtterTune (2024) suggest that knob-only tuning delivers real but limited value and is hard to deploy.

### Cited Findings

**OtterTune (Van Aken, Pavlo, Gordon, Zhang, SIGMOD 2017)**
- A DBMS-agnostic tuning service that reuses a repository of data from past tuning sessions. It ranks knobs with Lasso, maps the target workload to the most similar past workload by Euclidean distance over metrics, then fits a Gaussian Process regression to recommend configurations, balancing exploration and exploitation. — [Acolyer summary](https://blog.acolyer.org/2017/08/11/automatic-database-management-system-tuning-through-large-scale-machine-learning/); [GaTech lecture slides](https://www.cc.gatech.edu/~jarulraj/courses/8803-f18/slides/11_ottertune.pdf); [paper PDF](https://www.cs.purdue.edu/homes/csjgwang/CloudNativeDB/OtterTuneSIGMOD17.pdf)
- Reported 58–94% lower latency than default settings or other advisors' configurations. It produced configurations in under 60 minutes that came within 94% of expert DBA configurations. The evaluation covered MySQL, Postgres, and Actian Vector on EC2, and the slides cite about 30k training trials per DBMS. — [Acolyer summary](https://blog.acolyer.org/2017/08/11/automatic-database-management-system-tuning-through-large-scale-machine-learning/); [GaTech slides](https://www.cc.gatech.edu/~jarulraj/courses/8803-f18/slides/11_ottertune.pdf)
- Commercial arc: co-founded in March 2020 by Pavlo, Van Aken, and Bohan Zhang. It launched in May 2021 and raised a $12M Series A in 2022. — [VentureBeat](https://venturebeat.com/business/ottertune-raises-12m-to-automate-database-maintenance)
- The company announced the shutdown of its services in June 2024 (search snippet citing a June 3, 2024 announcement; I could not open the announcement). — [search result context](https://buttondown.com/jaffray/archive/the-problem-with-declarativity/comment/7e66d97b-cc09-46db-bbab-ec7a08e2ea3f)
- Pavlo's 2024 retrospective says only that "the company is dead (RIP)", that "Dana, Bohan, and I worked on this research project and startup for almost a decade", and that he is "disappointed at how a particular company treated us at the end". It gives no technical or market post-mortem. — [Pavlo, Databases in 2024](https://www.cs.cmu.edu/~pavlo/blog/2025/01/2024-databases-retrospective.html)

**Van Aken et al., "An Inquiry into ML-based Automatic Configuration Tuning Services on Real-World DBMS" (PVLDB 14(7), 2021)**
- The study evaluated OtterTune with three ML algorithms on a real Oracle installation running a real workload trace, with Société Générale co-authors. ML-generated configurations improved performance by about 45% over enterprise-grade configurations. — [PVLDB PDF](https://www.vldb.org/pvldb/vol14/p1241-aken.pdf)
- The paper criticizes prior evaluations on four counts. They used open-source DBMSs with limited tuning headroom, synthetic uniform benchmarks, and local storage rather than SAN or cloud block storage. They were also unclear about how much was really automated, since a human often picked knob bounds and starting points. The paper also identifies deployment and measurement problems that earlier research overlooked. — [PVLDB PDF](https://www.vldb.org/pvldb/vol14/p1241-aken.pdf)
- [prior knowledge, unverified] The three algorithms were GPR, DNN, and DDPG. The paper reported that GPR and DNN matched or beat DDPG, that tuning about 10–20 important knobs was enough, and that replaying the workload on a clone was hard and noisy.

**CDBTune (Zhang et al., SIGMOD 2019) and CDBTune+ (VLDB Journal 2021), Tencent / Tsinghua**
- End-to-end deep RL knob tuning with DDPG over a high-dimensional continuous knob space. It uses reward feedback instead of regression to reduce the training data needed. The authors report it beat prior tools and DBAs on real cloud databases. — [BIT pure record](https://pure.bit.edu.cn/en/publications/an-end-to-end-automatic-cloud-database-tuning-system-using-deep-r/); [CDBTune+ journal PDF](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/cdbtune-journal.pdf); [Springer](https://link.springer.com/article/10.1007/s00778-021-00670-9)

**QTune (Li, Zhou, Li, Gao, PVLDB 12(12), 2019)**
- Query-aware knob tuning. It featurizes SQL queries and uses a Double-State DDPG actor-critic that combines query features with database state. It supports query-, workload-, and cluster-level tuning and was evaluated on three DBMSs. — [PVLDB PDF](https://www.vldb.org/pvldb/vol12/p2118-li.pdf); [DBScholar](https://rmarcus.info/dbscholar/papers/h721a64cdd90a0a40)

**ResTune (Zhang et al., SIGMOD 2021, Alibaba / PKU)**
- Resource-oriented tuning. It minimizes resource use (CPU, I/O, memory) subject to throughput and latency SLA constraints, which is constrained BO. It reuses past tuning histories through an ensemble of models weighted by a meta-learned estimate of workload similarity. — [paper PDF](https://users.cs.utah.edu/~lifeifei/papers/restune-sigmod21.pdf); [CMU 15-799 copy](https://15799.courses.cs.cmu.edu/spring2022/papers/08-knobs3/zhang-sigmod2021.pdf)
- A secondary summary reports about 18x speedup over earlier methods. I did not verify this against the paper. — [paper PDF](https://users.cs.utah.edu/~lifeifei/papers/restune-sigmod21.pdf)

**OnlineTune (Zhang et al., SIGMOD 2022, "Towards Dynamic and Safe Configuration Tuning for Cloud Databases")**
- The paper's motivation is that prior tuners work in a fixed time window on a fixed workload, often on a copied instance, which is expensive, slow, and unsafe for live cloud databases. OnlineTune tunes online and treats workload and data dynamics as context. — [arXiv 2203.14473](https://arxiv.org/pdf/2203.14473)
- Method: contextual Bayesian optimization with context-space partitioning. A safety assessment combines black-box (GP) and white-box (rule) knowledge, and safe exploration uses subspace adaptation. — [arXiv 2203.14473](https://arxiv.org/pdf/2203.14473); [talk slides](https://users.cs.utah.edu/~lifeifei/papers/sigmod22-onlinetune-talk.pdf)
- Results: 14.4%–165.3% better cumulative performance and 91.0%–99.5% fewer unsafe configuration recommendations than state-of-the-art methods. — [arXiv 2203.14473](https://arxiv.org/pdf/2203.14473)

**HUNTER (Cai et al., SIGMOD 2022)**
- Hybrid online tuner for cloud DBs. A genetic algorithm warm-starts deep RL. PCA, random forest, and a fast exploration strategy shrink the search space. Stress tests run in parallel on multiple **cloned** CDB instances for "faster and safer" exploration. Reported speedups were up to 2.8x with 1 clone and 22.8x with 20 clones under the same time budget. — [DBScholar](https://rmarcus.info/dbscholar/papers/h3e719852380feec1); [Unpaywall/DOI](https://unpaywall.org/10.1145%2F3514221.3517882)

**LlamaTune (Kanellis et al., PVLDB 15(11), 2022, Microsoft / UW-Madison)**
- The authors argue that sample efficiency is the key requirement for tuning across Microsoft's "millions of databases". The method uses randomized low-dimensional embeddings (random projection), biased sampling of special knob values (e.g., 0 or -1 meaning "disabled"), and bucketization of knob values. — [arXiv 2203.05128](https://arxiv.org/pdf/2203.05128); [MSR page](https://www.microsoft.com/en-us/research/publication/llamatune-sample-efficient-dbms-configuration-tuning)
- It reached best configurations with up to 11x fewer workload runs and up to 21% higher throughput. Gains generalize across GP-BO, random-forest BO (SMAC), and RL optimizers, and across DBMS versions. — [arXiv 2203.05128](https://arxiv.org/abs/2203.05128v2)

**DB-BERT (Trummer, SIGMOD 2022; VLDB Journal 2023)**
- A pre-LLM NLP tuner. BERT extracts tuning hints (parameter and recommended value) from hundreds of text documents such as manuals and blogs. RL then decides how to combine and reweight the hints and which settings to try, using measured benchmark runs. Evaluated on Postgres and MySQL with TPC-C and TPC-H. — [DeepAI/arXiv](https://deepai.org/publication/db-bert-a-database-tuning-tool-that-reads-the-manual); [arXiv 2112.10925](https://arxiv.org/abs/2112.10925v1); [GitHub](https://github.com/itrummer/dbbert); [VLDBJ](https://link.springer.com/article/10.1007/s00778-023-00831-y)

**Zhang et al., "Facilitating Database Tuning with Hyper-Parameter Optimization: A Comprehensive Experimental Evaluation" (arXiv 2110.12654; PVLDB 2022)**
- The paper decomposes a tuning system into three modules: knob selection, the configuration optimizer, and knowledge transfer. It ablates each, concludes that HPO algorithms can be borrowed to improve DB tuning, names the best choice per module, and releases a surrogate-model benchmark to cut evaluation cost. — [arXiv 2110.12654](https://arxiv.org/abs/2110.12654)
- [prior knowledge, unverified] Specific winners: SHAP for knob importance, SMAC (random-forest BO) for high-dimensional heterogeneous spaces, and RGPE-style transfer. This work fed OpenBox-based tuners from PKU and Alibaba. The OpenBox toolkit itself is from PKU's DAIR lab (Li et al., KDD 2021).

**openGauss DBMind X-Tuner (Huawei)**
- A built-in knob tuning tool using deep RL plus global search, with train, tune, and recommend modes. If tuned parameters need a restart, the DB restarts multiple times during tuning, which is a live-system safety caveat. — [openGauss docs (5.0.0 AI sub-functions)](https://docs.opengauss.org/en/docs/5.0.0/docs/AIFeatureGuide/ai-sub-functions-of-the-dbmind.html); [X-Tuner source](https://gitcode.com/opengauss/openGauss-DBMind/tree/master/dbmind/components/xtuner)

**Newer knob/config tuners (2025–2026, non-LLM or hybrid)**
- 2025 entries include TopTune (mixed categorical and continuous knobs, ICDE 2025) and DemoTuner (demonstration RL). MFTune (arXiv 2026) is a multi-fidelity tuner for Spark SQL configuration. — [ML4DB paper list](https://github.com/LumingSun/ML4DB-paper-list); [DemoTuner arXiv](https://arxiv.org/html/2511.09998); [MFTune arXiv](https://arxiv.org/pdf/2603.16450)

### Inferences
- Signal: every academic knob tuner above optimizes **measured** performance of a benchmark or replayed workload. Their sample cost (minutes per run, often with restarts) is the binding constraint, which is why most of the field's contributions are about sample efficiency (LlamaTune, ResTune, the HPO benchmark) and transfer (OtterTune mapping, ResTune meta-learning).
- Where they run: offline on a clone or benchmark instance (OtterTune, CDBTune, QTune, LlamaTune, HUNTER with explicit clones), with OnlineTune as the main exception tuning the live instance. Live tuning forces the safety machinery OnlineTune adds.
- Coverage: knobs only. Indexes, plans, layout, and the application are treated as fixed context. QTune uses query features as an input signal but does not change queries.
- OtterTune's commercial failure is under-documented in public. Pavlo's post blames no technical cause, so any "knob tuning isn't enough" lesson is inference, not a documented finding.

### Gaps
- I found no public OtterTune post-mortem that gives business or technical reasons for the shutdown. The OtterTune blog is offline.
- I could not verify the exact Van Aken 2021 findings (algorithms compared, knob counts, tuning hours) because the PDF text was not extractable. Use the PVLDB PDF directly.
- I could not verify the specific winners in the HPO evaluation paper.
- No sources on ResTune or CDBTune production deployment scale at Alibaba or Tencent beyond author claims.

---

## Q2. Index / physical design and learned query optimization

### Takeaway
Classical physical design tools (AutoAdmin/DTA) and their cloud successors search over indexes, materialized views, and partitioning using optimizer **what-if cost estimates**. Production systems (Azure SQL, Oracle) learned that those estimates are not trustworthy enough on their own and added **measured validation with automatic revert**. RL index advisors (SWIRL and others) mostly optimize cost-model estimates and need long training. Learned query optimizers (Neo, Bao, Balsa, Lero, AutoSteer) touch only per-query plans or hints, measure execution latency, and treat indexes and knobs as fixed.

### Cited Findings

**AutoAdmin / Database Engine Tuning Advisor (Microsoft Research, Chaudhuri and Narasayya)**
- The 1998 "what-if" index analysis utility (SIGMOD 1998) let the optimizer cost hypothetical indexes without building them, estimating workload cost changes. — [DBLP/VLDB](https://www.vldb.org/dblp/db/conf/sigmod/ChaudhuriN98.html); [UBC slides](https://www.cs.ubc.ca/~rap/teaching/504/2006/slides/what_if.pdf)
- The lineage ran from the Index Tuning Wizard (SQL Server 7.0) to integrated recommendations for indexes, materialized views, and partitioning, and then to DTA, which replaced ITW in SQL Server 2005 and later. — [AutoAdmin overview (MSR)](https://microsoft.com/en-us/research/wp-content/uploads/2016/02/AutoAdmin1.pdf)

**Azure SQL Database auto-indexing (Das et al., SIGMOD 2019)**
- The service had been in production for more than 2 years at publication. It generated index recommendations for every Azure SQL database, auto-implemented them for a large fraction, and improved performance for hundreds of thousands of databases. The authors also experimented at scale on production databases. — [MSR publication page](https://www.microsoft.com/en-us/research/publication/automatically-indexing-millions-of-databases-in-microsoft-azure-sql-database/)
- The paper's outline includes separate recommenders (Missing Indexes DMV-based and DTA-based), drop-index logic, implementation and **validation**, "B-instances" (experimentation copies) with an experimentation framework, and an "Operational Experience" section covering customer feedback and lessons. — [paper PDF](https://www.microsoft.com/en-us/research/uploads/prod/2019/02/autoindexing_azuredb.pdf) (section headings only; body text not extracted)
- Brent Ozar described the paper as a candid account of where the service succeeded and where it failed. — [Brent Ozar](https://www.brentozar.com/?p=256565)

**Azure SQL automatic tuning (current product documentation)**
- The product has three options: CREATE INDEX, DROP INDEX (indexes unused for 90 days, plus duplicates; unique and PK indexes are never dropped), and FORCE LAST GOOD PLAN (automatic plan correction). Azure defaults are FORCE_LAST_GOOD_PLAN on, CREATE_INDEX off, DROP_INDEX off. Managed Instance supports only FORCE LAST GOOD PLAN. — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview)
- Safety: changes are applied only during low CPU, data I/O, and log I/O. The system can disable itself ("Disabled by the system"). Each change is verified against measured workload performance and reverted if there is no notable gain or a regression. Validation takes 30 minutes to 72 hours depending on query frequency. Recommendations applied manually via T-SQL get no auto-validation or revert. — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview)
- Coverage limits: no index recommendations for tables whose clustered index or heap exceeds 10 GB. No recommendation is made if it would push space use over 90% of max size. DROP INDEX may auto-disable when queries use index hints or the workload does partition switching. Premium and Business Critical tiers never drop unused indexes. — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview)
- The product claims to learn "horizontally from all databases on Azure" (fleet-level learning). — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview)

**Oracle Automatic Indexing (19c+, the core of Autonomous Database indexing)**
- A background task runs every 15 minutes. Candidates are identified from column usage, created **invisible and unusable**, then verified by test-executing sample workload SQL against them. Only candidates that improve measured SQL performance become visible. Unused auto indexes are later deleted (default retention 373 days). — [Oracle 19c Admin Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html)
- Regression prevention: if an index helps overall but individual statements regress, SQL plan baselines are created for those statements. The feature uses the SQL Performance Analyzer framework and has a REPORT ONLY mode. — [Oracle 19c Admin Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html)
- Limitations: local B-tree only, no temp tables, and tables need fresh statistics. Requires the Real Application Testing option. — [Oracle 19c Admin Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html)
- An "Automatic Indexing in Oracle" paper is listed for VLDB 2025. — [ML4DB paper list](https://github.com/LumingSun/ML4DB-paper-list) (venue not independently verified)

**Google AlloyDB index advisor**
- It tracks regular queries and periodically recommends CREATE INDEX statements with estimated storage size and the number of queries affected. It does **not** apply them; the user runs the DDL. On-demand analysis is available via `google_db_advisor_recommend_indexes()`, and there is a vector-index advisor flag. The docs do not state the signal used (hypothetical index or cost estimate). — [AlloyDB docs](https://docs.cloud.google.com/alloydb/docs/use-index-advisor)

**SWIRL (Kossmann, Kastius, Schlosser, EDBT 2022)**
- RL index selection that internalizes index-candidate knowledge in a preliminary training phase, generalizes to unseen query classes, and uses invalid-action masking to handle thousands of candidates. It was competitive in quality, with selection runtime up to orders of magnitude faster than competitors, on TPC-H, TPC-DS, and JOB. — [HPI news](https://hpi.de/plattner/news/news-archive/2022/swirl-selection-of-workload-aware-indexes-using-rl-accepted-edbt-2022.html); [Beyond SWIRL summary](https://rss.boorghani.com/?p=379821)
- BALANCE (PVLDB 17, 2024) calls SWIRL state of the art for dynamic workloads but notes its substantial training time on TPC-H 10GB. The exact figure was garbled in the snippet. — [BALANCE PVLDB](https://www.vldb.org/pvldb/vol17/p1642-lin.pdf)
- [prior knowledge, unverified] SWIRL's reward uses what-if optimizer cost estimates, not measured execution.
- Newer index advisors (2025–2026) include AutoIndexer (RL), Rainbow (SIGMOD 2025), and UTune (uncertainty-aware online index tuning, arXiv 2026). — [ML4DB paper list](https://github.com/LumingSun/ML4DB-paper-list); [UTune arXiv](https://arxiv.org/pdf/2601.18199)

**Learned query optimizers / hint steering**
- **Bao (Marcus et al., SIGMOD 2021):** It chooses per-query hint sets (e.g., disabling join types) on top of the native optimizer. It models this as a contextual multi-armed bandit with Thompson sampling and a tree-convolutional network trained on **measured** latency. It improved end-to-end and tail latency and learned about an order of magnitude faster than prior learned optimizers. — [Bao SIGMOD'21 PDF](https://people.csail.mit.edu/tatbul/publications/bao_sigmod21.pdf); [arXiv 2004.03814](https://arxiv.org/abs/2004.03814v1)
- **Balsa (Yang et al., SIGMOD 2022):** Deep RL optimizer without expert demonstrations. It bootstraps from a simple cost simulator, then does "safe" learning in real execution. It matched expert optimizers on JOB in about 2 hours of training and was up to 2.8x faster after more training. — [arXiv 2201.01441](https://arxiv.org/abs/2201.01441v2)
- **Lero (Zhu et al., PVLDB 16, 2023):** A pairwise learning-to-rank plan comparator on top of the native optimizer. It cut execution time by up to 70% vs. PostgreSQL native and up to 37% vs. other learned optimizers. — [PVLDB PDF](https://www.vldb.org/pvldb/vol16/p1466-zhu.pdf); [arXiv 2302.06873](https://arxiv.org/pdf/2302.06873)
- **AutoSteer (Anneser et al., PVLDB 16(12), 2023, TUM / Meta / Intel):** Extends Bao with automatic hint-set discovery for any SQL engine with optimizer knobs (PostgreSQL, PrestoDB, SparkSQL, MySQL, DuckDB). It gained up to 40% on PrestoDB. It was evaluated on a Meta PrestoDB production workload of more than 3000 daily queries scanning PBs on hundreds of nodes, focused on tail latency. — [AutoSteer paper PDF](https://www.db.in.tum.de/~anneser/autosteer-paper.pdf); [PVLDB listing](https://mail.vldb.org/pvldb/volumes/16/paper/AutoSteer%3A%20Learned%20Query%20Optimization%20for%20Any%20SQL%20Database)
- [prior knowledge, unverified] **Neo (Marcus et al., PVLDB 2019)** builds plans end-to-end with a value network, bootstrapped from expert (PostgreSQL) plans. **LOGER (Chen et al., PVLDB 2023)** restricts operators and uses an ε-beam search. Neither was fetched.

### Inferences
- Signal split. Cost-model-based advisors (DTA, SWIRL, AlloyDB, as far as the docs indicate) are cheap but inherit estimation errors. Production systems (Azure, Oracle) bolt on measured verification plus revert or plan baselines as the safety net. Learned query optimizers use measured latency but tune only plans.
- Coordination: no learned query optimizer above models how hints interact with indexes or knobs. Azure SQL couples indexes and plans only loosely, through separate validation loops.
- Fleet scale and conservatism are what makes commercial deployment work: default-off index creation, size caps, low-utilization windows, and long validation windows (up to 72h).

### Gaps
- Das et al. 2019 specifics (fraction of databases auto-indexed, revert rates, customer-feedback lessons) are not extracted here. Read Sections 7–8 of the PDF.
- I found no source confirming what signal AlloyDB's advisor uses, or whether Cloud SQL's index advisor (Query Insights) differs.
- I did not fetch DRLindex or other RL index advisors such as DRLinda or DBA bandits (Perera et al.).

---

## Q3. Multi-component (holistic) tuners

### Takeaway
UDO, UniTune, and Proto-X are the main academic attempts to tune knobs, indexes, and query hints or plans jointly with measured execution. Even these cover only three or four DBMS-internal dimensions and run offline on a fixed workload. The DBMind/openGauss line bundles separate per-component tools without a joint optimizer. I found no 2024–2026 non-LLM system that widens holistic coverage beyond knobs, indexes, and hints. MODT (DASFAA 2024) adds resource-utilization objectives for indexes and knobs.

### Cited Findings
- **Proto-X / Holon (Zhang et al., PVLDB 17, 2024):** Tunes knobs, query hints, and indexes simultaneously rather than in sequence. It learns a high-dimensional latent encoding of similarities across the action spaces and synthesizes "proto-actions" to navigate it. It reports up to 53% improvement on PostgreSQL over the next-best approach. — [PVLDB paper](https://vldb.org/pvldb/vol17/p3373-zhang.pdf); [PVLDB listing](https://mail.vldb.org/pvldb/volumes/17/paper/The%20Holon%20Approach%20for%20Simultaneously%20Tuning%20Multiple%20Components%20in%20a%20Self-Driving%20Database%20Management%20System%20with%20Machine%20Learning%20via%20Synthesized%20Proto-Actions); [Ryan Marcus course slides](https://rmarcus.info/blog/courses/cis6500/20_holon.pdf)
- **UniTune (Zhang et al., SIGMOD 2023, arXiv 2303.05710):** A coordinating framework that argues joint tuning of multiple components beats standalone tuning. — [arXiv 2303.05710](https://arxiv.org/pdf/2303.05710)
- **MODT (DASFAA 2024, ECNU):** Hierarchical RL for indexes and knobs with multiple objectives including resource utilization. Evaluated on TPC-H, TPC-DS, and JOB. — [ECNU record](https://pure.ecnu.edu.cn/en/publications/modt-multi-objective-database-tuner-using-hierarchical-reinforcem/)
- **DBMind (openGauss, PVLDB 2021):** Self-monitoring, self-diagnosis, and self-optimization. Self-optimization comprises DRL knob tuning, RL index selection, and encoder-decoder view (MV) selection as separate modules. — [openGauss docs](https://docs.opengauss.org/en/docs/5.0.0/docs/AIFeatureGuide/ai-sub-functions-of-the-dbmind.html)
- [prior knowledge, unverified] **UDO (Wang, Trummer, Basu, PVLDB 14(13), 2021)** separates "heavy" parameters (indexes, which are expensive to change) from "light" ones (knobs). It uses hierarchical MCTS with delayed heavy-parameter evaluation and orders reconfigurations to amortize index creation cost. **UniTune** [prior knowledge, unverified] uses a Thompson-sampling or bandit-style coordinator to allocate tuning time across per-component tuners, with early stopping. Proto-X compares against both. These are well known to the user and were not re-verified here.

### Inferences
- All three academic holistic tuners optimize measured runtime of a fixed benchmark workload on a dedicated (non-production) instance, within budgets of hours. None includes production safety (revert, low-utilization windows), drift handling, or application-level changes.
- "Holistic" in this literature means 3–4 DBMS-internal knobs (system knobs, indexes, per-query hints, sometimes MVs). Commercial systems that do cover more dimensions (Azure, Oracle, Databricks) cover each with an independent loop.

### Gaps
- I found no non-LLM 2025–2026 holistic tuner in searches. Most 2025–2026 "joint" work found was LLM-based (e.g., MCTuner, arXiv 2509.06298), which is out of scope.
- I could not extract Proto-X's stated limitations or tuning budget from the PDF here.

---

## Q4. Self-driving DBMS and commercial autonomous services

### Takeaway
The self-driving vision (Peloton 2017 and NoisePage/MB2) set out the broadest scope: forecasting, behavior models, and planning over an action catalog spanning knobs, physical design, resources, and query tuning. The research artifacts never shipped a working general planner. Commercial "autonomous" features are narrow, conservative, per-dimension loops: index create/drop, plan correction, clustering, compaction/vacuum/statistics, and advisory diagnostics. Each has its own measured-validation safety net.

### Cited Findings
- **Peloton (Pavlo et al., CIDR 2017):** It argues that advisory tools leave humans in the loop and proposes an integrated planner with workload forecasting, an action catalog (e.g., AddIndex) with an outcome history, and receding-horizon planning. The tuning areas are knobs, physical design, resource allocation, and query tuning. The paper is preliminary. — [CIDR paper PDF](https://web.eecs.umich.edu/~linmacse/publications/2017.self-driving.cidr.pdf); [CIDR slides](https://www.cidrdb.org/cidr2017/slides/p42-pavlo-cidr17-slides.pdf); [Acolyer summary](https://blog.acolyer.org/2017/01/17/self-driving-database-management-systems/)
- **MB2 / ModelBot2 (Ma et al., SIGMOD 2021, NoisePage):** An end-to-end framework for ML behavior models of a self-driving DBMS, decomposed into operating units, with offline data generation. The architecture has three parts: forecasting, behavior modeling, and action planning. — [CMU PDL abstract](https://www.pdl.cmu.edu/PDL-FTP/Database/ma-sigmod2021_abs.shtml); [NSF PAR](https://par.nsf.gov/biblio/10318905)
- A student critique says MB2 assumes an in-memory DB and cached plans, adds developer overhead for operating units, and does not explore offline training cost. This is an opinion, not peer review. — [Cambridge R244 slides](https://www.cl.cam.ac.uk/~ey204/teaching/ACS/R244_2021_2022/presentation/S5/MB2_Conor.pdf)
- **Azure SQL automatic tuning:** indexes and plan correction with verification and revert. See Q2. — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview)
- **Oracle Automatic Indexing:** invisible-index verification and SQL plan baselines. See Q2. — [Oracle docs](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html)
- **Snowflake Automatic Clustering:** The user defines a clustering key, and Snowflake monitors DML and reclusters in the background on Snowflake-managed compute. It is suspendable per table. From September 1, 2026, newly clustered tables use "Optima Clustering" while existing ones stay on "Clustering Classic". Third parties warn of substantial cost. — [Snowflake docs](https://docs.snowflake.com/en/user-guide/tables-auto-reclustering); [select.dev](https://select.dev/posts/snowflake-clustering)
- **Databricks Predictive Optimization:** Runs OPTIMIZE (incremental clustering and file sizing, no ZORDER), VACUUM, ANALYZE (statistics), and REFRESH INDEX (full-text) on Unity Catalog managed tables (Delta and Iceberg) only. With automatic liquid clustering it may choose new clustering keys. It runs on serverless jobs compute. Decision criteria are not documented, and skip reasons can take 24h to show. — [Databricks docs](https://docs.databricks.com/aws/en/optimizations/predictive-optimization)
- **AWS (Aurora/RDS):** DevOps Guru for RDS applies ML to Performance Insights metrics to detect anomalies (reactive insights) and to produce threshold-based proactive recommendations, e.g., "Idle In Transaction" sessions on Aurora PostgreSQL. These are diagnostic recommendations, not automatic changes. Not available for Aurora Serverless. — [Aurora User Guide](https://docs.aws.eu/en_us/AmazonRDS/latest/AuroraUserGuide/devops-guru-for-rds.html); [AWS What's New 2023](https://aws.amazon.com/about-aws/whats-new/2023/03/amazon-devops-guru-rds-proactive-insights); [Aurora recommendations](https://docs.aws.amazon.com/en_us/AmazonRDS/latest/AuroraUserGuide/monitoring-recommendations.html)
- **Google AlloyDB:** advisory index recommendations, not auto-applied. — [AlloyDB docs](https://docs.cloud.google.com/alloydb/docs/use-index-advisor)
- **Huawei openGauss DBMind:** knob tuning (X-Tuner), index advisor, view selection, and diagnosis. — [openGauss docs](https://docs.opengauss.org/en/docs/5.0.0/docs/AIFeatureGuide/ai-sub-functions-of-the-dbmind.html)
- **Microsoft (LlamaTune context):** Microsoft operates "millions of databases", and sample efficiency is the gating requirement for tuners there. — [arXiv 2203.05128](https://arxiv.org/pdf/2203.05128)

### Inferences
- In commercial practice, autonomy is per-dimension and validated on live measurements, with conservative defaults. Examples are Azure CREATE_INDEX defaulting to off, Oracle's REPORT ONLY mode, and Snowflake requiring a user-supplied clustering key. Cross-dimension coordination is left to humans.
- Lakehouse vendors (Databricks, Snowflake) automate maintenance and layout (compaction, clustering, vacuum, statistics) but not knobs or plans. OLTP clouds automate indexes and plans but not layout or maintenance scheduling.

### Gaps
- I did not fetch Oracle Autonomous Database's broader auto-tuning scope (auto statistics, SQL plan management evolution, auto-scaling), Alibaba DAS/Tencent DBbrain productization of ResTune/CDBTune, Azure SQL "intelligent insights", or Cloud SQL recommenders (idle or over-provisioned instance sizing).
- No public quantitative data on how often commercial auto-tuners revert changes.

---

## Q5. Coverage grid and gaps

### Takeaway
Across ~30 systems, coverage clusters in three islands: knobs (academic), indexes plus plans (OLTP cloud and academic), and layout plus maintenance (lakehouse vendors). Connection pooling and middleware, caching layers, workload management, application or query rewrite, and joint infrastructure sizing are almost entirely uncovered by automated tuners. No system jointly optimizes across islands with production-grade safety.

### Cited Findings (grid)
Legend: **Y** = automated action; **A** = advisory/recommendation only; **c** = used as context or input but not changed; blank = not covered. Each cell is backed by the sources cited in Q1–Q4. Cells marked † come from my unverified prior knowledge.

| System | Knobs | Indexes | Plans/hints | Layout/partition/MV | Stats | Maintenance (vacuum/compaction) | Pooling/middleware | Caching | Workload mgmt | Infra/instance sizing | App/query rewrite | Lakehouse layout | Signal | Where |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OtterTune (2017) | Y | | | | | | | | | | | | measured | offline / tuning instance |
| CDBTune / QTune | Y | | (QTune: query features c) | | | | | | | | | | measured | cloud instance |
| ResTune | Y (resource-min under SLA) | | | | | | | | | c (resource use as objective) | | | measured | cloud instance |
| OnlineTune | Y | | | | | | | | | | | | measured, live | live, safe exploration |
| HUNTER | Y | | | | | | | | | | | | measured | cloned instances |
| LlamaTune | Y | | | | | | | | | | | | measured | offline |
| DB-BERT | Y (from text hints) | | | | | | | | | | | | measured | offline |
| DTA/AutoAdmin | | A | | A (MVs, partitioning) | | | | | | | | | what-if cost | offline |
| Azure SQL auto-tuning | | Y (create/drop) | Y (force last good plan) | | | | | | | | | | measured validation + revert | live |
| Oracle Auto Indexing | | Y | Y (SQL plan baselines vs. regressions) | | | | | | | | | | measured test execution | live (invisible indexes) |
| AlloyDB index advisor | | A | | | | | | | | | | | undocumented | live, advisory |
| SWIRL and RL index advisors | | Y | | | | | | | | | | | cost estimate† | offline training |
| Bao / Lero / Balsa / AutoSteer | | c | Y | | | | | | | | | | measured latency | live or offline |
| UDO | Y | Y | (Y†) | | | | | | | | | | measured | offline |
| UniTune | Y | Y | Y† | | | | | | | | | | measured | offline |
| Proto-X | Y | Y | Y | | | | | | | | | | measured | offline |
| MODT | Y | Y | | | | | | | | c (resource objective) | | | measured | offline |
| openGauss DBMind | Y | A/Y | | Y (view selection) | | | | | | | | | mixed | in-DB tools |
| Peloton/NoisePage (vision) | Y | Y | Y | Y | | | | | | Y (resource alloc.) | | | behavior models (MB2) | in-DBMS |
| Snowflake Auto Clustering | | | | Y (needs user key) | | Y (reclustering) | | | | | | Y | internal | background |
| Databricks Predictive Opt. | | (full-text index refresh) | | Y (liquid clustering keys) | Y (ANALYZE) | Y (OPTIMIZE, VACUUM) | | | | | | Y | internal | serverless background |
| AWS DevOps Guru for RDS | | | | | | A (e.g., idle-in-transaction) | A† | | | A† | | | metrics/anomaly | live, advisory |

### Inferences
- **Gap 1, cross-island coordination:** no system jointly decides knobs + indexes/plans + layout/maintenance. Academic holistic tuners stop at knobs, indexes, and hints. Vendors run independent loops per dimension.
- **Gap 2, outside-the-DBMS dimensions:** connection pooling (e.g., PgBouncer settings), caching tiers, workload management (admission control, resource groups), instance sizing, and application/query rewrite are effectively unaddressed by automated tuners. AWS offers only diagnostics. ResTune and MODT treat resources as an objective, not as a decision.
- **Gap 3, signal fidelity vs. cost:** cost-model tuners are cheap but wrong often enough that Azure and Oracle add measured validation. Measured tuners are accurate but sample-hungry (hours of replay), which drives clones (HUNTER), replays (OtterTune), or risky live exploration (OnlineTune).
- **Gap 4, safety for holistic changes:** commercial revert mechanisms exist per change type (index revert, plan forcing, SQL plan baselines). No academic holistic tuner offers safe online application or rollback of a joint configuration.
- **Gap 5, workload drift and transfer:** transfer exists only for knob tuners (OtterTune mapping, ResTune meta-learning, OnlineTune context). Holistic tuners such as Proto-X retrain per workload, as far as the sources here show.
- **Gap 6, evaluation realism:** Van Aken 2021 shows that benchmark-only, local-storage, open-source evaluations overstate automation and understate deployment problems. This applies equally to holistic tuners.
- **Gap 7, actionability for humans:** commercial systems emphasize history and audit (Azure keeps 21-day history and T-SQL scripts). Academic tuners emit opaque configurations.

### Gaps
- Grid cells marked † are unverified.
- I found no source quantifying the interaction gains between lakehouse layout and query plans in an automated system.
- Infra sizing autotuners (e.g., Azure SQL serverless auto-scale, Aurora Serverless) were not researched here and may deserve their own row.
