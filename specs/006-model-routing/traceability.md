# Feature 006 Traceability

## Requirement Matrix

| Requirement | Evidence | Status / limitation |
|---|---|---|
| MODEL-006-01 | `apps/backend/src/policylens/agent_runtime/models.py`; `apps/backend/src/policylens/agent_runtime/gateway.py`; `apps/backend/tests/unit/test_model_gateway.py`; `apps/backend/tests/api/test_model_capabilities.py` | Typed gateway, provider capabilities, usage, and run metadata are covered by unit/API tests. |
| MODEL-006-02 | `apps/backend/tests/unit/test_agent_provider.py`; `apps/backend/tests/unit/test_model_gateway.py`; `apps/backend/tests/unit/test_generation_baseline.py`; `apps/backend/tests/unit/test_agent_runtime.py` | Standard OpenAI Responses and Foundry Chat Completions selection, usage metadata, selected model, and no implicit retries are mocked. No live OpenAI call was made by verification. |
| MODEL-006-03 | `apps/backend/src/policylens/agent_runtime/mlx_provider.py`; `apps/backend/src/policylens/agent_runtime/mlx_actions.py`; `apps/backend/tests/unit/test_agent_tools.py`; `apps/backend/tests/unit/test_mcp_client.py`; `apps/backend/tests/unit/test_mlx_provider.py`; `apps/backend/tests/integration/test_mlx_endpoint.py`; `scripts/tests/test_agent_contracts.py`; `contracts/mlx-action.schema.json` | Loopback, model discovery, MCP-aligned statistics bounds, host action validation, and conservative native capability reporting use fake clients/HTTP transport and JSON Schema validation. Real MLX-LM execution is unrun on this Linux host. |
| MODEL-006-04 | `apps/backend/tests/unit/test_agent_runtime.py::test_agent_runtime_uses_selected_mlx_gateway_without_openai_fallback`; `apps/backend/tests/unit/test_mlx_provider.py`; `apps/backend/tests/integration/test_mlx_endpoint.py` | MLX failure remains local and safe; no OpenAI fallback is constructed. |
| MODEL-006-05 | `apps/backend/tests/unit/test_settings.py::test_generation_and_embedding_providers_are_independent`; `apps/backend/tests/unit/test_generation_baseline.py::test_baseline_settings_select_openai_or_mlx_independently_from_embeddings` | Generation and embedding selectors are tested independently for both runtime paths. |
| EVAL-006-01 | `scripts/evaluate_providers.py`; `scripts/tests/test_provider_evaluation.py`; `specs/006-model-routing/contracts/provider-comparison.schema.json`; `docs/evaluation/provider-comparison.md` | The report records its versioned prompt (`agent-v1` or `agent-v2`), the same frozen case set, and per-case retrieval index version. Default rows are skipped; quality, memory, and cost are not inferred. No on-device parity claim is made. |
| SEC-006-01 | `apps/backend/src/policylens/agent_runtime/gateway.py`; `apps/backend/src/policylens/agent_runtime/traces.py`; `apps/backend/tests/unit/test_agent_runtime.py`; `apps/backend/tests/unit/test_mlx_provider.py`; `apps/backend/tests/integration/test_mlx_endpoint.py` | Provider tracing excludes sensitive payloads; tests cover untrusted input handling and safe provider/action failures. No prompt, response body, or credential is included in comparison output. |
| AC-006-01 | `apps/backend/tests/unit/test_agent_provider.py`; `apps/backend/tests/unit/test_model_gateway.py`; `apps/backend/tests/api/test_model_capabilities.py`; `scripts/tests/test_agent_contracts.py` | OpenAI and Foundry route, configured model identity, usage, and capability responses are mocked and contract-validated. |
| AC-006-02 | `apps/backend/tests/unit/test_settings.py::test_openai_generation_requires_key_and_model`; `apps/backend/tests/unit/test_agent_provider.py::test_foundry_deployment_without_base_url_fails_before_client_creation` | Missing selected-provider configuration fails before an outbound generation request. |
| AC-006-03 | `apps/backend/tests/unit/test_mlx_provider.py::test_mlx_gateway_discovers_model_and_reports_local_capabilities`; `apps/backend/tests/integration/test_mlx_endpoint.py::test_fake_http_endpoint_discovers_model_and_runs_bounded_completion` | Fake loopback endpoint only; Apple-silicon runtime and hardware behavior remain unverified. |
| AC-006-04 | `apps/backend/tests/unit/test_mlx_provider.py::test_mlx_gateway_rejects_model_mismatch_before_completion`; `apps/backend/tests/unit/test_agent_runtime.py::test_agent_runtime_uses_selected_mlx_gateway_without_openai_fallback`; `apps/backend/tests/integration/test_mlx_endpoint.py` | Model mismatch, endpoint errors, timeout, and malformed output fail safely without external fallback. |
| AC-006-05 | `apps/backend/tests/unit/test_settings.py::test_generation_and_embedding_providers_are_independent`; `apps/backend/tests/unit/test_generation_baseline.py::test_baseline_settings_select_openai_or_mlx_independently_from_embeddings` | Explicit environment selection leaves the other provider available and does not change embedding selection. |
| SC-006-01 | `apps/backend/tests/unit/test_settings.py`; `apps/backend/tests/unit/test_agent_provider.py`; `apps/backend/tests/unit/test_mlx_provider.py`; `apps/backend/tests/api/test_model_capabilities.py` | Both provider routes and their safe configuration failures have focused mocked coverage. |
| SC-006-02 | `apps/backend/tests/unit/test_agent_runtime.py::test_agent_runtime_uses_selected_mlx_gateway_without_openai_fallback`; `scripts/tests/test_provider_evaluation.py::test_default_cli_writes_skipped_rows_without_entering_provider_runner` | No implicit external fallback; the comparison CLI default does not enter a provider runner. |
| SC-006-03 | `scripts/tests/test_provider_evaluation.py`; `specs/006-model-routing/contracts/provider-comparison.schema.json`; `docs/evaluation/provider-comparison.md` | Report identity, frozen case checksum, failures/skips, metrics, and limitations are schema-validated. |

