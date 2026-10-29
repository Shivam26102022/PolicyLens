# Feature 009 Quickstart

Feature 009 introduced an accessible research workbench over the existing local backend. The current workbench also includes Feature 011's persistent sessions and workspace-scoped memory; use [Feature 011's quickstart](../011-session-memory/quickstart.md) for the full storage and memory workflow. Neither feature adds provider credentials to the browser, runs evaluations from the UI, or calls a model directly.

## Prerequisites

- Backend and frontend dependencies installed with `make setup`.
- Backend `.env` configured with at least one supported generation provider and the local retrieval index available for full answers.
- The selected MLX service, when used, is reachable only at the configured loopback address.
- Standard OpenAI uses Responses API. Custom Foundry endpoints default to Chat Completions; set `OPENAI_USE_RESPONSES_API=true` only after confirming the configured deployment supports the Responses endpoint, then restart the API. The default remains `false`, and no route fallback occurs.

## Start the services

Terminal 1:

```bash
make dev-api
```

Terminal 2:

```bash
make dev-frontend
```

Open `http://127.0.0.1:3009`.

## Verify backend contracts

```bash
curl -sS http://127.0.0.1:8009/model/options
curl -sS http://127.0.0.1:8009/health/ready
curl -sS http://127.0.0.1:8009/evaluation/summary
```

Model options contain provider/model identifiers and safe availability metadata only. OpenAI answer requests require a per-run consent field; selecting OpenAI is not consent. The evaluation endpoint returns aggregate summaries only and does not start a run.

The Research page keeps saved chats in a left column and the conversation plus message box in the main column. At narrow widths, the page becomes one column. The main flow is simple: open or start a chat, ask a question, then continue with **Send follow-up**. **New chat** starts without the previous chat's context. Example prompts fill the message box and automatically scope the submitted request to their exact PDF source; they never submit a request on their own. Editing an example question clears its source scope.

The composer has no search-method, answer-depth, PDF-source, country, or year controls. It uses Hybrid retrieval and Standard reasoning (`none`) for every request. PDF examples retain a source-ID scope while ordinary questions search the full corpus. The long-term-memory toggle shows whether cross-chat memory is on, while **Manage memory** contains clear and delete actions. Memory is off by default, and external generation or embedding requires fresh consent for each turn.

On the Responses API, the configured output-token limit is the Standard baseline. Backend requests at other supported effort levels scale that ceiling by 2x, 4x, and 8x, capped at 8,000 tokens, because reasoning and the final structured answer share the provider's output-token budget. This is a ceiling, not a target; actual usage remains provider-reported. The Research UI currently submits Standard only. Custom Responses-compatible endpoints receive the requested `reasoning.effort` without the optional `reasoning.summary` request; official OpenAI Responses requests may ask for the SDK summary. Chat Completions exposes Standard only.

The Responses API route uses explicit application-managed session context rather than provider-managed `previous_response_id` state. Follow-ups are persisted by the backend, which selects at most the five latest completed exchanges; older messages remain visible in the full transcript and the browser does not send that transcript wholesale. Every answer searches current evidence. Local Chroma/BM25 ranking remains in the backend, and hybrid results can be reordered by the local cross-encoder after permission filtering (maximum 20 candidates); model failures retain hybrid order. Before generation, selected passages are fetched through the registered Policy Data MCP resource and checked against the ranked text, hashes, and provenance. Missing or mismatched passages stop safely. During a run, the **Agent trail** shows live safe processing activity; after completion, each assistant message has an expanded-by-default activity summary with a clear collapse/reopen control. It contains only that message's retrieval/reranking, MCP passage verification, model, memory, validation, and read-only statistics events. Reranker model, candidates scored, duration, and safe fallback are visible; private reasoning content, prompts, raw tool arguments, and evidence payloads are not. The per-answer trail identifies API route and reasoning effort and displays provider-reported token counts. Responses API runs may show the SDK-generated reasoning summary when the provider returns it; Chat Completions displays why that summary is unavailable. Browser cancellation stops waiting and does not guarantee provider work has stopped.

