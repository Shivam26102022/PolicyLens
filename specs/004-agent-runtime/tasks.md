# Tasks: Bounded Agent Runtime

**Input**: Design documents from `/specs/004-agent-runtime/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`

**Tests**: Tests are required by the Feature 004 specification and use fake providers/adapters; no live OpenAI/Foundry request runs in the default suite.

## Phase 1: Setup

**Purpose**: Add validated provider and bounded runtime configuration.

- [x] T001 [P] Add settings tests for deployment-model/base-URL pairing, standard `OPENAI_MODEL`, missing credentials, retry/call/token bounds, effective model selection, and no provider fallback in `apps/backend/tests/unit/test_settings.py` and `apps/backend/tests/unit/test_generation_baseline.py` (AC-004-02, AGENT-004-02, SEC-004-01).
- [x] T002 Implement `openai_deployment_model`, `openai_base_url`, effective model selection, and bounded per-tool/retry/output settings in `apps/backend/src/policylens/settings.py`; update `apps/backend/src/policylens/retrieval/generation.py` to use the effective model, base URL, and Foundry chat endpoint; update `.env.example` with the base URL placeholder while preserving `OPENAI_DEPLOYMENT_MODEL=gpt-6-luna` (AGENT-004-02, SEC-004-01).
- [x] T003 [P] Add Feature 004 configuration and Foundry/standard OpenAI setup notes to `README.md` and `docs/architecture/architecture.md` (AGENT-004-02, DOC-004-01).

## Phase 2: Foundational Contracts and State

**Purpose**: Establish answer models, host state transitions, and a safe per-run event ledger before either user story uses the agent.

- [x] T004 [P] Add model tests for answer statuses, claim/citation/calculation references, conflicts, terminal errors, and response bounds in `apps/backend/tests/unit/test_agent_models.py` (AC-004-01 through AC-004-03, AGENT-004-03).
- [x] T005 [P] Add state-machine and event-redaction tests for valid transitions, terminal states, sequence bounds, and excluded prompt/query/evidence/tool payloads in `apps/backend/tests/unit/test_agent_state.py` (AGENT-004-01, OBS-004-01, SEC-004-01).
- [x] T006 Implement Pydantic request/draft/response/calculation/event models and status invariants in `apps/backend/src/policylens/agent_runtime/models.py`, matching `specs/004-agent-runtime/contracts/agent-api.schema.json` (AGENT-004-03, AGENT-004-04).
- [x] T007 Implement the finite host-owned state machine, run budget counters, trace ID, and redacted event builder in `apps/backend/src/policylens/agent_runtime/state.py` and `apps/backend/src/policylens/agent_runtime/traces.py` (AGENT-004-01, AGENT-004-02, OBS-004-01).
- [x] T008 Validate the public request/draft/response JSON Schema and cross-schema citation references with representative instances in `scripts/tests/test_agent_contracts.py` (AGENT-004-03, DOC-004-01).

**Checkpoint**: Typed run state and response invariants reject invalid terminal outcomes before model integration.

## Phase 3: User Story 1 - Answer from Evidence (Priority: P1)

**Goal**: Return validated claim-linked answers or clarification, abstention, conflict, blocked, and safe-failure outcomes.

**Independent Test**: Run mocked structured outputs for each status; verify only current-run citations survive and all other paths fail safely.

### Tests for User Story 1

- [x] T009 [P] [US1] Add runtime tests for retrieval-first execution, empty evidence, ambiguity, conflict, out-of-scope, malformed output, fabricated citations, paraphrase acceptance with exact quotes, host-rendered calculation claims, timeouts, and citation validation in `apps/backend/tests/unit/test_agent_runtime.py` (AC-004-01 through AC-004-03, AGENT-004-01 through AGENT-004-04).
- [x] T010 [P] [US1] Add OpenAI/Foundry client-construction tests using an injected fake `AsyncOpenAI`, verifying deployment-model precedence, custom base URL, explicit standard endpoint, disabled SDK retries/tracing, and no network calls in `apps/backend/tests/unit/test_agent_provider.py` (AGENT-004-02, OBS-004-01, SEC-004-01).
- [x] T011 [P] [US1] Add `POST /agent/answer` API tests for valid request/response, stable failures, trace IDs, and provider metadata in `apps/backend/tests/api/test_agent_api.py` (AC-004-01 through AC-004-03, OBS-004-01).

### Implementation for User Story 1

