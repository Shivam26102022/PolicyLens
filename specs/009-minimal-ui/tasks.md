---

description: "Implementation tasks for the PolicyLens research workbench"
---

# Tasks: PolicyLens Research Workbench

**Input**: Design documents from `/specs/009-minimal-ui/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`.

**Tests**: Required by `TEST-009-01`; tests use mocked backend responses and do not make live provider calls.

**Organization**: Tasks are grouped by independently testable user story. All browser/API provider traffic remains explicit.

## Phase 1: Setup

**Purpose**: Add only the UI dependencies and browser test harness required by the plan.

- [x] T001 Add pinned `react-router-dom`, `lucide-react`, `@playwright/test`, and Playwright scripts to `apps/frontend/package.json` and update `apps/frontend/package-lock.json`.
- [x] T002 Configure the Playwright web server, base URL, browser project, and test output directories in `apps/frontend/playwright.config.ts` and `apps/frontend/package.json`.

---

## Phase 2: Foundational

**Purpose**: Lock API contracts and shared frontend API/error types before story implementations.

- [x] T003 [P] Add JSON Schema contract validation tests for `specs/009-minimal-ui/contracts/model-options.schema.json`, `specs/009-minimal-ui/contracts/agent-provider-selection.schema.json`, and `specs/009-minimal-ui/contracts/evaluation-summary.schema.json` in `apps/backend/tests/api/test_feature009_contracts.py`.
- [x] T004 [P] Add typed frontend API contract and error-mapping tests in `apps/frontend/tests/api/client.test.ts` for validation, consent-required, unavailable, and malformed responses.
- [x] T005 Implement shared versioned frontend request/response types and abortable backend client functions in `apps/frontend/src/api/client.ts`.
- [x] T006 Add shared accessible navigation, shell, layout, and responsive tokens in `apps/frontend/src/App.tsx` and `apps/frontend/src/App.css` without changing backend behavior.

**Checkpoint**: Contract schemas validate; the shell can navigate views; frontend API code has no provider or filesystem access.

---

## Phase 3: User Story 1 - Ask Questions in the Research Workspace (Priority: P1)

**Goal**: Users can enter a question, autofill an example, submit, cancel, and see honest run progress and terminal states.

**Independent Test**: Mock answer endpoint tests verify example selection makes no request, explicit submit makes one request, cancel aborts, and loading/error states are accessible.

### Tests for User Story 1

- [x] T007 [P] [US1] Add composer/example autofill and no-auto-submit tests in `apps/frontend/tests/research.test.tsx`.
- [x] T008 [P] [US1] Add mocked submit, abort, timeout, offline, validation, permission, and server-error tests in `apps/frontend/tests/research.test.tsx`.

### Implementation for User Story 1

- [x] T009 [US1] Add reviewed example prompts and supported filter values in `apps/frontend/src/data/example-prompts.ts`.
- [x] T010 [US1] Implement chat composer, prompt autofill, optional filters, explicit submit, abortable request, ephemeral recent runs, loading, and terminal-state presentation in `apps/frontend/src/pages/ResearchPage.tsx`.

**Checkpoint**: Research flow works with mocked answer data and no request is sent by selecting an example.

---

## Phase 4: User Story 2 - Choose a Configured Model Safely (Priority: P1)

**Goal**: Model settings reflect backend configuration and require per-run external-processing consent.

**Independent Test**: Backend and component tests cover configured/unconfigured options, provider/model propagation, missing consent rejection, unavailable provider, and no fallback.

### Tests for User Story 2

- [x] T011 [P] [US2] Add configured/unconfigured model-options endpoint tests and schema assertions in `apps/backend/tests/api/test_model_options.py`.
- [x] T012 [P] [US2] Add provider-specific answer, missing-consent, external-opt-in, invalid-option, and no-fallback tests in `apps/backend/tests/api/test_agent_api.py`.
- [x] T013 [P] [US2] Add provider preference, per-run OpenAI consent, missing-configuration, and accessible settings tests in `apps/frontend/tests/settings.test.tsx`.

### Implementation for User Story 2

