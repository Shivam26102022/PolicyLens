# Implementation Plan: Evaluation and Error Analysis

**Branch**: `007-evaluation` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-evaluation/spec.md`

## Summary

Build a leakage-resistant evaluation set and an offline-by-default suite runner that reuses the existing retrieval and provider evaluators. Register each run with case-set, corpus/index, prompt/model, dependency, configuration, and code identity fingerprints (Git revision when available, otherwise a source-tree hash); preserve negative results and link each reviewed error to a regression test. The release gate requires at least 30 human-approved cases. Candidate cases may be prepared in code, but must not be marked approved without reviewer evidence. An explicit, bounded AI judge can score groundedness/relevance without receiving oracle labels; its scores are not human-validated or release approval.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Existing Pydantic, jsonschema, pytest, retrieval and model-provider packages; no new runtime dependency is planned.

**Storage**: Versioned JSON case sets and append-only JSON run/error manifests under `data/`; Markdown rubric and reports under `docs/`.

**Testing**: pytest unit and contract tests, deterministic fake providers, existing retrieval metric tests, and explicit live-provider opt-in only.

**Target Platform**: Existing Linux/macOS Python workspace; MLX measurements require Apple silicon. Offline retrieval and schema checks run on supported CI hosts.

**Project Type**: Existing Python backend plus repository evaluation CLI and data artifacts; no new service.

**Performance Goals**: No evaluation-run latency SLO. Record per-case p50/p95 latency where samples support it; runner must process the frozen set without unbounded retries or memory growth.

**Constraints**: At least 30 approved cases for a release evaluation; dev/test labels stay outside runtime requests; candidate cases are not approved by automation; default runs make no live provider calls; AI judging requires explicit generation/provider opt-in, is bounded and structured, and stores no raw answer/rationale; report small-sample and judge limitations; no restricted data or secrets in artifacts.

**Scale/Scope**: 30-60 cases initially, current public/synthetic corpus, existing retrieval, non-agent baseline, bounded agent, OpenAI/MLX routes where available, and one controlled chunking/filter comparison.

## Constitution Check

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Expected anchors and citations are checked against current-run evidence; labels are not runtime instructions. | PASS |
| II. Scientific Evaluation Before Complexity | Frozen splits, simple baselines, stratified reporting, human review, uncertainty, and negative results are explicit. | PASS; 30 approved cases are a release gate. |
| III. Bounded Agency and Deterministic Computation | Existing bounded runtime is reused; evaluation runners have explicit time, case, and provider limits. | PASS |
| IV. Secure MCP Trust Boundaries | Failure/injection cases use existing host/server validation; evaluation fixtures cannot grant tools or permissions. | PASS |
| V. Provider Portability With Measured Parity | OpenAI and MLX comparisons are opt-in, same-case, and report unsupported/unmeasured metrics honestly. | PASS; on-device MLX remains platform-gated. |
| VI. Reproducibility Is a Product Feature | Runs fingerprint case set, corpus/index, config, prompt/model, dependency lock, Git revision when available or source tree otherwise, and seed. | PASS |
| VII. Privacy, Responsible AI, and Human Oversight | Public/synthetic data only; case approval remains human-owned; AI output scores disclose model identity, calibration limits, and are not release approval. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | CLI and schemas only; no additional deployable service. | PASS |
| IX. Testable Specifications and Traceability | Every case/metric/error field maps to a contract or test. | PASS |
| X. Honest Reporting | Candidate/reviewed status, skipped/failed runs, sample limits, and unrun providers remain visible. | PASS |

## Project Structure

### Documentation

```text
specs/007-evaluation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Evaluation Inputs and Outputs

```text
data/evaluation/feature007-cases.json
data/manifests/evaluation-run-manifest.json
data/manifests/evaluation-errors.json
docs/evaluation/evaluation-review-rubric.md
docs/evaluation/evaluation-report.md
scripts/evaluate_suite.py
scripts/analyze_evaluation_errors.py
scripts/tests/test_evaluation_suite.py
```

Existing `scripts/evaluate_retrieval.py`, `scripts/evaluate_providers.py`, `apps/backend/src/policylens/retrieval/evaluation.py`, and the frozen Feature 003/004 case sets remain the reusable baseline implementations.

**Structure Decision**: Keep evaluation in the current scripts and data-manifest structure. Add one suite orchestrator, strict JSON contracts, and an error-analysis utility; do not create a new service or duplicate the existing metric implementations.

## Implementation Sequence

1. Define schemas and leakage checks; validate candidate sets without making provider calls.
2. Add run registration and configuration fingerprints; reuse retrieval and provider metrics.
3. Add the 30+ case set as candidate material, then require human review before approval/release evaluation.
4. Add human-review rubric, stratified report, and error records linked to tests.
5. Add the release gate, reproduce registered baselines, and document provider/platform limits.

## Complexity Tracking

No constitution exception or new deployable service is required.
