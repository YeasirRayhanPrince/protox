# LLM-based Database Administration, Tuning, Diagnosis and Optimization Agents (2023–2026)

Scope note: covers LLM-centred systems only (non-LLM ML/RL tuners appear only as baselines). "Research prototype" vs "Product" is marked on each entry. Some systems on the original list could not be verified with primary sources within the research budget; they are listed under Gaps rather than described from memory.

## 1. Knob / configuration tuning with LLMs

### Takeaway
LLM knob tuners went from "LLM reads the manual, a classical optimizer searches" (GPTuner, 2023–24) to "LLM writes whole configs, measured runs pick the winner" (λ-Tune, 2025), then to closed-loop agent harnesses (AgentTune 2025; AgenticDB and EvoTune 2026). The agent harnesses have explicit planner, validator, executor and recovery roles, keep memory, run measured benchmarks, and report $ and token cost. Every one validates by **measured workload runs** on a benchmark replica, not on production. Their safety checks are rule-based (static range and type checks plus rollback on restart or apply failure). None of them handles SLO-aware online deployment.

### Cited Findings
**GPTuner** (Research prototype; Lao et al., VLDB 2024)
- Uses an LLM pipeline to collect and refine tuning knowledge from manuals and forum discussions, with a "prompt ensemble" to structure it. It then does workload-aware, training-free knob selection, narrows each knob's value range, and runs coarse-to-fine Bayesian optimization. Evaluated on TPC-C and TPC-H, PostgreSQL and MySQL — [arXiv 2311.03157](https://arxiv.org/abs/2311.03157)
- Reports finding better configs about 16x faster on average than SOTA, and up to 30% better throughput or latency than the best alternative — [arXiv 2311.03157](https://arxiv.org/abs/2311.03157)
- Architecture: the LLM is an offline knowledge source, and the actions come from BO. It acts on a test DBMS through measured runs.
- A 2026 paper calls manual-derived LLM guidance like GPTuner's "useful but largely static guidance" — [EvoTune, arXiv 2607.17841](https://arxiv.org/html/2607.17841)

**λ-Tune** (Research prototype, open source; Giannakouris & Trummer, Cornell, SIGMOD 2025)
- The LLM generates **whole configuration scripts** (knobs plus physical design such as indexes) rather than hints for single parameters. Targets OLAP on Postgres and MySQL, evaluated on JOB and TPC-H. Reports beating GPTuner, DB-BERT, UDO, LlamaTune and ParamTree — [arXiv 2411.03500](https://arxiv.org/abs/2411.03500)
- An earlier SIGMOD 2024 demo built prompts from the DBMS, hardware specs and the query set to get knob and physical-design recommendations — [ACM DL demo](https://dl.acm.org/doi/10.1145/3626246.3654751)
- Code is public — [GitHub gsvic/lambda-tune](https://github.com/gsvic/lambda-tune)
- AgenticDB characterizes it as "generate complete configuration scripts, then evaluate selected candidates" — [AgenticDB, arXiv 2606.20318](https://arxiv.org/html/2606.20318)

**"Is Large Language Model Good at Database Knob Tuning?"** (Empirical study; Li et al., Renmin, arXiv Aug 2024)
- Uses GPT-4 and Claude-3 as "experienced DBAs" through prompts. Splits tuning into knob pruning, model initialization and knob recommendation. Claims LLM approaches match or beat traditional methods, are interpretable (CoT), and generalize to new benchmarks, engines and hardware by changing prompts — [arXiv 2408.02213](https://arxiv.org/abs/2408.02213)
- The abstract gives no quantitative numbers, and the arXiv page lists no peer-reviewed venue — [arXiv 2408.02213](https://arxiv.org/abs/2408.02213)

**AgentTune** (Research prototype; Li et al., PACMMOD 2025)
- An LLM agent that splits knob tuning into analysis, selection, pruning and tree-based recommendation — [AgenticDB related work](https://arxiv.org/html/2606.20318)
- It uses online feedback, but "considers only the top-k observations for the current query" — [EvoTune](https://arxiv.org/html/2607.17841)

**E2ETune** (Research prototype; Huang et al., arXiv 2024)
- End-to-end knob tuning with a **fine-tuned** generative LM — [AgenticDB related work](https://arxiv.org/html/2606.20318)
- Criticized because it "incurs high data preparation cost" and generalizes poorly under workload shift — [EvoTune](https://arxiv.org/html/2607.17841)

**DB-BERT** (Research prototype; Trummer, SIGMOD 2022, the pre-GPT precursor)
- Extracts tuning hints from DBMS manuals with BERT and combines them with RL — [AgenticDB related work](https://arxiv.org/html/2606.20318)

**Rabbit / RAG-based config debugging** (Research prototype)
- Rabbit uses RAG for knob tuning (ICDE 2025), per a reference list — [search snippet of arXiv 2604.06566 refs](https://arxiv.org/pdf/2604.06566). Not verified from primary source.
- Chen et al. (PACMMOD 3(1), 2025) do automatic DB configuration debugging with RAG — [DBA-Bench refs](https://arxiv.org/html/2607.22165v1). EvoTune calls this "static guidance" from manual knowledge encoded into prompts — [EvoTune](https://arxiv.org/html/2607.17841)

**AgenticDB** (Research prototype; Yang, Wang, Zheng, Zhang, Wu, arXiv 2606.20318, 2026). The closest prior art to a harness.
- LLM-driven closed loop that **jointly tunes DBMS knobs and OS parameters** (MySQL 8.0.45, PostgreSQL 16.13). It diagnoses the bottleneck from runtime metrics, applies a change, observes, and decides to continue, redirect, switch layers or stop — [arXiv 2606.20318](https://arxiv.org/html/2606.20318)
- Components — [arXiv 2606.20318](https://arxiv.org/html/2606.20318):
  - Initializer: profiles the deployment, builds a workload fingerprint and an action catalog.
  - LLM DBA Planner: diagnoses buffer, WAL, checkpoint, IO, CPU, lock, spill and connection bottlenecks, and emits structured diagnosis-action records that flag reload versus restart.
  - Validator: rule-based (existence, type, range, hardware limits, conflicts, protected benchmark settings). It uses no LLM and no benchmark, and runs in under 0.01 s.
  - Executor: applies the config, verifies it took effect, runs the workload, collects metrics.
  - Recovery: reads logs, repairs or rolls back to the last safe state, verifies availability.
  - Auditor: controls the loop and distills experience.
  - Memory Book: session memory plus experience memory retrieved by fingerprint. No weight updates.
- Safety examples: rejected a supported but semantics-changing isolation-level change, and an unsupported sysctl key. Recovery restored `wal_level` after a failed PG restart. Recovery covers only failures at apply, restart or run time, not subtle regressions — [arXiv 2606.20318](https://arxiv.org/html/2606.20318)
- Budget is a **100-minute wall-clock limit per method** on a 12 vCPU / 64 GB / CPU-only box. Average LLM cost per workload — [arXiv 2606.20318](https://arxiv.org/html/2606.20318):
  - GPT-5.5: $3.97 (about 584k tokens, 11 planner calls)
  - Claude Opus 4.7: $4.80 (about 795k tokens)
  - GLM 5.1: $0.84
  - Kimi K2.6: $0.68
  - DeepSeek V4 Pro: $0.26
- Results (median of 3 runs) — [arXiv 2606.20318](https://arxiv.org/html/2606.20318):
  - On average 118.1% better than the best baseline per workload (range 5.7%–337.7%).
  - MySQL Sysbench Write: +337.7% over GPTuner. PG Sysbench Write: +201.8% over AgentTune.
  - OS-level tuning added up to 24% after DBMS-level gains plateaued.
  - Time-to-best was 179.7 min vs 232.3 min for the best baselines.
  - Baselines were GPTuner, DB-BERT, AgentTune and CDBTune. λ-Tune was **not** evaluated.

**EvoTune** ("From Blind Search to Memory-Aware Evolution…", Research prototype; Renmin Univ. + PingCAP, arXiv 2607.17841, 2026). Multi-component tuning.
- Tunes four component classes together: **query rewrites, 27 query-level knobs, 19 optimizer hints (pg_hint_plan), and indexes**, on PostgreSQL and TiDB — [arXiv 2607.17841](https://arxiv.org/html/2607.17841)
- Architecture — [arXiv 2607.17841](https://arxiv.org/html/2607.17841):
  - Collaborative diagnosis: a lightweight model plus an LLM Detection Agent, arbitrated by a Thompson-sampling bandit.
  - A utility-aware retriever trained with soft Q-learning.
  - Hierarchical memory of observations and distilled experiences.
  - GPT-4.1 backend, no fine-tuning.
- Validation — [arXiv 2607.17841](https://arxiv.org/html/2607.17841):
  - A Verification Agent checks syntax and feasibility, with 3 retries.
  - Rewrites are checked for equivalence with QED and then by comparing results, falling back to the original SQL.
  - Measured runs on JOB, TPC-H SF10 and TPC-DS SF50, 3 trials, 5-minute per-query timeout.
- Uses a **30-hour tuning budget**. Per-SQL overhead is about 3.8 s diagnosis, 3.7 s recommendation, 1.0 s model refinement and 0.6 s retriever update — [arXiv 2607.17841](https://arxiv.org/html/2607.17841)
- Final latency is 20.3% (JOB), 44.5% (TPC-H) and 27.7% (TPC-DS) lower under the same budget. It reaches the best baseline's final performance 2.1x, 3.9x and 1.5x faster. Reports 2.1x time-to-target vs **Proto-X** on TPC-H and 2.3x total time vs Booster — [arXiv 2607.17841](https://arxiv.org/html/2607.17841)
- **Booster** is described as the only prior LLM-based multi-component tuner. Its weaknesses: it explores the full config space without localizing the problem, and its similarity retrieval leads to premature convergence — [arXiv 2607.17841](https://arxiv.org/html/2607.17841)

**PLRTune** (Research prototype; Yang et al., arXiv 2606.14312, 2026)
- Importance pre-sampling plus LLM-guided RL for tuning — [AgenticDB related work](https://arxiv.org/html/2606.20318)

**Baseline cost context**
- BO and RL tuners needed more than 20 hours of workload replay to tune a single TPC-H workload — [LLM × DATA survey](https://arxiv.org/html/2505.18458v1)
- The LLM × DATA survey groups LLM config tuning into: manual prompts, auto-generated prompts, RAG over offline tuning experience, RAG with online retrieval, and objective-aligned training — [arXiv 2505.18458](https://arxiv.org/html/2505.18458v1)

### Inferences
- In this line of work, the "validation by measured runs on a replica plus rule-based guardrails plus rollback" pattern is now standard, and agent cost is small relative to compute. AgenticDB spends about $0.26–$4.80 of LLM per workload against 100 minutes of benchmarking. **Wall-clock time for benchmarking, not tokens, is the binding budget.**
- No surveyed tuner optimizes under explicit SLOs or a joint $+time budget. They optimize raw throughput or latency with a fixed time cap. That is a gap the target problem definition can claim.
- EvoTune is the nearest "holistic" research system. It covers knobs, hints, indexes and rewrites, and benchmarks against Proto-X, which is relevant to this repo.

### Gaps
- LLMTune (as a distinct named system) was not found in fetched sources.
- AgentTune's primary paper, and λ-Tune's exact speedup numbers and token costs, were not fetched.
- The "Is LLM Good at Knob Tuning" quantitative results were not retrieved (the abstract has no numbers).
- No independent replication of any LLM tuner's claims was found, except AgenticDB and EvoTune re-running GPTuner and AgentTune as baselines.

## 2. Diagnosis / root-cause analysis / DBA copilots (research)

### Takeaway
D-Bot (VLDB 2024) set the template: RAG over diagnosis docs, tree-search RCA and multi-agent debate. A 2026 live-fault benchmark (DBA-Bench) shows these systems perform poorly when they must actually **repair** a live database safely. The best automated Safe-Pass is 17.9%, against 93.4% for a human DBA. A plain ReAct loop on a frontier model beats D-Bot and DBAIOps. The "diagnosis-to-repair gap" and unscoped or unsafeguarded actions are the main failure modes.

### Cited Findings
**D-Bot / DB-GPT** (Research prototype, open source; Zhou, Li et al., Tsinghua, PVLDB 17, 2024)
- D-Bot pulls knowledge from diagnosis documents and produces root cause and fix reports, in under 10 minutes vs hours for a DBA. Its parts are offline knowledge extraction, automatic prompt generation, tree-search RCA (tree-of-thought with backtracking), and multi-LLM collaboration for multi-root-cause anomalies. Evaluated on 539 anomalies across 6 applications, beating traditional methods and vanilla GPT-4 — [PVLDB 17 p2514](https://www.vldb.org/pvldb/vol17/p2514-li.pdf); [arXiv 2312.01454](https://arxiv.org/abs/2312.01454)
- Follow-up: "D-Bot: An LLM-Powered DBA Copilot," SIGMOD-Companion 2025 — [SIGMOD25 demo PDF](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/SIGMOD25-DBOT.pdf)
- Under DBA-Bench with a GPT-5.5 backbone, D-Bot scored DP 18.9%, OP 13.2% and SP 5.7% at **$7.16 per run**. That is 7x the cost of plain ReAct, for a worse result — [DBA-Bench](https://arxiv.org/html/2607.22165v1)

**DBAIOps** (Research prototype; Zhou et al., 2026)
- Knowledge-graph-guided reasoning. DBA-Bench had to reimplement it because there is no public code. GPT-5.5 results: DP 38.7%, OP 23.6%, SP 14.2%, $0.315 per run — [DBA-Bench](https://arxiv.org/html/2607.22165v1)

**DBAgent** (Research prototype; Chen et al., PVLDB 19(12), 2026)
- Cited as an RL-based agent for autonomous DB operations and maintenance — [DBA-Bench refs](https://arxiv.org/html/2607.22165v1). Full text not retrieved.

**GaussMaster** (Huawei; Zhou et al., 2025) and **Panda** (Singh et al., CIDR 2024, grounding LLMs for DB debugging)
- Both are cited as LLM DB-ops systems — [DBA-Bench refs](https://arxiv.org/html/2607.22165v1). Details not retrieved.

**Adjacent cloud-incident RCA agents** (Microsoft and others)
- These are precedents for DB-ops agents: RCAgent (CIKM 2024), Xpert (ICSE 2024), MonitorAssistant (FSE 2024), automatic RCA for cloud incidents (EuroSys 2024), Ahmed et al. ICSE 2023, and the AIOpsLab benchmark (MLSys 2025) — [DBA-Bench refs](https://arxiv.org/html/2607.22165v1)

The LLM × DATA survey groups anomaly diagnosis into: direct prompting, RAG over historical diagnoses, and multi-agent collaboration — [arXiv 2505.18458](https://arxiv.org/html/2505.18458v1)

### Inferences
- Elaborate fixed pipelines (D-Bot's tree search) lose to a simple ReAct loop once the backbone model is strong. This argues for a harness that gives agents good tools and verification rather than hard-coded reasoning scaffolds.
- Diagnosis accuracy does not guarantee a correct repair. A harness must verify outcomes end to end ("close the verification loop").

### Gaps
- Primary texts for Panda, DBG-PT, Andromeda, GaussMaster, DBAgent and DBAIOps were not fetched. Their observation spaces and action-or-advise status are unverified here.

## 3. Query rewrite / LLM query optimization

### Takeaway
LLM rewriting has three shapes:
- LLM picks rules for a rule engine (LLM-R2).
- Pure LLM rewriting with NL rules and counterexample repair (GenRewrite).
- Retrieval plus step-wise reflection (R-Bot, deployed at Huawei), and agentic DBA-assist (LITHE).

Equivalence checking and measured speedups are the validation norm. Separately, LLM embeddings can steer plan choice (LLMSteer line).

### Cited Findings
- **LLM-R2** (Research prototype; Li, Yuan, Wang, Cong, Bing; arXiv 2404.12872)
  - The LLM proposes rewrite rules for a rule-based rewriter.
  - A contrastive model trained with curriculum learning selects in-context demonstrations.
  - Motivated by inaccurate DBMS cost estimators. Claims significant efficiency gains, but the abstract gives no numbers — [arXiv 2404.12872](https://arxiv.org/abs/2404.12872). One listing attributes it to VLDB 2025 — [search result](https://arxiv.org/pdf/2412.01661)
- **GenRewrite** (Research prototype; Liu & Mozafari; arXiv 2403.09060, v3 Dec 2025)
  - Natural-Language Rewrite Rules (NLR2s) transfer rewrite knowledge between queries.
  - Counterexample-guided repair fixes syntactic and semantic errors and cuts LLM cost.
  - On TPC-DS it reaches ≥2x speedup on 25 queries, 1.35x more than LLM baselines and 2.6x more than LLM-enhanced rule baselines. Also evaluated on JOB and SQLStorm variants — [arXiv 2403.09060](https://arxiv.org/abs/2403.09060)
- **R-Bot** (Research prototype with production deployment; Tsinghua/SJTU/Huawei; arXiv 2412.01661)
  - Builds rewrite evidence from multiple sources and uses hybrid structure-semantic retrieval, then rewrites step by step with self-reflection.
  - Deployed at Huawei and with real customers — [arXiv 2412.01661](https://arxiv.org/pdf/2412.01661)
- **LITHE** (Research prototype; arXiv 2502.12918)
  - An LLM rewriting assistant for DBAs tuning slow queries.
  - Produces >1.5x speedup rewrites on about two-thirds of TPC-DS, about 4x the coverage of SOTA — [arXiv 2502.12918](https://arxiv.org/html/2502.12918v2)
- **"The Unreasonable Effectiveness of LLMs for Query Optimization"** (LLMSteer line; Akioyamen, Yi, Marcus; NeurIPS ML for Systems Workshop 2024)
  - A binary classifier on LLM embeddings of query text, trained on few labels, picks between alternative plans and beats heuristics.
  - The authors call the results preliminary — [arXiv 2411.02862](https://arxiv.org/abs/2411.02862)
- **EvoTune** adds rewrites to multi-component tuning, with QED equivalence checking and a result-comparison fallback. It criticizes LLM-R2-style static similarity retrieval for surfacing low-utility examples — [arXiv 2607.17841](https://arxiv.org/html/2607.17841)

### Inferences
- Rewrite correctness is a hard safety constraint, and semantic-equivalence checks are immature. Result comparison on sample data is the usual fallback, which is weak for a production harness.

### Gaps
- LLM-QO and "Can LLMs serve as query optimizers" were not fetched.
- LITHE's authors and venue were not confirmed.

## 4. Index advice with LLMs

### Takeaway
LLM index advisors can sometimes beat DTA. But Microsoft's own 2026 study shows high variance, frequent underperformance on a first or median sample, possible severe regressions, and validation cost (creating indexes) as the deployment bottleneck. This is a strong argument for measured validation inside any harness.

### Cited Findings
- **LLMIdxAdvis** (Research prototype; Zhao et al., Renmin + ByteDance, arXiv 2503.07884)
  - Frames index recommendation as seq2seq: (workload, storage budget, DB environment) to indexes.
  - Uses GPT-4-Turbo-synthesized demonstrations and no heavy fine-tuning — [arXiv 2503.07884](https://arxiv.org/html/2503.07884v1)
- **MAAdvisor / AMAZe** (Research prototype; arXiv 2508.16044)
  - A multi-agent, zero-shot LLM index advisor.
  - It reports that LLMIdxAdvis is only comparable on simple workloads and underperforms SOTA on complex workloads and schemas — [arXiv 2508.16044](https://arxiv.org/html/2508.16044v1)
- **Microsoft SQL Server study** (Wang, Wu, Narasayya, Chaudhuri; arXiv 2603.09181, 2026). Prompts GPT-5 with the query, schema, existing indexes and plan, and compares against DTA on TPC-H plus 4 real enterprise workloads with **measured** execution time — [arXiv 2603.09181](https://arxiv.org/abs/2603.09181) via [Pith summary](https://pith.science/paper/2603.09181). Findings:
  - Best-of-5 LLM recommendations are sometimes significantly better than DTA.
  - Quality varies a lot, and the first or median response underperforms DTA on more than half of 127 queries.
  - LLM indexes often have higher optimizer-estimated cost, so they fit poorly into cost-based advisors.
  - Adding them to DTA's candidates often hurt.
  - Validation (materializing indexes) can cost more than tuning itself.
  - The variance and regression details come from the Pith secondary review.
- A survey states that LLM advisors such as LLMIA, LLMIdxAdvis and MAAdvisor match or exceed DTA, but that a gap remains between recommendation quality and validation cost — [Zenodo survey](https://zenodo.org/records/19760577). This is a lower-quality venue.

### Inferences
- Best-of-N sampling plus measured validation works but is expensive. A budgeted harness must decide how many candidates to materialize, which makes this an explicit cost-allocation problem.

### Gaps
- No primary source was found for "AutoIndex with LLMs."

## 5. Products and industry agents (agentic DBA)

### Takeaway
Shipping products mostly **observe and advise**, with humans approving actions:
- Xata Agent (open source, now archived)
- DBtune (agentic tuning, human-in-the-loop)
- pganalyze (MCP server feeding Claude Code and others)
- Google's Gemini database agents (review-and-approve)

Vendors explicitly push back on the fully autonomous "AI DBA" framing because of accountability.

### Cited Findings
- **Xata Agent** (Product, open source, self-hosted)
  - Watches Postgres logs and metrics, tunes configs, finds slow queries and locks, and alerts through Slack — [Xata on X](https://x.com/xata/status/1900234497288810512)
  - Supports RDS, Aurora and Cloud SQL. **The repo was archived on Jun 15, 2026** — [GitHub xataio/agent](https://github.com/xataio/agent)
- **DBtune** (Product)
  - Agentic AI tuning of production Postgres: server parameters, index optimization, autovacuum monitoring. The user stays in the loop and decides whether to apply recommendations — [DBtune product](https://www.dbtune.com/product); [How DBtune works](https://www.dbtune.com/docs/overview)
  - It has an open-source observe-and-configure agent — [GitHub dbtune-agent](https://github.com/dbtuneai/dbtune-agent)
- **pganalyze** (Product)
  - The MCP Server (public preview) lets AI tools such as Claude Code query metrics, inspect EXPLAIN plans, run the Index Advisor and review issues — [pganalyze MCP docs](https://pganalyze.com/docs/mcp); [preview blog](https://pganalyze.com/blog/mcp-server-public-preview)
  - Lukas Fittl (Mar 11, 2026) argues that "AI DBA" conflates doing the work with owning the outcome. He argues that agents can't be accountable, that high-risk actions need approval, and that deterministic logic is sometimes better than AI — [The Dilemma of the 'AI DBA'](https://pganalyze.com/blog/the-ai-dba-dilemma)
- **Google Cloud Gemini database agents** (Product)
  - Reported to automate setup, monitoring, troubleshooting and optimization using Database Insights, Cloud Monitoring, Logging and Trace, with recommended actions that teams review and approve before execution. The only source is secondary — [xcademia](https://www.xcademia.com/news/google-cloud-launches-gemini-ai-agents-for-smarter-database-operations)
  - Also: Gemini CLI extensions for Google Data Cloud — [Google Cloud blog](https://cloud.google.com/blog/products/databases/gemini-cli-extensions-for-google-data-cloud)
- **AWS**: no Amazon Q DBA or performance agent was found. Amazon Q generative SQL for Redshift is text-to-SQL, which is out of scope — [AWS blog](https://aws.amazon.com/blogs/big-data/write-queries-faster-with-amazon-q-generative-sql-for-amazon-redshift/)

### Inferences
- Industry consensus as of 2026 is advise plus human approval. A harness that *acts* under a budget will need explicit guardrails, an audit trail, and scoped permissions to be credible.

### Gaps
- Not researched within budget: Supabase and Neon AI assistants, Aiven AI optimizer, EverSQL, Datadog DBM AI features, OtterTune's successors (OtterTune shut down in 2024, from memory and unverified), and Microsoft Azure SQL Copilot.

## 6. Benchmarks, surveys and vision papers

### Takeaway
DBA-Bench (2026) is the first production-fidelity, live-fault, safety-scored benchmark for DB-ops agents. It reports per-run $ cost and finds large gaps to human DBAs. Vision work (Cheng, Zaharia, Stoica et al., 2026) frames LLM-driven evolutionary search (AlphaEvolve-style) as a research engine for databases.

### Cited Findings
**DBA-Bench** (arXiv 2607.22165, 2026)
- Setup — [DBA-Bench](https://arxiv.org/html/2607.22165v1):
  - 106 live PostgreSQL scenarios (42 Easy, 64 Hard) across 7 domains: query tuning, system failure, health check, business change, resource governance, composite faults, misleading alerts.
  - Snapshot restore before each run, with active OLTP, OLAP or mixed workloads.
  - Tools: metrics, SQL, instance management, logs, and a knowledge base of docs and runbooks.
- Metrics — [DBA-Bench](https://arxiv.org/html/2607.22165v1):
  - Diagnosis Pass (DP)
  - Outcome Pass (OP)
  - Safe Pass (SP): an outcome pass with zero safety penalty
  - USD per run
- Results — [DBA-Bench](https://arxiv.org/html/2607.22165v1):
  - Across 848 automated runs: DP 32.7%, OP 19.6%, SP 12.4%.
  - Best SP is 17.9% (GPT-5.5 and Claude Opus 4.8), vs 93.4% for a human DBA.
  - Opus 4.8 matched GPT-5.5's SP at 36.5% lower cost. DeepSeek V4 Pro cost $0.08 per run.
  - GPT-5.5 ReAct scored DP 44.3%, OP 26.4%, SP 17.9% at $1.02 per run.
- Failure modes — [DBA-Bench](https://arxiv.org/html/2607.22165v1):
  - 62.1% of diagnosis-passing runs fail the outcome check.
  - 36.7% of outcome-passing runs fail the safety check.
  - Unsafe recoveries break down as unscoped (17), missing safeguards (15) and destructive (8).
  - Typical failures: decoy anchoring on misleading alerts (68.3%), truncated causal chains in composite faults (45.9%), and "unclosed verification" in query tuning (24.4%).
- Inconsistency: the difficulty-split figures in the abstract vs the body appear inconsistent (per my read of the fetched text) — [DBA-Bench](https://arxiv.org/html/2607.22165v1)

**Surveys and vision papers**
- **LLM × DATA survey** (Tsinghua; arXiv 2505.18458) covers LLM-for-system-optimization (config tuning, query rewrite, anomaly diagnosis) — [arXiv 2505.18458](https://arxiv.org/abs/2505.18458); paper list at [GitHub awesome-data-llm](https://github.com/OpenDataBox/awesome-data-llm)
- **"AI-Driven Research for Databases"** (Cheng, Ng, Kabcenell, Bailis, Zaharia, Ma, Shi, Stoica; arXiv 2604.06566, 2026) — [arXiv 2604.06566](https://arxiv.org/pdf/2604.06566)
  - Its reference keys include GPTuner, λ-Tune, AgentTune, LLM-R2, DB-BERT, AlphaEvolve, OpenEvolve and GEPA, plus Claude Code and Cursor.
  - I could not extract the body text, so its thesis is unverified.

### Inferences
- DBA-Bench's metrics (outcome plus safety plus $ per run) are a good template for evaluating a holistic harness, but it lacks performance-under-SLO and wall-clock-budget dimensions.

### Gaps
- No "BIRD-Critic-style" or SWE-bench-like *performance-optimization* benchmark for DB agents was found beyond DBA-Bench.
- "Can Foundation Models Wrangle Your Data?" and Trummer's other vision papers were not fetched.
- No public source on "Gen-DBA" was found.