- [x] T012 [US1] Add versioned system instructions that delimit evidence as untrusted and require structured, citation-linked output in `prompts/agent/system-v1.md` (SEC-004-01, AGENT-004-03).
- [x] T013 [US1] Implement explicit OpenAI/Foundry provider construction and one-agent creation with typed output, deterministic settings, no handoffs, and disabled SDK tracing in `apps/backend/src/policylens/agent_runtime/provider.py` and `apps/backend/src/policylens/agent_runtime/runtime.py` (AGENT-004-02, SEC-004-01).
- [x] T014 [US1] Implement retrieval-first orchestration, host-owned state transitions, total-run timeout/cancellation, structured output validation, extractive current-run citation validation, host-rendered calculation claims, and safe status/error mapping in `apps/backend/src/policylens/agent_runtime/runtime.py` (AC-004-01 through AC-004-03, AGENT-004-01 through AGENT-004-04).
- [x] T015 [US1] Add `POST /agent/answer` with lazy backend runtime wiring and typed OpenAPI response in `apps/backend/src/policylens/api/agent.py` and `apps/backend/src/policylens/api/app.py` (AC-004-01 through AC-004-03).

**Checkpoint**: Evidence-only runs return valid current-run citations; missing/ambiguous/conflicting/out-of-scope evidence never becomes an unsupported answer.

## Phase 4: User Story 2 - Use Deterministic Tools Within Budgets (Priority: P1)

**Goal**: Permit one bounded deterministic statistics tool through a typed adapter that can be replaced by Feature 005's production MCP client.

**Independent Test**: Use fake adapters to exercise valid tool results, invalid arguments/output, timeout, transient retry limits, call budgets, and tool-derived calculation provenance.

### Tests for User Story 2

- [x] T016 [P] [US2] Add adapter tests for validated `query_statistics` requests/results, error taxonomy, source-row provenance, oversized output, permission failure, transient-only retry, and total/per-tool call budgets in `apps/backend/tests/unit/test_agent_tools.py` (AC-004-04 through AC-004-06, AGENT-004-02, AGENT-004-04).
- [x] T017 [P] [US2] Add runtime integration tests proving only the allow-listed tool is model-visible and tool evidence becomes a validated calculation record in `apps/backend/tests/unit/test_agent_runtime.py` and `apps/backend/tests/unit/test_agent_tools.py` (AC-004-04 through AC-004-06, SEC-004-01).

### Implementation for User Story 2

- [x] T018 [US2] Define typed `StatisticsToolAdapter` protocol, request/result validation, transient error classification, and fake adapter fixture aligned with Feature 005's draft `query_statistics` contract in `apps/backend/src/policylens/agent_runtime/tools.py` (AC-004-04 through AC-004-06).
- [x] T019 [US2] Expose only the `query_statistics` function tool; enforce per-tool/total call budgets, timeout/cancellation, finite transient retry, and deterministic calculation provenance in `apps/backend/src/policylens/agent_runtime/tools.py` and `apps/backend/src/policylens/agent_runtime/runtime.py` (AGENT-004-02, AGENT-004-04, SEC-004-01).
- [x] T020 [US2] Validate calculation claims against recorded tool results and input-row evidence; map malformed or unauthorized adapter output to stable fail-safe results in `apps/backend/src/policylens/agent_runtime/runtime.py` (AC-004-05, AGENT-004-03, AGENT-004-04).

**Checkpoint**: Only the typed statistics operation is callable, and invalid or untrusted tool results cannot enter an answered response.

## Phase 5: User Story 3 - Inspect a Run (Priority: P2)

**Goal**: Return safe, ordered run events and provider/model/prompt metadata without exposing hidden reasoning or raw payloads.

**Independent Test**: Assert event schema/order and scan API responses/log capture for prompts, credentials, raw query/evidence/tool bodies, and private reasoning.

- [x] T021 [P] [US3] Add API and logging tests for trace ID, event ordering, tool summaries, provider/model/prompt fields, and sensitive-content redaction in `apps/backend/tests/api/test_agent_api.py` and `apps/backend/tests/unit/test_agent_state.py` (AC-004-07, OBS-004-01, SEC-004-01).
- [x] T022 [US3] Connect Agents SDK lifecycle hooks to safe event summaries, suppress SDK tracing, and ensure no callback logs model prompts, inputs, outputs, or tool payloads in `apps/backend/src/policylens/agent_runtime/traces.py` and `apps/backend/src/policylens/agent_runtime/runtime.py` (AGENT-004-01, OBS-004-01, SEC-004-01).
- [x] T023 [US3] Return the trace ID, safe event list, provider/model/prompt/index identity, and stable terminal reason in the public response schema/API in `apps/backend/src/policylens/agent_runtime/models.py` and `apps/backend/src/policylens/api/agent.py` (AC-004-07, OBS-004-01).

**Checkpoint**: A reviewer can reconstruct state/tool choices from safe events without access to private reasoning or raw evidence payloads.

## Phase 6: Polish and Evaluation

