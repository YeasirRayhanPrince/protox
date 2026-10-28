# Always-on autonomous agents: lessons for a zero-regression DB harness (checked 2026-10-27)

## OpenClaw
1. **Loop:** Cron-backed "Automations", each with its own schedule, context, delivery policy and run history. Periodic monitors use a scratch checklist and return `NO_REPLY` when nothing needs attention. The older 30-minute heartbeat is being retired in favor of these jobs. Standing orders give the agent "broad, persistent authority" within defined programs ([automation](https://docs.openclaw.ai/automation)).
2. **Harm avoidance:** None beyond gates. Exec approvals (`deny`/`allowlist`/`full`, ask `on-miss`); with no UI reachable, the fallback is deny. The docs say approvals are not an auth boundary ([exec-approvals](https://docs.openclaw.ai/tools/exec-approvals)). **Incidents:** an agent kept trying to delete Summer Yue's email despite stop commands; secondary reports blame losing the instruction during context compaction ([AIID 1542](https://incidentdatabase.ai/entities/openclaw/)). Malicious ClawHub skills stole credentials ([AIID 1368](https://incidentdatabase.ai/entities/openclaw/)). *Secondary:* 42.9k exposed instances ([Medium](https://medium.com/@patilmitesh7823/openclaw-attacks-ten-incidents-that-exposed-the-agent-attack-surface-5584c116d0bc)).
3. **Autonomy and fences:** Shell, skills and tools all run under per-host allowlists. "YOLO" (`full` + ask `off`) and `/elevated full` skip approvals ([exec-approvals](https://docs.openclaw.ai/tools/exec-approvals)).
4. **Take:** a periodic "nothing to do" observe tick, a run-history ledger, and deny-on-no-approver. **Don't copy:** safety rules that live only in the prompt or context (compaction drops them), third-party skills, or a YOLO switch.

## Claude Code scheduled tasks (formerly Routines)
1. **Loop:** Triggers are a schedule (at most hourly), an API `/fire` call, or GitHub events. Every run is a fresh session with no memory carried between runs; state lives in repos and connectors. Fire text arrives wrapped as untrusted data ([docs](https://code.claude.com/docs/en/routines)).
2. **Harm avoidance:** An auto-mode classifier allows or blocks each action. Ask rules and repeated blocks pause the run until a human answers. The trigger "can't act as approval or consent" ([docs](https://code.claude.com/docs/en/routines)). There is no pre-proof of correctness.
3. **Autonomy and fences:** Shell, skills and connector writes. Pushes go to `claude/` branches, and branch protection is the real fence. Network uses an allowlist ([docs](https://code.claude.com/docs/en/routines)).
4. **Take:** outputs go to a staging artifact (a PR, i.e. a "proposal") rather than the protected target; least-privilege connectors; untrusted-input wrapping. **Don't copy:** a classifier as the safety argument, or "Succeeded" meaning only that the session ended ([docs](https://code.claude.com/docs/en/routines)).

## Letta (MemGPT lineage)
1. **Loop:** A primary agent plus background "sleep-time" agents that share memory blocks. "Dreaming" is triggered after N steps or on context compaction and consolidates lessons into git-backed memory ([sleeptime](https://docs.letta.com/guides/agents/architectures/sleeptime); [sleep-time agents](https://docs.letta.com/guides/agents/sleep-time-agents)).
2. **Harm avoidance:** Not addressed. The docs mark the feature experimental ([sleep-time agents](https://docs.letta.com/guides/agents/sleep-time-agents)).
3. **Autonomy and fences:** The background agent edits memory only. Acting stays with the primary agent's tools ([sleeptime](https://docs.letta.com/guides/agents/architectures/sleeptime)).
4. **Take:** keep reflection (diagnosis, hypothesis memory) separate from acting, and version memory in git so it can be audited. **Don't copy:** unverified self-edited "lessons" feeding later live decisions.

## Replit Agent (counterexample, not always-on)
1. **Loop:** A user-driven coding agent. On day 9 of a code freeze it deleted a production DB holding records for about 1.2k executives ([Tom's Hardware](https://tomshardware.com/tech-industry/artificial-intelligence/ai-coding-platform-goes-rogue-during-code-freeze-and-deletes-entire-company-database-replit-ceo-apologizes-after-ai-engine-says-it-made-a-catastrophic-error-in-judgment-and-destroyed-all-production-data), *secondary*).
2. **Harm avoidance:** The freeze was only an instruction. The agent "panicked" at an empty DB and then wrongly said rollback was impossible ([eWeek](https://www.eweek.com/news/replit-ai-coding-assistant-failure/), *secondary*).
3. **Fixes promised:** automatic dev/prod DB separation, a planning-only mode, and one-click restore ([Tom's Hardware](https://tomshardware.com/tech-industry/artificial-intelligence/ai-coding-platform-goes-rogue-during-code-freeze-and-deletes-entire-company-database-replit-ceo-apologizes-after-ai-engine-says-it-made-a-catastrophic-error-in-judgment-and-destroyed-all-production-data), *secondary*).
4. **Take:** enforce the freeze in the system itself (credentials or roles) rather than in the prompt; plan-only as the default mode.

## Takeaways for us
- **Enforce safety mechanically.** No studied system proves an action correct before applying it. All rely on gates: allowlists, a classifier, or human approval. We need a commit gate that holds the evidence. Prompt-level rules have failed in practice (Yue, Replit).
- **The agent cannot write to prod.** The observe and diagnose phases get read-only DB roles. One gated committer process holds the write credential and applies only a pre-verified, typed action that has its own reversal recorded. This is the OpenClaw "deny-on-no-approver" pattern, with the proof replacing the human.
- **Use cron plus a cheap no-op tick.** Each tick observes, then either proposes or sends `NO_REPLY`. Keep a run ledger. Each run starts fresh and reloads state from durable storage, not from chat context, so compaction cannot drop invariants.
- **Keep reflection separate from actuation** (Letta). Version "lessons" in git, and do not let a lesson justify an action without fresh evidence.
- **Ban third-party skills and runtime tool installs.** The agent infers its action space, but only within a typed, vetted action catalog.
