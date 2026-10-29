# Feature 006 Data Model

## Provider Selection

### `ModelProviderConfig`

Generation provider is `openai` or `mlx`, selected by `MODEL_PROVIDER`. Embedding provider remains separately selected by `EMBEDDING_PROVIDER`. A provider change is explicit for each process configuration; no request-time or automatic fallback is permitted.

The selected generation route applies to both the Feature 004 agent answer and Feature 003 non-agent retrieval answer baseline. Retrieval, citation validation, and embedding-provider selection remain owned by their existing boundaries.

The OpenAI model identifier is resolved from the effective configured `OPENAI_DEPLOYMENT_MODEL` or `OPENAI_MODEL`. The MLX model identifier is the explicit `MLX_MODEL` value and must match an identifier discovered from the loopback MLX-LM `/v1/models` endpoint. Neither model identifier is silently replaced by a default during an agent run.

When `MODEL_PROVIDER=mlx`, `MLX_BASE_URL` must use HTTP and a loopback host (`localhost`, `127.0.0.1`, or `::1`), with no URL username/password, query, or fragment. Its path is the configured OpenAI-compatible API root, normally `/v1`. The configured model ID, endpoint kind, and server/runtime version are safe metadata; credentials and full endpoint URLs are not returned to clients or logs.

## Gateway and Capabilities

### `ModelGateway`

Provider-neutral runtime boundary for:

- provider/model descriptor and health/capability discovery;
- bounded agent execution returning a Pydantic-validated Feature 004 `AgentDraft`;
- OpenAI Agents SDK model/provider construction where native agent execution is supported;
- usage and latency metadata.

The non-agent retrieval baseline uses the same `MODEL_PROVIDER` selector and its own validated response adapter; it does not implement `ModelGateway`.

The OpenAI implementation retains the existing Responses path for standard OpenAI and Chat Completions path for Foundry/custom endpoints. The MLX implementation uses the local Chat Completions endpoint and client-side schema validation. Unsupported operations raise a stable capability error rather than changing providers.

### `ModelCapabilities`

Contains provider, exact model ID, route kind, readiness, capability booleans for native JSON-schema output and host-validated action envelopes, native tool-call support, streaming support, usage-reporting support, context/output bounds, server/library version when available, and limitations. Native structured output versus host-validated JSON is represented by `native_json_schema` and `host_action_envelope`; no separate mode field is returned. A capability is marked supported only when established by the selected adapter contract or a versioned compatibility test; it is not inferred from an OpenAI-compatible URL.

For the documented MLX-LM server, initial capabilities are text generation, model discovery, usage reporting when returned by the server, and a host-validated JSON action envelope. Native tool calling and server-enforced JSON-schema output are reported unsupported unless an explicit compatibility test later verifies them.

### `ModelUsage` and `ModelRunMetadata`

Usage contains nullable prompt, completion, and total token counts plus nullable cost and memory values. Run metadata contains the selected provider/model, capability profile, prompt version, request latency, usage, and fallback decision (`none` for this feature). Local cost/memory remain null unless measured; no estimate is represented as a measurement.

## Local Action Envelope

### `MLXAgentAction`

A strict JSON object returned by local generation with `schema_version=1.0` and exactly one action:

- `final`: carries a validated Feature 004 `AgentDraft` (including its existing abstention states) and no tool request.
- `query_statistics`: carries one Feature 004 `StatisticsQueryRequest` and no draft.

Unknown action names, extra properties, missing/incompatible payloads, malformed JSON, invalid query arguments, or invalid drafts fail safely. Only `query_statistics` is routable. The backend validates the action, runs the existing Feature 005 adapter under Feature 004 budgets, marks tool output untrusted, and may request a final structured draft. The local model cannot select a provider or additional tool.

The action cycle is finite: local planning, at most the configured tool budget, and local final generation. Cancellation, request timeout, output-token limits, and the existing agent turn/tool limits apply. No action is retried by switching to OpenAI.

## Agent Response Metadata

Extend the existing Feature 004 agent response with provider (`openai`, `mlx`), effective model ID, `ModelCapabilities`, nullable `ModelUsage`, model latency in milliseconds, and a fallback decision fixed to `none` for this feature. Extend the Feature 003 non-agent baseline generation metadata with provider/model, nullable usage, latency, and the same no-fallback marker. Responses retain existing citation, calculation, status, and trace fields; they add no prompt, raw provider response, or credential.

## State and Failure Model

Provider discovery yields `ready`, `unsupported`, or `unavailable` with the exact descriptor. Stable external agent errors reuse `MODEL_UNAVAILABLE` for configuration/transport/capability failures and `OUTPUT_SCHEMA_INVALID` for malformed structured output; internal gateway errors retain typed causes without exposing raw prompts, credentials, or provider response bodies.

A local endpoint that is remote, has no matching model, exceeds its configured bounds, times out, or produces an invalid action is rejected before a successful answer is returned. The existing OpenAI route remains available only when explicitly selected by `MODEL_PROVIDER=openai`.

## Provider Comparison

### `ProviderComparisonReport`

The report records the frozen case-set ID and SHA-256, the versioned agent prompt (`agent-v1` or `agent-v2`), creation time, platform, provider/model/route/runtime descriptors, and one result per provider/case pair. Each result includes the retrieval `index_version` returned by that run (null when the case was skipped). A result's `status` is `succeeded` only when the response status matched the frozen case's expected status; it also records observed tool selection, argument validity, structured validity, latency, available token usage, groundedness, answer quality, memory, and cost. Numeric quality metrics are only populated when a defined evaluator or human review produced them; otherwise they are `not_measured`. Memory/cost are `not_measured` when the platform/provider does not expose defensible measurements. Failed/skipped cases and limitations remain in the report. `live_requests_made` is true when the selected provider was probed or invoked; default skipped reports do not make provider requests.

Summary structured-validity and tool-selection rates are pooled across attempted provider/case rows; tool selection is correct when the observed boolean matches the frozen case's `requires_tool` label. Latency is the arithmetic mean of measured rows, memory is the maximum only when every attempted row has a measurement, and cost is the sum only when every attempted row has a measurement. Groundedness and answer quality average reviewed numeric scores; otherwise they remain `not_measured`.
