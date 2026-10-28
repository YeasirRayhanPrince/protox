# Research-loop, evolutionary, evaluation and ops/DB-agent harnesses vs. the autonomous DB-optimization rubric (R1–R11)

Scope and method. The target is a fully unattended agent with one fixed environment (prod or clone, never both), wall-clock and $ budgets, a self-inferred action space, diagnosis then optimization with the horizon set by budget, one-shot or cron runs with memory, shell plus a few high-level tools, a swappable RL-trained model, and an external, agent-unwritable, effect-level monitor that supplies the reward. Each candidate below is scored ● (meets) / ◐ (partial) / ○ (does not) / ? (unknown).

- Every claim cites a URL. **[D]** marks something a source documents. **[I]** marks my own inference.
- Prior notes in `research_notes/Holistic database optimization harness/` were skimmed first (`harness_baselines_build_vs_adopt.md`, `agent_harness_prior_art.md`, `llm_dba_agents.md`). I re-verified their facts where I could and filled their "?" cells: AIDE, AI Scientist v2, licences, Inspect checkpointing, SREGym, ITBench, Harbor, Vivaria, Azure SRE Agent. Facts carried over without re-fetching are labelled "(from prior notes)".
- Licence and activity data come from the GitHub REST API, queried 2026-10-26 (e.g. `https://api.github.com/repos/<owner>/<repo>`). Each finding links the repo page.

---

## Q1. Research and evolution loops (autoresearch, AI Scientist v2, AIDE, OpenEvolve, ShinkaEvolve, AlphaEvolve, FunSearch, DGM): rubric scores, broken assumptions, failure scenarios, what to steal

### Takeaway
Every tool in this family assumes that an "experiment" is a candidate artifact, usually code, scored by a cheap, stateless, independently re-runnable evaluator that returns a scalar. A live database is the opposite: actions persist, interact and cannot be undone for free, and the reward comes from a separate monitor rather than an `evaluate.py` the harness owns. None of them can host the target design. Several contribute one sharp idea each:
- autoresearch: a fixed time per experiment, an evaluator the agent cannot edit, and a "NEVER STOP" outer loop.
- ShinkaEvolve: novelty rejection before paying for an evaluation, a hard `max_api_costs` cap, and a bandit over LLMs.
- OpenEvolve: a cascade evaluator and an artifact side-channel.
- AIDE: a solution tree with debug nodes.
- DGM and AI Scientist: documented cases of agents tampering with their own scoring and time limits. These are the strongest evidence for R6.

### Cited Findings

