# Feature 008 Traceability

Traceability reflects the local-only scope. A `not tested` entry is a documented limitation, not a passing security result.

## Functional Requirements

| Requirement | Evidence | Status / limitation |
|---|---|---|
| SEC-008-01: nine trust boundaries | `docs/security/threat-model.md`; `scripts/tests/test_security_audit.py::test_boundary_inventory_contains_all_required_fields`; `scripts.security_audit --boundaries` | Tested: all nine IDs and mandatory fields are validated |
| SEC-008-02: adversarial and failure classes | `data/evaluation/security-attack-fixtures.json`; backend/MCP security tests; existing agent, MCP, retrieval, and provider tests | Fifteen fixtures map to local tests; consequential eligibility is not testable locally |
| SEC-008-03: allow-lists, read-only scope, identity, bounds, timeout, cancellation | `apps/backend/tests/security/`; `apps/backend/tests/unit/test_agent_runtime.py`; `apps/backend/tests/unit/test_agent_tools.py`; `apps/backend/tests/unit/test_mcp_client.py`; `services/mcp-policy-data/tests/test_passages.py` | Local configured controls tested; production identity and deployment limits are not tested |
| SEC-008-04: untrusted content cannot alter host policy | `apps/backend/tests/security/test_security_boundaries.py`; `apps/backend/tests/unit/test_mcp_client.py::test_passage_read_keeps_instruction_text_untrusted_and_redacts_logs`; `docs/security/threat-model.md` | Fixture-specific checks only; no general prompt-injection guarantee |
| PRIV-008-01: allowed data, retention, permissions, and human review | `docs/security/privacy-retention.md`; `docs/security/security-residual-risks.md`; `data/evaluation/security-attack-fixtures.json` | Policy documented; organizational retention and appeal execution are not tested |
| PRIV-008-02: credentials excluded from bundles, source, health, and logs | `scripts/security_audit.py`; `scripts/tests/test_security_audit.py`; `apps/frontend/tests/security.test.ts`; `apps/backend/tests/security/test_security_boundaries.py`; existing backend and MCP logging tests | Deterministic text/bundle scans and synthetic sensitive-query trace test; novel encodings remain residual risk |
| DOC-008-01: report measured coverage and residual risk | `docs/security/security-residual-risks.md`; `scripts/security_audit.py`; `data/manifests/security-test-manifest.json` | Report records tested mappings and explicitly unavailable coverage; no perfect-prevention claim |

## Acceptance Scenarios

| Scenario | Test or inspection | Result boundary |
|---|---|---|
| AC-008-01: all boundaries have complete fields | Boundary inventory parser test and `docs/security/threat-model.md` | Nine local boundaries |
| AC-008-02: missing tests are residual risk, not pass | Fixture status validation and `docs/security/security-residual-risks.md` | One consequential-decision fixture explicitly unavailable |
| AC-008-03: user prompt override does not change policy | Backend untrusted-input and lifecycle-redaction tests | Tests selected synthetic paths; hidden prompt non-disclosure is not generalized |
| AC-008-04: retrieved/MCP injection cannot authorize actions | Existing MCP untrusted passage test, backend tool allow-list tests, synthetic fixture catalog | Fixture-specific assertions only |
| AC-008-05: malformed, oversized, unknown, timeout, and traversal inputs fail safely | Backend/MCP security tests and existing `test_mcp_client.py` / `test_passages.py` tests | Local adapters only; no production deployment assessment |
| AC-008-06: fake secrets are absent from outputs and bundles | Redaction, scanner, sensitive-query trace, logging, and frontend bundle tests | Synthetic canaries only; scanner limitations remain documented |
| AC-008-07: external provider requires explicit opt-in | `scripts/tests/test_evaluation_suite.py::test_generation_executor_is_not_called_without_provider_opt_in`; backend provider settings/runtime tests | No provider request made by security verification |
| AC-008-08: restricted sources and consequential decisions are handled safely | Permission-scope rejection tests; `docs/security/privacy-retention.md` | Consequential-decision enforcement and appeal execution are not testable in this scope |

## Success Criteria

| Criterion | Evidence |
|---|---|
| SC-008-01: deterministic fixture or unavailable reason | Fixture catalog, strict loader, and test-reference checks |
| SC-008-02: tested unauthorized evidence/secret/tool action does not cross boundary | Existing permission, redaction, allow-list, timeout, and no-fallback tests plus Feature 008 additions |
| SC-008-03: residual risk and human oversight remain visible | `docs/security/security-residual-risks.md` and `docs/security/privacy-retention.md` |

## Verification Commands

- `make security-verify`
- `make format-check-python`
- `make lint-python`
- `make typecheck-python`
- `make test-python`
- `npm --prefix apps/frontend test`
- `python3 scripts/check_traceability.py`