# Implementation Plan: OpenAI and Local MLX Model Routing

**Branch**: `006-model-routing` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-model-routing/spec.md`

## Summary

Add a provider-neutral model gateway to the existing backend runtime. Preserve the OpenAI/Foundry route and add an explicitly selected, loopback-only MLX-LM Chat Completions adapter. Because the official MLX-LM server documents chat completions and model listing but not native tools or JSON-schema output, the local agent route uses a Pydantic-validated action envelope for `final` or the existing `query_statistics` tool. The host executes only that allow-listed tool and never falls back from MLX to OpenAI.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Existing `openai==3.37.0` and `openai-agents==0.24.0`; no new backend runtime dependency and no MLX package in the Linux backend. The separate Apple-silicon environment installs pinned `mlx-lm==0.32.2` from root `requirements-mlx.txt` and serves the configured model on loopback.

**Storage**: No new persistent store. Record provider, exact configured model ID, capability profile, prompt version, latency, and available usage in existing agent response/event metadata. Comparison output uses a versioned evaluation report.

**Testing**: pytest unit tests with mocked `AsyncOpenAI`/HTTP peers, runtime routing tests, fake structured outputs/action envelopes, and a provider comparison harness over frozen cases. Linux CI makes no live OpenAI or MLX calls. A real MLX smoke/parity run is Mac-only and explicitly deferred on this host.

**Target Platform**: Backend API on Python 3.12 Linux/macOS; MLX-LM runtime on Apple silicon/macOS only. Initial user-reported target is a 16-core GPU and 24 GB unified memory; exact chip/model revision is unconfirmed. OpenAI remains usable from supported backend hosts.

**Project Type**: Existing FastAPI backend package and existing API/runtime tests; no new service or model-serving process owned by PolicyLens.

**Performance Goals**: No unmeasured latency SLO. Preserve `request_timeout_seconds=90` and the configured `max_agent_output_tokens` baseline; Responses API output ceilings scale by reasoning effort (1x/2x/4x/8x for none/low/medium/high) and never exceed 8,000 tokens. Keep agent input within the existing 50,000-character bound. The local action loop is finite and uses existing turn/tool budgets.

**Constraints**: `MODEL_PROVIDER` selects generation independently from `EMBEDDING_PROVIDER`. MLX endpoint host must be loopback; `MLX_MODEL` is explicit and must match `/v1/models`. No automatic provider fallback. The local server is treated as supporting only documented Chat Completions/model-list behavior until capability checks prove otherwise. Structured output is locally Pydantic-validated; tool selection uses only the constrained `final`/`query_statistics` envelope. Do not log credentials, prompts, raw responses, or tool payloads. Do not claim Apple-silicon execution or provider parity on Linux.

**Scale/Scope**: One selected provider per request, the existing bounded agent workflow, and a frozen Feature 004 case subset. No browser credentials, UI provider selector, new embedding implementation, server-side MLX installation, or automatic data-handling switch.

## Constitution Check

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Both routes keep current-run citations and deterministic statistics evidence; local action and model output are untrusted and validated. | PASS |
| II. Scientific Evaluation Before Complexity | Compare the same frozen cases; disclose that Apple-silicon runtime and quality parity are unverified on Linux. | PASS |
| III. Bounded Agency and Deterministic Computation | Use typed action envelopes, one allow-listed statistics tool, existing turn/tool/output/time bounds, and safe stopping. | PASS |
| IV. Secure MCP Trust Boundaries | Preserve Feature 005 host validation; enforce MLX loopback and validate local model outputs/capabilities. | PASS |
| V. Provider Portability With Measured Parity | Keep OpenAI and MLX independently selectable; no silent fallback and no parity claim without measurements. | PASS |
| VI. Reproducibility Is a Product Feature | Record exact effective model IDs, endpoint mode, prompt version, capability profile, versions, and frozen case-set hash. | PASS |
| VII. Privacy, Responsible AI, and Human Oversight | Keep keys backend-side; MLX requests stay loopback; redact prompts and outputs; report model limitations. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | Add backend adapters only; retain the three existing deployable services. The MLX server remains user-managed. | PASS |
| IX. Testable Specifications and Traceability | Map all provider, failure, capability, privacy, and parity criteria to tests/commands. | PASS |
| X. Honest Reporting | Mocks are labeled; Linux checks do not claim MLX execution, memory, cost, or quality parity. | PASS |

## Project Structure

### Documentation

```text
specs/006-model-routing/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── traceability.md
├── contracts/
└── tasks.md
```

### Source and Tests

```text
apps/backend/src/policylens/agent_runtime/
├── gateway.py
├── provider.py
├── mlx_provider.py
├── mlx_actions.py
├── runtime.py
└── models.py
apps/backend/src/policylens/api/model_capabilities.py
apps/backend/src/policylens/settings.py
apps/backend/src/policylens/retrieval/generation.py
apps/backend/tests/unit/test_model_gateway.py
apps/backend/tests/unit/test_mlx_provider.py
apps/backend/tests/unit/test_agent_runtime.py
apps/backend/tests/unit/test_agent_models.py
apps/backend/tests/unit/test_generation_baseline.py
apps/backend/tests/api/test_model_capabilities.py
apps/backend/tests/integration/test_mlx_endpoint.py
specs/004-agent-runtime/contracts/agent-api.schema.json
scripts/evaluate_providers.py
scripts/tests/test_provider_evaluation.py
docs/evaluation/provider-comparison.md
requirements-mlx.txt
```

**Structure Decision**: Keep both providers inside the existing API backend. Preserve the OpenAI/Foundry adapter and add a loopback MLX-LM adapter; the user runs MLX-LM separately on Apple silicon. The gateway reports native endpoint capabilities explicitly. Local structured generation is a bounded Pydantic-validated action envelope; only the existing `query_statistics` operation may be host-routed. No public MLX endpoint, local-to-OpenAI fallback, new PolicyLens service, or model weights are added.

## Complexity Tracking

No additional service or framework is required. The constrained local action envelope is needed because the documented MLX-LM server does not promise native tool calls or JSON-schema output; it preserves a strict host boundary while allowing explicit capability reporting.