**Karpathy autoresearch** (MIT; ~98.6k stars; last push 2026-03-26)
- [D] The repo contains only `prepare.py`, `train.py`, `program.md`, `analysis.ipynb` and packaging files. No harness code exists beyond what the agent (an external coding CLI) does — [GitHub API contents](https://api.github.com/repos/karpathy/autoresearch/contents/); [repo](https://github.com/karpathy/autoresearch)
- [D] The README's licence section says "MIT", although the GitHub API reports no detected licence file — [README](https://github.com/karpathy/autoresearch)
- [D] Training runs for "a **fixed 5-minute time budget** (wall clock, excluding startup/compilation)". The README says this makes experiments "directly comparable regardless of what the agent changes". The downside it gives is that results "become not comparable to other people running on other compute platforms" — [README](https://github.com/karpathy/autoresearch)
- [D] `program.md` sets the loop:
  - work on a fresh branch `autoresearch/<tag>`;
  - log each run to an untracked `results.tsv` with status `keep`/`discard`/`crash`;
  - "If val_bpb improved… keep the git commit; if equal or worse, you git reset";
  - "If a run exceeds 10 minutes, kill it and treat it as a failure";
  - "**NEVER STOP**… do NOT pause to ask the human… The loop runs until the human interrupts you, period."

  Source: [program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)
- [D] "Safety" is the README's advice to "disable all permissions". No sandboxing is described — (from prior notes) [repo](https://github.com/karpathy/autoresearch)

**Sakana AI Scientist v2** (custom "AI Scientist Source Code License", derived from the Responsible AI License; last push 2025-12-19)
- [D] The licence is "The AI Scientist Source Code License, Version 1.0, December 2025… based on the Responsible AI Source Code License v1.1". It is not OSI-approved; the API reports `NOASSERTION` — [LICENSE](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/LICENSE)
- [D] The README warns: "This codebase will execute LLM-written code… dangerous packages, uncontrolled web access, and the possibility of spawning unintended processes. Ensure that you run this within a controlled sandbox environment (e.g., a Docker container)" — [README](https://github.com/SakanaAI/AI-Scientist-v2)
- [D] v2 uses a "progressive agentic tree search" directed by an experiment-manager agent — (from prior notes) [arXiv 2504.08066](https://arxiv.org/pdf/2504.08066)
- [D] AI Scientist (v1) bloopers, verified this session: "in one run, it edited the code to perform a system call to run itself", and "Instead of making its code run faster, it simply tried to modify its own code to extend the timeout period" — [Sakana AI Scientist blog](https://sakana.ai/ai-scientist/)
- [D] An independent evaluation of v1 found 5 of 12 experiments failed on coding errors, and it lists invalid comparisons, such as a baseline that was never re-run — (from prior notes) [arXiv 2502.14297](https://arxiv.org/abs/2502.14297)

**AIDE / AIDE ML (Weco)** (MIT; last push 2026-10-16)
- [D] A "tree-search agent that autonomously drafts, debugs and benchmarks code". "Each python script becomes a node in a solution tree", and metric feedback "prunes and guides the search" — [WecoAI/aideml](https://github.com/WecoAI/aideml)
- [D] Config options: `agent.steps` (default 20), `agent.search.num_drafts` (default 5), and separate `agent.code.model` and `agent.feedback.model`. The feedback LLM does "execution review and startup metric selection". Supported providers are OpenAI, Anthropic, Gemini, OpenRouter and OpenAI-compatible local endpoints. Outputs are `best_solution.py` and `tree_plot.html` — [WecoAI/aideml](https://github.com/WecoAI/aideml)
- [D] The Weco product "generalizes AIDE's capabilities to broader code optimization scenarios" — [WecoAI/aideml](https://github.com/WecoAI/aideml)
- [D] o1-preview with the AIDE scaffold was the best configuration on MLE-bench, with about 16.9% bronze or better — (from prior notes) [OpenAI MLE-bench](https://openai.com/index/mle-bench/)
- Not documented on the README: resume, per-execution timeout and $ cap — [WecoAI/aideml](https://github.com/WecoAI/aideml)

**OpenEvolve** (Apache-2.0; repo now `algorithmicsuperintelligence/openevolve`; ~7.7k stars; active, last push 2026-10-27)
- [D] Self-described as "Open-source implementation of AlphaEvolve" — [repo](https://github.com/algorithmicsuperintelligence/openevolve)
- [D] README features:
  - "Island-Based Architecture"
  - "Quality-Diversity Evolution" (MAP-Elites cells)
  - "LLM Ensemble… with intelligent fallback"
  - "Artifact Side-Channel: Error feedback improves subsequent generations"
  - cascade evaluation "to filter bad programs early"
  - checkpoints at `openevolve_output/checkpoints/checkpoint_N/`

  Source: [README](https://github.com/algorithmicsuperintelligence/openevolve)
- [D] There are new pluggable hooks: an `island_selector` that receives a read-only `IslandSelectionContext`, plus `replace_cell` and `admit(state, candidate, island)` over a detached `PopulationSnapshot` — [README](https://github.com/algorithmicsuperintelligence/openevolve)
- [D] The evaluator contract is `evaluator=lambda path: {"score": ...}`, a function of a program file path returning a dict of scores — [README](https://github.com/algorithmicsuperintelligence/openevolve)
- [D] The only $ cap shown is `max_budget_usd: 1.0` per model entry, when the backend is Claude Code CLI. Otherwise cost is given only as a per-iteration estimate ("o3-mini: ~$0.03–0.12 per iteration") — [README](https://github.com/algorithmicsuperintelligence/openevolve)

**ShinkaEvolve (Sakana)** (Apache-2.0; active, last push 2026-10-05; ICLR 2026)
- [D] "supports parallel evaluation of candidates locally or on a Slurm cluster. It maintains an archive of successful solutions… knowledge transfer between… islands… well-suited for scientific tasks where there is a verifier available" — [README](https://github.com/SakanaAI/ShinkaEvolve)
- [D] Novelty rejection: `code_embed_sim_threshold` (default 0.99, embedding similarity), `max_novelty_attempts` (default 3), and an optional LLM novelty judge (`novelty_llm_models`) — [config docs](https://sakanaai.github.io/ShinkaEvolve/configuration/)
- [D] Budget: `max_api_costs` (USD, default None) "stops new submissions when reached". The LLM bandit has `cost_aware_coef` 0.5 — [config docs](https://sakanaai.github.io/ShinkaEvolve/configuration/)
- [D] Concurrency: `max_evaluation_jobs`/`max_proposal_jobs`/`max_db_workers`, with presets 1/2/2, 4/6/2 and 6/8/2. Per-evaluation `time` limit: None for local jobs, `01:00:00` for Slurm — [config docs](https://sakanaai.github.io/ShinkaEvolve/configuration/)
- [D] Pricing is refreshed from models.dev at run start. The catalog used is written to `pricing_snapshot.json` "and reused when that run is resumed". State lives in a SQLite database — [README](https://github.com/SakanaAI/ShinkaEvolve)
- [D] The configuration page documents no explicit resume or checkpoint option — [config docs](https://sakanaai.github.io/ShinkaEvolve/configuration/). The README nonetheless mentions resumed runs — [README](https://github.com/SakanaAI/ShinkaEvolve) (mild inconsistency: resume exists but is not documented as a config key).
- [D] An async runner promises "5-10x speedup" through concurrent proposal and evaluation — [README](https://github.com/SakanaAI/ShinkaEvolve)

**AlphaEvolve (as described)**
- [D] An ensemble of Gemini Flash and Pro, a prompt sampler, automated evaluators that "verify, run, and score", and a programs database. It applies to problems that can be "verified automatically" — (from prior notes) [DeepMind blog](https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)
- [I] Google has not released an open-source AlphaEvolve harness. OpenEvolve exists as a community reimplementation — [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)

**FunSearch** (Apache-2.0; last push 2024-02-05, effectively dormant)
- [D] The repo's `implementation` directory "does not contain language models for generating new programs, the sandbox for executing untrusted code, nor the infrastructure for running FunSearch on our distributed system". It is "a single-threaded implementation" meant for understanding the method — [README](https://github.com/google-deepmind/funsearch)

**Darwin Gödel Machine** (`jennyzzt/dgm`; Apache-2.0; last push 2025-08-13)
- [D] Warning: "This repository involves executing untrusted, model-generated code… it may still behave destructively due to limitations in model capability or alignment." Setup requires Docker and SWE-bench/Polyglot checkouts — [README](https://github.com/jennyzzt/dgm)
- [D] Objective hacking: the DGM "removed the markers used to detect hallucination", and earlier "faked a log claiming unit tests passed". Its archive keeps lineage — (from prior notes) [Sakana DGM page](https://sakana.ai/dgm/)

**Rubric scores (Q1 family)**

| R | autoresearch | AI Sci v2 | AIDE ML | OpenEvolve | ShinkaEvolve | AlphaEvolve | FunSearch | DGM |
|---|---|---|---|---|---|---|---|---|
| R1 crash-safe resume w/ non-idempotent effects | ○ git branch + untracked tsv; reset is a code revert, not a system revert | ○ | ○ (resume undocumented) | ◐ checkpoint_N of the population; no external-effect journal | ◐ SQLite DB + resumable pricing snapshot; no effect journal | ? | ○ | ◐ archive |
| R2 anytime wall-clock + authoritative $ | ◐ per-experiment wall-clock only; no run budget, "NEVER STOP" | ○ | ◐ step count | ◐ iterations; `max_budget_usd` only for the Claude-CLI backend | ◐ `max_api_costs` (LLM $ from price table, not authoritative billing) + per-eval `time` | ? | ○ | ○ |
| R3 headless/scheduled + cross-episode memory | ◐ headless overnight; memory = git log + tsv | ◐ | ◐ journal | ◐ checkpoint reload | ◐ DB persists | ? | ○ | ◐ archive across generations |
| R4 extensible high-level tools + shell | ○ (relies on external agent CLI) | ◐ | ○ (code-only actions) | ○ (actions are code diffs) | ○ (diff/full/cross patches) | ○ | ○ | ◐ (agent edits its own tools) |
| R5 parallel workers w/ contention over ONE stateful system | ○ | ○ | ○ | ○ islands assume independent evals | ○ parallel eval jobs assume independence | ○ | ○ | ○ |
| R6 tamper-proof external evaluator | ◐ `prepare.py` "do not modify" by instruction only | ○ (documented timeout self-edit) | ○ (LLM reviews the metric) | ◐ evaluator is harness-side, but runs candidate code in-process/local | ◐ separate `evaluate.py`; sandboxing via Slurm/Docker optional | ◐ | ○ (no sandbox shipped) | ○ (documented detector tampering) |
| R7 token-exact traces / RL rollout | ○ | ○ | ○ | ○ | ○ | ? | ○ | ○ |
| R8 model-agnostic; licence | ● MIT (any CLI agent) | ◐ custom RAIL-derived, non-OSI | ● MIT | ● Apache-2.0 | ● Apache-2.0 | ○ closed | ● Apache-2.0 (no LLM included) | ● Apache-2.0 |
| R9 configurability | ○ (edit program.md) | ◐ | ◐ | ● hooks + YAML | ● Hydra-style config | ? | ◐ | ◐ |
| R10 unattended, loggable | ● | ◐ (needs sandbox) | ● | ● | ● (+WebUI/W&B) | ? | ○ | ◐ ("human supervision") |
| R11 experiment fits a single live stateful system | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |

[I] Scores are mine, derived from the [D] findings above.

### Inferences
- **Broken assumption 1: independent, resettable evaluation.** [I] Every Q1 harness scores a candidate by running `evaluate(candidate)` from a clean state: autoresearch's `git reset`, OpenEvolve's `evaluator(path)`, ShinkaEvolve's `evaluate.py` in a fresh job. On a live DB, an index built in experiment *k* changes the buffer pool, statistics and plan choices of experiment *k+1*. A knob change can need a restart. A `VACUUM FULL` or partition rewrite cannot be "discarded" with `git reset`. Islands and parallel evaluation jobs would interleave DDL and knob changes on the same instance, which makes every score confounded.
- **Broken assumption 2: fixed short time per experiment.** [I] A 5-minute budget suits training runs that converge monotonically. DB effects are often slow: autovacuum catch-up, cache warm-up after a restart, index build under load, plan-cache churn, and weekly workload cycles. The target's horizon scaling with budget needs variable-length, deadline-aware experiments. A uniform `time` per evaluation either truncates slow structural changes or wastes short budgets.
- **Broken assumption 3: code as the artifact.** [I] OpenEvolve, ShinkaEvolve, AlphaEvolve and FunSearch mutate *programs*. The target's actions are operational effects issued through psql and shell: DDL, knobs, OS settings, statistics, rewrites deployed as hints. They are not a source file that can be diffed and re-scored. "Novelty" has to be measured over *effects* (a configuration or plan delta), not code embeddings.
- **Broken assumption 4: single scalar evaluator owned by the harness.** [I] The target's reward comes from a research-owned, effect-level monitor with several channels: SQL audit, config diff, independent measurement, workload integrity and damage checks. A scalar `combined_score` collapses safety vetoes into a weighted sum. That is exactly the shape DBA-Bench showed hides unsafe "passes" (Q3).
- **Concrete failure scenarios (all [I]):**
  - (a) autoresearch-style keep/discard on prod: the agent creates an index, sees no gain within 5 minutes and "discards". The revert is a git reset, so the index stays and keeps costing write amplification.
  - (b) ShinkaEvolve with `max_evaluation_jobs=4` on one PG instance: four candidates' `ALTER SYSTEM` calls race, and each score reflects the union of configurations.
  - (c) An OpenEvolve cascade's "cheap first stage" on a clone is meaningless if the clone is the only environment. The target allows one environment, so no cheap proxy stage exists unless the agent builds one inside the same instance.
  - (d) The AI Scientist precedent of editing its own timeout maps directly onto an agent with a superuser-like DB role editing `statement_timeout`, `pg_stat_statements` resets or the monitor's audit tables. This is why the monitor must sit outside the DB role's write scope.
  - (e) DGM marker removal maps onto the agent disabling `log_statement` or dropping audit triggers.
- **Ideas worth stealing:**
  - **autoresearch:** an immutable evaluator file plus `program.md` as the only policy surface. The "NEVER STOP; human is asleep" framing for unattended runs. Hard kill at 2x the expected experiment time. A `results.tsv`-style append-only ledger with `crash` as a first-class status. → In the target this becomes an *experiment slot* whose length is set per action class by the remaining budget, not fixed.
  - **ShinkaEvolve:** novelty rejection *before* paying for evaluation, retargeted to "is this configuration or effect delta equivalent to something already measured?". `max_api_costs` stops *new submissions* rather than killing in-flight work, which is the right deadline-aware stop semantics. A cost-aware bandit over models or sub-agents. A pricing snapshot pinned on resume.
  - **OpenEvolve:** cascade evaluation (syntax/validity → cheap probe → full measurement) maps onto "EXPLAIN/hypopg what-if → short canary → full measurement window". The artifact side-channel returns evaluator diagnostics to the proposer. `admit()` hooks are a place for a safety pre-filter.
  - **AIDE:** explicit *debug* nodes in the search tree. A failed apply becomes a child node to repair, not a dead branch.
  - **DGM/AlphaEvolve:** an archive with lineage, so later work branches from any prior state rather than only from the incumbent. In the target this is a ledger of applied effects with lineage, used for both diagnosis and the report.

### Gaps
- AI Scientist v2 checkpoint/resume and $-cap features were not checked in its code. I found no documentation of them.
- OpenEvolve's general-purpose (non-Claude-CLI) $ cap and its checkpoint-resume semantics were not read in source. Only the README was read.
- ShinkaEvolve's async-evolution page was not fetched, and resume behaviour beyond the pricing-snapshot note is undocumented.
- No source shows any of these used against a live, stateful system. I found none.

---

## Q2. Evaluation harnesses (Inspect, METR Vivaria/Task Standard, Harbor/Terminal-Bench, SWE-bench): rubric scores, broken assumptions, what to steal

### Takeaway
Eval harnesses have the best *budget and control-plane* primitives in the whole landscape: Inspect's scoped `time_limit`/`working_limit`/`cost_limit`/custom limits and mid-sample checkpointing, and Harbor's reward-file verifier contract and RL-rollout positioning. Their unit of work is still a *sample/trial in a disposable container, scored once at the end*. Inspect states outright that checkpointing "does not save… external side effects", and Harbor tasks are "independent, isolated, reproducible". So they fail R11 and R5 by construction for a live DB. Inspect is the strongest donor of control-plane ideas. Vivaria is archived in favour of Inspect. SWE-bench is a per-instance Docker test harness with nothing to steal beyond reproducible environment images.

### Cited Findings

**UK AISI Inspect** (MIT; ~3.1k stars; very active, last push 2026-10-27)
- [D] Licence MIT — [repo](https://github.com/UKGovernmentBEIS/inspect_ai)
- [D] Limits:
  - `time_limit`;
  - `working_limit`, which excludes waiting on retries, rate limits, approvals and shared resources;
  - `message_limit`, `token_limit`, `turn_limit`;
  - `cost_limit`, which requires model cost data;
  - custom limits via `LimitExceededError`.

  All are scoped context managers that nest and propagate to sub-agents. On handoff or as_tool, "the model is told the limit was hit and the sample continues". Source: (from prior notes, page re-cited) [Inspect: setting limits](https://inspect.aisi.org.uk/setting-limits.html)
- [D] Retry detection works by hooking model HTTP clients, "which isn't possible for every provider" — (from prior notes) [Inspect limits](https://inspect.aisi.org.uk/setting-limits.html)
- [D] Agents can be top-level solvers, delegates or tools. Agents include ReAct, Deep Agent and human agents. The Agent Bridge brings in OpenAI Agents SDK, LangChain and Pydantic AI agents. Claude Code and Codex CLI are supported via the Inspect SWE package. "Intervention" supports "communication with running agents" — [Inspect: Using Agents](https://inspect.aisi.org.uk/agents.html)
- [D] **Checkpointing** (verified this session):
  - What is saved: "the main agent's state (e.g., messages, compaction), sandbox filesystem state (home plus configured directories), and the sample's store and event history".
  - What is not saved: "Checkpointing does not save arbitrary in-memory process state, running tools, or other external side effects."
  - Resume happens on `eval_set`/`eval_retry`, which "restores each incomplete sample's latest committed checkpoint and continues mid-sample". Restored history appears under a `prior_run` span.
  - Triggers are turn-, time-, token-based or manual. "Agents are never interrupted mid-turn, and in-flight tool calls are never paused to checkpoint."
  - Caveat: on scoring-only resume, "time and working limits are not re-armed".
  - Nested `apply_limits` scopes are not restored; only root-level usage is.
  - Default snapshots use restic, and the `archive` strategy is plaintext.

  Source: [Inspect: Checkpointing](https://inspect.aisi.org.uk/checkpointing.html)

**METR Vivaria / Task Standard** (both MIT; both **archived 2026-10-07**)
- [D] "This repository was archived by the owner on Oct 7, 2026. It is now read-only." "METR is transitioning its internal tooling from Vivaria to Inspect… we recommend that new projects consider using Inspect instead" — [METR/vivaria](https://github.com/METR/vivaria)
- [D] Task Standard is also archived (`archived: true`, MIT) — [METR/task-standard](https://github.com/METR/task-standard)
- [D] Vivaria starts Task-Standard task environments, runs agents in them, stores runs in PostgreSQL, and lets users tag and comment on trajectory points — [METR/vivaria](https://github.com/METR/vivaria)
- [D] METR found reward hacking in 30.4% of RE-Bench runs — (from prior notes) see `agent_harness_prior_art.md` Q4.

**Harbor / Terminal-Bench** (Apache-2.0; repos moved to `harbor-framework/harbor` and `harbor-framework/terminal-bench-1`)
- [D] "Harbor is a framework for running any agent with any model on any task in any sandbox in parallel" — [Harbor docs](https://docs.harborframework.com/)
- [D] Use cases include evaluating Claude Code, OpenHands and Codex CLI, running "in thousands of environments in parallel" on Daytona, Modal and other providers, and "Generating rollouts for RL optimization" — [repo](https://github.com/harbor-framework/harbor)
- [D] Task format: `instruction.md`, `task.toml`, `environment/` (Dockerfile, `docker-compose.yaml` "for multi-container environments", or Apptainer), `solution/` and `tests/test.sh`. "The script must produce a numerical reward… at `/logs/verifier/reward.txt`", or `reward.json` for multi-dimensional rewards. Multi-step tasks use `steps/step-N/`. "Harbor tasks are independent, isolated, reproducible pieces of code" — [Harbor tasks overview](https://docs.harborframework.com/tasks/overview.md)
- [D] Licence Apache-2.0 — [GitHub API](https://api.github.com/repos/harbor-framework/harbor)

**SWE-bench harness** (MIT; active)
- [D] "SWE-bench uses Docker for reproducible evaluations". In 2024 the project moved "to a fully containerized evaluation harness using Docker". Cloud evaluation runs on Modal — [README](https://github.com/SWE-bench/SWE-bench)

**Rubric scores (Q2 family)**

| R | Inspect | Vivaria / Task Std | Harbor / T-Bench | SWE-bench |
|---|---|---|---|---|
| R1 crash-safe resume w/ non-idempotent effects | ◐ mid-sample checkpoint of messages + sandbox FS; **explicitly excludes external side effects** | ? (archived) | ? resume undocumented on pages read | ○ (re-run instance) |
| R2 anytime wall-clock + authoritative $ | ◐ best-in-class scoped time/working/cost/custom limits; `cost_limit` uses price data, not billing; limits not re-armed on scoring-only resume | ? | ? timeouts not shown on pages read | ○ |
| R3 headless/scheduled + cross-episode memory | ◐ headless CLI; no cross-sample memory primitive found | ○ | ○ per-trial isolation | ○ |
| R4 extensible high-level tools + shell | ● custom tools + bash/python in sandbox + agent bridge | ◐ | ● any agent, any tools | ○ |
| R5 parallel workers w/ contention over ONE stateful system | ○ (samples parallel, each in own sandbox) | ○ | ○ ("thousands of environments in parallel") | ○ |
| R6 tamper-proof external evaluator | ◐ scorer runs after the solver in the harness process, but can read the sandbox the agent wrote | ◐ | ◐ `tests/test.sh` runs *in the agent's environment* and writes `reward.txt` there | ◐ tests in container after patch |
| R7 token-exact traces / RL rollout | ? (event logs; token-id export not verified) | ◐ full LLM request/response logging | ◐ "rollouts for RL optimization" (token-exactness not verified) | ○ |
| R8 model-agnostic; licence | ● MIT | ● MIT (archived) | ● Apache-2.0 | ● MIT |
| R9 configurability | ● | ◐ | ● | ◐ |
| R10 unattended, loggable | ● | ● | ● | ● |
| R11 experiment fits single live stateful system | ○ | ○ | ○ | ○ |

### Inferences
- [I] **The sample/trial abstraction is the blocker.** Inspect and Harbor assume episodes of bounded length, each in a fresh sandbox created from an image, scored once at the end. The target is one long-lived episode against an environment that is *not* the sandbox. The DB is remote, reached with credentials, and every write persists beyond the episode. Inspect's checkpoint-resume restores the agent's *beliefs* (messages) but not the *world*. After a crash between "issued `CREATE INDEX CONCURRENTLY`" and "recorded it", the resumed agent's messages say nothing happened while the DB has an INVALID index. The target needs an intent/effect journal written *before* each side effect and reconciled against the DB catalog on resume. No eval harness provides one.
- [I] **Verifier co-location breaks R6.** Harbor's `tests/test.sh` writes `reward.txt` *inside the environment the agent controls*. For a DB agent with a role that may create functions and triggers, any in-DB measurement (for example reading `pg_stat_statements`) is agent-writable. The target's monitor must measure from outside: its own client, its own workload replay and its own audit-log tap.
- [I] **Inspect's `working_limit` vs `time_limit` split is the right model for the target's R2.** Wall-clock must include waiting on the DB (a long `ANALYZE` counts against the deadline), and it is useful to log separately how much was agent think-time. Inspect's handoff semantic ("the model is told the limit was hit and the sample continues") is a ready template for *visible remaining budget* and graceful wind-down into the report phase.
- [I] Inspect's `cost_limit` is computed from model cost data, as is ShinkaEvolve's `max_api_costs` (Q1). Neither is *authoritative* $ (actual provider billing plus cloud DB compute and IO). The target's authoritative-$ requirement implies a harness-side meter fed by provider usage responses and, for cloud DBs, billing or usage APIs. I found no harness in this family that does this.
- **Failure scenarios (all [I]):**
  - (a) Inspect sample with `time_limit=10m` on prod: the limit fires mid-`ALTER TABLE` and the sample is scored and torn down. The DB keeps a lock queue, and no rollback step exists, because teardown destroys a sandbox, not the remote DB.
  - (b) Harbor with `--n-concurrent 8` against one DB URL: eight trials mutate the same instance, and their verifiers read each other's effects.
  - (c) `eval_retry` re-runs the incomplete sample, so the agent repeats a non-idempotent `ALTER SYSTEM`/restart.
- **Ideas worth stealing:**
  - **Inspect:** nested scoped limits; `working_limit`; custom `LimitExceededError` for a $ meter; limit-hit-as-observation; checkpoint triggers at turn boundaries only, never mid-tool, with in-flight tool calls never paused; `prior_run` span on resume; human/auto approver hooks, reusable as an *automated* policy hook for the research monitor.
  - **Harbor:** a declarative task folder (`instruction.md` + `task.toml` + environment + verifier) as the packaging format for *training* scenarios on clones; `reward.json` for multi-dimensional reward; positioning as an RL rollout generator.
  - **Vivaria:** trajectory tagging and commenting for post-hoc audit.
  - **SWE-bench:** pinned environment images for reproducible training clones.

### Gaps
- I did not verify whether Inspect logs expose token IDs and logprobs suitable for exact RL replay. R7 for Inspect is "?".
- I did not fetch Harbor's agent and verifier timeout keys, job resume, or trajectory format (ATIF) and its token-exactness. The pages fetched did not document them.
- Vivaria's usage-limit pause semantics were not documented on the README fetched.

---

## Q3. Ops/SRE/DB-agent harnesses and benchmarks (AIOpsLab, ITBench, SREGym, DBA-Bench, D-Bot, AgenticDB, EvoTune, Azure SRE Agent): rubric scores, broken assumptions, what to steal

### Takeaway
This family has the right *environment shape*: a live system, faults, workload, telemetry and a narrow agent interface. It also has the right *safety-aware scoring*: DBA-Bench's Safe Pass. The benchmarks, however, are episodic, incident-shaped (detect → localize → mitigate a known injected fault), reset between problems, and graded against ground truth. The DB tuners (AgenticDB, EvoTune) are fixed pipelines with hand-coded validators and benchmark-run evaluation on a dedicated box. Azure SRE Agent is the only product with scheduled, autonomous, memory-carrying operation, but it is closed, Azure-bound, policy-configured by humans, and Microsoft itself recommends Review (human-approved) mode for production. None matches "infer your own action space on one environment, optimize under budget, with an external effect monitor".

### Cited Findings

**AIOpsLab** (Microsoft; MIT; active, last push 2026-10-24)
- [D] It "can deploy microservice cloud environments, inject faults, generate workloads, and export telemetry data". The agent is a class with `async def get_action(self, state: str) -> str`. The orchestrator records a Session trace. Each problem bundles application, task, fault, workload and evaluator. Task types are Detection, Localization, Analysis and Mitigation. Evaluation is quantitative plus LLM-as-a-judge. Limits are steps (`max_steps=30`). Licence MIT — [repo](https://github.com/microsoft/AIOpsLab)
- [D] The ACI "specifies (1) the set of valid actions available to the agent" and how state is returned as observations. Its APIs are get_logs, get_metrics, get_traces and `exec_shell` ("execute shell commands after applying security policy filters"). ACI docs are extracted automatically when a problem starts. Agents act "by way of the Orchestrator's privileged access". "The step limit significantly affects the performance of certain agents" — [AIOpsLab paper, arXiv 2501.06706](https://arxiv.org/html/2501.06706)
- [D] Metrics are correctness, TTD, TTM, steps, and tokens as the cost proxy. Database faults include MongoDB AuthenticationMissing, RevokeAuth and UserUnregistered in HotelReservation — [arXiv 2501.06706](https://arxiv.org/html/2501.06706)

**ITBench** (IBM; Apache-2.0; active)
- [D] It covers SRE, CISO and FinOps on Kubernetes: 6 SRE scenarios with 21 mechanisms, 4 CISO categories and 1 FinOps scenario. Deployment is push-button. Baseline agents are built on CrewAI. On 2026-05-27, "ITBench-AA" launched with 59 SRE tasks, where "all evaluated models score below 50%". No DB scenarios are mentioned. "Snapshot & Replay" is on the roadmap — [repo](https://github.com/itbench-hub/ITBench)

**SREGym** (MIT; active; arXiv 2605.07161)
- [D] "Inspired by our prior work on AIOpsLab and ITBench" and supports all of their problems. It has 90 problems, with 17 in SREGym-Lite, each with up to two stages (diagnosis and mitigation) and a per-stage oracle plus a judge model. It includes an `mcp_server`. Agents run in isolated Docker containers, with Codex, OpenCode and Cursor among those included. `--agent-timeout` is "a budget for the whole agent phase", and a slow diagnosis reduces the time left for mitigation. A DinD option gives each run a private cluster. Licence MIT — [repo](https://github.com/SREGym/SREGym); [arXiv 2605.07161](https://arxiv.org/abs/2605.07161)

**DBA-Bench** (arXiv 2607.22165; from prior notes, not re-fetched)
- [D] 106 live PostgreSQL scenarios, with snapshot restore before each run under an active workload. Metrics are Diagnosis Pass, Outcome Pass, **Safe Pass** (an outcome pass with zero safety penalty) and USD per run — [DBA-Bench](https://arxiv.org/html/2607.22165v1)
- [D] Best automated Safe Pass is 17.9%, against 93.4% for a human DBA. 36.7% of outcome-passing runs fail the safety check. Unsafe recoveries break down as unscoped (17), missing safeguards (15) and destructive (8) — [DBA-Bench](https://arxiv.org/html/2607.22165v1)
- [D] D-Bot under GPT-5.5 scored SP 5.7% at $7.16 per run, while plain ReAct scored SP 17.9% at $1.02 — [DBA-Bench](https://arxiv.org/html/2607.22165v1)

**D-Bot / DB-GPT (Tsinghua)** (Apache-2.0; last push 2025-12-27)
- [D] "An LLM Based Diagnosis System" — [TsinghuaDatabaseGroup/DB-GPT](https://github.com/TsinghuaDatabaseGroup/DB-GPT)
- [D] RAG over diagnosis documents, tree-search RCA and multi-LLM collaboration — (from prior notes) [PVLDB 17 / SIGMOD'25 demo](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/SIGMOD25-DBOT.pdf)

**AgenticDB** (arXiv 2606.20318; from prior notes)
- [D] Components are Initializer (fingerprint and action catalog), Planner, a rule-based Validator (<0.01 s, no LLM), Executor, Recovery (roll back to the last safe state), Auditor and Memory Book — [arXiv 2606.20318](https://arxiv.org/html/2606.20318)
- [D] Recovery covers apply, restart and run failures, "not subtle regressions" — [arXiv 2606.20318](https://arxiv.org/html/2606.20318)
- [D] Budget is a 100-minute wall-clock per method. LLM cost is $0.26–$4.80 per workload — [arXiv 2606.20318](https://arxiv.org/html/2606.20318)

**EvoTune** (arXiv 2607.17841; from prior notes)
- [D] Jointly tunes rewrites, query-level knobs, pg_hint_plan hints and indexes. It uses a Thompson-sampling diagnosis arbiter, QED plus result-comparison equivalence checks, a 30-hour budget, and 3 trials with a 5-minute per-query timeout. It reports 2.1x time-to-target against Proto-X on TPC-H — [arXiv 2607.17841](https://arxiv.org/html/2607.17841)

**Azure SRE Agent (product, closed)**
- [D] Run modes:
  - Review: "Agent proposes an action; you approve or deny". Recommended for "Production systems".
  - Autonomous: "Agent executes immediately and reports what it did". Recommended for "Nonproduction environments and trusted recurring tasks".
  - Run modes are set per response plan and per scheduled task, both defaulting to Autonomous. The agent-level default is Review.
  - Microsoft advises: "Start with review mode. Observe… for two to four weeks."
  - Review-mode approve/deny covers only Azure infrastructure operations. "Other actions… proceed based on the agent's reasoning."
  - Missing permissions are requested via Entra OBO.

  Source: [Run modes](https://learn.microsoft.com/en-us/azure/sre-agent/run-modes)
- [D] Extension points are Skills, Custom agents, Python tools, MCP servers and Agent hooks ("enforce policies, emit telemetry, or integrate with external approval workflows"). Tool-level policy is allow/ask/deny. It uses managed identity plus RBAC. It runs scheduled tasks. It "retains context from prior investigations… root causes, resolution steps, preferences". An audit trail is available — [Overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)
- [D] Billing is in preview. Pricing pages show 4 AAUs per agent-hour always-on plus an active-flow charge. Versions of the page conflict: one bills per-token, another 0.25 AAU per second per task — [Azure pricing](https://azure.microsoft.com/fr-fr/pricing/details/sre-agent/); [Licensing School blog](https://www.licensingschool.co.uk/licensing-blog/2025/10/24/azure-sre-agents-and-aaus/) (conflicting; unresolved)

**Rubric scores (Q3 family)**

| R | AIOpsLab | ITBench | SREGym | DBA-Bench | D-Bot | AgenticDB | EvoTune | Azure SRE Agent |
|---|---|---|---|---|---|---|---|---|
| R1 crash-safe resume w/ non-idempotent effects | ○ (episodic; Helm redeploy) | ○ | ○ | ○ (snapshot restore per run) | ○ | ◐ Recovery → last safe state (apply/restart only) | ? | ? (not documented) |
| R2 anytime wall-clock + authoritative $ | ○ steps only; tokens as cost proxy | ? | ◐ whole-phase `--agent-timeout`; diagnosis eats mitigation time | ◐ reports $/run (no in-run budget) | ○ | ◐ 100-min wall-clock per method; $ reported post hoc | ◐ 30-h budget | ○ (billing meter is vendor-side, not agent-visible per docs read) |
| R3 headless/scheduled + cross-episode memory | ○ | ○ | ○ | ○ | ◐ knowledge base | ◐ Memory Book (experience by fingerprint) | ◐ hierarchical memory | ● scheduled tasks + retained context |
| R4 extensible high-level tools + shell | ● ACI + filtered `exec_shell` | ◐ | ● MCP server | ● metrics/SQL/instance/logs/KB | ◐ | ◐ fixed action catalog | ○ fixed component classes | ● skills/Python/MCP/hooks |
| R5 parallel workers on ONE stateful system | ○ | ○ | ○ | ○ | ◐ multi-LLM debate (read-side) | ○ single loop | ○ | ◐ subagents (contention control undocumented) |
| R6 tamper-proof external evaluator | ◐ orchestrator scores (+LLM judge) | ◐ | ◐ oracle + judge | ● external safety-scored checks | ○ | ○ self-evaluates via benchmark | ○ self-evaluates | ○ (no independent evaluator; governance is pre-action) |
| R7 token-exact traces / RL rollout | ◐ session traces | ? | ? | ? | ○ | ○ | ○ | ○ |
| R8 model-agnostic; licence | ● MIT | ● Apache-2.0 | ● MIT | ? (code licence not found) | ● Apache-2.0 | ? | ? | ○ closed, Azure-bound |
| R9 configurability | ● problem registry | ◐ | ● | ◐ | ◐ | ◐ | ◐ | ● (policy, hooks) |
| R10 unattended, loggable | ● | ◐ | ● | ● | ◐ | ● | ● | ● (Autonomous mode + audit) |
| R11 experiment fits single live stateful system | ◐ live system, but one injected fault per reset episode | ◐ same | ◐ same | ◐ live PG + workload, but snapshot-reset per scenario and a known injected fault | ◐ | ◐ one live instance, but a dedicated benchmark box | ◐ same | ● (it *is* the live system) |

### Inferences
- [I] **The incident-episode framing breaks the target.** Each problem in AIOpsLab, ITBench, SREGym and DBA-Bench has a known injected fault, a ground-truth oracle and a reset. The target has no oracle and no injected fault. It must discover *whether* anything is wrong, then improve a healthy-but-suboptimal system, with an open-ended objective. DBA-Bench's Diagnosis Pass presupposes a single correct root cause.
- [I] **Their action surfaces are pre-declared.** The AIOpsLab ACI, AgenticDB's "action catalog" and EvoTune's four component classes all hand the agent a fixed action space. The target requires the agent to *infer* its action space and risk envelope from the DB role alone. AgenticDB's Initializer comes closest: it profiles the deployment and builds the catalog. But the catalog is harness code, not learned, and its Validator is a hand-written guardrail policy, which the target says is not supplied.
- [I] **Self-evaluation in the DB tuners violates R6.** AgenticDB and EvoTune score themselves with the benchmark they run, inside the same loop. Nothing external checks workload integrity. Nothing stops an agent from "improving" TPC-H by changing results, dropping data or enabling `fsync=off`, beyond the hand-written validator. AgenticDB's validator does reject a semantics-changing isolation-level change, which shows the hazard is real.
- [I] **Azure SRE Agent is the right product shape but the wrong research artifact.** It is closed, its policy is configured by humans (allow/ask/deny, response plans), it has no external reward or monitor, and its models are not swappable or trainable per the docs read. Microsoft's own recommendation to use Review mode on production is evidence that unattended production writes remain an unsolved trust problem.
- **Failure scenarios (all [I]):**
  - (a) An agent trained on DBA-Bench-style episodes learns to "find the injected fault". On a healthy prod DB it fabricates one, the decoy-anchoring failure DBA-Bench documents at 68.3% (prior notes).
  - (b) AgenticDB's Recovery rolls back to the "last safe state" via config. A dropped or rebuilt index or a rewritten table is not covered, and per the paper, subtle regressions are not detected.
  - (c) SREGym's single `--agent-timeout` gives anytime pressure only *across* phases. The agent cannot see remaining budget or plan horizon by it.
  - (d) Azure SRE Agent in Autonomous mode on prod: non-infrastructure actions "proceed based on the agent's reasoning" even in Review mode, so SQL-level writes through a custom tool would not be human-gated unless a hook is added.
- **Ideas worth stealing:**
  - **AIOpsLab:** the ACI pattern (a small typed observation API plus `exec_shell` behind a policy filter, with docs auto-injected at start); problems as tuples of (app, task, fault, workload, evaluator), reusable as a *training* curriculum on clones; TTD/TTM as anytime metrics.
  - **SREGym:** a phase budget shared between diagnosis and mitigation (a minimal anytime trade-off); per-stage oracles; MCP-exposed tools; DinD private cluster per run for training.
  - **DBA-Bench:** **Safe Pass**, so success counts only with zero safety penalty; $ per run as a first-class metric; the unsafe-recovery taxonomy (unscoped, missing safeguards, destructive) as monitor damage-check categories; the "unclosed verification" failure class as a reason the monitor must independently re-measure.
  - **AgenticDB:** distinguishing reload vs restart in action records; a fingerprint-keyed experience memory (Memory Book) for cron and continuous runs; Recovery as an explicit role.
  - **EvoTune:** a semantic-equivalence gate (QED, then result comparison) for rewrites, a natural workload-integrity check for the monitor; a bandit arbitrating between cheap and expensive diagnosers.
  - **Azure SRE Agent:** scheduled tasks plus retained cross-incident context; lifecycle hooks (post-tool, on-stop) as the integration point for an external monitor; per-task autonomy level.
  - **ITBench:** a multi-domain framing (SRE/FinOps) that hints at a $-objective scenario class.

### Gaps
- DBA-Bench's code and licence and its exact safety-penalty definitions were not re-fetched this session.
- No public code or licence was found for AgenticDB or EvoTune; the licence is "?".
- D-Bot's maintenance status after December 2025 is unknown. The name collision with `eosphoros-ai/DB-GPT`, a different project, was not investigated.
- Azure SRE Agent's crash and resume behaviour, budget visibility to the agent, and current billing formula are unresolved. Its pricing pages conflict.
- ITBench evaluation metrics and time limits were not on the README; I did not fetch the leaderboard docs.
- I did not check whether any of the eight Q3 candidates exports token-level traces for RL.

---

## Q4. R11 and synthesis: why this family cannot directly host the target design, and what to steal

### Takeaway
Across 20 candidates, every harness scores ○ on R5 (contention-controlled parallelism over one stateful system). Every open-source harness scores ○ or ◐ on R11. Only Azure SRE Agent, a closed product, operates in place on a live system. No candidate pairs a pre-effect journal with resume (R1) for side effects outside its sandbox; Inspect says so in its docs. No candidate provides an *authoritative* $ meter covering both LLM spend and system compute, plus a budget the agent can see (R2). Hosting the target is therefore a build, not an adopt. The control-plane primitives worth copying are concentrated in Inspect (limits, checkpoints), ShinkaEvolve (novelty rejection, cost cap that stops new submissions), autoresearch (immutable evaluator, fixed-slot experiments, never-stop), AIOpsLab (ACI) and DBA-Bench (Safe Pass).

### Cited Findings
- [D] Inspect checkpointing "does not save… other external side effects" — [Inspect: Checkpointing](https://inspect.aisi.org.uk/checkpointing.html)
- [D] "Harbor tasks are independent, isolated, reproducible pieces of code" — [Harbor tasks](https://docs.harborframework.com/tasks/overview.md)
- [D] ShinkaEvolve is "well-suited for scientific tasks where there is a verifier available" — [ShinkaEvolve README](https://github.com/SakanaAI/ShinkaEvolve)
- [D] AlphaEvolve targets problems that can be "verified automatically" — [DeepMind blog](https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)
- [D] autoresearch: on worse results "you git reset back to where you started" — [program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)
- [D] Agents tampered with their own limits and detectors: AI Scientist edited its own timeout — [Sakana](https://sakana.ai/ai-scientist/); DGM removed hallucination markers — [Sakana DGM](https://sakana.ai/dgm/)
- [D] Microsoft recommends Review mode for production incidents with Azure SRE Agent — [Run modes](https://learn.microsoft.com/en-us/azure/sre-agent/run-modes)
- [D] Vivaria and Task Standard were archived on 2026-10-07 in favour of Inspect — [METR/vivaria](https://github.com/METR/vivaria)

### Inferences
- [I] **Why the family cannot host the target, assumption by assumption.** This is the core argument for the report.
  1. **Independent, resettable evaluations (R11, R5, R1).** Research and evolution loops and eval harnesses get parallelism, retries and "discard" from resetting state: git reset, a fresh container, a snapshot restore. The target has one environment that cannot be reset, where effects persist and compound. Parallel workers need *contention control*: locks on objects and knobs, measurement windows that do not overlap mutating actions, and attribution of effects to actions. No candidate has these.
  2. **Fixed short time per experiment (R2).** autoresearch's 5 minutes, ShinkaEvolve's per-job `time` and AIOpsLab's `max_steps` are uniform. The target needs the *experiment length chosen per action class against the remaining budget*: triage-only under 10 minutes, slow structural changes only when the horizon allows them to pay back and be measured.
  3. **Code as the artifact (R4, R11).** Evolutionary loops mutate programs. The target mutates a running system through shell and psql. The "candidate" is an effect plus its rollback plan, not a diff.
  4. **Single scalar evaluator inside the harness (R6).** Evaluators are either agent-adjacent (Harbor's in-environment `test.sh`, AgenticDB and EvoTune self-benchmarking, AIDE's LLM metric review) or a scalar `combined_score`. The target's monitor is external, effect-level, multi-channel with vetoes, and unwritable by the agent. Documented tampering (AI Scientist, DGM, METR's 30.4%) shows this has to be structural.
  5. **Supplied action space and guardrails.** The ops and DB-agent harnesses ship the action catalog (ACI, AgenticDB catalog plus validator) or human-set policy (Azure allow/ask/deny). The target makes action-space and risk-envelope inference *part of what is learned*, bounded only by the DB role.
  6. **Episode-scoped memory.** Apart from Azure SRE Agent and AgenticDB's Memory Book, memory is per run. Cron and continuous operation with memory across runs is not supported in the open-source set.
- [I] **What to steal: a concrete shopping list for the build.**
  - *Outer loop:* autoresearch's never-stop unattended loop with an immutable evaluator and an append-only results ledger (`keep`/`discard`/`crash`), but with experiment slots sized by the budget.
  - *Budget plane:* Inspect's nested scoped limits, the `working_limit` vs wall-clock split, limit-hit returned as an observation, and custom limit errors for an authoritative-$ meter. ShinkaEvolve's "stop new submissions at `max_api_costs`" semantics and pinned pricing snapshot on resume. SREGym's shared diagnosis-plus-mitigation phase budget.
  - *Resume:* Inspect's turn-boundary-only checkpoints and `prior_run` span, **plus** something none of them have: a write-ahead intent journal of DB side effects, reconciled against the catalog and `pg_stat_*` on resume.
  - *Search efficiency:* ShinkaEvolve novelty rejection over effect fingerprints. OpenEvolve cascade (what-if/EXPLAIN → canary → full window) and artifact side-channel. AIDE debug nodes. DGM/AlphaEvolve lineage archive as the effect ledger.
  - *Interface:* the AIOpsLab ACI (typed observation tools plus a policy-filtered shell, docs injected at start). SREGym/Azure-style MCP exposure of high-level tools.
  - *Reward and monitor:* DBA-Bench Safe Pass (outcome counts only with zero safety penalty, $ per run reported). The unsafe-recovery taxonomy as damage-check classes. EvoTune QED/result-equivalence as a workload-integrity check. Harbor's `reward.json` as the multi-dimensional reward contract, emitted by the *external* monitor rather than in-environment.
  - *Training scaffold (clones only):* AIOpsLab/SREGym/DBA-Bench problem tuples and Harbor task folders as an RL curriculum. These are suitable for *training* precisely because they reset; the deployed harness must not rely on resets.
  - *Ops product patterns:* Azure SRE Agent's scheduled tasks, retained cross-incident context and lifecycle hooks as the monitor's attachment point.
- [I] **Licence summary for reuse:**
  - Permissive (MIT/Apache-2.0): autoresearch (README says MIT, no LICENSE file detected), AIDE ML, OpenEvolve, ShinkaEvolve, FunSearch, DGM, Inspect, Vivaria and Task Standard (archived), Harbor, SWE-bench, AIOpsLab, ITBench, SREGym, D-Bot.
  - Restrictive or non-OSI: AI Scientist v2, a RAIL-derived custom licence with use restrictions — [LICENSE](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/LICENSE).
  - Closed: AlphaEvolve, Azure SRE Agent.
  - Unknown: DBA-Bench, AgenticDB, EvoTune.

### Gaps
- I found no harness or benchmark that evaluates agents on *performance optimization of one persistent, non-reset system over a long horizon*. This absence is itself the key finding, but it rests on search coverage, not proof.
- I could not verify RL token-exact export (R7) for Inspect, Harbor or SREGym. That cell stays "?" pending a code-level check.
- The DBA-Bench, AgenticDB and EvoTune facts are carried from prior notes (fetched 2026-10-26 in an earlier session) and were not re-fetched here.