- [x] T014 [US2] Implement strict model-option response models and `GET /model/options` in `apps/backend/src/policylens/api/model_capabilities.py`, exposing configured IDs and safe local/external state only.
- [x] T015 [US2] Add provider and consent fields to `AgentAnswerRequest` in `apps/backend/src/policylens/agent_runtime/models.py`; resolve selections against `AppSettings`, validate consent, and cache runtimes by configured provider/model in `apps/backend/src/policylens/api/agent.py`.
- [x] T016 [US2] Implement settings view and per-run external-processing confirmation in `apps/frontend/src/pages/SettingsPage.tsx` and `apps/frontend/src/components/ProviderConsentDialog.tsx`; never persist consent.

**Checkpoint**: UI provider choice changes the actual backend route, OpenAI requires consent for each run, and unsupported choices fail without fallback.

---

## Phase 5: User Story 3 - Inspect Answers, Evidence, and Tool Activity (Priority: P1)

**Goal**: Every answer is inspectable through typed claims, citation evidence, calculations, uncertainty, limitations, and safe tool summaries.

**Independent Test**: Fixture responses cover answered, abstained, clarification, conflict, calculation, and failed-safe states; citations open exact bounded evidence.

### Tests for User Story 3

- [x] T017 [P] [US3] Add answer-state, claim/citation, calculation, conflict, abstention, and safe tool activity tests in `apps/frontend/tests/research.test.tsx`.
- [x] T018 [P] [US3] Add evidence drawer, bounded text, structured row provenance, copy citation, and untrusted-string rendering tests in `apps/frontend/tests/research.test.tsx`.

### Implementation for User Story 3

- [x] T019 [US3] Implement inline answer and claim presentation, uncertainty/conflict/limitations sections, trace/provider metadata, and safe activity summaries in `apps/frontend/src/pages/ResearchPage.tsx`.
- [x] T020 [US3] Implement evidence detail drawer with source metadata, exact bounded passage/rows, provenance, and copy-citation action in `apps/frontend/src/components/EvidenceDrawer.tsx`.

**Checkpoint**: All corpus-derived claims link to evidence; untrusted response strings render as text only.

---

## Phase 6: User Story 4 - Review Evaluation Results (Priority: P2)

**Goal**: Users can inspect read-only aggregate evaluation summaries with honest empty, blocked, and unavailable states.

**Independent Test**: Backend tests validate populated, missing, malformed, and blocked manifests; browser tests assert no raw case data and no evaluation launch.

### Tests for User Story 4

- [x] T021 [P] [US4] Add evaluation-summary model/schema tests for populated, empty, null-metric, and malformed manifest cases in `apps/backend/tests/api/test_evaluation_summary.py`.
- [x] T022 [P] [US4] Add evaluation overview/table, honest null/empty states, and read-only navigation tests in `apps/frontend/tests/evaluations.test.tsx`.

### Implementation for User Story 4

- [x] T023 [US4] Implement validated allow-listed manifest aggregation and `GET /evaluation/summary` in `apps/backend/src/policylens/api/evaluation_summary.py`; exclude prompts, raw cases, credentials, and filesystem paths.
- [x] T024 [US4] Register the read-only evaluation router in `apps/backend/src/policylens/api/app.py` and add endpoint contract tests in `apps/backend/tests/api/test_evaluation_summary.py`.
- [x] T025 [US4] Implement evaluation overview with run status, time, coverage, selected aggregate metrics, limitations, and unavailable states in `apps/frontend/src/pages/EvaluationsPage.tsx`.

**Checkpoint**: Existing run results are browsable as aggregate data only; no run or provider call can be started from the page.

---

## Phase 7: User Story 5 - Understand the System Architecture (Priority: P2)

**Goal**: Users can explore system layers and understand runtime tool calling, request state, trust boundaries, and implementation status.

**Independent Test**: Architecture content tests require all nine layers and status labels; browser tests navigate by keyboard and open documentation references.

### Tests for User Story 5

- [x] T026 [P] [US5] Add architecture-layer completeness, reference, status, and request-scoped-memory assertions in `apps/frontend/tests/architecture.test.tsx`.

### Implementation for User Story 5

- [x] T027 [US5] Add reviewed data for UI/API, retrieval/index, agent runtime/state, tools/MCP, provider gateway, evidence validation, evaluation, and logging layers in `apps/frontend/src/data/architecture.ts`.
- [x] T028 [US5] Implement navigable architecture guide with layer details, status labels, trust-boundary flow, and docs links in `apps/frontend/src/pages/ArchitecturePage.tsx`.
- [x] T029 [US5] Update `docs/architecture/architecture.md` and `docs/architecture/architecture-diagram.md` to identify currently implemented/configured/planned features and clarify that memory is request-scoped, not persistent chat memory.

