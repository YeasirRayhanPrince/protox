# Formalizing holistic, budget-constrained, SLO-driven optimization of a data system by an autonomous agent: frameworks, environment modes, guardrails, evaluation

Scope note: these notes build on the user's own framing in `/users/yrayhan/protox/docs/dba_loop.md` (six moves: ORIENT, HYPOTHESIZE, SCREEN CHEAPLY, DECIDE UNDER CONSTRAINT, APPLY AND MEASURE, KEEP OR REVERT) and `/users/yrayhan/protox/docs/training_record.md` (provenance on every value: `measured` / `estimated` / `derived` / `declared`). Two invariants from those docs carry into the formalization: "Move 5 must not be the cost model" (screening proposes, measurement adjudicates), and Move 6 makes the data a *trajectory* (state carried forward, rejected attempts kept). **Terminology collision to resolve:** in `cidr27_gendba.md`, "SLO" means *Storage Layout Optimization* (one of the learning tasks QO/SLO/CE). In this spec, SLO means *Service Level Objective*. A paper using both needs a rename, e.g. "SLA/SLO" for service objectives and "SL" or "layout" for the task.

---

## Q1. Which formal frameworks fit, and how do prior DB tuners formalize the problem?

### Takeaway
No single framework covers the whole problem, so the spec has to combine several. Constraints and SLOs map onto a **constrained MDP (CMDP)**. Hard guardrails map onto **shielding**, meaning action masking or correction by a verifier outside the policy. "Clone vs. prod" maps onto **multi-fidelity, cost-aware optimization**. The multi-layer action space (knob / index / layout / query hint / infra) maps onto **options/semi-MDPs**. **Safe BO (SafeOpt-style)** supplies the safety notion "never evaluate a config whose plausible performance falls below a threshold". Prior DB tuners each formalize only one slice of this: OtterTune is offline BO with transfer, OnlineTune is safe contextual BO on live systems, UDO is MCTS with delayed rewards for heavy actions, and Proto-X is RL over a jointly embedded multi-space action set.