Corpus claims may be concise model-written summaries rather than verbatim quotes. Their citations contain exact bounded excerpts from passages selected and verified for that run, with source metadata assembled by the backend. If the model's excerpt hint does not match the passage exactly, the backend replaces it with a passage excerpt before validating passage identity and provenance. The validator does not prove semantic entailment, so open the linked passage when reviewing a paraphrase. If validation rejects a citation, the trail reports a safe reason code without storing or displaying the rejected model draft.

Check **System status** for the current MCP readiness summary. Readiness preserves component details when `/health/ready` returns HTTP 503; generation readiness reflects configuration of the selected model and does not claim that a remote provider is reachable. Workspace labels describe storage scope, not model execution location.

## Browser scenarios

1. Open Research and click an example prompt. Confirm it fills the composer, sends no request until Submit, and the submitted request carries the matching PDF source ID. Edit the question and confirm its source scope is cleared.
2. Select a configured local model and submit a synthetic factual question. Confirm the request uses Hybrid retrieval and Standard reasoning, and that the answer, citations, trace ID, and safe retrieval/tool/validation activity render.
3. Select OpenAI generation and/or external embeddings. Confirm no request is sent before approval and that each follow-up requires fresh consent; the browser request includes consent flags but no credentials.
4. After the first answer, select **Send follow-up** and inspect its request payload. Confirm it includes the active session ID and an empty caller-supplied conversation; the backend owns the five-exchange context bound. Reload and verify the saved transcript and latest response are restored.
5. Acknowledge the data-use notice before storing only public, synthetic, or appropriately anonymized content. Enable or pause long-term memory, then open **Manage memory** to confirm before clearing memories or deleting a chat.
6. Exercise answer, abstention, conflict, unavailable provider, timeout, local cancellation, and offline fixtures. Local cancellation aborts the browser wait; it does not guarantee the backend/provider stopped before the configured timeout.
7. Open Evaluations with populated, blocked, empty, and malformed manifests. Confirm null and missing metrics are not shown as zero and no evaluation is triggered.
8. Open Architecture and inspect UI/API, retrieval, runtime/state, tool/MCP, provider, validation, evaluation, and logging layers; confirm run state and backend-managed session context are accurately described.
9. Use keyboard-only navigation at desktop and a 320 CSS-pixel viewport; confirm focus, status announcements, one-column Research layout, and no horizontal page overflow.
10. With a mocked Responses API answer, confirm its activity trail is open by default, collapse and reopen it, then inspect route, effort, input/output/reasoning/cached/total token counts, and summary text. With a Chat Completions answer, confirm token usage appears when returned and the missing-summary explanation is explicit. Never use a live external request for this UI check.

## Validation

```bash
npm --prefix apps/frontend run build
npm --prefix apps/frontend test
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run typecheck
uv run --locked --package policylens pytest apps/backend/tests/api/test_model_options.py apps/backend/tests/unit/test_model_gateway.py apps/backend/tests/unit/test_agent_state.py apps/backend/tests/unit/test_mlx_provider.py apps/backend/tests/api/test_evaluation_summary.py apps/backend/tests/api/test_agent_api.py
npm --prefix apps/frontend run test:e2e
make check
make security-verify
make retrieval-verify
make evaluation-verify
```

Playwright tests use mocked backend contracts and make no provider requests. See [contracts](contracts/) and [data-model.md](data-model.md) for response shapes and state boundaries. Feature 011's synthetic memory-ranking evaluation is documented separately and is not a production Chroma or answer-quality benchmark.

## Verified Results (refreshed 2026-10-28)

