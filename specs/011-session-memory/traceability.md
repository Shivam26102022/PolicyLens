# Feature 011 Traceability

This matrix records implemented verification surfaces. The synthetic memory evaluation validates only deterministic retrieval mechanics; it is not evidence of answer-quality improvement.

## Functional Requirements and Success Criteria

| Requirement | Implemented evidence |
|---|---|
| FR-001: create, list, open, delete sessions | `apps/backend/tests/api/test_sessions_api.py`; `apps/backend/tests/api/test_memory_api.py`; `apps/frontend/tests/research.test.tsx`; Playwright session workflow |
| FR-002: ordered persistence and restore | `apps/backend/tests/unit/test_conversation_store.py`; `apps/backend/tests/integration/test_session_followups.py`; `apps/frontend/tests/research.test.tsx`; Playwright reload/resume |
| FR-003: last five completed pairs | `apps/backend/tests/unit/test_conversation_store.py`; `apps/backend/tests/integration/test_session_followups.py`; frontend follow-up asserts caller history is empty |
| FR-004: warm history, not wholesale prompt context | session-history pagination in `apps/backend/tests/api/test_sessions_api.py`; follow-up context tests; frontend history restore/pagination |
| FR-005: same-workspace memory, top five | `apps/backend/tests/unit/test_conversation_memory.py`; `apps/backend/tests/integration/test_memory_context.py`; synthetic harness and results |
| FR-006: memory untrusted and not evidence | `apps/backend/tests/unit/test_agent_runtime.py`; `apps/backend/tests/integration/test_memory_context.py` |
| FR-007: workspace isolation and derived-memory deletion | conversation store and Chroma memory unit tests; `apps/backend/tests/api/test_memory_api.py`; memory integration tests |
| FR-008: pause and clear long-term memory | `apps/backend/tests/api/test_memory_api.py`; `apps/frontend/tests/research-memory.test.tsx`; Playwright memory controls |
| FR-009: session, transcript, next message, states | `apps/frontend/tests/research.test.tsx`; `apps/frontend/tests/research-memory.test.tsx`; `apps/frontend/tests/e2e/research.spec.ts` |
| FR-010: safe operational progress only | runtime/API event tests; Research Agent trail tests verify safe stage labels, MCP passage-resource lifecycle, and errors without memory text or raw tool names; passage mismatches fail before model execution |
| FR-011: fresh external generation and embedding consent | `apps/backend/tests/integration/test_memory_context.py`; `apps/frontend/tests/research-consent.test.tsx`; provider-consent Playwright tests |
| FR-012: application-managed context | `apps/backend/tests/integration/test_session_followups.py`; frontend request assertions; provider-independent runtime tests |
| FR-013: typed backend-only browser API | `apps/frontend/tests/api/client.test.ts`; frontend security tests; no direct provider/vector client in the web app |
| FR-014: explicit persistence/retrieval/deletion failures | memory context/API failure tests; `apps/frontend/tests/research-memory.test.tsx` accessible failure assertions |
| FR-015: recorded acknowledgement gates persistence | conversation model/store/session API tests; `apps/frontend/tests/research.test.tsx`; Playwright acknowledgement workflow |
| FR-016: per-answer safe activity is open by default, has a collapse/reopen control, and restores with its session response | `apps/frontend/tests/research.test.tsx` verifies default-open independent trails, toggling, and passage-resource status/count; `apps/frontend/tests/e2e/research.spec.ts` verifies default-open/toggle behavior, reload restoration, citations, and passage verification; trail summaries are derived only from allow-listed event types |
| SC-001: ordered transcript restored after reload | session follow-up integration test; frontend reload test; Playwright reload/resume workflow |
| SC-002: at most five pairs from active session | store/hot-context integration tests; frontend sends no caller-controlled transcript |
| SC-003: top-five workspace-filtered memory and deletion | Chroma service tests, memory API tests, and synthetic evaluation |
| SC-004: memory cannot ground citations | `test_long_term_memory_cannot_be_used_as_citation_evidence` in `test_agent_runtime.py` |
| SC-005: clear/delete controls prevent reuse | service/API clear and delete tests; UI controls and Playwright workflow |
| SC-006: failures are accessible and not success-shaped | backend retrieval/write/delete failure tests; frontend memory-control failure tests |
| SC-007: acknowledgement gates persistence; memory defaults off | model/store/API tests; frontend acknowledgement and preference tests |
| SC-008: per-response trail is open by default, independently toggleable, and remains associated after reload | `research.test.tsx` verifies adjacent answers retain separate events and can be collapsed/reopened; Playwright verifies default-open state after a response and reload |

## Acceptance Scenarios

