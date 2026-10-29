# Feature 005 Data Model

## Approved Sources

### `StatisticsSource`

Resolved from `data/manifests/sources.yaml` plus the latest successful ingestion-manifest record matching the registry's raw SHA-256. Eligible only when `source_kind=structured`, `sensitivity=public`, `license_review_status=verified`, `allowed_usage` contains `statistics`, and the source ID/indicator are in the initial two-series allow-list. The canonical structured file must remain below `data/canonical/`, match its manifest SHA-256, and match the source ID, indicator ID, country set, and year range declared by the registry.

The initial approved sources are `wb-youth-unemployment-1524-2015-2025` (`SL.UEM.1524.ZS`) and `wb-total-unemployment-2015-2025` (`SL.UEM.TOTL.ZS`). Both carry CC BY 4.0 and require attribution to ILOSTAT and World Bank Data. Both contain modeled ILO estimates, which may be revised and must not be presented as national-estimate data. Reports and sources without `statistics` permission are ineligible.

### `StatisticsQueryRequest`

Contains `schema_version=1.0`, `indicator`, one to four unique uppercase ISO3 `geographies`, `start_year`, `end_year`, `aggregation` (`none`, `mean`, `sum`, `median`), unique `group_by` fields (`geography`, `year`), and `row_limit` (1–44). Years must be within the approved source range 2015–2025; the interval may not be reversed. For `aggregation=none`, `group_by` must be empty and each result row preserves a source observation. Aggregate operations group on the selected fields; an empty `group_by` creates one aggregate across the filtered observations. Omitted grouping fields are null in the result row. A sum returns percentage-point totals, not an unemployment rate. If the complete result exceeds `row_limit`, return `STATISTICS_ROW_LIMIT_EXCEEDED` rather than truncating rows or provenance. Calculations use decimal arithmetic; unaggregated values preserve source precision and aggregate results are rounded to six decimal places using `ROUND_HALF_EVEN`. The model cannot provide paths, SQL, URLs, arbitrary source IDs, or output expressions.

### `StatisticsResultRow` and `StatisticsToolResult`

A row contains nullable geography ISO3/name and year grouping values, nullable numeric value, unit, observation status, and decimal precision. Aggregate rows use `observation_status=aggregated`; unaggregated queries preserve source observation status. Results contain the normalized request, bounded ordered rows, deterministic calculation operation/formula/rounding, source ID, exact input row keys, raw-source SHA-256 and canonical-file SHA-256, explicit source attribution, and warnings. Aggregations ignore null observations and report their count; unaggregated queries preserve nulls. Non-finite input/output values are rejected. An empty filtered source selection returns a typed `STATISTICS_DATA_UNAVAILABLE` error. The result never reports more rows than `row_limit` or 44.

### `StatisticsToolError`

Stable error codes: `STATISTICS_SOURCE_NOT_ALLOWED`, `STATISTICS_INDICATOR_UNSUPPORTED`, `STATISTICS_INVALID_ARGUMENTS`, `STATISTICS_RANGE_INVALID`, `STATISTICS_ROW_LIMIT_EXCEEDED`, `STATISTICS_DATA_UNAVAILABLE`, `STATISTICS_DATA_INVALID`, and `STATISTICS_NON_FINITE_VALUE`. Errors contain a safe bounded message and no filesystem path, raw query, row data, or credentials.

## Passage Resource

### `PassageCatalog`

An ignored, atomically replaced JSON export produced by the backend from `RetrievalService`'s validated in-memory active passage map. It contains `schema_version`, `index_version`, build time, and passage records sorted by exact Feature 003 `passage_id`. The MCP process reads only this export, never Chroma. The exporter emits the exact Feature 003 `passage_id`, text, source metadata, locations/row key, content hashes, licence, sensitivity, permission scope, and `allowed_usage` containing `retrieval`.

The MCP service validates the catalog schema and every passage text SHA-256, then checks that `catalog.index_version` equals `data/indexes/active-index.json` at load and before resource reads. A missing/stale/malformed catalog fails closed. Catalog writes use a same-directory temporary file plus atomic replacement. The catalog is rebuildable derived data and is not committed.

### `PassageResourceRequest` and `PassageResourceResult`

The request is the URI `policy://sources/{source_id}/passages/{passage_id}`. `source_id` must resolve by exact registry/catalog lookup; `passage_id` must match `sha256:<64 lowercase hex>`. No user value is converted into a filesystem path. A result contains schema version, exact source/passage IDs, bounded verbatim passage text (maximum 5,000 characters), source title/publisher/URI, page/section or row key, source content hash, text hash, sensitivity, licence, usage constraints, and `untrusted=true`. Missing, disallowed, malformed, or oversized records return stable safe errors.

## Host/Server Contracts

### `MCPServerIdentity` and `AllowedCapability`

The host expects server name `PolicyLens Policy Data Server`, server version `0.1.0`, protocol version `2026-07-28` from pinned `mcp==2.3.0`, exactly the `query_statistics` tool, and the declared passage resource template. Startup discovery compares advertised names and JSON schemas with the committed contract before use. Additional/unknown capabilities fail closed.

### `MCPHostError`

Stable host errors include `MCP_UNAVAILABLE`, `MCP_TIMEOUT`, `MCP_IDENTITY_MISMATCH`, `MCP_CAPABILITY_MISMATCH`, `MCP_SCHEMA_INVALID`, `MCP_MALFORMED_RESPONSE`, `MCP_PERMISSION_DENIED`, `MCP_RESOURCE_NOT_FOUND`, `MCP_CATALOG_STALE`, `MCP_PASSAGE_MISMATCH`, and `MCP_INTERNAL_ERROR`. Tool retry is allowed only for explicitly transient transport errors, is bounded, and never retries invalid arguments or malformed results.

## Lifecycle

1. Load the source registry and ingestion manifest; resolve and checksum-verify only the two statistics-approved canonical datasets.
2. Load only rows matching the validated query and enforce geography/year/row bounds before computation.
3. Aggregate deterministically, retain exact row provenance, and construct a typed result with required attribution/caveats.
4. On MCP startup, validate server identity and tool/resource schemas; load the passage catalog and compare its index version to the active pointer.
5. Resolve resource URIs by exact in-memory catalog membership and return bounded verbatim metadata/text marked untrusted.
6. For each locally ranked passage selected for an answer, the backend host reads the exact source/passage IDs through the declared resource and verifies the returned text, hashes, and provenance against the active retrieval result before model execution; any mismatch fails closed. The host also validates arguments/results, applies timeouts/cancellation, records safe hashes/status/duration/trace IDs, and exposes no unapproved capability.