# Feature 011 Quickstart: Session Chat and Memory

## Prerequisites

- The PolicyLens API and frontend dependencies are installed as described in the repository README.
- A validated retrieval index and a configured embedding provider are available for end-to-end agent requests.
- Local synthetic tests do not require live OpenAI calls or real policy documents.
- Before saving sessions, acknowledge the data-use notice and store only public, synthetic, or appropriately anonymized content; long-term memory is off until explicitly enabled.

## Validate Backend Contracts and Persistence

```bash
uv run --locked --package policylens pytest \
  apps/backend/tests/unit/test_conversation_models.py \
  apps/backend/tests/unit/test_conversation_store.py \
  apps/backend/tests/unit/test_conversation_memory.py \
  apps/backend/tests/api/test_sessions_api.py \
  apps/backend/tests/api/test_memory_api.py \
  apps/backend/tests/integration/test_session_followups.py \
  apps/backend/tests/integration/test_memory_context.py
```

Expected: session ordering, five-pair hot-context bounds, workspace isolation, memory top-five bounds, clear/delete behavior, and explicit failure states pass using synthetic data and fake embedding/model adapters.

## Compare Memory Retrieval with the No-Memory Baseline

```bash
uv run --locked --package policylens python scripts/evaluate_conversation_memory.py
```

Expected: the versioned synthetic fixture reports precision@5 and recall@5 for memory retrieval and the no-memory baseline. The report is a retrieval-mechanics check only; it does not measure factual answer quality.

See [evaluation-results.md](evaluation-results.md) for the recorded configuration, category-level metrics, latency caveat, cost estimate, limitations, and negative results.

## Validate Follow-Up and Session UI

```bash
npm --prefix apps/frontend test -- tests/research.test.tsx tests/research-consent.test.tsx tests/research-memory.test.tsx tests/api/client.test.ts
npm --prefix apps/frontend run build
```

Expected: a new session can be created, messages survive page reload, follow-up requests use the active session only, and the UI exposes memory/session failures without claiming they succeeded.
Each assistant answer has an open-by-default **How this answer was prepared** summary. Use its chevron control to collapse or reopen that turn's safe processing events, API route, reasoning effort, and provider-reported token counts. Responses API runs may also show the SDK-generated summary text; private reasoning content is never shown. Saved trails return open with their corresponding answers after reload. Local Chroma/BM25 ranking remains unchanged; before generation, the backend reads each selected passage through the registered Policy Data MCP resource and checks its identity, text, hashes, and provenance against the ranked result. A missing or mismatched passage stops safely with a specific MCP diagnostic and is visible in that answer's trail.

The eight PDF examples also select their exact indexed `source_id`; ordinary questions search the full corpus, and editing an example question clears its source scope. Citation actions and Markdown links to registered World Bank item pages share an in-app PDF iframe preview served by the backend from the existing hash-verified local file at `/sources/{source_id}/pdf`. A matching citation supplies its page and excerpt search; a link without structured citation data opens the PDF without implying a highlight. The iframe does not contact the remote `documents1.worldbank.org` host.

Corpus claims may be concise summaries linked to exact excerpts from the current run. Citation validation checks the excerpt and source provenance; it does not independently prove semantic entailment, so open the linked evidence to review a paraphrase. Citation failures carry a safe reason code in the answer trail, without persisting the rejected model draft.

## Exercise a Local End-to-End Session

1. Start the API and frontend using the repository's existing `make dev-api` and `make dev-frontend` commands.
2. Acknowledge the data-use notice; use only public, synthetic, or appropriately anonymized content.
3. Open the research page, select **New chat**, and submit a synthetic question.
4. Submit a follow-up and verify the live Agent trail reports safe session/context stages, evidence retrieval, and Policy Data MCP passage verification. After the response completes, confirm its per-answer activity summary is open by default, toggle it closed and open again, and verify it shows only that turn's safe events and remains open after reload.
5. Reload the page, reopen that session, and verify its saved transcript is restored.
6. Enable long-term memory explicitly, send another synthetic question, and verify memory retrieval status is visible.
7. Open **Manage memory**, clear long-term memory or delete the session, and verify the next request cannot retrieve the cleared records.
8. Select OpenAI only when explicitly configured and approve each external-processing dialog; do not make an unapproved external request.

## Verification Record (refreshed 2026-10-28)

- Focused backend session/memory tests: **41 passed**. Focused frontend session, consent, memory, and API tests: **50 passed**. Focused MCP/runtime/API regressions: **55 passed**; focused Research UI tests: **27 passed**.
- `make check` passed formatting, lint, Python mypy, TypeScript typecheck, **284 backend tests**, **39 MCP tests**, **122 script tests**, **65 frontend tests**, and traceability.
- `make security-verify` passed **140 selected backend/security/evaluation tests**, **13 MCP tests**, the production frontend build, **65 frontend tests**, and secret scanning with no findings.
- `npm --prefix apps/frontend run test:e2e` passed **11 mocked Playwright tests** covering consent, session creation/resume/follow-up, memory controls, safe activity, provider consent, accessibility, and the 320 CSS-pixel Research layout.
- Per-answer trail and MCP passage-verification regression: **27 focused Research UI tests** and all **11 mocked Playwright tests** passed; reload restored the matching trail and the cited PDF opens at its page with the excerpt highlighted. The answer trail exposes passage verification and actionable failure codes without private reasoning or raw tool inputs.
- `make retrieval-verify` reported `status: ready`. `make evaluation-verify` reported 36 approved cases across 20 categories, `release_eligible=true`, and `live_requests_made=false`.
- The deterministic memory harness reported macro precision@5 **0.2667**, recall@5 **0.6667**, no-memory baseline precision/recall **0.0000**, fixture-ranking latency **0.0730 ms mean / 0.1151 ms max**, and estimated provider cost **$0.00**. No seed applies because ranking is deterministic. The local retrieval index was ready, but the harness does not use it, Chroma, production embeddings, or a generation model; no live provider requests were made. See [evaluation-results.md](evaluation-results.md) for category results, qualitative errors, negative results, and limitations.
- Fresh PDF/source-filter regression: the backend source-file and retrieval API tests passed **13 tests**, including local hash verification and byte ranges; a local smoke request served the stored India PDF (775,995 bytes). The focused Research UI suite passed **33 tests**, the full frontend suite passed **64 tests**, the production build, ESLint, and Prettier checks passed, and all **11 mocked Playwright tests** passed. The India example sends `wb-india-skills-programs-2015`; the Singapore item-page URL maps to the local PDF endpoint. No live provider or report endpoint was called.
- Fresh answer-trail regression: each per-answer **How this answer was prepared** section opens by default with a visible chevron that collapses/reopens it; session reload restores it open. All **65 frontend tests** and **11 mocked Playwright tests** passed, along with Prettier, ESLint, TypeScript, production build, and repository traceability. No live provider endpoint was called.