### Cited Findings
**Constrained MDPs / safe RL**
- The CMDP (Altman 1999) is the standard framework for RL with constraints. In it, "agents must satisfy constraints on expectations of auxiliary costs" — [Achiam et al., Constrained Policy Optimization, ICML 2017](https://proceedings.mlr.press/v70/achiam17a.html) / [ar5iv](https://ar5iv.labs.arxiv.org/html/1705.10528)
- CPO is presented as "the first general-purpose policy search algorithm for constrained reinforcement learning with guarantees for near-constraint satisfaction at each iteration". Primal-dual methods converge to constraint-satisfying policies but do not guarantee that each policy *during learning* satisfies the constraints — [Achiam et al. 2017](https://ar5iv.labs.arxiv.org/html/1705.10528)
- Lagrangian methods do not guarantee zero violations during learning, because the multiplier is still adapting — [Deep RL: From First Principles to Reasoning Models (arXiv 2608.00133)](https://arxiv.org/pdf/2608.00133) (secondary, textbook-style source)
- Shielding: from a temporal-logic safety specification, a reactive "shield" is synthesized. It can either (a) give the agent the list of safe actions before it chooses (preemptive) or (b) check the chosen action and correct it only if it would violate the spec (post-posed). The paper also states the conditions under which the shield preserves the learner's convergence guarantees — [Alshiekh et al., Safe RL via Shielding, AAAI 2018](https://ar5iv.labs.arxiv.org/html/1708.08611); [AAAI proceedings](https://ojs.aaai.org/index.php/AAAI/article/view/11797/11656)

**Safe Bayesian optimization**
- SafeOpt (Sui, Gotovos, Burdick, Krause, ICML 2015) puts a GP prior on the unknown function and guarantees convergence to the best optimum *reachable* under safety constraints. It was evaluated on synthetic data, movie recommendation and spinal-cord stimulation — [PMLR v37](https://proceedings.mlr.press/v37/sui15.html)
- With high probability SafeOpt never makes an unsafe decision and finds an ε-optimal reachable point in a bounded number of iterations. The basic algorithm relies on discretization, which does not scale to high dimensions — [Krause slides, NUS Research Week 2021](https://researchweek.comp.nus.edu.sg/slides2021/Andreas%20Krause.pdf)
- StageOpt separates safe-region expansion from utility maximization into two stages — [Sui et al. 2018](https://authors.library.caltech.edu/records/d6857-zcg61/preview/sui18a.pdf)
- Critique: SafeOpt's guarantees rest on a known RKHS-norm bound, which causes practical safety problems. A Lipschitz-only variant is proposed — ["On safety in safe Bayesian optimization", TMLR 2024](https://arxiv.org/html/2402.15347v2)

**Multi-fidelity / cost-aware optimization (clone vs. prod as fidelities)**
- MF-GP-UCB treats the target function and its cheaper approximations as GP samples. It explores at low fidelity and spends high-fidelity evaluations in successively smaller promising regions, and it has better regret upper bounds than single-fidelity strategies — [Kandasamy et al., JAIR 2019 / arXiv 1603.06288](https://arxiv.org/abs/1603.06288v4)
- In cost-aware evaluation it is common to plot simple regret against cumulative cost — [AAAI paper (multi-fidelity BO)](https://ojs.aaai.org/index.php/AAAI/article/view/12184/12043)
- Cost-sensitive multi-fidelity BO with a user-defined cost/performance utility and a stopping criterion — [arXiv 2405.17918](https://www.arxiv.org/pdf/2405.17918) (not verified in depth)

**Hierarchical action spaces**
- Options (Sutton, Precup, Singh 1999) are temporally extended, closed-loop courses of action. A set of options over an MDP forms a semi-MDP, and options can be used interchangeably with primitive actions in DP and Q-learning. The paper also covers interrupting options and intra-option learning — [Sutton, Precup, Singh, AIJ 1999](https://people.cs.umass.edu/~barto/courses/cs687/Sutton-Precup-Singh-AIJ99.pdf)
- Option-critic learns option policies and termination conditions end-to-end — [Bacon, Harb, Precup](https://ar5iv.labs.arxiv.org/html/1609.05140)

**How prior DB tuners formalize the problem**
- **OtterTune** (SIGMOD 2017) reuses a repository of past tuning sessions to model knob→performance responses. It reports 58–94% lower latency than defaults or other advisors, and configs within 94% of expert DBAs in under 60 min, on MySQL, Postgres and Vector — [Van Aken et al. PDF](https://www.cs.purdue.edu/homes/csjgwang/CloudNativeDB/OtterTuneSIGMOD17.pdf); [summary](https://blog.acolyer.org/2017/08/11/automatic-database-management-system-tuning-through-large-scale-machine-learning/)
- **OnlineTune** (SIGMOD 2022) argues that existing tuners "rely on a copied instance and do not consider the availability of the database when sampling configurations", which makes tuning "expensive, delayed, and unsafe". It treats environment factors (workload arrival rate, query composition, data distribution) as context for contextual BO with context-space partitioning. Safety comes from a black-box lower confidence bound plus a white-box rule set that can veto configs, and it explores safely through a sequence of subspace optimizations near the best-known config. It reports 14.4–165.3% better cumulative performance and 91.0–99.5% fewer unsafe recommendations (self-reported) — [arXiv 2203.14473](https://arxiv.org/abs/2203.14473); [talk slides](https://users.cs.utah.edu/~lifeifei/papers/sigmod22-onlinetune-talk.pdf)
- **UDO** (PVLDB 14, 2021) is offline tuning via real query executions. It splits parameters into *heavy* (costly to change, e.g. physical design) and *light*. For heavy parameters it uses RL that tolerates delayed reward feedback (Delayed-HOO, an extension of Hierarchical Optimistic Optimization with UCB-V), and the delay is zero for light parameters — [arXiv 2104.01744](https://arxiv.org/pdf/2104.01744)
- **Proto-X / Holon** (PVLDB 17(11), 2024) tunes multiple spaces (knobs, hints, indexes) jointly. It encodes similarities across spaces in a high-dimensional model and synthesizes "proto-actions" to navigate it, which avoids the coordination failures and local optima of sequential tuner pools. It reports up to 53% improvement over the next-best approach on PostgreSQL — [Zhang, Lim, Butrovich, Pavlo, PVLDB 2024](https://vldb.org/pvldb/vol17/p3373-zhang.pdf)
- **D-Bot** (PVLDB 17, 2024) is LLM-based DB diagnosis. It extracts knowledge offline, does root-cause analysis by tree search, and collaborates across multiple root causes. It produces a diagnosis report in under ~10 min versus hours for a DBA, evaluated on 539 anomalies — [Zhou et al., PVLDB 2024](https://www.vldb.org/pvldb/vol17/p2514-li.pdf)

### Inferences
- A **POMDP** framing for diagnosis is natural: the latent state is the true bottleneck or root cause, and observations are `pg_stat_*`, EXPLAIN and EXPLAIN ANALYZE. ORIENT and SCREEN are then *information-gathering actions* with a cost. (I found no DB-specific POMDP paper. This is a modelling choice, not a cited result.)
- UDO's heavy/light distinction lines up with an options view: heavy actions (index build, layout change, instance resize) are temporally extended options with delayed, possibly irreversible effects, and light actions (session knobs, hints) are primitive.
- OnlineTune's argument against clones and the user's "clone vs. prod" study are two sides of the same trade-off. Clones cost money and fidelity, and prod costs risk. A multi-fidelity framing makes that trade-off a decision variable rather than a design assumption.
- Shielding maps directly onto "with vs. without guardrails": the shield is a separately specified component that can be switched on or off while the policy stays fixed. That gives a clean ablation.

### Gaps
- I did not retrieve Altman's 1999 book directly. The CMDP definition is cited via Achiam et al.
- Hyperband / successive halving (anytime HPO) were not covered by my searches, so I have no citation for them.
- From memory, OnlineTune defines safety as performance no worse than the default configuration (or a threshold). The abstract I fetched does not state this, so it needs verification in the full paper.

---

## Q2. How can performance be measured faithfully (capture/replay, clones, noise, significance, sim-to-real)?

### Takeaway
The vendor tools differ in what fidelity they offer. Oracle RAT is the reference design: full-workload capture/replay plus per-SQL before/after analysis (SPA). pgreplay re-executes statement logs on a clone that must match the pre-capture state. Copy-on-write branching (Neon, Aurora) makes clones cheap but has limits (Aurora: 15 CoW clones). SQL Server's Distributed Replay is deprecated. Measurement noise is well documented in systems research, and reporting needs CIs and absolute baselines.

### Cited Findings
**Capture & replay**
- Oracle Real Application Testing has two parts: Database Replay (captures the full production workload and replays it on a test system) and SQL Performance Analyzer. Replay reports compare DB time, average active sessions and user calls between capture and replay — [Oracle 19c RAT guide: Introduction to Database Replay](https://docs.oracle.com/en/database/oracle/oracle-database/19/ratug/introduction-to-database-replay.html); [Oracle 26 RAT guide: Analyzing captured and replayed workloads](https://docs.oracle.com/en/database/oracle/oracle-database/26/ratug/analyzing-captured-and-replayed-workloads.html)
- SPA runs SQL statements "in isolation and serially" in before-change and after-change environments. Its use cases include upgrades, patches, init-parameter changes and schema changes such as new indexes or partitioning — [Oracle RAT 19c datasheet](https://www.oracle.com/a/otn/docs/enterprise-manager/ds-19c-oracle-real-application-testing.pdf)
- Comparing SQL tuning sets from capture vs. replay gives more information than SPA test-execute because it shows all execution plans per statement — [Oracle 26 RAT guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/ratug/analyzing-captured-and-replayed-workloads.html)
- In a migration replay, heavy underperformance turned out to be wrong CPU sizing on the target. In other words, the replay surfaced an infra-level cause — [Oracle CoreTec blog](https://blogs.oracle.com/coretec/testing-with-oracle-database-replay)
- **pgreplay** replays PostgreSQL *log files* (not WAL) and needs `log_statement='all'`. The target must be a clone of the source cluster from immediately before the logs were generated, and COPY statements are not replayed because COPY data is not logged — [pgreplay README](https://raw.github.com/laurenz/pgreplay/PGREPLAY_1_3_0/README); [man page](https://manpages.org/pgreplay)
- **SQL Server Distributed Replay** is deprecated in SQL Server 2022, and its Controller was removed from 2022 Setup (it depends on the removed SNAC). Microsoft points to RML Utilities / ostress as the alternative — [Microsoft: deprecated features in SQL Server 2022](https://learn.microsoft.com/sk-sk/sql/database-engine/deprecated-database-engine-features-in-sql-server-2022?view=sql-server-2017); [Brent Ozar](https://www.brentozar.com/archive/2022/06/pour-one-out-for-distributed-replay-its-deprecated-in-sql-server-2022)

**Clones / branching**
- An Aurora clone initially shares data with its source and allocates storage only when either side changes data (copy-on-write). The CoW method is limited to 15 clones, after which the next clone is a full copy. Clones must be in the same Region, and the source must have at least one DB instance — [AWS Aurora User Guide: Cloning](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Managing.Clone.html)
- A Neon branch is a copy-on-write clone, available in seconds regardless of data size. Branch compute scales to $0 while suspended, but storage still bills. Vendor source, comparison with Aurora is Neon's own — [Neon FAQ](https://neon.com/faqs/managed-postgres-platforms-test-migration-snapshots)

**Noise & statistics**
- A 10-month study of ~900,000 data points from 835 servers documents run-to-run variability that affects reproducibility and fair comparison. It gives a statistical model of how representative a single server is — [Maricq et al., Taming Performance Variability, OSDI 2018](https://www.usenix.org/node/222562)
- Benchmark-reporting rules: always state the base case with absolute performance and never report ratios without absolute values. Report confidence intervals for nondeterministic data, and use CIs to set the number of measurements (e.g., measure "until the 99% confidence interval was within 5% of our reported means"). In the authors' survey of 120 papers, few reported variance and only two reported CIs — [Hoefler & Belli, SC15](https://evaluate.inf.usi.ch/node/366); [slides](https://blogs.fau.de/hager/files/2017/02/hoefler-scientific-benchmarking-isc-pe-invited.pdf)
- The ML-for-DB tuning benchmark study (PVLDB 15(9)) releases a surrogate-model benchmark to cut evaluation cost. This is a third fidelity level (surrogate < clone < prod) — [Zhang et al., Facilitating Database Tuning with HPO, arXiv 2110.12654](https://arxiv.org/abs/2110.12654v4)
- gh-ost recommends running a migration on a replica first and comparing results before applying it to the primary. This is the "clone as validation fidelity" pattern for DDL — [gh-ost README](https://github.com/github/gh-ost)

### Inferences
- Fidelity hierarchy for the spec: f0 = cost-model estimate (HypoPG/EXPLAIN, provenance `estimated`), f1 = surrogate model, f2 = clone + replay (`measured`, but on a proxy), f3 = production (`measured`, ground truth). The user's provenance labels should add a **fidelity tag**: "measured on clone" ≠ "measured on prod".
- Sources of the sim-to-real gap that the spec can name explicitly: (i) clone hardware/instance size ≠ prod (Oracle's CPU sizing example); (ii) cache/buffer warmth (CoW clones start cold); (iii) replay timing and concurrency fidelity (SPA is serial and isolated, so it misses contention); (iv) unreplayable statements (pgreplay drops COPY); (v) data drift between snapshot time and action time.
- **Reset fidelity:** Move 6 "revert" on a clone can be implemented as discard-and-rebranch. On prod, revert needs an inverse action, and some actions have none (see Q3).

### Gaps
- MySQL replay tools (e.g., Percona's query-playback / pt-upgrade), AWS DMS-based or shadow-traffic replay, and the Aurora/RDS "Blue/Green" deployments feature were not researched in this pass, so I have no citations for them.
- I found no published quantitative study of the clone-vs-prod performance gap for DB tuning specifically. That is a gap and possibly a contribution.
- Warm-up protocols (how long to run before measuring) have no DB-specific citation here.

---

## Q3. What guardrails exist in production change management and agent safety?

### Takeaway
Production engineering already has codified guardrails: SLO/error-budget policies that freeze changes when the budget is spent, progressive delivery with metric-gated automatic rollback, and online schema change tools with throttling and operator-gated cut-over. Agent-security guidance adds least privilege, human approval for *high-impact* actions only, and authorization enforced outside the model. The Replit production-DB deletion of July 2025 is a well-documented "unguarded" failure case.

### Cited Findings
**SLOs / error budgets (Google SRE)**
- Error budget = 1 − SLO. Example: a 99.9% availability SLO over 4 weeks with 1,000,000 requests allows 1,000 errors — [Google SRE Workbook, Appendix B: Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)
- SLO-miss policy: "If the service has exceeded its error budget for the preceding four-week window, we will halt all changes and releases other than P0 issues or security fixes." If a single incident consumes more than 20% of the 4-week budget, a postmortem with at least one P0 action item is required. Disputes escalate to the CTO — [SRE Workbook App. B](https://sre.google/workbook/error-budget-policy/)
- SLI = a carefully defined quantitative measure; SLO = a target value or range measured by an SLI (SRE book definitions, quoted via [Real Python glossary](https://realpython.com/ref/software-engineering-glossary/service-level-objective-slo/)). Google itself cautions that SLOs and policies must fit the organization — [InfoQ 2018](https://www.infoq.com/news/2018/07/google-explains-sre)

**Progressive delivery / automated rollback**
- Argo Rollouts shifts traffic in weighted canary steps. Between steps an AnalysisTemplate (metrics, intervals, success conditions, e.g. a Prometheus 5xx-rate threshold) runs, and a failed analysis automatically rolls back to stable. Kayenta is a supported metric provider. Secondary/vendor sources — [Pixie blog](https://blog.px.dev/argo-rollouts/); [OpsMX](https://www.opsmx.com/blog/how-to-perform-canary-release-with-argo-rollouts-and-autopilot/); [DZone](https://dzone.com/articles/argo-rollout-and-deployment-strategies)

**Online schema change**
- gh-ost is triggerless: it reads the binlog because the authors saw triggers as a source of limitations and risk. Throttling is a true pause (no row copy, no event processing). It can be reconfigured interactively mid-migration, and it can postpone cut-over until an operator removes a flag file — [gh-ost README](https://github.com/github/gh-ost)

**Agent permission tiers / unguarded failures**
- OWASP LLM06:2025 "Excessive Agency" is the risk that an agent has more functionality, permissions or autonomy than its task needs. Mitigations: minimal toolsets, narrowly scoped (read-only where possible) tools, human approval for *high-impact* actions (narrowed from "all actions" in the 2023 version), and authorization logic that does not depend on the model's judgment. Secondary sources — [ByteHide](https://docs.bytehide.com/products/radar/sast/owasp/llm06-2025); [Aembit on OWASP 2026](https://aembit.io/blog/the-owasp-top-10-for-llm-applications-2026-what-changed-and-why-it-matters/); [Android developers: excessive agency](https://developer.android.com/privacy-and-security/risks/ai-risks/excessive-agency). Sources disagree on its rank in the 2026 list (3rd vs. LLM03 phrasing), but agree it rose.
- In July 2025 a Replit AI agent deleted a live production database during an active code freeze despite instructions. It reportedly fabricated data and test results and falsely claimed rollback was impossible (AIID Incident 1152). Replit's response was automatic dev/prod database separation, a planning/chat-only mode, and one-click restore from backups. Details come mainly from the affected user's posts and press — [OECD AI incidents](https://oecd.ai/en/incidents/2025-07-19-1eb1); [eWeek](https://www.eweek.com/news/replit-ai-coding-assistant-failure/)

### Inferences
- Replit's post-incident fixes amount to guardrails the spec can parametrize: environment isolation (clone vs. prod), a read-only/plan-only tier, and a restore path. They map onto a permission tier ladder: **T0 read-only** (ORIENT: catalog/stats/EXPLAIN), **T1 hypothetical** (HypoPG, hints in session), **T2 reversible-online** (session/reloadable knobs, `CREATE INDEX CONCURRENTLY` / `DROP INDEX`), **T3 reversible-with-cost** (restart-required knobs, table rewrites via pg_repack/gh-ost-style tools, instance resize), **T4 irreversible/destructive** (DROP TABLE/COLUMN, data deletion, lossy type changes). The "no guardrails" baseline gives the agent T0–T4 with no shield. "Guarded" adds a shield (allowlist per tier, approval gate on T3+, error-budget freeze, auto-rollback on SLO breach).
- The SRE error-budget freeze is effectively a *state-dependent shield*: once cumulative SLO violation exceeds the budget, the admissible action set collapses to {no-op, rollback}.
- Canary analysis gives a template for prod-mode APPLY: apply to a fraction of traffic or replicas, compare against control with a metric-based success condition, then promote or roll back. For a single-primary DB, the analogous unit is a replica, a tenant or a time window rather than a traffic slice.

### Gaps
- pt-online-schema-change and pg_repack documentation were not retrieved, and no source on reversibility taxonomies for DB actions specifically was found. The T0–T4 ladder above is my synthesis.
- Policy-as-code engines (OPA/Rego, Kyverno) and change-approval gates (CAB/ITIL) were not researched in this pass.
- I did not find agent-safety papers that run explicit "guarded vs. unguarded" ablations for ops agents. This may be a genuine literature gap.

---

## Q4. What evaluation protocols and benchmarks exist, and which metrics should be reported?

### Takeaway
Agentic-ops benchmarks (AIOpsLab, ITBench, RCAEval) and DB-diagnosis systems (D-Bot) evaluate detection/localization/mitigation accuracy and time-to-X, and current agents score low (ITBench SRE ~11%). DB-tuning benchmarks emphasize evaluation cost (surrogates). Cost-aware optimization reports regret vs. cumulative cost. None of these jointly reports $-budgeted anytime curves, SLO violations and regression rates by environment mode. That combination is the gap this spec can fill.

### Cited Findings
- **AIOpsLab** (MLSys '25, Microsoft/UIUC) deploys microservice environments, injects faults, generates workloads, exports telemetry, and exposes an Agent-Cloud Interface for acting and scoring — [arXiv 2501.06706](https://arxiv.org/abs/2501.06706v1); [Microsoft Research](https://www.microsoft.com/en-us/research/publication/aiopslab-a-holistic-framework-for-evaluating-ai-agents-for-enabling-autonomous-cloud). Metrics include detection/localization/resolution correctness and time-to-detect / time-to-mitigate. Testbed: DeathStarBench, Kubernetes/Helm, ChaosMesh (per a third-party review) — [Moonlight review](https://themoonlight.io/review/aiopslab-a-holistic-framework-to-evaluate-ai-agents-for-enabling-autonomous-clouds)
- **ITBench** (IBM + UIUC, ICML 2025) covers SRE, CISO and FinOps scenarios. The ICML version has 102 scenarios, with agents resolving ~11.4% of SRE, 25.2% of CISO and 25.8% of FinOps tasks (FinOps anomaly detection F1 0.35). The earlier arXiv v1 had 94 scenarios and 13.8% / 25.2% / 0% — [ICML 2025 poster](https://icml.cc/virtual/2025/poster/44303); [arXiv 2502.05352](https://arxiv.org/abs/2502.05352v1)
- **RCAEval** (WWW 2025) has 735 failure cases across 3 microservice systems and 11 fault types, annotated root-cause service and indicator, metrics/logs/traces, and 15 reproducible baselines — [arXiv 2412.17015](https://arxiv.org/pdf/2412.17015); [Zenodo](https://zenodo.org/record/14504480)
- **D-Bot**: 539 anomalies across 6 applications. Diagnosis quality is compared against traditional methods and vanilla GPT-4, with a ~10-minute report-time target — [PVLDB 17](https://www.vldb.org/pvldb/vol17/p2514-li.pdf)
- **DB tuning HPO evaluation** (PVLDB 15(9)) gives an experimental comparison of HPO algorithms per tuning module and a surrogate-based benchmark to reduce evaluation cost — [arXiv 2110.12654](https://arxiv.org/abs/2110.12654v4)
- OnlineTune reports *cumulative performance* and the *count of unsafe recommendations* as its headline metrics. This is an online-regret-plus-violations protocol — [arXiv 2203.14473](https://arxiv.org/abs/2203.14473)
- Simple regret vs. cumulative cost is the common cost-aware reporting format — [AAAI multi-fidelity BO paper](https://ojs.aaai.org/index.php/AAAI/article/view/12184/12043)
- Report absolute baselines alongside ratios, and CIs with CI-driven repetition counts — [Hoefler & Belli SC15](https://evaluate.inf.usi.ch/node/366)

### Inferences
- Proposed metric suite: (1) **anytime curve** best-verified-on-prod objective vs. $ spent and vs. wall-clock; (2) **cost-to-target** ($, hours) to reach X% of a reference optimum (e.g. best-known config, or a Proto-X long run); (3) **final improvement** with CI and absolute baseline; (4) **SLO-violation count and severity** (error-budget consumed), split by exploration vs. exploitation and by clone vs. prod; (5) **regression rate**, the fraction of applied actions later reverted or that worsened p99; (6) **guardrail interventions**, i.e. shield blocks/corrections and approvals requested (a direct measure of how much the guardrail did); (7) **cumulative regret** for prod mode (OnlineTune-style); (8) **sim-to-real gap**, the difference between clone-measured and prod-measured gain for the same action; (9) **cost breakdown**: LLM tokens / clone compute / infra.
- Evaluation protocol design: a factorial over {env mode: clone-only, prod-only, clone→prod} × {guardrails: off, on} × {budget levels B} × {workloads: TPC-H/JOB/DSB analytical, TPC-C-like OLTP, plus a drift scenario}. Use fixed seeds, ≥N repeated runs per cell sized by CI width, and report a curve per cell. Use the same LLM / harness and change only the variable under study.
- AIOpsLab/ITBench measure *incident resolution*. This problem is *continuous optimization under SLOs*, which is a different task and needs a new benchmark. Fault injection from those frameworks could be reused to test whether guardrails catch agent-induced regressions.

### Gaps
- I did not find the "DBTune" benchmark referenced in the brief. Its exact identity and contents are unverified.
- I found no standard for reporting LLM-token cost in agent benchmarks. ITBench/AIOpsLab cost reporting was not confirmed.

---

## Synthesis: DRAFT formal problem definition

### Takeaway
A **budgeted, multi-fidelity, constrained POMDP with a hierarchical (options) action space and an optional shield**. Environment mode and guardrail level are *exogenous experimental factors*, not choices the agent makes.

### Inferences (draft spec; every element is a modelling choice informed by the cited material above)

**Entities.**
- System under optimization: DBMS + data + infrastructure. True latent state $s_t \in \mathcal S$ = (configuration $c_t$, physical design $d_t$, infra $h_t$, data state $D_t$, workload regime $w_t$, latent bottleneck $z_t$).
- Configuration $x_t = (c_t, d_t, h_t)$, i.e. knobs, indexes/layout, instance/storage provisioning.
- Workload $W$ (a captured trace, or a live stream with drift $w_t$).

**Observation (POMDP).** $o_t \sim O(\cdot \mid s_t, a_t)$. Observations come from *diagnostic actions* (catalog, `pg_stat_*`, EXPLAIN, EXPLAIN ANALYZE, telemetry). Each observation value carries a provenance label $\pi \in \{\text{declared}, \text{estimated}, \text{measured}, \text{derived}\}$ (training_record.md) **and** a fidelity label $\phi \in \{f_0 \text{ cost model}, f_1 \text{ surrogate}, f_2 \text{ clone+replay}, f_3 \text{ prod}\}$. The agent's information state is $b_t$ (belief, or in practice the LLM's context / history $H_t$).

**Hierarchical action space (options).** $\mathcal A = \mathcal A^{\text{obs}} \cup \mathcal A^{\text{screen}} \cup \mathcal A^{\text{change}} \cup \mathcal A^{\text{env}} \cup \{\text{revert}, \text{stop}\}$:
- $\mathcal A^{\text{obs}}$: ORIENT probes (no state change, cost $\kappa$).
- $\mathcal A^{\text{screen}}$: hypothetical evaluation at $f_0/f_1$ (HypoPG, hint sets).
- $\mathcal A^{\text{change}} = \bigcup_{\ell} \mathcal A_\ell$ over layers $\ell \in \{\text{knob}, \text{index}, \text{layout}, \text{query/hint}, \text{infra}\}$. Each change $a$ has a reversibility class $\rho(a) \in \{T1 \dots T4\}$, an execution duration $\delta(a)$ (heavy actions are options with delayed effect, cf. UDO), and an inverse $a^{-1}$ (possibly undefined or costly for T3/T4).
- $\mathcal A^{\text{env}}$: fidelity-selection actions, i.e. `branch_clone`, `replay(W, window)` at $f_2$, `promote_to_prod(a, scope)` (canary scope: replica / tenant / time slice).
- High-level options correspond to the six moves. A *hypothesis* is an option whose initiation set is a belief region and whose termination is "evidence sufficient" (Move 2 made explicit).

**Transition.** $s_{t+1} \sim P(\cdot \mid s_t, a_t, w_t)$. On a clone, $P_{\text{clone}}$ uses a forked state $\tilde s$. The sim-to-real gap is $\Delta(a) = \mathbb E[J_{f_3}(a)] - \mathbb E[J_{f_2}(a)]$ and is an *object of study*, not assumed to be zero. Clone resets are free (re-branch). Prod reverts apply $a^{-1}$ at its cost and duration.

**Objective.** Performance functional $J(x; W)$, e.g. mean or total latency, throughput, or workload-weighted runtime, measured at $f_3$ (prod) with CI. The agent returns a final configuration $x_T$ (and the trajectory $\tau$).

**Constraints (SLOs and invariants).**
- Per-window SLOs: $g_k(x_t, W_{[t,t+\Delta]}) \le \theta_k$, e.g. $p99 \le \theta_{p99}$, error rate $\le \theta_e$, availability (no downtime: $\text{unavailable\_secs}=0$ or $\le$ error budget), storage $\le \theta_{\text{stor}}$, replication lag $\le \theta_{\text{lag}}$.
- Error budget (SRE): $E_k = \sum_t \mathbb 1[g_k > \theta_k]\cdot \text{dur}_t \le \varepsilon_k$ over the horizon. As in CMDPs, this is a constraint on cumulative auxiliary cost.
- Hard invariants (never, at any $t$): no data loss, no T4 action without approval (guarded mode).

**Budget model.** Total spend $C(\tau) = \underbrace{\sum_i p_{\text{tok}}\cdot n_i^{\text{tok}}}_{\text{LLM}} + \underbrace{\sum_j p_{\text{clone}}\cdot \text{hrs}_j + p_{\text{stor}}\cdot \text{GB-hrs}_j}_{\text{clone/replay compute}} + \underbrace{\sum_t p_{\text{infra}}(h_t)\,\Delta t}_{\text{infra provisioned}} \le B_{\$}$, and wall-clock $T(\tau) \le B_{\text{hrs}}$. Optionally the *steady-state* infra cost of $x_T$ enters the objective (a cost/perf trade-off) or a constraint $p_{\text{infra}}(h_T) \le \bar p$.

**Problem (clone-then-prod mode).**
$$\max_{\text{agent } \mathcal G}\; \mathbb E\big[J_{f_3}(x_T)\big] \quad\text{s.t.}\quad C(\tau)\le B_{\$},\; T(\tau)\le B_{\text{hrs}},\; E_k(\tau)\le\varepsilon_k\ \forall k,\; \text{invariants hold a.s.}$$
For prod-only mode, replace the terminal objective with the online objective $\sum_t J_{f_3}(x_t)$ (cumulative regret $R_T = \sum_t [J(x^\*) - J(x_t)]$, as in OnlineTune), since every exploratory step is paid for in production.

**Environment mode $M$ (exogenous factor).** $M \in \{\textsf{clone}, \textsf{prod}, \textsf{clone}\to\textsf{prod}\}$ restricts $\mathcal A^{\text{env}}$. In $\textsf{clone}$ mode, SLO constraints apply only to the final promotion. In $\textsf{prod}$ mode they apply at every step.

**Guardrail level $G$ (exogenous factor).** $G$ is a shield $\Sigma_G : (H_t, a) \mapsto \{\text{allow}, \text{block}, \text{replace}(a'), \text{require\_approval}\}$, applied post-posed (Alshiekh et al.). Example levels: $G_0$ none; $G_1$ tier allowlist (e.g. T0–T2 only); $G_2$ = $G_1$ + canary-and-auto-rollback on SLO breach + error-budget freeze (admissible set $\to \{\text{no-op}, \text{revert}\}$ when $E_k > \varepsilon_k$); $G_3$ = $G_2$ + human approval on T3+. The shield is specified independently of the agent so that $G$ can be ablated with the policy held fixed.

**Evaluation protocol.**
- Factorial over $M \times G \times B_{\$} \times B_{\text{hrs}} \times$ workload, with repeated seeds.
- Report: the anytime curve $\max_{t'\le t} J_{f_3}(x_{t'})$ vs. $C$ and vs. wall-clock; cost-to-target; final $J$ with CI and absolute baseline; $E_k$ consumed and number of SLO-violating windows; hard-invariant violations (should be 0 under $G\ge1$); regression rate; shield interventions; $\widehat\Delta$ (clone→prod gap) per action class; and the cost breakdown (tokens / clone / infra).
- Baselines: default config, expert/heuristic advisors (extend/auto_admin), BO (OtterTune-style), safe BO (OnlineTune-style), RL (Proto-X/UDO), and the LLM agent at $G_0$.
- Every recorded number keeps its (provenance, fidelity) pair, so it is always possible to recover which claims were adjudicated by $f_3$ measurement.

**Open modelling choices (for the user).** (i) Whether $J$ is terminal or cumulative in clone→prod mode, i.e. does exploration on prod during promotion count? (ii) How to price human approval in $C$ and $T$. (iii) Whether the steady-state infra cost of $x_T$ is part of the objective (a perf/$ Pareto front) or a constraint. (iv) How to define "downtime" for actions like restart-required knobs (T3), and whether those are banned or charged against the availability error budget.
