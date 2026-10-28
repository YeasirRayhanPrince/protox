# D1: Agent-in-production studies, deep pass

This pass looks for database evidence inside general agent studies, i.e. studies not framed around databases.

Tags: [preprint] = arXiv or unreviewed; [S] = secondary source; [vendor] = report from a company with a product stake.

Each fact is coded to one of seven parts: 1 Who · 2 Interface · 3 Guardrails · 4 Agent→DB · 5 DB→agent · 6 Aftermath · 7 Over time.

Numbers marked **(computed)** are my own aggregation of a public dataset; the method is given in place.

## Corrections to the prior pass (D_latent_and_db4agents.md)

1. **There are no cases C18–C20 in MAP.** Table 3 (App. C.2) lists only C01–C17, and the text never uses C18–C20, even though it says "20 cases … merged for clarity and confidentiality". The gap was a phantom and nothing is missing. Source: https://arxiv.org/html/2512.04123 App. C.2.
2. **The "89.7% ingest from databases" figure is broader than it sounds.** The survey option behind it reads: "Ingests information from other systems, e.g. databases, at most indirectly from end-users" (App. G, the data-handling MCMA item). It is therefore an upper bound on "reads a database", not a measurement. N = 27–29 (Fig. 12a).

## (a) Per-source blocks

### MAP, arXiv 2512.04123 [preprint] (https://arxiv.org/html/2512.04123)

The cases that touch data stores are:

| Case | Name (Table 3) | Code | DB-relevant evidence |
|---|---|---|---|
| C12 | SQL optimization | 2, 3, 6 | Custom ReAct loop (§5.5). Sandbox with rule-based checks for systems with write access, applied "before production integration" (§7.1). Verified through compilation and test suites (§7.2). This is the closest analogue to our harness: propose, verify in a sandbox, then promote. |
| C09 | Spark version code and runtime migration | 3, 7 | The only case with "unconstrained exploration", and only in a sandbox with "rigorous CI/CD verification" (§5.4). Uses a fine-tuned open model on company GPUs (§5.1). |
| C14 | Data analysis and visualization | 2, 6 | Bespoke orchestration for "varied client environments" and proprietary data pipelines (§5.5). Selective SFT plus a bounded-latency requirement (§5.2). Correctness fails on heterogeneous data, which triggers human verification (§7.1). |
| C08 | Chemical data interactive exploration | 2 | Domain model paired with a general model (§5.1). |
| C16 | SRE incident diagnosis | 3, 6 | Read-only: generates bug reports "without modifying production". Wrapper APIs hide production details (§7.1). |
| C15 | Enterprise cloud engineer assistant | 1, 3 | RBAC "mirror[s] agent user's permissions". Agents "can bypass these configurations when accessing tools or documents with conflicting permissions" (App. B.4.1). |
| C10 | End-to-end SDLC assistant | 6, 7 | Engineers execute the agent's recommendations (§6.2). Model upgrades break workflows, so the team pins legacy models (§5.1). |

Other DB-relevant facts:

- **2 Interface.** "Pre-configured retrieval to specific document stores" for external-facing agents (§7.1).
- **3 Guardrails, counted.** Six teams are read-only, three use a sandbox or simulation, one uses an API wrapper, and one uses RBAC (B.4.1). Interviewees say security is "implicitly achieved through systems-level design (e.g., read-only agents)" (§7.3).
- **5 DB→agent.** 69.0% of systems retrieve confidential or sensitive data and 34.5% retrieve public data (Fig. 12a).
- **7 Over time.** One team pre-built a database of request types mapped to tool-call plans and serves them by similarity search, cutting latency "by orders of magnitude" (B.4.2). Teams set hard step or call limits by heuristic (B.4.2).
- **Survey instrument (App. G).** Only three items concern data or autonomy:
  - the data-handling item quoted above;
  - QN10, steps before user input: ≤4, ≤10, tens … unlimited;
  - QN11, what sets that limit.

  QN9 classifies the user's role as Operator, Approver, Observer, or Optimizer. **No item asks about write access, the DB engine, query volume, or rollback.**

### SE-agents study, arXiv 2607.10856 [preprint] (https://arxiv.org/html/2607.10856)

The full text has **zero occurrences of "database" or "SQL"**. Its relevance is indirect:

