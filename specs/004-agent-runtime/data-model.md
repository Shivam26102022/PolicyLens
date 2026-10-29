# Feature 004 Data Model

## Request and Run

### `AgentAnswerRequest`

Uses the Feature 003 retrieval request fields: `schema_version`, bounded `query`, retrieval `mode`, `top_k`, and restrictive `filters`. The caller cannot choose a provider, model, prompt, tool, permission scope, index, or filesystem path.

### `AgentRunContext`

Request-scoped internal state containing `run_id`, `trace_id`, current state, the current Feature 003 `RetrievalRun`, accepted Feature 005 adapter results, calculation records, tool/retry counters, start time, and bounded safe events. It is not persisted. Query text, prompts, tool arguments/results, evidence bodies, credentials, and private reasoning are excluded from events.

### `AgentRunState`

Finite states: `received`, `validated`, `retrieving`, `assessing`, `tool_execution`, `output_validation`, `citation_validation`, and terminal `answered`, `clarification_required`, `abstained`, `conflict`, `blocked`, or `failed_safe`. Transitions are host-owned; model output cannot set or skip a state.

## Evidence and Tools

### `AgentClaim` and `AgentCitation`

An `AgentClaim` has a stable `claim_id`, bounded factual `text`, zero or more server-derived citations, and zero or more `calculation_ids`. Corpus-derived text may summarize or paraphrase evidence; each attached citation must contain an exact excerpt validated with Feature 003's `CitationValidator`, and its source metadata is derived by the host. This validator proves quote and provenance integrity, not semantic entailment, so the UI exposes the excerpt for review. A calculation-derived claim must reference a validated calculation record, and its final text is rendered by the host from the validated operation and rows rather than trusted from the model. The model cannot author source metadata or citations.

`AgentCitation` is the existing Feature 003 `Citation` contract: source/title/URI, passage ID, location or row key, exact excerpt, source hash, retrieval rank/score, and retrieval mode.

### `StatisticsQueryRequest`, `StatisticsToolResult`, and `CalculationRecord`

The adapter request mirrors Feature 005's draft `query_statistics` interface: a validated indicator, geography set, bounded year range, supported aggregation, grouping, and row limit. The adapter result is schema-versioned and contains result rows, calculation operation/formula/rounding, evidence source IDs and input row keys/hashes, warnings, and a stable error code. Feature 004 validates the adapter result and records a `CalculationRecord` with a server-generated calculation ID and tool-call ID. The model may reference the calculation ID but cannot alter its result, formula, or source-row provenance.

Only the `query_statistics` adapter is exposed to the agent. Feature 005 owns its production MCP implementation and server identity. Feature 004 tests use a fake adapter implementing the same typed protocol. Transient retries are bounded and counted; invalid arguments, malformed output, permission errors, and non-transient failures are never blindly retried.

## Output and Observability

### `AgentAnswerResponse`

The versioned response includes `run_id`, `trace_id`, terminal status, optional concise answer, claims, validated calculations, uncertainty, conflict sides, one optional clarification question, limitations, provider/model/prompt/index identity, safe events, and an optional stable error code. Status invariants:

- `answered` requires at least one claim; each corpus-derived claim has valid current-run citations, and each calculation-derived claim references a validated calculation record.
- `clarification_required` requires one focused question and no unsupported claims.
- `abstained` requires an evidence-based reason.
- `conflict` presents both supported sides and their citations.
- `blocked` and `failed_safe` return no unsupported answer claims and include a stable error code.

### `AgentTraceEvent`

An event contains monotonic sequence, timestamp, state, event name, status, optional safe tool name/call ID, duration, retry count, and stable error code. Events never contain model prompts, model input/output, tool arguments/results, retrieved passage text, user query, secrets, or chain-of-thought. SDK tracing is disabled; the host builds these events from state transitions and SDK lifecycle callbacks.

## Lifecycles

1. Validate request and configuration, then create a run/trace ID.
2. Retrieve evidence through Feature 003 and register it for current-run citation validation.
3. Assess evidence and either clarify/abstain/conflict or run the single bounded agent.
4. If the allow-listed tool is requested, enforce budgets, call the typed adapter, validate the result, and record deterministic calculation provenance.
5. Validate structured output, references, citations, status invariants, and response size.
6. Return a terminal response and sanitized event list; discard request-scoped internal state.