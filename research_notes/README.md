# Research notes: holistic, zero-regression DB optimization harness

Start with [`DECISIONS.md`](DECISIONS.md): the problem, decisions so far, open questions, papers read.

| Path | What |
|---|---|
| `DECISIONS.md` | Living design log (update it as decisions are made) |
| `Holistic database optimization harness/` | First research pass: prior tuners, LLM DBA agents, harness prior art, formalization |
| `Harness landscape gap evaluation/` | Harness landscape: Exo/RSI, coding agents, RL rollout frameworks, DB vendor agents, observation tools |
| `Agent DB interaction/` | How agents interact with DBs in production: sources A–D, deep dives D1–D3, Unknown 1 (agent traffic) U1 |
| `../reports/` | Synthesized reports for the first two passes |
| `artifacts/site/` | Source of the published research pages (claude.ai artifact `3mumJpFN1z8zGbj4ELpdVd`) |
| `artifacts/deck/project/` | Source of the slide deck (claude.ai artifact `4EfmW3neceYKLQc5h2VHp4`) |

## Rebuilding pages

The `source-*`, `d*-*` and `u1-*` pages are generated from the `Agent DB interaction/` notes:

```bash
cd research_notes/artifacts/site
python3 -I build_sources.py .   # source-a..d
python3 -I build_pages.py .     # d1..d3, u1-*
```

The other pages (`holistic-db-harness.html`, `problem-definition.html`, `zero-regression.html`,
`harness-gaps.html`, `agent-db-interaction.html`, `u1-traffic.html`) are hand-written.
The published artifacts may have edits made in the claude.ai page editor; read the live version before republishing.

Downloaded papers and raw trace data were not committed (copyright, size); they are cited by URL in the notes.
