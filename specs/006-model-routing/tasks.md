---
description: "Implementation tasks for OpenAI and local MLX model routing"
---

# Tasks: OpenAI and Local MLX Model Routing

**Input**: Design documents from `/specs/006-model-routing/`

**Prerequisites**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included because the feature specification defines independent provider/failure criteria and explicitly requires mocked CI tests, a local endpoint integration contract, and an honest provider comparison.

**Organization**: Build the provider-neutral types first, preserve and test the existing OpenAI/Foundry route, then add the local MLX path and its host-routed action envelope. The final comparison uses the frozen Feature 004 case set and does not imply on-device parity on Linux.

## Phase 1: Setup

**Purpose**: Pin the optional Apple-silicon server dependency without adding MLX to the backend workspace.

- [x] T001 Create root `requirements-mlx.txt` pinning `mlx-lm==0.32.2`; keep the file separate from `uv.lock` and backend runtime dependencies.

---

## Phase 2: Foundational

**Purpose**: Establish provider-neutral models, capabilities, metadata, and configuration bounds used by both routes.

- [x] T002 [P] Add typed provider capability, usage, and run-metadata models in `apps/backend/src/policylens/agent_runtime/models.py`; enforce provider enum `openai|mlx`, route enum from `model-capabilities.schema.json`, nullable token/cost/memory fields, nonnegative latency, and fallback decision `none`.
- [x] T003 Define the provider-neutral `ModelGateway` protocol and result/error types in `apps/backend/src/policylens/agent_runtime/gateway.py`, depending on T002; expose provider/model identity, capability discovery, agent execution, and health without importing MLX libraries.
- [x] T004 Add provider-selector validation tests in `apps/backend/tests/unit/test_settings.py`; verify `MODEL_PROVIDER` and `EMBEDDING_PROVIDER` remain independent and a missing selected provider model fails before client construction. Keep MLX endpoint-specific URL checks in T014.

**Checkpoint**: Shared contracts and selection validation exist before provider-specific runtime behavior is changed.

---

## Phase 3: User Story 1 - Use OpenAI Generation (Priority: P1)

**Goal**: Preserve the current standard OpenAI and Foundry routes through the gateway, with exact provider/model/usage/latency metadata and safe configuration failures.

**Independent Test**: Mock client construction and completion results; verify standard OpenAI selects Responses, Foundry selects Chat Completions, missing configuration fails before outbound calls, and credentials/prompts are not logged.

### Tests for User Story 1

- [x] T005 [P] [US1] Expand `apps/backend/tests/unit/test_agent_provider.py` and `apps/backend/tests/unit/test_generation_baseline.py` to cover gateway selection for standard OpenAI and Foundry, exact effective model metadata, `max_retries=0`, missing key/model/base URL, mocked usage/latency capture, baseline provider selection, and redacted errors without live requests.
- [x] T006 [P] [US1] Add capability API tests in `apps/backend/tests/api/test_model_capabilities.py` for OpenAI readiness, selected model/route, bounded capability fields, missing/invalid configuration, and absence of credentials or full prompts in responses; validate payloads against the capability JSON Schema.

### Implementation for User Story 1

- [x] T007 [US1] Implement `OpenAIModelGateway` in `apps/backend/src/policylens/agent_runtime/gateway.py` around the existing OpenAI/Foundry builder in `apps/backend/src/policylens/agent_runtime/provider.py`; preserve standard Responses behavior, Foundry Chat Completions behavior, explicit effective model selection, bounded timeouts, and zero implicit retries.
- [x] T008 [US1] Implement OpenAI model capability discovery and configuration health in `apps/backend/src/policylens/agent_runtime/gateway.py`; report the effective configured model ID, route type, supported native tools/structured output, output limit, and safe limitations without making a generation request.
- [x] T009 [US1] Extend `AgentRuntime` and `AgentAnswerResponse` in `apps/backend/src/policylens/agent_runtime/runtime.py` and `apps/backend/src/policylens/agent_runtime/models.py` to report selected provider/model, bounded usage, model latency, capability profile, and `fallback_decision=none`; update `specs/004-agent-runtime/contracts/agent-api.schema.json`, `specs/006-model-routing/contracts/model-run-metadata.schema.json`, and `apps/backend/tests/unit/test_agent_models.py` so the provider enum permits `openai` and `mlx` while preserving existing response fields and OpenAI behavior.
- [x] T010 [US1] Implement the read-only `GET /model/capabilities` route in `apps/backend/src/policylens/api/model_capabilities.py` and register it in `apps/backend/src/policylens/api/app.py`; validate the response against `specs/006-model-routing/contracts/model-capabilities.schema.json` and never return credentials or the full configured endpoint URL.
- [x] T011 [US1] Route `NonAgentRagBaseline` through the selected `MODEL_PROVIDER` in `apps/backend/src/policylens/retrieval/generation.py`; preserve its extractive citation validation and OpenAI Responses/Foundry Chat Completions behavior, add locally validated MLX structured output and usage/latency metadata, update `specs/003-retrieval-and-citations/contracts/baseline-answer.schema.json` for `provider=openai|mlx`, and cover both providers in `apps/backend/tests/unit/test_generation_baseline.py` and `scripts/tests/test_agent_contracts.py` without changing embedding selection.

