# Feature 009 Traceability

Evidence maps to the current local assessment target. No live provider behavior is inferred from mocked browser tests.

> **Supersession note:** UI-009-02 and the related follow-up scenarios record Feature 009's original browser-only context contract. Feature 011 supersedes that behavior with persisted sessions and server-owned hot context; see [Feature 011 traceability](../011-session-memory/traceability.md) for current session and memory evidence.

## Functional Requirements

| Requirement | Implementation and validation |
|---|---|
| UI-009-01: chat composer, submit/cancel, fixed Hybrid/Standard defaults, no search/filter controls, and source-scoped examples | `apps/frontend/src/pages/ResearchPage.tsx`; `apps/frontend/src/data/example-prompts.ts`; `apps/frontend/src/data/pdf-sources.ts`; `apps/backend/src/policylens/api/source_files.py`; [local PDF contract](contracts/source-pdf.md); `apps/frontend/tests/research.test.tsx` verifies controls are absent, examples submit their source ID, and editing clears it; `apps/backend/tests/api/test_source_files.py`; `apps/frontend/tests/e2e/research.spec.ts` |
| UI-009-02 (historical): ephemeral run summaries and bounded browser-memory follow-up context | The original Feature 009 behavior bounded context to 8 messages, 4,000 characters per message, and 12,000 characters total. Feature 011 supersedes this with persisted sessions and at most five completed exchanges of server-owned hot context; see `specs/011-session-memory/traceability.md` and `quickstart.md`. |
| UI-009-03: select only backend-configured models | `apps/backend/src/policylens/api/model_capabilities.py::build_model_options`; `test_model_options.py`; `SettingsPage.tsx` |
| UI-009-04: per-run explicit OpenAI consent | `ProviderConsentDialog.tsx`; `agent.py`; `test_agent_api.py`; `research.test.tsx`; `tests/e2e/provider-consent.spec.ts` |
| UI-009-05: typed provider selection, no fallback | `AgentAnswerRequest`; `api/agent.py`; backend provider tests; `test_provider_boundaries.py` |
| UI-009-06: answer state, claims, calculations, uncertainty, conflicts, limits, trace/provider | `ResearchPage.tsx` renders answer, abstention, conflict, calculation, uncertainty, limitation, and run-activity fields; `research.test.tsx` covers answer states, conflict/calculation details, safe tool activity, and recoverable errors. |
| UI-009-07: bounded citation excerpt, source metadata, page/section/row, provenance, copy | `EvidenceDrawer.tsx` renders bounded passages or structured row keys, provenance, source metadata, and copy action; `research.test.tsx` verifies structured rows and that untrusted strings remain text. |
| UI-009-09: read-only aggregate evaluation summaries | `apps/backend/src/policylens/api/evaluation_summary.py`; `test_evaluation_summary.py`; `EvaluationsPage.tsx` |
| UI-009-10: null/unavailable metrics and no run launch | `evaluation-summary.schema.json` v1.5; `test_evaluation_summary.py`; `evaluations.test.tsx` and `e2e/evaluations.spec.ts` cover null, empty, populated, and read-only states. |
| UI-009-11: nine architecture layers and request-scoped memory | `apps/frontend/src/data/architecture.ts`; `ArchitecturePage.tsx`; `architecture.test.tsx` |
| UI-009-12: implementation status labels | `ArchitecturePage.tsx::StatusBadge`; `architecture.test.tsx` |
| UI-009-13: safe component status | `SystemStatusPage.tsx`; `system-status.test.tsx` covers ready/degraded service states, not-configured/unavailable components, and omission of an internal path. |
| UI-009-14: typed backend communication | `apps/frontend/src/api/client.ts`; `tests/api/client.test.ts` checks backend URLs, abort-signal propagation, and typed errors; `security.test.ts` verifies browser fetch calls are confined to typed API modules and excludes direct provider/MCP endpoints. |
| UI-009-15: fixed Standard effort in the Research UI; backend capability validation and effort-scaled bounded Responses output budget | `apps/frontend/src/pages/ResearchPage.tsx` submits `none`; `research.test.tsx` verifies Standard is sent and no depth control is rendered; `apps/backend/src/policylens/api/model_capabilities.py::build_model_options`; `apps/backend/src/policylens/api/agent.py::_resolve_runtime`; `apps/backend/src/policylens/agent_runtime/gateway.py`; `test_agent_api.py` rejects unsupported effort before runtime; `test_model_gateway.py` verifies all four output budgets, custom endpoint effort-only settings and serialized JSON, and official-endpoint summary settings; `test_model_capabilities.py` verifies the reported ceiling. |
| UI-009-16: typed safe SSE progress and bounded follow-up flow | `apps/backend/src/policylens/api/agent.py::answer_stream`; `apps/frontend/src/api/client.ts::submitAgentAnswerStream`; `ResearchPage.tsx::progressLabel`; `AgentTrail.tsx`; `test_agent_api.py`, `test_agent_runtime.py`, and `research.test.tsx`. OpenAI consent is re-confirmed on each turn; progress includes cross-encoder status/model/candidate count/duration and safe fallback messaging, but no raw tool identifiers or hidden reasoning. Feature 011 owns current persistent session context. |
| UI-009-17: report route, effort, provider usage, and safe SDK summary | `apps/backend/src/policylens/agent_runtime/usage.py`, `models.py`, `state.py`, `gateway.py`, and `traces.py` normalize SDK usage, type agent-only metadata/events, and return only Responses summary-text items; `api/agent.py` and the `specs/004-agent-runtime/contracts/agent-api.schema.json` and `specs/006-model-routing/contracts/model-run-metadata.schema.json` contracts expose the typed fields; `AgentTrail.tsx` displays metadata or event usage with explicit unavailability; `test_model_gateway.py`, `test_agent_state.py`, `test_model_options.py`, `test_mlx_provider.py`, `scripts/tests/test_agent_contracts.py`, and `research.test.tsx`. Citation claims may be concise paraphrases; tests ensure their exact evidence quotes remain validated and safe rejection reasons are visible. |
| UI-009-18: disclose AI judge provenance, generator-model relationship, and attempted/scored/failed/skipped coverage without raw answers | `apps/backend/src/policylens/api/evaluation_summary.py`; `specs/009-minimal-ui/contracts/evaluation-summary.schema.json` v1.5; `EvaluationsPage.tsx`; `test_evaluation_summary.py`; `evaluations.test.tsx`; mocked Playwright evaluation tests. |
| UI-009-19: explain score denominators, grouped retrieval recall, distributions, and condition/category comparisons | `evaluation_summary.py::_score_metrics` exposes per-metric sample counts, anchor totals, groundedness distributions, and condition/category summaries; `EvaluationsPage.tsx` explains per-result anchor recall, distinguishes pooled totals from averages, and flags historical recall without stored anchor totals; API/schema/UI regressions cover the safe summary only. |
| UI-009-20: expand metric definitions and distinguish reported, estimated, partial, and unavailable cost | Summary v1.5 exposes cost basis, model IDs, pricing date, and usage-gap count; `evaluation_summary.py::_cost_summary` prefers recorded provider cost and prices only explicitly supported models; `EvaluationsPage.tsx` provides per-metric disclosures and cost assumptions; backend and UI regressions cover precedence, gaps, and unknown models. |
| A11Y-009-01: keyboard and 320px layout | `tests/e2e/accessibility.spec.ts` checks keyboard navigation and horizontal overflow at 320 CSS pixels. Other accessibility criteria require separate evidence. |
| SEC-009-01: untrusted content as text; no hidden reasoning | UI renders backend strings as React text; `research.test.tsx` verifies unsafe citation text is not parsed as markup; `tests/security.test.ts` scans source/build output for credential patterns and direct non-backend endpoints; backend safe-activity tests cover allow-listed events. |
| TEST-009-01: answer, abstention, cancel/error, evaluations, architecture | `research.test.tsx`, `evaluations.test.tsx`, `architecture.test.tsx`, `system-status.test.tsx`, and mocked Playwright workflows cover answer/evidence, abstention, cancellation, error, evaluation, and architecture states. |

