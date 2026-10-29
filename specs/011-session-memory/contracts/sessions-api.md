# Sessions API Contract

All endpoints are served by `policylens-api`. Every request requires `X-Workspace-ID` containing a canonical UUID. The value scopes this local workspace; it is not authentication. Responses use JSON and `schema_version: "1.0"`. The browser never connects directly to SQLite, Chroma, or an embedding provider. Persistent session creation and turns require a recorded data-use acknowledgement that only public, synthetic, or appropriately anonymized content will be stored.

Literal routes such as `/sessions/preferences` and `/sessions/memories` MUST be registered before dynamic `/{session_id}` routes so they cannot be interpreted as session identifiers.

## List Sessions

`GET /sessions?limit=50&before=<cursor>`

- `limit`: optional integer, default 50, maximum 50.
- `before`: optional opaque cursor returned by the prior page.
- Returns the workspace's sessions newest-updated first, without transcript content.

```json
{
  "schema_version": "1.0",
  "sessions": [
    {
      "session_id": "uuid",
      "title": "Compare employment estimates",
      "created_at": "2026-10-27T12:00:00Z",
      "updated_at": "2026-10-27T12:05:00Z",
      "turn_count": 2
    }
  ],
  "next_cursor": null
}
```

## Create Session

`POST /sessions`

- Creates an empty session in the supplied workspace.
- Returns `201 Created` with a `SessionSummary`.
- An empty session title is `New conversation`.
- Returns `403 DATA_USE_ACKNOWLEDGEMENT_REQUIRED` unless the workspace has recorded the required data-use acknowledgement.

## Read Session History

`GET /sessions/{session_id}?limit=100&before_turn_id=<uuid>`

- `limit`: optional integer, default 100, maximum 100.
- Returns the session summary and one page of turns ordered oldest-to-newest.
- `next_before_turn_id` is the cursor for loading older turns; it is null when no older page remains.
- Each turn includes its saved response when available. It does not expose vector records or hidden model reasoning.
- Missing and cross-workspace IDs both return `404 SESSION_NOT_FOUND`.

## Delete Session

`DELETE /sessions/{session_id}`

- Removes all associated long-term vectors and then deletes the transcript.
- Returns `200` with `{"schema_version":"1.0","session_id":"uuid","deleted":true}` only after both operations succeed.
- Returns `404 SESSION_NOT_FOUND` for missing or cross-workspace IDs.
- Returns a stable `503` error if vector or transcript deletion fails; the UI must not claim success.

## Memory Preference

`GET /sessions/preferences`

Returns the current acknowledgement and memory preference. A new workspace defaults to `data_use_acknowledged: false` and `long_memory_enabled: false`.

`PUT /sessions/preferences`

```json
{
  "schema_version": "1.0",
  "data_use_acknowledged": true,
  "long_memory_enabled": false
}
```

The acknowledgement records the user's confirmation that only public, synthetic, or appropriately anonymized content will be stored and that restricted or identifiable private content must not be stored. Enabling long-term memory without acknowledgement is rejected. When `long_memory_enabled` is false, no long-term vectors are retrieved or written; existing vectors remain until deleted.

## Clear Long-Term Memory

`DELETE /sessions/memories`

- Deletes all memory records matching the current workspace. If the collection identity is incompatible, it can be reset only when no other workspace records would be affected.
- Leaves all sessions and transcript turns intact.
- Returns `200` with `{"schema_version":"1.0","status":"cleared","deleted_count":3}` only after deletion succeeds.
- Returns a stable `503` error on failure.

If the current embedding provider/model/dimension does not match the existing memory collection, retrieval reports `embedding_mismatch` and writes fail closed. Clearing can remove an incompatible collection only when it can prove that no other workspace records would be affected; a replacement collection is created lazily on the next consented memory-enabled write. No automatic re-embedding is performed.

## Data-Use Acknowledgement

Session creation and session-backed agent turns return `403 DATA_USE_ACKNOWLEDGEMENT_REQUIRED` until `data_use_acknowledged` is true for the workspace. The frontend must present the acknowledgement before creating a session; clearing data remains available without acknowledgement.

## Errors

Errors use the existing PolicyLens API envelope:

```json
{
  "schema_version": "1.0",
  "error_code": "SESSION_NOT_FOUND",
  "message": "The requested session is unavailable."
}
```

Workspace header errors, invalid UUIDs, and malformed pagination values return a client error. Error messages must not disclose whether a session exists in another workspace or include stored transcript text.