**Checkpoint**: Architecture content matches the implementation and labels unavailable/planned layers honestly.

---

## Phase 8: User Story 6 - Check System Status (Priority: P2)

**Goal**: Users can inspect safe backend, retrieval/index, MCP, and model status.

**Independent Test**: Mock ready, degraded, unavailable, and not-configured health/model responses and verify safe accessible status labels.

### Tests for User Story 6

- [x] T030 [P] [US6] Add status component tests for ready, degraded, unavailable, and not-configured responses in `apps/frontend/tests/system-status.test.tsx`.

### Implementation for User Story 6

- [x] T031 [US6] Implement system status view using `/health/ready` and model-options state in `apps/frontend/src/pages/SystemStatusPage.tsx`; render no internal paths, credentials, or raw exception text.

**Checkpoint**: Status states distinguish unavailable from not configured and expose no infrastructure secrets.

---

## Phase 9: Polish and Cross-Cutting Concerns

- [x] T032 [P] [US1] Add Playwright mocked-backend workflows for prompt autofill, answer/evidence, abstention, cancellation, and failed-tool states in `apps/frontend/tests/e2e/research.spec.ts`.
- [x] T033 [P] [US2] Add Playwright checks for OpenAI consent, local provider selection, and no request before consent in `apps/frontend/tests/e2e/provider-consent.spec.ts`.
- [x] T034 [P] [US4] Add Playwright checks for populated/empty evaluation summaries with no request-launch controls in `apps/frontend/tests/e2e/evaluations.spec.ts`.
- [x] T035 [P] [US5] Add Playwright keyboard navigation and 320 CSS-pixel checks for architecture and core research views in `apps/frontend/tests/e2e/accessibility.spec.ts`.
- [x] T036 [P] Add source/bundle tests proving the browser contains no provider credential patterns and communicates only with the backend in `apps/frontend/tests/security.test.ts`.
- [x] T037 Update `specs/009-minimal-ui/traceability.md` and `specs/009-minimal-ui/quickstart.md` with final API/view behavior and test mappings, including streaming, effort, and bounded follow-ups.
- [x] T038 Run Feature 009 API, Python, frontend, Playwright, formatting, lint, typecheck, and repository traceability gates; record actual results in `specs/009-minimal-ui/quickstart.md`.

---

## Phase 10: Reasoning Effort, Progress, and Follow-Ups

**Purpose**: Expose supported effort choices, safe streamed processing status, and bounded follow-up context without hidden reasoning or provider-managed memory.

- [x] T039 [US2] Advertise route-specific reasoning efforts and reject unsupported request values before runtime execution in `apps/backend/src/policylens/api/model_capabilities.py` and `apps/backend/src/policylens/api/agent.py`; cover capability rejection in `apps/backend/tests/api/test_agent_api.py`.
- [x] T040 [US1] Add typed operational SSE progress/result/error events at `/agent/answer/stream` and consume them through the typed frontend client with safe labels in `apps/backend/src/policylens/api/agent.py`, `apps/frontend/src/api/client.ts`, and `apps/frontend/src/pages/ResearchPage.tsx`.
- [x] T041 [US1] Implement browser-memory follow-up context with 8-message, 4,000-character per-message, and 12,000-character total bounds; keep prior messages untrusted and require fresh OpenAI consent for every turn in `apps/backend/src/policylens/agent_runtime/models.py`, `apps/frontend/src/pages/ResearchPage.tsx`, and `apps/frontend/src/components/ProviderConsentDialog.tsx`.
- [x] T042 [P] [US1] Test streamed safe progress, selected effort, bounded follow-up payloads, conversation clearing, and fresh per-turn consent in `apps/backend/tests/api/test_agent_api.py` and `apps/frontend/tests/research.test.tsx`.

---

## Phase 11: Provider Usage and Responses Summary

**Purpose**: Make provider execution, token usage, and available SDK summaries clear without exposing private reasoning.

