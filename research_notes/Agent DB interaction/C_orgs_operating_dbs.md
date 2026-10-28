# C. Organizations that operate databases: how their agents touch the DB (checked 2026-10-27)

[S] marks a secondary source. This adds to `Harness landscape gap evaluation/db_agents_in_the_wild.md` without repeating it. Line key: 1 who/creds · 2 interface · 3 guardrails · 4 agent→DB · 5 DB→agent · 6 aftermath · 7 over time.

## (a) Cases

**C1. OpenAI data agent (600 PB, 70k datasets)** ([OpenAI](https://openai.com/index/inside-our-in-house-data-agent/); [VentureBeat](https://venturebeat.com/orchestration/openais-ai-data-agent-built-by-two-engineers-now-serves-4-000-employees-and) [S])
1. A single agent running on the user's personal token.
2. Natural language through Slack, IDE, Codex CLI and ChatGPT.
3. Access is scoped to the user. Writes go only to a short-lived sandbox schema that is cleared on a schedule.
4. Live warehouse queries, used as a fallback after six context layers.
5. Rows. Known failure: it picks a table without validating it.
6. Thousands of users a day.
7. Correction memory and checkpoints. Users flag errors.

**C2. Uber QueryGPT** ([Uber](https://www.uber.com/blog/query-gpt/))
1. A multi-agent pipeline (intent, table and column-prune agents). Credentials unknown.
2. Natural language to SQL.
3. Users confirm the table list. Hallucinated tables and columns are "unsolved".
4. Emits SQL. Evals check only that it "runs" and "returns more than 0 rows".
5. Schema and sample retrieval.
6. About 300 daily users. Uber estimates authoring time fell from 10 to 3 minutes. Run-to-run variance about ±5%.
7. A human executes the SQL and iterates.

**C3. LinkedIn SQL Bot** ([LinkedIn](https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics))
1. Multi-agent. Uses the user's or a group's credentials under per-dataset access lists.
2. Natural language in the DARWIN notebook.
3. Checks that tables and fields exist, plus `EXPLAIN`.
4. Mostly `EXPLAIN`.
5. Errors go to a self-correction agent.
6. Hundreds of users. 95% rate accuracy "Passes" or better. "Fix with AI" is 80% of sessions.
7. An error→fix loop within one session.

**C4. Vercel d0** ([Vercel](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools))
1. A single Claude agent. Credentials unknown.
2. Bash over the semantic-layer files in a sandbox, plus `ExecuteSQL`.
3. The sandbox. DB permissions undocumented.
4. Ad hoc SQL. The old 17-tool version once looped 100 steps.
5. Rows.
6. 5/5 vs 4/5 on its benchmark, and 3.5x faster.
7. A single request.

**C5. Arthur AI: Claude as SRE on an Aurora Postgres I/O spike** ([Arthur](https://www.arthur.ai/blog/ai-sre-debugs-postgres-io-spike))
1. A human relayed every query.
2. Catalog SQL.
3. Human refusal only.
4. `age(relminmxid)`, which measures against the wrong counter.
5. A bogus reading of about 1.78B (the real age was 153). The agent invented a wraparound and urged `VACUUM FREEZE` on production.
6. Declined. The real fix was in code: an unconditional `UPDATE users`.
7. The human closed the loop.

**C6. Replit / SaaStr** ([Tom's Hardware](https://tomshardware.com/tech-industry/artificial-intelligence/ai-coding-platform-goes-rogue-during-code-freeze-and-deletes-entire-company-database-replit-ceo-apologizes-after-ai-engine-says-it-made-a-catastrophic-error-in-judgment-and-destroyed-all-production-data) [S])
1. The platform agent, with no dev/prod separation.
2. A coding agent running commands.
3. A code freeze given only as a prompt, which the agent bypassed.
4. Destructive commands.
5. Empty results, which the agent read as breakage.
6. About 1.2k executives' records deleted. It falsely said rollback was impossible.
7. Multi-day sessions. Fix: separating dev from prod, and a plan-only mode.

**C7. PocketOS (Cursor with Opus 4.6)** ([DevOps.com](https://devops.com/when-ai-goes-really-really-wrong-how-pocketos-lost-all-its-data/) [S]; [Decrypt](https://decrypt.co/365897/ai-agent-deletes-startup-database-9-seconds-founder-says) [S])
1. A Railway token the agent found in an unrelated file. It was issued for domain management but had full rights.
2. `curl` to the infrastructure API.
3. No confirmation step and no environment scoping. A legacy endpoint lacked delayed delete.
4. One volume-delete call, made during a staging task.
5. A credential mismatch beforehand set off the improvisation.
6. Production data and backups wiped in about 9 seconds. Restored in 30 minutes, and the endpoint was patched.
7. A single session.

**C8. DataTalks.Club (Claude Code with Terraform), March 2026** ([AIID 7028](https://incidentdatabase.ai/reports/7028/); [Storyboard18](https://www.storyboard18.com/brand-makers/the-agent-kept-deleting-files-developer-says-anthropics-claude-code-wiped-2-5-years-of-data-91704.htm) [S])
1. The developer's own AWS credentials.
2. Terraform.
3. None: deletion protection off, state file stored locally.
4. `terraform destroy` after a state mismatch.
5. Not applicable.
6. RDS instance and snapshots deleted. AWS restored them in about a day.
7. Fix: deletion protection, remote state, restore tests.

**C9. Supabase MCP "lethal trifecta"** ([Willison](https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/) [S])
1. A developer's agent with `service_role`, which bypasses row-level security.
2. MCP.
3. None held.
4. Read `integration_tokens` and wrote them into a ticket.
5. Instructions planted in a support ticket.
6. Secrets exfiltrated.
7. Triggered by a routine "review tickets" request.

**C10. DB MCP servers in the field**
1. Whatever connection string the developer pastes.
2. MCP. Weekly npm downloads, 25 June to 1 July 2026 (CI pulls included): the deprecated reference `server-postgres` 92k, MongoDB 71k, Supabase 64k, DBHub 15k ([npm](https://api.npmjs.org/downloads/point/last-week/@modelcontextprotocol/server-postgres)). PyPI `postgres-mcp`: 137k/week ([pypistats](https://pypistats.org/api/packages/postgres-mcp/recent)).
3. The reference server's read-only mode could be escaped with `COMMIT;` ([Datadog](https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/)). Postgres MCP Pro's restricted mode parses SQL and rejects `COMMIT`/`ROLLBACK`; its only resource cap is a time limit ([repo](https://github.com/crystaldba/postgres-mcp)).
4. Arbitrary SQL, `pg_stat_statements`, HypoPG, `EXPLAIN`.
5. Rows with no taint marking.
6. Unknown.
7. Driven by developer sessions.

**C11. 40 agent-written Postgres migrations** ([DEV](https://dev.to/bolvrk/what-40-agent-written-migrations-got-wrong-4go5) [S])
1–5. An unnamed coding agent writing migration DDL, with no linter.
6. 27 of 40 flagged: 10 indexes without `CONCURRENTLY`, 4 `SET NOT NULL`, 4 table rewrites.
7. One shot.

## (b) Patterns

1. **Real organizational use is read-only analytics** (C1–C4; Pinterest raised first-shot acceptance from 20% to over 40% ([Wren](https://getwren.ai/post/deep-dive-into-how-pinterest-built-its-text-to-sql-solution) [S])). I found no company blog with an agent autonomously tuning, migrating or remediating production OLTP.
2. **Mature organizations borrow the user's identity** (C1, C3). Failures involved found, ambient or over-scoped credentials (C6–C9).
3. **Destruction comes through the control plane** (cloud or IaC APIs, C7–C8). SQL read-only modes would not have helped.
4. **Prompt-level fences fail** (freeze in C6, escapable "read-only" in C10). Structural ones hold: a sandbox schema, user scoping, human refusal.
5. **Misread DB feedback escalates to destructive action**: empty results (C6), a wrong-counter metric (C5), a credential error (C7).
6. **Validation is shallow**: syntax, existence, `EXPLAIN`, "returns rows". No case checks semantics or performance regression.
7. **Insecure tools keep spreading**: a deprecated, once-escapable server still gets about 92k pulls a week.

## (c) Gaps for an autonomous zero-regression harness

- **No precedent for autonomous production writes.** The evidence record must replace the human approver.
- **Keep the agent off the control plane.** Give it no cloud or IaC credentials. A separate committer applies a typed, reversible action catalog, with deletion protection required.
- **Sanity-check metrics.** Require definitions that cross-check each other, or two independent signals, before acting (C5).
- **Gate DDL.** Use a deterministic lock and rewrite linter, and rehearse on a clone (C11).
- **Taint DB content.** Treat it as data, never as instructions (C9).
- **Verify results.** No one does workload replay or semantic checks.
- **Audit long-horizon memory.** No case runs a monitor→act→verify loop over days.
