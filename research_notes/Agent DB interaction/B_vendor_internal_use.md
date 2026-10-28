# B. How vendors and hyperscalers use agents on their own data systems (Oct 2026)

[S] = secondary source, [preprint] = not peer reviewed. "unk" = undocumented. This note builds on `../Harness landscape gap evaluation/db_agents_in_production_studies.md` and `db_vendor_agent_designs.md`.

## (a) Per-system coding

**Huawei GaussMaster (banking GaussDB, incl. ABC)** https://arxiv.org/html/2506.23322v1 [preprint]
1. Multi-agent: a chief DBA agent recruits Resource and Component expert agents. Identity and concurrency: unk.
2. 25 DBMind tools behind REST. Tools are picked by hybrid retrieval and re-ranking; arguments are filled in a separate step.
3. Expert-defined diagnosis trees fix the tool sequence. The Q&A path has a 20k-word sensitive-word filter and a classifier. Read-only or approval controls: unk.
4. Reads metrics and slow SQL, and produces recommendations. Writes are not described despite the module name "Repair".
5. Tool output is poured into fixed templates, then summarized by each expert.
6. Retrieves historical alarm cases and diagnosis trees.
7. Tree-guided loop with cross-review. Claims "zero human intervention" in 34+ scenarios it does not define; 85.23% Q&A quality; tool selection above 95%.

**Huawei DBAgent (DWS)** https://www.vldb.org/pvldb/vol19/p3928-chen.pdf (I could not parse the PDF; lines below come from the abstract)
1–3. Single RL-trained policy wired to Autopilot, DWS's production auto-remediation service. Identity and guardrails: unk.
4–5. Consumes KPIs, execution plans and Autopilot alerts.
7. Think–act–observe loop. "+23% success, ~5% hallucination" comes from a machine summary and is unverified [S] https://rmarcus.info/dbscholar/papers/h87d8ab03d45e3de1

**Huawei R-Bot (GaussDB query rewrite)** https://arxiv.org/html/2412.01661v2 [preprint]
1–2. A single LLM chooses and orders Calcite rules. It never writes SQL; the engine applies the rules.
3. Rules keep each rewrite semantically equivalent, and the optimizer's cost check gates acceptance.
4. Sends SQL to the engine and gets cost estimates back. Output is a cached rewrite pattern.
5. Gets back the rule list, retrieved recipes and costs.
7. Reflection loop. At ICBC (20 slow queries), 70% got faster and total latency fell from 9.23h to 4.37h. A rewrite is cached only if it beats GaussDB's own.

**Microsoft RCACopilot (Transport/Exchange)** https://arxiv.org/html/2305.15778v4
1–2. On-call engineers author handlers per alert type: scope-switch, query/script and mitigation-suggestion actions.
3. The LLM does **not** choose tools; handlers are deterministic.
5. The LLM compresses diagnostics to about 130 words.
6. FastText nearest-neighbour search over past incidents (K=5, with time decay).
7. The LLM predicts a root-cause category for engineers to review. Micro-F1 0.766 on 653 incidents. Collection has run for 4+ years across 30+ teams; prediction ran for months in one service.

**Microsoft ReAct RCA agent** https://arxiv.org/html/2403.04123
2. Incident Q&A tool, historical retrieval, a DB query tool, a KB-article tool and a human-interaction tool (Azure case study).
3. Permissions: unk.
7. Capped at 20 iterations. Offline accuracy 35% vs 39% for CoT, but hallucination 4% vs 12%. The Azure work was a 4-week prototype for one team.

**Microsoft LLM index tuning (SQL Server)** https://arxiv.org/html/2603.09181v1 [preprint]
2. GPT-5 sees SQL, schema, existing indexes and the SHOWPLAN_XML plan; nothing is executed to produce them.
3–4. Indexes are validated by building them and running timed queries offline.
7. The best of 5 runs often beats DTA, but the worst often regresses or times out. Feeding LLM candidates into DTA often hurt, and validation costs more than tuning. Not deployed.

**Alibaba RCAgent (Flink real-time compute)** https://arxiv.org/html/2310.16340v3 [preprint]
1. Single controller with expert tools. Runs a locally hosted Vicuna-13B for privacy.
2. Simplified log (SLS), history-DB and code-read tools.
3. Log evidence must fuzzy-match its source or it is dropped. Read-only: unk.
5. An "observation snapshot key" shows only the head of a long output plus a hash; the full text is fetched on demand. Truncation beat LLM summaries.
7. ReAct loop with self-consistency at the final step. Deployed for jobs the existing rules don't handle; root-cause reports go to SREs.

