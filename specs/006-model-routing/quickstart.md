# Feature 006 Quickstart

Feature 006 keeps OpenAI and local MLX independently selectable. The backend never switches providers automatically.

## Backend Verification (Linux/macOS)

Prerequisites: Python 3.12 and `uv`. The tests use fake providers and do not make external model requests.

```bash
uv sync --locked --all-packages --all-groups
uv run --locked --package policylens pytest \
  apps/backend/tests/unit/test_agent_tools.py \
  apps/backend/tests/unit/test_mcp_client.py \
  apps/backend/tests/unit/test_agent_provider.py \
  apps/backend/tests/unit/test_model_gateway.py \
  apps/backend/tests/unit/test_mlx_provider.py \
  apps/backend/tests/unit/test_generation_baseline.py \
  apps/backend/tests/unit/test_agent_runtime.py \
  apps/backend/tests/api/test_model_capabilities.py \
  apps/backend/tests/integration/test_mlx_endpoint.py \
  scripts/tests/test_provider_evaluation.py \
  scripts/tests/test_agent_contracts.py
```

With provider settings configured, start the backend and request its read-only capability report:

```bash
make dev-api
curl -fsS http://127.0.0.1:8000/model/capabilities
```

The capability endpoint reports the configured provider only; it does not make a generation request.

## Local MLX Runtime (Apple Silicon Only)

On the target Mac, install the documented MLX-LM server in a separate local Python environment. Do not add MLX or model weights to the backend workspace.

```bash
python3.12 -m venv .mlx-venv
source .mlx-venv/bin/activate
python -m pip install -r requirements-mlx.txt
```

Configure the backend environment explicitly:

```text
MODEL_PROVIDER=mlx
MLX_BASE_URL=http://127.0.0.1:8080/v1
MLX_MODEL=<exact-model-id-reported-by-v1-models>
```

Start the server in the separate environment with the same configured model ID:

```bash
mlx_lm.server --model "$MLX_MODEL"
```

MLX-LM binds to localhost by default. Keep it on loopback and do not expose it publicly. Check the loaded model with `GET /v1/models`; the backend refuses to run if the exact `MLX_MODEL` is absent. Use a quantized model compatible with the target's available unified memory; record the exact model ID, revision, quantization, macOS version, chip, and memory for any on-device result.

## Capability and Agent Checks

```bash
make mcp-health
uv run --locked --package policylens pytest \
  apps/backend/tests/unit/test_agent_tools.py \
  apps/backend/tests/unit/test_mcp_client.py \
  apps/backend/tests/unit/test_model_gateway.py \
  apps/backend/tests/unit/test_mlx_provider.py \
  apps/backend/tests/unit/test_agent_runtime.py \
  apps/backend/tests/integration/test_mlx_endpoint.py
```

The MLX capability report distinguishes native tool calls and server-enforced JSON-schema output from the host-validated action envelope. Unsupported native capabilities are not inferred from the OpenAI-compatible endpoint. Invalid actions, unreachable endpoints, and model mismatches fail safely without OpenAI fallback.

The statistics function-tool schema and MLX action contract use the MCP server's bounds: one to four unique uppercase ISO3 geographies, years 2015–2025, and `row_limit` 1–44. With `aggregation=none`, `group_by` must be empty.

## Provider Comparison

The default command writes a contract-shaped report with skipped rows and makes no provider requests. The test suite exercises fake provider observations and an in-memory HTTP endpoint. Live OpenAI generation requires explicit `--allow-openai-live`; local MLX model discovery and generation require explicit `--run-mlx`. If OpenAI embeddings are configured, the same OpenAI opt-in is required because retrieval could otherwise make an external request. On Apple silicon, pass the separately installed MLX-LM version and record the model/quantization and hardware. On Linux, do not claim MLX execution, memory, cost, or quality parity.

```bash
uv run --locked --package policylens python scripts/evaluate_providers.py
uv run --locked --package policylens python scripts/evaluate_providers.py \
  --providers openai --providers mlx \
  --allow-openai-live --run-mlx --mlx-runtime-version 0.32.2
```

Each attempted result records the retrieval `index_version`; skipped rows have a null version. `status=succeeded` means the response status matched the frozen case's expected status. Summary rates pool attempted provider/case rows; tool selection is scored against each case's `requires_tool` label. Latency is mean model latency, memory is peak reported usage, and cost is total reported usage only when every attempted row is measured. Otherwise memory/cost remain `not_measured`. The report does not infer groundedness or answer quality from schema validity.

## Quality Gates

```bash
make format-check-python
make lint-python
make typecheck-python
make test-python
python3 scripts/check_traceability.py
make data-verify
make retrieval-verify
make mcp-health
```

## Verification Record (2026-10-26)

- Formatting, Ruff, and mypy gates passed for backend/scripts and MCP.
- `make test-python` passed: 180 backend, 37 MCP, and 55 script tests (272 total).
- `scripts/check_traceability.py`, data verification, retrieval verification, and MCP health all passed; retrieval and MCP status were `ready`.
- The default comparison report contains skipped rows only and records `live_requests_made=false`.
- Real MLX execution, on-device memory/cost, and provider quality were not measured on this Linux host. The exact Mac chip/model and quantization remain unconfirmed.

## MCP Statistics Contract Regression (2026-10-27)

- Focused agent-tool, MLX action, and MCP adapter tests: **36 passed**.
- The generated strict statistics tool schema exposes the MCP input bounds; MLX action parsing rejects out-of-range years/rows and unsupported `aggregation=none` grouping.
- `make check` passed formatting, lint, Python and TypeScript typechecks, **256 backend tests**, **39 MCP tests**, **115 script tests**, **50 frontend tests**, and traceability.
- The updated MLX action contract parsed as valid JSON. No live OpenAI or MLX generation request was made.
