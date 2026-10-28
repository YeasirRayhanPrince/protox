# Design log: zero-regression autonomous DB optimization harness

The living record of the problem and of decisions made with the user. Read this first in a new session.
Newest decisions go into the relevant section; dated so they can be traced. "User" = the researcher;
"open" = not decided yet, do not treat as settled.

## 1. Problem (decided)

- **Goal:** an LLM-centred agent harness that optimizes a data system holistically and engine-agnostically
  (lakehouses included). The harness is the research artifact; the model is swappable.
- **Autonomous, no human in the loop.** DB role / credentials are the only hard boundary. No guardrails are
  given: the agent infers its own action space and risk envelope. We still need our own monitor and
  guardrails against reward hacking.
- **One fixed environment:** prod OR clone, never both, no clone→prod promotion, no branching on the live system.
- **Budget:** wall-clock hours + dollars covering everything (tokens, compute, infra). Objective: performance under SLOs.
- **Workload unknown:** the agent sees only what runs during its observation window, plus history that may or may not exist.
- **Zero regression:** no try-fail-revert on the live system. Every commit carries a certificate checked by an
  outside verifier V (C1 semantic safety, C2 no regression on seen/unseen queries, C3 net benefit).
  Inspiration: Oracle invisible indexes + SPM; JetStream (arXiv 2610.20527, Verus proofs against a frozen spec;
  proves correctness, not performance).
- **Diagnosis first and anytime:** 10 min ⇒ triage; unbounded ⇒ deep diagnosis + long-horizon changes.
- **Modes:** one-shot or continuous/cron (cron liked).
- **Joint, not sequential, optimization** (2026-10-27): "Joint optimization is the way to go." Proto-X is the
  only prior system that searches the joint space (knobs + indexes + hints); UDO, UniTune, EvoTune, AgenticDB
  are sequential/staged/alternating; λ-Tune proposes whole configs but does no iterative search.
  Counterpoint to prepare for: EvoTune reaches its target 2.1× faster than Proto-X on TPC-H by staging.
  Framing: joint is needed for correctness under interactions; making it affordable is the open problem;
  the certificate must cover the joint change.
- **Naming clash:** in `docs/cidr27_gendba.md` SLO = Storage Layout Optimization; here SLO = Service Level Objective.
- **Banked for later:** system side (how many threads/agents to spawn).

## 2. Phases

- **Phase 1, training:** varied settings ξ = (E, B, T, R, W, D, H); branching, resets, trial and error allowed;
  a regression is a training signal. Tool usage (which shell/psql commands) is learned here.
- **Phase 2, deployment:** weights frozen; one live system; zero regression; improves only in context via an
  RSI loop that **updates its own harness** (tools, prompts, skills, strategies) plus memory.
  Exo-style split: mutable layer m = harness + memory; immutable layer I = weights, verifier, gate, ledger,
  log, monitor, credentials. Memory is evidence, never permission.
- **Open (2026-10-27): what does Phase 1 train?**
  A model only (rejected by the argument below) · B harness only, frozen model · C both, alternating ·
  D both jointly with the Phase-2 edit loop running inside training.
  Argument: Phase 2 edits the harness, so Phase 1 must train with harness edits happening, else deployment is
  out of distribution. Tension: D makes trained weights part of the contribution, against "model is swappable".
  Recommendation given: D as the system, B as the baseline. User has not chosen.
- **Open:** do Phase-2 harness edits need their own certificate? (DGM deleted its own checks.)

## 3. The loops (2026-10-28)

User's view: this is the same as RSI / ADRS / coding agents / autoresearch, especially diagnosis. Five loops:

| Loop | Repeats | Analogue | Free failure? |
|---|---|---|---|
| 1 Diagnosis | hypothesis → probe → evidence | autoresearch, coding-agent debugging | yes, within probe load ε |
| 2 Option search | candidate → offline evaluation | ADRS / evolve-and-evaluate | yes, approximate evaluator |
| 3 Commit | prove → commit once → watch | none (our difference) | **no** |
| 4 RSI | rewrite harness + memory | DGM, Exo | open |
| 5 Training | episodes → weights | agent RL | yes |

