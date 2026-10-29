# Implementation Plan: Security and Responsible AI

**Branch**: `008-security-and-responsible-ai` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-security-and-responsible-ai/spec.md`

## Summary

Produce a nine-boundary threat model and a versioned attack-coverage record that reuses existing Feature 003-007 controls/tests. Add only the missing adversarial fixtures, permission/redaction scans, privacy/retention policy, and residual-risk report. The deployment target is local assessment only; do not introduce public endpoints, production authentication, a new service, or a claim that prompt injection is solved.

## Technical Context

**Language/Version**: Python 3.12; existing TypeScript/React frontend.

**Primary Dependencies**: Existing FastAPI, Pydantic, pytest, jsonschema, logging, and provider/MCP packages. No new runtime dependency planned.

**Storage**: Markdown threat/privacy documentation plus versioned JSON security fixture and result manifests; existing logs remain structured JSON.

**Testing**: Existing pytest backend/MCP/script suites, security-specific deterministic fixtures, source/bundle/log secret scans, and documented manual boundary review.

**Target Platform**: Local Linux/macOS assessment services. No production hosting/auth target is defined.

**Project Type**: Cross-cutting documentation, test, and offline audit-script changes across existing web/API/MCP services.

**Performance Goals**: Security scans run offline within the existing CI budget; no security test introduces live provider calls by default.

**Constraints**: Maintain nine trust boundaries; only public/synthetic/approved anonymized data; separate instructions from untrusted data; preserve existing tool allow-lists/read-only permissions; keep secrets out of bundles/traces/reports; report residual risk and unsupported checks.

**Scale/Scope**: Current PolicyLens local assessment stack, seven currently implemented source records, providers/features 001-007, and the 15 attack classes listed in the master spec.

## Constitution Check

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Adversarial inputs cannot change evidence/citation rules; unsupported claims fail or abstain. | PASS |
| II. Scientific Evaluation Before Complexity | Security behavior is tested through deterministic fixtures and negative results are retained. | PASS |
| III. Bounded Agency and Deterministic Computation | Tool allow-list, timeouts, turn/token budgets, and deterministic host validation remain enforced. | PASS |
| IV. Secure MCP Trust Boundaries | Reuse server identity, permission, argument/result validation, timeout, redaction, and read-only controls; test gaps. | PASS |
| V. Provider Portability With Measured Parity | No implicit external fallback; local requests remain local unless explicitly opted in. | PASS |
| VI. Reproducibility Is a Product Feature | Record test fixture IDs, dependency lock, code revision when available, and test results. | PASS |
| VII. Privacy, Responsible AI, and Human Oversight | Public/synthetic data only; document retention, review, consent boundary, and escalation. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | Documentation/tests/audit script only; no new deployable service. | PASS |
| IX. Testable Specifications and Traceability | Each attack and acceptance criterion maps to fixture/test or explicit unavailable reason. | PASS |
| X. Honest Reporting | Do not claim prompt injection solved; disclose untested production boundaries and residual risk. | PASS |

## Project Structure

```text
specs/008-security-and-responsible-ai/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
docs/security/threat-model.md
docs/security/privacy-retention.md
docs/security/security-residual-risks.md
scripts/security_audit.py
scripts/tests/test_security_audit.py
apps/backend/tests/security/
services/mcp-policy-data/tests/
```

**Structure Decision**: Keep the threat model and residual-risk artifacts in `docs/`, the versioned attack/result contracts in the Feature 008 spec, and tests at existing service boundaries. Reuse current feature controls; do not add a security service or production auth layer for the local-only target.

## Implementation Sequence

1. Inventory the nine trust boundaries and current controls/tests.
2. Add deterministic adversarial/failure fixtures for coverage gaps and assert no policy, permission, or provider change.
3. Add secret-scan, permission-boundary, and log/trace checks using only synthetic test values.
4. Document local retention/review/appeal practices, test evidence, untested deployment risks, and residual risk.
5. Run the full Python/frontend checks and produce the coverage report; do not claim complete protection.

## Complexity Tracking

No new service, framework, or production authentication layer is required for the clarified local-only scope.
