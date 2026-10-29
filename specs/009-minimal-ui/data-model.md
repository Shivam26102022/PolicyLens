# Feature 009 Data Model

## ModelOption

A safe description of a provider/model configured by the backend. Fields: provider (`openai` or `mlx`), selected API route, configured model ID, processing scope (`external` or `local`), configuration status (`configured` or `not_configured`), selected-by-default flag, supported reasoning efforts, and whether per-run external-processing consent is required. Never contains a credential, raw endpoint URL, or arbitrary user-provided model ID.

## AgentProviderSelection

Per-request selection carried with the answer request. Fields include provider, external-processing consent boolean, reasoning effort, bounded prior conversation, question, retrieval mode, filters, and top-k. Reasoning effort must be advertised for the selected route. If provider is OpenAI, consent must be true on every turn; if the selection is unconfigured or consent is absent, the request is rejected before provider invocation. Local MLX remains loopback-only. Provider selection never triggers fallback.

## Conversation Context

An ordered sequence of user/assistant messages sent explicitly by the browser with a follow-up request. The request accepts at most 8 messages, 4,000 characters per message, and 12,000 characters total. It exists only in browser memory, is cleared with the conversation or on reload, and is untrusted context rather than evidence. The backend does not persist it or rely on provider-managed conversation IDs.

This describes the original Feature 009 contract. Feature 011 supersedes it in the current application with persistent server-side sessions and at most five completed exchanges of hot context; see `specs/011-session-memory/data-model.md`.

## AgentProgressEvent

A typed operational event delivered over the answer SSE stream with sequence, state, event type, status, optional approved tool name, duration, safe error code, retry count, optional model route/effort, provider-reported token usage, and optional SDK summary text. The UI maps it to reviewed labels. It excludes private reasoning content, prompts, raw tool arguments, and evidence payloads.

## ResearchRunSummary

Per-answer state for one submitted request: run/trace IDs, submitted question, selected provider/model and route, reasoning effort, status, answer, claims/citations, calculation records, limitations, safe activity events, optional provider usage, optional SDK summary text, and timestamps. Session persistence and reload behavior are owned by Feature 011; unavailable usage and summaries remain explicitly unavailable. Private reasoning content is never stored in the visible trail.

## EvaluationSummary

Read-only API response composed from validated local manifests. Contains case-set coverage (case/review counts, per-category counts, and dev/test counts), run summaries (run ID, status, timestamps, split, case count, selected aggregate metrics, `live_requests_made`, and limitations), scored-review count, and error-record count. Null or unavailable metrics remain null/unavailable; raw questions, case prompts, reference claims, full results, credentials, and local artifact paths are excluded.

### EvaluationMetricSummary

An allow-listed subset of existing aggregates: retrieval recall@k, nDCG@k, expected-behavior accuracy, citation correctness/completeness, groundedness, answer relevance, p50/p95 latency, estimated cost, and measured case count. Values may be null when not measured.

## ArchitectureLayer

Static, reviewed explanatory content with stable ID, title, plain-language purpose, inputs/outputs, trust boundary, implementation state (`implemented`, `configured`, `planned`, `unavailable`), and references to repository documentation. It is not populated from untrusted model/source content.

## ExamplePrompt

Reviewed query text plus an optional reviewed PDF source ID. Clicking an example copies its text and source scope into the composer without submitting a request. Editing the question clears that scope.

## State Boundaries

- Provider credentials and provider endpoints remain in backend configuration.
- The model-options endpoint reports identifiers/configuration state only.
- Consent is attached to the individual OpenAI request and is not persisted in browser storage.
- Recent runs and selected provider preference may exist only in browser memory or non-sensitive local preference storage; they are not server-side conversation memory.
- Follow-up messages are browser-memory-only and bounded; every run independently retrieves and validates evidence, and every OpenAI run requires fresh consent.
- These two browser-only conversation statements are historical Feature 009 behavior. Feature 011 owns current session persistence and memory behavior.
- Evaluation data is summarized by the backend from validated manifests and is never read from local files by the frontend.
