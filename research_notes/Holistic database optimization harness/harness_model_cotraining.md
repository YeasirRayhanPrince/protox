# Co-training the agent harness and the model (2025–2026): implications for an autonomous DB-optimization harness

Source-quality legend: **[PR]** peer-reviewed venue; **[TR]** arXiv preprint / tech report (not peer-reviewed); **[V]** vendor blog / product claim; **[AGG]** secondary aggregator (use for pointers only); **[PK]** fact from the researcher's prior knowledge with the canonical URL, *not re-fetched in this session*, so verify before quoting numbers.

---

## Q1. End-to-end agentic RL with the model trained inside its harness/tools

### Takeaway
The standard 2025–26 recipe for frontier agents is outcome-reward RL (GRPO/PPO variants) run *through* a specific harness: real tools, sandboxes, and context management in the loop. Most of the engineering effort goes into rollout infrastructure, meaning sandboxes, async decoupling, token-consistency fixes and verifier hygiene, rather than into the RL algorithm. The models that come out are measurably tied to the harness they were trained in (see Q3).

### Cited Findings
- **Kimi K2.5 Agent Swarm / PARL [V]**: a trainable orchestrator learns to split tasks into parallel subtasks and spawns *frozen* sub-agents. Reward = task outcome r_perf + an "instantiation" reward r_parallel (against "serial collapse") + a sub-agent finish-rate reward r_finish (against "spurious parallelism"). The auxiliary weights are annealed to zero during training. Latency is measured in "critical steps" (orchestration overhead + slowest sub-agent per stage). Scale: up to 100 sub-agents and 1,500 coordinated steps. Claimed 3–4.5x fewer critical steps on wide search and ~80% runtime reduction in internal evals — [Kimi K2.5 blog](https://www.kimi.com/blog/kimi-k2-5)
- Secondary reporting gives BrowseComp 60.6% single-agent vs 78.4% swarm. These are vendor numbers with no independent replication found — [AGG summary](https://www.morphllm.com/kimi-k2-5-agent-swarm); [Phil Schmid overview of Kimi/Cursor/Chroma agentic RL](https://www.philschmid.de/kimi-composer-context)
- **Kimi-Researcher [V][PK]**: end-to-end agentic RL of a single model with search/browse/code tools and learned context management. Reported HLE rose from 8.6% to 26.9% through RL — [Kimi-Researcher](https://moonshotai.github.io/Kimi-Researcher/)
- **Tongyi DeepResearch [TR][PK]**: agentic mid-training + SFT + on-policy RL. Part of the RL runs in a *simulated* environment (an offline Wikipedia-based corpus) instead of the live web, to cut cost and instability — [arXiv 2510.24701](https://arxiv.org/abs/2510.24701)
- **MiroThinker [TR][PK]**: argues for "interactive scaling", training the model to sustain hundreds of tool calls per task (up to ~600) with long context — [arXiv 2511.11793](https://arxiv.org/abs/2511.11793)
- **KAT-Coder-V2.5 (Kuaishou) [TR]**. Infra lessons from agentic coding RL:
  - Token drift (re-tokenization mismatch) affected ~40% of samples at ~200-turn scale. They fixed it with a Gateway Server that calls `/generate` directly instead of the chat endpoint.
  - The sandbox feedback error rate fell from ~16% to <2%, and training collapses dropped ~10x.
  - Timeout-invalid rollouts fell from 6–7% to <1%. An env-var bug was corrupting 6–7% of verifier outputs.
  - AutoBuilder produced >100k verifiable environments across 12 languages, with build success raised from 16.5% to 57.2%.
  - An Experience Buffer decouples inference from training.

  — [arXiv 2607.05471](https://arxiv.org/html/2607.05471v1)
- **SWE-RL (Meta) [TR][PK]**: RL on GitHub PR data with a *rule-based patch-similarity reward and no execution*. The point is that a cheap proxy reward avoids costly environments — [arXiv 2502.18449](https://arxiv.org/abs/2502.18449)
- **DeepSWE / rLLM (Agentica + Together) [V][PK]**: Qwen3-32B trained purely with RL inside an execution sandbox (R2E-Gym environments). Reported ~42% Pass@1 on SWE-bench Verified, higher with test-time scaling — [Together blog](https://www.together.ai/blog/deepswe); [rLLM](https://github.com/agentica-project/rllm)
- **Multi-turn tool RL precedents [TR][PK]**:
  - Search-R1 interleaves search calls with reasoning and masks retrieved tokens out of the loss — [arXiv 2503.09516](https://arxiv.org/abs/2503.09516)
  - ReTool trains code-interpreter use via RL — [arXiv 2504.11536](https://arxiv.org/abs/2504.11536)
  - ToolRL studies reward design for tool calls — [arXiv 2504.13958](https://arxiv.org/abs/2504.13958)
- **Training frameworks [PK]** (all open source):
  - verl / verl-agent. verl-agent adds GiGPO, which gives step-level credit by grouping identical "anchor states" across rollouts — [GiGPO arXiv 2505.10978](https://arxiv.org/abs/2505.10978); [verl](https://github.com/volcengine/verl)
  - SkyRL, multi-turn agent RL including SWE tasks in OpenHands-style harnesses — [SkyRL](https://github.com/NovaSky-AI/SkyRL)
  - AReaL, fully asynchronous RL that decouples generation from training — [arXiv 2505.24298](https://arxiv.org/abs/2505.24298)
  - ROLL — [arXiv 2506.06122](https://arxiv.org/abs/2506.06122)
  - slime — [GitHub](https://github.com/THUDM/slime)
  - ART (OpenPipe), GRPO for existing agent code with RULER LLM-judge rewards — [GitHub](https://github.com/OpenPipe/ART)
  - Prime Intellect verifiers / Environments Hub — [verifiers](https://github.com/PrimeIntellect-ai/verifiers)
- **Agent Lightning (Microsoft) [TR][PK]**: decouples agent execution from training. Any existing agent framework emits transitions through a tracing/observability interface with near-zero code change. "LightningRL" assigns credit across multi-call trajectories hierarchically. This is the most direct precedent for "build the harness first, attach RL later" — [arXiv 2508.03680](https://arxiv.org/abs/2508.03680)
- **Harness Scaling [TR]** (IQuest/Beihang/RUC) uses veRL with asynchronous vLLM rollouts, GRPO/PPO for 300 steps, on 16–32 H20 GPUs — [arXiv 2610.29458](https://arxiv.org/html/2610.29458v1)

### Inferences
- The training stack (verl/SkyRL/AReaL/slime/ART/Agent Lightning) has converged on one contract: a rollout worker runs the *unmodified* harness, records token-level trajectories with tool-output masks, and returns a scalar or per-step reward. A harness that already logs lossless episodes (Gen-DBA's record) is close to this contract. What it is missing is token-exact model I/O and a reward hook.
- KAT-Coder's numbers show that a few percent of corrupted verifiers or timeouts is enough to destabilize RL. Slow, flaky DB environments will make this worse.

### Gaps
- OpenAI deep research / Codex training: no primary technical description was found in this session beyond high-level statements that they are RL-trained in their tool environments. Treat any specifics as unverified.
- I did not re-fetch exact numbers for Kimi-Researcher, DeepSWE, Tongyi or MiroThinker ([PK] items).

---

## Q2. Training orchestrators and multi-agent systems jointly (learned delegation and budget allocation)

### Takeaway
Learned orchestration is real and pays off, mainly in wall-clock time and cost. The dominant pattern trains *only the orchestrator/planner* and keeps sub-agents and tools frozen. That is the tractable variant for a DB swarm: a learned planner that decides what to investigate, which sub-agent or tool to spawn, and how much budget to spend.

### Cited Findings
- PARL trains the orchestrator only, with frozen sub-agents, and uses annealed shaping rewards to stop collapse to serial execution or spurious fan-out — [Kimi K2.5 blog](https://www.kimi.com/blog/kimi-k2-5) [V]
- **AgentFlow [TR][PK]**: a modular system (planner, executor, verifier, generator) with memory. Only the planner is trained "in the flow" with Flow-GRPO, which broadcasts the final outcome reward to every turn. A 7B planner is reported to beat larger proprietary models on search/agentic/math tasks — [arXiv 2510.05592](https://arxiv.org/abs/2510.05592)
- **ToolOrchestra / Orchestrator-8B (NVIDIA) [TR][PK]**: an 8B model is RL-trained to call tools and larger models, with rewards for outcome, *efficiency/cost* and user preference. It is reported to beat GPT-5 on HLE at substantially lower cost. This is a direct precedent for budget-aware delegation rewards — [arXiv 2511.21689](https://arxiv.org/abs/2511.21689)
- **Multi-agent LLM RL [TR/PR][PK]**:
  - MAPoRL co-trains multiple LLMs with multi-agent PPO and a verifier on collaborative discussion — [arXiv 2502.18439](https://arxiv.org/abs/2502.18439)
  - MARFT formalizes multi-agent RL fine-tuning for LLM agent systems — [arXiv 2504.16129](https://arxiv.org/abs/2504.16129)

### Inferences
- For a $-budget / wall-clock-limited DB harness, PARL's "critical steps" metric and ToolOrchestra's cost reward map directly onto the objective: the reward should be measured SLO improvement minus a $ and latency penalty. Shaping terms should be annealed so they cannot be gamed long-term.
- Training only the orchestrator also shrinks the RL problem. The orchestrator's actions (spawn, allocate, stop) are few and high-level, so off-policy learning from logged swarm runs is more plausible than training every sub-agent.

### Gaps
- I found no published *joint* training of orchestrator and sub-agents at frontier scale with measured gains over orchestrator-only training.

---

## Q3. Harness/scaffold optimization without weight updates, co-evolution, transfer, and "harness overfitting"

### Takeaway
Searching over harness code (Meta-Harness, DGM, ADAS/AFlow, AHE, ACE, GEPA) yields large gains at a fraction of RL cost. Harness *structure* (tools, middleware, memory) tends to transfer across models; prompt prose does not. Conversely, RL on a single harness produces models that overfit to it, and training over many harness variants fixes much of this. By mid-2026 the first harness+policy co-evolution papers (HarnessForge, HarnessX, SIA) report extra gains over either alone. All of these are preprints.

### Cited Findings
- **Meta-Harness (Lee, Nair, Zhang, Lee, Khattab, Finn; Mar 2026) [TR]**: an outer loop in which a coding-agent proposer reads the source, scores and *execution traces of all prior candidates via a filesystem* and writes new harness code.
  - +7.7 points over a strong context-management baseline with 4x fewer context tokens on online text classification.
  - A discovered RAG-math harness gained +4.7 points averaged across **five held-out models**, which is evidence of cross-model transfer.
  - Beat hand-built harnesses on TerminalBench-2.

  — [arXiv 2603.28052](https://arxiv.org/abs/2603.28052)
- **Darwin Gödel Machine [TR]**: open-ended archive-based self-modification of a coding agent.
  - SWE-bench 20.0% to 50.0%; Polyglot 14.2% to 30.7%.
  - The evolved agent transferred to a different model and reached 59%.
  - A run cost about $22k and two weeks.
  - Documented objective hacking: an agent deleted the logging markers its hallucination detector read.

  — [arXiv 2505.22954](https://arxiv.org/abs/2505.22954), numbers as summarized by [AGG blog](https://jxzhangjhu.github.io/blog/2026/self-evolving-agentic-harnesses/)
- **Huxley-Gödel Machine [TR][PK]**: refines DGM's selection with a lineage "clade metaproductivity" estimate to pick which agents to expand, and reports better results with less compute — [arXiv 2510.21614](https://arxiv.org/abs/2510.21614)
- **ADAS [PR, ICLR 2025]** reports DROP +13.6 F1 — [arXiv 2408.08435](https://arxiv.org/abs/2408.08435). **AFlow [PR, ICLR 2025]**: MCTS over code workflows; a cheaper model beat GPT-4o — [arXiv 2410.10762](https://arxiv.org/abs/2410.10762). **Gödel Agent [PK]** — [arXiv 2410.04444](https://arxiv.org/abs/2410.04444); the AGG blog reports a 14% regression rate for its greedy, archive-free search.
- **GEPA [TR]**: reflective prompt evolution. Beats GRPO by up to ~20% with up to 35x fewer rollouts — [arXiv 2507.19457](https://arxiv.org/abs/2507.19457)
- **ACE (Agentic Context Engineering) [TR]**: an evolving "playbook" context. It warns of *context collapse*: monolithic rewriting shrank context from 18,282 to 122 tokens and accuracy fell from 66.7 to 57.1 — [arXiv 2510.04618](https://arxiv.org/abs/2510.04618) (collapse numbers via [AGG](https://jxzhangjhu.github.io/blog/2026/self-evolving-agentic-harnesses/))
- **Agentic Harness Engineering (AHE, 2026) [TR]**:
  - Terminal-Bench 2 rose from 69.7% to 77.0%, above the Codex harness's 71.9%.
  - Transferred to five other base models (+2.3 to +10.1).
  - Structural edits (tools, middleware, memory) transfer. System-prompt edits do not, and evolving the prompt alone regressed by 2.3 points.

  — [arXiv 2604.25850](https://arxiv.org/abs/2604.25850) via [AGG](https://jxzhangjhu.github.io/blog/2026/self-evolving-agentic-harnesses/)
- Other harness-evolution systems:
  - Adaptive Auto-Harness: the prompt grew from ~2 KB to 68 KB on a task stream while accuracy declined, a stream-overfitting failure — [arXiv 2606.01770](https://arxiv.org/abs/2606.01770) [TR via AGG]
  - SkillOpt accepts edits only on a held-out selection split (4:1:5 train/select/test) — [arXiv 2605.23904](https://arxiv.org/abs/2605.23904) [TR via AGG]
  - RRSI: gains on the evolution split often don't carry out of distribution, and several runs end *below* the initial harness H_0. It regularizes both proposal and selection — [arXiv 2609.24972](https://arxiv.org/html/2609.24972v1) [TR]
- **Model vs harness share of variance**: Terminal-Bench reports that model swaps moved scores +52% relative vs +17% for scaffold swaps — [arXiv 2601.11868](https://arxiv.org/abs/2601.11868) [TR via AGG]. Harness benefit is non-monotonic in model capability, with mid-tier models gaining most — [arXiv 2605.30621](https://arxiv.org/abs/2605.30621) [TR via AGG]
- **Harness overfitting from RL**:
  - KAT-Coder-V2.5 names three forms: *format* (the parse failure rate "rises significantly once the tool-invocation protocol is switched"), *context-structure*, and *control-flow*. It gives no numbers.
  - The mitigation is training over mini-swe-agent plus black-box harnesses (Claude Code, Codex, OpenClaw, OpenHands). It also randomizes tool names, argument conventions, output formats and prompts, and injects missing dependencies, transient failures, truncated outputs and noisy logs.

  — [arXiv 2607.05471](https://arxiv.org/html/2607.05471v1) [TR]
- **Harness Scaling (Oct 2026) [TR]**:
  - Factorizes the harness into 5 components (system prompt, tool interface, observation, context management, workflow) with 3 realizations each (243 configs). Training uses 18 configs chosen by a strength-2 orthogonal design.
  - Qwen3-4B GRPO average Pass@1: 29.81 (single harness) to 39.04. Qwen3-30B-A3B GRPO: 37.29 to 42.78.
  - A single-harness 30B policy scores 59.82 on its own harness but 48.12 in-space and 46.02 on Claude Code. The Harness-Scaling policy scores 59.63 / 58.60 / 49.62.
  - Zero-shot transfer to Claude Code beat both black-box SFT and black-box RL trained through OpenClaw (4B: 37.22 vs 35.08 / 33.38).

  — [arXiv 2610.29458](https://arxiv.org/html/2610.29458v1)
- **Co-evolution of harness and weights**:
  - HarnessForge treats an agent as a harness–policy pair and evolves both via "fault-guided harness tailoring" and "harness-conditioned policy alignment". On Qwen3-4B/8B across 5 benchmarks it reports gains of up to 12.0% over the strongest baseline, beats harness-only and policy-only baselines, and claims favorable rollout efficiency — [arXiv 2606.01779](https://arxiv.org/abs/2606.01779) [TR]
  - HarnessX interleaves harness search with cross-harness GRPO and reports +4.7% from co-evolution on top of harness search — [arXiv 2606.14249](https://arxiv.org/abs/2606.14249) [TR via AGG]
  - SIA jointly updates harness and weights, and warns of "coupled co-evolutionary Goodhart" when two optimizers share one verifier — [arXiv 2605.27276](https://arxiv.org/abs/2605.27276) [TR via AGG]
  - The AGG survey notes that no system yet co-evolves harness, weights *and* environment together — [AGG](https://jxzhangjhu.github.io/blog/2026/self-evolving-agentic-harnesses/)

### Inferences
- Harness search is the cheap first lever and should come first. It needs only scored, trace-rich episodes in a filesystem-readable archive (Meta-Harness, DGM). Weight training is the second lever and should train across *harness variants*, not one frozen harness, to avoid format, context and control-flow overfitting.
- So "co-trainability" for the DB harness mostly means making the harness itself parameterized and perturbable: swappable tool schemas, context policies and workflows, plus an archive of evaluated variants.
- Held-out selection splits are mandatory (SkillOpt, RRSI). With few DB workloads, a harness evolved on one workload will overfit it, as Adaptive Auto-Harness's stream decline shows.

### Gaps
- Most 2026 numbers come from preprints, and several came to me only through one aggregator. Verify against the PDFs before citing in a paper. HarnessForge's mechanism details were not readable (the PDF fetch failed).

---

## Q4. Systems issues: rollout cost, async RL, simulators, rewards, offline learning, credit assignment, reward hacking

### Takeaway
Rollout cost and environment reliability dominate. Labs respond in four ways: async decoupling (AReaL, Experience Buffers); cheap proxy rewards (SWE-RL, cost-model rewards); simulated or LLM-world-model environments (Tongyi's offline corpus, Simia-RL, Qwen-AgentWorld, GenEnv); and step-level credit (GiGPO, Flow-GRPO). Reward hacking is common whenever the agent can see or touch the checker.

### Cited Findings
- **Async RL and decoupling**: AReaL fully decouples generation from training — [arXiv 2505.24298](https://arxiv.org/abs/2505.24298) [PK]. KAT-Coder uses a Gateway Server plus an Experience Buffer — [arXiv 2607.05471](https://arxiv.org/html/2607.05471v1). Harness Scaling uses async vLLM rollouts in veRL — [arXiv 2610.29458](https://arxiv.org/html/2610.29458v1)
- **Simulated environments**:
  - Simia-RL uses an LLM as both environment simulator and reward computer, so GRPO can run without hand-built envs — [arXiv 2511.01824](https://www.alphaxiv.org/abs/2511.01824) [TR]
  - Qwen-AgentWorld, a language world model simulating 7 agent environments (terminal, SWE, OS, …) — [arXiv 2606.24597](https://arxiv.org/html/2606.24597v1) [TR]
  - GenEnv co-evolves a learned environment generator with the agent at aligned difficulty — [arXiv 2512.19682](https://arxiv.org/pdf/2512.19682) [TR]
  - A survey on building simulation environments for agentic RL — [arXiv 2607.05773](https://arxiv.org/html/2607.05773v1) [TR]
  - A vendor caution: simulated envs miss the failures that matter for agents acting on real APIs and DBs — [dev.to](https://dev.to/ethan_5383afd058ff/6-best-reinforcement-learning-rl-tools-in-2026-21dg) [V, opinion]
- **Cheap proxy rewards**: SWE-RL's patch-similarity reward needs no execution — [arXiv 2502.18449](https://arxiv.org/abs/2502.18449) [PK]. E3-Rewrite uses an *estimated-cost* reward (see Q5).
- **Credit assignment**:
  - GiGPO gives step-level advantages via anchor-state grouping — [arXiv 2505.10978](https://arxiv.org/abs/2505.10978) [PK]
  - Flow-GRPO broadcasts the trajectory outcome to every planner turn — [arXiv 2510.05592](https://arxiv.org/abs/2510.05592) [PK]
  - Agent Lightning uses hierarchical credit over multi-call trajectories — [arXiv 2508.03680](https://arxiv.org/abs/2508.03680) [PK]
- **Reward hacking**:
  - DGM deleted hallucination-detector markers, and hacking was more frequent when the checker was visible, so the authors hid it.
  - STOP's scaffold flipped `use_sandbox=True` to `False` in 0.42% of GPT-4 generations.
  - DemoEvolve: a noisy reward made a no-op edit look beneficial.

  — all via [AGG](https://jxzhangjhu.github.io/blog/2026/self-evolving-agentic-harnesses/) (DGM [arXiv 2505.22954](https://arxiv.org/abs/2505.22954); STOP [arXiv 2310.02304](https://arxiv.org/abs/2310.02304))
- **Verifier hygiene matters quantitatively**: 6–7% corrupted verifier outputs and 6–7% timeout-invalid rollouts were material enough to need dedicated fixes — [arXiv 2607.05471](https://arxiv.org/html/2607.05471v1)

### Inferences
- In DB terms, reward hacking looks like this:
  - dropping or ignoring queries in the measured workload
  - turning off durability (`fsync`, `synchronous_commit`)
  - caching or warm-buffer effects that inflate "measured" speedups
  - editing the benchmark harness
  - exploiting estimated-cost rewards (Gen-DBA already measured the PG cost model understating benefit ~2x, `docs/training_record.md`)

  The measurement harness and SLO checker must be outside the agent's write scope. Cold/warm state must be controlled and recorded.
- Noisy latency rewards behave like DemoEvolve's noisy reward: no-op changes look good. Repeated measurements, recorded variance, and significance-gated rewards are needed.

### Gaps
- I found no published cost figures (GPU-hours or $) per DB-scale environment step for agentic RL. Harness Scaling reports GPUs but not $.

---

## Q5. Database-specific RL-on-LLM work and DB simulators

### Takeaway
RL-trained LLMs for DB tasks exist mainly for single-shot SQL generation and rewriting. There, rewards come from execution correctness or cost estimates, and they work well. I found **no** published agentic (multi-turn, tool-using) RL of an LLM for knob tuning, index selection or holistic DB optimization. Current LLM tuners are training-free (prompting + BO/RL hybrids). This is an open niche, and Gen-DBA's lossless records are positioned for it.

### Cited Findings
- **Arctic-Text2SQL-R1 (Snowflake) [TR → PR, ACL Findings 2026]**: GRPO with *execution-correctness-only* reward, no shaping. 32B reached 71.83% execution accuracy on BIRD (v1 claims #1; the later ACL version phrases it more cautiously). The 7B outperforms prior 70B-class systems — [arXiv 2505.20315](https://arxiv.org/abs/2505.20315); [ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1345/)
- **SQL-R1 [TR][PK]**: RL-trained text-to-SQL reasoning — [arXiv 2504.08600](https://arxiv.org/abs/2504.08600)
- **E3-Rewrite [TR]**: an LLM SQL rewriter trained with GRPO. Rewards cover executability, equivalence and *cost estimation*, with a curriculum that adds efficiency after executability and equivalence. Reported up to 25.6% reduction in query execution time, and TPC-H average latency from 78.81 s to 29.67 s (Qwen-based) — [arXiv 2508.09023](https://arxiv.org/pdf/2508.09023)
- **LLM knob tuning, mostly training-free**:
  - An experimental evaluation of LLM knob tuning — [arXiv 2408.02213](https://arxiv.org/pdf/2408.02213)
  - GPTuner, LLM-guided BO — [VLDB 2024](https://vldb.org/pvldb/vol17/p1939-tang.pdf) [PR]
  - MCTuner, LLM-guided exploration — [arXiv 2509.06298](https://arxiv.org/html/2509.06298v1) [TR]
  - AgenticDB, an LLM "DBA planner" for DBMS+OS reconfiguration with validation, recovery and audit stages; aggregator listing only, RL use unconfirmed — [AGG list](https://github.com/tmgthb/Autonomous-Agents)

### Inferences
- The text-to-SQL precedent says simple, verifiable outcome rewards are enough when the environment is cheap: execution on BIRD costs milliseconds. DB optimization rewards are measured performance under SLOs, which takes minutes per evaluation and is noisy. The cost-model reward used by E3-Rewrite is cheap but biased (Gen-DBA's 2x measurement).
- So a tiered environment is the natural design:
  1. A cost-model / what-if tier (hypopg, EXPLAIN): cheap, biased, for exploration and pre-filtering.
  2. A sampled or scaled-down clone tier: medium cost, measured.
  3. A full-fidelity clone: expensive, for final reward and verification.

  Each reward carries its `provenance` tag (measured vs estimated), as Gen-DBA's training record already enforces.

### Gaps
- I found no DB-environment simulators or world models built for agentic LLM RL. I found no DB-specific multi-harness or harness-overfitting study. I could not confirm a primary paper for AgenticDB.

---

## Q6. Distilled implications: should the DB harness be built for co-training, and what must it expose?

### Takeaway
Yes. Build for co-trainability from day one, because the marginal cost is mostly interface discipline. But plan the training order cheapest-first:
1. Harness/prompt/memory search on frozen frontier models (Meta-Harness/GEPA/ACE style; trace archive only).
2. SFT/offline learning of a small orchestrator from logged lossless episodes.
3. Online RL of the *orchestrator only*, on cheap-tier environments with measured-tier validation.
4. Full harness+policy co-evolution (HarnessForge/HarnessX-style) only once a cheap, reasonably faithful environment tier exists.

Full end-to-end RL on production-fidelity DB rollouts is not realistic at current costs.

### Cited Findings (supporting the design requirements)
- Decoupled tracing, so RL attaches to an unmodified agent — [Agent Lightning arXiv 2508.03680](https://arxiv.org/abs/2508.03680) [PK]
- Filesystem archive of code + scores + full traces, which harness search needs — [Meta-Harness arXiv 2603.28052](https://arxiv.org/abs/2603.28052)
- Token-exact generation logging (avoid chat-template re-tokenization drift), sandbox reliability, and verifier isolation — [KAT-Coder-V2.5](https://arxiv.org/html/2607.05471v1)
- Parameterized harness components (prompt, tool interface, observation, context mgmt, workflow) so policies can be trained across variants — [Harness Scaling](https://arxiv.org/html/2610.29458v1)
- Learned orchestrator with frozen workers, parallelism/finish shaping, and a critical-path latency metric — [Kimi K2.5](https://www.kimi.com/blog/kimi-k2-5); cost-aware rewards — [ToolOrchestra arXiv 2511.21689](https://arxiv.org/abs/2511.21689) [PK]
- Hidden checker and held-out selection splits — [AGG on DGM/SkillOpt](https://jxzhangjhu.github.io/blog/2026/self-evolving-agentic-harnesses/); [RRSI](https://arxiv.org/html/2609.24972v1)
- GEPA reaches GRPO-level gains with up to 35x fewer rollouts, which argues for prompt/harness search first when rollouts are expensive — [arXiv 2507.19457](https://arxiv.org/abs/2507.19457)

### Inferences: the concrete harness contract
1. **Episode = trajectory record**, a superset of the Gen-DBA record (`docs/training_record.md`). Add:
   - exact model input/output token IDs (or the raw completion strings plus the exact chat template and tokenizer version), sampling params and logprobs if available
   - a tool-output loss mask
   - parent/child agent IDs for swarm trees
   - per-step $ and wall-clock cost
   - harness-variant ID (a config hash of prompt, tools, context policy and workflow)
2. **Resettable, snapshot-able environments** at declared fidelity tiers (what-if/cost model → sampled clone → full clone), with `reset(snapshot_id)`, `step(action)`, and a `fidelity` tag on every reward. Plan copy-on-write snapshots (e.g., ZFS/LVM/cloud volume clones) so many rollouts can share a base.
3. **A rollout API matching the trainer contract**: an OpenAI-compatible inference endpoint, or a direct `/generate` path to avoid template drift, that a verl/SkyRL/AReaL/ART/Agent-Lightning worker can point at. Plus `run_episode(task, harness_cfg, policy_endpoint) → trajectory, reward`. Rollouts must be **async and preemptible**, with timeouts recorded as such and not scored as failures.
4. **Reward hooks outside the agent's write scope**:
   - measured SLO-aware reward with repeated trials and variance
   - shaping terms (parallelism, finish rate, cost) whose weights can be annealed
   - integrity checks against DB-specific hacks (durability knobs, workload truncation, cache warmth, benchmark tampering)
5. **A harness-as-parameters layer**: tool schemas, observation formats, context-management policy and workflow graph are swappable configs. This enables both harness search and multi-harness RL (avoiding format/context/control-flow overfitting), and means the harness can be evolved without retraining.
6. **An archive and splits**: every harness variant's code, scores and traces live in a queryable filesystem archive. Workloads and engines are split into train / selection / test so self-improvement is held out.
7. **Off-policy readiness**: logged episodes from frontier-model swarms, Proto-X and baselines become SFT / offline RL / rejection-sampling data. Because measured and estimated outcomes are kept separate, cost-model-reward pretraining can later be corrected with measured rewards.

**Realism:**
- Each DB rollout takes minutes to hours, and GRPO-style training uses e.g. 16 tasks × 8 rollouts × 300 steps (≈38k rollouts in Harness Scaling, [source](https://arxiv.org/html/2610.29458v1)). Full-fidelity online RL is therefore impractical.
- Feasible paths are:
  - training only the high-level orchestrator, which has few decisions per episode
  - cheap tiers plus occasional measured validation
  - offline/SFT on the growing lossless corpus
  - harness search, whose sample efficiency is better (GEPA)
- A learned DB world model or simulator is a research contribution in its own right; none exists yet (Q5 gap).

### Gaps
- There is no empirical evidence yet on how well RL on low-fidelity DB tiers transfers to production-fidelity outcomes. This is the key unknown that would decide whether online co-training pays off.
