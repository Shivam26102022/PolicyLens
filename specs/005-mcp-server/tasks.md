---
description: "Implementation tasks for the standalone MCP service and trust controls"
---

# Tasks: Standalone MCP Service and Trust Controls

**Input**: Design documents from `/specs/005-mcp-server/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included because each user story specifies independent test criteria and the acceptance scenarios require protocol, permission, failure, and provenance checks. Write focused tests before the implementation tasks in each story phase.

**Organization**: Tasks are grouped by the three P1 user stories. US1 and US2 share the server entrypoint; implement their service modules independently, then add resource registration after the statistics registration to avoid parallel edits to `server.py`.

## Phase 1: Setup

**Purpose**: Complete the MCP package's direct runtime dependency setup.

- [x] T001 Add direct dependency `PyYAML>=6,<7` to `services/mcp-policy-data/pyproject.toml` and refresh `uv.lock` with `uv lock`.

---

## Phase 2: Foundational

**Purpose**: Establish typed contracts and stable error models required by both server capabilities and the backend host.

- [x] T002 [P] Implement server-side Pydantic request, result, passage-catalog, and safe-error models in `services/mcp-policy-data/src/policylens_mcp/models.py`, enforcing the `statistics-tool.schema.json` and `passage-resource.schema.json` constraints, including the two indicator IDs, one to four unique uppercase ISO3 geographies, years 2015–2025, row limit 1–44, passage text limit 5,000 characters, exact `sha256:` passage IDs, and `schema_version=1.0`.
- [x] T003 [P] Create backend MCP capability, response, and stable host-error models in `apps/backend/src/policylens/mcp/models.py`, enforcing server name `PolicyLens Policy Data Server`, server version `0.1.0`, protocol version `2026-07-28` from the pinned `mcp==2.3.0` SDK, one `query_statistics` tool, the resource template `policy://sources/{source_id}/passages/{passage_id}`, and the host error codes in `data-model.md`.

**Checkpoint**: Both packages have versioned typed boundaries; story implementation can proceed.

---

## Phase 3: User Story 1 - Query Approved Statistics (Priority: P1)

**Goal**: Return deterministic, bounded calculations only from the two statistics-approved unemployment series, with row provenance, hashes, attribution, and caveats.

**Independent Test**: Compare valid tool output with a deterministic reference calculation; verify unapproved sources, invalid query ranges/grouping, row overflow, corrupt hashes, and non-finite values fail with typed errors.

### Tests for User Story 1

- [x] T004 [P] [US1] Add statistics unit tests in `services/mcp-policy-data/tests/test_statistics.py` comparing results with a deterministic reference calculation and covering unknown indicators, unsupported aggregation/grouping, invalid year ranges, geography bounds, `allowed_usage` enforcement, public/verified source requirements, raw/canonical hash mismatches, hard `row_limit` overflow without truncation, non-finite values, null handling, Decimal rounding, ordered row keys, attribution, and modeled-estimate caveats.

### Implementation for User Story 1

- [x] T005 [US1] Implement source-registry and ingestion-manifest resolution in `services/mcp-policy-data/src/policylens_mcp/statistics.py`; require `allowed_usage` to contain `statistics`, require a public source with verified licence review, enforce the exact two approved source IDs/indicator IDs, confine canonical reads to `data/canonical/`, and verify raw SHA-256, canonical SHA-256, manifest status, source identity, indicator, and year range before exposing observations.
- [x] T006 [US1] Implement deterministic filtering and aggregation in `services/mcp-policy-data/src/policylens_mcp/statistics.py`; accept one to four unique ISO3 geographies and inclusive years 2015–2025, reject reversed ranges and any complete result exceeding request `row_limit` or 44 rows (never truncate), reject non-finite values, preserve nulls for `aggregation=none`, ignore and count nulls for aggregates, use `Decimal` with six-place `ROUND_HALF_EVEN` aggregate rounding, and sort rows and provenance deterministically without SQL or dynamic expressions.
- [x] T007 [US1] Register exactly one structured-output `query_statistics` tool in `services/mcp-policy-data/src/policylens_mcp/server.py`, instantiate `MCPServer` with version `0.1.0`, validate input/output with the typed models, return the stable statistics error codes, and include source IDs, row keys, raw/canonical hashes, ILOSTAT and World Bank Data attribution, and the modeled-ILO-estimate caveat.

**Checkpoint**: The statistics tool can be tested independently without an MCP host or external network calls.

---

## Phase 4: User Story 2 - Read a Source Passage (Priority: P1)

**Goal**: Resolve exact active Feature 003 passage IDs through a bounded read-only resource while keeping Chroma owned by the backend.

**Independent Test**: Read valid, unknown, malformed, traversal-shaped, disallowed, oversized, checksum-invalid, and stale-index records; only a valid current catalog entry may return verbatim bounded text and provenance marked `untrusted=true`.