- `make check` passed formatting, lint, type checks, **300 backend tests**, **39 MCP tests**, **131 script tests**, **68 frontend tests**, and repository traceability.
- `make security-verify` passed **148 selected backend/security/evaluation tests**, **13 MCP tests**, production build, **68 frontend tests**, and secret scanning with no findings.
- `npm --prefix apps/frontend run test:e2e` passed all **11 mocked browser tests**, including persisted-session resume/follow-up, memory controls, provider consent, evaluation states, keyboard navigation, and the 320 CSS-pixel layout.
- The System Status regression tests cover structured degraded HTTP 503 responses without rendering internal details.
- `make retrieval-verify` reported `status: ready`. `make evaluation-verify` validated **36 approved cases across 20 categories and both splits**, with `release_eligible=true` and `live_requests_made=false`.
- The synthetic memory evaluation reported macro precision@5 **0.2667** and recall@5 **0.6667**; the empty no-memory baseline scored **0.0000** for both. Latest fixture-ranking latency was **0.0730 ms mean / 0.1151 ms max**; this is not production Chroma or embedding latency. See [Feature 011 evaluation results](../011-session-memory/evaluation-results.md) for stratified results and limitations.
- Selected passages are re-read through the registered Policy Data MCP resource and checked against local ranking before generation; the per-answer trail reports verified passage counts or specific safe mismatch/catalog errors. PDF citation actions and answer Markdown links open the same in-app iframe preview. Registered World Bank item-page URLs resolve to `/sources/{source_id}/pdf`, which serves the existing hash-verified local report inline; the browser no longer embeds `documents1.worldbank.org`. A matching citation supplies the page and excerpt search, and the excerpt remains highlighted in the dialog and citation card. Links without structured citation metadata open the PDF without claiming an excerpt highlight. A new-tab fallback is available.
- Browser tests use mocked backend contracts. The live AI-judged evaluation below explicitly made provider and MCP requests.
- The per-answer trail regression is covered by the focused UI tests and mocked browser suite; each answer retains its own safe event trail after session reload.

### Earlier structured-data prompt retrieval and MCP smoke check

The original four structured-data examples were run against the active local hybrid retrieval index with local embeddings. Every selected passage was then read from the repository's actual Policy Data MCP stdio server and passed the production identity, content, and provenance validation. No mock evidence or model/provider requests were used. These were historical retrieval checks; the current UI examples now target PDF content.

| Example prompt | Retrieved / MCP verified | Observed result |
|---|---:|---|
| Compare Singapore youth unemployment in 2020 and 2025 | 6 / 6 | Singapore youth rows for 2020 and 2025 ranked first; total-unemployment rows also appeared in the top six. |
| Find an estimate for one country | 2 / 2 | India's 2025 youth estimate ranked first; a total-unemployment row also appeared. |
| Clarify an indicator | 5 / 5 | Relevant youth-indicator rows were retrieved, along with some less relevant passages. |
| Explore workforce training evidence | 6 / 6 | Relevant training and employment evidence came from four sources. |

In that earlier check, the first example named Singapore and applied the `SGP` country filter; this removed the original geography ambiguity, but the result set still contained a different unemployment indicator. The India example had the same indicator-mixing limitation. These checks show that retrieval and MCP passage verification succeeded; they did not reproduce the earlier `TOOL_INVALID_ARGUMENTS` statistics-tool failure, which occurs later in answer generation. The original prompt omitted a geography, while the statistics tool requires 1 to 4 unique uppercase ISO3 geographies, making that a plausible cause but not a confirmed one: the safe event does not retain which argument failed. The per-answer trail now displays the tool's validation requirements without exposing raw arguments. The configured provider is OpenAI, so no model request was made without fresh per-run consent; answer generation remains unverified.

### Current PDF-focused sample questions

The eight current UI examples name topics present in the four enabled local PDFs, and each applies the corresponding manifest `source_id` as a retrieval filter. I checked the report text locally; this verifies the question topics and filter mapping, not live retrieval ranking or model answers. No provider endpoint was called.

| PDF | Topics used by the sample questions |
|---|---|
| India skills-program report | Placement at training completion and employment 1–2 years later by state (Table 8); classroom plus practical or apprenticeship training and employment outcomes (Executive Summary). |
| Malaysia informal-employment report | Informal-sector vs. informal-employment definitions (Sections 2.1–2.2); protection and productivity recommendations (Section 4.1). |
| Indonesia Jobs Action Program | Youth unemployment, job creation, and labor-market skills; effects of labor regulations on employers, workers, and job creation (opening report pages). |
| Singapore SABER workforce-development report | Government, union, and stakeholder partnership; workforce-development benchmarks for 1970, 1990, and 2010 (Executive Summary). |

### PDF preview and source-filter regression (fresh)

