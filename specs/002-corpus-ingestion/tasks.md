# Tasks: Initial Data Acquisition, Corpus Ingestion, and EDA

**Input**: Design documents from `/specs/002-corpus-ingestion/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Current execution boundary**: Complete all Feature 002 tasks through parsing, quality checks, data sheet, EDA, documentation, and verification. Features 003-010 remain outside this task.

**Tests**: Required by the feature specification. Automated tests use local fixtures and mocked HTTP; no test requires live network access.

**Format**: `- [ ] T### [P?] [US#] Description with exact file path`

## Phase 1: Setup

**Purpose**: Add the script/test dependencies and command wiring needed for acquisition, parsing, and EDA.

- [x] T001 Add `Matplotlib`, `PyYAML`, and `PyMuPDF` to the development dependency group in `apps/backend/pyproject.toml` and refresh `uv.lock`; reuse the already locked `httpx2` dependency (ACQ-002-03 through ACQ-002-05, EDA-002-01).
- [x] T002 [P] Add `data-fetch`, `data-verify`, `data-parse`, and `data-eda` targets to the root `Makefile`, invoking the scripts through the locked workspace environment (ACQ-002-09, PARSE-002-01, EDA-002-01).
- [x] T003 [P] Extend `.gitignore` to retain the raw-data placeholders, ignore raw/canonical/quality outputs and acquisition `.part` files, and keep manifests trackable (ACQ-002-02, ACQ-002-06, DATA-002-02).

## Phase 2: Foundational

**Purpose**: Establish the typed source and attempt model shared by source review and acquisition.

- [x] T004 Define validated `SourceDefinition`, `DownloadAttempt`, and `RawSnapshot` models plus stable error codes in `scripts/download_data.py` using `specs/002-corpus-ingestion/data-model.md` (ACQ-002-01, ACQ-002-08).

## Phase 3: User Story 1 - Approve Lawful Sources (Priority: P1)

**Goal**: Review and approve only sources whose provenance, usage rights, and acquisition locations are explicit.

**Independent Test**: Registry tests accept the two indicator APIs and four verified PDF sources, reject malformed or unapproved entries, and never schedule manual-review candidates.

### Tests for User Story 1

- [x] T005 [US1] Add offline tests for registry fields, HTTPS host/path allow-listing, verified versus manual-review rights, disabled-source skipping, and deterministic source IDs in `scripts/tests/test_download_data.py` (AC-002-01, AC-002-02; ACQ-002-01, ACQ-002-10).

### Implementation for User Story 1

- [x] T006 [US1] Add two World Bank indicator definitions, four World Bank report definitions, and the disabled Singapore MOM manual-review candidate to `data/manifests/sources.yaml` with publisher, item/API URL, direct URL, date, parser/parser_version, rights, attribution, usage limits, null initial `retrieved_at`/`sha256`, and local-path template (AC-002-01, AC-002-02, AC-002-08, AC-002-09; ACQ-002-01, ACQ-002-02, ACQ-002-10).
- [x] T007 [US1] Implement YAML loading and source-definition validation in `scripts/download_data.py`; stop before any request when an enabled source lacks a verified licence, required attribution, or approved host (AC-002-01, AC-002-02; ACQ-002-01, ACQ-002-10).
- [x] T008 [US1] Document topic, source selection, exact rights, the manual-review candidate, data limitations, null-value handling, and refresh policy in `data/README.md` (SC-002-01, SC-002-03; ACQ-002-10).

**Checkpoint**: The validated registry contains exactly two enabled World Bank structured sources and four enabled World Bank report PDFs. The Singapore MOM candidate remains disabled for manual rights review.

## Phase 4: User Story 2 - Reproducibly Acquire and Validate (Priority: P1)

**Goal**: Fetch only approved sources, preserve original response bytes, and create immutable, verifiable snapshots and manifests.

**Independent Test**: Fixture-driven tests prove successful and failed fetch behavior, checksum stability, no overwrite, unchanged-file handling, and nonzero exit for a mandatory source failure.

### Tests for User Story 2

- [x] T009 [US2] Add offline tests for SHA-256, World Bank JSON envelope/coverage, PDF MIME/signature/structure/text-extractability, malformed or scanned-only PDF, maximum size, invalid content type, `.part` cleanup, retries, 250 ms request spacing, conditional 304 handling, source/attempt timestamps/checksums, manifest entries, and failed-source exit status in `scripts/tests/test_download_data.py` (AC-002-03, AC-002-04, AC-002-08, AC-002-09; ACQ-002-03 through ACQ-002-09).

### Implementation for User Story 2

