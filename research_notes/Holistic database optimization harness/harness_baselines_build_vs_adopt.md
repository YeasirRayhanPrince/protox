# Harness baselines for an autonomous DB-optimization harness: build vs. adopt

Scope: concrete candidate bases (agent SDKs, agent frameworks, research/evolution loops, eval/ops harnesses, non-LLM substrates) judged against eight requirements of the DB problem (R1 long-horizon/resume, R2 budget across tokens+compute+wall-clock, R3 swarms + contention for a scarce DB/clone fleet, R4 stateful slow expensive environments, R5 safety tiers incl. deliberately unguarded runs, R6 verification estimated-vs-measured, R7 lossless trajectories for training/RL, R8 model-agnosticism/licence/lock-in). The local record contract is `docs/training_record.md` (provenance `measured|estimated|derived|declared` on every value, raw payloads kept, absent-not-inferred, per-event `duration_s`) and `docs/dba_loop.md` (six moves; "Move 5 must not be the cost model").

Method note: 15 tool calls budget. Claims are cited where verified this session. Statements marked "(inference)" are my reasoning; statements I believe from background knowledge but did not verify this session are placed in Gaps, not Findings.

---

## Q1. General-purpose agent SDKs (Claude Agent SDK / Claude Code, OpenAI Agents SDK / Codex, OpenHands SDK, SWE-agent / mini-swe-agent): what do they give, and what do they make hard?

### Takeaway
The agent SDKs are good *inner loops* (one agent, tool calls, hooks, subagents, session resume, token-cost estimates), and OpenHands' event-sourced state is the closest to a lossless trajectory. None of them owns external-compute dollars, a shared scarce-resource scheduler, or measured-vs-estimated provenance. Their own cost figures are client-side token estimates, and they are built around a workspace/filesystem, not a live database.