### Tests for User Story 2

- [x] T008 [P] [US2] Add passage-resource unit tests in `services/mcp-policy-data/tests/test_passages.py` for exact URI/ID lookup, retrieval permission, source metadata, text checksum and 5,000-character bounds, malformed/traversal-shaped IDs, unknown records, corrupt catalogs, and active-index version mismatch.
- [x] T009 [P] [US2] Add passage-export tests in `scripts/tests/test_mcp_passage_export.py` using a fake validated retrieval service to verify exact Feature 003 passage IDs/provenance, registry retrieval permission, sorted records, index version, text hashes, fixed output location, atomic replacement, and fail-closed behavior.

### Implementation for User Story 2

- [x] T010 [US2] Add a narrow read-only passage iterator to `apps/backend/src/policylens/retrieval/search.py` that exposes only validated in-memory passages whose `allowed_usage` contains `retrieval` and whose permission scope is active; do not expose Chroma handles or add any MCP-to-Chroma path.
- [x] T011 [US2] Implement `scripts/export_mcp_passages.py` to use the existing active-index verification and retrieval service, enrich records from the source registry, reject sources without retrieval permission or supported sensitivity, preserve exact passage IDs and provenance, write only `data/indexes/mcp-passage-catalog.json`, and replace it atomically from a same-directory temporary file.
- [x] T012 [US2] Implement catalog loading and exact resource resolution in `services/mcp-policy-data/src/policylens_mcp/passages.py`; validate `schema_version`, passage text SHA-256, URI and ID formats, `allowed_usage` containing `retrieval`, the 5,000-character limit, and equality between catalog `index_version` and `data/indexes/active-index.json` both at load and before reads; fail closed on missing, malformed, stale, disallowed, or oversized records.
- [x] T013 [US2] Register the single read-only resource template `policy://sources/{source_id}/passages/{passage_id}` in `services/mcp-policy-data/src/policylens_mcp/server.py`, returning the versioned resource wrapper with verbatim text, stable source/passage IDs, locations or row key, hashes, licence, sensitivity, usage constraints, and `untrusted=true` without resolving caller values as filesystem paths.

**Checkpoint**: Valid active passages resolve with exact IDs; stale or malformed catalogs never return data.

---

## Phase 5: User Story 3 - Safely Discover and Call MCP (Priority: P1)

**Goal**: Make the backend validate server identity, protocol, and exact capability schemas before calling the production statistics adapter, with bounded failures and untrusted outputs.

**Independent Test**: Exercise the backend client against the expected stdio server and fault peers for wrong identity, unknown capabilities, schema mismatch, unavailability, timeout/cancellation, malformed output, and instruction-like tool/resource content.

### Tests for User Story 3

- [x] T014 [P] [US3] Add backend client unit tests in `apps/backend/tests/unit/test_mcp_client.py` for identity/protocol and capability allow-list checks, input/output/resource schema validation, `query_statistics` and passage reads, stable error mapping, timeouts/cancellation, explicit transient-only retry behavior, and instruction-like resource content remaining `untrusted=true` without changing host policy or the discovered tool allow-list; also assert log redaction of credentials, arguments, results, and passage text.
- [x] T015 [P] [US3] Add a real-server stdio protocol integration test in `apps/backend/tests/integration/test_mcp_protocol.py` for the expected identity and exact capability/schema contract; cover unavailable process, wrong identity, additional capabilities, malformed schemas/results, timeout, and no provider fallback with fault fixtures in `apps/backend/tests/unit/test_mcp_client.py`.
- [x] T016 [P] [US3] Extend `services/mcp-policy-data/tests/test_startup.py` to launch the server over stdio and assert server name `PolicyLens Policy Data Server`, server version `0.1.0`, protocol version `2026-07-28`, one registered tool, and one resource template; verify invalid statistics/catalog state fails safely in `services/mcp-policy-data/tests/test_statistics.py` and `services/mcp-policy-data/tests/test_passages.py`.

### Implementation for User Story 3

- [x] T017 [US3] Implement the async request-scoped MCP host client, `StatisticsToolAdapter.query_statistics`, and typed `read_passage(uri)` in `apps/backend/src/policylens/mcp/client.py`; validate the exact identity/version/protocol in `host-capabilities.schema.json`, require the one-tool/one-resource allow-list, compare discovered tool input/output schemas with `statistics-tool.schema.json` using canonical SHA-256 fingerprints, validate the discovered resource-template URI against `host-capabilities.schema.json`, parse resource content and validate it against `passage-resource.schema.json`, preserve `untrusted=true`, enforce `mcp_timeout_seconds` and cancellation, map failures to stable codes, and avoid automatic retries except the existing explicit transient-error policy.
- [x] T018 [US3] Wire the production MCP statistics adapter as the default in `apps/backend/src/policylens/api/app.py` while preserving the `statistics_tool_adapter` injection path used by tests; do not add provider fallback or a public HTTP MCP transport.
- [x] T019 [US3] Extend `apps/backend/src/policylens/api/mcp_probe.py` to reuse host identity/capability/schema validation and report `ready` only for the exact approved server contract, retaining bounded timeout and safe `MCP_*` errors.
- [x] T020 [US3] Extend the safe JSON formatters in `apps/backend/src/policylens/observability/logging.py` and `services/mcp-policy-data/src/policylens_mcp/logging.py` to emit only server identity/version, tool or resource name, argument hash, status, duration, trace ID, and stable error code; never log raw arguments, credentials, results, prompts, or passage text, and cover redaction in `apps/backend/tests/unit/test_mcp_client.py`.