- [x] T010 [US2] Implement allow-listed HTTPS requests with `httpx2` separate connect/read timeouts, descriptive user agent, redirect checks, minimum 250 ms request spacing, transient-only bounded exponential retries, `Retry-After` handling, streaming, and configurable size enforcement in `scripts/download_data.py` (AC-002-03, AC-002-04; ACQ-002-03, ACQ-002-04, ACQ-002-09).
- [x] T011 [US2] Implement JSON and PDF validation in `scripts/download_data.py`, including JSON structure and 44-row coverage checks, PyMuPDF media type/signature/structure/page-count/transient text-presence checks, discarded validation text, and SHA-256 computation (AC-002-08, AC-002-09; ACQ-002-05).
- [x] T012 [US2] Implement content-addressed raw paths, `.part` temporary files, atomic placement, conditional requests, checksum verification before `unchanged`, and no-overwrite behavior in `scripts/download_data.py` (AC-002-04; SC-002-02; ACQ-002-02, ACQ-002-06, ACQ-002-07).
- [x] T013 [US2] Implement atomic append-only run records in `data/manifests/download-manifest.json` and update `retrieved_at` plus the latest successful `sha256` in `data/manifests/sources.yaml` after each attempt; implement `fetch`/`verify` command behavior in `scripts/download_data.py`, include safe failure details, and return nonzero when any enabled mandatory source fails (AC-002-03, AC-002-04; ACQ-002-08, ACQ-002-09).
- [x] T014 [US2] Run the offline acquisition tests and `make data-fetch`, verify all local files and manifest records with `make data-verify`, and report the actual downloaded paths, byte counts, hashes, and any failures (SC-002-01, SC-002-02, SC-002-04; AC-002-03, AC-002-04, AC-002-08, AC-002-09).
- [x] T015 [US2] Update `data/README.md` with the actual retrieval date, expected output layout, observed null values, exact sizes/checksums, and any failed/manual-review sources after the real run (SC-002-01, SC-002-03; DATA-002-01, DATA-002-02).

**Checkpoint**: Two raw JSON API responses and four World Bank report PDFs are validated and recorded; no ILO-published PDFs are in the active corpus.

**Acquisition Checkpoint (before parsing/EDA)**:

- `uv run --locked --package policylens pytest scripts/tests/test_download_data.py -q`: 20 passed.
- `make test-python`: 48 passed across backend (19), MCP (4), and scripts (25).
- `uv run --locked --package policylens ruff check scripts/download_data.py scripts/tests/test_download_data.py`: passed.
- `uv run --locked --package policylens ruff format --check scripts/download_data.py scripts/tests/test_download_data.py`: passed.
- `uv run --locked --package policylens mypy scripts/download_data.py scripts/tests/test_download_data.py`: passed with no issues.
- `make lint-python`, `make typecheck-python`, and `make format-check-python`: passed.
- `make data-fetch`: after the source-set change, both World Bank indicator JSONs were restored and all four World Bank PDFs were unchanged; the repeat fetch returned `unchanged` for all six enabled sources. The Singapore MOM candidate remained skipped. ILO-published report sources were removed from the active registry and their raw files removed; historical attempts remain in the append-only manifest.
- `make data-verify`: passed for all six enabled sources after the repeat fetch; no `.part` files remained.
- Earlier acquisition-only quickstart in a fresh isolated Python 3.12.14 environment: locked sync installed 58 packages; `make data-fetch` returned `unchanged` for all six active sources and skipped MOM; `make data-verify` passed; the downloader suite passed (20 tests). The expanded Feature 002 run is recorded below.
- A clean Git checkout and Git ignore tracking cannot be verified because this workspace has no Git metadata.

## Phase 5: User Story 3 - Inspect Parsed Data and EDA (Priority: P2)

**Goal**: Inspect canonical structure, transformations, quality decisions, and reproducible findings from the approved snapshots.

**Independent Test**: Rebuild canonical artifacts and both EDA outputs from the same approved snapshots and compare deterministic manifest hashes.

- [x] T016 [US3] Add structured-parser and canonical-record tests, including units, keys, nulls, and provenance, in `apps/backend/tests/unit/test_ingestion.py` (AC-002-05; PARSE-002-01).
- [x] T017 [US3] Implement structured JSON parsing and canonical records under `apps/backend/src/policylens/ingestion/structured.py` without modifying `data/raw/` (AC-002-05; PARSE-002-01).
- [x] T018 [US3] Add report-parser tests for headings, page numbers, text locations, parser version, and third-party/license metadata in `apps/backend/tests/unit/test_ingestion.py` (AC-002-06; PARSE-002-01).
- [x] T019 [US3] Implement report parsing in `apps/backend/src/policylens/ingestion/reports.py`; do not add OCR unless a future approved plan documents it (AC-002-06; PARSE-002-01).
- [x] T020 [US3] Add source quality checks and the data sheet in `apps/backend/src/policylens/ingestion/quality.py` and `docs/data/data-sheet.md` (AC-002-05, AC-002-06; DATA-002-01, DATA-002-02).
- [x] T021 [US3] Add two reproducible descriptive analyses and visualizations in `scripts/eda/youth_employment.py` and `docs/data/eda/`; do not make causal claims (AC-002-07; EDA-002-01).

