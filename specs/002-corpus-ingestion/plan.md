# Implementation Plan: Initial Data Acquisition, Corpus Ingestion, and EDA

**Branch**: `002-corpus-ingestion` (Spec Kit feature identifier; this workspace is not a Git repository) | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-corpus-ingestion/spec.md`

**Implementation authorization**: Complete Feature 002 through source approval, acquisition, structured/PDF parsing, canonical records, quality checks, data sheet, and two reproducible descriptive analyses. Features 003-010 remain outside this implementation.

## Summary

Acquire two original World Bank Indicators API JSON responses and four rights-reviewed World Bank PDFs for the employment/youth-unemployment corpus. No ILO-published PDFs are in the active source set; the modeled indicators retain ILOSTAT upstream attribution. Parse only verified snapshots into versioned canonical datasets/documents, report data quality and licensing limitations, and produce two descriptive EDA outputs. Use an explicit YAML registry, allow-listed HTTPS retrieval, bounded retries/timeouts/size, content validation, SHA-256-addressed immutable paths, atomic writes, and stage manifests.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Existing locked `httpx2` client for independent connect/read timeouts and mock transport; locked PyYAML for the source registry, PyMuPDF for PDF validation and parsing, and Matplotlib for static EDA figures.

**Storage**: Immutable raw files under `data/raw/{structured,reports}/<source_id>/<sha256>.<ext>`; parser-versioned canonical outputs under `data/canonical/`; quality outputs under `data/processed/quality/`; acquisition, ingestion, and EDA manifests under `data/manifests/`; figures and findings under `docs/data/eda/`.

**Testing**: pytest, `httpx2.MockTransport`, temporary directories, deterministic JSON/PDF fixtures; no live network in automated tests.

**Target Platform**: Python 3.12 on Linux and macOS; no API key or external runtime service.

**Project Type**: Local command-line data acquisition utility in the existing Python workspace.

**Performance Goals**: Bounded small corpus: two API responses (44 rows each) and four World Bank PDFs; no throughput target. Each file is limited to a configurable 50 MiB by default.

**Constraints**: HTTPS only; explicit host allow-list including redirect targets; connect timeout 8s, read timeout 30s; at least 250 ms between outbound requests; at most 3 retries with exponential backoff for transient errors; no arbitrary URL input, credentials, or OCR. Do not build chunks, embeddings, indexes, retrieval/RAG, MCP tools, the agent, or complete backend/frontend workflows.

**Scale/Scope**: Four ISO3 countries, two indicators, 2015-2025, and four active World Bank PDFs for Indonesia, Malaysia, India, and Singapore. The Singapore MOM report remains disabled for rights review.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Source records carry canonical/item URLs, publisher, licence, attribution, and retrieval evidence; unverified rights block download. | PASS |
| VI. Reproducibility Is a Product Feature | Original bytes, SHA-256, versions, parameters, response metadata, and retrieval time are retained; changed content creates a new path. | PASS |
| VII. Privacy and Responsible AI | Only public sources are selected; no personal or confidential data, secrets, or keys are used. | PASS |
| VIII. Minimal Engineering, Strong Contracts | One existing-workspace CLI script; no new service or application framework. | PASS |
| IX. Testable Specifications and Traceability | ACQ/AC/SC identifiers map to offline tests, inspection, or commands. | PASS |
| X. Honest Reporting | Manual-review source is excluded; live-download results and unrun checks are reported exactly. | PASS |

No constitution exception is required.

## Project Structure

### Documentation (this feature)

```text
specs/002-corpus-ingestion/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── sources.schema.json
│   └── download-manifest.schema.json
└── tasks.md
```

### Source Code (repository root)
```text
scripts/
├── download_data.py
├── parse_data.py
├── eda/youth_employment.py
└── tests/
    ├── test_download_data.py
    └── test_youth_employment.py
apps/backend/src/policylens/ingestion/
├── models.py
├── structured.py
├── reports.py
└── quality.py
apps/backend/tests/unit/test_ingestion.py
data/
├── raw/
│   ├── structured/<source_id>/<sha256>.json
│   └── reports/<source_id>/<sha256>.pdf
├── manifests/
│   ├── sources.yaml
│   ├── download-manifest.json
│   ├── ingestion-manifest.json
│   └── eda-manifest.json
├── canonical/
├── processed/quality/
└── README.md
docs/data/data-sheet.md
docs/data/eda/
Makefile
.gitignore
apps/backend/pyproject.toml  # script/test-only dependencies
uv.lock
```

**Structure Decision**: Keep acquisition/parse orchestration and EDA in root `scripts/`; place canonical parsers and quality checks in the backend's `policylens.ingestion` package without adding API endpoints. `.gitignore` contains exclusions for raw/canonical/quality outputs; Git tracking cannot be verified in this workspace. No Feature 003+ retrieval/indexing, MCP tool, agent, or frontend work is part of this feature.

## Phase 0: Research

- Verified World Bank Indicators API v2 JSON syntax, multi-country semicolon syntax, date ranges, pagination, and no-key access in official documentation.
- Executed the exact combined-country API request for each indicator. Each returned `pages=1`, `total=44`, the four requested ISO3 codes, and 2015 through 2025.
- Official indicator pages identify ILOSTAT as upstream and CC BY 4.0; attribution and change-notice requirements are recorded in the spec and source registry.
- Verified CC BY 3.0 IGO metadata for the World Bank India skills report and Singapore SABER report; both are enabled with attribution and third-party-content constraints.
- Verified the Indonesia and Malaysia World Bank report front matter permits whole/partial noncommercial reproduction with full attribution; these are not labeled as CC licences.
- The two ILO-published reports were removed from the active corpus at the user's request; prior attempt metadata remains only in the append-only download manifest.
- Excluded the Singapore MOM youth report because its PDF says all rights reserved and further reproduction requires written permission; it remains disabled until reuse for corpus storage is approved.
- Observed `Last-Modified` headers on World Bank API and document endpoints; use conditional requests when validators exist, then verify the local checksum before skipping.

See [research.md](research.md) for URLs, evidence, alternatives, and limitations.

## Phase 1: Design

- Source definitions and attempt/snapshot records are specified in [data-model.md](data-model.md).
- The YAML source registry and JSON download manifest contracts are in `contracts/`.
- [quickstart.md](quickstart.md) defines acquisition, verification, and offline test commands.
- URL allow-listing, response validation, content-addressed paths, atomic writes, and license gates are required before any raw artifact is retained locally.

## Implementation Boundary

Feature 002 ends after acquisition, canonical parsing, quality checks, the data sheet, and the two EDA outputs. OCR, chunking, embeddings, indexes, retrieval/RAG, MCP tools, agent execution, and complete backend/frontend behavior remain assigned to later feature specifications.

## Complexity Tracking

No constitution violations or additional services are required.
