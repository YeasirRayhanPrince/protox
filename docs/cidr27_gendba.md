# **Gen-DBA: Generative Database Agent** 

## Yeasir Rayhan and Walid G. Aref 

Purdue University, West Lafayette, IN, USA {yrayhan,aref}@purdue.edu 

### **Abstract** 

Leveraging Machine Learning to optimize database systems (ML4DB) dates back to the early 1990s, spanning indexing techniques, selectivity estimation, and query optimization. However, the idea has gained mainstream traction following the introduction of learned indexes in 2018, triggering a surge of research. Today, the ML4DB optimization landscape is dominated by dedicated specialist models targeting a single learning task on a small set of database engines, hardware platforms, query workloads, and optimization objectives. This specialist paradigm can fall short in real-world deployments, where these factors vary significantly and can evolve over time. As a result, existing approaches scale combinatorially, requiring an ever-growing number of specialist models with limited portability, knowledge transfer, and generalization capabilities. We address this limitation with Gen-DBA, a single general-purpose database agent for optimizing DBMSs. This paper presents GenDBA and highlights the key challenges that must be addressed to fully realize Gen-DBA. We present experimental evidence on three learning tasks, i.e., query optimization, storage layout optimization, and cardinality estimation, and quantify the deployment cost of Gen-DBA to demonstrate its feasibility. 

### **1 Introduction** 

The DBMS optimization landscape is combinatorial in nature, spanning **five** dimensions, i.e., **(1) database learning tasks** , **(2) database engines** , **(3) hardware platforms** , **(4) data and query workloads** , and **(5) optimization objectives** . Existing ML4DB literature typically follows a specialist paradigm, i.e., designing a dedicated ML model for optimizing only a small subset of configurations across this landscape. This can lead to a combinatorial explosion, potentially requiring as many as _𝑛_<sup>5</sup> specialist models, in the worst case. Any shift along any dimension, e.g., to a different engine or a hardware platform requires training a separate model from scratch. _Is this combinatorial explosion merely a theoretical concern?_ 

Examining the top database publication venues since 2020, more than 450 papers have been published targeting over 27 distinct learning tasks [10], including configuration knob tuning, physical index design, data layout design, query optimization, cardinality and cost estimation, among others. Similarly, there has been an explosion of database engines with distinct architectural choices, and target data models. To date, over 1,057 database engines have been reported [1]. These database engines are hosted on a wide range of hardware platforms with major cloud providers, e.g., Amazon EC2, Google Cloud, Microsoft Azure providing as many as 1000 hardware instance choices [12]. Together, these trends expose the fundamental limitation of the specialist paradigm. 

Moreover, the specialist paradigm discards the knowledge accumulated by the existing ML models, preventing knowledge transfer both within and across dimensions, thus failing to leverage the wisdom learned from a different learning task or engine. It increases the 

startup cost of optimizing a learning task from scratch, not to mention the operational and resource overhead of training, deploying, and maintaining these specialist models. Finally, portability remains a challenge for these specialist models in unseen deployment scenarios, where the hardware platform and data and query workloads may not be known in advance, e.g., as in cloud environments. 

In this paper, we depart from the specialist paradigm and propose <u>Generative Database Agent, Gen-DBA for short, a single general-</u> purpose database agent capable of (1) performing a broad range of **database learning tasks** (e.g., query scheduling, query optimization, data layout design), (2) operating across diverse **database engines** (e.g., PostgreSQL, DuckDB, MySQL, Oracle) (3) various **hardware platforms** (e.g., Intel, AMD, NVIDIA, Amazon), (4) various **data and query workloads** (e.g., OLTP, OLAP, HTAP, ML workloads), and (5) supporting multiple **optimization objectives** (e.g., query throughput, query latency, cost, service level agreements). Gen-DBA adopts the generative, foundation-model paradigm pioneered in the domain of Natural Language Processing, Computer Vision, and Robotics. 