## Phase 6: Polish and Cross-Cutting Concerns

- [x] T022 [P] Add acquisition, parsing/EDA commands, provenance, attribution, and limitation details to the root `README.md` (ACQ-002-08, ACQ-002-10, DATA-002-02).
- [x] T023 Update `docs/traceability/traceability.md` with Feature 002 requirements and evidence paths after their corresponding implementation tasks are complete (DATA-002-02).
- [x] T024 Run the expanded quickstart from `specs/002-corpus-ingestion/quickstart.md` in a fresh isolated locked environment, including parse, EDA, and focused tests; record actual results in `data/README.md`. Note that this workspace has no Git metadata, so clean-checkout/ignore tracking cannot be verified (SC-002-02, SC-002-04).

**Feature 002 Final Verification**:

- `make test-python`: 59 passed across backend (28), MCP (4), and scripts (27).
- `make lint-python`, `make typecheck-python`, and `make format-check-python`: passed.
- `make traceability`: passed with 67 global requirements, 14 feature requirements, 11 acceptance criteria, 5 success criteria, and 10 demo scenarios.
- `make data-verify`: all six active raw snapshots verified.
- `make data-parse`: both indicator datasets and all four PDF reports parsed; quality reports were generated. PyMuPDF emitted only its optional layout-package suggestion.
- Two `make data-eda` runs produced identical hashes: results `b5823ed5be16a62105e2de2632551dad18459b16ae212050c235afaf52528cb9`, comparison figure `2bc397382caa72cf126dbce7de797b431475c7b932f33748f07b32617ece1a0a`, and trend figure `aef3fa37e5b9b59b8043dd1b82deb2c8b424e7da9f5f9c86eb17855e8ecc9e8f`.
- Expanded quickstart in a fresh isolated Python 3.12.14 environment installed 69 locked packages; all six enabled sources were unchanged and verified, MOM was skipped, parsing/EDA succeeded, downloader tests passed (20), and ingestion/EDA tests passed (11). Git tracking and clean-checkout status remain unverified.

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T002 and T003 are parallelizable.
- **Foundational (Phase 2)**: Depends on Setup; T004 establishes the shared source/attempt model.
- **User Story 1 (Phase 3)**: Depends on Foundation; approve the registry before any network access.
- **User Story 2 (Phase 4)**: Depends on a passing US1 rights gate; tests precede HTTP and storage implementation.
- **User Story 3 (Phase 5)**: Depends on completed acquisition; parser/quality/EDA tasks were reverified in T024.
- **Polish (Phase 6)**: Documentation and traceability follow verified implementation evidence; quickstart is the final end-to-end check.

### User Story Dependencies

- **US1**: Independent after the shared model; registry and rights decision are prerequisites for every download.
- **US2**: Depends on US1 approval but does not depend on parsing or any other user story.
- **US3**: Depends on acquired snapshots; completed against immutable content-addressed inputs.

### Parallel Opportunities

- T002 and T003 touch separate files and can run in parallel.
- US1 documentation may be drafted independently from registry validation after the selected sources are fixed, but the source inventory must be identical in both files.
- US2 test implementation is in a separate file from `scripts/download_data.py`; code changes follow the tests.
- US3 parsing, quality, and EDA consume immutable inputs in dependency order; EDA runs after canonical parsing.

## Parallel Example: Setup

```text
T002: Add Make targets in Makefile
T003: Add raw/temp ignore rules in .gitignore
```

## Implementation Strategy

### Current MVP

1. Complete Setup and Foundational work.
2. Complete US1 source registry and rights gate.
3. Complete US2 offline tests, downloader, and actual acquisition verification.
4. Complete US3 parsing, quality checks, data sheet, and EDA from immutable acquired snapshots.
5. Reconcile documentation and traceability, then rerun final checks and the expanded quickstart.

### Explicitly Excluded

Do not add OCR, chunking, embeddings, indexes, retrieval/RAG, MCP tools, an agent, or complete backend/frontend workflows under Feature 002.