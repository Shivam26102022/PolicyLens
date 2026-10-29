# Tasks: Session Chat and Memory

**Input**: Design documents from `/specs/011-session-memory/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`

**Tests**: Required by Feature 011 acceptance criteria and the PolicyLens constitution. Tests must use synthetic content and fake providers; no live provider call is required.

**Organization**: Tasks are grouped by user story after shared persistence/model foundations.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel in different files without incomplete-task dependencies
- **[Story]**: User-story label for story phase tasks
- Each task includes its target file path

## Phase 1: Setup

**Purpose**: Create the pre-implementation traceability gate.

- [X] T000 Create `specs/011-session-memory/traceability.md` before implementation; map every FR, buildable SC, and acceptance scenario to a planned test, evaluation case, inspection, or command, and map each planned test to requirement IDs. Record any uncovered items and resolve them before implementation is approved. Verified: 22 requirements, 14 acceptance scenarios, and all planned test tasks are mapped with no uncovered items.

---

## Phase 2: Foundational

**Purpose**: Shared data and durable transcript storage required by all user stories

### Tests

- [X] T001 [P] Add workspace, session, and turn validation tests in `apps/backend/tests/unit/test_conversation_models.py`; cover UUID identifiers, `data_use_acknowledged` defaulting to false, `long_memory_enabled` defaulting to false, `title` at most 80 characters, `user_content` 1-4000 characters, `assistant_content` at most 12000 characters, and `in_progress`/`completed`/`failed` turn states. Verified: 5 model test cases pass.
- [X] T002 [P] Add SQLite storage tests in `apps/backend/tests/unit/test_conversation_store.py`; cover workspace isolation, unique session-position ordering, completed-turn selection, 100-turn pagination, and session-delete cascade. Verified: 6 store test cases pass.

### Implementation

- [X] T003 Create typed workspace, session, turn, pagination, and preference models in `apps/backend/src/policylens/conversations/models.py` with `data_use_acknowledged` and `long_memory_enabled` defaulting to false and the field constraints recorded in `specs/011-session-memory/data-model.md`. Verified: model validation tests pass.
- [X] T004 Implement transactional SQLite schema and store operations in `apps/backend/src/policylens/conversations/store.py`; use a fixed ignored path under `data/indexes/`, enforce workspace ownership for every operation, and persist the full ordered transcript. Verified: store tests pass for isolation, ordered turns, hot selection, pagination, and cascade deletion.

**Checkpoint**: Shared domain models and storage pass their focused unit tests.

---

## Phase 3: User Story 1 - Resume and Continue a Chat Session (Priority: P1)

**Goal**: Create, reopen, and continue a persisted session with the last five completed pairs as hot context.

**Independent Test**: Create two workspaces and sessions, save more than five turns in one session, reopen after reload, and verify only that session's last five completed pairs reach the agent.

### Tests

- [X] T005 [P] [US1] Add session API tests in `apps/backend/tests/api/test_sessions_api.py` for create/list/read, required `X-Workspace-ID`, 403 without data-use acknowledgement, paginated transcript history, and indistinguishable 404 responses for foreign sessions. Verified: 5 API contract cases pass.
- [X] T006 [P] [US1] Add follow-up integration tests in `apps/backend/tests/integration/test_session_followups.py` for persisted request/response order, reload restoration, five-pair hot-context bounds, and zero context leakage between sessions. Verified: 4 integration tests pass.

### Implementation

