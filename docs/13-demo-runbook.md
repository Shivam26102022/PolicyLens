# 13. PolicyLens 20-Minute Demo Runbook

> Assignment demo: ten scenarios in about 20 minutes. The table below maps each required scenario to a UI action and its recorded evidence, so every scenario can also be shown from stored artifacts when a live provider call is not authorized.

| # | Required scenario | Show | Recorded evidence (case category or test) |
|---|---|---|---|
| 1 | Factual question with citations | Research tab, India skills-program example | `factual` |
| 2 | Synthesis across sources | Statistics plus report question | `structured_unstructured_synthesis`, `multi_source_synthesis` |
| 3 | Deterministic calculation | Mean or median of unemployment rates | `deterministic_calculation`, `multi_step_tool` |
| 4 | Abstain or clarify | Unanswerable, ambiguous or out-of-scope question | `unanswerable`, `ambiguity`, `out_of_scope`, `stale_time_sensitive` |
| 5 | Conflicting evidence | Conflict status | `conflicting_evidence` (n=1, synthetic) |
| 6 | Prompt injection | Override attempt in the query | `user_prompt_injection`, `retrieved_document_injection` |
| 7 | Failed retrieval or tool | Unavailable or malformed tool | `mcp_timeout_unavailable`, `malformed_tool_response` |
| 8 | MCP discovery and invocation | `make mcp-health`, then the activity trail | `test_mcp_protocol.py` |
| 9 | Invalid arguments and timeout | Unsupported country, fault injection | `invalid_mcp_arguments`, `mcp_timeout_unavailable` |
| 10 | Injection in tool output | Fault-injection wrapper | `mcp_output_injection` |

Scores per category are in [6. Evaluation](06-evaluation-analysis.md). Scenarios 5 and 6 (retrieved document) have a single synthetic case each.

## Preflight

Use the local corpus and current checked-out code. These checks do not call a model or remote data source:

```bash
make data-verify
make retrieval-verify
make mcp-health
make evaluation-verify
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --render-run-id ad3163da-7b37-440d-b317-83b1f0075d97
```

In separate terminals, start `make dev-api` and `make dev-frontend`. Open `http://127.0.0.1:3009`; the API docs are at `http://127.0.0.1:8009/docs`. Confirm the selected model's configuration and consent requirements before any answer request. Do not send a provider request unless the demo owner has explicitly authorized that endpoint and per-turn consent is given.

## Timed Flow

| Time | Demo | Evidence and caveat |
|---|---|---|
| 0-2 min | State the use case: evidence-grounded research over a small, approved corpus, not policy decision automation. | Point to the four PDF reports and structured 2015-2025 series in `docs/data/data-sheet.md`; call out modeled ILO estimates and no OCR. |
| 2-5 min | Walk the architecture from browser to API, retrieval, agent, MCP, and source. | Show the allow-listed read-only `query_statistics` tool and passage resource. Explain that retrieved text and tool output are untrusted; the host checks citation identity/provenance and hides private reasoning. |
| 5-9 min | Open Research, select the India skills-program example, and inspect its source-scoped request. | Ask: "According to the India skills-program report, what were placement rates at training completion and employment rates one to two years later by state?" If a provider is not explicitly authorized, stop before submitting and show the local source preview instead. |
| 9-12 min | Inspect the PDF preview, highlighted citation passage, answer claims, and per-answer activity trail. | Explain that exact passage/provenance checks do not prove semantic entailment; the reader must inspect whether the passage supports the claim. The trail shows safe operational events, not private reasoning or raw tool inputs. |
| 12-15 min | Show a saved session, a follow-up, and the memory controls. | Explain that the backend owns context from at most five completed exchanges; long-term memory is opt-in and treated as untrusted context, never evidence. Do not enter personal or confidential data. |
| 15-18 min | Open Evaluations and `docs/evaluation/evaluation-report.md`. | Latest registered run `ad3163da-7b37-440d-b317-83b1f0075d97` used `agent-v4` and the non-agent baseline (`gpt-6-luna`, seed 0, 67 cases). All-attempt expected-behaviour accuracy is 0.866 for the agent and 0.433 for the baseline (paired difference +0.433, 95% bootstrap [+0.299, +0.567], discordant 31/2, exact McNemar p<0.0001); failed generations count as incorrect. The previous `agent-v3` run (`18454f3c`) scored 0.881 against 0.418; the two agent scores are statistically indistinguishable. AI-judged groundedness is 3.54/5 and relevance 4.58/5 (scored by the generating model, so use them as a screen, not a verdict). Dev/test accuracy is 0.853/0.879 for the agent, so the earlier dev-over-test gap is not present in `agent-v4`. Lowest categories: adversarial citation (0.333) and the single-case conflict and local-model-failure categories (0.000), then invalid MCP arguments, multi-source synthesis, multi-step tool use, unauthorized source and user injection (0.667 each); categories of three or fewer cases are descriptive. All 67 case definitions are human-approved under `reviewer-user`. A 19-answer human review of the deployed app is recorded in `data/manifests/evaluation-review-manifest.json` (rubric: `docs/evaluation/evaluation-review-rubric.md`). |
| 18-20 min | Close with known gaps and the measurement plan. | Prioritize independent answer review and a non-generator judge for the measured `agent-v3` run; do not present unit tests or the offline report renderer as evidence of answer quality. |

## If a Live Answer Is Not Authorized

Skip submission and use the registered run report, local PDF preview, architecture view, and mocked UI tests to demonstrate system boundaries. Do not substitute fixture output for a live result or imply that a historical run measures the current prompt.

## After the Demo

Keep any newly authorized provider run append-only in the evaluation manifest, render its report by run ID, and review its answers separately with the documented rubric. Record material failures with a run-linked regression case. Never overwrite prior runs or label AI-assisted review as independent human validation.
