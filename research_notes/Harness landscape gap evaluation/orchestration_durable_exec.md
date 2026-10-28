# Agent orchestration frameworks and durable-execution substrates vs. the autonomous DB-optimization harness rubric

Scope: LangGraph (+ LangChain Deep Agents), AutoGen / AG2 / Microsoft Agent Framework (MAF), CrewAI, Google ADK, smolagents, DSPy, Pydantic AI, LlamaIndex Workflows, OpenAI Agents SDK (Swarm successor), plus the durable-execution substrates Temporal, Ray (Workflows/Serve), Restate, DBOS, Inngest and Dapr Workflows. 2026 additions: Agent Lightning (RL trainer that wraps any framework), MAF 1.0 GA, Pydantic AI's 8-engine durable layer and Deep Agents. These are judged against R1–R10 for a no-human, budgeted agent that holds credentials to one DB.

Method and honesty notes. This pass used about 27 tool calls. Licences were read from the GitHub API and LICENSE files on 2026-10-26. "(inference)" marks my reasoning. "(background, not fetched)" marks facts I am confident of but did not re-fetch this session. Vendor posts (Diagrid, Restate) are flagged as interested parties. This pass also resolves the "?" cells for AutoGen/AG2, CrewAI, ADK, smolagents and Ray in the prior note `Holistic database optimization harness/harness_baselines_build_vs_adopt.md`. Its LangGraph cells are refined below: its R1 "●" is downgraded to "◐" because recovery is manual and the in-flight node re-runs.

---

## Q1. How does each durable-execution engine treat non-idempotent side effects (the DDL / restart case)?

### Takeaway
None of the engines (Temporal, DBOS, Restate, Inngest, Ray, Dapr, or the framework checkpointers) gives exactly-once for an external side effect. All of them give "memoize after completion, re-run the step that was in flight" (at-least-once), or at-most-once if you turn retries off, in which case the outcome is unknown. The one documented exactly-once case is DBOS `@transaction`: the write and the checkpoint commit atomically in the *same* Postgres database. It does not cover DDL like `CREATE INDEX CONCURRENTLY`, `ALTER SYSTEM`, restarts, or non-Postgres engines. Crash safety for DDL therefore has to come from a harness-owned intent journal plus *reconcile-by-observation* (query the catalog to decide whether the effect happened). No substrate supplies that.