**Checkpoint**: OpenAI and Foundry remain independently selectable through the gateway, with no change to the default provider or embedding selector.

---

## Phase 4: User Story 2 - Select Local MLX Additively (Priority: P1)

**Goal**: Run a selected local MLX-LM model through loopback Chat Completions with exact model discovery, bounded output, explicit capability reporting, and no external fallback.

**Independent Test**: Use a fake local HTTP endpoint for `/v1/models` and `/v1/chat/completions`; verify loopback-only routing, model mismatch/unavailability, bounded deterministic requests, valid/invalid action envelopes, host-routed statistics, and zero OpenAI client creation.

### Tests for User Story 2

- [x] T012 [P] [US2] Add MLX adapter unit tests in `apps/backend/tests/unit/test_mlx_provider.py` for loopback URL validation, `/v1/models` identity matching, model/endpoint failures, request timeout, temperature `0`, `max_tokens` bound, usage extraction, safe errors, and no external URL/client use.
- [x] T013 [P] [US2] Add local action-envelope tests in `apps/backend/tests/unit/test_mlx_provider.py` and `apps/backend/tests/unit/test_agent_runtime.py` for `final` and `query_statistics` actions, Feature 004 `AgentDraft`/`StatisticsQueryRequest` validation, extra/unknown fields, malformed JSON, invalid tool arguments, output bounds, and no provider fallback.
- [x] T014 [P] [US2] Add fake-HTTP integration tests in `apps/backend/tests/integration/test_mlx_endpoint.py` for model discovery, successful completion, non-2xx/timeout, empty or malformed content, unsupported server capabilities, and rejection of non-loopback endpoints without external network access.

### Implementation for User Story 2

- [x] T015 [US2] Implement the local HTTP configuration validator in `apps/backend/src/policylens/settings.py`; reject non-loopback hosts, URL credentials/query/fragment, missing `MLX_MODEL`, and invalid bounds whenever `MODEL_PROVIDER=mlx`, without coupling to `EMBEDDING_PROVIDER`.
- [x] T016 [US2] Implement `MLXModelGateway` in `apps/backend/src/policylens/agent_runtime/mlx_provider.py` using the existing pinned `AsyncOpenAI` Chat Completions client against `MLX_BASE_URL`; check `/v1/models` for exact `MLX_MODEL`, set `temperature=0`, cap output/timeout, capture available usage, disable retries, and report native tool/schema capability as unsupported unless an explicit compatibility test proves otherwise.
- [x] T017 [US2] Implement strict `MLXAgentAction` parsing in `apps/backend/src/policylens/agent_runtime/mlx_actions.py` against `contracts/mlx-action.schema.json`; allow only `final` with Feature 004 `AgentDraft` or `query_statistics` with Feature 004 request fields constrained to the MCP contract, reject all extra fields, and mark model/action text as untrusted. Verified MCP-aligned geography/year/row bounds and `aggregation=none` grouping in parser tests and the MLX action JSON Schema test.
- [x] T018 [US2] Route `AgentRuntime` through the selected `ModelGateway` in `apps/backend/src/policylens/agent_runtime/runtime.py`; preserve the OpenAI Agents SDK path, add a finite MLX action loop using only the injected Feature 005 statistics adapter, enforce current turn/tool/time/output bounds, and fail safely without OpenAI fallback.
- [x] T019 [US2] Extend `GET /model/capabilities` in `apps/backend/src/policylens/api/model_capabilities.py` to report MLX model identity, loopback route, readiness, usage availability, configured limits, `host_action_envelope=true`, `native_tool_calls=false`, and `native_json_schema=false` unless verified; add API tests in `apps/backend/tests/api/test_model_capabilities.py`.

**Checkpoint**: With `MODEL_PROVIDER=mlx`, requests remain local, only the configured model is used, tool execution stays host-owned, and unsupported features fail closed.