- [X] T043 [P] [US2] Add backend tests for route-specific effort availability, provider usage normalization/aggregation, and safe Responses SDK summary extraction in `apps/backend/tests/api/test_model_options.py`, `apps/backend/tests/unit/test_model_gateway.py`, `apps/backend/tests/unit/test_agent_state.py`, `apps/backend/tests/unit/test_mlx_provider.py`, and `apps/backend/tests/api/test_agent_api.py`. Verified: 39 focused backend tests pass.
- [X] T044 [US1] Record API route, reasoning effort, aggregate provider usage, and only SDK summary-text items in typed model metadata and safe progress events in `apps/backend/src/policylens/agent_runtime/usage.py`, `models.py`, `state.py`, `gateway.py`, `traces.py`, `mlx_provider.py`, `apps/backend/src/policylens/api/agent.py`, `specs/004-agent-runtime/contracts/agent-api.schema.json`, and `specs/006-model-routing/contracts/model-run-metadata.schema.json`. Verified: 39 focused backend tests and 4 agent-contract tests pass; repository checks pass.
- [X] T045 [US1] Display route, effort, provider-reported token counts, SDK summary or explicit unavailability, and custom Chat Completions limitations in `apps/frontend/src/components/AgentTrail.tsx`, `apps/frontend/src/pages/ResearchPage.tsx`, and `apps/frontend/src/App.css`; cover Responses metadata and event fallback in `apps/frontend/tests/research.test.tsx`. Verified: 26 Research tests and 2 Architecture tests pass; production build, Prettier, ESLint, and TypeScript checks pass.
- [X] T046 Update Feature 009 requirements, traceability, and quickstart plus Feature 011's per-answer quickstart description; record only freshly verified results in `specs/009-minimal-ui/quickstart.md` and `specs/011-session-memory/quickstart.md`. Verified: fresh focused backend, contract, UI, and mocked E2E tests pass; `make check`, `make security-verify`, `make retrieval-verify`, `make evaluation-verify`, and repository traceability pass.
- [X] T047 Scale the Responses API output-token ceiling with reasoning effort in `apps/backend/src/policylens/agent_runtime/gateway.py`, keeping it within the 8,000-token bound; test all four budgets, reported model limits, and SDK request serialization in `apps/backend/tests/unit/test_model_gateway.py` and `apps/backend/tests/api/test_model_capabilities.py`. Verified: 65 focused API/runtime/settings/gateway tests pass; Ruff, formatting, and mypy pass; no provider endpoint called.
- [X] T048 For custom Responses-compatible endpoints, send the selected reasoning effort without the optional `reasoning.summary` field; retain SDK summary requests for official OpenAI Responses. Verify both gateway settings and serialized custom request JSON in `apps/backend/tests/unit/test_model_gateway.py`. Verified: 14 gateway tests pass using fakes and a local mock transport; no provider endpoint called.

---

## Phase 12: Simplified Research Composer

- [X] T049 [US1] Remove visible search/filter/depth controls, fix Research requests to Hybrid and Standard, and preserve PDF-example-only source scoping in `apps/frontend/src/pages/ResearchPage.tsx`, `apps/frontend/src/data/example-prompts.ts`, `apps/frontend/src/App.css`, and `apps/frontend/tests/research.test.tsx`. Verified: 34 focused Research tests pass.
- [X] T050 Update Feature 009/011 requirements, traceability, quickstarts, and this task record; run focused mocked UI checks and frontend static/build checks without calling provider endpoints. Verified: 65 frontend tests, 11 mocked browser tests, formatting, lint, typecheck, production build, and repository traceability pass; no provider endpoint called.
- [X] T051 [US1] Show local cross-encoder outcome, model, candidate count, duration, and safe hybrid fallback in `apps/frontend/src/components/AgentTrail.tsx`; update the Architecture layer, answer-trail contract, Feature 009 requirements/traceability/quickstart, and add Research/Architecture regressions. Verified: 38 focused UI tests, 11 mocked Playwright tests, full `make check`, and `make security-verify` pass; no live generation or remote reranking API call was made.
- [X] T052 [US4] Expose AI-judge model/rubric, generator-model relationship, and attempted/scored/failed/skipped counts in the read-only evaluation summary API/UI; version the contract, clearly label groundedness/relevance as AI-judged and not human-validated, and test that no raw answer or judge rationale is exposed. Verified: v1.2 summary contract; backend/API and UI tests cover safe provenance, skipped coverage, and hidden answer/rationale; 11 mocked Playwright tests pass.
- [x] T053 [US4] Expose per-metric scored counts, pooled retrieval/citation anchor coverage, groundedness distribution, and condition/category breakdowns in the v1.4 read-only summary and UI; explain macro-averaged retrieval recall and preserve historical values without anchor data. Verified: the v1.4 contract/API and 6 focused UI tests pass; Python/frontend formatting, lint, type checks, frontend build, traceability, and offline case validation pass. No answer or judge rationale is exposed, and no provider call was made.

