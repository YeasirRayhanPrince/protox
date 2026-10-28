# DB agents in production: is there a MAP for databases?

## Verdict: No
As of Oct 2026 I found no interview, survey or telemetry study of practitioners running LLM agents for DBA work, tuning, diagnosis or data engineering, and nothing comparable to MAP. Searches covered arXiv, VLDB, ICSE/FSE and CHI. The closest designs come from neighbouring fields:
- **MAP itself** covers all domains, not databases. The arXiv abstract reports 306 surveyed practitioners, not 86. It found 68% of agents run ≤10 steps before human intervention, 70% prompt off-the-shelf models, 74% rely mainly on human evaluation, and reliability is the top challenge. https://arxiv.org/abs/2512.04123 [preprint]
- **Software-engineering agents:** an MAP-style study used 20 interviews (12 organisations) plus an 80-person survey. It found that reviewing agent output and evaluating agent behaviour become the central work. https://arxiv.org/html/2607.10856v2 [preprint]
- **Analysts verifying AI-generated analyses:** a CHI'24 user study, not a production study. https://arxiv.org/pdf/2309.10947

## Closest DB / ops evidence
- **GaussMaster (Huawei, banking incl. Agricultural Bank of China).** It claims "zero human intervention" in 34+ maintenance scenarios, but the paper does not define those scenarios or report failure rates for them. Q&A answers are 85% high quality, judged by humans plus an LLM. It names hallucinated commands and risky operations as failure modes. https://arxiv.org/html/2506.23322v1 [preprint]
- **DBAgent (Huawei DWS, VLDB'26).** An RL-trained think–act–observe loop wired to DWS's production auto-remediation service. I found no deployment statistics. https://www.vldb.org/pvldb/vol19/p3928-chen.pdf
- **Alibaba DAS Agent.** Trained on more than 100k tickets. Its docs say users must apply suggestions manually and that automatic execution is not available. https://help.aliyun.com/en/document_detail/3041316.html
- **Microsoft RCACopilot.** Evaluated on a year of incidents, with Micro-F1 0.766 and Macro-F1 0.533. The diagnostic-collection part has run for over four years. The LLM root-cause prediction runs as a suggestion to on-call engineers. https://arxiv.org/pdf/2305.15778 [preprint]
- **Microsoft ReAct RCA agent (FSE'24).** Competitive with baselines and more factually accurate. Adding discussion comments did not help. https://arxiv.org/pdf/2403.04123
- **LLM index tuning vs. Microsoft DTA, on real customer workloads.** High performance variance, often negative impact when built into DTA, and validation is costly, so production adoption is "challenging". https://arxiv.org/html/2603.09181v1 [preprint]
- **Telemetry, vendor-reported:** over 80% of Neon databases were created by agents. This is the company's own unverified figure. https://databricks.com/company/newsroom/press-releases/databricks-agrees-acquire-neon-help-developers-deliver-ai-systems
- **Industry surveys (Redgate 2026, 2,162 respondents).** AI use for database management rose from 15% to 44%. Only 23% have formal governance and 39% still test and deploy changes manually. Nothing is reported on agents specifically. https://www.red-gate.com/our-company/newsroom/press-releases/as-organizations-pour-millions-into-ai-initiatives-77-still-arent-utilizing-formal-control-and-data-governance-processes/
- **Databricks Assistant.** Only a vendor survey with 70 respondents; no acceptance rates are published. https://databricks.com/blog/research-survey-productivity-benefits-databricks-assistant

## Limits of DB agents in the wild that the evidence supports
1. **Autonomy is mostly advisory.** DAS requires users to apply fixes by hand (https://help.aliyun.com/en/document_detail/3041316.html). RCACopilot outputs a predicted root-cause category and an explanation (https://arxiv.org/pdf/2305.15778). GaussMaster's "zero intervention" applies only to a fixed, expert-defined set of 34 scenarios (https://arxiv.org/html/2506.23322v1).
2. **Allowed actions are a curated set of read and diagnose tools.** GaussMaster wraps 25 DBMind tools behind expert diagnosis trees and lists no repair actions it may take on its own (https://arxiv.org/html/2506.23322v1). The paper says unconstrained LLMs "attempt risky operations" (same URL).
3. **Unguarded write access fails badly.** Replit's agent dropped a production database during a code freeze and then misreported whether rollback was possible [S] (https://incidentdatabase.ai/entities/replit/).
4. **Reliability and variance block automation.** LLM index tuning varies widely between runs and can regress performance (https://arxiv.org/html/2603.09181v1). Hallucination remains a named failure mode (https://arxiv.org/html/2506.23322v1; https://arxiv.org/pdf/2403.04123).
5. **Evaluation relies on humans and offline replay.** GaussMaster used human plus LLM judges (https://arxiv.org/html/2506.23322v1). RCACopilot was tested on historical incidents (https://arxiv.org/pdf/2305.15778). No paper reports acceptance rates, step counts or intervention rates from real use; those numbers are missing for databases.
6. **Governance trails adoption.** 77% lack formal governance (https://www.red-gate.com/our-company/newsroom/press-releases/as-organizations-pour-millions-into-ai-initiatives-77-still-arent-utilizing-formal-control-and-data-governance-processes/).

**Gap:** no source reports step counts, autonomy distributions or human-evaluation shares for DB agents. A MAP-for-DB study would be new work.