---

## Phase 5: User Story 3 - Compare Providers Honestly (Priority: P2)

**Goal**: Compare OpenAI and MLX on identical frozen cases with exact model/platform identity, capability outcomes, per-case metrics, and explicit unmeasured fields.

**Independent Test**: Run the report builder with fake provider observations and verify same case coverage, schema validation, negative outcomes, `not_measured` cost/memory, and no live request by default.

### Tests for User Story 3

- [x] T020 [P] [US3] Add provider-comparison report tests in `scripts/tests/test_provider_evaluation.py` for frozen case-set hash, prompt version, and per-case retrieval index version, exact provider/model identity, status/tool/structured metrics, nullable groundedness/answer quality/memory/cost, platform limitations, and failed/partial runs.

### Implementation for User Story 3

- [x] T021 [US3] Implement `scripts/evaluate_providers.py` using the existing frozen `data/evaluation/agent-tool-cases.json`; default to no live OpenAI request, require explicit opt-in for OpenAI, allow local MLX execution only when the configured loopback endpoint is ready, and record per-case tool selection, argument/structured validity, expected outcome, latency, available usage, groundedness/answer quality when reviewed, and `not_measured` memory/cost where unavailable.
- [x] T022 [US3] Emit comparison records conforming to `contracts/provider-comparison.schema.json` and preserve reports/limitations in `docs/evaluation/provider-comparison.md`; include model IDs, prompt version, endpoint route type, retrieval index versions, package/runtime version, platform, case-set checksum, failures, and whether any live requests occurred.
- [x] T023 [P] Update `specs/006-model-routing/quickstart.md` with the separate `requirements-mlx.txt` setup, loopback MLX server command, API capability probe, fake-endpoint test command, explicit OpenAI live opt-in, provider comparison command, and Apple-silicon-only verification limitation.
- [x] T024 [P] Create `specs/006-model-routing/traceability.md` mapping every `MODEL-006-*`, `SEC-006-01`, `EVAL-006-01`, `AC-006-*`, and `SC-006-*` item to tests, inspection, or a reproducible command; explicitly label the Mac-only MLX runtime check unrun on Linux.
- [x] T025 Run `make format-check-python`, `make lint-python`, `make typecheck-python`, `make test-python`, and `python3 scripts/check_traceability.py`; record exact results and residual Mac-only checks in `specs/006-model-routing/traceability.md` and `specs/006-model-routing/quickstart.md`.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Pin the separate Mac-only MLX server dependency; do not install it in the backend workspace.
- **Foundational (Phase 2)**: Typed gateway/capability/usage models and loopback config validation block provider work.
- **US1 (Phase 3)**: Starts after Phase 2; preserves the currently working OpenAI/Foundry path and defines shared runtime metadata.
- **US2 (Phase 4)**: Depends on Phase 2; tests may start independently, but gateway/runtime integration follows US1's shared interface.
- **US3 (Phase 5)**: Depends on both providers and the capability model; comparison is local/fake by default and live-provider opt-in only.

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational; no dependency on MLX implementation.
- **US2 (P1)**: Starts after Foundational; reuses US1 gateway and response metadata but can validate the endpoint with a fake client independently.
- **US3 (P2)**: Starts after US1/US2; it evaluates both providers and the non-agent baseline but does not change routing behavior.

### Parallel Opportunities

- T002 precedes T003 because the gateway protocol uses the shared capability and usage models; T004's selector tests use the settings boundary independently.
- T005/T006 and the US2 fake endpoint/action tests can be authored in separate test files after their shared models exist.
- OpenAI adapter preservation (T007) and local MLX adapter implementation (T015) touch separate files; runtime routing integration waits until both gateway interfaces are stable.
- T020 report tests can be developed independently from the runtime provider adapters using fake observations.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational tasks.
2. Complete US1 and verify no change to current OpenAI/Foundry routing.
3. Complete US2 with fake-endpoint tests and no-fallback behavior; do not claim real MLX success on Linux.

### Incremental Delivery

1. Keep OpenAI as the existing default and add MLX only behind explicit configuration.
2. Add provider capability/usage reporting and fail-closed local action handling.
3. Add the frozen-case comparison harness and record local/Linux versus Apple-silicon evidence separately.

## Notes

- `[P]` means tasks edit separate files and have no dependency on incomplete tasks.
- Linux tests use fake HTTP clients and must not call external APIs.
- A real MLX model must be run only on the user's Apple-silicon machine; report its exact chip/model/quantization or leave that validation explicitly unrun.
- Do not mark tasks complete without recorded verification evidence.