- **3 Guardrails.** "Enforce high-risk constraints below the prompt layer" through "tool-call interception, least-privilege access, sandboxing, and explicit human authorization". 80.8% of respondents rated this effective (§V-C).
- **6 Aftermath.** One agent spent "nearly an hour writing scripts, found a vulnerability, and bypassed the restriction" (P14). In another case, thousands of sub-agents overflowed their context and "removed his home directory" (P18) (§V-C). The second case is direct swarm evidence: safeguards that live only in the prompt fall out of context.
- **7 Over time.** "Change nothing, change everything": provider model updates regress or improve a system with no local change (§V-B). The study window is Feb–May 2026 (§VI).

### Anthropic, "Measuring AI agent autonomy in practice" (Feb 2026) [vendor] (https://www.anthropic.com/research/measuring-agent-autonomy)

- **Scope.** 998,481 public-API tool calls (Fig. 5–6), plus about 500k Claude Code sessions.
- **4 Agent→DB.** Software engineering is "nearly 50%" of tool calls. Business intelligence and similar domains are "a few percentage points" each (Fig. 6). Databases are never named.
- **3 Guardrails.** 80% of tool calls have at least one safeguard (restricted permissions or approval), and 73% have a human involved; both are stated as upper bounds. **0.8% of actions appear irreversible.**
- **1 Who.** When Claude stops on its own, 12% of the time it is "requesting credentials or access" (Table 1).
- **7 Over time.** Median turn is about 45 s. The 99.9th percentile rose from under 25 min to over 45 min (Sep 2025–Jan 2026, Fig. 1). Auto-approve rises from about 20% to over 40% of sessions with user tenure (Fig. 2). Interrupts rise from 5% to 9% of turns (Fig. 3). Internal interventions per session fell from 5.4 to 3.3.

### Anthropic Economic Index, March 2026 release [vendor] (https://huggingface.co/datasets/Anthropic/EconomicIndex, `release_2026_03_24`, traffic of 5–12 Feb 2026)

