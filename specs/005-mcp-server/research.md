# Feature 005 Research

## Decisions

### MCP server and transport

- Keep the existing `policylens-mcp` package and `MCPServer` identity. Use pinned `mcp==2.3.0` decorators for one structured-output `query_statistics` tool and one URI-template passage resource. Keep stdio as the only transport for this local feature.
- Runtime tool/resource lists are exactly the approved capability set. The host checks server identity, tool names/input schemas, resource template, and schema version before use; unknown or mismatched capabilities fail closed.
- No authentication or public HTTP listener is added. The process reads approved local data and snapshots only; it does not access arbitrary paths or Chroma.

### Statistics data access

- Read the YAML source registry and ingestion manifest, then resolve a canonical structured JSON file only for sources whose registry `allowed_usage` includes `statistics`, whose licence review is verified, and whose sensitivity is public. Verify the raw input hash, canonical output hash, parser status, and source identity before loading observations.
- The initial allow-list is exactly the two user-approved World Bank Indicators API sources. Their values remain modeled ILO estimates. Return ILOSTAT and World Bank Data attribution and the non-national-estimate caveat with every result. Do not expose PDF/report content through `query_statistics`.
- Use deterministic Python aggregation over typed observations; no SQL, dynamic expressions, or LLM-computed arithmetic. Ignore null values for aggregations and report the omitted count as a warning; preserve nulls for unaggregated rows. Reject non-finite values, unsupported groups/aggregations, invalid ranges, excessive source rows, and result overflow.
- A successful tool result includes the normalized query, ordered output rows, operation/formula/rounding, source IDs, row keys, source hashes, attribution, and caveats. Tool errors use a small stable taxonomy and do not leak filesystem paths or source payloads.

### Passage resource and Chroma boundary

- The resource must use the exact passage IDs, text, and provenance from the active Feature 003 index. The MCP process MUST NOT open Chroma.
- Add a narrow read-only `RetrievalService` export that returns its already-validated in-memory passage records. A backend CLI writes a versioned JSON passage catalog atomically, including the active `index_version` and record content hashes. The MCP process loads this bounded catalog and checks its index version against the active pointer before serving resources.
- Resolve resource URIs by exact in-memory catalog lookup. Validate source IDs and the `sha256:<hex>` passage ID format; never convert caller-controlled IDs to filesystem paths. Return bounded verbatim text and complete source/location/hash/licence/sensitivity metadata plus `untrusted: true`.
- A missing, stale, malformed, or checksum-invalid catalog fails resource reads closed. Rebuild the export after the retrieval index changes.

### Backend MCP host/client

- Implement a request-scoped async stdio client using the repository's pinned MCP SDK. Enforce the configured MCP timeout, cancellation, expected server identity, exact capability allow-list, and both input/output Pydantic validation.
- The Feature 004 adapter will call only `query_statistics` through this host client. MCP error results map to the Feature 004 stable taxonomy; no automatic provider/tool fallback is added.
- Log only server identity/version, tool/resource name, argument hash, status, duration, and trace ID. Never log tool arguments, result rows, passage text, tokens, prompts, or credentials.

### Evaluation and comparison

- Compare MCP with a thin direct-call adapter on the same deterministic request fixtures for contract parity, results, and measured local latency. Preserve negative results and explain that the MCP server is required by the assignment; do not claim that MCP is intrinsically higher quality.
- Unit/protocol tests use fixtures and no live external calls. The existing public sources permit deterministic regression tests locally.

## Verification Basis

- Inspected the installed `mcp==2.3.0` APIs: `MCPServer.tool`, `MCPServer.resource`, `run('stdio')`, `Client.list_tools`, `call_tool`, `list_resources`, and `read_resource`.
- Inspected Feature 002 source registry, ingestion manifest, and canonical `StructuredDataset`/`CanonicalDocument` layouts.
- Inspected Feature 003 retrieval loading: passage records are already materialized and validated in `RetrievalService`, but there is no public passage-export API. The approved JSON catalog bridge preserves exact indexed passage IDs without giving MCP direct Chroma access.
- The source schema now supports the `statistics` permission; only the two approved indicator source entries carry it. No new deployable service is planned.