- [x] T024 [P] Create a versioned author-curated set of tool-requiring cases and a deterministic comparison harness using the same cases/evidence for agent and Feature 003 baseline in `data/evaluation/agent-tool-cases.json`, `scripts/evaluate_agent.py`, `scripts/tests/test_agent_evaluation.py`, and `Makefile` (`agent-eval`) (EVAL-004-01, SC-004-03).
- [ ] T025 Run the controlled agent-versus-baseline comparison on the frozen tool-required cases and record metrics, negative results, and limitations in `docs/evaluation/agent-evaluation.md`; require explicit authorization for provider calls and do not claim the agent demonstrates value from mocks or historical Feature 007 runs (EVAL-004-01, SC-004-03).
- [x] T026 [P] Update `README.md`, `docs/architecture/architecture.md`, `docs/traceability/traceability.md`, `specs/README.md`, `POLICYLENS_MASTER_SPEC.md`, and `specs/001-foundation/plan.md` with the agent route, Foundry config, Feature 005 boundary, safety limits, and verification evidence (DOC-004-01, AGENT-004-01 through AGENT-004-04).
- [x] T027 Run the Feature 004 quickstart and all required Python quality, test, traceability, schema, data, and retrieval gates; record live Foundry tests as unrun unless explicitly configured and authorized in `specs/004-agent-runtime/tasks.md` (SC-004-01 through SC-004-03).
- [ ] T028 Run Feature 004 convergence against the spec, plan, tasks, contracts, tests, and outputs; reconcile remaining gaps in `specs/004-agent-runtime/tasks.md` (SC-004-01 through SC-004-03).

## Dependencies and Execution Order

### Phase Dependencies

- Setup (Phase 1) precedes all runtime work.
- Foundational models/state (Phase 2) block all user stories.
- User Story 1 (Phase 3) uses Feature 003 retrieval/citations.
- User Story 2 (Phase 4) builds on the state/runtime from User Story 1 and uses a mockable Feature 005 adapter.
- User Story 3 (Phase 5) observes the completed answer/tool run.
- Polish/evaluation (Phase 6) depends on all three stories.

### Parallel Opportunities

- T001 and T003 are independent setup/test documentation work.
- T004 and T005 can be written in parallel; implementations follow their tests.
- T009, T010, and T011 cover separate files and can be prepared in parallel.
- T016 and T017 can be prepared in parallel after foundational models exist.
- T024 and T026 touch separate files and can be prepared in parallel.

## Implementation Strategy

1. Finish provider settings and foundational typed state/contracts.
2. Deliver User Story 1 as the first independently testable increment.
3. Add the mockable deterministic tool adapter and budget enforcement for User Story 2.
4. Add redacted run inspection for User Story 3.
5. Run the controlled comparison harness; do not claim the agent adds value without a measured result.
6. Run quickstart, quality gates, traceability, and convergence.

## Phase 7: Convergence

- [ ] T029 Complete the controlled agent-versus-baseline comparison with an explicitly authorized provider and the Feature 005 MCP adapter; the current Feature 004 command is readiness-only and has no comparison executor. Record tool reliability, output validity, latency, failures, and limitations, and retain the agent only if the measured comparison supports value per SC-004-03 (partial).

## Phase 8: Readable Claims and Actionable Citation Failures

- [X] T030 [P] Add regression coverage for paraphrased claims, canonicalization of nonmatching model excerpt hints, fabricated passage rejection, and frontend display of safe citation reasons in `apps/backend/tests/unit/test_agent_runtime.py`, `apps/backend/tests/unit/test_agent_models.py`, and `apps/frontend/tests/research.test.tsx`. Verified: 42 focused backend runtime/model/provider/contract tests pass after canonicalization; the 29 Research UI tests pass from the earlier UI change.
- [X] T031 Allow concise evidence-linked claim text while retaining current-run passage and source-provenance validation; canonicalize nonmatching model excerpt hints to exact passage text and use the versioned agent-v2 prompt in `apps/backend/src/policylens/agent_runtime/models.py`, `runtime.py`, `gateway.py`, `mlx_provider.py`, and `prompts/agent/system-v2.md`. Verified: focused runtime/model/provider tests pass; no live provider call was made.
- [X] T032 Update Feature 004/006 contracts and rationale, Feature 009 traceability/UI messaging, and provider-comparison prompt-version compatibility. Verified: contract/provider evaluation tests pass, Python and frontend static checks pass, and repository traceability passes.

## Verification Record

- `make test-python`: 176 passed (backend 133, MCP 4, scripts 39).
- `make lint-python`, `make typecheck-python`, and `make format-check-python`: passed; mypy checked 66 backend/script and 8 MCP files.
- `make traceability`: passed; `make data-verify` verified all six source hashes; `make retrieval-verify` reports the active v4 index ready.
- `agent-api.schema.json` and its Feature 003 retrieval/citation references passed Draft 2020-12 validation; representative request, draft, answered response, and no-evidence response instances validated.
- `make agent-eval` validated the six-case set without a live request. After `OPENAI_BASE_URL` was configured, `python -m scripts.evaluate_agent --live` advanced to `blocked`/`FEATURE_005_ADAPTER_NOT_AVAILABLE`. No live request or agent-value comparison was made; SC-004-03 remains unverified until Feature 005 supplies its production adapter.
- No live OpenAI/Foundry calls were made. This workspace has no Git metadata, so clean-checkout/tracking claims are not made.