- `uv run --locked --package policylens pytest apps/backend/tests/api/test_source_files.py apps/backend/tests/api/test_retrieval_api.py -q`: **13 passed**. The PDF route tests cover local hash verification, inline disposition, byte ranges, CORS, unapproved sources, path traversal, and changed file content.
- A local API smoke test served the stored India report as **775,995 bytes** with `application/pdf`; it made no remote request.
- `npm --prefix apps/frontend test -- tests/research.test.tsx`: **34 passed**. Regressions cover the India sample's `source_ids` request payload, removed composer controls and fixed defaults, edited-example scope clearing, canonical item-page to local PDF route mapping, citation page/excerpt behavior, plain answer URLs, and unregistered PDF links remaining external.

- `npm --prefix apps/frontend test`: **68 passed**; the production build, ESLint, TypeScript build check, and Prettier check passed.
- `npm --prefix apps/frontend run test:e2e`: **11 mocked Playwright tests passed**. No live provider or World Bank endpoint was contacted.

### Simplified search composer regression (refreshed 2026-10-28)

- The Research composer no longer displays Search method, Answer depth, PDF source, Country, Year, or Clear filters. Requests use Hybrid retrieval and Standard reasoning (`none`); PDF examples retain their exact source ID, while editing an example clears that scope.
- `npm --prefix apps/frontend test -- tests/research.test.tsx`: **34 passed**; full frontend tests: **68 passed**; mocked Playwright tests: **11 passed**.
- Frontend Prettier, ESLint, TypeScript, and production build checks passed. `python3 scripts/check_traceability.py` passed with 67 global requirements, 14 Feature 009 requirements, 11 acceptance criteria, 5 success criteria, and 10 demo scenarios.
- No live provider, PDF host, or remote evidence endpoint was called; browser coverage used mocked backend responses.

### Citation rejection regression (refreshed 2026-10-27)

- Agent-v2 permits concise claims supported by retrieved evidence. A nonmatching model excerpt hint is replaced with exact text from that current-run passage, so quote-copying errors no longer stop the answer; unknown passages and source-provenance mismatches are still rejected.
- Trace `5358f3fc-ecc9-4c8a-af0e-5b732993c6ff` confirmed the prior `QUOTE_NOT_EXACT` failure. The regression test now verifies host-side excerpt canonicalization; no live provider request was used for verification.
- 42 focused backend runtime/model/provider/contract tests passed after canonicalization, along with Python lint, format, and type checks. The Research UI's prior 29 focused tests and frontend lint, typecheck, build, and format checks passed; no frontend code changed in this follow-up. Repository traceability passed.
- No live provider endpoint was called. The supplied historical failures did not persist the rejected model draft, so their exact validation branch cannot be reconstructed.

### Answer-depth budget regression (fresh)

- The configured Standard baseline is 1,200 output tokens. Offline gateway tests verify Responses ceilings of **1,200 / 2,400 / 4,800 / 8,000** for Standard / Low / Medium / High, with the maximum bounded at 8,000; model capability metadata reports the maximum available ceiling.
- The focused backend API/runtime/settings/gateway tests passed **65 tests**; Ruff, formatting, and mypy passed. An `httpx.MockTransport` regression verified that the Agents SDK serializes the selected value as `reasoning.effort` alongside `max_output_tokens`; it made no live provider request. This verifies request construction and budget bounds, not deployment-specific acceptance or answer quality.
- Custom Responses compatibility regression: **14 gateway tests passed**. The SDK wire test confirms custom deployments receive only `reasoning.effort` (not the optional `reasoning.summary`); the official OpenAI path retains summary requests. No live endpoint was called, so deployment-specific acceptance is not claimed.

### Advanced RAG reranking and answer-trail regression (fresh 2026-10-28)

