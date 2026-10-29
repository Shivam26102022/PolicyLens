# Feature 008 Security Results and Residual Risks

## Scope and Reporting Rule

This report describes the local assessment target only. A passing fixture proves only the tested code path and synthetic input. It does not establish general prompt-injection prevention, production security, or suitability for consequential decisions.

## Current Offline Audit

Recorded 2026-10-27 with `uv run --locked --package policylens python -m scripts.security_audit --verify --scan-secrets`:

| Measure | Result |
|---|---:|
| Trust boundaries parsed | 9 / 9 |
| Synthetic attack fixtures loaded | 16 |
| Fixtures mapped to local tests | 15 |
| Explicitly unavailable locally | 1 |
| Secret-scan findings | 0 |
| Live provider/network requests | 0 |

The one unavailable fixture concerns consequential eligibility determinations: this local runtime has no explicit decision-policy boundary to test, so the case is documented for human review rather than marked passed. The inventory audit checks mapping and data shape; it does not itself execute each attack fixture. `make security-verify` executes the linked deterministic test suites before reporting the audit.

## Verification Record

Recorded 2026-10-27:

| Command | Result |
|---|---|
| `make security-verify` | Passed: 118 backend/script tests, 13 MCP tests, frontend production build, 5 frontend tests, audit complete; no live requests |
| `make test-python` | Passed: 187 backend + 39 MCP + 114 script tests = 340 |
| `make format-check-python` | Passed |
| `make lint-python` | Passed |
| `make typecheck-python` | Passed |
| `npm --prefix apps/frontend run format:check` | Passed |
| `npm --prefix apps/frontend run lint` | Passed |
| `npm --prefix apps/frontend run typecheck` | Passed |
| `npm --prefix apps/frontend test` | Passed: 5 tests |
| `python3 scripts/check_traceability.py` | Passed: 67 global requirements, 14 feature requirements, 11 acceptance criteria, 5 success criteria, 10 demo scenarios |

The audit also passed independently in `--boundaries` mode and with `--verify --scan-secrets`. No per-fixture result rows were fabricated; the append-only manifest remains available for explicit, schema-validated result records.

## Residual Risks

| Boundary or concern | Untested condition | Existing mitigation/evidence | Next trigger |
|---|---|---|---|
| Browser/API and all services | Public hosting, production authentication, multi-tenant authorization, TLS, and reverse-proxy policy | Local loopback target; backend permission checks; no production deployment added | Before any public or multi-user deployment |
| API/OpenAI | Provider-side data retention, account controls, and external service security | Explicit provider selection/consent tests; no call in the audit target | Before enabling external-provider use with non-public content |
| API/MLX | Host compromise, model artifact provenance, and remote machine isolation | Loopback-only settings and no-fallback tests | Before moving MLX to another host or network |
| User/retrieved/MCP instructions | Generalization to novel prompt-injection techniques | Synthetic injection tests assert selected invariants and untrusted-content handling | On each model, prompt, provider, or tool change |
| Consequential requests | Eligibility, enforcement, benefits, legal, safety, or funding decision policy and appeal process | Product limitation and human escalation documentation; one fixture is explicitly not testable | Before any consequential-use workflow |
| Ingestion/source | Publisher authenticity, rights changes, and source-level poisoning | Permission manifest, hashes, and local parser validation | On source or license changes |
| Logs/traces | Host filesystem access, backups, and deletion execution | Allow-listed logging, redaction tests, local retention policy | Before centralized or shared log storage |
| Secret scanner | Encoded, split, encrypted, binary, or novel secret formats | Offline text scan with explicit exclusions for known fake test values | When adding secret formats or changing build artifacts |

## Explicit Limitations

- No production authentication, public exposure, tenant isolation, deployment hardening, or capacity certification is implemented.
- The secret scan is a deterministic source/build check, not a general-purpose secret-management system. Approved fake-secret tests and the MLX no-auth placeholder are explicitly excluded or normalized.
- Fixture coverage does not prove universal resistance to prompt injection. Do not claim that prompt injection is solved.
- The suite makes no live provider calls unless a separate existing execution flow is explicitly opted in; this report does not certify provider-side retention.
- Human review, appeal, and consequential decision authority remain organizational responsibilities.