**Checkpoint**: The host validates the server contract before use, returns typed errors on faults, and treats all MCP content as data rather than instructions.

---

## Phase 6: Polish and Cross-Cutting Concerns

**Purpose**: Record the measured comparison, trace all requirements, and verify repository gates.

- [x] T021 Add deterministic MCP-versus-direct parity tests in `scripts/tests/test_mcp_comparison.py`, using identical fixture inputs to assert output/contract parity and to keep mock/local evidence distinct from live measurements.
- [x] T022 Implement `scripts/evaluate_mcp_direct.py` to run the same deterministic fixture requests through the production MCP adapter and a thin direct-call adapter, report result/contract parity and measured local latency as machine-readable output, and make no external provider/data calls.
- [x] T023 Record ADR-005-01 in `docs/architecture/adr/ADR-005-01-mcp-vs-direct.md`, comparing interoperability, operational overhead, latency, debugging, trust, and versioning; include actual local comparison evidence and explicitly label mocks/local results without claiming live or intrinsic quality superiority.
- [x] T024 Update `specs/005-mcp-server/quickstart.md` with verified dependency, data/index prerequisite, fixed-path passage export, focused tests, local probe/comparison, and Python quality-gate commands; state that live Foundry calls are not part of Feature 005 verification.
- [x] T025 Create `specs/005-mcp-server/traceability.md` mapping every `MCP-005-*`, `OBS-005-01`, `ADR-005-01`, `AC-005-*`, and `SC-005-*` item to its test/evaluation evidence and reproducible command; identify any requirement intentionally verified by inspection rather than a test.
- [x] T026 Run `make format-check-python`, `make lint-python`, `make typecheck-python`, `make test-python`, and `python3 scripts/check_traceability.py`; fix Feature 005 regressions and record the results in `specs/005-mcp-server/traceability.md` and `specs/005-mcp-server/quickstart.md`.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; completes the MCP package dependency/lock update.
- **Foundational (Phase 2)**: Depends on Setup; typed server and host models block all user stories.
- **User Stories (Phases 3–5)**: Depend on Foundational. US1 and US2 are independently testable; US2's exporter and resolver can proceed separately from US1, but resource registration in `server.py` follows US1's tool registration to avoid conflicting edits. US3's final exact-capability validation depends on both server capabilities being registered.
- **Polish (Phase 6)**: Depends on US1, US2, and US3; comparison, ADR, traceability, and final gates require the implemented service and host client.

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2; no dependency on another story.
- **US2 (P1)**: Starts after Phase 2; its final `server.py` registration follows T007, while the exporter/resolver work is otherwise independent of US1.
- **US3 (P1)**: Tests can start after Phase 2; production capability validation and adapter wiring require US1 and US2 registrations.

### Parallel Opportunities

- T002 and T003 can run in parallel because server and backend models are in separate packages.
- T004 can be prepared alongside T008/T009 and T014/T015/T016 because the test files are separate; each story's tests must pass against its own implementation before the checkpoint.
- T008 and T009 can run in parallel; T014, T015, and T016 can run in parallel.
- US1 statistics loading/aggregation and US2 passage export/resolver can be implemented in parallel until edits to `services/mcp-policy-data/src/policylens_mcp/server.py` are needed.
- T021 may be authored while T022 is implemented because the test and harness files are separate; T023 requires observed harness output.

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational phases.
2. Complete US1, including its independent source permission, deterministic result, and provenance tests.
3. Stop and validate the statistics capability locally; do not represent this server-only milestone as Feature 004 agent value until US3 wires the production host adapter.

### Incremental Delivery

1. Add US2 to preserve exact Feature 003 passage IDs through the versioned backend export.
2. Add US3 to validate capabilities and connect the backend adapter over stdio.
3. Complete comparison, ADR, traceability, quickstart, and all Python gates.

## Notes

- `[P]` marks tasks that edit separate files and have no dependency on incomplete tasks.
- Tests use local fixtures/fake peers; no task assumes a live Foundry or external data-provider call.
- The MCP process must not import backend internals or open Chroma; the backend exporter is the only passage-catalog producer.
- Do not mark a task complete without recording its focused verification evidence.