- The backend now optionally reranks up to 20 permission-filtered hybrid candidates with local `jinaai/jina-reranker-v1-tiny-en`. The answer trail reports the model, candidates scored, duration, and an explicit hybrid-order fallback if reranking fails. No private reasoning, prompts, raw arguments, or evidence payloads are exposed.
- Evaluation `52910cc4-f8a4-4f8f-a374-d2a9b110cb1a` used seven author-curated cases across three chunk configurations: **21/21** reranking attempts completed, with zero failures and zero cases without candidates. Mean metrics across chunk configurations: hybrid Recall@6 **0.571**, nDCG@6 **0.530**, MRR **0.516**, latency **7.07 ms**; hybrid+cross-encoder Recall@6 **0.619**, nDCG@6 **0.578**, MRR **0.563**, latency **219.46 ms**. Citation metadata completeness was **1.000** and empty-result rate was **0.000** for both modes.
- The result is not uniformly better: recall improved for the 450-token structure-aware chunker, was unchanged for the other two, and nDCG declined for the 250-token configuration. The cross-encoder therefore remains a measured option, not a proven quality win. The first measured cross-encoder query includes lazy model initialization; latency is local, machine-dependent, and not an SLO. The seven cases are not independently reviewed and do not measure answer quality or source accuracy. Inference is local; no live generation or remote reranking API call was made.
- Full per-chunker results and the run configuration are in [the retrieval evaluation report](../../docs/evaluation/retrieval-evaluation.md) and [evaluation manifest](../../data/manifests/retrieval-evaluation-manifest.json). Focused reranking/runtime/contract/evaluation tests passed **64 tests** and Research plus Architecture UI tests passed **38**. The latest `make check` covers **300 backend**, **39 MCP**, **131 script**, and **68 frontend** tests, formatting, lint, typecheck, and traceability; `make security-verify` covers **148 selected backend/security/evaluation** and **13 MCP** tests, production build, frontend tests, and secret scanning with no findings. All **11** mocked Playwright tests passed.

### AI-only evaluation results (fresh 2026-10-28)

- Full approved-set run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` used all **36 approved cases**, producing **297 metric rows** across retrieval, agent, and baseline conditions. The UI displays the **36 unique cases**, not the row count. The run is `partial`: four agent and five baseline outputs failed safely. Failed outputs are excluded from answer-quality scoring and reported separately; retrieval and operational metrics remain available.
- Failure-excluded expected-behavior accuracy is **65.1%** across **63 scored outputs** (**75.0% agent**, 32 scored; **54.8% non-agent baseline**, 31 scored). Retrieval Recall@6 averaged **56.6%** across retrieval conditions; citation correctness was **75.0%**; AI-judged groundedness **2.742/5** and answer relevance **4.226/5**; latency p50/p95 **5.5 / 5,168 ms**. Cost was **not measured**; external requests were made.
- The judge scored **31 of 33 attempted** outputs, with **0 failed**, **3 skipped**, and **2 ineligible outputs excluded**. Judge model ID `gpt-6-luna` matched the generation model ID for scored cases. These same-model scores are exploratory and not human-validated. Latency percentiles aggregate all 297 retrieval and generation metric rows; per-condition generation latency is shown in the report.
- `docs/evaluation/evaluation-report.md` contains per-condition results and limitations. The read-only evaluation summary contract is v1.4 and exposes per-metric scored counts, anchor coverage, groundedness distribution, condition/category comparisons, rubric/model identity, and judge counts without answers or judge rationale.

### Score transparency refresh (fresh 2026-10-28)

- Retrieval recall in new runs counts expected evidence anchors, not passage variants: a single anchor split into multiple chunks can contribute only one hit. The displayed Recall@k is the average of per-result fractions; pooled anchor hits/expected totals provide a denominator view and may not numerically equal that average. The sample count is the number of scored result rows, so it can exceed the number of unique cases when several retrieval conditions are present.
- The v1.4 read-only API/UI shows each metric's scored count, groundedness score distribution when measured, pooled retrieval/citation anchor totals, and expandable condition/category summaries. Historical recalls without persisted anchor totals remain unchanged and are explicitly marked as lacking a denominator; they are not recomputed from incomplete stored rows.
- New AI-judge runs use rubric `feature007-ai-judge-v2`, which may consider separately bounded validated deterministic calculation results as evidence for calculation claims. The judge still receives no expected labels, raw tool arguments, private reasoning, raw answer persistence, or free-form rationale storage. Historical run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` used rubric v1; its **2.742/5** groundedness score is unchanged. No new provider or judge call was made for this refresh.
- Re-run the focused offline regressions with:

  ```bash
  uv run --locked --package policylens pytest -q \
    scripts/tests/test_evaluation_metrics.py \
    scripts/tests/test_evaluation_suite.py \
    scripts/tests/test_evaluation_judge.py \
    apps/backend/tests/api/test_evaluation_summary.py \
    apps/backend/tests/api/test_feature009_contracts.py
  npm --prefix apps/frontend test -- tests/evaluations.test.tsx
  ```