Those systems have a ground-truth evaluator and free failure; we have that only in loops 1, 2, 5.
The hard hand-off is 2 → 3: an approximate evaluator must yield a certificate strong enough to commit without trial.

## 4. The two most important questions (user, 2026-10-28)

1. **How do we know we are missing a diagnosis?**
2. **How do we know option 1 is better than option 2** without trying them on the live system?

### Diagnosis design (decided, 2026-10-28)

- **A fixed, sufficient core** of observations: the answer must be derivable even if the agent does only these.
  Backbone is time accounting ("where does the time go": per query class, wait event, resource), plus workload
  mix and current state (config, indexes, stats freshness). Because the core closes the account, the
  unexplained remainder is the deployment-time "missed something" signal.
- **An open loop** on top, budget-bounded, for further probes and emergent diagnoses.
- **Cross-reference only in training** (injected faults, second diagnoser, branches); none in deployment.
  Training also tests sufficiency of the core: for each case, is the right diagnosis derivable from the core alone?
- Implications raised (not yet confirmed by user): the core belongs in the immutable layer (agent may add
  observations, never remove core ones); the core is defined by questions with per-engine adapters; it must
  fit the smallest budget (10-min triage) within ε; when it cannot be collected (no history, no statement
  stats) we hit the extension question below.
- **Next step:** write a candidate core and test sufficiency against known failure cases
  (e.g. the Microsoft paper's missed Real-M Q19/Q22).

### Open

- Installing a restart-requiring diagnostic extension: action (recommended) vs precondition vs out of scope.
  User: "not clear".

## 5. Related papers read with the user

- **AgenticDB** (arXiv 2606.20318v4, read in full): one LLM planner + Initializer (builds action catalog),
  rule-based Validator, Executor (apply/restart/benchmark), Recovery (revert to last safe config), Auditor,
  Memory Book (experience keyed by workload fingerprint). Knobs then OS, sequential. Frozen weights.
  MySQL/Postgres, Sysbench/YCSB/TPC-H, 100-min budget, +118% avg over best baseline. Trial and error on target
  with a replayable benchmark: our natural baseline. Its Validator checks legality; our verifier must check
  "cannot make any query slower or wrong".
- **AgentTune** (PACMMOD 3(6) 2025, DOI 10.1145/3769758; full text NOT read): four prompt-chained agents
  (workload analyzer, knob selector, range pruner, tree-based recommender), knobs only, fixed replay budget.
- **LLM index tuning on SQL Server** (Wang, Wu, Narasayya, Chaudhuri; PVLDB 19(12) 2026; arXiv 2603.09181).
  User: "the issues they raise are good." Missed bottlenecks (Real-M Q19/Q22, where DTA gets ~90% of gain);
  less attention to costly queries as workloads grow; unused recommended indexes; high variance across
  invocations, worst runs time out; optimizer cost estimates misrank LLM indexes; execution validation costs
  more than tuning; best-of-5 is only knowable by oracle. Their fix (validate by building and running) is the
  trial we forbid.
- Holistic tuners classified: see §1. Sources: Proto-X PVLDB 17:3373; UDO PVLDB 14(13); UniTune SIGMOD 2023;
  EvoTune arXiv 2607.17841; λ-Tune SIGMOD 2025 (arXiv 2411.03500).
- Production evidence on agents and DBs: `Agent DB interaction/` notes. Key: in production LLMs read and
  propose, humans or deterministic systems write; only Oracle proves before commit; nobody publishes
  regression rates. DBA-Bench best automated Safe Pass 27.1% (PG) / 21.0% (TiDB) vs human 92.5% / 91.9%.

## 6. How the user wants to work

- Short, decision-oriented answers. Long reports "do not help us in any way whatsoever".
- Not paper/deadline-focused; papers are by-products. Goal: understand how agents interact with data
  systems in production to inform the main project.
- No design suggestions without concrete grounding; ask clarifying questions before spawning research.
- Likes the "unknowns" framing. Extra slides go at the end of the deck; keep old slide versions.
- Persist everything in this repo (CloudLab nodes are ephemeral), not in Claude's local memory.
