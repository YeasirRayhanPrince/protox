# Coding-agent harnesses and agent SDKs vs. an autonomous, budgeted, single-environment DB-optimization agent

Scope: Claude Agent SDK / Claude Code headless, OpenAI Codex CLI (`codex exec`) and OpenAI Agents SDK, OpenHands Software Agent SDK, SWE-agent / mini-swe-agent, Gemini CLI (now Antigravity CLI), OpenCode, Goose. Each is scored on rubric R1–R10 from the brief. Legend: ● first-class (documented) · ◐ partial · ○ absent · ? unverified. "(inference)" marks my reasoning. Anything not cited is in Gaps.

Method: about 25 tool calls, dated 2026-10-26. I skimmed the prior note `Holistic database optimization harness/harness_baselines_build_vs_adopt.md` and did not repeat what it verified. This session closes several of its "?" cells:
- OpenHands licence: MIT.
- Codex sandbox and approval modes, and `exec resume`.
- The Claude SDK licence position and the Claude open-weight route, via vLLM's Anthropic-format endpoint.

These facts were verified in the prior note and are reused here without re-verifying:
- Claude `max_budget_usd` is a client-side estimate, resets on resume or `/clear`, and can be zeroed on crash ([Claude cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)).
- OpenHands is event-sourced with deterministic replay ([arXiv 2511.03690](https://arxiv.org/html/2511.03690v1)).
- The OpenAI Agents SDK gets durability through Temporal ([PyPI](https://pypi.org/p/openai-agents)).
- mini-swe-agent appears in RL stacks ([PSRL](https://psrl.readthedocs.io/en/latest/examples/agentic_rl/swe/index.html)).

---

## Q1. Claude Agent SDK / Claude Code headless (`-p`, hooks, subagents, permission modes, cost tracking)

### Takeaway
This is the richest inner loop for R4, R6 and R10. It has about 35 hook events, a six-step permission order in which hooks run first, and a `dontAsk` mode for headless use. It fails R2: the dollar cap is an estimate checked only after each call, and the ledger has documented accounting bugs. It is also weak on R1 for non-idempotent effects, R7 (no token IDs) and R8. It is Anthropic-format only, and Anthropic does not support non-Claude models, although vLLM provides a working route.

### Cited Findings
**Scores**
- **R1 ◐.** Sessions persist the conversation as JSONL under `~/.claude/projects/<encoded-cwd>/*.jsonl`, with `continue`, `resume` and `fork`. A `SessionStore` adapter is available for cross-host resume. The docs say: "Sessions persist the **conversation**, not the filesystem", and file checkpointing only reverts *files* — [Claude sessions](https://code.claude.com/docs/en/agent-sdk/sessions). Nothing models external side effects such as DB state. The docs themselves suggest: "Don't rely on session resume. Capture the results you need ... as application state" — [same](https://code.claude.com/docs/en/agent-sdk/sessions)
  - Open resume and transcript bugs, Sept–Oct 2026:
    - A deferred-tool resume drops the supplied `tool_result` ([#97358](https://github.com/anthropics/claude-code/issues/97358)).
    - A retry notice's `parentUuid` can point at a row that is never written ([#96628](https://github.com/anthropics/claude-code/issues/96628)).
    - A compaction is undone on resume ([#95328](https://github.com/anthropics/claude-code/issues/95328)).
    - A turn goes permanently idle with a dropped `tool_result` ([#94252](https://github.com/anthropics/claude-code/issues/94252)).
- **R2 ◐.** `--max-budget-usd` / `max_budget_usd` exist, and runs can end with `error_max_budget_usd` and then be resumed with a higher limit — [sessions](https://code.claude.com/docs/en/agent-sdk/sessions). The figures are client-side estimates — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking). Open accounting bugs:
  - The cap "is checked after each call returns, so a $1 cap stops at $1.38". A $10 cap stopped at $12.06 — [#100111](https://github.com/anthropics/claude-code/issues/100111)
  - After a mid-stream API error and a non-streaming retry, usage counts both calls — [#101951](https://github.com/anthropics/claude-code/issues/101951)
  - `set_model` sends a billed request that `total_cost_usd` and `modelUsage` miss — [#101954](https://github.com/anthropics/claude-code/issues/101954)
  - The cap is print-mode only — [#95964](https://github.com/anthropics/claude-code/issues/95964)
  - "Uncontrolled API spending on non-Anthropic providers during failed test runs" — [#97821](https://github.com/anthropics/claude-code/issues/97821)

  I found no wall-clock limit or remaining-budget signal to the model in the docs I fetched (see Gaps).
- **R3 ◐.** Headless `-p` and the SDK work under cron (inference: any CLI can be cron'd). Memory across episodes is only the conversation transcript or CLAUDE.md-style files, not a typed store — [sessions](https://code.claude.com/docs/en/agent-sdk/sessions).
- **R4 ●.** Custom tools and MCP servers, with tool names `mcp__<server>__<action>` — [hooks doc](https://code.claude.com/docs/en/agent-sdk/hooks); custom tools can carry `permission_policy` `always_ask`/`always_deny` — [permissions](https://code.claude.com/docs/en/agent-sdk/permissions).
- **R5 ◐.**
  - Subagents exist, and the `SubagentStart`/`SubagentStop` hooks carry `agent_id` and `agent_transcript_path` — [hooks](https://code.claude.com/docs/en/agent-sdk/hooks). The prior note found depth, concurrency and spend caps — [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking).
  - There is no resource lease for a shared external DB.
  - Practitioner reports of a concurrency hook failing:
    - Resuming a finished subagent "emits no new start event to hooks", so "a PreToolUse concurrency hook counted six while seven ran" — [#97782](https://github.com/anthropics/claude-code/issues/97782)
    - Subagent-frontmatter `PreToolUse` hooks "never fire" — [#95650](https://github.com/anthropics/claude-code/issues/95650); [#102719](https://github.com/anthropics/claude-code/issues/102719)
    - An agent "auto-spawns multiple subagent forks consuming excessive quota" — [#79735](https://github.com/anthropics/claude-code/issues/79735)
- **R6 ◐.**
  - Hooks fire on tool use, compaction, model switch, subagent lifecycle, `ConfigChange`, `InstructionsLoaded` and `FileChanged`. They can deny or rewrite input, or replace tool output (`updatedToolOutput`). "A hook deny applies even in `bypassPermissions` mode" — [hooks](https://code.claude.com/docs/en/agent-sdk/hooks); [permissions](https://code.claude.com/docs/en/agent-sdk/permissions).
  - Hooks only see the harness's *tool calls*. The Write/Edit matcher example warns: "If Claude writes `.env` with a Bash command, the hook doesn't run" — [hooks](https://code.claude.com/docs/en/agent-sdk/hooks).
  - Shell hooks load from settings files (`.claude/settings.json`) when `settingSources` includes them — [hooks](https://code.claude.com/docs/en/agent-sdk/hooks). Inference: the agent has a shell, so settings files inside its writable filesystem are agent-tamperable unless the harness pins `setting_sources` and keeps the monitor in-process or out-of-sandbox.
  - Caller identity in hook payloads was missing in v2.1.222 ([#84926](https://github.com/anthropics/claude-code/issues/84926)). Current docs say `agent_id` is populated inside subagents ([hooks](https://code.claude.com/docs/en/agent-sdk/hooks)), so the conflict is likely version-dependent.
  - Someone has filed a request for "signed run receipts" so hooks can verify that a subagent run happened — [#104409](https://github.com/anthropics/claude-code/issues/104409).
  - A hung `PostToolUse` hook silently blocks a turn for up to 600 s — [#104363](https://github.com/anthropics/claude-code/issues/104363).
- **R7 ◐/○.** Transcripts are chat-message JSONL, readable via `get_session_messages()` — [sessions](https://code.claude.com/docs/en/agent-sdk/sessions). Nothing in the docs mentions token IDs or logprobs. Per-step `output_tokens` is a placeholder (prior note, [cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)).
- **R8 ◐.** Gateways must expose a supported Anthropic API format. "Anthropic ... doesn't support routing Claude Code to non-Claude models through any gateway" — [LLM gateway](https://code.claude.com/docs/en/llm-gateway).
  - vLLM documents a Claude Code integration: it implements the Anthropic Messages API, and Claude Code is pointed at it via the base URL — [vLLM Claude Code](https://docs.vllm.ai/en/stable/serving/integrations/claude_code/).
  - A practitioner reports that Claude Code ≥ 2.1.154 broke against vLLM by sending extra roles, and the workaround was to pin the version — [NVIDIA forum](https://forums.developer.nvidia.com/t/claude-code-2-1-154-breaks-with-vllm-anthropic-compatible-endpoint-on-dgx-spark/371797).
  - Licence: the repo sidebar says MIT, but "Use of this SDK is governed by Anthropic's Commercial Terms of Service". The SDK bundles the Claude Code CLI binary — [claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python).
- **R9 ◐.** System prompt, tool set (`allowed_tools`/`disallowed_tools`, including removing Bash entirely), hooks that inject context, `PreCompact`/`PostCompact`, and subagent definitions are all configurable — [permissions](https://code.claude.com/docs/en/agent-sdk/permissions); [hooks](https://code.claude.com/docs/en/agent-sdk/hooks). The core loop, compaction algorithm and built-in tool schemas live in a closed, frequently updated binary (inference from the bundled-CLI fact above).
- **R10 ●.** `dontAsk` turns every prompt into a deny ("a fixed, explicit tool surface for a headless agent"). `bypassPermissions` approves everything except critical-path `rm` and similar actions, and hooks still run. In `-p`/SDK, since v2.1.302 the default mode denies unapproved calls — [permissions](https://code.claude.com/docs/en/agent-sdk/permissions). Caveats:
  - Claude Code "refuses to start in this mode as root or under `sudo` outside a recognized sandbox" — [permissions](https://code.claude.com/docs/en/agent-sdk/permissions).
  - Before v2.1.210, a hook timeout was reported as a user rejection, "which made unattended sessions stop and wait for input" — [hooks](https://code.claude.com/docs/en/agent-sdk/hooks).

### Inferences
- **Broken assumption: the workspace is a filesystem.** Checkpointing, `acceptEdits`, critical-path `rm` checks and path-scoped `Edit(...)` rules all reason about files. For `psql -c "DROP INDEX ..."` the harness sees only an opaque Bash string. R6 must sit at the DB (audit log, role) rather than in hooks.
- **Broken assumption: cost is an estimate on one currency.** The cap overshoots by up to one call, double-counts retries and misses model-switch calls. For a "$X authoritative" budget, the harness must meter at a proxy or gateway it owns (the gateway doc itself lists "Cost controls: enforce budgets ... in one place" — [LLM gateway](https://code.claude.com/docs/en/llm-gateway)) and reconcile against provider billing.
- **Failure scenario: crash after `CREATE INDEX CONCURRENTLY`.**
  1. The `PostToolUse` record and the `tool_result` may never be written ([#94252](https://github.com/anthropics/claude-code/issues/94252) shows dropped `tool_result`s even without a crash).
  2. On `resume`, the model sees a dangling or absent call and re-issues the DDL. It gets "relation already exists", or, if the first build was killed mid-way, finds an INVALID index it may not know to drop.
  3. The budget for the resumed run restarts at $0 ([cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)), so the episode overspends.
- **Failure scenario: restart mid-diagnosis.** An `ALTER SYSTEM` followed by `pg_ctl restart` drops the psql session. Hooks fire per Bash call, so they cannot tell the agent that the server is warming up. Subsequent "measurements" in the same turn are cold-cache artefacts unless the external monitor marks them.
- **Fit.** This is the best *frontier-model baseline arm* and the easiest to run unattended. It is a poor *trained-model* substrate because it is closed and changes weekly, has no token IDs, and needs an Anthropic-format server.

### Gaps
- Not verified: a native wall-clock limit (beyond `max_turns`) and any API that tells the model its remaining budget. Cloud "routines" or scheduled agents as a cron substitute (they exist in the Claude product, but I did not fetch docs this session).

---

## Q2. OpenAI Codex CLI (`codex exec`) and OpenAI Agents SDK

### Takeaway
- **Codex CLI.** It has the best headless *event stream* (`--json` with typed `item.*` events and per-turn usage) and an OS sandbox (`read-only` / `workspace-write` / `danger-full-access`). It also has a persisted, budgeted long-horizon "Goal" object. That budget is a soft token budget, not dollars, and its pre-request reservation across subagents is still a feature request. Licence: Apache-2.0.
- **Agents SDK.** It is a library (MIT, provider-agnostic via LiteLLM/any-llm) with sandbox agents. Durability and budgets are left to the integrator.

### Cited Findings
**Codex CLI**
- **R1 ◐.** `codex exec resume --last` or `resume <SESSION_ID>`. `--ephemeral` disables persisted rollout files — [Codex non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode).
  - Goal mode (`/goal`) keeps a per-thread objective with statuses including `budget_limited`, and an optional `token_budget` — [#34215](https://github.com/openai/codex/issues/34215). A secondary source says goals survive "terminal crashes, and even machine reboots" — [Vaughan blog](https://codex.danielvaughan.com/2026/05/07/codex-cli-goal-command-persisted-long-horizon-workflows-pause-resume-budget/) (third-party; sources disagree on the version and default enablement).
  - Bugs: `codex exec resume` overrides the persisted cwd when `-C` is omitted ([#40702](https://github.com/openai/codex/issues/40702)); resume re-appends the full skills listing ([#55488](https://github.com/openai/codex/issues/55488)); Code Mode store values don't persist across resume ([#49905](https://github.com/openai/codex/issues/49905)).
- **R2 ◐.** `turn.completed` carries `input_tokens`, `cached_input_tokens`, `output_tokens` and `reasoning_output_tokens` — [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode). The Goal token budget soft-stops and cannot easily be raised and resumed ([#34215](https://github.com/openai/codex/issues/34215)). An open issue asks to "Extend the existing shared rollout budget so it reserves capacity **before each model request** ... across the root and its descendants" — [#55180](https://github.com/openai/codex/issues/55180). That implies today's shared budget is checked after the fact (inference from the issue text). There is also an open request for "progress-aware budgets ... compaction-safe continua[tion]" — [#55990](https://github.com/openai/codex/issues/55990). No dollar figures or wall-clock budget appear on the non-interactive page.
- **R3 ◐.** `codex exec` is scriptable. `--output-schema` gives structured final output, and `-o` writes the last message — [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode). Memory across runs is session files plus `history.jsonl` under `CODEX_HOME` — [advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced).
- **R4 ●.** MCP tool calls are a first-class item type in the event stream — [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode).
- **R5 ◐.** Subagents exist (the shared-budget issue references "root and subagents" — [#55180](https://github.com/openai/codex/issues/55180)). I found no documented concurrency or resource-lease control.
- **R6 ◐.** Hooks come from `hooks.json` or `[hooks]` in `config.toml` at user and repo level. "Project-local hooks load only when the project is trusted" — [advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced). OTel export (`[otel]`, `otlp-http`/`otlp-grpc`) is off by default. The sandbox separates the agent from host files, and `--ignore-user-config` / `--ignore-rules` exist — [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode); [advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced).
- **R7 ◐.** Typed JSONL events with usage, but no token IDs (inference: none are documented on the pages fetched).
- **R8 ◐.**
  - Custom `[model_providers.<id>]` takes `base_url`, `env_key` and `wire_api` (`responses` is shown).
  - `--oss` covers Ollama and LM Studio. With `--oss` and no provider configured, `codex exec` exits with an error.
  - "Chat Completions providers will ignore" some settings, so Chat Completions remains partially supported — [advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced).
  - Licence Apache-2.0 — [openai/codex](https://github.com/openai/codex).
- **R9 ◐.** Open source, so prompts and tools are forkable. The loop is tuned for OpenAI models and the Responses API (inference).
- **R10 ●.** The default `exec` sandbox is read-only. `--sandbox workspace-write` and `danger-full-access` exist. `--full-auto` "is no longer supported", and `--approve-for-me` routes approvals through automatic review — [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode).

**OpenAI Agents SDK**
- **R1, R3, R6, R8 notes.** MIT licence. "Provider-agnostic, supporting the OpenAI Responses and Chat Completions APIs, as well as 100+ other LLMs" through LiteLLM and any-llm. `SandboxAgent` is "preconfigured to work with a container to perform work over long time horizons" and can "preserve workspace state across longer tasks". Its example workspace manifest is a `GitRepo` — [openai-agents-python](https://github.com/openai/openai-agents-python). Sessions (Redis optional) and built-in tracing are available — [same](https://github.com/openai/openai-agents-python).
- **R7.** Agent Lightning lists the OpenAI Agents SDK as a trainable framework — [Agent Lightning docs](https://microsoft.github.io/agent-lightning/stable/).

### Inferences
- **Broken assumption: the sandbox protects a local workspace.** For this design the dangerous surface is a *network* credential to a DB. `workspace-write` blocks file writes outside the repo, but the agent still needs network access to reach the DB, and once it has network access, the sandbox offers no DB-semantic protection. The sandbox is still useful as the *agent-vs-monitor* separation: the monitor and its credentials live outside it.
- **Goal mode is the closest native "anytime" construct.** It has a persisted objective, a budget, a soft stop and a resume. It counts tokens, not dollars, and the cap is not reserved before each request (per #55180). The model is steered to wrap up, which is a weak form of R2's "graceful stop".
- **Failure scenario: `--ephemeral` or a crash between `item.started` and `item.completed`.** If the process is killed after `command_execution` starts a `VACUUM FULL`, the JSONL stream has a started item with no completion. `exec resume` restores the thread but not the knowledge of whether the rewrite finished. The table lock may still be held by an orphaned backend.
- **Agents SDK as a base.** It is a better *library* than Codex for a custom DB-ACI because the tools are Python functions and LiteLLM gives open-weight support. It has no built-in budget, and durability needs Temporal (prior note).

### Gaps
- No official OpenAI doc for Goal mode or `rollout_budget` was fetched. Its semantics come from a GitHub issue and third-party blogs that conflict. Codex hook event list not fetched. Agents SDK `max_turns` and usage APIs not verified.

---

## Q3. OpenHands Software Agent SDK (V1, arXiv 2511.03690)

### Takeaway
This is the strongest open base for R1, R7 and R8. It is MIT, persists every event as an append-only file, has an agent server with remote workspaces, and is used by RL stacks (SkyRL). Its safety model is weak for R6: `ConfirmRisky` relies on *LLM-self-reported* risk. Its pause/resume semantics have sharp edges. Like the others, it does not reconcile in-flight external side effects on resume.

### Cited Findings
- **R1 ◐+.** Conversation persistence uses `persistence_dir` and `conversation_id`. `base_state.json` holds config, status and stats, and `events/event-00000-<id>.json` holds one file per event. Events are append-only and auto-saved, and state "is always recoverable, even if the process crashes unexpectedly" — [OpenHands persistence](https://docs.openhands.dev/sdk/guides/convo-persistence). The page does not say how an in-flight tool call is reconciled after a crash.
  - Bugs: resume re-emits a duplicate `SystemPromptEvent` mid-history ([#5710](https://github.com/OpenHands/software-agent-sdk/issues/5710)). A resumed conversation keeps a disabled plugin's skills ([#5628](https://github.com/OpenHands/software-agent-sdk/issues/5628)). Cloud-workspace resume leaves the client on a stale connection ([#4664](https://github.com/OpenHands/software-agent-sdk/issues/4664)).
- **R2 ◐.** It accumulates LLM cost in state (prior note; [ICLR'25](https://arxiv.org/html/2407.16741v3)). `max_iterations` appears in a practitioner report (500) — [#6010](https://github.com/OpenHands/software-agent-sdk/issues/6010). No dollar cap is documented on the pages fetched.
- **R3 ◐.** An agent server runs agents locally or in "ephemeral workspaces (e.g. in Docker or Kubernetes)" — [software-agent-sdk](https://github.com/OpenHands/software-agent-sdk). No scheduler. Memory equals the persisted conversation.
- **R4 ●.** Typed tool system with MCP — [arXiv](https://arxiv.org/html/2511.03690v1).
- **R5 ?.** Not verified this session.
- **R6 ◐.**
  - Confirmation policies are `AlwaysConfirm`, `NeverConfirm` and `ConfirmRisky`. `LLMSecurityAnalyzer` works because "The LLM can annotate actions with security risk levels during generation". The page warns that "the model can be manipulated" and lists, as known limitations, no hard deny at the analyzer boundary and "`execute_tool()` bypassing checks", with hooks as a possible fix — [OpenHands security](https://docs.openhands.dev/sdk/guides/security).
  - Event files on disk give an external monitor a tail-able stream (inference from the persistence layout).
- **R7 ●/◐.** Event-sourced and replayable ([arXiv](https://arxiv.org/html/2511.03690v1)). The original SkyRL pipeline was "built on top of VeRL and OpenHands" — [Berkeley Sky](https://sky.cs.berkeley.edu/project/skyrl/). SkyRL-Agent works with SkyRL-train, VeRL and Tinker — [arXiv 2511.16108](https://arxiv.org/abs/2511.16108v1). Token-level capture still depends on the inference server; see Q6.
- **R8 ●.** MIT — [software-agent-sdk](https://github.com/OpenHands/software-agent-sdk). It is multi-LLM (prior note). One report shows it running on `openai/ark-code-latest` ([#6010](https://github.com/OpenHands/software-agent-sdk/issues/6010)).
- **R9 ●.** Immutable agent config plus a typed tool system, all in open Python ([arXiv](https://arxiv.org/html/2511.03690v1)).
- **R10 ◐.** `NeverConfirm` is unattended. But "a plain user message silently resumes a paused conversation — 'stop' can be undone by talking to the agent" — [#6010](https://github.com/OpenHands/software-agent-sdk/issues/6010). That is relevant if a monitor injects messages.

### Inferences
- **Broken assumption: the LLM labels its own risk.** For a reward-hacking study, a risk analyzer that the agent itself annotates is, by construction, tamperable. Use `NeverConfirm` plus an external, effect-level monitor, and treat the analyzer as just another logged field.
- **Broken assumption: workspace-centric runtime.** Docker or K8s workspaces assume the environment can be torn down cheaply. Here the environment is an external prod DB or clone that the workspace merely connects to.
- **Failure scenario.** The event log records an `ActionEvent` for `CREATE INDEX CONCURRENTLY`, then the process dies before the `ObservationEvent`. After restore, the log ends in an action with no observation. Whether the agent re-runs it is undefined per the docs. The deterministic replay replays the *log*, not the DB, so replay-based debugging diverges from reality whenever DB state has moved on (e.g., autovacuum, stats).

### Gaps
- Not verified: subagent and parallel-agent support, native budget caps, hooks API state (the security page names hooks only as a future fix), the agent-server's crash and idempotency semantics.

---

## Q4. SWE-agent and mini-swe-agent

### Takeaway
mini-swe-agent is the cleanest *RL rollout* harness. It is MIT, has about 100 lines of agent loop, keeps a linear history, runs on any model via LiteLLM, and its authors pitch it for "FT or RL and don't want to overfit to a specific agent scaffold". It has nothing for R1, R2's dollar side, R3, R5 or R6, and each action is a fresh subprocess, which breaks a persistent psql session.

### Cited Findings
- "Just some 100 lines of python for the agent class". It "Supports all models via litellm, openrouter, portkey" and has "a completely linear history". Environments include local, docker/podman, singularity, bubblewrap and contree. The authors say "consider mini-swe-agent your default choice", recommending SWE-agent only for experimenting with tool sets or history processors. Licence MIT — [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent).
- Each action is an independent `subprocess.run` (prior note: [notes](https://shekhargulati.com/2025/09/01/notes-on-mini-swe-agent)). It is used in PSRL and AReaL SWE examples (prior note).
- Scores: R1 ○, R2 ◐ (cost/step limits are not documented on the README fetched; see Gaps), R3 ○, R4 ○ (bash only by design), R5 ○, R6 ○ (a linear message log only), R7 ●, R8 ●, R9 ● (trivially forkable), R10 ● (no permission system at all).

### Inferences
- A stateless subprocess per step means each `psql -c` is a fresh connection. Session-level `SET`s, advisory locks, `BEGIN` and temp tables don't persist across steps, and prepared-statement and plan-cache experiments are impossible. This is a correctness-relevant change in the action space, not just a matter of convenience.
- It is ideal as the *RL-training loop* of a two-harness design: a thin loop where every non-bash affordance (budget, observation tools, monitor) is injected by the environment wrapper.

### Gaps
- `cost_limit`/`step_limit` config and trajectory file format not verified this session. SWE-agent (full) 2026 maintenance status not checked.

---

## Q5. Gemini CLI / Antigravity CLI, OpenCode, Goose

### Takeaway
- **Gemini CLI** is being superseded for consumers by Antigravity CLI (June 18, 2026). Antigravity's openness is unconfirmed, which is a licence and longevity risk.
- **OpenCode** (MIT) has a client/server mode and a headless `--auto` permission mode, and supports many providers.
- **Goose** (Apache-2.0, Linux Foundation AAIF) is the only one with a *built-in cron scheduler* for recipes, which covers R3 natively.

None addresses R2 (authoritative dollars), R5 contention or R6 effect-level monitoring.

### Cited Findings
**Gemini CLI → Antigravity CLI**
- Google announced (May 19, 2026) that "On June 18, 2026, Gemini CLI and Gemini Code Assist IDE extensions will stop serving requests for Google AI Pro and Ultra". Enterprise "access remains unchanged", and Gemini CLI "will remain accessible via paid Gemini and Gemini Enterprise Agent Platform API keys" — [Google Developers Blog](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/). The post does not say whether Antigravity CLI is open source. Secondary reports call it a closed binary written in Go — [search summary of buildfastwithai/ostechnix](https://ostechnix.com/google-is-replacing-gemini-cli-with-google-antigravity/) (secondary).
- Headless: `-p`, `--output-format` JSON (`response`, `stats`, `error`) or stream-JSON events (`init`, `message`, `tool_use`, `tool_result`, `error`, `result` with per-model token usage). Exit code 53 means turn limit exceeded. Cost figures are not reported — [Gemini CLI headless](https://geminicli.com/docs/cli/headless/).
- Scores: R1 ? · R2 ◐ (tokens and turn limit only) · R3 ◐ · R4 ● (MCP, not re-verified) · R5 ? · R6 ◐ (the event stream) · R7 ◐ · R8 ◐ (Gemini-centric) · R9 ◐ · R10 ? (`--yolo` not on the fetched page).

**OpenCode**
- `opencode run` has `--continue`/`--session`/`--fork`, `--format json` ("raw JSON events", schema undocumented) and `--auto` ("Auto-approve permissions that are not explicitly denied"). `OPENCODE_PERMISSION` takes inline JSON. `opencode serve` is a headless HTTP server with basic auth. `opencode stats` gives "token usage and cost statistics", and `opencode export` gives session JSON — [OpenCode CLI](https://opencode.ai/docs/cli/). Providers come from Models.dev — [same](https://opencode.ai/docs/cli/).
- Licence MIT. The repo is now at `anomalyco/opencode` — [GitHub](https://github.com/sst/opencode).
- Scores: R1 ◐ · R2 ◐ (cost stats after the fact) · R3 ◐ (server plus cron) · R4 ● (inference; not verified this session) · R5 ? · R6 ◐ (the server is a separate process with an HTTP API) · R7 ◐ · R8 ● · R9 ● · R10 ●.

**Goose (Block)**
- Apache-2.0. "goose is part of the Agentic AI Foundation (AAIF) at the Linux Foundation". It supports 15+ providers, including Ollama and OpenRouter, and "70+ extensions via the Model Context Protocol" — [block/goose](https://github.com/block/goose).
- `goose schedule add --schedule-id --cron --recipe-source` and `goose schedule list` — [goose-schedule man page](https://www.mankier.com/1/goose-schedule); [Mintlify CLI ref](https://www.mintlify.com/block/goose/api/cli/schedule) (mirror, not official docs). An in-process `tokio_cron_scheduler` stores jobs in local JSON — [instagit guide](https://instagit.com/block/goose/goose-scheduled-recipe-execution-cron/) (secondary).
- Scores: R1 ? · R2 ? · R3 ● (scheduler plus recipes) · R4 ● · R5 ? · R6 ? · R7 ◐ · R8 ● · R9 ● (recipes) · R10 ?.

### Inferences
- Goose's scheduler is a convenience, not a property of the harness. An external cron or systemd timer calling any headless CLI gives the same result. What matters for R3 is a *typed, harness-owned* memory across episodes, and none of these provides one.
- Antigravity's closed-binary status (if confirmed) makes it unsuitable as a research artefact, and Gemini CLI's consumer sunset makes it a fragile baseline.

### Gaps
- Goose: official docs on headless `goose run`, retries, subrecipes and permission modes were not fetched (one 404). Gemini CLI repo licence (believed Apache-2.0) not re-verified. OpenCode plugin and hook API not verified.

---

## Q6. Cross-cutting: RL compatibility (R7) and open-weight swap (R8)

### Takeaway
Token-exact traces come from the *inference server*, not the harness. Any harness that talks to an OpenAI-compatible endpoint can be trained if the endpoint is a vLLM proxy that returns token IDs (Agent Lightning's approach). Harnesses that speak only the Anthropic Messages format (Claude Code) need vLLM's Anthropic endpoint, and token-ID return there is unverified.

### Cited Findings
- vLLM ≥ 0.10.2 adds `return_token_ids` to its OpenAI-compatible API (`prompt_token_ids` after the chat template, and completion `token_ids`) to fix "retokenization drift" in agent RL. Agent Lightning routes requests through LiteLLM Proxy to collect traces — [vLLM blog](https://vllm.ai/blog/2025-10-22-agent-lightning); [LiteLLM: Agent Lightning](https://docs.litellm.ai/docs/projects/Agent%20Lightning).
- Agent Lightning: "complete decoupling between agent execution and training", and it works with LangChain, the OpenAI Agents SDK, AutoGen, CrewAI or plain Python — [Agent Lightning](https://microsoft.github.io/agent-lightning/stable/); [arXiv 2508.03680](https://huggingface.co/papers/2508.03680).
- ART (OpenPipe): GRPO over vLLM, HF or Unsloth models, with a client/server design, a LangGraph drop-in integration and the RULER LLM-judge reward — [ART LangGraph integration](https://art.openpipe.ai/integrations/langgraph-integration); [OpenPipe/ART](https://github.com/OpenPipe/ART).
- SkyRL-Agent supports SkyRL-train, VeRL and Tinker. SA-SWE-32B (pure RL from Qwen3-32B) reaches 39.4% Pass@1 on SWE-Bench Verified with a simplified ReAct loop — [arXiv 2511.16108](https://arxiv.org/html/2511.16108v1).
- Claude Code can target vLLM's Anthropic Messages endpoint — [vLLM docs](https://docs.vllm.ai/en/stable/serving/integrations/claude_code/). NeMo Gym exposes `/v1/messages` model servers for Claude Code — [NeMo Gym](https://docs.nvidia.com/nemo/gym/model-server/anthropic-messages).

### Inferences
- **Why harness-side traces are not enough.** Claude Code, Codex and OpenCode rewrite context: they compact, inject skills or system reminders, and re-append skill listings on resume ([Codex #55488](https://github.com/openai/codex/issues/55488)). The training sample is what the server actually tokenized. So the R7 design is: run the harness against a research-owned proxy that logs the exact prompt and completion token IDs per call, keyed by a harness-supplied episode and step ID.
- **RL and ART's RULER.** An LLM-judge reward conflicts with this design, whose reward comes from the effect-level monitor. Use ART or Agent Lightning for the *trainer plumbing* only.
- **Ranking for R8 and R9 together.** mini-swe-agent ≈ OpenHands > OpenAI Agents SDK > OpenCode/Goose > Codex > Claude Code (proprietary binary, Anthropic format, vendor says unsupported for non-Claude models).

### Gaps
- Whether vLLM's Anthropic-format endpoint can return token IDs is unverified. verl's agent-loop interface is not re-verified this session.

---

## Q7. Synthesis: fundamental mismatches, failure scenarios, score matrix and ranked shortlist

### Takeaway
No coding-agent harness can meet R2 (authoritative dollars, remaining budget exposed, deadline-aware stop), R5 (contention control on one shared DB) or R1-with-non-idempotent-effects. All three are properties of the *environment* (the DB plus the billing meter), which these harnesses do not model. Choose a harness for R4, R7, R8, R9 and R10, and build a thin, research-owned control plane for R1, R2, R5 and R6. Recommendation: **OpenHands SDK** (or a **mini-swe-agent-style loop**) as the trained-model harness, and **Claude Agent SDK** plus **Codex exec** as frontier baseline arms.

### Cited Findings: score matrix (cells summarize Q1–Q6; see citations there)
| | R1 resume w/ side-effects | R2 wall+$ anytime | R3 headless+memory | R4 MCP/tools | R5 parallel+contention | R6 external monitor | R7 token traces/RL | R8 open-weight/licence | R9 configurable | R10 unattended |
|---|---|---|---|---|---|---|---|---|---|---|
| Claude Agent SDK/Code | ◐ convo-only, open resume bugs | ◐ est., post-call check, overshoot | ◐ | ● | ◐ subagent caps; hook gaps | ◐ rich hooks, Bash-opaque | ◐ JSONL, no token IDs | ◐ Anthropic-format only; Commercial Terms | ◐ closed core | ● dontAsk/bypass |
| Codex CLI | ◐ exec resume, Goal persisted | ◐ token Goal budget, soft | ◐ | ● | ◐ (no lease) | ◐ hooks+OTel+OS sandbox | ◐ typed JSONL | ◐ custom providers/--oss; Apache-2.0 | ◐ | ● |
| OpenAI Agents SDK | ◐ sessions; Temporal | ○ | ◐ | ● | ◐ handoffs | ◐ tracing | ◐ Agent Lightning | ● MIT, LiteLLM | ● | ● (library) |
| OpenHands SDK | ◐+ event files, in-flight undefined | ◐ cost accrued | ◐ agent server | ● | ? | ◐ LLM self-risk | ● SkyRL lineage | ● MIT | ● | ◐ pause quirk |
| mini-swe-agent | ○ | ◐? | ○ | ○ | ○ | ○ | ● | ● MIT | ● | ● |
| Gemini/Antigravity CLI | ? | ◐ tokens, turn limit | ◐ | ● | ? | ◐ stream-json | ◐ | ◐ consumer sunset; Antigravity openness unconfirmed | ◐ | ? |
| OpenCode | ◐ | ◐ cost stats | ◐ serve | ●(inf.) | ? | ◐ | ◐ | ● MIT | ● | ● --auto |
| Goose | ? | ? | ● scheduler | ● | ? | ? | ◐ | ● Apache-2.0, AAIF | ● | ? |

### Inferences
**Fundamental assumptions that break for this problem**
1. **The environment is a local filesystem or repo.** Checkpointing, sandbox write scopes, path permission rules and `git reset`-style recovery all assume this. Here the state that matters is remote DB state reached through a credential. Every harness sees DDL as an opaque shell string.
2. **Tasks are short and cheaply resettable.** Resume restores *conversation*, not *world*. No harness journals external effects (intent → issued → confirmed) or reconciles them on restart.
3. **Cost is an estimated token count.** Claude overshoots by up to one call ([#100111](https://github.com/anthropics/claude-code/issues/100111)) and double-counts retries ([#101951](https://github.com/anthropics/claude-code/issues/101951)). Codex budgets are token-based and soft ([#34215](https://github.com/openai/codex/issues/34215), [#55180](https://github.com/openai/codex/issues/55180)). None covers DB-side dollars (warehouse credits, clone compute).
4. **UX is approval-centric.** Safety equals prompts, and "unattended" is a mode that *removes* safety. This design inverts that: no guardrails, and full observation by an *external* monitor.
5. **Parallelism means independent workers.** Subagent caps limit *count* and *spend*, not access to a shared, measurement-sensitive resource. Subagent lifecycle events can be missed by hooks ([#97782](https://github.com/anthropics/claude-code/issues/97782)).
6. **Safety is classified at the harness.** Claude auto mode and OpenHands' `LLMSecurityAnalyzer` sit inside the agent's trust domain. For reward-hacking research the monitor must be outside it: at the DB (pgaudit or the engine audit log, a role without `ALTER SYSTEM` if desired, config-diff snapshots) and at the LLM proxy.

**Concrete failure scenarios (apply to all harnesses unless noted)**
- *Crash after `CREATE INDEX CONCURRENTLY` starts.* The Postgres build continues server-side only while the backend lives. If the client dies, the backend is cancelled and leaves an INVALID index. On resume the agent sees either a missing observation or a stale one, retries, hits "already exists", or builds a duplicate under another name. The budget counter restarts (Claude) or soft-stops (Codex). A harness-owned effect journal plus a monitor-side `pg_index.indisvalid` check is required.
- *Restart (`ALTER SYSTEM` + restart).* The psql connection drops. A stateless-subprocess harness (mini-swe-agent) reconnects cleanly, but a persistent-shell harness may hang on a dead socket until the tool timeout. Measurements in the following minutes are cold-cache, and only an independent measurement in the monitor can label them.
- *Parallel diagnosis subagents.* Five subagents each run `EXPLAIN ANALYZE` on heavy queries at once. They perturb the workload they are diagnosing, and the monitor's workload-integrity check flags the result as damage. No harness offers a lease or mutex on the DB, so contention control must be an observation tool (a broker) the subagents call instead of raw psql, or a DB-side semaphore (e.g., a limited role connection count) (inference).
- *Deadline.* At T−2 min a long `VACUUM FULL` or `pg_repack` is in progress. No harness exposes "remaining wall-clock" to the model, and Claude's `max_turns` or budget-stop ends the session *after* the call returns, possibly mid-rewrite. The harness needs a deadline-aware scheduler that refuses to start actions whose expected duration exceeds the remaining budget (requires an action-duration model, which is new research).
- *Cron episodes with memory.* Episode N+1 resumes episode N's transcript. Inherited context includes N's "I already created idx_foo", but a DBA or autovacuum may have changed the world since. Memory must be re-grounded against fresh observation, not trusted.
- *Agent tampering with the monitor.* In Claude Code, shell hooks live in `.claude/settings.json` inside the agent-writable cwd. A shell-capable agent could edit them, and a `ConfigChange` hook can observe but not prevent this if the file sits outside harness control (inference). Mitigation: in-process SDK callback hooks only, `setting_sources=[]`, a read-only config mount, and a monitor that does not rely on hooks.

**Ranked shortlist for this design**
1. **OpenHands Software Agent SDK** as the primary research harness. MIT; open, typed tools plus MCP; event-file persistence that an external monitor can tail; agent server separation; SkyRL lineage for RL; multi-LLM. Must add: an effect journal and resume reconciliation, an authoritative budget via the proxy, a remaining-budget observation injected per step, a DB contention broker, and replacing `LLMSecurityAnalyzer` with `NeverConfirm` plus an external monitor.
2. **mini-swe-agent-style minimal loop** (or a fork) as the *RL-training* harness and the harness-overfitting control. It is MIT, any model, linear history, and is designed to avoid scaffold overfitting. Must add: persistent DB sessions (or explicitly treat stateless psql as part of the action space), budget injection, observation tools, and the monitor. It is cheap to produce many harness variants (R9).
3. **Claude Agent SDK** as the frontier-model baseline arm. It has the best hook surface for *logging*, mature unattended modes, and subagents for breadth-first diagnosis. Weaknesses: estimated dollars, open resume and hook bugs, Commercial Terms, the Anthropic-format requirement, and the vendor not supporting non-Claude models. That rules it out as the trained-model substrate but keeps it as the strongest "what does a frontier harness do" comparator.
4. **Codex CLI (`exec`)** as the second frontier baseline. Apache-2.0, the best typed JSONL event stream, OS sandbox separation for agent vs. monitor, and a native Goal + token budget, the closest to anytime operation. Custom providers allow open-weight models, but the loop is tuned to the Responses API.
5. **OpenAI Agents SDK** if a library is preferred over an agent product. MIT, LiteLLM, Agent Lightning compatibility. Durability via Temporal.
6. **OpenCode / Goose** as optional robustness arms (open licence, many providers; Goose has a native scheduler). They add little beyond 1–4 for this design.
7. **Gemini CLI / Antigravity**: not recommended. Consumer sunset, and the successor's openness is unconfirmed.

Bottom line (inference): the harness research artefact is the **control plane between the loop and the DB**: effect journal, budget ledger, deadline scheduler, contention broker, tamper-proof monitor, and token-exact proxy. It is not the loop. Pick loops that are cheap to swap (1, 2) and use 3 and 4 as baselines.

### Gaps
- Not verified for any candidate: a native wall-clock budget, or a remaining-budget signal to the model. I found no evidence that any of them exposes one, but absence was not exhaustively checked.
- No practitioner report found of any of these harnesses being used against a live production database. The failure scenarios above are inferences from documented mechanics and DB semantics.
- Other 2026 harnesses not covered within budget: Cursor CLI, Amp, Aider, Cline/Roo CLI, Kimi/Qwen Code CLIs, and LangChain deep agents.