---

## Phase 13: Evaluation Metric Explanations and Cost Basis

- [X] T054 [P] [US4] Add backend and frontend regressions for provider-reported cost precedence, known/unknown model pricing, missing token usage, and per-metric disclosures in `apps/backend/tests/api/test_evaluation_summary.py`, `apps/backend/tests/api/test_feature009_contracts.py`, and `apps/frontend/tests/evaluations.test.tsx`. Verified: 19 focused backend/API contract tests and 7 evaluation UI tests pass.
- [X] T055 [US4] Version the summary contract to v1.5, estimate cost only from explicit model rates and recorded generation/judge tokens, expose estimate basis/date/model/usage gaps, and add accessible explanations to every run and condition metric in `apps/backend/src/policylens/api/evaluation_summary.py`, `specs/009-minimal-ui/contracts/evaluation-summary.schema.json`, `apps/frontend/src/api/client.ts`, `apps/frontend/src/pages/EvaluationsPage.tsx`, and `apps/frontend/src/App.css`. Verified: focused backend and UI regressions pass; unknown model IDs remain unpriced.
- [X] T056 [US4] Update Feature 009 specification, traceability, quickstart, and the historical evaluation report with token-estimate assumptions, expandable metric behavior, and fresh local verification in `specs/009-minimal-ui/spec.md`, `specs/009-minimal-ui/traceability.md`, `specs/009-minimal-ui/quickstart.md`, and `docs/evaluation/evaluation-report.md`; run focused formatting, lint, typecheck, build, and traceability checks without a live provider request. Verified: 19 focused backend/API contract tests, 71 frontend tests, and 2 mocked evaluation Playwright tests pass; Ruff formatting/lint, Python mypy, Prettier, ESLint, TypeScript, build, and repository traceability pass. No provider request was made.

---

## Dependencies & Execution Order

- Setup (T001-T002) precedes all user stories.
- Foundational contract and client work (T003-T006) blocks story implementation.
- US1 and US2 form the MVP: chat interaction is P1, while provider selection/consent is required before live answer submission.
- US3 extends the MVP response rendering and depends on the answer contract.
- US4, US5, and US6 are independent P2 views after the shared shell and client exist.
- Polish depends on the corresponding views and API contracts being complete.
- Phase 11 tests (T043) precede usage/event implementation (T044); frontend presentation (T045) depends on the stable metadata/event contract; documentation and fresh verification (T046) follow all implementation checks.
- Evaluation cost and metric work follows the v1.4 score-breakdown work: T054 tests precede T055 implementation, and T056 documentation and verification follow both.

## Parallel Opportunities

- T003 and T004 can proceed independently after package setup.
- T007-T008 can run in parallel with backend tests T011-T012 because they touch different packages.
- T017-T018, T021-T022, and T026/T030 are independent test files within their story.
- Architecture content (T027/T029) can be prepared independently from evaluation endpoint implementation.
- After the shared shell/client are complete, US4, US5, and US6 can proceed in parallel.

## Independent Test Criteria

- **US1**: Example prompt autofills without network traffic; explicit submit has loading/terminal state and cancellation.
- **US2**: Configured options match backend selection; OpenAI calls are absent without fresh consent; no fallback occurs.
- **US3**: Answer states and citations render correctly; every corpus claim opens bounded evidence; tool events contain no raw reasoning.
- **US4**: Aggregate summaries work for populated, empty, blocked, and malformed manifests without exposing raw cases or launching runs.
- **US5**: Nine architecture layers are navigable and the memory/runtime descriptions match implementation state.
- **US6**: Health states are distinct and contain no secrets or infrastructure paths.

## Implementation Strategy

1. Build the UI shell and chat/provider MVP with mocked backend tests.
2. Add backend model options and per-run provider consent before enabling provider selection.
3. Complete evidence inspection, then add evaluation, architecture, and status views independently.
4. Finish with Playwright, privacy, accessibility, and full repository validation.
