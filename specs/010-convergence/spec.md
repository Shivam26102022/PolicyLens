# Feature Specification: Convergence and Submission Package

**Feature Branch**: `010-convergence`  
**Created**: 2026-10-24  
**Status**: Draft; depends on prior feature evidence  
**Input**: `POLICYLENS_MASTER_SPEC.md`, Sections 18-20 and 25

## Product Outcome

An assessor can reproduce the project setup, understand architecture and trust boundaries, inspect real evaluation evidence and limitations, and execute a deterministic 20-minute demonstration covering all mandatory scenarios.

## Scope and Dependencies

Depends on the implemented and verified state of Features 001-009. Owns a final requirement audit, traceability generation, architecture diagrams, data sheet, evaluation report, model/system card, threat model, ADR index, innovation assessment, limitations, demo fixtures/runbook, and clean-checkout verification.

## User Scenarios & Testing

### User Story 1 - Audit Completeness (Priority: P1)

As a reviewer, I can map every global requirement and demo scenario to implementation or explicit blocker evidence.

**Independent Test**: Run the traceability checker and deliberate orphan/missing mapping fixtures; verify all completion claims have executable evidence.

**Acceptance Scenarios**:

1. **AC-010-01** Given all feature artifacts, When convergence runs, Then it identifies missing, contradictory, or unsupported completion claims and assigns an owner/next action.
2. **AC-010-02** Given an unrun test or experiment, When reports are generated, Then the result is labeled unrun rather than passing or measured.

### User Story 2 - Reproduce the Demonstration (Priority: P1)

As an assessor, I can run each of the ten demonstration scenarios with expected states, evidence, tools, and forbidden outcomes.

**Independent Test**: Follow the demo runbook from a clean setup using fixed fixtures and verify scenario checklist outputs.

### User Story 3 - Inspect Submission Evidence (Priority: P1)

As a technical reviewer, I can inspect the data, evaluation, model, security, architecture, innovation, and limitation materials.

**Independent Test**: Validate all required deliverables and links; compare reported versions/results to manifests and CI/test artifacts.

## Functional Requirements

- **CONV-010-01**: Reconcile implementation, plans, tests, diagrams, evaluation reports, run manifests, and limitations before declaring convergence.
- **CONV-010-02**: Map every mandatory assessment requirement and all ten demos to code/test/evaluation/inspection evidence or an explicit blocker.
- **DOC-010-01**: Produce README, architecture diagrams, data sheet, evaluation report, concise model/system card, threat model, ADRs, traceability, innovation assessment, demo runbook, and limitations.
- **DEMO-010-01**: The 20-minute runbook MUST include all ten scenarios and a deterministic offline backup path.
- **HONEST-010-01**: Do not fabricate benchmarks, citations, test results, source data, human review, provider parity, or task completion.
- **REPRO-010-01**: A clean-checkout setup and demo must use pinned dependencies, model/prompt/index/corpus versions, and manifest-backed evidence.

## Success Criteria

- **SC-010-01**: Every mandatory requirement has an implemented/evidenced state or a named blocker; no planned-only work is labeled complete.
- **SC-010-02**: All ten demos can be replayed from documented fixtures with reproducible expected outcomes.
- **SC-010-03**: Deliverables agree with the implementation and include explicit metric, judge, data, and platform limitations.

## Assumptions and Open Questions

- Q-DATA-01 and Q-MLX-01 must be resolved or prominently retained as blockers; neither may be silently guessed.
- Human-review availability, actual evaluation outputs, and challenge submission format are recorded when known.
- Convergence is evidence-driven and may report incomplete rather than manufacture a passing state.

## Out of Scope

Adding new product features solely to improve presentation or making unsupported quality claims.