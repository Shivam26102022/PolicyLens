# Feature 005 Quickstart

These checks are local and deterministic. They do not make external model or data-provider calls.

## Prerequisites

- Python 3.12 and `uv` installed.
- Repository dependencies synchronized from `uv.lock`.
- Feature 002 data verified before exercising statistics against the local corpus.
- Feature 003 active index verified before exporting or reading passages.

```bash
uv sync --locked --all-packages --all-groups
make data-verify
make retrieval-verify
```

## Build the Passage Snapshot

Export the active retrieval service's validated in-memory passage records. The exporter writes a derived, ignored catalog and fails if the active index is unavailable or the snapshot cannot be validated.

```bash
uv run --locked --package policylens python scripts/export_mcp_passages.py
```

The MCP process must never open Chroma. Re-run this export after rebuilding the retrieval index; the server rejects a snapshot whose `index_version` differs from the active pointer.

## Focused Verification

```bash
uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests
uv run --locked --package policylens pytest \
  apps/backend/tests/unit/test_mcp_client.py \
  apps/backend/tests/integration/test_mcp_protocol.py \
  scripts/tests/test_mcp_passage_export.py \
  scripts/tests/test_mcp_comparison.py
python3 scripts/check_traceability.py
```

The tests use temporary manifests, canonical JSON fixtures, and fake MCP peers. They cover the source permission allow-list, deterministic aggregation/provenance, malformed and stale catalogs, exact passage IDs, capability/schema rejection, timeouts, and malformed responses.

## Local Protocol Probe and Comparison

Use the backend probe to verify the configured local stdio server and its allow-listed capabilities:

```bash
make mcp-health
```

Run the MCP-versus-direct adapter comparison on the same deterministic request fixtures. Record contract parity, result parity, and measured local latency; label fixture/mock measurements as local, not live production evidence.

```bash
uv run --locked --package policylens python scripts/evaluate_mcp_direct.py --repeats 3
```

The accepted local comparison is recorded in [ADR-005-01](../../docs/architecture/adr/ADR-005-01-mcp-vs-direct.md). It reports exact result parity and separately measured local stdio startup/protocol overhead; it is not live-production or quality evidence.

No live Foundry request is needed for Feature 005 verification. The MCP service itself uses stdio; do not expose it as a public HTTP listener.

## Observed Local Results

Verified on 2026-10-26 with the repository's locked Python environment:

- `make test-python`: 149 backend tests, 37 MCP tests, and 49 script tests passed.
- `make format-check-python`, `make lint-python`, and `make typecheck-python`: passed for both Python packages.
- `make data-verify`: all six registered source files verified.
- `make retrieval-verify`: active index ready (`45935afc940a7489563a38c32bbac909b0d8e6a9fb58182fb5c14e86ff130ea4`).
- `make mcp-health`: ready for the exact pinned identity, protocol, capabilities, and schemas.
- The comparison's three fixtures had exact result parity; local latency and limitations are in [ADR-005-01](../../docs/architecture/adr/ADR-005-01-mcp-vs-direct.md).

## Repository Gates

```bash
make format-check-python
make lint-python
make typecheck-python
make test-python
```