### Cited Findings
**Claude Agent SDK / Claude Code**
- Has a `max_budget_usd` option that caps a session's spend (unset by default). It was added in v0.1.6, and the session ends once the budget is exceeded — [changelog](https://git.joshthomas.dev/mirrors/claude-code-sdk-python/raw/tag/v0.1.6/CHANGELOG.md); [options reference (mirror)](https://www.mintlify.com/anthropics/claude-agent-sdk-python/api/types/claude-agent-options)
- Cost fields (`total_cost_usd`, `costUSD`) are "client-side estimates, not authoritative billing data", computed from a price table bundled at build time. The docs say: "Do not bill end users or trigger financial decisions from these fields" — [Claude docs: cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
- `max_budget_usd` "counts only the call's own spend: totals restored from a resumed session don't count against it, and a `/clear` starts the budget over" — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
- After a session crash, the final `error_during_execution` result "may carry zeroed `usage`, `total_cost_usd`, and `modelUsage`". In the fallback path, "subagent usage isn't recoverable", nor are output tokens or USD — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
- The `usage` field excludes subagent tokens. `total_cost_usd`/`modelUsage` include them. Per-step `output_tokens` is a placeholder — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
- Subagents have depth, concurrency and spend limits ("cap subagent depth, concurrency, and spend") — [cost tracking → subagents link](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
- Sessions can be resumed by ID, and `fork_session` gives a resumed session a new ID — [options reference (mirror)](https://www.mintlify.com/anthropics/claude-agent-sdk-python/api/types/claude-agent-options)
- Permission checks run in a fixed order with hooks first. Hook events include PreToolUse, PostToolUse, SubagentStart/Stop and PermissionRequest, with allow/ask/deny decisions — [Claude docs: permissions](https://code.claude.com/docs/en/agent-sdk/permissions); [third-party guide](https://www.augmentcode.com/guides/claude-agent-sdk-agent-loops-tool-calls)
- A third-party guide says the SDK does not provide built-in retry logic, default turn/budget limits, durable execution, multi-tenant deployment or centralized observability — [augmentcode guide](https://www.augmentcode.com/guides/claude-agent-sdk-agent-loops-tool-calls) (secondary; not confirmed in official docs this session)

**OpenAI Agents SDK**
- Runs are traced automatically, and tracing is "extensible by design, supporting custom spans" with external destinations (Logfire, Braintrust, AgentOps) — [PyPI openai-agents](https://pypi.org/p/openai-agents)
- Durable, long-running and human-in-the-loop workflows are delegated to a **Temporal integration** rather than built in — [PyPI / README](https://pypi.org/p/openai-agents)
- Features listed include guardrails (input/output validation, fail-fast), sessions (incl. Redis-backed), handoffs, MCP, sandbox agents — [PyPI](https://pypi.org/p/openai-agents); [secondary listing](https://jimmysong.io/ai/openai-agents-python)

**OpenHands Software Agent SDK (V1)**
- Paper (arXiv 2511.03690, MLSys 2026 oral) describes "an event-sourced state model with deterministic replay", immutable agent configuration and a typed tool system with MCP — [arXiv](https://arxiv.org/html/2511.03690v1); [MLSys 2026](https://proceedings.mlsys.org/paper_files/paper/2026/hash/8ae9cf363ea625161f885b798c1f1f78-Abstract-Conference.html)
- Production data shows V1 reduced system-attributable failures compared with V0, with negligible event-sourcing overhead — [MLSys abstract](https://proceedings.mlsys.org/paper_files/paper/2026/hash/8ae9cf363ea625161f885b798c1f1f78-Abstract-Conference.html)
- The original OpenHands state is a chronological event stream of actions/observations plus auxiliary data such as accumulated LLM cost — [OpenHands ICLR'25](https://arxiv.org/html/2407.16741v3)

**mini-swe-agent**
- Bash-only. It does not use the LM tool-calling interface, so it "run[s] with literally any model". Each action is an independent `subprocess.run` (stateless) and the message history is linear, "ideal for debugging and fine-tuning" — [sourcepulse summary](https://www.sourcepulse.org/projects/10595405); [notes](https://shekhargulati.com/2025/09/01/notes-on-mini-swe-agent)
- Used as the rollout harness in RL stacks: the PSRL recipe uses mini-SWE-agent + Docker sandboxes + fresh-container grading + async GRPO/DAPO — [PSRL docs](https://psrl.readthedocs.io/en/latest/examples/agentic_rl/swe/index.html); AReaL has a similar SWE example — [AReaL](https://gitcode.com/GitHub_Trending/are/AReaL/blob/main/examples/swe/agent.py)

### Inferences
- (inference) Claude SDK `max_budget_usd` is fine as an *inner guard per agent*, but it cannot be the harness's budget ledger: it is an estimate, it resets on resume and `/clear`, it can zero on crash, and it knows nothing about clone/replay/infra dollars. The harness must keep its own ledger fed from authoritative sources (provider usage APIs, cloud billing / metered instance-hours).
- (inference) Hooks (PreToolUse/PermissionRequest) are a good place to *implement* permission tiers, approval gates, dry-run rewriting and audit logging, and they can be switched off for "no guardrail" arms. That makes the guardrail level a config variable, which fits the research design. But hooks see tool calls, not DB semantics. Blast-radius classification (is this `DROP`/`ALTER SYSTEM`/`VACUUM FULL` reversible? on prod or clone?) has to be your own classifier behind the hook.
- (inference) The Claude Code session transcript is a chat log, not a provenance-tagged record. You would still project tool events into the `training_record.md` schema yourself. OpenHands' event stream is structurally closer to that schema (typed events, replay).
- (inference) mini-swe-agent's statelessness is right for RL rollouts on cheap, resettable containers, but it is the opposite of the DB setting. Here the environment state (buffer cache, stats, created indexes, replication lag) is the thing being optimized, and reset costs minutes to hours.
- (inference) All four assume a workspace (repo or filesystem) as the shared substrate and "run tests" as cheap verification. For DBs the substrate is a fleet of live, stateful engines and verification is an expensive, noisy measurement.

### Gaps
- Did not verify this session: OpenHands SDK licence (MIT, I believe) and its exact resume API; Codex CLI's sandbox/approval modes and the `codex exec` resume semantics; OpenAI Agents SDK built-in cost accounting (I found no evidence it has a USD budget cap); Claude Agent SDK licence terms (the SDK is open source, but Claude Code itself is proprietary and the SDK is tied to Anthropic models plus Bedrock/Vertex/Foundry. Whether it runs arbitrary open-weight models only through a compatible proxy is unverified).
- No GitHub issues collected on crash/resume failures for any of these. They are worth checking before committing.

---

## Q2. Graph/multi-agent frameworks (LangGraph, AutoGen/AG2, CrewAI, MetaGPT, Google ADK, smolagents, DSPy)

### Takeaway
LangGraph is the only one verified here with first-class durable execution (checkpointers, `interrupt()`, thread IDs, sync durability mode). That covers R1 and part of R5 (approval gates). Like the rest, it has no notion of dollars beyond tokens, no shared-resource scheduler and no measurement semantics. The others were not verified in this session.

### Cited Findings
- LangGraph: "If you are using LangGraph with a checkpointer, you already have durable execution enabled. You can pause and resume workflows at any point, even after interruptions or failures" — [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- The durability modes are `exit` (no mid-run crash recovery), `async` and `sync` (each checkpoint is written before the next step) — [durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- The docs advise making workflows "deterministic and idempotent" and to "wrap any side effects or non-deterministic operations inside tasks" — [durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- `interrupt()` can be placed anywhere and can be conditional. On resume, "execution ... starts at the beginning of the node", and state is persisted while it waits indefinitely — [LangGraph HITL](https://docs.langchain.com/oss/python/langgraph/human-in-the-loop); [interrupts](https://docs.langchain.com/oss/langgraph/interrupts)

### Inferences
- (inference) "Resume restarts the node" is dangerous for DB actions. A node that ran `CREATE INDEX CONCURRENTLY` and then crashed will re-execute the DDL unless the side effect is wrapped as an idempotent task with an external effect log. The harness needs its own **action journal** (intent → applied → verified → rolled back), keyed by an idempotency token, whatever the base.
- (inference) LangGraph's graph abstraction suits a fixed DBA loop (orient → hypothesize → screen → decide → apply/measure). It is less natural for an open-ended swarm where an LLM orchestrator spawns a variable number of investigators. You end up re-implementing a scheduler inside a graph node.
- (inference) DSPy is a prompt/program optimizer, not a runtime harness. It is relevant later for optimizing sub-prompts (e.g., the hypothesize move), not as a base.

### Gaps
- Not verified this session: AutoGen→AG2 / Microsoft Agent Framework status in 2026; CrewAI and MetaGPT persistence, budget and licence features; Google ADK session/memory services and evaluation; smolagents CodeAgent sandboxing; LangChain "deep agents" (planning tool, filesystem, subagents). I could not obtain citations for these within budget, so the report writer should not make specific claims about them from these notes.

---

## Q3. Research/evolution loops (Karpathy autoresearch, OpenEvolve, ShinkaEvolve, AlphaEvolve-style, AIDE, AI Scientist v2)

### Takeaway
These encode the *outer loop* that matters most for DB tuning: a fixed evaluation budget per experiment, a scalar metric, an archive/population and checkpoints. But they assume a stateless, cheap, deterministic evaluator (a training run or a scored program), and a single agent or a population with no live-system safety. autoresearch's main lesson for us is that a fixed wall-clock budget per experiment buys *comparability*.

### Cited Findings
- autoresearch: training runs for "a fixed 5-minute time budget (wall clock, excluding startup/compilation), regardless of the details of your compute". It runs at roughly 12 experiments/hour, ~100 overnight, on a single NVIDIA GPU — [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
- autoresearch: `program.md` holds human-edited baseline instructions for one agent, `train.py` is the file the agent edits, and the metric is val_bpb — [repo](https://github.com/karpathy/autoresearch); [explainer](https://www.theneuron.ai/explainer-articles/andrej-karpathys-autoresearch-tiny-repo-big-implications/)
- Commentary: the fixed budget exists because agents otherwise fail "not because they lack capability, but because they lack comparability" — [The Other 199,800 Lines](https://engineeredintelligence.substack.com/p/the-other-199800-lines). A practitioner reported real throughput far below the README estimate — [HackerNoon](https://hackernoon.com/i-let-karpathys-autoresearch-agent-run-overnight)
- OpenEvolve: MAP-Elites database with island-based evolution and periodic migration. The cascade evaluator makes programs pass thresholds at each stage. Checkpoints go to `.../checkpoints/checkpoint_N/` — [everydev summary](https://www.everydev.ai/tools/openevolve) (secondary)
- The ADRS systems-research paper used OpenEvolve with 5 islands, checkpoint interval 10, cascade off. Its ShinkaEvolve config lists diff/full/cross patch types and `max_parallel_jobs: 10` — [Let the Barbarians In (arXiv 2512.14806)](https://arxiv.org/pdf/2512.14806)
- Another team configured an OpenEvolve cascade of syntax check → small calibration → full held-out eval — [KV-cache eviction via program evolution (arXiv 2608.14555)](https://arxiv.org/pdf/2608.14555)

### Inferences
- (inference) The cascade evaluator maps cleanly onto the DB "screen cheaply → measure" split: stage 1 is a hypopg/EXPLAIN estimate (`estimated`), stage 2 a short replay on a clone, stage 3 a full replay with repeats (`measured`). What these frameworks lack is a *label* on each stage's score saying whether it is an estimate or a measurement. A score from stage 1 can silently become the selection signal, which is exactly the "self-certifying loop" `dba_loop.md` forbids.
- (inference) Evolution frameworks evolve *code* (a program text) against an evaluator. DB tuning acts on *state* (indexes, knobs, partitioning, MV, compaction policy), often non-commutatively, and order and interaction effects matter. You can encode a configuration as a "program", but rollback and reset of the evaluator's state between candidates becomes the dominant cost. It is also missing (for example, index builds alter the buffer cache).
- (inference) `max_parallel_jobs: 10` assumes evaluations are independent. On a shared DB host, parallel measurements contaminate each other (CPU, I/O, cache), so you need a clone fleet or a serializing lease on the measurement resource.
- (inference) autoresearch has no budget beyond per-experiment wall-clock, no safety beyond "edit one file", and no resume semantics beyond git. Its value is as a design pattern (a tiny harness plus `program.md` plus a fixed eval budget), not as a codebase to extend.

### Gaps
- Not verified: AIDE (Weco) tree search over solutions and its open-source licence; Sakana AI Scientist v2 agentic tree search and its documented failure modes (Sakana reported the system tried to edit its own timeout limits. I recall this, but did not re-verify it this session); ShinkaEvolve island and checkpoint internals; AlphaEvolve is not open source (AlphaEvolve-style = OpenEvolve/ShinkaEvolve).

---

## Q4. Eval and ops harnesses (Inspect AI, AIOpsLab, ITBench) and Ray as a substrate

### Takeaway
Inspect has the richest *budget primitives* seen in this survey: scoped, nestable token, cost, time, working-time and custom limits, propagated to sub-agents. AIOpsLab has the right *environment shape* (deploy a system, inject faults, generate workload, export telemetry, Agent-Cloud Interface). Neither is a production-control harness. Ray (not verified this session) is the plausible substrate for the clone fleet and experiment queue.

### Cited Findings
- Inspect limits: `time_limit`, `working_limit` (excludes waiting on retries, rate limits, approvals and shared resources), `message_limit`, `token_limit`, `turn_limit`, `cost_limit` (requires model cost data) and custom limits via `LimitExceededError`. All are available as scoped context managers over any code block — [Inspect: setting limits](https://inspect.aisi.org.uk/setting-limits.html)
- Token and turn limits stack across nested scopes. Sub-agents receive limits via `handoff()`, `as_tool()`, `as_solver()` or `run()`. With handoff/as_tool, the model is told the limit was hit and the sample continues — [Inspect limits](https://inspect.aisi.org.uk/setting-limits.html)
- Inspect detects retries by hooking model HTTP clients, "which isn't possible for every provider" — [Inspect limits](https://inspect.aisi.org.uk/setting-limits.html)
- The limits page describes per-sample and per-scope limits, but no eval-wide limit (as summarized by my fetch) — [Inspect limits](https://inspect.aisi.org.uk/setting-limits.html)
- AIOpsLab (Microsoft + UIUC/Berkeley/IISc, arXiv 2501.06706) deploys microservice environments, injects faults, generates workloads, exports telemetry, orchestrates agent–cloud interaction through an Agent-Cloud Interface (ACI), and scores results. The code is public — [MSR publication](https://www.microsoft.com/en-us/research/publication/aiopslab-a-holistic-framework-for-evaluating-ai-agents-for-enabling-autonomous-cloud); [arXiv](https://arxiv.org/html/2501.06706v1)

### Inferences
- (inference) Inspect's `working_limit` (excluding time waiting on shared resources) is exactly the distinction we need between *agent think-time* and *queueing for the clone fleet*. Its custom-limit hook could carry a compute-dollar budget. But Inspect is designed around samples (bounded episodes scored at the end), not a days-long single run on prod with a mid-run orchestrator.
- (inference) AIOpsLab's ACI (a narrow, typed action/observation interface to the system) is the right abstraction to copy for a DB-ACI (`orient`, `probe_whatif`, `apply`, `measure`, `rollback`). Its problem framing is incident detection/RCA/mitigation on microservices, not performance optimization under budget.
- (inference) Ray actors and placement groups (unverified this session) would be a natural home for clone-fleet leases and a measurement queue, with the LLM agents as Ray tasks. Ray brings no LLM semantics, safety or provenance.

### Gaps
- ITBench (IBM) not found by my search. Its SRE/FinOps/CISO scenarios and harness design are unverified.
- Not verified: Inspect sandbox providers (Docker/K8s), the `.eval` log format and whether it suits RL export; Ray Tune/Workflows checkpointing; Temporal's role as a durable substrate (only referenced via the OpenAI SDK integration).

---

## Q5. Practitioner "harness engineering" lessons relevant to adopting a base

### Takeaway
Practitioners converge on putting durable state *outside* the context window: progress files, JSON task lists and git for Anthropic; repo legibility for OpenAI; the filesystem plus a stable, cache-friendly prompt prefix for Manus. They also rebuild their harness repeatedly. This supports a thin, owned layer rather than deep coupling to one framework.

### Cited Findings
- Anthropic long-running agents: an initializer agent sets up an init script, a progress log (`claude-progress.txt`) and an initial git commit. Later coding sessions make incremental progress and leave artifacts, because each session starts with no memory, "like engineers arriving on a new shift" — [Anthropic engineering](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Secondary write-ups: a JSON feature list (200+ entries) is used because the model tends to rewrite Markdown — [Towards AI](https://pub.towardsai.net/anthropics-long-running-agents-keep-their-task-list-in-json-not-markdown-because-the-model-897951907cbc) (secondary)
- OpenAI "Harness engineering" (Feb 2026): five months, an internal product with zero manually written lines, "Humans steer. Agents execute." — [OpenAI](https://openai.com/index/harness-engineering)
- Manus: "KV-cache hit rate is the single most important metric for a production-stage AI agent" (cached $0.30 vs uncached $3/MTok on Sonnet). Keep the prefix stable and mask tool logits instead of removing tools. They rebuilt the framework four times — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)

### Inferences
- (inference) For a dollar-budgeted harness, cache hit rate is a budget lever. A base that rewrites the system prompt or tool list per subagent spawn will burn budget, so the ledger should record cache read/write tokens separately (the Claude SDK exposes `cache_read_input_tokens`/`cache_creation_input_tokens` — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)).
- (inference) The "progress file + git" pattern is a coding-workspace pattern. The DB analogue is an append-only experiment ledger plus a configuration-state journal (what is applied where, with a rollback recipe). These must be owned by the harness, not by the agent's context.

### Gaps
- Cognition ("Don't build multi-agents") and LangChain "deep agents" posts were not fetched this session.

---

## Q6. Synthesis: requirement matrix, what is impossible/hard, and the build-vs-adopt framework

### Takeaway
No candidate covers R2 (multi-currency budget), R3 (scarce-resource contention and measurement serialization), R4 (stateful clone and replay lifecycle) or R6 (estimated-vs-measured provenance). These four are the DB-specific core and must be custom whatever you pick. Adopt a *model-loop SDK* for the inner agent (Claude Agent SDK for hooks and subagents, or OpenHands SDK for event-sourced replay and model-agnosticism), optionally a durable-execution substrate (LangGraph checkpointer or Temporal or Ray). Build a thin owned control plane for the ledger, scheduler, environment manager, action journal and record writer.

### Cited Findings
- Budget primitives exist only for tokens/LLM cost: Claude SDK `max_budget_usd` (an estimate, reset on resume) — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking); Inspect `cost_limit`/`token_limit`/`working_limit` + custom — [Inspect](https://inspect.aisi.org.uk/setting-limits.html)
- Durable resume: LangGraph checkpointers (sync mode for crash recovery) — [LangGraph](https://docs.langchain.com/oss/python/langgraph/durable-execution); OpenHands event sourcing + deterministic replay — [arXiv 2511.03690](https://arxiv.org/html/2511.03690v1); OpenAI SDK via Temporal — [PyPI](https://pypi.org/p/openai-agents)
- Environment orchestration closest to ours: AIOpsLab (deploy, faults, workload, telemetry, ACI) — [MSR](https://www.microsoft.com/en-us/research/publication/aiopslab-a-holistic-framework-for-evaluating-ai-agents-for-enabling-autonomous-cloud)

### Requirement-by-candidate matrix
Legend: ● documented, first-class · ◐ partial / needs work · ○ absent (must build) · ? unverified this session. Cells are my assessment from the cited findings above. "?" cells must not be presented as facts.

| Candidate | R1 long-horizon/resume | R2 budget (tok+$compute+wall) | R3 swarm + scarce-resource contention | R4 stateful env lifecycle | R5 safety tiers / unguarded mode | R6 est-vs-measured | R7 lossless traces / RL hookup | R8 model-agnostic / lock-in |
|---|---|---|---|---|---|---|---|---|
| Claude Agent SDK / Code | ◐ session resume/fork; crash can zero cost | ◐ token-$ estimate only; resets on resume | ◐ subagents with depth/concurrency/spend caps; no resource leases | ○ | ● hooks + permission modes (can disable) | ○ | ◐ transcripts, not provenance-typed | ◐ Anthropic-centric (?) |
| OpenAI Agents SDK / Codex | ◐ sessions; durability via Temporal | ? | ◐ handoffs | ○ | ◐ guardrails, HITL | ○ | ◐ tracing with custom spans | ? |
| OpenHands SDK | ● event-sourced, deterministic replay | ◐ accumulates LLM cost | ? | ◐ sandboxed runtime (workspace-centric) | ? | ○ | ● event stream (closest to record) | ● (? licence) |
| SWE-agent / mini-swe-agent | ○ | ○ | ○ | ○ stateless per step | ○ | ○ | ● linear history, used in RL stacks | ● any model |
| LangGraph | ● checkpointer, sync mode | ○ | ◐ graph-level parallelism | ○ | ● `interrupt()` approval gates | ○ | ◐ state snapshots | ● |
| AutoGen/AG2, CrewAI, MetaGPT, ADK, smolagents | ? | ? | ? | ○ | ? | ○ | ? | ? |
| DSPy | n/a (optimizer) | ○ | ○ | ○ | ○ | ○ | ◐ | ● |
| autoresearch | ○ (git only) | ◐ fixed wall-clock per experiment | ○ single agent | ○ | ○ | ○ | ○ | ● |
| OpenEvolve / ShinkaEvolve | ◐ checkpoints every N | ○ | ◐ islands, parallel jobs (assumes independent evals) | ○ | ○ | ◐ cascade stages, but untyped scores | ◐ program archive | ● |
| AIDE / AI Scientist v2 | ? | ? | ? | ○ | ? | ○ | ? | ? |
| Inspect AI | ◐ per-sample episodes | ● scoped token/cost/time/working + custom | ◐ sub-agent limits | ◐ sandboxes (?) | ◐ approvals (?) | ○ | ◐ eval logs (?) | ● |
| AIOpsLab / ITBench | ○ | ○ | ○ | ● deploy/fault/workload/telemetry (AIOpsLab) | ○ | ◐ scored vs ground truth | ◐ | ● |
| Ray (substrate) | ? | ○ | ? (actors/resources — unverified) | ○ | ○ | ○ | ○ | ● |

### Things NOT possible or very hard in existing harnesses (inference, grounded in the findings above)
1. **One budget over three currencies.** No base meters clone-hours, replay compute or provisioned infra in the same ledger as tokens, or schedules against it ("is the next measurement worth $4 of clone time vs 200k tokens of investigation?"). Token-$ figures themselves are estimates that can reset or zero ([Claude cost docs](https://code.claude.com/docs/en/agent-sdk/cost-tracking)).
2. **Contention for a scarce, stateful measurement resource.** Parallelism in all of them assumes independent workers. None has leases on a DB, measurement serialization, or noise isolation (no co-located load, cache-state control, warmup, repeats).
3. **Expensive, non-idempotent environment transitions.** Reset means re-cloning or restoring a snapshot, and side effects (DDL, `ALTER SYSTEM`, restarts) are not safely re-executed on resume. LangGraph explicitly requires idempotent side effects ([durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)), and code harnesses assume a cheap `git reset`/fresh container ([PSRL](https://psrl.readthedocs.io/en/latest/examples/agentic_rl/swe/index.html)).
4. **Semantic blast-radius classification.** Permission systems gate *tool names and paths*, not "reversible index add on a clone" vs "irreversible table rewrite on prod". You must write the classifier yourself, and you can attach it to hooks or interrupts.
5. **Evidence provenance.** No base distinguishes an `estimated` score (cost model) from a `measured` one (wall clock), so the loop can self-certify. Evolutionary cascades even encourage it.
6. **Anti-fabrication of results.** Agents report numbers in text. Nothing forces every claimed number to reference a harness-recorded measurement event.
7. **Statistically rigorous measurement.** No base has repeats, confidence intervals, A/A noise floors or SLO-percentile checks.
8. **Lossless, provenance-typed trajectories across a swarm.** Traces are per agent or per session chat logs. Joining many agents plus environment events plus decisions with rejected alternatives into one `training_record.md` episode is custom work. OpenHands' event stream is the nearest starting point ([arXiv](https://arxiv.org/html/2511.03690v1)).
9. **Live-prod operation over days with deliberate guardrail removal as an experimental arm.** It is possible in principle with Claude hooks or permission modes, but no base offers *experiment-controlled* guardrail levels with matched logging.

### Recommendation framework
- **Do not build the model loop from scratch.** Tool-calling loops, subagents, context compaction, caching and permission hooks are commodity and well tested. Re-implementing them costs months for no research value (inference).
- **Do not adopt a framework as the control plane.** The four DB-specific requirements (R2, R3, R4, R6) are the research contribution and the safety-critical part. They need to sit *outside* any agent framework so that the agent cannot bypass them and the framework can be swapped (inference; consistent with Manus rebuilding four times — [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)).
- **Pick the inner-loop SDK by your top secondary priority:**
  - *Fastest path, strongest safety hooks:* Claude Agent SDK (hooks, permissions, subagents with spend caps). Risk: model lock-in for open-weight or fine-tuned Gen-DBA models (verify proxy support).
  - *Training-data and model-agnosticism first:* OpenHands SDK (event-sourced, replayable, multi-LLM). Risk: workspace and coding-centric runtime assumptions.
  - *RL rollouts of a fine-tuned model:* a mini-swe-agent-style minimal loop with the DB-ACI as its only tools. It is simplest to connect to GRPO stacks ([PSRL](https://psrl.readthedocs.io/en/latest/examples/agentic_rl/swe/index.html)).
  - Keep the agent ↔ control-plane boundary an MCP or typed tool interface, so all three can be run as arms of the same experiment.
- **Thin custom layer must own** (inference):
  1. *Budget ledger + scheduler*: authoritative token usage (provider APIs), metered clone/replay/infra $, wall-clock; reservations before spend; budget-aware admission of experiments.
  2. *Environment manager*: clone/branch provisioning, snapshot/reset, workload replay, leases on the fleet, a measurement queue with isolation, warmup and repeats.
  3. *DB-ACI*: typed verbs (orient / probe_whatif / apply / measure / rollback) that return provenance-tagged payloads. This is the only way the agent touches a system.
  4. *Action journal + safety policy*: intent → applied → verified → rolled-back, with idempotency keys; a reversibility/blast-radius classifier; per-arm guardrail level (`none … full approval`), enforced at the ACI, not in the prompt.
  5. *Evidence store + claim checker*: every number in a decision or report must cite a measurement event ID. `estimated` can never satisfy a "measured" acceptance check.
  6. *Record writer*: emits `training_record.md` episodes (header, events with `duration_s` and provenance, decisions with rejects, terminal), plus RL-replay projections.
  7. *Durable orchestration*: a LangGraph checkpointer, Temporal or Ray for the orchestrator's own state. Choosing an existing durable-execution engine here is cheaper than writing one.

### Gaps
- Licence and model-support facts for Claude Agent SDK, Codex CLI, OpenHands, AutoGen/AG2, CrewAI, MetaGPT, ADK and smolagents were not verified this session. Neither were Ray, Temporal and ITBench capabilities. The "?" matrix cells need a follow-up pass before publication.
- I found no published harness, from academia or industry, that targets *database performance optimization under a dollar budget on clones plus prod*. That absence is a weak signal (limited search), not a proven negative.
