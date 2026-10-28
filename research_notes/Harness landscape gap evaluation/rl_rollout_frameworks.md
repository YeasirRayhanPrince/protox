# Agentic-RL rollout / training frameworks as the training side of an autonomous DB-optimization harness (state as of Oct 2026)

Evidence legend:
- **[D]** documented in the project's own README, docs or paper, fetched this session (2026-10-26).
- **[I]** my inference from that documentation, not stated by the project.
- **[PK]** prior-knowledge item carried over from `harness_model_cotraining.md`. Where this session verified one, it is marked **[PK→D]**.

Repo metadata (licence, last push) was read via the GitHub API on 2026-10-26. Scores are a reading of the docs, not hands-on tests.

---

## Q1. Per-framework rubric scores (T1–T10), broken assumptions, adaptation cost, licence

### Takeaway
By late 2026 almost every major framework supports multi-turn tool rollouts (T1) and has some async mode (T3). Most now also have an **OpenAI-compatible gateway/proxy that captures token IDs** from an unmodified harness (T2/T5): Agent Lightning v1.0, AReaL, rLLM, NeMo Gym, ART, and OpenRLHF's server executor.

The rubric items no framework covers natively are:
- **T4** stateful, leased, snapshot-restored environments
- **T6** delayed, censored rewards
- the single-environment / no-group-sampling regime

All of them assume many parallel, cheap, resettable sandboxes, and most assume GRPO-style groups of N sibling rollouts from the same start state.

The best fits for black-box, slow rollouts are Agent Lightning, AReaL, rLLM and prime-rl, plus Tinker-style hosted training so no GPU sits idle during hour-long episodes.

### Score table (● full / ◐ partial / ○ none / ? unknown; justification and URLs in Cited Findings)

| Framework | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | T9 | T10 (licence) |
|---|---|---|---|---|---|---|---|---|---|---|
| verl (verl-project) | ● | ◐ | ● | ○ | ● | ◐ | ● | ◐ | ○ | ● Apache-2.0, most mature |
| verl-agent (GiGPO) | ● | ○ | ◐ | ◐ | ◐ | ◐ | ◐ | ● (Dr. MAS) | ○ | ◐ Apache-2.0, research code |
| SkyRL (+gym, agent, tx) | ● | ◐ | ● | ◐ | ◐ | ◐ | ◐ | ? | ◐ | ● Apache-2.0 |
| AReaL 2.0 | ● | ● | ● | ○ | ● | ◐ | ● | ? | ◐ | ● Apache-2.0 |
| OpenPipe ART | ● | ● | ◐ | ○ | ◐ | ◐ | ● | ? | ○ | ◐ Apache-2.0, LoRA/small-scale |
| Agent Lightning v1.0 | ● | ● | ● | ◐ (K8s Jobs) | ● | ◐ | ? | ● (lineage) | ◐ | ● MIT |
| rLLM | ● | ● | ● | ◐ (snapshot+warm-pool) | ● | ◐ | ● | ◐ | ● (10+ harnesses) | ● Apache-2.0 |
| Prime Intellect verifiers + prime-rl + Hub | ● | ◐ | ● | ◐ | ● | ◐ | ● | ● (subagent edges) | ◐ | ● MIT / Apache-2.0 |
| slime | ● | ◐ | ● | ○ | ● | ◐ | ● | ◐ | ○ | ● Apache-2.0 |
| ROLL (+RollArt) | ● | ◐ | ● | ◐ | ? | ◐ | ● | ? | ○ | ● Apache-2.0 |
| OpenRLHF | ● | ◐ | ● | ◐ (`reset/step`) | ● | ◐ | ● | ◐ (MARTI fork) | ○ | ● Apache-2.0 |
| TRL (+OpenEnv) | ● | ○ | ○/◐ | ◐ | ◐ | ◐ | ● | ○ | ○ | ● Apache-2.0 / BSD-3 |
| NeMo-RL + NeMo Gym | ● | ● | ● | ● (closest) | ● | ● (multi-reward) | ● | ? | ● (task-level harness routing) | ● Apache-2.0 |
| Tinker (hosted) | ◐ (you write loop) | ● (your code) | ● (your code) | n/a (your code) | ● (renderers) | ● (your code) | ● | ◐ | n/a | ◐ proprietary service; cookbook Apache-2.0 |
| SWE-RL / KAT-Coder pipelines (papers) | ● | ● (KAT: black-box harnesses) | ● | ◐ | ● | ◐ | ● | ○ | ● (KAT) | ○ not released as frameworks |

