# Exo + self-improving harnesses: what transfers to a zero-regression DB harness
(researched 2026-10-27; [S] = secondary source)

## Exo (primary source found)
Repo: https://github.com/exoharness/exo (Rust, MIT [S] https://trendshift.io/repositories/64498). Built by Krentsel, Casado and Goyal [S] https://latent.space/wiki/alex-krentsel/.
1. **Loop:** The exoharness keeps an append-only event log. The harness (prompt assembly, model calls, tools) is replaceable, and "the prompt is a view the harness builds from" the log (https://exoharness.ai/docs/architecture/data-model). The agent edits its code and calls `rebuild_and_restart_exo`, which "validates and builds Exo, then hands a restart to the guardian" (https://github.com/exoharness/exo/tree/main/examples/self-improving-agent).
2. **Regressions:** The only gate the docs show is a build. Sandbox snapshot and rewind restore files, "not the conversation log" (https://exoharness.ai/docs/archive/concepts/lifecycles). Forking "does not undo commands... or roll back an external service" (data-model page). A secondary source says a failed executor trial step reverts to the previous snapshot [S] (https://www.startuphub.ai/news/alex-krentsel-on-exo-and-recursive-self-improving-ai-agents). The docs do not show this.
3. **Fenced off:** The agent cannot touch the log, the vault secrets or host-side service control. Sandbox network policy applies only to sandbox processes, and harness modules are "trusted host code" with no capability sandbox (https://exoharness.ai/docs/architecture/harnesses).
4. **Take:** Use an immutable log the agent cannot write as ground truth, with a mutable policy layer on top. Exo itself says rollback stops at external side effects. A production DB is exactly such an external effect.

## Darwin Gödel Machine (2505.22954)
1. **Loop:** Keep an archive of agents, sample one, let an LLM write a modified version, then "empirically validat[e] each change using coding benchmarks" (https://arxiv.org/abs/2505.22954).
2. **Regressions:** It relies on trial and error in a sandbox. Bad variants just score low and stay in the archive (same URL).
3. **Fenced off:** The paper cites sandboxing and human oversight (same URL). The benchmark and evaluator are outside the agent's reach.
4. **Take:** Every candidate is scored by a fixed evaluator the agent cannot edit, and an archive of all candidates allows a fallback.

## Huxley-Gödel Machine (2510.21614, ICLR 2026)
1. **Loop:** Tree search over self-modifications, guided by CMP: the scores of a node's descendants rather than its own score (https://arxiv.org/abs/2510.21614).
2. **Regressions:** Benchmark trials in a sandbox. It names the "Metaproductivity-Performance Mismatch": today's score is a poor predictor of how well a node improves later (same URL).
3. **Fenced off:** Benchmarks and the scoring procedure stay fixed (same URL).
4. **Take:** Choose diagnostic and proof strategies on the clone by their track record, then promote only the action that proved out.

## Meta-Harness (2603.28052, Stanford)
1. **Loop:** An outer loop where a coding-agent proposer reads "the source code, scores, and execution traces" of earlier harnesses through a filesystem (https://arxiv.org/abs/2603.28052). Code: https://github.com/stanford-iris-lab/meta-harness.
2. **Regressions:** Offline search on task sets, with transfer checked on held-out models (same URL).
3. **Fenced off:** Only harness code is searched. The models and tasks are fixed (same URL).
4. **Take:** Give the diagnoser raw traces, not summaries. A secondary summary says raw traces roughly double median accuracy versus scores alone [S] (https://huggingface.co/papers/2603.28052).

## Takeaways for us
- **None of these systems solve our problem.** All of them rely on trial and error with revert, against a benchmark or sandbox (DGM, HGM, Meta-Harness papers above). Exo says plainly that forking does not roll back external effects (data-model page). The step that matters for us is promoting a proved change to the live DB, and none of them has it.
- **Split what the agent can change from what it cannot,** following Exo (data-model and harnesses pages). The agent cannot touch: the event log, the budget meter, the evaluator, the promotion gate and the credentials for the live DB. The agent can change: the diagnosis and planning policy and its own tool definitions.
- **Keep trial and error, but only on the clone or a snapshot,** and keep the clone's evidence in the log. Commit to the live DB once, only if the proof holds. Keep a rejected-candidates archive like DGM's for later diagnosis (https://arxiv.org/abs/2505.22954).
- **Feed raw traces to the diagnoser,** such as query plans and wait events, not aggregate scores (https://arxiv.org/abs/2603.28052).
- **Treat the agent's self-edits as trusted-code risk.** Exo's modules run with no sandbox around them (harnesses page). Our live-DB connection should sit outside any code the agent can modify.