### Cited Findings
**Temporal**
- Activities: "We recommend that it be idempotent, so retries can be processed without duplicate side effects". "If an Activity attempt fails, it is automatically retried using its Retry Policy". "Each attempt starts from the initial state, unless your code uses a Heartbeat detail payload for checkpointing" — [Temporal: Activities](https://docs.temporal.io/activities)
- The default Activity retry policy is initial interval 1 s, backoff 2.0, max interval 100× initial, and **Maximum Attempts "unlimited"**. "Setting the value to 1 means a single execution attempt and no retries". Errors can be marked non-retryable — [Temporal: Retry policies](https://docs.temporal.io/encyclopedia/retry-policies)
- Event History is "limited to 51,200 Events or 50 MB", with a warning after 10,240 events / 10 MB — [Temporal: limits](https://docs.temporal.io/workflow-execution/limits)
- Licence: MIT (server repo `temporalio/temporal`) — [GitHub API](https://api.github.com/repos/temporalio/temporal)

**DBOS**
- "once a step completes and is checkpointed, it is never re-executed". "If a workflow fails while executing a step, it retries the step during recovery", so steps should be idempotent. Workflow functions must be deterministic — [DBOS architecture](https://docs.dbos.dev/architecture)
- Transactions are exactly-once because the application write and the DBOS durability record commit atomically in your database. A plain step that writes to a DB "may re-execute (and re-commit) if the process crashes after the write but before the step is checkpointed" — [DBOS Go transaction tutorial](https://docs.dbos.dev/golang/tutorials/transaction-tutorial); [DBOS Java step factories](https://docs.dbos.dev/java/tutorials/step-factory-tutorial); [DBOS outbox example](https://docs.dbos.dev/python/examples/outbox) (I read search snippets of these, not the full pages)
- The June 2026 release added pluggable datasources for exactly-once transactional steps against multiple databases — [What's new in DBOS, June 2026](https://dbos.dev/blog/new-in-dbos-june-2026) (snippet)
- Queues give rate and concurrency limits per queue and per worker. The system DB stores schedule and queue state — [DBOS architecture](https://docs.dbos.dev/architecture)
- Scheduled workflows use an idempotency key built from schedule name and scheduled time, so "each scheduled invocation occurs exactly once" while the app is active, even across restarts. Schedules are stored in the DB and can be paused/resumed — [DBOS Python scheduled workflows](https://docs.dbos.dev/python/tutorials/scheduled-workflows); [DBOS Java](https://docs.dbos.dev/java/tutorials/scheduled-workflows) (snippets)
- Licence: MIT (`dbos-transact-py`) — [GitHub API](https://api.github.com/repos/dbos-inc/dbos-transact-py)

**Restate**
- Restate "tracks every step of your code execution in a journal". On failure it replays the journal and skips completed steps. Request-level idempotency keys deduplicate whole invocations. The docs give no guidance on making the side effect inside a step idempotent — [Restate durable execution](https://docs.restate.dev/concepts/durable_execution)
- A third-party test (Oct 2026) killed a worker between a tool's side effect and `ctx.run` recording its result. It got **duplicate charges in 3/3 trials**, and kills at other points gave single charges. The mitigation was an idempotency key from `ctx.rand.uuidv4()` honoured by the callee — [nerdleveltech](https://nerdleveltech.com/restate-durable-agent-duplicate-tool-calls-tested) (read from a search snippet only; the fetch returned HTTP 429)
- Licence: **Business Source License 1.1**, with an additional use grant that excludes a "Public Restate Platform Service" — [restate LICENSE](https://raw.githubusercontent.com/restatedev/restate/main/LICENSE)

**Inngest**
- "Later requests replay saved results (memoization)". A step's result is saved only on success. The docs say "Make `refundOrder` idempotent because a refund can succeed before Inngest saves the step result and retries the step". Durable Endpoints "should last no longer than 60 seconds"; use workflows for longer work. Concurrency is a built-in flow control. Triggers are event, schedule or webhook — [Inngest: how functions are executed](https://www.inngest.com/docs/learn/how-functions-are-executed)
- Licence: the server and CLI are under **SSPL** with delayed open-source publication under Apache 2.0. The SDKs are Apache 2.0 — [inngest LICENSE.md](https://raw.githubusercontent.com/inngest/inngest/main/LICENSE.md); [README](https://github.com/inngest/inngest)

**Ray**
- Ray Workflows is "deprecated and will be removed in a future version of Ray". It was alpha in Ray 2.0+. A Ray moderator said there is no plan to replace it and pointed users to Airflow or Temporal — [Ray Workflows docs](https://docs.ray.io/en/latest/workflows/index.html); [Ray forum](https://discuss.ray.io/t/ray-workflows-deprecated/22132)
- Licence: Apache-2.0 — [GitHub API](https://api.github.com/repos/ray-project/ray)

**Framework-level checkpointers (same semantics, weaker supervision)**
- LangGraph time travel: "Nodes after the checkpoint re-execute, including any LLM calls, API requests, and interrupts". Pending writes from successful sibling nodes in a failed superstep are kept and not re-run — [LangGraph time travel](https://docs.langchain.com/oss/langgraph/use-time-travel); [LangGraph checkpointers](https://docs.langchain.com/oss/langgraph/checkpointers)
- LangGraph `interrupt()`: on resume "execution ... starts at the beginning of the node" — [LangGraph interrupts](https://docs.langchain.com/oss/langgraph/interrupts)
- Google ADK resume: it "reinstates the results from the tools A and B, and resumes the workflow by re-running the tool C request". Tools run "at least once" and "may run more than once when resuming". Custom Agents are not resumable by default. Requires Python ADK ≥1.16 — [ADK: resume stopped agents](https://adk.dev/runtime/resume/index.md)
- Pydantic AI durable layer: "A restarted run replays the completed ones from the journal and retries the one in flight" — [Pydantic AI durable execution](https://pydantic.dev/docs/ai/integrations/durable_execution/overview/)
- MAF: checkpoints are created "at the end of each superstep, after all executors in that superstep have completed". Resume is by explicit `checkpoint_id`, and the rebuilt workflow "must preserve the topology and executor identities". Storage options are in-memory, file and Cosmos DB, and the docs say "Checkpoint storage is a trust boundary" (pickle with a restricted unpickler) — [MAF checkpoints, MS Learn, 2026-09](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)

**PostgreSQL facts that make the DB case hard** (background, not fetched): `CREATE INDEX CONCURRENTLY` "cannot be executed inside a transaction block", and a failed concurrent build leaves an INVALID index that must be dropped — [PG docs: CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html). `ALTER SYSTEM` "cannot be executed inside a transaction block" — [PG docs: ALTER SYSTEM](https://www.postgresql.org/docs/current/sql-altersystem.html).

### Inferences
- (inference) Scenario T1 (Temporal): an activity runs `CREATE INDEX CONCURRENTLY ix ...`. The worker dies 40 min into the build, and the session dies with it, so PG aborts the build and leaves `ix` INVALID. The default policy (unlimited retries) re-runs the DDL, which fails with "relation already exists". Or, with `IF NOT EXISTS`, it silently succeeds and *keeps the INVALID index*. Correct handling: before acting, the activity reads the journal and the catalog (`pg_index.indisvalid`) and branches to create, drop-and-recreate, or no-op. That is engine- and DDL-specific code the substrate cannot provide.
- (inference) Scenario T2 (restart): `pg_ctl restart` or a cloud reboot API succeeds, then the worker crashes before completion is recorded. Retry restarts the production DB a second time. Temporal `MaximumAttempts=1` prevents that, but leaves a "did it happen?" ambiguity that only an observation (postmaster start time, `pg_postmaster_start_time()`) resolves.
- (inference) DBOS exactly-once transactions are tempting for Postgres targets. Using them would put DBOS system tables into the target DB, which is a write the agent role may lack and a footprint on prod. It also cannot wrap non-transactional DDL. And it is Postgres-specific, which breaks engine-agnosticism. Use DBOS's system DB as a *separate* harness store, not co-located.
- (inference) The general rule: durable engines make the *orchestrator's* progress crash-safe and make *pure* or *journal-guarded* steps replay-safe. For the agent's free-form `psql` tool, the harness must (a) write an intent record with an idempotency token before execution, (b) execute, (c) record the result, and (d) on recovery of an intent without an outcome, run an engine-specific reconcile probe. When the action is learned free text, the harness cannot know the probe in general. So the honest fallback is to surface "uncertain outcome of command X" to the model as an observation after resume. That makes the model responsible for reconciliation, which is itself trainable behaviour.
- (inference) The 51,200-event cap matters for hours-to-days loops: each model call and each tool call is at least one activity (several history events). A multi-day run with thousands of shell calls needs Continue-As-New with the conversation state carried over, so context or memory compaction becomes a harness concern.

### Gaps
- I did not find an official Restate statement on crash-between-effect-and-journal semantics. The duplicate test is a single third-party post that I could not fetch in full.
- Temporal Schedules (overlap policy, catch-up window) and Dapr Workflows semantics were not fetched this session. Dapr is Apache-2.0 per the [GitHub API](https://api.github.com/repos/dapr/dapr). Its at-least-once activity semantics are background knowledge, not verified.
- No GitHub issue was found that documents a real duplicated DDL under any engine. The scenarios above are constructed from the documented semantics.

---

## Q2. Agent frameworks: what each provides per rubric, and which assumptions break

### Takeaway
All of these frameworks are inner-loop libraries built around request/response chat with a turn or step cap. None has an authoritative dollar budget, a wall-clock deadline exposed to the model, a contention model for a shared external resource, or a separation between agent and monitor. Their "durability" is checkpoint-and-manual-resume, with the in-flight step re-executed. LangGraph and ADK are the most explicit about this. MAF is newest (GA April 2026), and Pydantic AI delegates durability to eight external engines. They are acceptable as a thin model loop. None should own durability, budget, or monitoring.

### Cited Findings
**LangGraph + Deep Agents (MIT)**
- Durability modes are `exit`/`async`/`sync`. The docs say make workflows "deterministic and idempotent" and "wrap any side effects ... inside tasks" — [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- Vendor critique (Diagrid, Feb 2026): there is "No automatic failure detection" and "No automatic resumption". Resume is `graph.invoke(None, config)` with the same `thread_id`. There is no coordination preventing two processes resuming one thread, and the OSS library is single-process with no task queue — [Diagrid](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) (competitor vendor)
- Deep Agents: MIT, with `write_todos` planning, filesystem tools (read/write/edit/ls/glob/grep), a `task` subagent tool with isolated contexts and async subagents. It follows a "trust the LLM" model, and the docs advise enforcing limits at the tool or sandbox level — [deepagents README (npm)](https://cdn.jsdelivr.net/npm/deepagents@1.10.2/README.md); [LangChain reference](https://reference.langchain.com/javascript/deepagents); [jimmysong summary](https://jimmysong.io/ai/deepagents) (secondary)
- Licences: langgraph MIT, deepagents MIT — [GitHub API langgraph](https://api.github.com/repos/langchain-ai/langgraph); [GitHub API deepagents](https://api.github.com/repos/langchain-ai/deepagents)

**AutoGen / AG2 / Microsoft Agent Framework**
- AutoGen has been in maintenance mode (bug and security fixes only) since about Oct 2025. MAF 1.0 GA was around 2 April 2026, and AutoGen v0.2 code does not run unmodified on MAF — [Atlan](https://atlan.com/know/ai-agent/what-is-autogen/); [byteiota](https://byteiota.com/?p=16638) (secondary; dates not confirmed on MS Learn)
- MAF checkpoints happen at superstep boundaries and require an explicit restore (see Q1) — [MS Learn](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints). Diagrid says recovery is manual: "no supervisor, no scheduler, no automatic restart" — [Diagrid: Still not durable](https://www.diagrid.io/blog/still-not-durable-how-microsoft-agent-framework-and-strands-agents-repeat-the-same-mistake) (vendor, snippet)
- Licences: MAF MIT — [GitHub API](https://api.github.com/repos/microsoft/agent-framework); AutoGen code MIT (the repo SPDX reads CC-BY-4.0 for docs; code is in LICENSE-CODE) — [LICENSE-CODE](https://raw.githubusercontent.com/microsoft/autogen/main/LICENSE-CODE); AG2 Apache-2.0 — [GitHub API](https://api.github.com/repos/ag2ai/ag2)

**CrewAI (MIT)**
- `crewai replay -t <task_id>` "only retains the last kickoff". The Flow `@persist` decorator saves to SQLite after each method, but "the framework does not skip completed steps automatically". The agent's mid-ReAct cursor is not persisted. Defaults are `max_retry_limit`=2 and `max_iter`=20. There is "no locking or deduplication" for concurrent recovery — [Diagrid](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) (vendor; not cross-checked against CrewAI docs)
- Licence MIT — [GitHub API](https://api.github.com/repos/crewAIInc/crewAI)

**Google ADK (Apache-2.0)**
- Sessions are immutable event logs, with in-memory, DB (SQLite/PG/MySQL) and Vertex backends. Resume re-invokes with the original `invocation_id`. The caller must detect the interruption, and there is no watchdog — [Diagrid](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) (vendor); resume semantics confirmed in [ADK docs](https://adk.dev/runtime/resume/index.md)
- Restate ships an ADK integration (Jan 2026) for automatic recovery — [Restate blog](https://restate.dev/blog/build-resilient-ai-agents-with-restate-and-google-adk)
- Licence Apache-2.0 — [GitHub API](https://api.github.com/repos/google/adk-python)

**smolagents (Apache-2.0)**
- CodeAgent can run code remotely with `executor_type="e2b"` or `"docker"`. That sandboxes only the code, "doesn't support multi-agents", and requires passing state between the environment and the sandbox. The local executor is not a security boundary: import allowlists and op caps are best-effort — [smolagents secure code execution](https://huggingface.co/docs/smolagents/v1.21.0/tutorials/secure_code_execution)
- Licence Apache-2.0 — [GitHub API](https://api.github.com/repos/huggingface/smolagents)

**Pydantic AI (MIT)**
- Supports "eight durable execution engines, plus a builder for any other engine": Temporal, DBOS, Prefect and Restate (co-maintained with the vendors), plus AWS Lambda, Absurd, pgtask and Airflow. Model requests and tool calls are journalled as durable units, and the in-flight one is retried — [Pydantic AI durable execution](https://pydantic.dev/docs/ai/integrations/durable_execution/overview/)
- Licence MIT — [GitHub API](https://api.github.com/repos/pydantic/pydantic-ai)

**LlamaIndex Workflows (MIT)**
- Durability comes through DBOS (`llama-agents-dbos`, "every workflow transition is automatically persisted", SQLite default) or DIY context saving. A secondary summary calls the workflows ephemeral by default — [DBOS LlamaIndex integration](https://docs.dbos.dev/integrations/llamaindex); [hyper.ai summary](https://hyper.ai/en/stories/b743f264940468bceb23c65273b07893) (secondary); [Workflows 1.0](https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems)
- Licence MIT — [GitHub API](https://api.github.com/repos/run-llama/llama_index)

**OpenAI Agents SDK (Swarm successor; MIT)**
- Swarm's repo is still MIT but last pushed 2026-04 — [GitHub API swarm](https://api.github.com/repos/openai/swarm). Agents SDK MIT — [GitHub API](https://api.github.com/repos/openai/openai-agents-python)
- Tracing is "extensible by design, supporting custom spans" with external destinations. Long-running durability is delegated to Temporal — [PyPI openai-agents](https://pypi.org/p/openai-agents). The Temporal plugin runs the agent loop in the Workflow and the model calls as Activities. `activity_as_tool` wraps Activities as tools. Model calls are "not repeated during Workflow replay" — [Temporal: OpenAI Agents integration](https://docs.temporal.io/develop/python/integrations/openai-agents); [cookbook](https://docs.temporal.io/ai-cookbook/openai-agents-sdk-python)
- Non-OpenAI models are supported through Chat-Completions-compatible endpoints or LiteLLM. Per one review, traces default to OpenAI's backend even for other providers — [PyPI](https://pypi.org/project/openai-agents/); [Geekflare](https://geekflare.com/open-source/openai-agents-sdk/) (secondary). `max_turns` caps the loop — [tessl registry](https://tessl.io/registry/tessl/pypi-openai-agents) (secondary)

**DSPy (MIT)** — a program/prompt optimizer, not a runtime. It is relevant only for tuning sub-prompts or modules — [GitHub API](https://api.github.com/repos/stanfordnlp/dspy) (licence); role per the prior note.

**Mastra (TypeScript)** — mixed licence: `ee/` directories are under a separate enterprise licence — [mastra LICENSE.md](https://raw.githubusercontent.com/mastra-ai/mastra/main/LICENSE.md). Features not evaluated.

### Inferences — assumptions that break here
- (inference) **Chat-centric, request/response.** Every framework's unit is a "run" triggered by a user message that ends when the model stops calling tools or hits `max_turns`/`max_iter`/`recursion_limit`. Our episode is triggered by a budget and a deadline, not by a message. "Stop" has to be decided by remaining wall-clock and dollars, with a guaranteed report phase. None of them reserves budget for the report. When the cap is hit they raise an error (LangGraph's recursion error, CrewAI's max_iter), so the agent never writes its diagnosis. Failure scenario: a 10-minute triage run hits the turn cap at minute 9 mid-`EXPLAIN ANALYZE` and produces no report.
- (inference) **No notion of external resource cost.** Token counts may be exposed, but none of them meters DB-side cost (a 30-min `ANALYZE` on prod, cloud instance-hours, I/O credits) or makes it visible to the model. R2's "authoritative $" must come from provider billing or usage APIs plus cloud metering, joined by the harness.
- (inference) **Replay-from-node.** LangGraph, MAF, ADK and Pydantic AI all re-run the interrupted unit. If the "unit" is a whole ReAct node (LangGraph's prebuilt agent node, a CrewAI task), the re-run repeats *every* tool call in that node since its last checkpoint, not just the last one. Granularity matters. Only per-tool-call journalling (Temporal activity per tool, ADK per tool, Pydantic AI per tool) bounds the duplicate to one command.
- (inference) **Parallel subagents assume independent workers.** Deep Agents' `task`, MAF's Concurrent/Magentic, CrewAI crews and ADK ParallelAgent fan out with no lease on the shared DB. Failure scenario: two subagents each run `CREATE INDEX` and `VACUUM FULL` on the same hot table. They contend for locks, pass each other's lock waits off as "regressions", and both report wrong causal attributions. Contention control (an advisory-lock or lease service and a measurement mutex) must be harness-side. DBOS or Inngest queue concurrency limits can *implement* the mutex for harness-mediated tools, but cannot stop a raw `psql` shell from opening its own sessions.
- (inference) **Hooks and traces live inside the agent process.** OTel spans, LangSmith traces, MAF events and RunHooks are emitted by code in the same process as the shell tool. An agent with shell access on that host can, in principle, edit the tracer, kill the exporter or forge spans. For R6 none of these is "tamper-proof". The effect-level monitor must observe the DB itself (server logs, `pg_stat_statements`, audit extension, catalog diffs, OS metrics) through a channel the agent role cannot write. Durable-engine histories (Temporal or DBOS system DB) are useful as a second, harness-side record only if the agent's shell runs in a different security principal from the worker.
- (inference) **Permission models.** Most frameworks have no permission model ("trust the LLM", Deep Agents). The HITL primitives (LangGraph `interrupt`, ADK tool confirmation, MAF request/response) are designed for humans. For R10 this is acceptable: "unattended" means no approval gates. Loggability then has to be supplied by the harness journal, not by the framework's approval log.

### Gaps
- CrewAI, MAF and ADK claims about auto-recovery are taken largely from Diagrid, a competitor vendor. They match the official ADK and MAF docs I read but were not checked against CrewAI's own docs.
- I found no practitioner GitHub issue where a framework re-executed DB DDL on resume. The LangGraph-node and duplicate-tool-call risk is documented behaviour, not a reported incident.
- I did not evaluate AWS Strands Agents (the repo moved, API redirect), or Mastra or Dapr Agents features, in depth.

---

## Q3. R7/R9: token-exact traces and RL-rollout compatibility

### Takeaway
No orchestration framework records token IDs. They store strings and messages. Exact RL needs token-in/token-out (TITO) at the inference server, such as vLLM `return_token_ids`, plus a trainer-side tracer. Agent Lightning (MIT, Microsoft) is the 2026 bridge that wraps existing frameworks via OTel-style tracing. It is worth adopting at the tracing and training boundary, independent of the orchestration choice.

### Cited Findings
- Retokenization drift: "tokens are detokenized during inference and subsequently retokenized during training", so the two can differ even when the strings match. vLLM added `return_token_ids` to its OpenAI-compatible endpoints — [vLLM blog](https://vllm.ai/blog/2025-10-22-agent-lightning)
- The Agent Lightning v1.0 paper (arXiv 2608.17528) names chat-template non-compositionality and decode–retokenize drift. For example, Qwen's template can strip an earlier think marker and break prefix continuity — [arXiv 2608.17528](https://arxiv.org/pdf/2608.17528)
- HF "TITO done right": never re-encode decoded tokens, and require prefix-preserving templates for tool messages — [HF blog](https://huggingface.co/blog/huggingface/tito). LMSYS Miles: the trainer must evaluate the exact token sequence the engine consumed and produced — [LMSYS](https://www.lmsys.org/blog/2026-05-13-no-token-left-behind)
- Agent Lightning decouples agent execution from training and works with LangChain, OpenAI Agents SDK, AutoGen or custom agents "with almost zero code modifications". It captures LLM I/O through instrumentation and sends it to a Lightning server. It has a LangGraph + VERL/GRPO example — [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2025/10/microsoft-agent-lightning/) (secondary); [arXiv 2508.03680](https://www.alphaxiv.org/abs/2508.03680v1). Licence MIT — [GitHub API](https://api.github.com/repos/microsoft/agent-lightning)

### Inferences
- (inference) R7 for every framework in the table is "◐ at best": they capture messages and tool I/O, and token exactness comes only from the serving layer. A framework that rewrites history (summarization middleware in Deep Agents, context compaction, Continue-As-New carry-over) breaks prefix continuity by design. RL training then needs per-call segments, not one long sequence.
- (inference) R9 (training across harness variants) is easiest when the harness is a small owned loop whose prompt, tool set, observation tools, budget-display format and compaction policy are config fields. Graph frameworks bake topology into code, and MAF checkpoints even require identical "topology and executor identities" to resume ([MS Learn](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)). That makes harness-variant sweeps awkward.

### Gaps
- I did not verify which frameworks pass through `return_token_ids` or logprobs from vLLM responses unmodified. Most wrap provider SDKs that drop unknown fields; this is unverified.

---

## Q4. Rubric matrix

Legend: ● first-class documented · ◐ partial · ○ absent · ? unverified. Cells are my assessment from the citations above (section in brackets). "n/a" means the system is not an agent loop.

| Candidate (licence) | R1 long-horizon + crash-safe w/ non-idempotent effects | R2 wall-clock + authoritative $, visible, graceful stop | R3 headless/cron + cross-episode memory | R4 MCP/custom tools + shell | R5 parallel subagents + contention on one DB | R6 external tamper-proof monitor attachable | R7 token-exact traces / RL | R8 model-agnostic incl. open-weight | R9 harness-variant configurability | R10 unattended permissions, loggable |
|---|---|---|---|---|---|---|---|---|---|---|
| LangGraph (MIT) | ◐ checkpointer; manual resume; node re-runs [Q1,Q2] | ○ recursion_limit only | ◐ via LangGraph Platform/cron (?), store for memory (?) | ● tools/MCP (background) | ◐ fan-out, no leases | ◐ traces in-process [Q2] | ◐ messages | ● | ◐ topology in code | ● no gates by default; interrupt for HITL |
| Deep Agents (MIT) | ◐ inherits LangGraph | ○ | ◐ filesystem memory | ● fs + shell/sandbox + MCP | ◐ `task` subagents, isolated ctx, no DB leases | ◐ | ◐ | ● "any model" | ◐ middleware composable | ● "trust the LLM" |
| MAF 1.0 (MIT) / AutoGen (MIT, maintenance) / AG2 (Apache) | ◐ superstep checkpoints; explicit restore; topology-locked [Q1] | ○ | ? (Azure hosting) | ● (background) | ◐ Concurrent/Magentic, no leases | ◐ | ◐ | ◐ (?) | ○ topology-locked checkpoints | ◐ |
| CrewAI (MIT) | ○/◐ `@persist`, no auto-skip; last kickoff only [Q2] | ○ max_iter | ? | ● (background) | ◐ crews, no locking | ◐ | ◐ | ● (background) | ◐ | ◐ |
| Google ADK (Apache) | ◐ resumable ≥1.16, per-tool at-least-once, caller must detect [Q1] | ○ | ◐ DB/Vertex sessions + memory | ● (background) | ◐ ParallelAgent (background) | ◐ plugins in-process | ◐ event log | ◐ Gemini-first; LiteLLM (background, ?) | ◐ | ◐ confirmation is HITL |
| smolagents (Apache) | ○ | ○ max_steps | ○ | ● code-as-action | ○ "doesn't support multi-agents" remotely [Q2] | ○ | ◐ | ● | ● tiny | ○ local executor not a boundary |
| DSPy (MIT) | n/a | n/a | n/a | ◐ | n/a | n/a | ◐ | ● | ● (as optimizer) | n/a |
| Pydantic AI (MIT) | ● when on Temporal/DBOS/Restate; in-flight retried [Q1] | ◐ usage limits (background, ?) | ◐ via engine schedules | ● MCP (background) | ◐ | ◐ | ◐ | ● | ◐ | ◐ |
| LlamaIndex Workflows (MIT) | ◐ via DBOS integration | ○ | ○ | ● | ◐ | ◐ | ◐ | ● | ◐ | ◐ |
| OpenAI Agents SDK (MIT) | ● with Temporal plugin (model calls = activities) [Q2] | ○ max_turns | ◐ sessions (Redis etc.) | ● MCP | ◐ handoffs/agents-as-tools | ◐ custom TracingProcessor | ◐ | ◐ Chat-Completions/LiteLLM | ◐ | ◐ guardrails (HITL-oriented) |
| Temporal (MIT) | ● orchestrator; activities at-least-once (unlimited default) or at-most-once [Q1] | ◐ timeouts; no $ | ● Schedules (background) + workflow state | n/a substrate | ◐ task queues/rate limits (background) | ● history server-side, separate principal possible | ○ | ● | ● | ● |
| DBOS (MIT) | ● steps at-least-once; transactions exactly-once same-DB only [Q1] | ○ | ● exactly-once cron schedules [Q1] | n/a | ● queue concurrency limits | ● system DB (separate PG) | ○ | ● | ● | ● |
| Restate (BSL 1.1) | ● journal; crash-between-effect duplicates reported [Q1] | ○ | ◐ | n/a | ◐ virtual objects (background, ?) | ● server journal | ○ | ● | ● | ● |
| Inngest (SSPL server) | ● memoized steps; at-least-once [Q1] | ○ | ● schedules | n/a | ● concurrency flow control | ◐ (cloud-hosted state) | ○ | ● | ● | ● |
| Ray (Apache) | ○ Workflows deprecated [Q1] | ○ | ◐ | n/a | ◐ actors/resources (background) | ○ | ○ | ● | ● | n/a |
| Agent Lightning (MIT) | n/a | n/a | n/a | n/a | n/a | ◐ tracer is agent-side | ● with TITO serving [Q3] | ● | ● framework-agnostic | n/a |

Every row is ○ on authoritative dollars, deadline-visible-to-model and graceful report reservation. Every row lacks an effect-level DB monitor. These must be built.

---

## Q5. Adopt as substrate vs. not

### Takeaway
Adopt **one durable-execution engine for the harness's own control loop** and **TITO serving plus an Agent-Lightning-style tracer for RL**. Keep the model loop a small owned loop rather than a graph framework. Build budget, contention, intent journal and reconcile, and the effect-level monitor yourself. Recommended durable engine: **DBOS** (MIT, a Postgres library, exactly-once schedules, queue concurrency limits, no extra server) for a lab-scale single-node harness. Use **Temporal** (MIT) if you need multi-host workers, strong separation between the agent principal and the orchestrator history, and mature tooling. Avoid Restate (BSL) and Inngest (SSPL server) for an open research artifact unless the licence fits. Avoid Ray Workflows (deprecated).

### Cited Findings
- DBOS: steps are checkpointed and not re-run, there are queue concurrency limits, and schedules run exactly once via idempotency key; MIT — [DBOS architecture](https://docs.dbos.dev/architecture); [scheduled workflows](https://docs.dbos.dev/python/tutorials/scheduled-workflows); [GitHub API](https://api.github.com/repos/dbos-inc/dbos-transact-py)
- Temporal: retry and at-most-once control per activity, heartbeat checkpointing, a 51,200-event history cap, and an OpenAI-Agents integration with model calls as activities; MIT — [retry policies](https://docs.temporal.io/encyclopedia/retry-policies); [activities](https://docs.temporal.io/activities); [limits](https://docs.temporal.io/workflow-execution/limits); [OpenAI Agents integration](https://docs.temporal.io/develop/python/integrations/openai-agents)
- Restate is BSL 1.1 — [LICENSE](https://raw.githubusercontent.com/restatedev/restate/main/LICENSE). Inngest's server is SSPL — [LICENSE.md](https://raw.githubusercontent.com/inngest/inngest/main/LICENSE.md). Ray Workflows is deprecated — [Ray docs](https://docs.ray.io/en/latest/workflows/index.html)

### Inferences — concrete adoption plan
- (inference) **Wrap each tool call as a durable step or activity, never a whole ReAct turn.** Configure shell and psql activities with `MaximumAttempts=1` (Temporal) or no automatic step retry. On recovery, inject an "outcome unknown" observation plus harness-run reconcile probes (catalog diff, postmaster start time) instead of retrying. LLM calls *can* be retried (they are idempotent up to the cost of tokens), but their cost must be booked even on failure.
- (inference) **Budget as a durable workflow variable.** Keep the dollar ledger (provider usage API plus cloud metering) and a wall-clock deadline in workflow state. Inject `remaining_time` and `remaining_$` into every model turn. Reserve a fixed slice for the mandatory report step, enforced by a durable timer (Temporal timers or DBOS sleep). That gives anytime behaviour: when the timer fires the loop switches to "report" regardless of model intent.
- (inference) **Cron and continuous runs plus memory.** A DBOS or Temporal schedule launches episodes. Cross-episode memory is a harness-owned store, separate from the target DB, summarised into the next episode's prompt. An overlap policy of "skip if previous still running" (Temporal Schedules, background) prevents two episodes on one DB.
- (inference) **Contention.** Harness-mediated high-level tools go through a queue with concurrency 1 per "measurement" resource (DBOS queues or Temporal task-queue rate limits). For raw shell, give each subagent a distinct DB role or `application_name` so the external monitor can attribute effects, and use DB advisory locks inside a harness `apply` wrapper. Raw-shell contention can only be *observed*, not prevented, unless the shell is mediated.
- (inference) **Monitor separation.** Run the durable engine's system store, the effect monitor (DB logs, catalog snapshots, metrics) and the reward computation under a principal the agent's DB role and OS user cannot write. The orchestration history is then a second witness to compare against the monitor's effect stream. Divergence (a command in the history with no matching effect, or an effect with no command) is itself a reward-hacking signal.
- (inference) **What not to adopt.** Do not let LangGraph, CrewAI, MAF or ADK own durability. Their manual resume, node-level replay and topology-locked checkpoints conflict with R1 and R9. Deep Agents and smolagents are useful *references* for minimal harness design (todo tool, filesystem memory, code-as-action), not foundations. DSPy is out of scope as runtime.

### Gaps
- I did not benchmark DBOS vs Temporal overhead per step for thousands of shell calls.
- Whether Pydantic AI's Temporal/DBOS wrappers let you set per-tool retry=0 and inject custom reconcile logic is unverified. If they do, Pydantic AI would be the cheapest "framework + substrate" combination to try as one harness variant.
