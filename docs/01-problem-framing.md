# 1. Problem Framing and Experimental Design

> Assignment §1: target users, decisions, scope, assumptions, success criteria, failure modes, a non-LLM baseline, and a leakage-safe split.

## Problem

Policy researchers work with statistics and reports that are incomplete, inconsistent and hard to search. PolicyLens answers analytical questions over a small approved corpus, shows the exact source passage or data row behind every claim, and says so when the evidence is insufficient.

## Users, decisions and scope

| Item                | Definition                                                                                                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target users        | Policy researchers and analysts preparing briefings on youth and general unemployment in Southeast and South Asia.                                                                          |
| Decisions supported | Which sources and figures to cite in a briefing; which questions need more research. PolicyLens makes no policy decision.                                                                   |
| In scope            | Four countries (SGP, MYS, IDN, IND), modelled ILO unemployment series for 2015–2025, and four World Bank PDF reports ([data sheet](02-data-sheet.md)).                                      |
| Out of scope        | Other countries, years or topics; legal, eligibility, benefits, funding or enforcement determinations; personal or confidential data; open-ended chat. See [limitations](14-limitations.md). |

## Assumptions

- All content is public. Nothing confidential is used. The Singapore MOM youth report is excluded because its reproduction rights are unconfirmed.
- Users prefer an honest abstention to a plausible but unsupported answer.
- The reader inspects the cited passage before reusing a claim. An exact-excerpt check proves the text exists in the source, not that the claim follows from it.

## Hypotheses and measurable success criteria

Status is taken from the [evaluation report](evaluation/evaluation-report.md) (run `ad3163da…`, `agent-v4`). Case counts per category are small, so these are descriptive, not conclusive. See [evaluation analysis](06-evaluation-analysis.md).

| #  | Hypothesis                                                                      | Measure                                                             | Target                                         | Status                                                                                                                                                                                                                                                       |
| -- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| H1 | Hybrid retrieval beats keyword-only and dense-only.                             | Recall@k, MRR, nDCG, bootstrap 95% CI (40 cases).                   | Hybrid above both with non-overlapping CIs.    | **Directional, not significant.** Hybrid Recall@k is 0.688–0.713 against 0.629–0.675 for BM25 and 0.637–0.662 for dense (run `ad3163da`), but every interval overlaps.                                                                                                                              |
| H2 | Structure-aware chunking beats fixed-size chunking.                             | Same metrics.                                                       | Higher Recall@k.                               | **Not supported.** Recall@k is 0.629–0.713 across the nine non-reranked configurations with overlapping intervals; chunker choice does not separate them.                                                                                                                                                          |
| H3 | The tool-using agent beats the non-agent baseline on calculation and synthesis. | Expected-behaviour accuracy by category (67 cases).                 | Agent ≥ baseline on multi-step and synthesis. | **Partly supported.** Overall 0.866 against 0.433, paired difference +0.433 (95% CI [+0.299, +0.567]). Synthesis: 1.000 against 0.000 (structured plus unstructured) and 0.667 against 0.000 (multi-source), n=3 each. Multi-step: 0.667 against 1.000 (n=3), so the multi-step part of the target is not met. |
| H4 | Verified excerpt citations remove unsupported claims.                           | Citation validity; `CITATION_INVALID` rate; human citation score. | 0 uncited factual claims released.             | **Partly supported.** The host blocks uncited or non-verbatim claims. A 19-answer human review scores citation correctness (mean 3.68/5); claim-to-excerpt support is the open part.                                                                                                                                  |
| H5 | The system abstains on unanswerable, out-of-scope and unauthorised requests.    | Behaviour accuracy on those categories.                             | ≥ 0.9                                         | **Met, low n.** 14/15 = 0.933 across unanswerable, out-of-scope, unauthorised-source, sensitive-data and ambiguity (3 cases each); the one miss is a provider error (`MODEL_UNAVAILABLE`), not an unsafe answer.                                                                                                                                 |

## Key failure modes

| Failure mode                                                   | Where it is handled                                                                                          |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Retrieval miss or wrong period                                 | Hybrid retrieval plus per-passage verification; abstain when evidence is missing ([RAG](03-rag-pipeline.md)). |
| Stale data or modelled-estimate-versus-survey confusion        | Source metadata and caveats carried into answers ([data sheet](02-data-sheet.md)).                            |
| Arithmetic error                                               | All maths is deterministic code behind one MCP tool ([agent](05-agentic-workflow.md)).                        |
| Citation that does not support the claim                       | Exact-excerpt check; semantic entailment is an open risk.                                                    |
| Conflicting sources reconciled silently                        | `conflict` status requires both sides cited; differing definitions are flagged, not merged.                |
| Instruction injected via query, passage, memory or tool output | Untrusted-content handling and host guards ([responsible AI](07-responsible-ai.md)).                          |
| Sensitive or unauthorised data request                         | Deterministic block before the model.                                                                        |
| Tool failure, timeout or malformed result                      | Bounded retry, then fail-safe status ([agent](05-agentic-workflow.md), [MCP](09-mcp-integration.md)).          |
| Provider safety-filter rejection or outage                     | Mapped to `blocked` or `MODEL_UNAVAILABLE`; no silent fallback.                                          |

## Baselines

1. **Retrieval, non-LLM:** BM25 keyword search. Dense and hybrid are compared against it.
2. **Generation, simple:** a non-agent generator (retrieve, then answer in one structured call, no tools), prompt `non-agent-v1`. The agent (`agent-v3`) is compared against it on the same 67 cases.

## Data splits and leakage control

- Every evaluation case is labelled `dev` (34) or `test` (33) in `data/evaluation/feature007-cases.json`.
- Prompts, chunking and retrieval parameters are tuned on `dev` only. `test` is run once per release after parameters are frozen and recorded in the run manifest (index version, chunking, prompt version, model, seed).
- Cases are written from approved source anchors. Near-duplicate cases stay in the same split.
- Case labels, reference claims, splits and review status are never placed in a runtime request.
- Synthetic fixtures (injection passages, conflict data, fault injections) are labelled synthetic and never used as source content.
- **Known leakage risk:** the model may have seen World Bank and ILO text in pre-training, so a correct answer does not prove retrieval worked. The corpus-anchored exact-excerpt check and the unanswerable cases guard against this.
- **Scope note:** agent dev/test accuracy is 0.853/0.879 on `agent-v4`; the earlier `agent-v3` run showed a dev-over-test gap (0.941/0.818), which this run does not repeat.
