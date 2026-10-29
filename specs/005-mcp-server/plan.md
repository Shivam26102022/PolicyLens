# Implementation Plan: Standalone MCP Service and Trust Controls

**Branch**: `005-mcp-server` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-mcp-server/spec.md`

## Summary

Implement the existing stdio MCP service with exactly one deterministic `query_statistics` tool and one bounded passage resource. The tool reads only the two source-registry entries explicitly permitted for `statistics`, validates current canonical hashes, computes aggregates in Python, and returns row-level provenance and attribution. For passage reads, the backend exports a versioned JSON catalog from the already-validated Feature 003 in-memory index; the MCP process reads only that snapshot and never opens Chroma. The backend client verifies server identity/capabilities and validates both sides of every contract.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Existing `mcp==2.3.0`; pin MCP server package version `0.1.0` and negotiated protocol version `2026-07-28`; add direct `PyYAML>=6,<7` dependency to the MCP package for source-registry parsing. Backend reuses FastAPI/Pydantic, Chroma, and BM25S dependencies already installed.

**Storage**: Read-only `data/manifests/sources.yaml`, `data/manifests/ingestion-manifest.json`, and content-addressed `data/canonical/` JSON for the approved statistics tool. A backend-owned ignored `data/indexes/mcp-passage-catalog.json` snapshot contains active `index_version` and bounded passage records. For passage lookups, MCP reads only this snapshot and `active-index.json`; it never opens Chroma or raw report paths.

**Testing**: pytest unit tests, direct server tests, backend host-client tests, and stdio subprocess integration/fault tests. Use temporary manifests/canonical fixtures and fakes; no network calls are required.

**Target Platform**: Python 3.12 on Linux and macOS; local stdio only.

**Project Type**: Existing standalone Python MCP process plus typed client integration inside the existing FastAPI backend and one backend-owned export script.

**Performance Goals**: No unmeasured latency SLO. Bound tool inputs to four geographies, 2015–2025, at most 44 source observations and result rows; bound passage payloads to 5,000 characters and MCP calls to `MCP_TIMEOUT_SECONDS`.

**Constraints**: Only `query_statistics` and the approved passage resource are discoverable. Statistics source IDs are allow-listed from registry `allowed_usage: statistics`; initial scope is the youth and total unemployment series. All computations are deterministic; nulls are never imputed. Include ILOSTAT/World Bank attribution and modeled-estimate caveat. Apply no automatic retries except a bounded explicit transient-error policy. Reject stale, malformed, unauthorized, or oversized data; no arbitrary paths, SQL, URLs, shell, or writes. Preserve exact Feature 003 passage IDs via a versioned export; the active index version must match.

**Scale/Scope**: Two approved structured sources (44 observations per indicator) and four report sources for passage reads. No public HTTP transport, authentication system, new service, or production write action is introduced.

## Constitution Check

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Tool results include row-level source provenance; resources return verbatim bounded passages marked untrusted. | PASS |
| II. Scientific Evaluation Before Complexity | Compare MCP and thin direct adapter on the same fixtures for contract parity/results/latency; do not claim intrinsic quality. | PASS |
| III. Bounded Agency and Deterministic Computation | Server tools are deterministic and bounded; retries, rows, payloads, and timeouts are finite. | PASS |
| IV. Secure MCP Trust Boundaries | Backend allow-lists identity/capabilities; server and host validate inputs/outputs; stale catalog and injection fail closed. | PASS |
| V. Provider Portability With Measured Parity | No generation provider/fallback changes are added. | PASS |
| VI. Reproducibility Is a Product Feature | Data hashes, index version, server/protocol versions, tool schema, and manifests are checked and recorded. | PASS |
| VII. Privacy and Responsible AI | Only public approved data is exposed; rights and modeled-estimate caveats are preserved; logs redact content. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | Reuse existing MCP process and backend; no fourth service or framework. | PASS |
| IX. Testable Specifications and Traceability | Protocol, permission, failure, and provenance criteria map to tests and quickstart commands. | PASS |
| X. Honest Reporting | Mocks and local comparisons are identified; no live/production identity claims are invented. | PASS |

## Project Structure

### Documentation

```text
specs/005-mcp-server/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── traceability.md
├── contracts/
└── tasks.md
```

### Source and Tests

```text
services/mcp-policy-data/src/policylens_mcp/
├── server.py
├── settings.py
├── models.py
├── statistics.py
└── passages.py
services/mcp-policy-data/tests/
├── test_statistics.py
├── test_passages.py
├── test_settings.py
└── test_startup.py
apps/backend/src/policylens/
├── retrieval/search.py
└── mcp/
    ├── client.py
    └── models.py
apps/backend/tests/
├── unit/test_mcp_client.py
└── integration/test_mcp_protocol.py
scripts/export_mcp_passages.py
scripts/evaluate_mcp_direct.py
scripts/tests/test_mcp_passage_export.py
scripts/tests/test_mcp_comparison.py
docs/architecture/adr/ADR-005-01-mcp-vs-direct.md
```

**Structure Decision**: Keep the MCP server independent, with no imports from backend internals. It reads approved canonical JSON and the backend-exported passage catalog. The backend owns Chroma and supplies a narrow, read-only in-memory passage iterator for the export script. The backend host uses the existing MCP SDK client over stdio and exposes only the allow-listed capability set.

## Complexity Tracking

No additional service or framework is required. The passage catalog is a derived export needed to preserve exact indexed IDs while respecting the rule that MCP must not own or open Chroma.
