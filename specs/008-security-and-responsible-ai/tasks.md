---
description: "Implementation tasks for local-only security and responsible AI assurance"
---

# Tasks: Security and Responsible AI

**Input**: Design documents from `/specs/008-security-and-responsible-ai/`

**Prerequisites**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Required by the specification and constitution. Reuse existing Feature 003-007 tests and add deterministic synthetic/fake tests for any uncovered boundary. No live provider calls are required.

**Organization**: Inventory current controls, fill the threat-model matrix, test missing attacks, and publish privacy/residual-risk artifacts. No new service or production authentication is in scope.

## Phase 1: Setup

**Purpose**: Establish versioned security evidence and local verification commands.

- [X] T001 Create a strict security-test-result schema in `specs/008-security-and-responsible-ai/contracts/security-test-result.schema.json` and validate it with JSON Schema tests.
- [X] T002 Add `security-verify` to the root `Makefile`; it must run offline fixture coverage and secret scans without provider calls.
- [X] T003 Add an append-only security test-result manifest at `data/manifests/security-test-manifest.json` using the existing evaluation registry writer.

---

## Phase 2: Foundational

**Purpose**: Define the nine boundaries and reusable attack-result validation before adding fixtures.

- [X] T004 [P] Add strict boundary, attack-fixture, and residual-risk models in `scripts/security_audit.py` using the nine boundary IDs in `data-model.md`.
- [X] T005 Add an offline loader for the versioned synthetic fixture set in `scripts/security_audit.py`; reject unknown boundary IDs, unknown fixture IDs, duplicate IDs, and fixtures containing real source text or secret-shaped values.
- [X] T006 [P] Add contract tests in `scripts/tests/test_security_audit.py` for every schema constraint and the local-only deployment scope.
- [X] T007 [P] Add tests in `scripts/tests/test_security_audit.py` proving audit validation and reporting do not instantiate OpenAI, MLX, or MCP clients.

**Checkpoint**: Boundary/fixture records validate and security audit mode is offline by default.

---

## Phase 3: User Story 1 - Review Trust Boundaries (Priority: P1)

**Goal**: Let reviewers inspect assets, principals, controls, failures, and abuse cases at all nine boundaries.

**Independent Test**: The boundary matrix contains all nine required IDs and every row has assets/data class, identity, authorization, validation, logging, failure, abuse cases, and test references.

### Tests for User Story 1

- [X] T008 [P] [US1] Add a completeness test in `scripts/tests/test_security_audit.py` requiring all nine boundary IDs and all mandatory threat-model fields.
- [X] T009 [P] [US1] Add a traceability test in `scripts/tests/test_security_audit.py` requiring each in-scope boundary to reference at least one existing test or a documented local limitation.

### Implementation for User Story 1

- [X] T010 [US1] Create `docs/security/threat-model.md` with a data-flow/trust-boundary diagram and STRIDE or equivalent analysis for browser/frontend, frontend/API, API/OpenAI, API/MLX, MCP host/server, MCP/server-data, ingestion/source, evaluation/judge, and logs/traces.
- [X] T011 [US1] Implement `scripts/security_audit.py --boundaries` to validate the threat model and report missing boundary/control/test coverage without scanning network services.

**Checkpoint**: A reviewer can map each trust boundary to existing controls, tests, failure modes, and residual risk.

---

## Phase 4: User Story 2 - Exercise Adversarial Inputs (Priority: P1)

**Goal**: Exercise the specified attack classes with synthetic fixtures and confirm policy, permissions, and provider choice do not change.

**Independent Test**: Each attack fixture maps to an automated test or an explicit not-testable reason; no fixture makes a live external call.

### Tests for User Story 2

- [X] T012 [P] [US2] Add synthetic user/retrieved/MCP instruction fixtures in `data/evaluation/security-attack-fixtures.json` covering prompt override, retrieved injection, MCP resource/tool injection, and exfiltration attempts.
- [X] T013 [P] [US2] Add backend security tests in `apps/backend/tests/security/test_security_boundaries.py` for user prompt override, unauthorized source/filter access, fabricated citations, sensitive and consequential-decision requests, oversized request/result, cancellation, and agent/tool budgets.
- [X] T014 [P] [US2] Add MCP security tests in `services/mcp-policy-data/tests/test_security_boundaries.py` for invalid arguments, path/identifier traversal, unknown source/server identity, oversized resource, malformed result, timeout, cancellation, and repeated-call/resource-exhaustion bounds.
- [X] T015 [P] [US2] Add provider-boundary tests in `apps/backend/tests/security/test_provider_boundaries.py` for no implicit external fallback, explicit OpenAI consent, loopback-only MLX, unknown/unapproved provider identity, and ensuring local data is not sent before opt-in.