The concept of foundation models for DBMSs is not new, e.g., see [13]. However, it is still evolving, and remains broad and open to interpretation. In this paper, we define a _DBMS foundation model_ as one that generalizes across the stated five dimensions above, consistent with the vision of _Foundation Database Models_ , introduced in [13]. A 4B-parameter dense Large Language Model (LLM, for short), initialized from Qwen3-4B-Instruct-2507, lies at the core of Gen-DBA. The LLM is post-trained to solve different learning tasks across multiple database engines, hardware platforms, data and query workloads, and optimization objectives. Surrounding the LLM is a database harness that enables the LLM to interact with the DBMS ecosystem, e.g., execute SQL, retrieve schemas, constraints and statistics, observe and collect runtime and hardware measurements, change knobs or physical designs, steer or enforce plans, etc. The underlying LLM serves as the cognitive core of Gen-DBA providing intelligence. The harness serves as the motor core of GenDBA providing the communication and execution layer between the LLM and the database ecosystem. 

This is in contrast to Foundation Database Models [13] that are built on the principles of modularity and composability. Multiple base experts are pre-trained to learn different database representations, e.g., data distributions, logical plans, and physical plans. Downstream task-specific models are then constructed by composing the appropriate experts. Gen-DBA, on the other hand, adopts a unified foundation-model approach. Rather than modularizing intelligence into multiple specialized experts, Gen-DBA concentrates intelligence within a single model and trains it to reason across all five optimization dimensions. On top of this, Gen-DBA acts as an agent that interacts with the target database at runtime, using observations from the database environment to steer its decisions during inference. 

CIDR’27, January 24-27, 2027, Amsterdam, The Netherlands 

Yeasir Rayhan and Walid G. Aref 













<!-- Start of picture text -->
⇥ Task  Profile<br>⇥ Engine Profile<br>⇥<br><!-- End of picture text -->













<!-- Start of picture text -->
A2. H/W<br>HARVEST<br>MODE: MONITOR<br>MODE: EXEC<br>A3. Engine<br><!-- End of picture text -->



<!-- Start of picture text -->
A4. Workload A5. Objective<br>. Task<br>A1<br><!-- End of picture text -->





<!-- Start of picture text -->
PROBE<br><!-- End of picture text -->





<!-- Start of picture text -->
Gen-DBA Harness<br><!-- End of picture text -->



<!-- Start of picture text -->
⇥ CONNECT(DB)<br>⇥ HARVEST(SCHEMA, QUERY)<br>⇥ OBSERVE(STATS)<br>⇥ PROBE(DB)<br>⇥ REALIZE(PLAN,LAYOUT)<br><!-- End of picture text -->











<!-- Start of picture text -->
Data & Query<br>Workload<br><!-- End of picture text -->





