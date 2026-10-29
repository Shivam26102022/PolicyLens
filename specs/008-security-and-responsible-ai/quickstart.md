# Feature 008 Quickstart

Feature 008 audits the current local-assessment security boundaries. It does not add production authentication, public network exposure, or a claim that prompt injection is solved.

## Offline Security Checks

```bash
uv run --locked --package policylens pytest \
  apps/backend/tests/unit/test_agent_state.py \
  apps/backend/tests/unit/test_agent_runtime.py \
  apps/backend/tests/unit/test_agent_tools.py \
  apps/backend/tests/unit/test_mcp_client.py \
  apps/backend/tests/unit/test_retrieval.py \
  apps/backend/tests/unit/test_retrieval_models.py \
  apps/backend/tests/unit/test_logging.py \
  apps/backend/tests/unit/test_settings.py \
  services/mcp-policy-data/tests/test_logging.py
```

Security fixtures use fake keys, fake MCP responses, synthetic injection text, and local settings. They do not make live provider calls.

## Boundary Audit

```bash
uv run --locked --package policylens python -m scripts.security_audit
```

The audit reports fixture coverage and secret-scan results; it cannot certify production deployment controls because Feature 008 is scoped to local assessment only.

## Review

Inspect [threat-model.md](../../docs/security/threat-model.md), [privacy-retention.md](../../docs/security/privacy-retention.md), and [security-residual-risks.md](../../docs/security/security-residual-risks.md). Re-run the complete repository gates before accepting changes. Any new production deployment, public endpoint, or authentication requirement reopens Q-DEPLOY-01 and requires a separate threat assessment.