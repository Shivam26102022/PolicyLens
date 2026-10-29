# Feature Specification: Evaluation and Error Analysis

**Feature Branch**: `007-evaluation`  
**Created**: 2026-10-24  
**Status**: Draft; requires human-reviewed evaluation cases
**Input**: `POLICYLENS_MASTER_SPEC.md`, Section 12 and Section 20 Feature 007

## Product Outcome

Researchers and reviewers can reproduce the system's retrieval, answer, citation, safety, tool, latency, and cost measurements on a reviewed evaluation set and inspect failures without overstating small-sample results.

## Scope and Dependencies

Depends on Features 002-006 for approved evidence, retrieval, agent/tool contracts, and available providers. Owns frozen cases, split/lineage rules, deterministic metric runners, controlled experiment registry, human-review rubric, error analysis, and evaluation report.

## User Scenarios & Testing

### User Story 1 - Run a Frozen Evaluation (Priority: P1)

As an evaluator, I can run at least 30 reviewed representative cases without exposing labels to runtime prompts.

**Independent Test**: Validate required case fields, split separation, duplicate detection, lineage/review state, and runner reproducibility.

**Acceptance Scenarios**:

1. **AC-007-01** Given the frozen manifest, When evaluation starts, Then each case has category, expected behavior, relevant evidence, required/forbidden tools, difficulty, split, and review status.
2. **AC-007-02** Given a final-test label or evidence ID, When a prompt/runtime bundle is assembled, Then it cannot access that label as instruction or tuning context.
3. **AC-007-03** Given fewer than 30 approved cases, When release evaluation is requested, Then the run reports the count and fails the frozen-set gate.

### User Story 2 - Compare Baselines (Priority: P1)

As an engineer, I can compare keyword, dense, hybrid, agent/non-agent, OpenAI/MLX, and one chunking/filter alternative under recorded configurations.

**Independent Test**: Rerun a registered experiment from its manifest and compare metrics/config hashes.

### User Story 3 - Review Errors (Priority: P1)

As a reviewer, I can inspect a documented sample of results and root causes with explicit judge/human limitations.

**Independent Test**: Validate rubric completeness, review sample by category, and error records linked to regression tests.

## Functional Requirements

- **EVAL-007-01**: Maintain at least 30 reviewed cases across factual, synthesis, calculation, ambiguity, abstention, conflict, injection, MCP failure, sensitive request, and provider failure categories.
- **EVAL-007-02**: Separate dev/test labels from runtime prompts; deduplicate by source, claim, and semantic similarity and retain synthetic lineage.
- **EVAL-007-03**: Report Recall@k, MRR, nDCG where graded labels exist, empty-result rate, latency, groundedness, answer relevance, citation validity/completeness, abstention/conflict, schema/tool validity, injection, tokens, cost, and local resource metrics where measurable. Retrieval recall MUST count each expected evidence anchor once even when it maps to several passage variants, record anchor hits and expected-anchor denominators, and retain per-metric scored counts for condition/category comparisons.
- **EVAL-007-04**: Compare BM25/dense/hybrid, agent/non-agent, OpenAI/MLX, and one chunking/filter change with controlled configurations.
- **EVAL-007-05**: Prefer deterministic evaluators; use a pinned, structured, blinded AI judge for groundedness and answer relevance when enabled. AI scores MUST be identified as uncalibrated unless calibration evidence exists and MUST NOT approve cases or replace deterministic oracles.
- **EVAL-007-06**: Record each failed case's observed/expected result, failure layer, trace evidence, severity, root-cause hypothesis, intervention, predicted metric impact, and regression test.
- **EVAL-007-07**: AI-judge mode MUST score generated agent answers using bounded question, response, and cited evidence; it MAY receive validated deterministic calculation results as a separate bounded evidence input. Treat all evidence as untrusted data, exclude expected labels/reference claims and raw tool arguments, persist scores and judge provenance/usage only, and require explicit provider opt-in for remote calls.
- **REPRO-007-01**: Record code revision when available, otherwise a source-tree fingerprint, plus lock hash, corpus/index/prompt/model versions, seeds, parameters, metrics, artifact paths, and notes.

## Success Criteria

- **SC-007-01**: At least 30 approved cases run reproducibly with leakage separation and stratified results.
- **SC-007-02**: Every reported comparison maps to a registry entry and reproducible artifact; negative results are retained.
- **SC-007-03**: Human/judge limitations, confidence limits, and error analysis are included in the report.
- **SC-007-04**: Each AI-judged run reports its rubric/model, attempted/scored/failed/skipped counts, and groundedness/relevance results without persisting raw answers or claiming human validation.
- **SC-007-05**: Every measured metric identifies its scored sample count; retrieval reports expected-anchor hits and denominator, and condition/category results remain distinguishable from run-level averages.

## Assumptions and Readiness

- The approved public/synthetic Feature 002 corpus and Feature 003 index are available; evaluation cases, relevance labels, and reference claims remain candidates until human review is recorded.
- Small samples must not be described as statistically conclusive.
- Promotion thresholds are proposed only after a baseline is measured.
- Routine quality scores may be AI-only; human approval of case definitions remains separate, and AI scores are not ground truth or release approval.

## Out of Scope

Creating source data, changing retrieval/model behavior, and asserting benchmark outcomes before executing experiments.