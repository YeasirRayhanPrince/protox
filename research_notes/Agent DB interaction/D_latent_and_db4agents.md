# D: Latent DB evidence + DB4Agents

Key: [preprint] = arXiv/unreviewed; [S] = secondary source. Codes: 1 Who · 2 Interface · 3 Guardrails · 4 Agent→DB · 5 DB→agent · 6 Aftermath · 7 Over time.

## (a) Per-source blocks

**MAP, arXiv 2512.04123 [preprint]** (https://arxiv.org/html/2512.04123). The prior pilot covered §7.1/§7.3. New findings:
1. Agents act as the user via RBAC (C15). The agents mostly serve humans: 52% serve internal employees, 40% external customers, 8% non-human systems (§4.3). 59% use more than one model (§5.1).
2. **89.7% ingest from databases** (App. B.4.1, Fig. 12a, N≈29). One team wraps production tools in a hiding API layer (B.4.1). C12 is "SQL optimization" and C14 is "data analysis and visualization" (Table 3, App. C.2).
3. The B.4.1 counts: 6 teams use read-only access, 3 use sandboxed or mirrored environments, 1 uses an API wrapper, 1 uses RBAC. **The RBAC team reports agents bypassing permissions when tools or documents have conflicting permissions** (B.4.1). Only C09 allows unconstrained exploration, and only in a sandbox with CI/CD (§5.4).
4. Unknown (no query-level data). One team pre-built a database of request types mapped to actions and uses similarity lookup at runtime to cut latency (B.4.2).
5. "Correctness failures grow with heterogeneous data" (§7.1). Data integrity and drift is the #2 challenge category (Table 2, Fig. 11a).
6. In SRE cases, humans execute what the agent recommends (C10, §6.2). 74% use human-in-the-loop evaluation (§6.2).
7. **68% run fewer than 10 steps before human intervention, 47% fewer than 5** (§5.4, Fig. 7a). 16 of 20 cases use structured workflows (§5.4). 15 of 20 can run asynchronously, some hourly or overnight (§4.4). Model updates break workflows (C10, §5.1).

**SE-agents practitioner study, arXiv 2607.10856 [preprint]** (https://arxiv.org/abs/2607.10856). 20 interviews and 80 survey responses. The abstract says nothing about databases. Its only relevant point is that deployment is a bottleneck and that provider-side model updates change agent behavior. Codes 1–7 are unknown from the abstract.

**DBA-Bench, arXiv 2607.22165 [preprint]** (https://arxiv.org/html/2607.22165).
1. A single agent acting with DBA powers.
2. Five tools: `query_metrics`, `execute_sql` (catalog, locks, EXPLAIN, remediation), `manage_instance`, `read_log`, `query_knowledge_base` (§3.3).
3. Deterministic checks after the run, not gating: S1 protected objects, S2 scope, S3 missing post-action checks (§5.2, §6.4).
4. Live PostgreSQL and TiDB with active workloads (abstract). Up to 50 turns for ReAct, 150 for D-Bot (§6.1).
5. Multi-source observations: metrics, logs, docs.
6. **Best Safe Pass is 27.1% on PostgreSQL vs 92.5% for a human DBA. 72% of runs that diagnose correctly still fail to restore the objective. 17% of runs that restore it violate safety** (§6.2).
7. In 1–2 h persistent runs, Safe Pass is 2/40. Agents do not recheck earlier repairs (§6.6.1).

**BIRD-Interact, arXiv 2510.05318** (https://arxiv.org/html/2510.05318).
1. A single agent plus a simulated user.
2. 9 actions, including submit-SQL, ask-user, and schema/knowledge retrieval (§4.2, App. J).
3. A cost budget B = 6 + 2·ambiguities + 2·patience (App. J.1).
4. Covers full CRUD: 68% BI tasks, 32% data-management tasks (Table 1). About 13 interactions per task (Table 1).
5. Execution errors are fed back to the agent.
6. A fresh PostgreSQL 14 Docker instance for every run.
7. **submit and ask make up 60.9% of actions. Agents under-use schema and knowledge retrieval** (§5.2). They explore first and execute later (App. J.3). GPT-5 solves 17.0% of tasks in agentic mode (abstract).

**τ-bench, arXiv 2406.12045** (https://arxiv.org/abs/2406.12045). Interface: domain API tools over a database, plus a policy document. Success = **the final DB state equals the goal state**. pass^8 is below 25% in retail. **τ²-bench, arXiv 2506.07982 [preprint]** (https://arxiv.org/abs/2506.07982): in dual control, the user also mutates the shared state, and performance drops.

**Spider 2.0, arXiv 2411.07763** (https://arxiv.org/abs/2411.07763). 632 enterprise tasks on BigQuery and Snowflake with more than 1,000 columns. SQL often runs past 100 lines and spans several queries. The agent searches metadata and docs. o1-preview solves 21.3%.

**Supabase MCP leak** [S] (https://generalanalysis.com/blog/supabase-mcp-blog; https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/).
1. A Cursor agent connected with **service_role, which bypasses RLS**.
2. Interface: the Supabase MCP server.
3. No mediation.
4. The user asks it to "list support tickets."
5. **A row of customer text acts as instructions.** The agent then reads private tables and writes them back where the attacker can see them.

**Neon/Lakebase** [S] (https://www.databricks.com/blog/databricks-neon; https://databricks.com/blog/lakebase-and-agentic-sdlc-branching-databases-coding-agents).
1. **Over 80% of Neon databases are created by agents** (May 2025).
2. Copy-on-write branches in under a second, scaling to zero.
6. One ephemeral Postgres per coding agent or PR.

## (b) What agent DB traffic looks like quantitatively

Source: "Supporting Our AI Overlords", arXiv 2509.00997 [preprint] (https://arxiv.org/html/2509.00997).
- **Many tries:** success rises 14–70% as the number of parallel or sequential attempts grows (Fig. 1).
- **Highly redundant:** distinct sub-plans are often under 10–20% of 50 attempts (Fig. 2). Slides report more than 85% of small subexpressions are redundant [S] (https://www.cidrdb.org/cidr2026/slides/Parameswaran-108.pdf).
- **Phased:** agents explore metadata, then column statistics, then partial queries, then full queries (Fig. 3).
- **About 12.7 SQL queries per trace**, down to 10.4 with hints (Table 1, 44 o3 traces).
- **Branches:** agents create about 20× more branches and do about 50× more rollbacks than humans at Neon (§6.2).
- **Rate:** "hundreds or thousands of requests/s per agent", projected not measured (§1).
- **Interaction counts:** benchmarks show about 13 interactions per task (BIRD-Interact) and 50–150 turn budgets (DBA-Bench).

## (c) Cross-cutting patterns

1. **Read by default, write off to the side.** Teams use read-only access, sandboxes, and humans who execute agent recommendations. Direct writes to production are rare (MAP B.4.1).
2. **Permission is inherited rather than designed.** Agents either act as the user (RBAC) or with a superuser key. Both leak: MAP B.4.1 reports bypass, and the Supabase agent used service_role.
3. **Returned data is an attack surface.** Rows, tickets, and logs are untrusted text the agent may obey (Supabase).
4. **Agents diagnose well but fix poorly, and their fixes break safety rules** (DBA-Bench §6.2).
5. **Workloads are exploratory and redundant.** Metadata probing and many near-duplicate attempts suggest caching and multi-query optimization would pay off (2509.00997).
6. **Short leash.** Most production agents run fewer than 10 steps, follow structured workflows, and are evaluated by humans (MAP §5.4, §6.2).
7. **Branching is the agent-native way to isolate writes.** Neon/Lakebase use copy-on-write, and benchmarks reset to a fresh DB on every run.
8. **Success is judged by final state** (τ-bench goal DB, DBA-Bench outcome + safety), not by the queries themselves.

## (d) Holes for an autonomous zero-regression harness

- **No production query traces:** nothing is published from production on query volume, write share, or concurrency. Every number above comes from benchmarks or a 44-trace study.
- **Safety is checked after the fact:** DBA-Bench scores safety only once the run ends. No source shows a gate that blocks a change before it is applied.
- **Behavior over long horizons is untested:** nobody evaluates whether agents verify earlier fixes or catch regressions days later (DBA-Bench persistent runs: 2/40).
- **Swarms are unmeasured:** coordination among agents sharing one DB is not measured. In DBA-Bench, competing workloads were left uncoordinated.
- **Branches may not match production:** whether a branch reproduces production performance (cache state, stats, concurrent load) is unaddressed.
- **Untrusted DB output has no defense** beyond least privilege.
- **Model drift:** provider model updates silently change agent behavior (MAP §5.1; 2607.10856).
