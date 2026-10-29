# Feature Specification: Standalone MCP Service and Trust Controls

**Feature Branch**: `005-mcp-server`  
**Created**: 2026-10-24  
**Status**: Draft; depends on approved corpus  
**Input**: `POLICYLENS_MASTER_SPEC.md`, Section 9 and Section 20 Feature 005

## Product Outcome

The backend host can discover and call a narrow deterministic statistics tool and read an addressable source passage through an independent MCP process, while validating identity, schemas, permissions, timeouts, and untrusted output.

## Scope and Dependencies

Depends on Feature 002's approved structured dataset and Feature 003's active passage IDs. Owns the standalone Python MCP service, typed read-only tool/resource contracts, backend MCP lifecycle, capability allow-list, failure taxonomy, protocol tests, and MCP-versus-direct-call comparison. The initial `query_statistics` data allow-list is limited to the two World Bank unemployment indicator series. A backend-owned exporter provides MCP with a versioned JSON passage snapshot; the MCP process does not open Chroma. stdio is the local default.

## Clarifications

### Session 2026-10-26

- Q: May Feature 005's `query_statistics` expose only the two CC BY 4.0 World Bank indicator datasets, preserving ILO/World Bank attribution and the modeled-estimate caveat? → A: Yes. Limit it to those two series, include both attributions and the modeled-estimate caveat, and record statistics use in `allowed_usage`; do not expose report data through this tool.
- Q: May I add a read-only export from the validated Feature 003 index so MCP resources resolve the same passage IDs and citation provenance without MCP accessing Chroma? → A: Yes. The backend exports a versioned JSON snapshot; MCP reads it and verifies it matches the active index version.

## User Scenarios & Testing

### User Story 1 - Query Approved Statistics (Priority: P1)

As an analyst, I can request a bounded deterministic aggregation over approved challenge data with row-level provenance.

**Independent Test**: Compare tool results with a deterministic reference calculation and verify unknown indicators, out-of-range years, excessive rows, and non-finite values are rejected.

**Acceptance Scenarios**:

1. **AC-005-01** Given either explicitly approved unemployment indicator and bounded filters, When `query_statistics` runs, Then it returns schema-versioned rows, deterministic operation/formula/rounding, source IDs, row keys, checksums, warnings, and ILO/World Bank attribution with the modeled-estimate caveat.
2. **AC-005-02** Given invalid indicators, ranges, grouping, aggregation, or row limits, When the tool validates input, Then it returns a typed error without running arbitrary SQL.

### User Story 2 - Read a Source Passage (Priority: P1)

As a researcher, I can resolve an approved source/passage URI and inspect bounded verbatim text and provenance.

**Independent Test**: Read valid, unknown, malformed, and traversal-shaped identifiers and verify only approved bounded passage records can resolve.

**Acceptance Scenarios**:

1. **AC-005-03** Given a valid `policy://sources/{source_id}/passages/{passage_id}` URI, When it is read, Then the output contains stable IDs, bounded text, provenance/location, checksum, sensitivity, licence, and an untrusted-data marker.
2. **AC-005-04** Given an unknown or malformed identifier, When it is read, Then it fails with a stable safe error and does not access arbitrary paths.

### User Story 3 - Safely Discover and Call MCP (Priority: P1)

As a maintainer, I can verify the server identity, capabilities, and schemas and exercise timeouts and malformed responses.

**Independent Test**: Run the backend client against a known server and fault fixtures for wrong identity, unavailable process, timeout, and malformed output.

**Acceptance Scenarios**:

1. **AC-005-05** Given the expected server process, When the host connects, Then server name/version/protocol and capability schemas are checked against an allow-list before use.
2. **AC-005-06** Given an unknown server, invalid schema, timeout, or malformed result, When the host receives it, Then it fails closed with a stable error code and no automatic provider fallback.
3. **AC-005-07** Given MCP resource/tool content contains instructions, When a model consumes it, Then the content remains untrusted data and cannot change host policy or select additional tools.

## Functional Requirements

- **MCP-005-01**: Expose exactly the approved read-only statistics tool and bounded passage resource; do not expose shell, generic SQL, filesystem, URL-fetch, code execution, or write tools.
- **MCP-005-02**: Validate arguments and results at both server and host; enforce stable IDs, typed schemas, row/input/output bounds, timeout, cancellation, and error taxonomy.
- **MCP-005-03**: Use stdio by default. If a later approved deployment requires HTTP, bind to loopback locally and add the documented authentication/origin/body-limit controls.
- **MCP-005-04**: Apply the backend server allow-list and capability discovery; treat descriptions, annotations, resources, and tool output as untrusted.
- **MCP-005-05**: Keep operations read-only, deterministic, idempotent where applicable, and safe to retry only under explicit transient-error policy.
- **MCP-005-06**: `query_statistics` MUST only access sources whose registry `allowed_usage` contains `statistics`. Initial approval covers only `wb-youth-unemployment-1524-2015-2025` and `wb-total-unemployment-2015-2025`; results MUST retain ILO/World Bank attribution and identify values as modeled ILO estimates, not national estimates.
- **MCP-005-07**: Passage resources MUST use the exact Feature 003 passage IDs and provenance. The backend MUST export a versioned read-only JSON passage catalog from its validated in-memory retrieval service; the MCP process MUST NOT open Chroma and MUST fail closed if the catalog index version differs from the active pointer.
- **OBS-005-01**: Log server identity/version, tool name, argument hash, status, duration, and trace ID without raw credentials, private text, or sensitive arguments.
- **ADR-005-01**: Compare MCP with a thin direct-call adapter for interoperability, operational overhead, latency, debugging, trust, and versioning.

## Success Criteria

- **SC-005-01**: Valid tool/resource operations return schema-valid outputs with complete provenance.
- **SC-005-02**: Invalid input, wrong identity, timeout, unavailability, malformed output, and injection fixtures fail safely.
- **SC-005-03**: The host discovers only the approved capability set and never treats MCP output as instructions.

## Assumptions and Open Questions

- Passage resources may read only Feature 003 passages whose source registry permits retrieval; the statistics tool has its separate explicit `statistics` permission.
- No production authentication or public HTTP transport is required by the current local assessment target.
- Protocol/SDK versions are selected and pinned in the plan after contract verification.

## Out of Scope

Corpus ingestion (002), retrieval ranking/index ownership (003), agent orchestration (004), and final tool-activity UI (009).