- [X] T007 [US1] Implement typed session create/list/read routes and bounded cursors in `apps/backend/src/policylens/api/sessions.py`; limit session pages to 50 and transcript pages to 100 turns. Verified: session create/list/read and transcript pagination tests pass.
- [X] T008 [US1] Register the sessions router and allow the `X-Workspace-ID` header plus required HTTP methods in `apps/backend/src/policylens/api/app.py`. Verified: session API and CORS preflight tests pass.
- [X] T009 [US1] Extend agent request/response/event models in `apps/backend/src/policylens/agent_runtime/models.py` with optional `session_id`, session persistence metadata, and safe session event types; keep each message at most 4000 characters and the conversation at most 12000 total characters, with up to 10 messages for five pairs. Verified: agent model test accepts ten messages and rejects an eleventh.
- [X] T010 [US1] Update `apps/backend/src/policylens/api/agent.py` to require recorded data-use acknowledgement, validate session ownership, save the user turn before execution, replace caller history with the five most recent completed pairs, persist the completed response, and report persistence status without raw transcript content. Verified: integration tests cover acknowledgement/ownership denial, failed-turn persistence, response order, and five-pair isolation.
- [X] T011 [US1] Add typed workspace/session API helpers and include `X-Workspace-ID` and active `session_id` in agent requests in `apps/frontend/src/api/client.ts`. Verified: 10 client tests pass; TypeScript typecheck and ESLint pass.
- [X] T012 [US1] Implement a first-use acknowledgement for public, synthetic, or appropriately anonymized content before session creation, plus session list/create/switch/history pagination/reload restoration/follow-up in `apps/frontend/src/pages/ResearchPage.tsx`; add responsive styles in `apps/frontend/src/App.css`. Verified: frontend session and research tests pass; Playwright covers acknowledgement, reload, and follow-up.
- [X] T013 [US1] Add frontend tests in `apps/frontend/tests/research.test.tsx` for acknowledgement gating, create/switch/reopen, stable browser workspace identity, follow-up after reload, and the five-pair request bound. Verified: targeted research/API/consent/memory Vitest run — 34 passed.

**Checkpoint**: A user can reload the research page, reopen a session, and continue without mixing other sessions' messages.

---

## Phase 4: User Story 2 - Recall Relevant Long-Term Context (Priority: P1)

**Goal**: Store and retrieve a maximum of five relevant conversation memories within one local workspace while preserving evidence boundaries.

**Independent Test**: Save synthetic conversation pairs in one session, retrieve from another session in the same workspace, and verify the backend sends only same-workspace untrusted context while claims still require current-run evidence.

### Tests

- [X] T014 [P] [US2] Add Chroma memory tests in `apps/backend/tests/unit/test_conversation_memory.py` for the stable memory path, versioned collection metadata, embedding-identity mismatch, exact workspace filters, maximum five results, bounded 4000-character memory documents, and refusal to issue unscoped deletes. Verified: 7 memory-service tests pass, including safe mismatch reset and workspace-exact deletes.
- [X] T015 [P] [US2] Add agent memory-boundary tests in `apps/backend/tests/integration/test_memory_context.py` for cross-session recall, cross-workspace isolation, external-embedding consent, embedding-identity mismatch status, memory retrieval failure status, and memory text never becoming citation evidence. Verified: 6 integration tests pass; runtime unit tests separately reject memory-only citations.
- [X] T016 [P] [US2] Add consent UI tests in `apps/frontend/tests/research-consent.test.tsx` for external generation and external embeddings, including fresh approval on each turn and no request before approval. Verified: 2 consent UI tests pass.
- [X] T017 [P] [US2] Add a versioned synthetic fixture in `apps/backend/tests/fixtures/conversation_memory_eval_v1.json` and a deterministic harness in `scripts/evaluate_conversation_memory.py`; compute precision@5 and recall@5 against a no-memory baseline, stratify results by fixture category, and keep evaluation data separate from runtime prompts. Verified: harness reports stratified precision@5/recall@5 and no-memory baseline; output recorded in `evaluation-results.md`.

### Implementation