### Cited Findings

**verl**
- **[D]** The repo moved to `verl-project/verl` (Jan 2026). It is Apache-2.0 with ~24k stars and was pushed 2026-10-27. Recipes now live in a separate `verl-recipe` repo — [verl GitHub](https://github.com/verl-project/verl)
- **[D]** Has a multi-turn tool-calling "agent loop", SandboxFusion integration and SGLang "server-based RL, and partial rollout". There is a fully-async DAPO tutorial — [verl README](https://github.com/verl-project/verl)
- **[D]** Released 2026: `vexact`, a "zero-mismatch" HF rollout with batch-invariant kernels; `uni-agent`, an agent framework on verl; RL-Insight observability; and VeRL-Tinker, which runs the Tinker Cookbook loop on verl-managed GPUs — [verl README](https://github.com/verl-project/verl)
- **[D]** The verl team publishes a write-up on multi-turn tokenization and masking pitfalls with reasoning models — [Awesome-ML-SYS tutorial](https://github.com/zhaochenyang20/Awesome-ML-SYS-Tutorial/blob/main/rlhf/verl/multi-turn/fast_tokenization/multiturn_tokenization_and_masking.md)
- **[D]** Other frameworks use verl as their backend: Agent Lightning's async mode uses "verl's rollout correction" for staleness, and rLLM uses verl for distributed training — [Agent Lightning async doc](https://github.com/microsoft/agent-lightning/blob/main/docs/35-asynchronous-training.md); [rLLM README](https://github.com/rllm-org/rllm)

**verl-agent / GiGPO**
- **[D]** verl-agent uses a "step-independent multi-turn rollout" with customizable per-step input, history and memory modules.
- **[D]** Its environments are ALFWorld, WebShop, Search, Sokoban, Gym Cards and AppWorld. It runs "Parallelized Gym environments" and "Group environments support (for group-based RL)", with GiGPO/GRPO/PPO/DAPO/GSPO/RLOO.
- **[D]** GiGPO was accepted at NeurIPS 2025, and "similarity-based GiGPO" was added in 2025-08. Dr. MAS covers multi-agent end-to-end RL.
- **[D]** Last push 2026-06-09; Apache-2.0.

  — [verl-agent GitHub](https://github.com/langfengQ/verl-agent); [GiGPO arXiv 2505.10978](https://arxiv.org/abs/2505.10978) [PK→D]

**SkyRL**
- **[D]** SkyRL is now a unified library: skyrl-train, skyrl-tx (a Tinker-API backend on your own hardware), skyrl-agent ("long-horizon, real-environment tasks") and skyrl-gym (Gymnasium-API math/coding/search/**SQL** envs).
- **[D]** Supports "Fully Async RL with In-Flight Weight Updates" and integrates Harbor for terminal agents (Feb 2026).
- **[D]** Has a 397B knowledge-work RL guide with Mercor (APEX-Agents). Apache-2.0.

  — [SkyRL README](https://github.com/NovaSky-AI/SkyRL); [SkyRL-Agent paper arXiv 2511.16108](https://arxiv.org/pdf/2511.16108)

**AReaL**
- **[D]** AReaL 2.0 was released 2026-07-01. It is "optimized for online RL training for black-box agent applications by simply replacing the `base_url`".
- **[D]** It has an OpenClaw example ("no code changes, works with any agentic runtime") and a coding-agent RL example with "AReaL-SWEAgent/Claude Code Agent".

  — [AReaL README](https://github.com/areal-project/AReaL)
- **[D]** Its proxy is an "HTTP proxy server" with "complete token-level information". It "builds conversation trees and supports reward backpropagation". The proxy runs on local, Slurm and Ray schedulers — [AReaL agentic RL tutorial](https://github.com/areal-project/AReaL/blob/main/docs/en/tutorial/agentic_rl.md)
- **[D]** Staleness is bounded by `rollout.max_head_offpolicyness` (e.g., 4 versions; 0 gives synchronous training). **Partial rollouts** let one trajectory be "segmented across multiple policy versions" — [AReaL async doc](https://github.com/areal-project/AReaL/blob/main/docs/en/algorithms/async.md)
- **[D]** Supports DPO and SFT. Adds KPop/IcePop token masking for train–inference mismatch. Apache-2.0 — [AReaL README](https://github.com/areal-project/AReaL)

**OpenPipe ART**
- **[D]** ART is split into an "OpenAI-compatible client" and a server that "runs the model's latest LoRA in vLLM". Each message is stored in a Trajectory, and "your code assigns a `reward`".
- **[D]** It offers RULER LLM-judge rewards, MCP•RL, and a "W&B Training (Serverless RL)" hosted backend.
- **[D]** It has text-to-SQL SFT/distillation examples. Apache-2.0.

  — [ART README](https://github.com/OpenPipe/ART)

**Microsoft Agent Lightning**
- **[D]** v1.0 (Aug 2026) is a "3,500-line lightweight agentic RL framework for training agents with real harnesses". Agents talk to the model through a proxy "with ZERO changes".
- **[D]** It has native Kubernetes Jobs, so no external sandbox service is needed. An API Gateway "captures training data".
- **[D]** Reported coding-agent result: Qwen3.5-35B-A3B on SWE-bench Verified rose from 47.8% to 61.6%. MIT licence.

  — [Agent Lightning README](https://github.com/microsoft/agent-lightning); [tech report arXiv 2608.17528](https://arxiv.org/abs/2608.17528)
- **[D]** The motivation for token-ID passthrough is "No More Retokenization Drift: Returning Token IDs via the OpenAI Compatible API" — [vLLM blog](https://blog.vllm.ai/2025/10/22/agent-lightning.html)
- **[D]** How collocated async works:
  - Up to `async_train_batch_size` prompt groups are kept active, and unfinished groups "carry over" to the next step.
  - Before a weight update the Gateway "pauses new model requests and waits for requests already in flight". Paused requests get a retryable response, so agents need retrying clients.
  - "All four sibling rollouts must finish before that group can be used", which preserves GRPO/RLOO groups.
  - A carry-over age metric is reported.

  — [Agent Lightning async doc](https://github.com/microsoft/agent-lightning/blob/main/docs/35-asynchronous-training.md)
- **[D]** An earlier SQL-agent write-up trains "AI agents to write and self-correct SQL" — [Medium](https://medium.com/@yugez/training-ai-agents-to-write-and-self-correct-sql-with-reinforcement-learning-571ed31281ad)

**rLLM**
- **[D]** "Agentic RL on any harness, with any backend". It supports 10+ CLI harnesses (Claude Code, Codex, Terminus-2, mini-swe-agent, opencode) and Harbor task dirs, or `@rllm.rollout` around LangGraph / the OpenAI Agents SDK.
- **[D]** Sandboxes are Docker, Daytona, Modal or local, "with snapshot + warm-pool acceleration". Backends (`verl`, `tinker`, `fireworks`) switch with one flag.
- **[D]** A gateway captures token IDs and logprobs "by URL-routed sessions" into Episodes, which contain Trajectories made of Steps.
- **[D]** Supports GRPO, REINFORCE, RLOO, SFT and on-policy distillation, and has a fully-async deep-research recipe. Apache-2.0.

  — [rLLM README](https://github.com/rllm-org/rllm)
- **[PK]** DeepSWE (~42% SWE-bench Verified) was not re-verified this session — [Together blog](https://www.together.ai/blog/deepswe)

**Prime Intellect: verifiers, prime-rl, Environments Hub**
- **[D]** verifiers is "our library for creating environments to train and evaluate LLMs". It is tied to the Environments Hub, prime-rl and Hosted Training. Integration tests are tagged by "runtime and harness" (e.g., `docker and codex`). MIT — [verifiers README](https://github.com/PrimeIntellect-ai/verifiers)
- **[D]** prime-rl is "Fully asynchronous RL", with SFT, RL and evals in one stack. Apache-2.0 — [prime-rl README](https://github.com/PrimeIntellect-ai/prime-rl)
- **[D]** Staleness in prime-rl:
  - It is measured per token. `orchestrator.max_staleness` (default 8) masks tokens past the bound, and "drops a sample only when no token is left to train".
  - "Rollouts are never cancelled for staleness."

  — [prime-rl algorithms doc](https://github.com/PrimeIntellect-ai/prime-rl/blob/main/docs/algorithms.md)
- **[D]** Multi-turn merging in prime-rl:
  - Each LLM call is a trajectory step. Steps merge into one sample only while the **extension property** holds, i.e. each prompt is an exact prefix extension of the previous one.
  - Context compaction, sub-agent hand-off, or a template that strips thinking starts a new sample, so the worst case is O(T²).
  - Harness-declared `subagent_call` / `compaction` edges drive credit.
  - There are user token filters, e.g. "dropping warning lines from tool output".

  — [prime-rl algorithms doc](https://github.com/PrimeIntellect-ai/prime-rl/blob/main/docs/algorithms.md)

**slime**
- **[D]** Training runs on Megatron and rollout on SGLang + router, joined by a Data Buffer. Custom generate functions add multi-turn tools, sandboxes and verifiers.
- **[D]** There is a `fully_async` example for "long-tail agentic generation". The `coding_agent_rl` example trains Qwen3.8-27B with "token-correct trajectories".
- **[D]** Docs cover fault tolerance and debug replay.
- **[D]** Ecosystem: Dressage ("any agent and sandbox"), APRIL (active partial rollouts) and AWS AgentCore RL Toolkit. Apache-2.0.

  — [slime README](https://github.com/THUDM/slime); [slime fully_async](https://github.com/THUDM/slime/blob/main/examples/fully_async/README.md)

**ROLL**
- **[D]** Has agentic RL with "environment-level asynchronous parallel rollout" and async training, plus DPO, SFT, distill pipelines and GiGPO.
- **[D]** RollArt was an OSDI'26 paper. The ALE ecosystem and ROME agentic model were published in Jan 2026. Freshness-Aware prioritized experience replay is supported.
- **[D]** The README is internally inconsistent: one RLVR bullet still says "Asynchronous training under implementation".

  — [ROLL README](https://github.com/alibaba/ROLL); [RollArt arXiv 2512.22560](https://arxiv.org/abs/2512.22560); [ROLL Flash arXiv 2510.11345](https://arxiv.org/abs/2510.11345)

**OpenRLHF**
- **[D]** Uses "token-in-token-out agent execution … zero text-level mismatches", with a `reset()` + `step()` multi-turn agent API, `--train.agent_func_path` and `--train.async_enable`. An OpenAI-compatible server executor example exists.
- **[D]** **FlashREINFORCE** (2026-09): "critic-free, single-rollout asynchronous RL … one rollout per prompt". It uses a batch-mean baseline and a binary-KL trust region on the vLLM logprobs.
- **[D]** The MARTI fork covers multi-agent training. Apache-2.0.

  — [OpenRLHF README](https://github.com/OpenRLHF/OpenRLHF)

**TRL + OpenEnv**
- **[D]** In `GRPOTrainer(environment_factory=…)` the trainer "creates one … instance per generation" and calls `reset()` per episode. Public methods become tools, and the reward reads `env.reward`. The trainer itself runs the tool loop.
- **[D]** OpenReward and Harbor "conform to the same `environment_factory` contract".

  — [TRL OpenEnv doc](https://github.com/huggingface/trl/blob/main/docs/source/openenv.md)
- **[D]** OpenEnv is a Gymnasium-style `step()/reset()/state()` spec for containerized HTTP environments, from Meta-PyTorch and HF with a multi-company committee. BSD-3 — [OpenEnv docs](https://huggingface.co/docs/openenv/index); [HF blog](https://huggingface.co/blog/openenv)

**NeMo-RL + NeMo Gym**
- **[D]** NeMo Gym defines an environment as dataset + **agent harness** + verifier + **state** (per-task execution context).
- **[D]** It runs harnesses out of the box: OpenHands, mini-SWE-agent, LangGraph, Claude Code, Codex CLI, OpenClaw and more.
- **[D]** v0.6 can "use supported external agent harnesses during RL training while preserving exact token IDs". It does "task-level harness routing".
- **[D]** v0.7 adds:
  - Environment Servers that "manage sessions, verification, cleanup, and failures"
  - "automatic Slurm resume after timeout or preemption"
  - "pause or resume sandboxes without losing task state"
- **[D]** Has multi-reward verification and a BIRD SQL env. It integrates with NeMo RL, Unsloth and VeRL. Apache-2.0.

  — [NeMo Gym README](https://github.com/NVIDIA-NeMo/Gym)
- **[D]** NeMo-RL supports async rollouts with "replay buffers for off-policy training", multi-turn RL, SFT, DPO and GDPO multi-reward. Nemotron-3 Super/Ultra were trained with it — [NeMo-RL README](https://github.com/NVIDIA-NeMo/RL)
- **[D]** The Session State tutorial describes state as "(in-memory)" — [NeMo Gym README](https://github.com/NVIDIA-NeMo/Gym)

**Tinker (Thinking Machines)**
- **[D]** A managed service for "Open weights, dense and MoE, from 4B to 1T parameters". Its primitives are `sample`, `forward_backward`, `optim_step` and `save_state`.
- **[D]** "Your code controls the loop", and your code "evaluates the responses and computes rewards". You "pay for actual tokens used, not inactive time" — [Tinker page](https://thinkingmachines.ai/tinker/)
- **[D]** The cookbook uses `create_lora_training_client` and ships renderers for "bidirectional conversion between token sequences and structured chat messages". Apache-2.0 — [tinker-cookbook](https://github.com/thinking-machines-lab/tinker-cookbook)
- **[D]** The Tinker API is becoming a portability layer: SkyRL-tx implements it on your own GPUs, VeRL-Tinker runs it on verl, and rLLM has a `tinker` backend — [SkyRL README](https://github.com/NovaSky-AI/SkyRL); [verl README](https://github.com/verl-project/verl); [rLLM README](https://github.com/rllm-org/rllm)

**SWE-RL / KAT-Coder-style pipelines**
- **[PK]** SWE-RL uses an execution-free patch-similarity reward — [arXiv 2502.18449](https://arxiv.org/abs/2502.18449)
- KAT-Coder-V2.5 infrastructure:
  - A Gateway calling `/generate` directly fixed token drift in ~40% of samples.
  - Timeout-invalid rollouts were 6–7%, and an Experience Buffer decouples inference from training.
  - It trains across black-box harnesses (Claude Code, Codex, OpenClaw, OpenHands) with randomized tool schemas.

  — [arXiv 2607.05471](https://arxiv.org/html/2607.05471v1) (from the prior note, not re-fetched)

### Inferences (per framework: what breaks for slow, stateful, single-environment DB rollouts)
- **Universal break 1: GRPO groups need N clones of the same start state.**
  - verl, verl-agent, SkyRL, ART, TRL, Agent Lightning and prime-rl's default all use group-relative advantages. Agent Lightning even *requires all siblings to finish* [D].
  - With **one** fixed environment (prod, or one clone), group size is 1. Group sampling then means N sequential snapshot restores of a multi-GB DB, and an N-fold hour-long wall clock. **[I]**
  - Usable options:
    - single-rollout critic-free estimators (OpenRLHF FlashREINFORCE [D]; prime-rl's pluggable advantages [D])
    - PPO with a learned critic
    - offline methods
- **Universal break 2: "reset" means a fresh container.** TRL instantiates an env per generation [D]. verl-agent / SkyRL-gym / OpenEnv assume cheap `reset()` [D]. A DB `reset` is a snapshot restore (minutes) plus cache-state control. None of these frameworks has a lease/exclusive-lock concept for a scarce named resource. NeMo Gym's environment servers and pause/resume sandboxes come closest [D], but their session state is documented as in-memory. **[I]**
- **Universal break 3: hour-long episodes against version-bounded staleness.**
  - With prime-rl `max_staleness=8`, a 3-hour episode that spans more than 8 optimizer steps silently loses its earliest tokens from the loss [D mechanism; I consequence]. These are the diagnosis tokens, which matter most for credit.
  - AReaL `max_head_offpolicyness` behaves the same way [D].
  - The fix is to slow the optimizer clock (few, large steps) or to use importance-corrected off-policy losses with an explicit version tag per token.
- **Universal break 4: GPUs idle during DB measurement.** Colocated designs keep inference GPUs reserved while the agent waits minutes for a benchmark. Agent Lightning collocated async [D], verl hybrid engine and slime are examples. Hosted, token-billed Tinker ("not inactive time") [D] or a disaggregated trainer that only wakes when a batch is ready are economically better. **[I]**
- **Universal break 5: timeouts and censored outcomes.** No framework doc I read gives first-class semantics for "episode preempted, reward unknown or censored". The documented behaviour is drop/filter (KAT-Coder treats them as invalid; prime-rl drops samples with no trainable tokens). For DB work a preempted, half-applied optimization needs a separate state: rolled-back or not, with a damage-check result. **[I]**
- **verl-agent/GiGPO specifically:** step-level credit groups *identical anchor states* across group rollouts [PK→D]. DB states are continuous (knobs, metrics), so exact anchors rarely recur; the similarity-based variant [D] needs a DB-state similarity metric you define. It also still needs groups. **[I]**
- **Black-box harness fit (T2).** Agent Lightning, AReaL, rLLM, NeMo Gym and ART all accept an unmodified harness behind a base_url [D]. TRL and verl-agent require the loop inside the trainer [D]. verl/slime/ROLL/OpenRLHF need a custom generate or agent function, i.e. a moderate rewrite or an adaptor [D/I].
- **Context compaction (T5).** Long DB episodes need summarization. prime-rl documents exactly what happens: a new sample per compaction break, with explicit `compaction` edges [D]. Other frameworks' behaviour on non-prefix-extending prompts is undocumented in the READMEs I read. Treat it as a risk to test. **[I]**
- **Adaptation cost estimate [I]:**
  - Agent Lightning / rLLM / AReaL: write a DB-env controller (lease, restore, monitor-reward) plus a single-rollout or critic-based advantage. About weeks of work.
  - NeMo Gym: implement a resources server with persistent session state. About weeks.
  - TRL / verl-agent: rewrite the agent inside the trainer. This defeats the "harness is the artifact" goal.

### Gaps
- I did not run any framework. The scores are documentation-based.
- I did not read SkyRL's fully-async page, ROLL's agentic env API, or NeMo Gym's stateful-environment tutorial in full. Their T4 scores could move by one notch.
- Tinker's current pricing and whether full fine-tuning (not just LoRA) is offered were not stated on the page fetched. The cookbook shows LoRA.
- DeepSWE numbers and the AReaL paper ID (2505.24298) remain [PK], not re-verified.
- I found no documented support for censored/timeout reward semantics in any framework.

---

## Q2. Concrete failure scenarios for the target DB environment

### Takeaway
The failures are mostly about the environment lifecycle, not the RL math: group sampling on a singleton environment, stale-token masking over hour-long episodes, retry and timeout semantics, reward leakage and reset fidelity. Each scenario below maps to a harness-side requirement.

### Cited Findings
- Group completion is required before an update — [Agent Lightning async doc](https://github.com/microsoft/agent-lightning/blob/main/docs/35-asynchronous-training.md)
- Tokens beyond staleness 8 are masked, and rollouts are never cancelled — [prime-rl algorithms](https://github.com/PrimeIntellect-ai/prime-rl/blob/main/docs/algorithms.md)
- The gateway pauses requests during weight sync and returns retryable responses — [Agent Lightning async doc](https://github.com/microsoft/agent-lightning/blob/main/docs/35-asynchronous-training.md)
- One environment instance is created per generation — [TRL OpenEnv doc](https://github.com/huggingface/trl/blob/main/docs/source/openenv.md)
- 6–7% timeout-invalid rollouts and corrupted verifier outputs destabilized RL — [KAT-Coder-V2.5](https://arxiv.org/html/2607.05471v1)

### Inferences (scenarios, all [I])
1. **Sibling deadlock / starvation.** GRPO with n=4 on one clone: three siblings finish, and the fourth hits a 4-hour vacuum. Agent Lightning holds the whole group, and carry-over age grows without bound.
2. **Silent diagnosis loss.** A 2-hour episode where the first 90 minutes are diagnosis spans 10 optimizer steps under prime-rl defaults. The diagnosis tokens are masked out, so only the optimization phase is trained, which biases the agent toward skipping diagnosis.
3. **Retry-induced double apply.** During a weight-sync pause the harness's retrying client resends a model call. That is fine. But if the harness also retries *tool* calls on timeout, an `ALTER SYSTEM` or `CREATE INDEX CONCURRENTLY` may run twice. Tool calls must be idempotent or keyed.
4. **Reset infidelity.** A snapshot restore without cache, statistics and autovacuum state control makes later rollouts in a "group" start from different effective states. Group-relative advantages then reward luck.
5. **Prod non-resettability.** On prod there is no reset. Any on-policy RL there is a single-trajectory, irreversible bandit, and must not be mixed into group statistics. It belongs in an off-policy replay buffer tagged with `env_kind=prod` and `resettable=false`.
6. **Reward leakage.** Frameworks compute reward inside the rollout worker's process space (`env.reward` in TRL; reward fn in AReaL/ART). If that worker shares credentials or filesystem with the agent's shell, the agent can read or alter the monitor. The monitor must be a separate service whose result the trainer fetches by `episode_id`.
7. **Delayed reward.** The effect-level monitor may need a post-change soak window, say 30 minutes, before scoring. Frameworks expect reward at episode end. The harness must report an "episode closed, reward pending" state, and the trainer must join late rewards. Only prime-rl/AReaL-style async queues tolerate this, and the bound is still the staleness limit.

### Gaps
- I found no published post-mortem of agentic RL on a stateful, non-containerized resource (DB or VM fleet).

---

## Q3. DB-, SQL- and infra-environment RL examples

### Takeaway
RL environments exist for **SQL generation** (SkyRL-SQL, NeMo Gym BIRD, ART text-to-SQL, Agent Lightning's SQL agent) and, newly, **SRE/RCA** (Cloud-OpsBench as an RL sandbox; SREGym as a live benchmark with RL planned). I found **no** agentic multi-turn RL environment for DB tuning or physical design. Recent tuning papers still put classic RL (TD3/DDPG) under LLM hints.

### Cited Findings
- SkyRL-SQL is a multi-turn RL text-to-SQL pipeline. A 7B model "trained on just 653 samples" is reported to outperform GPT-4o and o4-mini, and skyrl-gym ships SQL envs — [SkyRL README](https://github.com/NovaSky-AI/SkyRL); [SkyRL-SQL blog](https://novasky-ai.notion.site/skyrl-sql)
- NeMo Gym "Bird Sql" env: BIRD dev, 1534 SQLite tasks, with a binary reward from unordered result-set equality — [NeMo Gym README](https://github.com/NVIDIA-NeMo/Gym)
- "Train SQL Data Agent with Multi-Turn RL": a 7B agent probes the DB, refines queries and verifies results across turns on Spider (NeurIPS 2025 workshop) — [NeurIPS virtual](https://neurips.cc/virtual/2025/128018)
- Agent Lightning SQL self-correcting agent — [Medium](https://medium.com/@yugez/training-ai-agents-to-write-and-self-correct-sql-with-reinforcement-learning-571ed31281ad); ART text-to-SQL SFT/distill examples — [ART README](https://github.com/OpenPipe/ART)
- SREGym (May 2026; NeurIPS 2026 poster): a live benchmark with 90 SRE problems on real cloud-native stacks with injected faults. The authors *plan* to make it an RL training ground — [arXiv 2605.07161](https://arxiv.org/abs/2605.07161); [NeurIPS 2026](https://neurips.cc/virtual/2026/poster/139695)
- Cloud-OpsBench is pitched as turning high-risk ops into "a safe low-latency sandbox for training policy optimization agents" and as SFT data — [arXiv 2603.00468](https://arxiv.org/html/2603.00468)
- DB tuning with RL plus LLM hints, not agentic LLM RL:
  - PLRTune (Jun 2026; MySQL 8.0, PG 16) — [arXiv 2606.14312](https://arxiv.org/pdf/2606.14312)
  - DemoTuner — [arXiv 2511.09998](https://arxiv.org/abs/2511.09998v1)
  - L2T-Tune (LHS+TD3) — [arXiv 2511.01602](https://arxiv.org/html/2511.01602v1)

### Inferences
- Every existing SQL RL environment is millisecond-scale and stateless per task: SQLite and read-only queries. They do not exercise the stateful, minutes-to-hours properties of the target design. SREGym/Cloud-OpsBench are closer in lifecycle (fault injection, live stacks) and are the best precedents for reset semantics. **[I]**

### Gaps
- I did not find current 2026 status for ITBench or AIOpsLab RL usage.
- I found no DB knob/index agentic-RL environment, and no DB simulator or world model for LLM RL (consistent with the prior note's Q5).

---

## Q4. Recommendation and harness-side contract

### Takeaway
Do not pick one framework. Make the harness speak the **two contracts the ecosystem has converged on**, and keep the environment lifecycle and reward on the research side:
- an OpenAI-compatible endpoint with token-ID passthrough, so the harness can run behind an Agent Lightning / AReaL / rLLM / NeMo Gym gateway unmodified
- an episode/trajectory record that also serves SFT/DPO/offline RL and Tinker-style loops

Recommended stack:
- **Primary: rLLM or Agent Lightning.** Black-box harness, gateway, K8s/sandbox controller, a verl backend for scale or Tinker for no-idle-GPU economics.
- **Async algorithm: prime-rl or AReaL.** Best-documented staleness and compaction semantics.
- **Environment-server reference: NeMo Gym.** Harness + state + verifier abstraction, harness routing for T9, preemption resume.
- **Algorithm: single-rollout or critic-based** (FlashREINFORCE-style or PPO) rather than GRPO, given one environment.
- **Offline (T7)** via TRL/OpenRLHF/NeMo-RL SFT and DPO on the trace corpus.

### Cited Findings
- Black-box gateway with token IDs: [Agent Lightning](https://github.com/microsoft/agent-lightning); [AReaL tutorial](https://github.com/areal-project/AReaL/blob/main/docs/en/tutorial/agentic_rl.md); [rLLM](https://github.com/rllm-org/rllm); [NeMo Gym](https://github.com/NVIDIA-NeMo/Gym)
- rLLM trace schema: Episode → Trajectories → Steps (one LLM call each, with token IDs + logprobs) — [rLLM README](https://github.com/rllm-org/rllm)
- prime-rl trace semantics: per-step records, extension property, `subagent_call` / `compaction` edges, per-token policy version — [prime-rl algorithms](https://github.com/PrimeIntellect-ai/prime-rl/blob/main/docs/algorithms.md)
- Single-rollout async RL — [OpenRLHF FlashREINFORCE](https://github.com/OpenRLHF/OpenRLHF)
- No billing for idle time — [Tinker](https://thinkingmachines.ai/tinker/); Tinker API available on own hardware via SkyRL-tx — [SkyRL](https://github.com/NovaSky-AI/SkyRL)
- Harness-variant training gains (Harness Scaling, 18 configs) — [arXiv 2610.29458](https://arxiv.org/html/2610.29458v1)

### Inferences: what the harness must expose [I]
1. **Model I/O:**
   - All model calls go through one configurable `base_url`, so no direct SDK calls bypass it.
   - Native support for `/generate`-style token-in/token-out or returned token IDs + logprobs, recording the tokenizer and chat-template hash.
   - Retrying model client (survives weight-sync pauses).
2. **Rollout API:**
   - `run_episode(task_spec, harness_variant_cfg, policy_endpoint, budget{wall,$}, env_lease) → episode_id`. It is asynchronous and resumable, and supports `cancel(episode_id)` and `status(episode_id)`.
   - The trainer never calls into DB state directly.
3. **Environment lifecycle (owned by the research side, not the trainer):**
   - `acquire_lease(env_pool, exclusive=True)`, `restore(snapshot_id)`, `snapshot()`, `release()`.
   - Declared `resettable: bool`, `fidelity_tier`, and a cache-state descriptor.
   - The pool size is what bounds concurrency, not GPU count.
4. **Trace schema** (superset of rLLM Episode/Trajectory/Step and prime-rl steps):
   - Per step: `policy_version`, prompt/completion token IDs, logprobs, a loss mask (tool output = 0), and edges for `compaction`, `subagent_call` and `continuation`.
   - Per tool call: command, idempotency key, exit status, wall time and $ cost.
   - Per episode: phase markers (diagnose / optimize / report), `harness_variant_id` (config hash), `env_kind` (prod/clone), and `terminal_status ∈ {completed, budget_exhausted, preempted, harness_error, env_error, rolled_back}`.
5. **Reward channel:**
   - The monitor service writes `reward(episode_id) = {components…, provenance, confidence/variance, available_at}` asynchronously, and may write it late.
   - The trainer joins rewards by ID. Censored episodes carry `reward=None` + status, never 0.
   - The monitor is unreachable from the agent's credentials.
6. **Harness-as-parameters:** prompt, tool schema, observation format, context policy and workflow are selectable per episode (T9). Task-level harness routing as in NeMo Gym is the target.
7. **Offline export:** the same traces export to SFT (successful episodes), DPO (pairs from the same snapshot), and replay buffers for off-policy RL, including non-resettable prod episodes as single-sample data.

### Gaps
- None of the frameworks has been shown to handle hour-long, singleton-environment episodes. The recommendation rests on documented interfaces, not reported runs.
- Whether single-rollout estimators are stable at 10²–10³ episodes is unverified for agentic tasks of this length.