<!-- Start of picture text -->
Training Records<br><plan> (Agg<br>(HashJoin<br>(SeqScan t)<br>Input<br>Output<br><!-- End of picture text -->



<!-- Start of picture text -->
<plan> (Agg (HashJoin (SeqScan mi)<br>(HashJoin (SeqScan mc) (HashJoin<br>(SeqScan t) (SeqScan ct))))) </plan><br><!-- End of picture text -->











**Figure 1: Gen-DBA Architecture** 

This paper provides an overview of Gen-DBA, a generalist agent for optimizing DBMSs. We present Gen-DBA’s architecture and describe an implementation that addresses three representative database learning tasks: query optimization, storage layout optimization and cardinality estimation. We present experimental results and quantify Gen-DBA’s deployment cost to demonstrate the feasibility of the proposed approach. For query optimization, Gen-DBA improves the p99.5 query latency on JOB by 3.5× over PostgreSQL. For storage layout optimization, Gen-DBA improves the workload latency on DSB by 2.48× over the baseline on PostgreSQL. For cardinality estimation, Gen-DBA improves the p95 Q-Error on IMDb by 54× over PostgreSQL. 

### **2 Gen-DBA Architecture** 

Gen-DBA draws inspiration from generative foundation models, e.g., Large Language Models (LLM), Vision Language Models (VLM), Vision Language Action Models (VLA), and Generative Agents [8] to optimize DBMSs. Figure 1 gives the Gen-DBA architecture. 

### **2.1 Specification** 

As a proof of concept, we instantiate Gen-DBA with the following configuration across the five optimization dimensions. 

- A1. **Learning Task** . Query Optimization (QO), Storage Layout Optimization (SLO), Cardinality Estimation (CE) 

- A2. **Hardware Platform** . Intel Skylake X 

- A3. **Database Engine** . PostgreSQL, DuckDB 

- A4. **Data and Query Workload** . IMDb (JOB), TPCH-SF10, DSBSF10, Baseball (DBGen Benchmark [3]) 

- A5. **Optimization Objective** . Query Latency, Workload Latency, Q-Error 

The three learning tasks: QO, SLO, and CE, capture fundamental physical decisions in a DBMS, i.e., selecting an execution plan (QEP) for a query, organizing data in storage, and estimating the size of intermediate query results. For SLO, the database engine acts as the _reader_ that executes queries over the data, while the storage 

engine stores database tables as Parquet files. The objective is to identify Parquet-like layouts that minimize workload latency. 

### **2.2 Runtime System** 

At a high level, Gen-DBA consists of two components: a foundation model initialized from a pre-trained LLM, and a surrounding harness that enables Gen-DBA to connect to a database engine, observe its state, and realize its decisions through executable actions. **1. Foundation Database Model.** Gen-DBA adopts a pre-trained Qwen3-4B-Instruct-2507 [11] checkpoint and post-trains it to solve various learning tasks. The model contains 4B parameters, uses 36 Transformer layers with grouped-query attention, and supports a 262K-token context length. At startup, Gen-DBA connects to the target engine, loads the model weights into the GPU, initializes the inference engine, i.e., vLLM in this case, and allocates the KV cache for efficient model prediction. This is a one-time cost and, depending on OS page-cache locality, ranges from 30 to 205 seconds on an A30 (median 35 seconds) and 22 to 25 seconds on an A100-40GB (median 23 seconds). Once initialized, Gen-DBA retrieves the following profiles from the client and the target database environment, and feeds them to the foundation model. 



**Task Profile** ( ) states the learning task to be solved. It operates in two modes: _imitate_ and _optimize_ . In the _imitate_ mode, Gen-DBA reproduces a reference policy, e.g., the QEP of a query engine, the partitioning layout produced by a heuristic, etc. In the _optimize_ mode, Gen-DBA finds the best solution for the specified objective. During training, the task profile operates in both modes. During inference, optimization remains the default mode. Aside from the task specification, the learning task profile defines the hard constraints and the canonical grammar for the stated learning task. 



**Engine Profile** ( ) states the database operators and execution characteristics supported by the target database engine, along with the knob settings. 



**Hardware Profile** ( ) states the hardware stack, e.g., CPU architecture, NUMA topology, memory and storage specifications on top of which the database engine runs. 







<!-- Start of picture text -->
1<br>Gey * =<br>L®-A8<br><!-- End of picture text -->

CIDR’27, January 24-27, 2027, Amsterdam, The Netherlands 

Yeasir Rayhan and Walid G. Aref 

- a. _Solution Spectrum_ . For each optimization instance, e.g., while optimizing a given SQL query, the training mix should expose the model to a spectrum of feasible solutions rather than only the optimal one. 

- b. _Scale_ . The training mix must be sufficiently large to faithfully capture the five optimization dimensions. Compressing this knowledge within a few training records degrades performance. 

- c. _Utility_ . Not all records contribute equally to the model’s performance, e.g., increasing self-join queries improves performance on these queries but provides diminishing benefit to overall QO. 

- d. _Self-consistency_ . Every training record in the mix must be selfconsistent. Even a small fraction of contradictory supervision can disproportionately degrade the entire training mix’s quality. Consider the Query 10a example from §2.2, where Gen-DBA learns to perform join elimination. Mixing records that eliminate the redundant join with records that retain it significantly degrades the Gen-DBA’s performance, which is why Gen-DBA trains it as a tool-record. 

Note that the list is not exhaustive. Figure 3 gives the training mix that the current version of Gen-DBA is trained on. Once we assemble Gen-DBA’s training mix, the next step in the learning pipeline is to choose the model architecture best suited to build the Foundation Database Model. 

**Model Architecture (Why LLM?)** . Gen-DBA’s foundation model is built on top of the Qwen3-4B-Instruct-2507 LLM. A natural question arises, _why build upon an LLM?_ The answer is two-fold. First, an LLM operates over a _universal_ token space, namely, _language_ . This provides Gen-DBA a common representation to express any point along each optimization dimension. A second question naturally follows, i.e., _Is any universal token space sufficient, then?_ This brings us to our second point. Beyond providing a universal representation, an LLM equips Gen-DBA with semantic priors and semantic intelligence acquired through internet-scale pre-training. Semantic priors enable Gen-DBA to have a broad understanding of database concepts, e.g., _Hash Join_ , _Indexing_ , _Selectivity_ , _Cache locality_ , etc. Semantic intelligence enables Gen-DBA to understand these concepts _in context_ , reason beyond direct observations, and 



<!-- Start of picture text -->
(a) Task (b) Hardware (c) Engine<br>24.4%<br>42.9% 111,281records 49.4% (QO + SLO)records63,584 10.9% (QO + SLO)records63,584<br>64.7%<br>7.7% 100.0%<br>QO CE. (Intel Skylake-X) PostgreSQL DuckDB<br>SLO Umbra<br>(d) Data & Query Workload (e) Optimization Objective (f) Tool vs. No-tool<br>5.8% 8.2% 17.0% 26.3%<br>4.7%<br>16.4% (QO + SLO 111,281records 42.9% (QO + SLO 111,281records records12,000<br>+ CE) 64.9% + CE)<br>40.1% 73.7%<br>IMDb (JOB) DSB SF10 Optimize w Tool<br>TPC-H SF1 SSB SF1 Imitate w/o Tool<br>TPC-H SF10 Match-exact<br>Figure 3: Training mixture composition.<br><!-- End of picture text -->

infer relationships among them [9]. To fully benefit from these capabilities, the LLM must be grounded in the database eco-system. This is the purpose of Gen-DBA’s post-training stage. 

**Post-Training Recipe** . Gen-DBA’s post-training recipe comprises the following three stages based on Supervised Fine Tuning (SFT) and Simple Preference Optimization (SimPO) [7]. 

1. _Base-SFT_ trains the base QWEN3 checkpoint on ⟨prompt, output⟩ training records spanning all three learning tasks (cf. Figures 3a– 3e) jointly, while excluding any tool-use demonstrations. 

2. _Tool-SFT_ continues training from the Base-SFT checkpoint by introducing Gen-DBA’s agentic loop behavior (cf. Figure 2) through training records of the form ⟨prompt, tool-call, tool-response, ..., output⟩. To prevent catastrophic forgetting, the training mixture also replays a subset of the non-tool records from the Base-SFT stage (cf. Figure 3f). 

3. _SimPO_ continues training from Tool-SFT checkpoint using training records of the form ⟨preferred output, rejected output⟩ pairs. Both outputs are sampled from the Tool-SFT checkpoint and are labeled according to their optimization cost. In QO, the lowercost query plan is designated as the preferred output, whereas the higher-cost plan is treated as the rejected output. 

Notice that all three post-training stages serve distinct purposes. Base-SFT aligns the LLM with the previously defined database profiles (See §2.2), teaching it to reason in the five dimensions. In Gen-DBA, Base-SFT performs the majority of the learning. The goal is to maximize the model’s performance on the learning tasks before introducing any subsequent training stage. Tool-SFT teaches Gen-DBA the database agentic loop, enabling Gen-DBA to interact with the database through tool calls and incorporate tool responses into its reasoning process before producing a final result. Finally, SimPO refines the model’s optimization policy by reinforcing the better decisions it has already learned. Rather than introducing new capabilities, SimPO sharpens the model’s existing knowledge. **Implementation Details** . All three post-training stages follow the Low-Rank Adaptation approach (LoRA, for short) [4]. LoRA keeps the pre-trained weights of the base model frozen and learns a set of low-rank adaptation matrices that capture the required weight updates. In Gen-DBA, we train a rank-32 adapter for all stages. After each training stage, the learned adapter is merged with the base model, and the subsequent stage is initialized from a fresh adapter. From our experience, we have found that a clear separation between Base-SFT and Tool-SFT is crucial for enabling Gen-DBA with the agentic behavior without sacrificing its task solving capability. Design principles that may appear intuitive from a DBMS perspective do not always translate to the training recipe. For example, one may expect that training Gen-DBA to first perform well on CE could improve its subsequent QO capabilities. To the contrary, this produces inferior QEPs over jointly training for both CE and QO tasks. Finally, while the two SFT stages teach Gen-DBA 

**Table 1: Training cost of Gen-DBA.** 

|Checkpoint|Records|GPUs|Wall-clock (h)|GPU-hours|
|---|---|---|---|---|
|Base-SFT|111,281|3|8.51|25.5|
|Tool-SFT|36,208|3|2.83|8.5|
|SimPO|127|3|0.04|0.12|



CIDR’27, January 24-27, 2027, Amsterdam, The Netherlands 

Gen-DBA: Generative Database Agent 

high-quality QEP or storage layouts, the optimal solution may not be consistently selected during deployment under greedy decoding inference. Thus, SimPO is essential as it teaches the model to rank its own sampled outputs, making the preferred solution more likely to be selected during greedy decoding. 

**Training Cost** . We train Gen-DBA using Hugging Face’s library TRL on the Purdue Anvil cluster, using NVIDIA A100-40GB GPUs (cf. Table 1). Each post-training stage runs for a single epoch. 

### **4 Deployment Pipeline** 

We quantify the costs from the moment Gen-DBA receives a request from the database client until it generates the final output token for a learning task. Gen-DBA serves the Foundation Database Model using vLLM [5]. To guarantee soundness, Gen-DBA equips vLLM with a Finite-State Machine (FSM) derived from the target database schema and the output grammar of the corresponding learning task. The FSM ensures that every generated database object is valid and every generated QEP and storage layout satisfies the target grammar’s structural constraints described in the Task profile <mark>(</mark> ). **Stages** . The end-to-end request processing pipeline comprises the following stages. 

1. _Digest_ extracts the schema objects and statistics referenced by the input query. 

2. _Render_ assembles the final prompt by materializing the database profiles discussed in §2.2. 

3. _Tokenization_ formats the prompt according to the model, i.e., QWEN’s chat-template, and converts it to Token IDs. 

4. _Constrained Decoding_ builds a Finite-State Machine (FSM) to generate only valid QEP and storage layouts. 

5. _Prefill_ performs a forward pass over the full input prompt, and produces the KV cache. 

6. _Decode_ reuses the KV cache and autoregressively generates the next token one at a time until the final token is produced. 

**End-to-end request processing latency** . Table 2 reports the endto-end request processing latency for each learning task. The measurements are performed on a single NVIDIA A100-40GB GPU on Purdue Anvil and a single NVIDIA A30 GPU on Purdue Gilbreth. QO is measured over the 113-query IMDb JOB (PK-only schema) workload. SLO and CE are measured over representative requests drawn from their respective evaluation workloads (See §5 for details). For context, PostgreSQL 12.5’s native optimizer requires 2.42 ms, 42.1 ms, 1.64 s, and 1.64 s of planning time at the p50, p90, p99, and p99.5 percentiles, respectively, over the same workload. These numbers highlight that Gen-DBA incurs a higher planning latency than PostgreSQL 12.5 optimizer. The gap narrows considerably for difficult queries, e.g., on an NVIDIA A100 GPU, the p99 planning latency of Gen-DBA is approximately 1.1× more expensive than PostgreSQL 12.5 optimizer. As in §5, this additional planning overhead is more than compensated by the lower query execution latency achieved by Gen-DBA’s generated QEP. For SLO and CE, the request latency remains within 1s and 120ms, respectively. **Where does the time go** ? Figure 4a gives the breakdown of a request latency in Gen-DBA across all three learning tasks. Decode dominates every task ranging from 87.5–97.3%. Prefill is the next dominating stage ranging from 1.5–10%. Figure 4b shows the Prefill latency as a function of prompt length under warm and cold caches. 

**Table 2: Request processing latency on A30 / A100 (seconds).** 

|**Task**<br>_𝑛_<br>**p50**<br>**p90**<br>**p99**<br>**p99.5**|
|---|
|QO<br>113<br>1.41 / 0.94<br>2.17 / 1.44<br>2.72 / 1.81<br>2.72 / 1.81|
|SLO<br>12<br>1.46 / 0.97<br>1.48 / 1.02<br>1.53 / 1.03<br>1.54 / 1.03|
|CE<br>12<br>0.18 / 0.12<br>0.18 / 0.12<br>0.19 / 0.12<br>0.19 / 0.12|
|Under a cold cache, the entire prompt is computed from scratch. Un-|
|der a warm cache, only the Data and Query Workload profle (<br>)<br>requires a new Prefll pass. The remaining profles are already resi-<br>dent in vLLM’s KV cache from a prior request. Thus, warm-cache|
|Prefll latency remains nearly constant as the prompt length grows,<br>reducing the latency by up to 7.6–19×, compared to a cold cache.|
|Figure 4c shows the Decode latency as a function of the output|
|token length. Decode latency scales linearly with the number of out-<br>put tokens, requiring approximately 13.1 ms to generate each token<br>on A30. This decoding bottleneck is entirely memory-bandwidth|
|bound, as generating each token requires reading the weights of the<br>entire 4B model from the GPU’s high-bandwidth memory (HBM).|
|Over the past several GPU generations, HBM bandwidth has in-<br>creased from 933 GB/s on the A30 (2021) to approximately 8 TB/s<br>on the B200 (2024), nearly an 8×increase in three years. Since de-<br>code latency is bound almost entirely by the HBM bandwidth, this<br>trajectory alone will substantially reduce Gen-DBA’s decode cost<br>in the near term with no change to the model itself.|



### **5 Preliminary Experiments** 

**Query Optimization** . We evaluate Gen-DBA on all 113 queries of the Join Order Benchmark (JOB) and compare against the PostgreSQL 12.5 (PG) optimizer. We randomly split the workload into 91 training queries and 22 test queries. We configure PG with 32 GB shared_buffers, 4 GB work_mem, and GEQO enabled (only for native PG measurements). Gen-DBA’s plans are injected into the PG engine using the INJECT harness (cf. §2.2). All measurements are performed on an Intel Skylake X with 92 cores and 2.95TB of DDR4 RAM running Ubuntu 22.04. Measurements include both the planning latency and the query execution time. Notice that Gen-DBA’s planning latency refers to the end-to-end request processing latency as in §4. Queries are executed sequentially. Figure 5 gives the query latency distributions of the JOB workload for both Gen-DBA and PG. Gen-DBA generates better QEPs than PG across both the training and test splits. On the training split, Gen-DBA outperforms PG by 1.4× and 5.3× at p50 and p99.5, respectively. On the test split, Gen-DBA outperforms PG by 1.1× and 1.6× at p50 and p99.5, respectively. The comparatively higher planning latency of Gen-DBA means, Gen-DBA remains competitive at p50, while 



<!-- Start of picture text -->
Digest Render Tokenize Fixed Overhead Prefill Decode QO SLO CE Warm Cold<br>100% 800<br>1.45 s 1.46 s 0.18 s 700 2500<br>20% 600 2000<br>500<br>15% 400 1500<br>10% 300 1000<br>200<br>5% 100 500<br>0% QO SLO CE 0 2000 3000 4000 5000 6000 7000 50 100 150 200<br>Prompt Length (Tokens) Output Length (Tokens)<br>(a) Stage Composition  (b) Prefill Stage (c) Decode Stage<br>Figure 4: Breakdown of a request latency in Gen-DBA (A30).<br>Percentage<br>Prefill Latency (ms) Decode Latency (ms)<br><!-- End of picture text -->

CIDR’27, January 24-27, 2027, Amsterdam, The Netherlands 

Yeasir Rayhan and Walid G. Aref 



<!-- Start of picture text -->
Gen-DBA PG Planning<br>25<br>20<br>15<br>10<br>5<br>0<br>p50 p90 p99 p99.5 p50 p90 p99 p99.5<br>Train (n=91) Test (n=22)<br>IMDb<br>Figure 5: QO performance of Gen-DBA.<br>DSB SF10 DSB SF100<br>10 3<br>DEF-opt timeout<br>10 2 Gen-DBA timeout<br>Both timeout<br>10 1<br> Gen-DBA faster  Gen-DBA faster<br>10 0<br>DEF-opt faster  DEF-opt faster<br>10 1<br>0 20 40 0 20 40<br>10 3<br>Both OOM<br>10 2<br>10 1<br> Gen-DBA faster  Gen-DBA faster<br>10 0<br>DEF-opt faster  DEF-opt faster<br>10 1<br>0 20 40 0 20 40<br>Queries (sorted by speedup) Queries (sorted by speedup)<br>Figure 6: SLO performance of Gen-DBA.<br>21.90 21.93<br>Latency (s) 3.05 2.18 4.80 8.08 6.05 6.26 2.36 1.28 3.87 3.57 4.74 4.93 4.75 5.04<br>PostgreSQL<br>Speedup<br>DuckDB<br><!-- End of picture text -->

comfortably outperforming PG at the tail by 1.1×, 3.5× and 3.5× at p90, p99 and p99.5, respectively. 

**Storage Layout Optimization** . We evaluate Gen-DBA on both PostgreSQL 12.5 and DuckDB 1.5.1 engines using the DSB-SF10 (seen) and DSB-SF100 (unseen) benchmark [2] that contains 53 queries. Each table is materialized as Parquet files on disk according to the storage layout predicted by Gen-DBA. DuckDB accesses these files directly using its native Parquet reader. PG accesses the same files through parquet_fdw, a foreign data wrapper. All measurements are performed on the same machine as that of the QO experiments. Queries are executed sequentially with a 6- minute timeout. Figure 6 compares Gen-DBA against DEF_opt [6] and calculates the speedup for every query. DEF_opt partitions store_sales, catalog_sales, web_sales, inventory, store_returns, catalog_returns and web_returns on their respective date columns, and customer_demographics on cd_gender. All 25 tables of DSB are written with the default sort order with a row-group size of 1,048,576 rows, and compressed with zstd. On queries for which both layouts complete, Gen-DBA achieves geometric-mean speedups of 2.38× and 2.86× on PG and 1.35× and 1.68× on DuckDB for SF10 and SF100, respectively, with up to 87.6× speedup on individual queries. Under the 6-minute timeout, DEF-opt times out on seven PG queries that Gen-DBA completes, versus one in reverse. On DuckDB, two SF100 queries exhaust memory under both layouts. 

**Cardinality Estimation** . We evaluate Gen-DBA on 2,304 unseen queries on three schemas, i.e., IMDb, TPC-H, and Baseball . The queries span from single-table queries to joins involving up to 16 tables. Figure 7 compares Gen-DBA against PostgreSQL 12.5 cardinality estimator. At p50, Gen-DBA improves over PG by 1.95×, 1.04×, and 1.17× on IMDb, TPC-H, and Baseball, respectively. The improvement is substantially larger at p95, reaching 54.4×, 2,558×, and 2.02×, respectively. 



<!-- Start of picture text -->
10 6 IMDb (JOB) TPC-H Baseball<br>Gen-DBA<br>10 4 PostgreSQL<br>10 2<br>10 0<br>10 2<br>10 4<br>10 6<br>1 4 5 8 9+ 1 4 5 8 9+ 1 2 3 4 5<br>n=239 n=170 n=47 n=90 n=329 n=190 n=274 n=208 n=209 n=402<br>Tables in query Tables in query Tables in query<br>Q-Error<br><!-- End of picture text -->

**Figure 7: CE Performance of Gen-DBA.** 

### **6 Conclusion** 

This paper presents the core architecture of Gen-DBA, a step towards realizing a foundation database agent for DBMSs. Gen-DBA challenges the prevailing paradigm of dedicated specialist models by operating across the five optimization dimensions within the same model. While several challenges still remain, the preliminary evidence from experimental results, advances in generative models, and GPU hardware demonstrate that this is a promising direction for ML4DB research. Fundamentally, while Gen-DBA demonstrates that a single model can optimize multiple database learning tasks across different database environments, much remains to be explored in fully utilizing the knowledge instilled within the model during post-training. We plan to explore how these tasks can cooptimize and benefit from each other within the same model. 

### **Acknowledgments** 

The authors would like to thank Ryan Marcus (UPenn) for his helpful feedback and NSF Access program for GPU allocations. 

### **References** 

- [1] Carnegie Mellon Database Group. 2026. Database of Databases. https://dbdb.io/. Accessed January 19, 2026. 

- [2] Bailu Ding, Surajit Chaudhuri, Johannes Gehrke, and Vivek R. Narasayya. 2021. DSB: A Decision Support Benchmark for Workload-Driven and Traditional Database Systems. _Proc. VLDB Endow._ 14, 13 (2021), 3376–3388. 

- [3] Benjamin Hilprecht and Carsten Binnig. 2022. Zero-Shot Cost Models for Out-ofthe-box Learned Cost Prediction. _Proc. VLDB Endow._ 15, 11 (2022), 2361–2374. 

- [4] Edward J. Hu, Yelong Shen, Phillip Wallis, Zeyuan Allen-Zhu, Yuanzhi Li, Shean Wang, Lu Wang, and Weizhu Chen. 2022. LoRA: Low-Rank Adaptation of Large Language Models. In _ICLR_ . 

- [5] Woosuk Kwon, Zhuohan Li, Siyuan Zhuang, Ying Sheng, Lianmin Zheng, Cody Hao Yu, Joseph E. Gonzalez, Hao Zhang, and Ion Stoica. 2023. Efficient Memory Management for Large Language Model Serving with PagedAttention. In _SIGOPS_ . 

- [6] Venkata Vamsikrishna Meduri, David Kreismann, Ronald Barber, and Berthold Reinwald. 2026. PTO: A Workload-driven Predictive Table Optimizer for Lakehouse Systems. _Proc. ACM Manag. Data_ 4, 1 (2026), 67. 

- [7] Yu Meng, Mengzhou Xia, and Danqi Chen. 2024. SimPO: Simple Preference Optimization with a Reference-Free Reward. In _NeurIPS_ . 

- [8] Joon Sung Park, Joseph C. O’Brien, Carrie Jun Cai, Meredith Ringel Morris, Percy Liang, and Michael S. Bernstein. 2023. Generative Agents: Interactive Simulacra of Human Behavior. In _UIST_ . ACM, 2:1–2:22. 

- [9] Bertrand Russell. 1910. Knowledge by Acquaintance and Knowledge by Description. _Proceedings of the Aristotelian Society_ 11 (1910), 108–128. 

- [10] Luming Sun. 2026. ML4DB Paper List. https://github.com/LumingSun/ML4DBpaper-list. Accessed January 19, 2026. 

- [11] Qwen Team. 2025. Qwen3 Technical Report. arXiv:2505.09388 [cs.CL] https: //arxiv.org/abs/2505.09388 

- [12] Viktor Leis Till Steinert, Maximilian Kuschewski. 2026. Cloudspecs: Cloud Hardware Evolution Through the Looking Glass. In _CIDR_ . 

- [13] Johannes Wehrstein, Carsten Binnig, Fatma Özcan, Shobha Vasudevan, Yu Gan, and Yawen Wang. 2025. Towards Foundation Database Models. In _CIDR_ . 

