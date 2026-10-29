# Feature 005 Traceability

This matrix maps each Feature 005 requirement and acceptance/success criterion to implementation evidence and a repeatable local check. All commands below use local fixtures, local canonical files, fake peers, or the local stdio server; none makes a live Foundry or external data-provider request.

## Requirements

| ID | Implementation/evidence | Verification |
|---|---|---|
| MCP-005-01 | `services/mcp-policy-data/src/policylens_mcp/server.py` registers one read-only tool and one read-only resource; stdio discovery checks the exact set. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_startup.py`; `uv run --locked --package policylens pytest apps/backend/tests/integration/test_mcp_protocol.py` |
| MCP-005-02 | Typed server and host models; both boundaries validate; the host uses bounded stdio sessions, timeout/cancellation, and stable errors. Statistics and catalog paths reject traversal and symlink redirection. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_statistics.py services/mcp-policy-data/tests/test_passages.py`; `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py` |
| MCP-005-03 | `MCPServer.run()` is stdio-only; backend settings reject no alternative transport and no public MCP listener is added. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_settings.py services/mcp-policy-data/tests/test_startup.py`; source inspection of `services/mcp-policy-data/src/policylens_mcp/server.py` |
| MCP-005-04 | Host checks pinned identity, tool/resource allow-list, and schema hashes; passage responses carry `untrusted=true`; resource text never changes client capabilities. | `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py`; `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_passages.py` |
| MCP-005-05 | Calculations are deterministic and read-only; the client itself does not retry, and the existing Feature 004 executor owns explicit transient retry policy. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_statistics.py`; `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py apps/backend/tests/unit/test_agent_tools.py` |
| MCP-005-06 | Statistics loader checks the exact two IDs, registry `allowed_usage`, public sensitivity, verified licence, source hashes, and modeled-estimate attribution; Feature 002 runtime validation accepts only declared usage values. | `make data-verify`; `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_statistics.py`; `python3 scripts/check_traceability.py` |
| MCP-005-07 | Backend exports exact active passage IDs from validated memory; MCP reads only the bounded, non-symlinked catalog and active pointer and rejects stale versions. | `make retrieval-verify`; `uv run --locked --package policylens pytest apps/backend/tests/unit/test_retrieval.py scripts/tests/test_mcp_passage_export.py`; `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_passages.py` |
| OBS-005-01 | Both JSON formatters whitelist server identity/version, operation, argument hash, status, duration, trace ID, and safe error code; raw arguments, results, and text are omitted. | `uv run --locked --package policylens pytest apps/backend/tests/unit/test_logging.py apps/backend/tests/unit/test_mcp_client.py`; `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_logging.py` |
| ADR-005-01 | Local comparison harness uses identical requests through the stdio adapter and direct deterministic function; measured results and limitations are recorded in [ADR-005-01](../../docs/architecture/adr/ADR-005-01-mcp-vs-direct.md). | `uv run --locked --package policylens pytest scripts/tests/test_mcp_comparison.py`; `uv run --locked --package policylens python scripts/evaluate_mcp_direct.py --repeats 3` |

## Acceptance Scenarios

| ID | Verification evidence | Command |
|---|---|---|
| AC-005-01 | Deterministic rows, operation/formula/rounding, row keys, raw/canonical hashes, attributions, and modeled caveat. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_statistics.py` |
| AC-005-02 | Unknown indicators, unsupported aggregation/grouping, invalid ranges, row overflow, non-finite values, malformed registry/manifest, and stable typed errors. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_statistics.py` |
| AC-005-03 | Exact passage ID, bounded verbatim text, provenance/location, checksum, licence, sensitivity, usage, and untrusted marker. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_passages.py`; `uv run --locked --package policylens pytest scripts/tests/test_mcp_passage_export.py` |
| AC-005-04 | Unknown, malformed, traversal-shaped, oversized, checksum-invalid, and stale-index resource requests fail safely. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_passages.py` |
| AC-005-05 | Real stdio server identity/version/protocol and exact tool/resource discovery; host compares both schema fingerprints. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_startup.py`; `uv run --locked --package policylens pytest apps/backend/tests/integration/test_mcp_protocol.py` |
| AC-005-06 | Wrong identity, unknown capability, schema mismatch, timeout, malformed result, and permission failures map to stable host errors without automatic fallback. | `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py` |
| AC-005-07 | Instruction-like passage content is returned only as a typed passage with `untrusted=true`; it does not expand the host tool allow-list. | `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py` |

## Success Criteria

| ID | Evidence | Command |
|---|---|---|
| SC-005-01 | Schema-valid statistics and resource responses with complete provenance; real local adapter smoke check. | `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py scripts/tests/test_mcp_passage_export.py`; `make mcp-health` |
| SC-005-02 | Invalid inputs, stale catalogs, mismatched identity/schema, timeout, unavailability, and malformed responses fail closed. | `uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests`; `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py` |
| SC-005-03 | Capability discovery is exact and MCP content stays untrusted; no provider fallback is introduced. | `uv run --locked --package policylens pytest apps/backend/tests/unit/test_mcp_client.py apps/backend/tests/unit/test_agent_tools.py apps/backend/tests/integration/test_mcp_protocol.py` |

## Final Gates

```bash
make format-check-python
make lint-python
make typecheck-python
make test-python
python3 scripts/check_traceability.py
```

## Recorded Verification

Verified on 2026-10-26:

| Gate | Result |
|---|---|
| Backend tests | 149 passed |
| MCP service tests | 37 passed |
| Script tests | 49 passed |
| Python Ruff lint | Passed for backend/scripts and MCP |
| Python mypy | Passed for 74 backend/script files and 13 MCP files |
| Python formatting | Passed for 74 backend/script files and 13 MCP files |
| `make data-verify` | All six registered source files verified |
| `make retrieval-verify` | Active index ready; version `45935afc940a7489563a38c32bbac909b0d8e6a9fb58182fb5c14e86ff130ea4` |
| `make mcp-health` | Ready |
| `scripts/check_traceability.py` | Passed: 67 global requirements, 14 Feature 001 requirements, 11 acceptance criteria, 5 success criteria, 10 demo scenarios |
| MCP/direct comparison | Three fixtures passed contract and result parity; local-only latency details are in ADR-005-01 |

Live Foundry/production behavior remains unverified by this feature. The comparison in ADR-005-01 is local, deterministic, and limited to three fixtures with three repetitions each.