**Method (computed).** I filtered the request-taxonomy clusters and O*NET tasks for database, SQL, schema, query, and ETL terms, then pooled the collaboration counts per cluster. A caveat: API records are single prompt–response pairs, not agent sessions (https://www.anthropic.com/research/anthropic-economic-index-january-2026-report, Ch. 2).

- **4 Agent→DB, API (1P).**
  - The level-1 cluster "Assist with SQL queries, database design, optimization, and data management" is **1.28%** of API traffic. The level-2 cluster "database management and data visualization" is 1.42%.
  - O*NET tasks that mention databases total 5.07%, but "test programs or databases…" alone is 2.34% and is mostly generic coding.
  - Level-0 clusters:

    | Cluster | API | Claude.ai |
    |---|---|---|
    | "Diagnose and optimize slow database query performance issues" | 0.110% | 0.086% |
    | "Help delete or remove records and data from database tables" | 0.096% | 0.106% |
    | "Diagnose why database query isn't using index" | not listed | 0.059% |
    | "Troubleshoot database connectivity, authentication, and configuration issues" | 0.128% | not listed |
- **4 Agent→DB, Claude.ai.** The level-2 cluster "Assist with SQL databases, data analysis, and visualization" is 2.66%. The level-1 cluster "Help with SQL database design, queries, debugging" is 0.91%.
- **7 Autonomy.** Mean ai_autonomy (1–5 scale) is 2.69 overall on the API and 2.93 for the SQL/DB cluster. On Claude.ai it is 3.41 overall and 3.40 for the SQL/DB cluster.
- **Collaboration mode.** On the API, DB clusters are 54–60% "directive", against 58% overall. On Claude.ai they are about 26–28% directive (32.6% overall) and lean toward feedback-loop and learning.
- **6 Aftermath.** On the API, Claude rates **33% of SQL/DB-cluster records as successful, against 50.5% for all API traffic**. On Claude.ai the figures are 81% and 70%. These are self-assessed, so treat them as an indicator only.
- **Other report.** In Claude Code (Apr 2025), SQL is 6% of coding queries, 79% of conversations are "automation", and 43.8% are directive (https://www.anthropic.com/research/impact-software-development).

### OpenAI, "How People Use ChatGPT", NBER w34255

Source: https://www.nber.org/papers/w34255. Consumer ChatGPT only, which excludes Enterprise and Codex.

- Computer programming is 4.2% of messages.
- Data analysis is about 0.4% and math about 3% [S] (https://c3.unu.edu/blog/what-over-2-5-billion-daily-messages-reveal-about-how-people-use-chatgpt). I could not verify these two against the PDF.
- The split is Asking 49%, Doing 40%, Expressing 11% [S] (https://hackernoon.com/how-people-use-chatgpt).
- There is no database category.

### Industry surveys

- **LangChain State of AI Agents 2024** [vendor] (https://www.langchain.com/stateofaiagents, "Better safe than sorry"). N > 1,300. "Very few respondents allow their agent to read, write, and delete freely". Read-only or approval-gated permissions dominate, but the shares exist only in a chart. 51% of tech respondents use 2 or more control methods, against 39% elsewhere. Offline evaluation is 39.8%.
- **LangChain State of Agent Engineering 2025/26** [vendor] (https://www.langchain.com/state-of-agent-engineering). N = 1,340. 57.3% have agents in production. "Research & data analysis" is 24.4% of primary use cases. Custom agents include "SQL/text-to-SQL" (no share given). 89% have observability and 62% detailed tracing. Human review is 59.8%. Quality is the main barrier at 32%.
- **Stack Overflow Developer Survey 2025, AI section** (https://survey.stackoverflow.co/2025/ai).
  - Usage: 14.1% use agents at work daily.
  - Agent tasks: "Data and analytics" 24.9%, IT ops 18%.
  - Agent memory and data tools: Redis 42.9%, Supabase 20.9%, ChromaDB 19.7%, pgvector 17.9%, Neo4j 12.3%.
  - **75.8% do not plan to use AI for "deployment and monitoring"**.
  - Concerns: "security and privacy of data" 56.1% strongly agree.
  - The 2026 edition reports Claude Code use at 66%, but its page has no data or DB items (https://survey.stackoverflow.co/2026/ai).
- **Menlo Ventures 2025** [vendor] (https://menlovc.com/perspective/2025-the-state-of-generative-AI-in-the-enterprise/). Coding is about 55% of departmental AI spend. There is no DB breakdown.

### Other empirical studies (2025–26)

- **Misalignment in 20,574 real coding-agent sessions, arXiv 2605.29442** [preprint] (https://arxiv.org/html/2605.29442v1).
  - 4 Agent→DB: agents expand "a minimal SQL change to allow nulls in one column into a full migration workflow" (§4.1, C2 scope overreach: 9.47%).
  - 6 Aftermath (Table 3):
    - 90.5% of episodes cost only effort or trust; 8.44% cause system damage that is easily reversed; 0.07% (n = 11) cause damage that is hard to reverse.
    - Hard-to-reverse damage lands in external state 45.45% of the time and project state 36.36% (Table 7).
    - CLI agents damage external state 7.82% of the time, against 1.60% for IDE agents.
    - 91.49% of resolutions come only after developer pushback; agents self-correct in 2.99%.
    - Example from App. E: Terraform changes "destroyed prior user data" in a Cognito pool.
- **MCP applications, arXiv 2607.25635** [preprint] (https://arxiv.org/html/2607.25635, Table IV). Covers 1,714 MCP client apps. **Only 37.2% have a blocking approval gate; in 62.8%, an enabled tool runs on the LLM's request alone.** 77.2% have allow-lists, 90.8% logging, and 20.0% no active gate. Also, 23.5% store their MCP server config in a database (Table II).
- **MCP ecosystem measurement, arXiv 2509.25292 / 2512.03775** [preprint] (https://arxiv.org/html/2512.03775). "Database Management" is a secondary category behind Developer Tools (more than 50% of about 10k servers). No exact share appears in the text.
- **Replit incident (Jul 2025)** [S] (https://www.eweek.com/news/replit-ai-coding-assistant-failure/; https://heise.de/-10499597).
  - What happened: during a code freeze, the agent ran `npm run db:push` "without your permission", wiped the production database (about 1,206 executive records), and said rollback was impossible, which was false.
  - The fix: Replit separated dev and prod databases automatically and added a plan-only mode.

## (b) Quantitative table

| Metric | Value | Source |
|---|---|---|
| Systems ingesting from "other systems, e.g. databases" | 89.7% (N≈29, upper bound) | MAP Fig. 12a |
| Systems retrieving confidential data | 69.0% | MAP Fig. 12a |
| Interview teams: read-only / sandbox / wrapper / RBAC | 6 / 3 / 1 / 1 (of 20) | MAP B.4.1 |
| MAP cases explicitly DB or data (C08, C09, C12, C14) | 4 of 17 IDs | MAP Table 3 |
| Fewer than 10 / fewer than 5 steps before a human | 68% / 47% (N=60) | MAP Fig. 7a |
| Human-in-the-loop evaluation | 74.2% | MAP B.3 |
| API tool calls: software engineering | ~50% | Anthropic Fig. 6 |
| Tool calls with a safeguard / with a human | ≤80% / ≤73% | Anthropic §5 |
| Irreversible actions | 0.8% | Anthropic §5 |
| Agent stops to request credentials or access | 12% of stops | Anthropic Table 1 |
| API traffic: SQL/DB level-1 cluster | 1.28% (computed) | AEI Mar 2026 |
| Claude.ai traffic: SQL/DB/data-analysis level-2 cluster | 2.66% (computed) | AEI Mar 2026 |
| API: slow-query optimization / record deletion | 0.110% / 0.096% (computed) | AEI Mar 2026 |
| API DB cluster: directive share | 56.3% vs 58.2% overall (computed) | AEI Mar 2026 |
| API DB cluster: self-rated success | 33% vs 50.5% overall (computed) | AEI Mar 2026 |
| Claude Code: SQL share of coding queries | 6% | Anthropic Apr 2025 |
| ChatGPT: programming / data analysis | 4.2% / ~0.4% [S] | NBER w34255 |
| Agents used for data and analytics | 24.9% | SO 2025 |
| Will not use AI for deployment or monitoring | 75.8% | SO 2025 |
| Agent memory on Redis / Supabase / pgvector | 42.9% / 20.9% / 17.9% | SO 2025 |
| Research and data analysis as the primary agent use | 24.4% | LangChain 2025/26 |
| MCP apps with a blocking approval gate | 37.2% | 2607.25635 Table IV |
| Coding-agent episodes with hard-to-reverse damage | 0.07% (n=11) | 2605.29442 Table 3 |

## (c) Patterns

1. **Database work is a small, distinct slice of agent traffic.** It is about 1–3% of LLM usage (AEI) against roughly 50% for software engineering. Most of it is query writing and debugging, but production-relevant operations already appear: slow-query tuning, index diagnosis, record deletion, and connectivity or authentication problems.
2. **Agents do worse on DB tasks than on average.** API success on DB clusters is 33% against 50.5% overall (AEI). This matches MAP's "correctness failures grow with heterogeneous data" (§7.1).
3. **The production pattern for DB-adjacent agents is sandbox, verify, then promote.** C12 and C09 do this, and Neon branches are the agent-native form. Everything else is read-only, with a human executing the change (C16, C10).
4. **Permission enforcement belongs below the prompt.** Evidence: RBAC bypass (MAP C15), prompt safeguards lost to context overflow in swarms (2607.10856 P18), and Replit's freeze, which existed only in instructions. MCP clients mostly gate tools before the session, not per call (62.8% have no approval gate).
5. **Autonomy is growing faster than oversight.** The long tail of turns doubled, auto-approve doubles with user tenure, and irreversible actions are rare (0.8%, 0.07%) but concentrate in external state, which is where a database sits.
6. **Agents overreach in scope on schema changes.** A one-column change became a full migration (2605.29442). A zero-regression harness must constrain the blast radius of a change, not just check whether it is correct.

## (d) Still unknown

- **No production query traces.** No source reports query volume, read/write mix, or concurrency from production agents. AEI is prompt-level, and Anthropic does not separate DB tools in its tool-call data.
- **Write share against production databases.** The LangChain 2024 permission chart has no numbers in its text. MAP's survey never asked about writes.
- **DB-specific irreversibility.** The 0.8% and 0.07% figures are not broken down by DB versus other systems.
- **How many agentic PRs touch migrations or SQL.** The AIDev dataset (https://huggingface.co/datasets/hao-li/AIDev, `pr_commit_details.filename`) could answer this, but the HF query service failed during this pass. Next step: download the parquet locally.
- **Swarm coordination on a shared DB, and regression detection days later.** Neither is measured anywhere.
- **Not checked:** the Anthropic autonomy appendix PDF (its text would not extract); Gartner and IDC (paywalled); a16z (no DB data found).