## Acceptance Scenarios

| Scenario | Verification |
|---|---|
| AC-009-01: example fills but does not submit | `research.test.tsx`; `e2e/research.spec.ts` |
| AC-009-02: streamed safe progress, trace, terminal answer | `ResearchPage.tsx`; `AgentTrail.tsx` presents reranker model/candidate count/duration and safe fallback; `research.test.tsx` checks retrieval/reranking/tool progress and hides raw tool names; `e2e/research.spec.ts` |
| AC-009-03: local stop-waiting behavior is honest | `research.test.tsx` verifies client abort and says backend may continue to timeout; stream route uses the browser signal without claiming server-side cancellation |
| AC-009-04: distinct recoverable error states | `api/client.test.ts`; `research.test.tsx`; backend error mapping tests |
| AC-009-05: configured model option metadata | `test_model_options.py`; `settings.test.tsx` |
| AC-009-06: OpenAI requires per-run consent | `test_agent_api.py`; `settings.test.tsx`; `e2e/provider-consent.spec.ts` |
| AC-009-07: unavailable models fail without fallback | `test_agent_api.py`; backend provider-boundary tests |
| AC-009-19: Research requests use fixed Hybrid/Standard settings without search controls and Responses output budget remains bounded | `research.test.tsx` checks controls are absent and payload defaults; `test_agent_api.py` rejects unsupported effort before runtime; `test_model_gateway.py` verifies 1x/2x/4x/8x budgets and the 8,000-token cap |
| AC-009-20 (historical): follow-up sends only bounded prior turns and revalidates evidence | The original browser-memory contract limited messages and content. Feature 011 replaces it with backend-selected five-pair session context; current evidence is in `specs/011-session-memory/traceability.md`. |
| AC-009-21 (historical): clearing/reloading does not retain conversation context | The original Feature 009 page reset context on reload. Feature 011 now restores persisted transcripts after reload and owns the current behavior; see `specs/011-session-memory/traceability.md`. |
| AC-009-22: answer trail reports provider usage and only safe Responses summary text | `test_model_gateway.py` and `test_agent_state.py` validate usage/summary extraction, custom endpoint omission of optional summary requests, and exclusion of private content; `research.test.tsx` covers Responses metadata, event fallback, route visibility, and Chat Completions' summary limitation |
| AC-009-08: citations open bounded evidence and provenance | `EvidenceDrawer.tsx`; `research.test.tsx` verifies bounded excerpt, structured row provenance, untrusted text, and copy behavior. |
| AC-009-09: tool events are safe summaries | `ResearchPage.tsx`; existing backend trace tests |
| AC-009-10: abstention and conflict are explicit | `research.test.tsx` covers conflict/calculation details; `e2e/provider-consent.spec.ts` covers an abstention response. |
| AC-009-11: aggregate runs and limitations | `test_evaluation_summary.py`; `evaluations.test.tsx` |
| AC-009-12: absent runs show empty state; null is not zero | `test_evaluation_summary.py`, `evaluations.test.tsx`, and `e2e/evaluations.spec.ts` cover empty, null, and populated states. |
| AC-009-13: evaluation page is read-only | API is GET-only; UI has no run controls; Playwright asserts no run button |
| AC-009-23: AI-judged metrics disclose model/rubric, generator-model relationship, attempted/scored/failed/skipped coverage, and non-human validation | `EvaluationJudgeSummary` allow-list; `EvaluationsPage.tsx`; backend/API and frontend regression tests. |
| AC-009-24: metrics show sample counts, expected-anchor denominator, groundedness distribution, and condition/category comparisons without treating missing historical denominators as zero | Summary v1.5 contract and `test_evaluation_summary.py`; `EvaluationsPage.tsx` and `evaluations.test.tsx` verify anchor totals, distributions, breakdowns, and historical missing-denominator messaging. |
| AC-009-25: expanded explanations describe metric calculations and cost provenance/coverage | Summary v1.5 schema/API tests validate provider-reported and token-estimated cost provenance; `evaluations.test.tsx` verifies each run metric has a disclosure and partial cost explains its rates and usage gaps. |
| AC-009-14: architecture layer detail | `architecture.test.tsx`; `e2e/accessibility.spec.ts` |
| AC-009-15: memory and runtime tool explanation | `architecture.ts` and architecture tests; memory explicitly request-scoped |
| AC-009-16: implementation status honesty | architecture layer status data and visible badges |
| AC-009-17: component status distinctions | `system-status.test.tsx` covers ready and degraded overall status, structured HTTP 503 readiness bodies, not-configured retrieval, and unavailable MCP. |
| AC-009-18: internal diagnostics omitted | `system-status.test.tsx` verifies a synthetic internal path is not rendered |

