# Feature 004 Research

## Decisions

### OpenAI Agents SDK integration

- Use the locked `openai-agents==0.24.0` package already present in the backend. Its installed API exposes `Agent`, `Runner.run`, `RunConfig`, `function_tool`, `OpenAIProvider`, and `OpenAIResponsesModel`; `Runner.run` accepts `max_turns`, and `RunConfig` supports disabling SDK tracing.
- Use one `Agent` with typed Pydantic output and a single allow-listed deterministic tool wrapper. Do not add handoffs or an agent swarm.
- Use a per-run `OpenAIProvider` built from an `AsyncOpenAI` client. Configure bounded HTTP timeout, zero implicit client retries, explicit model identity, and structured output. For an OpenAI-compatible custom endpoint, select the Chat Completions interface for compatibility; use the default Responses interface for the standard OpenAI endpoint.
- Enforce the total run timeout with host-side cancellation in addition to SDK turn and tool budgets. SDK traces are disabled; the application emits its own allow-listed event summaries and never records prompts, tool arguments/results, evidence bodies, credentials, or private reasoning.

### Provider configuration

- `OPENAI_DEPLOYMENT_MODEL`, when present, is the deployment identifier used by the agent. Otherwise use `OPENAI_MODEL` for the standard OpenAI route. `OPENAI_BASE_URL` is an optional OpenAI-compatible endpoint used for Foundry; it is a URL setting, not a credential. `MODEL_PROVIDER` must explicitly be `openai`; no MLX or other fallback is added in Feature 004.
- Keep the provider endpoint, deployment ID, API key, and model configuration backend-only. Tests inject a fake client and never make live requests. Live Foundry verification remains optional and requires the user-configured endpoint and credentials.

### MCP tool boundary

- Feature 005 defines the draft deterministic `query_statistics` contract and owns the production MCP process, server identity, and capability lifecycle. Feature 004 defines a narrow typed adapter protocol and an agent-facing function tool, with fake adapters in unit/integration tests. It does not implement or launch the production Feature 005 server.
- Only `query_statistics` is exposed to the model. Validate arguments and returned data against typed contracts, apply the run-wide tool-call budget before invocation, and retry only explicitly transient adapter errors within a finite retry budget.
- Corpus claims may be concise paraphrases. The runtime binds every citation to a current-run passage, replaces a model excerpt hint that is not an exact bounded substring with exact text from that same passage, and derives source metadata on the host. This avoids failing a complete answer because of quote-copying errors without accepting citations to unreturned passages or mismatched provenance. The verifier does not prove that a paraphrase is semantically entailed by its passage, so the UI must keep the linked evidence easy to inspect and the prompt must prohibit adding unsupported facts. For calculations, discard model-authored claim wording and render a deterministic summary from the validated tool result.

### State, output, and traces

- The host owns an explicit run state machine: request validation, retrieval, evidence assessment, optional tool execution/validation, output validation, citation validation, and terminal outcome.
- Return a versioned typed response with a trace ID, provider/model/prompt identity, safe state/tool events, claim-linked citations, and a stable terminal error. Store run traces only in memory for the response; do not persist hidden reasoning or raw query/evidence content.
- Use the existing Feature 003 non-agent baseline for the same query/evidence slice. A comparison report must distinguish deterministic/mocked checks from any live model evaluation and must not claim agent value without measured results.

## Verification Basis

- Inspected the installed `openai-agents==0.24.0` signatures for `Agent`, `Runner.run`, `RunConfig`, `function_tool`, `OpenAIProvider`, `OpenAIResponsesModel`, `RunHooks`, and `MCPServerStdio` without making a network request.
- Feature 004 uses existing FastAPI/Pydantic/OpenAI SDK dependencies; no new service or dependency is planned.
- The repository currently has no Feature 005 MCP tool implementation. Feature 004 adapter tests therefore use fakes until Feature 005 supplies the production server.