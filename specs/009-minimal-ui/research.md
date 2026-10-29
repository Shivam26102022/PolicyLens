# Feature 009 Research

## Decisions

### Multi-view research workbench

**Decision**: Use the existing React/Vite application with a shared application shell and explicit Research, Evaluations, Architecture, and Settings/System Status views. Use React Router because the views are distinct navigable destinations. Use Lucide icons for navigation and controls. Keep request and preference state local to the frontend; do not add a global state service.

**Rationale**: This gives researchers clear navigation between daily work, results, and explanatory content without adding a deployable service or a broad design-system dependency. The existing app is too small to justify a separate data-state framework.

**Alternatives considered**: One long dashboard page was rejected because chat, run metrics, and architecture reference content have different tasks and would become difficult to scan. A separate application/service was rejected by the constitution's minimal-service-complexity requirement.

### Configured provider selection and consent

**Decision**: Add a read-only model-options contract that reports only configured provider/model identifiers and safe availability state. Extend agent requests with a selected provider and an explicit per-request external-processing consent flag. Build/cache runtimes for validated configured providers; reject unsupported or unavailable selections and never fall back. Keep API keys and endpoint credentials server-side. Only the OpenAI option requires external-processing consent; the UI asks for it for each run and does not persist it.

**Rationale**: The current capability endpoint reports only the server-selected provider, and the answer route caches one runtime. A selector without request-level routing would misrepresent behavior. Per-run consent is the smallest safe change that makes the requested choice real while preventing accidental external transmission.

**Alternatives considered**: A client-only provider preference was rejected because it would not affect the backend runtime. A global mutable server setting was rejected because concurrent browser sessions could race and silently change one another's provider. Arbitrary browser-supplied model IDs and endpoints are rejected; users may choose only backend-configured models.

### Responses API route, usage, and safe summary

**Decision**: Use the OpenAI Responses API for the standard OpenAI endpoint. Keep custom Foundry-compatible endpoints on Chat Completions by default; expose an explicit server-side `OPENAI_USE_RESPONSES_API` opt-in for deployments whose endpoint is confirmed to support Responses. Record the SDK's aggregate provider usage and show token counts, route, and effort with each answer. Request the SDK-provided summary only for the official Responses endpoint with non-`none` reasoning effort, then expose only `summary_text` items from typed reasoning output. Custom Responses-compatible endpoints receive the selected reasoning effort without the optional summary request, which is an additional deployment-specific capability.

**Rationale**: The selected deployment's Chat Completions route advertises only `none` and does not provide Responses SDK reasoning summaries. Provider usage was already available from the SDK but was not surfaced by the frontend. Route-level reporting and explicit unavailability messages avoid implying that summaries or token counts exist when they were not returned.

**Alternatives considered**: Enabling Responses for every custom endpoint was rejected because compatibility is deployment-specific. Displaying private reasoning content or synthesizing a summary from hidden content is prohibited. Zero-filling missing usage was rejected because it would misrepresent an unmeasured value.

### Read-only evaluation summary

**Decision**: Add one versioned backend summary endpoint that validates the existing evaluation, review, and error manifests and returns selected run metadata, aggregate metrics, coverage, and limitations. Do not return prompts, per-case raw results, artifact filesystem paths, or credentials. The UI does not launch or mutate runs.

**Rationale**: Evaluation output is currently local manifest data and must not be read directly by the browser. An allow-listed summary preserves the backend trust boundary and makes `null`, blocked, empty, and measured states explainable.

**Alternatives considered**: Serving raw manifest files or reading local JSON from frontend code was rejected because the frontend must not access source/manifests directly. Starting evaluations from the page was rejected because it would introduce provider/resource side effects outside the controlled runner.

### Architecture and memory explanation

**Decision**: Maintain a versioned, data-driven architecture guide in frontend source and link to the corresponding repository documents. Every layer includes responsibility, flow, trust boundary, and implementation state. Describe the `AgentRunLedger` and current-run retrieval registry as request-scoped; explicitly state that PolicyLens does not provide persistent conversational memory.

**Rationale**: Existing system state tracks one bounded agent run and current-run evidence; it is not a cross-session memory store. Documentation must reflect observed behavior and separate implemented, configured, planned, and unavailable capabilities.

**Current implementation note**: Feature 011 subsequently added persisted sessions, five-exchange server-owned hot context, and optional workspace-scoped Chroma memory. The browser-only context decision above is historical Feature 009 behavior; the active system behavior is documented in `specs/011-session-memory/`.

**Alternatives considered**: Calling the run ledger a persistent memory layer was rejected as inaccurate. Rendering repository Markdown or model/source-provided HTML in the browser was rejected because untrusted HTML must remain text.

### Testing and accessibility

**Decision**: Reuse Vitest and React Testing Library for components and add Playwright browser tests with mocked backend responses. Keep tests deterministic and offline. Test with keyboard navigation and responsive widths down to 320 CSS pixels, and include reduced-motion behavior.

**Rationale**: The API is local-only and existing frontend tests already use Vitest. Browser tests can exercise cross-view interactions and consent without model-provider calls.

**Alternatives considered**: Live OpenAI/MLX tests were rejected for normal UI verification because they require external consent, credentials, and model availability.

## Existing Evidence

- `GET /model/capabilities` returns the configured provider's model/capabilities and does not expose credentials, but does not enumerate alternate configured providers.
- `POST /agent/answer` currently has no per-request provider selection; `AgentRuntime` uses `AppSettings` and the API caches one runtime.
- `AppSettings` contains server-side OpenAI/MLX settings; MLX configuration is validated as loopback-only when selected.
- `AgentAnswerResponse` contains answer claims/citations, calculations, uncertainty, conflicts, limitations, provider/model, trace ID, and safe lifecycle/tool events.
- `/health/ready` reports component states for API, generation, embedding/retrieval, and MCP without detailed infrastructure values.
- Feature 007 evaluation, review, and error results are local versioned JSON manifests; reports include blocked runs, missing metrics, and limitations.
- `AgentRunLedger` records bounded state transitions and safe events. `RetrievalRunRegistry` is bounded and scoped to current-run citation validation; neither implements persistent user conversation memory.

## Constraints

- Only backend-declared configured model IDs may be selected.
- The browser never receives provider credentials, local manifest contents, source files, or raw backend file paths.
- Evaluation status and missing metric values must remain explicit; unavailable is not zero.
- No component may display chain-of-thought or treat model/source/MCP content as trusted markup.
- Only provider-reported usage and SDK `summary_text` may be displayed; private reasoning content is never included.
- A custom endpoint remains on Chat Completions unless an operator explicitly enables Responses after confirming endpoint compatibility; no automatic API-route fallback is allowed.
- No new service, production authentication, or automatic provider fallback is added.