## Success Criteria

| Criterion | Evidence |
|---|---|
| SC-009-01: claims open to bounded evidence or explicit absence | `EvidenceDrawer.tsx` renders citation excerpts and provenance; `ResearchPage.tsx` routes Markdown links to registered PDFs through the shared preview; the source-file API serves hash-verified local PDFs inline; `research.test.tsx` and `test_source_files.py` cover canonical mapping, page/excerpt display, source integrity, structured rows, and answer/conflict states. |
| SC-009-02: example selection causes no answer request | `research.test.tsx`; `e2e/research.spec.ts` |
| SC-009-03: OpenAI request needs per-run approval and no fallback | backend consent/availability tests and Playwright consent flow |
| SC-009-04: evaluation is read-only and null remains unmeasured | summary API tests and evaluation view tests |
| SC-009-05: architecture explains nine layers and scoped state | architecture data completeness/navigation tests |
| SC-009-06: core workflows support keyboard and 320px width | `e2e/accessibility.spec.ts` verifies keyboard navigation and no horizontal overflow at 320 CSS pixels for its tested flow. |
| SC-009-07: browser sends app traffic only to backend | `security.test.ts` scans for credentials/direct provider and MCP endpoints and confines source fetch calls to typed API modules; Playwright uses mocked backend routes. |
| SC-009-08: Research uses fixed Hybrid/Standard settings without visible search controls; unsupported efforts are rejected and Responses token budget is bounded | `research.test.tsx` verifies controls are absent and the request defaults; `test_agent_api.py` verifies unsupported effort is rejected before runtime; `test_model_gateway.py` verifies effort-scaled output ceilings. |
| SC-009-09: progress displays operational summaries without sensitive internals | `research.test.tsx` verifies retrieval/tool labels render and raw tool identifiers are hidden; backend event tests verify typed progress. |
| SC-009-10: follow-up context is bounded and cleared | `research.test.tsx` verifies prior turns, selected effort, and clear behavior; request model enforces message and character limits. |
| SC-009-11: route and usage are transparent without exposing private reasoning | `research.test.tsx` verifies route, effort, counts, summary, and unavailable messaging; `test_agent_state.py` verifies only typed SDK summary text enters safe events. |
| SC-009-12: AI-quality metrics are distinguished and disclose provenance/validation limits | Feature 007 run metrics and judge record; `evaluation_summary.py` allow-lists judge model/rubric/counts; v1.5 schema and `evaluations.test.tsx` verify labels and score coverage. |
| SC-009-13: readers can interpret score sample counts, anchor denominators, distributions, and condition/category differences | Evaluation summary v1.5, `EvaluationScoreMetrics`, `EvaluationScoreMetrics` frontend type, and focused API/UI regressions. Historical records without anchor totals are explicitly left unchanged. |
| SC-009-14: expanded metrics explain calculations and cost-estimate assumptions | Summary v1.5 contract, `_cost_summary` tests for known/unknown pricing and provider-cost precedence, plus `evaluations.test.tsx` for expanded definitions and partial-usage disclosure. |

