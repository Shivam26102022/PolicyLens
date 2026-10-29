# 11. PolicyLens System Card

> Assignment submission artifact: system card covering intended use, limits, models, data, evaluation and risks. Numbers come from [6. Evaluation](06-evaluation-analysis.md).

## System summary
PolicyLens is an evidence-grounded research assistant for youth and general labour-market policy questions over a small approved corpus: ILOSTAT/World Bank unemployment statistics (SGP, MYS, IDN, IND, 2015–2025) and four World Bank PDF reports. See `docs/data/data-sheet.md` for provenance and licences.

- **Generation model:** configured chat model (currently an Azure/Foundry OpenAI deployment, `gpt-6-luna`) used through the `openai-agents` SDK, plus an optional loopback MLX route. Reasoning effort is `none` and the output is capped at 1,200 tokens, to keep latency and cost low on a task that is extraction and citation, not open reasoning. Sampling temperature is left at the provider default because the deployment rejects `temperature=0`.
- **Embeddings:** local `BAAI/bge-small-en-v1.5`, so corpus text never leaves the machine. External embeddings need explicit per-run consent.
- **Prompt:** `prompts/agent/system-v3.md` (`agent-v3`). The host removes recognized instruction-like clauses from provider-facing content, blocks injection-only and sensitive-data requests, and validates MCP rows/warnings before model exposure. These deterministic changes are covered offline; the current prompt has not had a live quality run.
- **Workflow:** a bounded state machine (RECEIVED → … → terminal) with at most 8 tool calls, 4 per tool, 1 retry, 6 turns and a 90 s deadline. The one tool, `query_statistics`, runs over a read-only MCP server and is deterministic.

## Intended use
- Exploratory research by policy analysts: find what the approved sources say, compute simple statistics, and see exactly which passage or data row supports each claim.
- A human reads the cited evidence before any claim is reused.

## Out-of-scope use
- Final authority for legal, regulatory, eligibility, enforcement, benefits or funding decisions.
- Questions on topics, countries or years outside the corpus. The system should abstain, not extrapolate.
- Personal, confidential or classified data. Do not upload any.
- Image generation and open-ended chat (blocked by a guard).

## Known limitations
- The corpus is small (4 countries, 4 PDF reports). Retrieval results cover 40 anchored cases; Recall@5 is about 0.54-0.58 across tested modes/chunkers, with overlapping bootstrap intervals. No method is shown to be better.
- Latest registered run `ad3163da-7b37-440d-b317-83b1f0075d97` used `agent-v4` and the non-agent baseline (`gpt-6-luna`, seed 0, 67 cases). All-attempt expected-behaviour accuracy is 0.866 for the agent and 0.433 for the baseline (paired difference +0.433, 95% bootstrap [+0.299, +0.567], discordant 31/2, exact McNemar p<0.0001); failed generations count as incorrect. The previous `agent-v3` run (`18454f3c`) scored 0.881 against 0.418; the two agent scores are statistically indistinguishable. AI-judged groundedness is 3.54/5 and relevance 4.58/5 (scored by the generating model, so use them as a screen, not a verdict). Dev/test accuracy is 0.853/0.879 for the agent, so the earlier dev-over-test gap is not present in `agent-v4`. Lowest categories: adversarial citation (0.333) and the single-case conflict and local-model-failure categories (0.000), then invalid MCP arguments, multi-source synthesis, multi-step tool use, unauthorized source and user injection (0.667 each); categories of three or fewer cases are descriptive. All 67 case definitions are human-approved under `reviewer-user`. A 19-answer human review of the deployed app is recorded in `data/manifests/evaluation-review-manifest.json` (rubric: `docs/evaluation/evaluation-review-rubric.md`). Expected-behaviour accuracy does not measure semantic answer quality. See `docs/evaluation/evaluation-report.md`.
- Modelled ILO estimates are not survey measurements; periods and definitions differ between sources.
- The model can still write fluent claims that over-read the excerpt. The excerpt check proves the text exists in the passage, not that the claim follows from it.

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Hallucinated or uncited claims | Typed output; every claim needs verified excerpts or calculation ids; failure becomes `failed_safe` or `conflict`. |
| Prompt injection (query, passage, memory, tool output) | Untrusted-content instructions, host redaction of recognized injection clauses, sensitive-request blocks, allow-listed read-only tools, validated MCP rows/warnings, and passage hash checks. Heuristic redaction does not solve novel or obfuscated injection. |
| Provider safety filter or outage | Content-filter rejections map to `blocked`/`POLICY_BLOCKED`; outages map to `MODEL_UNAVAILABLE`; there is no silent fallback to another provider. |
| Arithmetic errors | All calculations are done in deterministic code and shown with formula, rounding and input rows. |
| Compromised MCP server | Stdio subprocess only; pinned name, version, protocol, tool schema hash, and resource allow-list; result identity checked. |
| Data leakage to third parties | External model needs explicit consent; secrets stay server-side; logs record safe metadata, not question text. |
| Memory poisoning | Hot and warm memory are marked untrusted and never count as evidence; warm memory is opt-in and per workspace. |
| Over-trust | Answers separate source claims, deterministic calculations and uncertainty; statuses include abstain, clarify and conflict. |

## Oversight
All tools are read-only, so no action needs approval. Any future consequential tool (write, send, export) must require explicit user confirmation before execution.
