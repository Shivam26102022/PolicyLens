# Feature 006 Research

## Decisions

### Provider boundary

- Preserve `MODEL_PROVIDER` as the generation selector and `EMBEDDING_PROVIDER` as an independent selector. Keep OpenAI as the default and preserve the existing standard OpenAI Responses and Foundry Chat Completions behavior.
- Introduce a typed `ModelGateway` boundary for provider/model identity, capability discovery, structured generation, usage, and health. Keep the gateway and adapters in the existing backend package; do not add a service or a third-party adapter dependency.
- Keep the currently configured OpenAI model/deployment explicit. Record the effective model identifier in run metadata; do not print or persist API credentials.
- Apply `MODEL_PROVIDER` to both Feature 004 agent generation and Feature 003's non-agent retrieval answer baseline. Preserve retrieval, citation validation, and existing answer contracts; route only generation through the selected provider.

### Local MLX route

- Use the existing `MLX_BASE_URL` default (`http://127.0.0.1:8080/v1`) and `MLX_MODEL` setting to connect to an `mlx_lm.server` process on Apple silicon through its OpenAI-like Chat Completions API. Discover the loaded model through `/v1/models` and fail closed if the configured ID is absent.
- Require the local base URL to resolve to loopback (`localhost`, `127.0.0.1`, or `::1`) when `MODEL_PROVIDER=mlx`. The backend sends no external request and performs no provider fallback.
- Do not install or import MLX in the Linux backend. The user runs the MLX-LM server on the Apple-silicon host; CI uses a fake local HTTP endpoint. Record the exact configured model ID, server/library version when available, and platform in provider metadata and evaluation output.
- The official MLX-LM server documentation describes `/v1/chat/completions`, `/v1/models`, sampling controls, maximum output tokens, and usage fields. It does not document native tool calling or JSON-schema-constrained responses. Do not infer those capabilities from OpenAI-like HTTP compatibility.

### Capabilities and structured agent flow

- Report native structured-output and native tool-call support separately from application-level structured generation and host-routed tools.
- For MLX, use a bounded Pydantic-validated action envelope with only `final` or `query_statistics` actions. Treat model output as untrusted, validate tool arguments before execution, invoke only the existing Feature 005 statistics adapter, and limit the local action cycle to the configured finite tool budget.
- Generate the final `AgentDraft` through the same bounded local Chat Completions route and validate it with the existing Pydantic response models. Invalid JSON, invalid action arguments, missing capability, or malformed output fails safely; it never switches to OpenAI.
- Keep the OpenAI route on the Agents SDK's supported provider/model path with its existing native tool and structured-output behavior. Use the SDK's strict feature validation for the Chat Completions-based local route where available.

### Limits, usage, and privacy

- Reuse existing `request_timeout_seconds`, `max_agent_output_tokens`, `max_agent_turns`, and tool budgets. On the Responses API, the configured output-token limit is the standard-effort baseline; multiply it by 1/2/4/8 for none/low/medium/high, capped at 8,000, because provider reasoning tokens and the final structured answer share `max_output_tokens`. The local adapter sets deterministic sampling (`temperature=0`) and caps `max_tokens` at the configured output limit.
- Capture provider/model, capability profile, latency, and available prompt/completion/total-token usage. Local memory and cost are `not_measured` unless an Apple-silicon benchmark measures them.
- Keep tracing disabled for sensitive payloads; record only safe metadata. Never log full prompts, local model output, keys, or raw provider errors.

### Evaluation and platform limits

- Reuse the frozen Feature 004 agent/tool case set for same-input comparisons where compatible. Retain the per-case outcomes and report expected-status rate, tool selection/argument validity, structured validity, latency, and model/platform identifiers. Do not tune on the frozen cases.
- Unit and integration tests on Linux use fakes and assert no outbound request on the MLX path. Actual MLX runtime, memory, and parity certification remain a MacBook/Apple-silicon gate; no results will be invented.
- Live OpenAI/Foundry comparison remains explicit opt-in. Default tests use mocks; no live model request is required for Feature 006 implementation gates.

## Verification Basis

- Inspected the existing OpenAI provider and `AgentRuntime`: OpenAI/Foundry selection exists, while `AgentRuntime` currently rejects `MODEL_PROVIDER=mlx`, reports provider `openai` unconditionally, and exposes an OpenAI-only provider-builder type.
- Inspected existing `AppSettings`: `model_provider`, `mlx_base_url`, `mlx_model`, output-token/time limits, and independent embedding selection are already present.
- Verified the pinned Agents SDK `OpenAIProvider` constructor and Chat Completions model path locally. The existing Foundry route already uses `OpenAIProvider(..., use_responses=False)` for a custom OpenAI-compatible endpoint.
- Reviewed the official [MLX-LM server documentation](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md): the local server exposes Chat Completions and model listing on localhost, but does not document native tool calling or JSON-schema output.
- Reviewed the official [Agents SDK model documentation](https://openai.github.io/openai-agents-python/models/): it supports custom OpenAI-compatible endpoints and warns that structured-output and tool capabilities vary by backend and must be validated.
- The current host is Linux x86_64. It can verify routing, capability, safety, and fake-endpoint behavior, but cannot certify MLX execution or Apple-silicon memory/performance.
