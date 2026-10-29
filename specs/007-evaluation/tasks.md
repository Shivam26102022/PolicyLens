---
description: "Implementation tasks for Feature 007 evaluation and error analysis"
---

# Tasks: Evaluation and Error Analysis

**Input**: Design documents from `/specs/007-evaluation/`

**Prerequisites**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Required by the spec, project constitution, and evaluation integrity gates. All automated cases must use mocks/fakes unless live-provider flags are explicitly passed.

**Organization**: Establish contracts and leakage-safe loading first, then independently validate the frozen set, run baseline comparisons, and produce human-reviewed error analysis.

## Phase 1: Setup

**Purpose**: Establish the versioned evaluation contract and reproducible output locations.

- [x] T001 Create strict case-set, evaluation-run, error-record, and human-review JSON Schemas in `specs/007-evaluation/contracts/` from the field constraints in `data-model.md`.
- [x] T002 Add the `evaluation-verify` Makefile target for offline case/schema validation without provider calls.
- [x] T003 Create the empty versioned run registry at `data/manifests/evaluation-run-manifest.json` and document its append-only update semantics.

---

## Phase 2: Foundational

**Purpose**: Make case loading, label separation, release gating, and run identity reusable by all stories.

- [x] T004 [P] Implement strict evaluation case/set models and a loader in `scripts/evaluation_case_set.py`; reject duplicate case IDs and malformed anchors, splits, categories, and review states.
- [x] T005 Implement leakage-safe case-to-runtime request conversion in `scripts/evaluation_case_set.py`; expose only the question and ordinary retrieval filters, never expected behavior, references, split, or review labels.
- [x] T006 Implement the release gate in `scripts/evaluation_case_set.py`; require at least 30 `approved` cases across dev/test splits and report candidate/approved counts without changing review state.
- [x] T007 Implement an atomic append-only experiment manifest writer in `scripts/evaluation_registry.py`; record case, corpus/index, configuration, prompt/model, code, lock, seed, and artifact fingerprints, with a relevant source-tree fingerprint when Git revision metadata is unavailable.
- [x] T008 [P] Add contract and loader tests in `scripts/tests/test_evaluation_case_set.py` for unique IDs, split separation, label exclusion, candidate versus approved state, and the 30-case release gate.
- [x] T009 Add run-manifest tests in `scripts/tests/test_evaluation_registry.py` for deterministic fingerprints, append preservation, invalid prior manifests, and atomic writes.

**Checkpoint**: Case data validates independently; no evaluation labels can enter runtime requests; no live provider is constructed by validation.

---

## Phase 3: User Story 1 - Run a Frozen Evaluation (Priority: P1)

**Goal**: Validate and run a versioned, leakage-resistant evaluation set with explicit review status.

**Independent Test**: Validate a fake 30-case set, confirm labels are excluded from requests, and confirm a set with fewer than 30 approved cases fails release mode.

### Tests for User Story 1

- [x] T010 [P] [US1] Add candidate set coverage tests in `scripts/tests/test_evaluation_case_set.py` for all required categories, both splits, synthetic lineage, and exact/semantic duplicate findings.
- [x] T011 [P] [US1] Add runner reproducibility tests in `scripts/tests/test_evaluation_suite.py` for stable case ordering, case-set hash, fixed configuration/seed, and no provider request in default mode.

### Implementation for User Story 1

- [x] T012 [US1] Create `data/evaluation/feature007-cases.json` with at least 30 candidate cases spanning the Feature 007 categories; keep AI-assisted cases as `candidate` and never infer reviewer approval.
- [x] T013 [US1] Add review-state, split, exact-duplicate, and possible semantic-duplicate checks to `scripts/evaluation_case_set.py`; require dev/test separation and preserve source lineage for public or synthetic cases.
- [x] T014 [US1] Implement offline `--validate-only` and `--release` modes in `scripts/evaluation_case_set.py` to report set size, review counts, anchor/permission failures, and release-gate status without generation calls.

**Checkpoint**: The case set and release gate are independently testable; no candidate case is described as human-approved.

---

## Phase 4: User Story 2 - Compare Baselines (Priority: P1)

**Goal**: Compare retrieval, non-agent, agent, and provider alternatives under registered, controlled configurations.

**Independent Test**: Run fake provider observations on the same case IDs/configuration, validate aggregate and stratified metrics, and confirm default execution is offline.

### Tests for User Story 2

