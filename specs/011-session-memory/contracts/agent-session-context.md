# Agent Session Context Contract

## Request

The existing `POST /agent/answer` and `POST /agent/answer/stream` contracts accept an optional `session_id` UUID and require the `X-Workspace-ID` header when a session is selected.

- If `session_id` is present, the backend validates that the session belongs to the workspace, saves the new user turn, loads at most the five most recent completed pairs, and retrieves at most five matching long-term memories when enabled.
- Session-backed requests are rejected until the workspace has acknowledged that persisted content is limited to public, synthetic, or appropriately anonymized data.
- The backend ignores caller-supplied `conversation` context for a session-backed request. The persisted transcript is authoritative.
- Requests without `session_id` retain the existing bounded explicit-context behavior for compatibility.
- Every answer turn still performs current corpus retrieval and citation validation.
- If an external model provider is configured, `allow_external_provider` must be true before question, history, or memory is sent to it. If an external embedding provider is configured, `allow_external_embeddings` must be true before any embedding request. Each approval is independent and applies only to the current turn.

## Safe Progress Events

The stream and response may contain these additional `AgentEvent.event_type` values:

| Event | Status | Safe fields |
|---|---|---|
| `session_context_loaded` | `succeeded` / `failed` | Sequence, state, duration, error code |
| `memory_retrieval_completed` | `succeeded` / `failed` / `skipped` | Sequence, state, duration, error code; no memory text |
| `session_turn_persisted` | `succeeded` / `failed` | Sequence, state, duration, error code |
| `memory_write_completed` | `succeeded` / `failed` / `skipped` | Sequence, state, duration, error code |

No event includes prompts, raw memories, hidden reasoning, or secret values.

## Model Context

The backend sends context under distinct untrusted fields:

```json
{
  "query": "the current question",
  "untrusted_conversation_context": [
    {"role": "user", "content": "a recent question"},
    {"role": "assistant", "content": "its saved response"}
  ],
  "untrusted_long_term_memory_context": [
    {"content": "a bounded prior conversation pair"}
  ],
  "untrusted_evidence": "passages retrieved for this run"
}
```

Long-term memory is not added to the current retrieval run's evidence collection, citation validator, tool arguments, or policy instructions. Only evidence retrieved for this run may support corpus claims.

## Session Result

When `session_id` is present, `AgentAnswerResponse` includes a `session_context` object:

```json
{
  "session_id": "uuid",
  "turn_id": "uuid",
  "persisted": true,
  "long_memory_enabled": true,
  "memory_retrieval_status": "used",
  "retrieved_memory_count": 2,
  "memory_write_status": "stored"
}
```

`memory_retrieval_status` is `used`, `empty`, `disabled`, `unavailable`, or `embedding_mismatch`; `memory_write_status` is `stored`, `skipped`, or `failed`. The response never returns raw memory documents. If memory retrieval fails, the answer may continue with hot context only and must expose `unavailable`; an embedding-identity mismatch must expose `embedding_mismatch`. If transcript persistence fails, `persisted` is false and the UI must clearly label the answer as unsaved.

The request carries the per-turn `allow_external_embeddings` consent flag separately from generation consent. It defaults to false. Model options disclose whether the configured embedding provider requires external-processing consent.