- [X] T018 [US2] Implement the `ConversationMemoryService` in `apps/backend/src/policylens/conversations/memory.py` using a stable memory-specific directory beneath the configured Chroma root, a separate `policylens_chat_memory_v1` collection, provider/model/dimension metadata, exact non-empty workspace filters, at most five returned records, and fail-closed handling for mismatched embedding identity until memory is cleared. Verified: 7 focused service tests pass.
- [X] T019 [US2] Extend `apps/backend/src/policylens/agent_runtime/runtime.py` to serialize long-term memories under a distinct untrusted context field while keeping citation validation restricted to `RetrievalRun.evidence`. Verified: runtime tests confirm distinct untrusted context and reject memory-only citations.
- [X] T020 [US2] Integrate workspace-filtered memory retrieval and completed-turn writes in `apps/backend/src/policylens/api/agent.py`; require data-use acknowledgement, gate external embedding calls on current-turn consent, and expose separate retrieval/write statuses without returning memory text. Verified: 6 integration tests cover recall, consent, mismatch, retrieval/write failures, and content isolation.
- [X] T021 [US2] Expose external-embedding consent requirements in `apps/backend/src/policylens/api/model_capabilities.py` and update related response types in `apps/frontend/src/api/client.ts` and consent wording in `apps/frontend/src/components/ProviderConsentDialog.tsx`. Verified: model-options API/schema tests and external-consent UI tests pass.
- [X] T022 [US2] Add memory-stage progress labels, consent gating, and non-sensitive memory status indicators in `apps/frontend/src/pages/ResearchPage.tsx`; never display raw stored memory payloads or hidden reasoning. Verified: targeted frontend tests assert consent, safe status, and error rendering.

**Checkpoint**: Long-term memory is bounded, workspace-isolated, consent-aware, and cannot support citations or authorize tools.

---

## Phase 5: User Story 3 - Inspect and Control Stored Memory (Priority: P1)

**Goal**: Let the user pause memory, clear all workspace memories, and delete a session and its derived memories with explicit result states.

**Independent Test**: Disable memory, clear memory, and delete a session; verify no cleared content appears in later requests and every storage failure is visibly distinct from success.

### Tests

- [X] T023 [P] [US3] Add preference, acknowledgement, clear-memory, session-delete, workspace-isolation, and injected storage-failure tests in `apps/backend/tests/api/test_memory_api.py`; verify literal preference/memory routes work ahead of dynamic UUID routes. Verified: 8 API tests pass, including vector-before-transcript ordering and explicit failure responses.
- [X] T024 [P] [US3] Add memory-control UI tests in `apps/frontend/tests/research-memory.test.tsx` for acknowledgement, preference persistence, clear confirmation, session deletion, and accessible failure states. Verified: 2 UI tests pass for success and preference/deletion failures.

### Implementation

- [X] T025 [US3] Implement workspace preference read/update, acknowledgement enforcement, explicit user-initiated memory clearing/recreation after an embedding-identity mismatch, exact-filter memory clearing, and vector-before-transcript session deletion in `apps/backend/src/policylens/api/sessions.py`; fail closed without silently resetting or re-embedding memories, register literal preference/memory routes before `/{session_id}`, keep vectors if vector deletion fails, and never report partial deletion as success. Verified: 8 API tests and 7 memory unit tests pass; mismatch resets only when no other workspace records would be affected.
- [X] T026 [US3] Add visible long-memory enable/disable, clear-memory, and delete-session controls with confirmations and explicit pending/error/success states in `apps/frontend/src/pages/ResearchPage.tsx` and `apps/frontend/src/App.css`. Verified: UI control tests and the persistent-session Playwright workflow pass.
- [X] T027 [US3] Add a Playwright workflow in `apps/frontend/tests/e2e/research.spec.ts` that acknowledges data-use limits, creates a session, reloads and resumes it, disables and clears memory, and deletes the session. Verified: complete Playwright suite — 10 passed.

**Checkpoint**: Users can inspect and control persistent chat data; failed deletion never appears successful.

---

## Phase 6: Polish and Cross-Cutting Validation

**Purpose**: Traceability, fresh quickstart evidence, and full feature validation