### Implementation for User Story 2

- [X] T016 [US2] Implement fixture coverage and result recording in `scripts/security_audit.py`; use only fake clients and the security-result schema in `specs/008-security-and-responsible-ai/contracts/security-test-result.schema.json`.
- [X] T017 [US2] Reuse and extend existing Feature 004/005 tests in `apps/backend/tests/unit/test_agent_runtime.py`, `apps/backend/tests/unit/test_mcp_client.py`, and `apps/backend/tests/unit/test_agent_state.py` only where an attack class lacks deterministic coverage for tool allow-lists, retry/time/token budgets, cancellation, malformed outputs, or injection isolation.

**Checkpoint**: All locally testable attacks have a fixture and an invariant assertion; unsupported production attacks are labeled not tested.

---

## Phase 5: User Story 3 - Verify Privacy and Human Oversight (Priority: P1)

**Goal**: Make allowed data, secret handling, retention, consent, and escalation limits reviewable.

**Independent Test**: Secret scans find no injected canaries in browser output, default logs, or test traces; documents state local retention, review, and appeal/escalation boundaries.

### Tests for User Story 3

- [X] T018 [P] [US3] Add source/log/trace redaction tests in `scripts/tests/test_security_audit.py` using fake API keys, bearer tokens, passwords, and personal identifiers.
- [X] T019 [P] [US3] Add frontend bundle scan tests in `apps/frontend/tests/security.test.ts` proving provider credentials and secret canaries are absent from built assets.
- [X] T020 [P] [US3] Add consent and permission boundary tests in `apps/backend/tests/security/test_security_boundaries.py` for provider-change approval and restricted-source rejection.

### Implementation for User Story 3

- [X] T021 [US3] Implement offline secret-canary scanning in `scripts/security_audit.py`; scan tracked source, docs, test outputs, and frontend build output while excluding approved fake-secret fixtures and generated indexes.
- [X] T022 [US3] Create `docs/security/privacy-retention.md` documenting allowed data, log/trace fields, retention/deletion, reviewer identity minimization, consent boundaries, and human escalation/appeal limits for the local target.
- [X] T023 [US3] Create `docs/security/security-residual-risks.md` mapping untested production controls, attack coverage results, explicit limitations, and the prohibition on claiming prompt injection is solved.

**Checkpoint**: Privacy practices, approval boundaries, test evidence, and residual risks are explicit and reproducible.

---

## Phase 6: Polish and Cross-Cutting Concerns

- [X] T024 [P] Add `specs/008-security-and-responsible-ai/traceability.md` mapping every SEC/PRIV/DOC requirement and acceptance scenario to tests, inspection, or a documented local-only limitation.
- [X] T025 Run `make security-verify`, `make format-check-python`, `make lint-python`, `make typecheck-python`, `make test-python`, frontend tests, and `python3 scripts/check_traceability.py`; record exact results in `docs/security/security-residual-risks.md`.

---

## Dependencies and Execution Order

- Setup (T001-T003) precedes the boundary and attack work.
- Foundational boundary models and offline loader (T004-T007) block all user stories.
- User Story 1 creates the boundary inventory; User Story 2 maps and tests attacks against it; User Story 3 audits privacy and oversight across the same boundaries.
- Polish follows the three stories; production deployment and authentication remain outside this local-only feature.

## Parallel Opportunities

- T004 and T006 can proceed in parallel after T001.
- T012-T015 are test fixtures across different boundaries/files and can proceed in parallel.
- T018-T020 are separate redaction, frontend, and consent test surfaces.

## Implementation Strategy

1. MVP: validate all boundaries and demonstrate existing local controls using synthetic fixtures.
2. Add uncovered adversarial tests and the offline secret scan.
3. Publish privacy, human-oversight, and residual-risk documents with full gate evidence.

No task should claim complete prevention; report only measured fixture coverage.