**Alibaba DAS Agent** https://help.aliyun.com/en/document_detail/3041316.html
2. Hosted assistant; its SSE API is billed per output character https://www.alibabacloud.com/help/id/das/developer-reference/api-das-2020-01-16-getdasagentsse
3. Users apply suggestions themselves; there is no auto-execution.
6. Built from more than 100k tickets.

**Databricks Storex plus AI SRE (internal OLTP fleet)** https://www.databricks.com/en/blog/how-we-debug-1000s-databases-ai-databricks ; https://databricks.com/blog/how-databricks-uses-ai-accelerate-incident-investigation
1. One agent plus domain agents; a global instance coordinates regional shards so data stays in-region.
2. Tools are Scala functions with docstrings, driven by DsPy.
3. Access control at team, resource and RPC level. The API layer **limits agent query bursts** so they can't starve alerting.
4. Reads metrics, logs, schemas and slow-query logs. Restores, prod queries and config updates are "future work".
5. Every conclusion links to its raw evidence, and low confidence is stated.
7. Snapshot-replay evaluation with an LLM judge. Up to 90% faster debugging, 2,000+ investigations a day, 150+ teams. Humans act on the findings.

**Google SRE (Gemini CLI + ProdAgent)** https://cloud.google.com/blog/topics/developers-practitioners/how-google-sres-use-gemini-cli-to-solve-real-world-outages ; https://cloud.google.com/blog/products/devops-sre/how-google-sre-is-using-agentic-ai-to-improve-operations
1. Agents carry "strong identities" with roles.
2. Typed MCP tools only; no arbitrary bash.
3. Actions are tagged safe, reversible or destructive. Policies such as "2-person approval". A human confirms each action, and everything is audited.
4. Actions come from a closed set of generic mitigations (drain, rollback, restart, add capacity). Fixes ship as CLs that a human submits.
7. Some investigation agents "autonomously execute" mitigations, gated by incident risk categories. No numbers are published. The walkthrough incident was "real (simulated)".

**Meta RCA** https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/
2–3. A heuristic retriever narrows candidates, then a fine-tuned Llama-2-7B ranks them. Low-confidence answers are withheld.
7. The right root cause is in the top 5 for 42% of backtested cases. Suggestions only.

**AWS Kiro incident (Cost Explorer, Dec 2025)** [S] https://www.computerworld.com/article/4136512/what-really-caused-that-aws-outage-in-december.html
1. The agent had the engineer's operator-level role.
3. The usual approval step was bypassed. It deleted and recreated the environment, causing a 13h outage. Amazon blamed misconfigured access controls and added mandatory peer review for prod access.

## (b) Cross-cutting patterns
1. **Vendors use agents to read and humans to write.** Every fleet system above stops at diagnosis or recommendation (RCACopilot, Meta, Databricks, DAS). Where writes exist (Google), they come from a closed, typed mitigation set and need human confirmation.
2. **Experts fix the tool sequence and the LLM fills gaps.** Examples: handlers (RCACopilot), diagnosis trees (GaussMaster), deterministic checks before LLM synthesis (Databricks).
3. **Changes go through a deterministic engine.** R-Bot selects only equivalence-preserving rules, which the optimizer then cost-checks. It is the only DB-change agent in this set reported as deployed.
4. **Evidence grounding is used as an anti-hallucination guard.** Examples: the fuzzy-match check (RCAgent), evidence links (Databricks), confidence withholding (Meta).
5. **Large outputs are handled by truncating with on-demand lookup, templating or summaries.** RCAgent found truncation beat LLM summaries.
6. **Agent load on the systems it inspects is treated as its own risk** (Databricks burst limits, regional sharding).
7. **Evaluation is replay plus judges.** Snapshot replay with an LLM judge and backtesting are the norm. No vendor reports live intervention or acceptance rates.
8. **The worst failure came from inherited human privileges**, not from the agent's reasoning (Kiro).

## (c) Holes for an autonomous zero-regression harness
- No vendor publishes an agent that autonomously applies DB config, index or DDL changes on its own fleet. The closest are Autopilot+DBAgent (details unk) and R-Bot (rewrites cached only when they beat GaussDB's own rewrite).
- Nobody reports regression rates, rollbacks or acceptance rates for agent-proposed DB changes. The index-tuning study shows worst-case regressions and costly validation.
- Concurrency between multiple agents on the same database, and agent identity, are undocumented everywhere except Google's stated principles.
- No published defence treats DB-returned data (logs, query text) as untrusted prompt input.
- Memory across incidents is retrieval over past tickets; no system learns from the outcomes of its own changes.
- Tencent DBbrain, ByteDance, Ant Group and Snowflake: I found no public account of internal LLM agents (DBbrain docs describe ML only: https://tencentcloud.com/document/product/1035/50448).