- [X] T028 Update `specs/011-session-memory/traceability.md` with implemented tests and verification evidence; confirm every FR/SC, acceptance scenario, and test remains mapped, and resolve any coverage gaps. Verified: `python3 scripts/check_traceability.py` passed with no unmapped items.
- [X] T029 Run the focused commands and synthetic evaluation in `specs/011-session-memory/quickstart.md`; record configuration, seed (or why none applies), stratified precision@5/recall@5, no-memory baseline, retrieval latency, cost estimate, qualitative errors, negative results, limitations, skipped live-provider checks, and any local-index prerequisite in `specs/011-session-memory/evaluation-results.md` and `quickstart.md`. Verified: backend 41/41 and frontend 42/42 focused tests passed; deterministic results and limitations are recorded.
- [X] T030 Run `make check` and the relevant security/evaluation verification from the repository root; resolve regressions and record final evidence in `specs/011-session-memory/quickstart.md`. Verified: `make check` (263 backend, 39 MCP, 115 script, 56 frontend tests), `make security-verify`, `make retrieval-verify`, and `make evaluation-verify` passed; evidence is recorded in both quickstarts.

---

## Phase 7: Per-Answer Operational Trail

**Purpose**: Keep each assistant response's safe processing history attached to that response and restorable from session history.

### Tests

- [X] T031 [US3] Add frontend tests in `apps/frontend/tests/research.test.tsx` and `apps/frontend/tests/e2e/research.spec.ts` proving that multiple answers keep independent expandable trails and that a saved trail returns after session reload; verify no hidden reasoning or raw tool names are displayed. Verified: 26 focused Research UI tests and 11 mocked Playwright tests pass.

### Implementation

- [X] T032 [US3] Preserve each `AgentAnswerResponse` on its assistant transcript message in `apps/frontend/src/pages/ResearchPage.tsx`; render that response's safe events in an accessible expandable trail while retaining the live trail during active runs. Verified per-answer isolation and reload restoration in unit and E2E tests.
- [X] T033 [US3] Add compact responsive styles in `apps/frontend/src/App.css` and refresh `specs/009-minimal-ui/quickstart.md`, `specs/011-session-memory/quickstart.md`, and this feature's traceability with the per-answer behavior and verification results. Verified: frontend production build, `make check`, and traceability passed.

---

## Phase 8: MCP Passage Verification and Citation Polish

**Purpose**: Verify locally ranked passages through the registered MCP resource before generation and make that stage visible on each answer.

### Tests

- [X] T034 Add batched MCP resource and runtime tests in `apps/backend/tests/unit/test_mcp_client.py` and `apps/backend/tests/unit/test_agent_runtime.py`; cover request order/connection reuse, invalid and duplicate keys, MCP failures, provenance mismatches, and fail-closed model suppression. Verified: focused MCP/runtime/model suite — 47 passed.
- [X] T035 Add per-answer resource lifecycle assertions in `apps/frontend/tests/research.test.tsx` and `apps/frontend/tests/e2e/research.spec.ts`, including verified passage counts and safe error display. Verified: 26 focused Research UI tests and 11 mocked Playwright tests passed.

### Implementation

- [X] T036 Wire the production MCP adapter as an `AgentRuntime` passage reader in `apps/backend/src/policylens/api/agent.py`; fetch selected exact IDs and compare passage text, text/content hashes, location/row metadata, and source metadata with the local ranked result before model generation. Fail safely on any adapter error or mismatch. Verified: focused runtime/API tests — 55 passed.
- [X] T037 Add typed MCP resource start/completion events to `apps/backend/src/policylens/agent_runtime/models.py`, `state.py`, and `specs/004-agent-runtime/contracts/agent-api.schema.json`; display status, duration, passage count, and safe actionable failure codes in `apps/frontend/src/components/AgentTrail.tsx` and `ResearchPage.tsx`. Verified: frontend lint/typecheck and 27 focused Research UI tests passed.
- [X] T038 Refresh Feature 009/011 quickstarts, Feature 005 resource lifecycle documentation, Feature 011 traceability, and deterministic evaluation latency with current results. Verified: `make check` (270 backend, 39 MCP, 115 scripts, 57 frontend), `make security-verify`, `make retrieval-verify`, `make evaluation-verify`, and 11 mocked Playwright tests passed.

---