- [x] T015 [P] [US2] Add metric tests in `scripts/tests/test_evaluation_metrics.py` for Recall@k, MRR, nDCG when graded labels exist, abstention/conflict, citation validity/completeness, schema/tool validity, and empty-result rate.
- [x] T016 [P] [US2] Add controlled comparison tests in `scripts/tests/test_evaluation_suite.py` for keyword/dense/hybrid, agent/non-agent, OpenAI/MLX, and one chunking/filter alternative using the same split and registered configuration.

### Implementation for User Story 2

- [x] T017 [US2] Extend `scripts/evaluate_suite.py` to reuse `evaluate_retrieval()` and existing provider/baseline adapters rather than duplicate their metric logic; preserve identical case IDs and record each retrieval index version.
- [x] T018 [US2] Implement deterministic aggregate and per-category metric calculation in `scripts/evaluation_metrics.py`; compute bootstrap intervals only when the sample supports them and disclose sample size and method.
- [x] T019 [US2] Add explicit `--allow-openai-live` and `--run-mlx` gates in `scripts/evaluate_suite.py`; default mode must make no provider calls, and MLX must pass loopback/model readiness checks before generation.
- [x] T020 [US2] Record prompts/models, route, dependency lock, corpus/index, configuration, seed, latency, token use, available cost/resource measures, and negative outcomes in `scripts/evaluation_registry.py`.

**Checkpoint**: Each comparison is reproducible from a manifest; unmeasured quality, cost, memory, and unavailable provider paths remain explicit.

---

## Phase 5: User Story 3 - Review Errors (Priority: P1)

**Goal**: Review representative results and link material failures to a root-cause hypothesis and regression test.

**Independent Test**: Validate a rubric review and an error record, then produce a report grouped by category, failure layer, severity, and frequency without exposing secrets or restricted content.

### Tests for User Story 3

- [x] T021 [P] [US3] Add human-review record, append-only manifest, and rubric tests in `scripts/tests/test_evaluation_review.py` for anchored 1-5 ratings, pseudonymous reviewers, reviewer agreement, and required coverage across categories.
- [x] T022 [P] [US3] Add error-record and report tests in `scripts/tests/test_evaluation_errors.py` for valid failure layers/severity, trace linkage, regression-test references, redaction, and aggregation.

### Implementation for User Story 3

- [x] T023 [US3] Create `docs/evaluation/evaluation-review-rubric.md` defining anchored groundedness, relevance, citation correctness/completeness, safety, and expected-behavior review with two reviewers where feasible; record scores and disagreements without exposing restricted content.
- [x] T024 [US3] Implement validated error-record loading and append-only storage in `scripts/evaluation_errors.py`; require observed/expected outcome, failure layer, severity/frequency, root-cause hypothesis, intervention, predicted metric impact, and regression test.
- [x] T025 [US3] Implement `scripts/analyze_evaluation_errors.py` to produce redacted category/failure-layer summaries and retain negative outcomes without overwriting prior runs.
- [x] T026 [US3] Generate `docs/evaluation/evaluation-report.md` from registered manifests with baseline tables, stratified metrics, confidence/judge limits, review agreement, error analysis, and explicit unmeasured fields.

**Checkpoint**: Human/judge limitations, disagreements, negative results, and regression links are visible; no benchmark claim exceeds the evidence.

---

## Phase 6: Polish and Cross-Cutting Concerns

- [x] T027 [P] Update `specs/007-evaluation/quickstart.md`, root `Makefile`, and `specs/007-evaluation/traceability.md` with exact commands and requirement-to-test mappings.
- [x] T028 Run `make format-check-python`, `make lint-python`, `make typecheck-python`, `make test-python`, and `make evaluation-verify`; record exact results and the 30-approved-case/live-provider limitations in `docs/evaluation/evaluation-report.md`.
- [x] T029 [US2] Correct retrieval recall to count grouped expected evidence anchors once, provide bounded validated deterministic calculation evidence to the AI judge, and expose score counts/distributions plus anchor coverage in the read-only evaluation summary and UI; update the evaluation data model, Feature 009 summary contract, traceability, and quickstarts. Verified: 42 focused backend tests and 6 evaluation UI tests pass; Python/frontend formatting, lint, type checks, frontend build, traceability, and offline case validation pass. No provider call was made.

---

## Dependencies and Execution Order

