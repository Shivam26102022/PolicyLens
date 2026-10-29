# Feature 008 Research

## Decisions

### Reuse implemented trust controls

**Decision**: Audit existing controls first and add tests only for gaps. Relevant existing code includes Feature 003 permission filtering/citation validation, Feature 004 lifecycle-only safe hooks and deterministic tool budgets, Feature 005 MCP identity/permission/size checks, Feature 006 loopback MLX and explicit provider selection, and Feature 007 case/secret redaction.

**Rationale**: The repository already has unit tests for user/retrieved/MCP instruction separation, caller permission-scope rejection, server identity, read-only tool allow-list, timeouts, malformed output, secret redaction, and no provider fallback. Replacing these controls would increase risk and duplicate coverage.

### Local-only threat model

**Decision**: Treat the current local assessment deployment as the only in-scope operational target. Do not implement authentication, public HTTP transport, or production hosting assumptions. Record them as residual risks if deployment changes.

**Rationale**: The user resolved Q-DEPLOY-01 as local only. Feature 005 and the foundation assessment also describe local-only service boundaries.

### Deterministic fixtures and safe test data

**Decision**: Use synthetic attack payloads and fake providers/MCP responses. Do not copy restricted source text or real credentials into fixtures. Assert policy/permission/tool/provider invariants rather than relying only on model answer text.

**Rationale**: Existing tests already use fake secret-shaped strings and fixture sources; this makes the security checks repeatable and offline.

### Report coverage, not perfection

**Decision**: Use a threat model with assets, principals, boundary, data class, controls, failure modes, abuse scenarios, test IDs, and residual risks. A finding is not closed solely because a prompt says not to comply.

**Rationale**: The master spec expressly prohibits claiming prompt injection is solved and asks for measured attack coverage/residual risk.

## Existing Evidence

- `apps/backend/tests/unit/test_agent_state.py` verifies agent lifecycle hooks exclude system prompt, user query, and model output.
- `apps/backend/tests/unit/test_agent_runtime.py` and `test_agent_tools.py` cover tool permissions, budgets, fabricated citations, timeout, and safe stopping.
- `apps/backend/tests/unit/test_mcp_client.py` covers server allow-list identity/version, tool/resource allow-lists, timeout, malformed data, permission rejection, and untrusted passage text.
- `apps/backend/tests/unit/test_retrieval.py` and `test_retrieval_models.py` cover permission filtering before evidence return.
- `apps/backend/tests/unit/test_logging.py` and `services/mcp-policy-data/tests/test_logging.py` cover secret redaction and allow-listed telemetry fields.
- `apps/backend/tests/unit/test_settings.py` and `test_mlx_provider.py` cover loopback-only MLX configuration and no fallback.

## Residual Constraints

- No production target was specified. Public-network isolation, production authentication, multi-tenant authorization, and deployment secret management cannot be certified here.
- Tests prove specific fixtures and code paths only; they do not establish general prompt-injection prevention.