| Scenario | Implemented verification |
|---|---|
| US1-A1: save user and assistant messages in order | `test_session_followups.py`; `test_conversation_store.py` |
| US1-A2: restore saved transcript and latest response | `test_session_followups.py`; `research.test.tsx`; Playwright reload/resume |
| US1-A3: follow-up uses at most five completed pairs | `test_session_followups.py`; frontend follow-up request test |
| US1-A4: switching sessions does not leak context | `test_session_followups.py`; `research.test.tsx` |
| US2-A1: store bounded memory only when enabled | `test_conversation_memory.py`; `test_memory_context.py` |
| US2-A2: retrieve up to five same-workspace memories | `test_conversation_memory.py`; `test_memory_context.py`; evaluation fixture |
| US2-A3: memory cannot ground claims or tools | runtime citation-boundary test; prompt/context separation |
| US2-A4: other workspaces remain isolated | Chroma exact-filter tests; memory integration test |
| US2-A5: external model and embedding need fresh consent | memory integration and consent UI tests; provider-consent E2E |
| US3-A1: show safe session/memory operational status | API event tests; research UI status/activity tests include MCP passage verification |
| US3-A2: delete transcript and derived memories | memory API ordering/failure tests; Playwright delete workflow |
| US3-A3: clear memory prevents reuse | Chroma clear tests; API clear response; Playwright clear workflow |
| US3-A4: storage/deletion failures are explicit | memory API failure tests; UI accessible error tests |
| US3-A5: acknowledgement gates persistence | session API, agent integration, frontend, and Playwright tests |
| US3-A6: each answer expands to its own safe processing events, including after reload | `research.test.tsx`; Playwright session-resume workflow |

## Test-to-Requirement Map

| Test task | Test surface | Requirement IDs |
|---|---|---|
| T001 | `apps/backend/tests/unit/test_conversation_models.py` | FR-015, SC-007 |
| T002 | `apps/backend/tests/unit/test_conversation_store.py` | FR-002, FR-007, SC-001 |
| T005 | `apps/backend/tests/api/test_sessions_api.py` | FR-001, FR-015, SC-007 |
| T006 | `apps/backend/tests/integration/test_session_followups.py` | FR-002, FR-003, FR-004, FR-012, SC-001, SC-002 |
| T013 | `apps/frontend/tests/research.test.tsx` | FR-001, FR-002, FR-003, FR-009, FR-015, SC-001, SC-002, SC-007 |
| T014 | `apps/backend/tests/unit/test_conversation_memory.py` | FR-005, FR-007, SC-003 |
| T015 | `apps/backend/tests/integration/test_memory_context.py` | FR-006, FR-007, FR-010, FR-011, FR-014, SC-003, SC-004, SC-006 |
| T016 | `apps/frontend/tests/research-consent.test.tsx` | FR-011, SC-006 |
| T017 | fixture and `scripts/evaluate_conversation_memory.py` | FR-005, SC-003 |
| T023 | `apps/backend/tests/api/test_memory_api.py` | FR-007, FR-008, FR-014, FR-015, SC-003, SC-005, SC-006, SC-007 |
| T024 | `apps/frontend/tests/research-memory.test.tsx` | FR-008, FR-009, FR-010, FR-014, FR-015, SC-005, SC-006, SC-007 |
| T027 | `apps/frontend/tests/e2e/research.spec.ts` | FR-001, FR-002, FR-003, FR-007, FR-008, FR-009, FR-014, FR-015, SC-001, SC-002, SC-005, SC-006, SC-007 |
| T031, T039 | `apps/frontend/tests/research.test.tsx`; `apps/frontend/tests/e2e/research.spec.ts` | FR-010, FR-016, SC-008 |
| T034 | `apps/backend/tests/unit/test_mcp_client.py`; `apps/backend/tests/unit/test_agent_runtime.py` | FR-010, FR-016 |
| T035 | `apps/frontend/tests/research.test.tsx`; `apps/frontend/tests/e2e/research.spec.ts` | FR-010, FR-016, SC-008 |

## Verification Evidence

- `python3 scripts/check_traceability.py` passed: 67 global requirements, 14 feature requirements, 11 acceptance criteria, 5 success criteria, and 10 demo scenarios checked. Every feature requirement, success criterion, acceptance scenario, and planned test task is mapped; no uncovered items remain.
- Focused backend session/memory tests passed **41/41**; focused frontend session, consent, memory-control, and API tests passed **50/50**. Focused MCP/runtime/API regressions passed **55/55** and Research UI tests passed **27/27**.
- `make check` passed formatting, lint, Python and TypeScript typechecks, **284 backend tests**, **39 MCP tests**, **122 script tests**, **65 frontend tests**, and traceability.
- `make security-verify` passed **140 selected backend/security/evaluation tests**, **13 MCP tests**, production build, **65 frontend tests**, and secret scanning with no findings.
- All 11 mocked Playwright tests passed, including acknowledgement, session restore/follow-up, per-answer trail restoration, memory preference, clear, and delete.
- The refreshed memory evaluation in [evaluation-results.md](evaluation-results.md) reported macro precision@5 **0.2667**, recall@5 **0.6667**, and fixture-ranking latency **0.0730 ms mean / 0.1151 ms max**. No live provider calls were made and the evaluation does not exercise production Chroma embeddings. `make retrieval-verify` reported `status: ready`; `make evaluation-verify` validated 36 approved cases across 20 categories and both splits.
- Selected evidence passage IDs, text, hashes, and provenance were verified through the registered MCP resource before generation; mismatch and stale-catalog errors are specific and fail closed. PDF citation actions and Markdown links now share the in-app preview, served from the backend's hash-verified local source endpoint; tests cover inline/range/CORS behavior, canonical mapping, page/excerpt parameters, source-filter payloads, and unregistered links staying external. Backend source/retrieval API tests passed **13**, the full frontend suite passed **65**, focused Research UI passed **33**, and all **11 mocked Playwright tests** passed. Build, lint, and formatting checks passed; a local smoke test served the India PDF without remote requests.

## Unmapped Items

None identified. All required repository checks passed.