## Reproducible Checks

```bash
uv run --locked --package policylens pytest \
  apps/backend/tests/unit/test_agent_tools.py \
  apps/backend/tests/unit/test_mcp_client.py \
  apps/backend/tests/unit/test_agent_provider.py \
  apps/backend/tests/unit/test_model_gateway.py \
  apps/backend/tests/unit/test_mlx_provider.py \
  apps/backend/tests/unit/test_generation_baseline.py \
  apps/backend/tests/unit/test_settings.py \
  apps/backend/tests/unit/test_agent_runtime.py \
  apps/backend/tests/api/test_model_capabilities.py \
  apps/backend/tests/integration/test_mlx_endpoint.py \
  scripts/tests/test_agent_contracts.py \
  scripts/tests/test_provider_evaluation.py
```

Repository Python gates and traceability command:

```bash
make format-check-python
make lint-python
make typecheck-python
make test-python
python3 scripts/check_traceability.py
```

## Verification Results (2026-10-26)

| Check | Result |
|---|---|
| `make format-check-python` | PASS; 84 backend/script files and 13 MCP files already formatted. |
| `make lint-python` | PASS; backend/scripts and MCP Ruff checks passed. |
| `make typecheck-python` | PASS; mypy checked 84 backend/script files and 13 MCP files. |
| `make test-python` | PASS; 180 backend, 37 MCP, and 55 script tests passed (272 total). |
| `python3 scripts/check_traceability.py` | PASS; 67 global requirements, 14 Feature 001 requirements, 11 acceptance criteria, 5 success criteria, and 10 demos. |
| `make data-verify` | PASS; all six source data artifacts verified. |
| `make retrieval-verify` | PASS; active index status `ready`, version `45935afc940a7489563a38c32bbac909b0d8e6a9fb58182fb5c14e86ff130ea4`. |
| `make mcp-health` | PASS; MCP status `ready`. |
| Default provider report | PASS; six cases per provider were marked `skipped`, `live_requests_made=false`. |

## MCP Statistics Contract Regression (2026-10-27)

- Focused `test_agent_tools.py`, `test_mlx_provider.py`, and `test_mcp_client.py`: **36 passed**; the MLX action JSON Schema regression test also passes.
- `make check` passed formatting, lint, Python and TypeScript typechecks, **256 backend tests**, **39 MCP tests**, **115 script tests**, **50 frontend tests**, and traceability.
- The strict tool schema exposes MCP limits; local MLX parsing rejects invalid years, row limits, and grouping for `aggregation=none`. The MLX contract JSON parses successfully.
- No live OpenAI or MLX generation request was made.

## Unverified Platform Checks

- Real MLX-LM model discovery and generation on Apple silicon were not run; this implementation session is on Linux.
- The reported target has a 16-core GPU and 24 GB unified memory, but the exact chip/model is unconfirmed. Model revision and quantization remain configurable and unpinned.
- Provider quality, groundedness, memory, and cost have no live measurements. The comparison report leaves them `not_measured` unless valid measurements or human review are supplied.