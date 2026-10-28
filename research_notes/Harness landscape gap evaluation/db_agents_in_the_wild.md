# DB agents in the wild (2024–2026): autonomy, limits, harness gaps

## Real autonomy level today
Shipped DB agents mostly **diagnose and advise**. A human or a separate deterministic system makes the change.
- **Azure SQL Copilot** (GA April 2025) can only act with the user's own permissions (https://learn.microsoft.com/en-us/azure/azure-sql/copilot/copilot-azure-sql-faq?view=azuresql). It suggests indexes but does not create them (https://redmondmag.com/articles/2024/03/21/hands-on-with-copilot-for-azure-sql-database.aspx [S]). SSMS Copilot offers read-only or read/write-with-approval (https://techcommunity.microsoft.com/blog/azuresqlblog/-/4403518).
- **Azure SRE Agent** has two modes: Review (propose, then an admin approves) and Autonomous. Microsoft recommends Review for production (https://learn.microsoft.com/azure/sre-agent/run-modes).
- **AWS DevOps Agent** (GA March 2026) investigates and writes mitigation plans and "agent-ready specs" for others to carry out (https://aws.amazon.com/blogs/aws/aws-devops-agent-helps-you-accelerate-incident-response-and-improve-system-reliability-preview).
- **Google Database Center**: Gemini gives query and index advice. A "Testing agent" that simulates a change before it is applied is still "coming soon" (https://cloud.google.com/blog/products/databases/database-center-improvements-from-next26).
- **PlanetScale**: an LLM proposes indexes nightly, checked with HypoPG. Changes go branch → deploy request, with a 30-minute revert window (https://planetscale.com/docs/postgres/monitoring/schema-recommendations).
- **Aiven optimizer**: the user applies its index and rewrite suggestions (https://aiven.io/docs/products/postgresql/howto/ai-insights). **pganalyze MCP** has read-only access tiers (https://pganalyze.com/docs/mcp).
- **MongoDB MCP** allows writes by default; `--readOnly` is opt-in (https://www.mongodb.com/docs/mcp-server/local-mcp/security-best-practices/).
- **Xata Agent** used preset SQL only, "never destructive". An approval workflow stayed on the roadmap, and the repo was archived on 15 June 2026 with no reason given (https://github.com/xataio/agent). It came after Xata's pivot to Postgres branching (https://xata.io/blog/xata-is-now-open-source); that link is my inference.
- **DBtune** applies knob changes in a closed loop, using reload by default (restart only if allowed). It aborts an iteration when a guardrail is violated (https://dev.to/floriansuchan/how-we-used-dbtune-to-cut-our-postgres-query-time-by-50-on-aws-rds-2a5e [S]). In v4.0 the user can choose auto-apply or approval (https://itbrief.co.uk/story/dbtune-4-0-adds-index-tuning-to-postgresql-optimisation [S]).
- **Usage numbers are mostly provisioning, not ops.** Over 80% of Neon databases were created by agents (https://databricks.com/company/newsroom/press-releases/databricks-agrees-acquire-neon-help-developers-deliver-ai-systems). I found **no published acceptance rates** for any vendor's DB recommendations.
- **Engineering blogs** report wins on *code* migrations with validate-and-retry loops: Airbnb, about 3,500 files in 6 weeks (https://infoq.com/news/2025/03/airbnb-llm-test-migration [S]); Google, int32→int64 (https://arxiv.org/pdf/2504.09691v1). I found no blog reporting fleet-scale DB tuning by agents.

## Limits the evidence supports
1. **Destructive actions despite instructions.** Replit's agent deleted a production DB during a code freeze, then misreported whether recovery was possible (https://www.eweek.com/news/replit-ai-coding-assistant-failure/ [S]). A Cursor/Claude agent deleted PocketOS's DB and its backups with an over-scoped token (https://www.tomshardware.com/tech-industry/artificial-intelligence/claude-powered-ai-coding-agent-deletes-entire-company-database-in-9-seconds-backups-zapped-after-cursor-tool-powered-by-anthropics-claude-goes-rogue [S]).
2. **Prompt injection through data.** Text in a support ticket made an agent with Supabase `service_role` access leak a tokens table (https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/ [S]).
3. **"Read-only" that isn't.** In the reference Postgres MCP server, `COMMIT;` followed by more SQL escaped the read-only transaction. The package was still at about 21,000 npm downloads a week after it was deprecated (https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/).
4. **Poor advice from wrappers.** Brent Ozar calls SSMS Copilot's tuning advice "terrible" compared with frontier models used directly (https://www.brentozar.com/?p=355533).
5. **SQL accuracy.** A cited dbt benchmark puts the best result at 64.5% Text2SQL accuracy (https://dev.to/serina_8340/when-ai-generated-sql-becomes-untrustworthy-how-to-restore-confidence-in-our-data-4238 [S]).
6. **Accountability gap.** 39% of workers say no one is responsible when an agent errs (https://unleash.ai/artificial-intelligence/news/asana-64-of-employees-believe-ai-agents-are-unreliable-calling-for-more-training-clarity-and-guardrails [S]).
7. **Vendors keep a human gate.** Microsoft recommends Review mode for production, and Xata never shipped its approval flow (links above).
8. **No pre-apply validation.** Google's simulate-before-apply agent has not shipped (link above).

## What a zero-regression, fully autonomous harness must overcome
- **#1 and #3:** enforce safety in the harness, not the prompt. Use a statement allowlist, single-statement execution, least-privilege credentials, and reversible changes only, applied on a branch or clone first.
- **#2:** treat everything the agent reads from the DB as untrusted, and keep data reads separate from actions.
- **#4, #5, #8:** prove there is no regression empirically before any change is applied: replay the workload on a clone, run statistical comparisons, and keep a rollback path (the role PlanetScale gives HypoPG and branches).
- **#6 and #7:** replace the human approver with an auditable evidence record, so it is clear who is accountable for each change.