- These commands passed **42 backend tests** and **6 evaluation UI tests**. Python formatting/lint/mypy, frontend formatting/ESLint/TypeScript/build, traceability, and offline case validation also passed. The prior AI-only score numbers above are historical results, not scores from this verification pass; no provider call was made.

### Session-backed chat and evaluation parity smoke (fresh 2026-10-28)

- A fresh workspace and session sent the India report's state-rate question to `/agent/answer/stream` with explicit OpenAI consent. The endpoint returned `answered` with Assam **26%/42%**, Madhya Pradesh **32%/28%**, Rajasthan **20%/13%**, Odisha **12%/18%**, and Andhra Pradesh **50%/55%**.
- The response cited `wb-india-skills-programs-2015`, page **16** (Table 8). Its safe activity trail recorded reranking, a Policy Data MCP resource read, retrieval, model completion, citation validation, and persisted session context. The temporary session was deleted after verification.
- This confirms chat parity for this question and run, not general provider/model parity. The smoke check made an authorized OpenAI request and a local MCP call.

### Default-open answer activity trail (fresh)

- Per-answer **How this answer was prepared** sections open by default, show a chevron disclosure control, and can be collapsed/reopened.
- `npm --prefix apps/frontend test`: **68 passed**; `npm --prefix apps/frontend run test:e2e`: **11 mocked browser tests passed**, including toggle and reload behavior.
- Frontend Prettier, ESLint, TypeScript, and production build checks passed. No live provider endpoint was called.

### Evaluation metric explanations and cost estimate (fresh 2026-10-28)

The read-only evaluation summary contract is v1.5. Each run-level and condition-level metric has a **How it's measured** disclosure; AI-judge coverage also expands to explain attempted, scored, skipped, failed, and ineligible outputs. Cost is identified as provider-reported, token-estimated, partially estimated, or unavailable. A token estimate includes the priced model IDs, published pricing date, uncached-input assumption, and any rows without usable token usage or a known rate. Unknown models are never assigned GPT-6 Luna pricing.

The historical run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` remains unchanged and was not rerun. Its displayed measurements are:

| Metric | Recorded result |
|---|---:|
| Cases | 36 approved across 20 categories |
| Expected-behavior accuracy | 65.1% overall (63 scored outputs); agent 75.0% (32), baseline 54.8% (31) |
| Retrieval Recall@6 | 56.6% across 9 retrieval settings (225 result rows) |
| Citation correctness | 75.0% |
| AI-judged groundedness / relevance | 2.742 / 5; 4.226 / 5 |
| Latency p50 / p95 | 5.5 / 5,168 ms |
| AI judge coverage | 31 scored / 33 attempted; 0 failed, 3 skipped, 2 ineligible outputs excluded |
| Cost / external requests | **$0.0232642 partial token estimate** / requests made |

The estimate sums 145,745 generation input and 11,735 generation output tokens plus 10,517 judge input and 3,541 judge output tokens. It uses OpenAI Standard short-context rates as of 2026-10-28 ($0.10 per million input tokens and $0.50 per million output tokens; [pricing source](https://developers.openai.com/api/docs/pricing)). Cached input is not separately recorded and is treated as uncached. Five generation rows have no token counts (two abstentions, one block, and two failures), so the estimate covers only priced recorded usage and is not an invoice total. No new generation or judge request was made.

Fresh verification: focused backend summary/schema tests **19 passed**; the full frontend suite **71 passed**; mocked evaluation Playwright tests **2 passed**. Python Ruff format/lint and mypy, frontend Prettier/ESLint/TypeScript/build, and `python3 scripts/check_traceability.py` passed. No provider request was made for these checks.