## Phase 9: Default-Open Answer Activity

### Tests

- [X] T039 [US3] Update `apps/frontend/tests/research.test.tsx` and `apps/frontend/tests/e2e/research.spec.ts` to assert answer activity is open by default, can be collapsed/reopened, and is open after session reload. Verified: all 65 frontend unit tests and 11 mocked Playwright tests pass.

### Implementation and Documentation

- [X] T040 [US3] Add a clear chevron toggle to each default-open per-answer trail in `apps/frontend/src/components/AgentTrail.tsx` and `apps/frontend/src/App.css`; update Feature 011's FR-016/SC-008 traceability and both Feature 009/011 quickstarts to describe default-open behavior. Verified: 65 frontend tests, 11 mocked Playwright tests, Prettier, ESLint, TypeScript, production build, and repository traceability passed; no provider endpoint called.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T000 creates and checks the baseline traceability matrix before implementation; no dependency or service setup change is needed.
- **Foundational (Phase 2)**: Required before any story because all session and memory flows use the shared validated data model and SQLite store.
- **User Story 1 (Phase 3)**: Depends on Phase 2 and delivers persistent sessions and follow-up context.
- **User Story 2 (Phase 4)**: Depends on User Story 1 for saved completed turns and session identity; adds long-term vector recall.
- **User Story 3 (Phase 5)**: Depends on User Story 2 so pause/clear/delete controls cover both SQLite transcripts and Chroma memories.
- **Polish (Phase 6)**: Depends on all stories being implemented and their focused tests passing.
- **Per-Answer Operational Trail (Phase 7)**: Depends on the persisted assistant response and typed safe events delivered by User Story 1; private reasoning remains out of scope.
- **MCP Passage Verification (Phase 8)**: Depends on the registered Feature 005 passage resource and locally ranked current-run evidence; failed resource reads or mismatches stop model execution.

### User Story Dependencies

- **US1 (P1)**: Starts after the foundation; independent test is persisted session continuation with exact session isolation.
- **US2 (P1)**: Depends on US1's completed-turn persistence; independent test is same-workspace semantic recall with citation isolation.
- **US3 (P1)**: Depends on US1 and US2; independent test is end-to-end pause/clear/delete behavior and explicit storage errors.

### Parallel Opportunities

- T001 and T002 can run in parallel because they create distinct test files.
- Within US1, T005 and T006 can run in parallel; T011's API helper work can proceed after the backend request shape in T009 is agreed.
- Within US2, T014-T017 can run in parallel because each targets distinct test/fixture/harness files.
- Within US3, T023 and T024 can run in parallel because they target separate backend and frontend test files.
- Story implementation phases remain sequential because long-term memory and deletion depend on durable session turns.

## Parallel Example: User Story 2

```text
Task: T014 Chroma workspace-filter and result-bound tests in apps/backend/tests/unit/test_conversation_memory.py
Task: T015 agent memory/citation boundary tests in apps/backend/tests/integration/test_memory_context.py
Task: T016 external-processing consent UI tests in apps/frontend/tests/research-consent.test.tsx
Task: T017 synthetic memory-retrieval evaluation harness in scripts/evaluate_conversation_memory.py
```

## Implementation Strategy

### MVP First

1. Complete the shared models and SQLite store.
2. Complete User Story 1 and verify persistence, reload, and five-pair follow-up behavior.
3. Validate that increment independently before adding semantic memory.
4. Add User Story 2, then User Story 3.

### Incremental Delivery

1. Shared validated models and local transcript store.
2. Persistent session UI and backend-owned follow-up context.
3. Workspace-isolated Chroma memory with external-consent and evidence-boundary tests.
4. User memory controls and deletion semantics.
5. Traceability, quickstart results, and repository checks.

## Notes

- `[P]` tasks use distinct files and have no dependency on unfinished work.
- Every implementation task has a concrete source or documentation path.
- Tests use synthetic content and fake provider/vector adapters; live provider requests are not required.
- Do not mark a task complete without recording its verification result.