- Setup (T001-T003) precedes all implementation.
- Foundational loading and manifest work (T004-T009) blocks the user stories.
- User Story 1 produces a validated, reviewed case set before comparison or error analysis.
- User Story 2 depends on the case loader and registry, and reuses Feature 003-006 runners.
- User Story 3 consumes registered results from User Stories 1 and 2.
- Polish follows all stories; the release gate stays blocked until 30 cases are human-approved.

## Parallel Opportunities

- T004 and T007 can proceed in parallel after schemas land; their tests are file-isolated.
- T015/T016 can be authored independently using fake observations while T017/T018 implement the runners.
- T021/T022 are independent test files; T023 rubric work can proceed alongside error-record implementation.

## Implementation Strategy

1. MVP: schemas, leakage-safe loader, release gate, and fake tests.
2. Next: manifest registry and deterministic retrieval/provider metrics with explicit live flags.
3. Final: human review, error taxonomy/report, and approved-case release gate.

The initial case file may contain candidates, but no Feature 007 benchmark or parity claim is valid until the approved-case gate passes.

## Phase 7: Human-Owned Release Gate

**Purpose**: Complete the review work that cannot be truthfully automated.

- [X] T029 [US1] Have human reviewers inspect the source anchor, expected behavior, reference claims, split, and safety label for each case in `data/evaluation/feature007-cases.json`; record pseudonymous reviewer IDs and UTC dates using `docs/evaluation/evaluation-review-rubric.md`, resolve duplicate warnings, and mark cases approved only after sign-off. The release gate requires at least 30 approved cases covering both splits and all required categories.

---

## Phase 8: Report Integrity and Current Evidence

**Purpose**: Ensure generated reports accurately scope historical evidence and distinguish offline rendering from a new evaluation.

- [X] T030 [US3] Add report regressions in `scripts/tests/test_evaluation_suite.py` for per-run review/error filtering, separate same-case-set historical review context, mixed retrieval/generation rows, and offline registered-run rendering. Verified: all report-focused tests pass.
- [X] T031 [US3] Update `scripts/evaluate_suite.py` to recalculate stratified metrics from stored run results, correct the stale generation-skipped note when results exist, and render a selected registered run without retrieval or provider execution. Verified: run `bde70dd8-ed40-4aeb-b1e5-e3ae5f53c89d` rendered offline with 297 metric rows.
- [X] T032 [US2] Render calculation-only claims as readable operation/result rows in `apps/backend/src/policylens/agent_runtime/runtime.py` instead of exposing serialized JSON. Verified by `apps/backend/tests/unit/test_agent_runtime.py` and the full backend suite.
- [X] T033 [US3] Correct the readiness-only Feature 004 evaluation stub to report `FEATURE_004_COMPARISON_NOT_IMPLEMENTED`, not a missing Feature 005 MCP adapter. Verified by `scripts/tests/test_agent_evaluation.py`.
- [X] T034 Refresh `docs/evaluation/evaluation-report.md`, this quickstart, and `traceability.md` with the offline report, per-run reviews/errors, fresh verification results, and remaining evaluation limitations. Verified: `make check`, `make security-verify`, `make retrieval-verify`, `make evaluation-verify`, and 11 mocked Playwright tests passed; no new provider evaluation was run.

---

## Phase 9: AI-Only Answer Quality

**Purpose**: Fill groundedness and answer relevance with bounded structured AI judging while retaining deterministic evaluation and explicit limitations.

- [X] T035 Add the opt-in structured judge and per-agent score/provenance/usage aggregation in `scripts/evaluation_judge.py`, `scripts/evaluate_suite.py`, and `scripts/evaluation_metrics.py`; exclude expected labels and reference claims from judge input and never persist raw answers or rationale. Cover bounded input, output validation, failure, and aggregation with fakes. Verified: judge loop reuse, model-compatible request settings, bounded inputs, invalid output/failure handling, metrics aggregation, and no-answer-persistence tests pass.
- [X] T036 Expose safe judge provenance/counts in the Feature 009 read-only evaluation summary, run an authorized AI-judged evaluation of the approved set, and update the Feature 007 report/quickstart, Feature 009 quickstart/traceability, and verification evidence. Do not claim human validation or provider cost without provider-reported cost data. Verified with run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e`: 33/33 attempted judge outputs scored, 3 skipped, 0 judge failures; run is partial because some agent/baseline outputs failed safely. Provider cost remains unmeasured.