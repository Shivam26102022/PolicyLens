# PolicyLens Documentation: Assignment Map

Organised to follow **Tech Challenge – GenAI Engineer v1.0** (PDF in the repository root). One document per assignment section. Numbers come from run `ad3163da-7b37-440d-b317-83b1f0075d97` (`agent-v4`: 0.866 against a non-agent baseline of 0.433, 67 cases).

| Assignment section | Document | Code |
|---|---|---|
| §1 Problem framing, users, hypotheses | [01 Problem framing](01-problem-framing.md) | n/a |
| Data sheet (artifact) | [02 Data sheet](02-data-sheet.md) | `apps/backend/src/policylens/ingestion/` |
| §3 RAG pipeline | [03 RAG pipeline](03-rag-pipeline.md) | `retrieval/` |
| §4 GenAI experiments | [04 GenAI experiments](04-genai-experiments.md) | `prompts/`, `scripts/evaluate_suite.py` |
| §5 Agentic workflow | [05 Agentic workflow](05-agentic-workflow.md) | `agent_runtime/` |
| §6 Evaluation (25%) | [06 Evaluation analysis](06-evaluation-analysis.md) | `data/evaluation/feature007-cases.json` |
| §7 Responsible AI | [07 Responsible AI](07-responsible-ai.md) | `scripts/security_audit.py` |
| §8 GenAI concepts | [08 GenAI concepts](08-genai-concepts.md) | n/a |
| §9 MCP integration | [09 MCP integration](09-mcp-integration.md) | `services/mcp-policy-data/` |
| §10 Reproducibility | [10 Reproducibility](10-reproducibility.md) | `Makefile`, `.github/workflows/ci.yml` |
| System card (artifact) | [11 System card](11-system-card.md) | n/a |
| Section 2 (1–2 pages) | [12 Section 2](12-section2-innovation.md) | n/a |
| Demo (10 scenarios, 20 min) | [13 Demo runbook](13-demo-runbook.md) | n/a |
| Limitations | [14 Limitations](14-limitations.md) | n/a |

Reading order for a 15-minute review: 01, 06, 03, 05, 07, 09, 14.

Gaps stated openly: no human answer review (0 of 67), the judge is the generating model, several categories have n ≤ 3, and the corpus is four countries and four reports.

## Evidence and generated files (do not hand-edit)

[Evaluation report](evaluation/evaluation-report.md), [retrieval evaluation](evaluation/retrieval-evaluation.md), [retrieval re-run with reranker](evaluation/retrieval-rerank-run-report.md), [agent evaluation](evaluation/agent-evaluation.md), [provider comparison](evaluation/provider-comparison.md), [review rubric](evaluation/evaluation-review-rubric.md), [EDA](data/eda/results.md), [architecture](architecture/architecture.md), [diagram](architecture/architecture-diagram.md), [ADR-005-01 MCP vs direct](architecture/adr/ADR-005-01-mcp-vs-direct.md), [threat model](security/threat-model.md), [residual risks](security/security-residual-risks.md), [privacy and retention](security/privacy-retention.md). Scripts write or parse these paths.