## Provider Usage and Summary Test Mapping

| Task | Verification surface | Requirement IDs |
|---|---|---|
| T043 | `test_model_options.py`, `test_model_gateway.py`, `test_agent_state.py`, `test_mlx_provider.py` | UI-009-15, UI-009-17, AC-009-19, AC-009-22 |
| T044 | SDK usage/summary normalization, `AgentModelUsage` and safe event types, agent/model metadata schemas, and lifecycle-event tests | UI-009-17, SEC-009-01, AC-009-22, SC-009-11 |
| T045 | `apps/frontend/tests/research.test.tsx` | UI-009-17, SEC-009-01, AC-009-22, SC-009-11 |
| T047 | `test_model_gateway.py`, `test_model_capabilities.py` | UI-009-15, AC-009-19, SC-009-08 |
| T048 | `test_model_gateway.py` | UI-009-15, UI-009-17, AC-009-19, AC-009-22 |
| T053 | `test_evaluation_summary.py`, `apps/frontend/tests/evaluations.test.tsx`, summary v1.4 schema | UI-009-18, UI-009-19, AC-009-24, SC-009-12, SC-009-13 |
| T054-T055 | `test_evaluation_summary.py`, `test_feature009_contracts.py`, `evaluations.test.tsx`; v1.5 schema | UI-009-20, AC-009-25, SC-009-14 |
| T056 | Feature 009 quickstart, historical evaluation report, traceability, and focused validation record | UI-009-20, AC-009-25, SC-009-14 |

## Verification Commands

```bash
make security-verify
make format-check-python
make lint-python
make typecheck-python
make test-python
make check
make security-verify
make retrieval-verify
make evaluation-verify
npm --prefix apps/frontend run format:check
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run typecheck
npm --prefix apps/frontend test
npm --prefix apps/frontend run test:e2e
python3 scripts/check_traceability.py
```

Browser tests mock backend responses; they do not certify live OpenAI/MLX requests, browser-to-provider isolation beyond inspected routes, or production authentication.
