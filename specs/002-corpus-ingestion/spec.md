# Feature Specification: Initial Data Acquisition, Corpus Ingestion, and EDA

**Feature Branch**: `002-corpus-ingestion`  
**Created**: 2026-10-24  
**Status**: Feature 002 acquisition, parsing, quality checks, data sheet, and EDA implemented; downstream retrieval remains planned
**Input**: `POLICYLENS_MASTER_SPEC.md`, Sections 6 and 20 Feature 002

## Product Outcome

A reviewer can identify the approved source set, reproduce acquisition and parsing from immutable snapshots, inspect provenance and quality decisions, and reproduce at least two descriptive findings from real data without invented values.

## Clarifications

### Session 2026-10-25

- Q: Should initial dataset acquisition be a new Spec Kit feature or part of existing Feature 002? → A: Integrate it into existing Feature 002; preserve its directory and downstream feature numbering.

## Initial Corpus and Source Rights

The initial theme is employment and youth unemployment policy. Structured data covers Singapore (`SGP`), Malaysia (`MYS`), Indonesia (`IDN`), and India (`IND`) for 2015-2025. The two required indicators are `SL.UEM.1524.ZS` (youth unemployment, ages 15-24) and `SL.UEM.TOTL.ZS` (total unemployment).

The structured source uses two World Bank Indicators API v2 JSON requests, one per indicator, with `country/SGP;MYS;IDN;IND`, `date=2015:2025`, `format=json`, and `per_page=1000`. The verified response is one page containing 44 country-year records per indicator. The responses must be preserved byte-for-byte. The API requires no key. World Bank indicator pages identify ILOSTAT as the upstream source and CC BY 4.0 as the applicable data licence; attribution must identify ILOSTAT and World Bank Data, the access date, and any changes. No ILO-published PDF reports are included in the active source set.

| Source ID | Official item page | Direct download | Publication date | Acquisition parser metadata | Rights status and role |
|---|---|---|---|---|
| `wb-indonesia-jobs-action-2018` | https://documents.worldbank.org/en/publication/documents-reports/documentdetail/361621624942826086 | https://documents1.worldbank.org/curated/en/361621624942826086/pdf/Indonesia-Jobs-Action-Program-Towards-Win-Win-A-Labor-Reform-Strategy-to-Benefit-All.pdf | 2018-08-01 | `pymupdf` validation-only | The report permits whole or partial reproduction for noncommercial purposes with full attribution; this is not a CC licence. Record third-party-content restrictions. Indonesia jobs, youth unemployment, skills, and labour reform. |
| `wb-malaysia-informal-employment-2024` | https://documents.worldbank.org/en/publication/documents-reports/documentdetail/099022124104015011 | https://documents1.worldbank.org/curated/en/099022124104015011/pdf/P1810931e836170db184871b5fe7b37157c.pdf | 2024-02-22 | `pymupdf` validation-only | The report permits whole or partial reproduction for noncommercial purposes with full attribution; this is not a CC licence. Record third-party-content restrictions. Malaysia employment barriers and labour-market reform. |
| `wb-india-skills-programs-2015` | https://documents.worldbank.org/en/publication/documents-reports/documentdetail/798601468034846280 | https://documents1.worldbank.org/curated/en/798601468034846280/pdf/94682-Change-in-Title-Final-Revised-Output-Skill-Report-5-States.pdf | 2015-04-01 | `pymupdf` validation-only | World Bank Open Knowledge Repository lists CC BY 3.0 IGO. Attribute Meky and World Bank, cite DOI 10.1596/22391, and indicate changes; credited third-party material may have separate rights. Covers skills-program employment and earnings outcomes in five states. |
| `wb-singapore-workforce-development-2012` | https://documents.worldbank.org/en/publication/documents-reports/documentdetail/101071468299971244 | https://documents1.worldbank.org/curated/en/101071468299971244/pdf/799250WP0SABER0Box0379795B00PUBLIC0.pdf | 2012-01-01 | `pymupdf` validation-only | World Bank Open Knowledge Repository lists CC BY 3.0 IGO. Attribute World Bank, cite DOI 10.1596/17646, and indicate changes; credited third-party material may have separate rights. Historical workforce-development assessment. |
| `mom-singapore-youths-labour-market-2025-manual-review` | https://stats.mom.gov.sg/Pages/Youths-In-The-Labour-Market-2025.aspx | https://stats.mom.gov.sg/iMAS_PdfLibrary/mrsd-Youths-in-the-Labour-Market-2025.pdf | 2026-03-26 | `pymupdf` validation-only | Official item page and PDF are verified, but the PDF says all rights reserved and further reproduction requires written permission. Disabled pending rights clearance. Singapore youth employment, job-ready skills, and employment programmes. |

The four approved PDFs are World Bank reports for Indonesia, Malaysia, India, and Singapore. The Singapore MOM youth report remains disabled until written permission or another applicable reuse authorization is obtained. Earlier ILO report PDFs are excluded from the active corpus; the World Bank indicator series remain because they are distributed by the Bank with ILOSTAT identified as upstream.

For enabled World Bank reports, PyMuPDF performs acquisition-time eligibility validation and a separate versioned parser emits canonical page/block text without OCR. The disabled MOM candidate is validation-only and is not fetched or parsed.

The initial prototype is for noncommercial research. World Bank report copies remain local and are not redistributed; any commercial use or redistribution requires a separate rights review. Publication dates and rights above were checked against official item pages and report front matter. `retrieved_at` and the latest successful `sha256` begin as null in `sources.yaml` and are filled from the actual attempt; the download manifest retains every attempt.

## Scope and Dependencies

This feature owns source selection, manifest validation, allow-listed acquisition, immutable raw snapshots, checksums, parsers for at least one structured and one unstructured source, canonical document records, quality checks, a data sheet, and two reproducible EDA findings/visualizations.

Feature 003 owns chunking/indexing/retrieval. This feature MUST NOT implement Chroma, BM25, embeddings, an agent, or answer generation.

Feature 002 includes source approval, allow-listed acquisition, immutable raw snapshots, structured and PDF parsing, canonical records, quality checks, a data sheet, and two reproducible descriptive analyses. The acquisition-time PDF eligibility check uses transient text and discards it; the separate parse stage extracts text into canonical report blocks without OCR. Raw snapshots MUST remain unchanged. Chunking, embeddings, Chroma/BM25 indexing, retrieval/RAG, MCP tools, the agent, and the complete backend/frontend experience remain outside this feature.

## User Scenarios & Testing

### User Story 1 - Approve Lawful Sources (Priority: P1)

As a researcher, I can review source provenance, licence, usage, sensitivity, and theme before data is acquired.

**Independent Test**: Validate a source registry with one approved structured source and official unstructured reports, then reject a source with missing or disallowed rights.

**Acceptance Scenarios**:

1. **AC-002-01** Given an approved source registry, When validation runs, Then every source has stable identity, publisher, format, canonical URL or fixture provenance, licence, date, sensitivity, checksum policy, parser, and allowed usage.
2. **AC-002-02** Given an unavailable or ambiguous licence, When acquisition is requested, Then the pipeline stops before download and records the rights blocker.

### User Story 2 - Reproducibly Acquire and Validate (Priority: P1)

As a contributor, I can fetch only allow-listed sources and reproduce immutable snapshots.

**Independent Test**: Run fetch and validation twice against deterministic fixtures and verify unchanged inputs produce identical hashes and outputs.

**Acceptance Scenarios**:

1. **AC-002-03** Given an approved source, When acquisition runs, Then only its allow-listed HTTPS host/path is requested, with a descriptive user agent, separate connection/read timeouts, bounded exponential retries for transient failures, a configurable size limit, expected media type, checksum, retrieval metadata, temporary `.part` file, and atomic finalization.
2. **AC-002-04** Given a changed checksum, unexpected MIME, oversize file, malformed JSON/PDF, or disallowed host/redirect, When validation runs, Then the artifact is rejected with a machine-readable reason, incomplete files are removed, and prior raw snapshots remain unchanged.
3. **AC-002-08** Given the two approved World Bank indicator sources, When acquisition runs, Then each request uses the four specified ISO3 country codes, the 2015-2025 range, JSON, and `per_page=1000`, returns one page of 44 country-year records, and preserves the original response bytes.
4. **AC-002-09** Given the four approved public PDF reports, When acquisition runs, Then each item-page URL and direct-download URL are recorded separately, each PDF is publicly accessible, valid, and has transiently extractable text verified with PyMuPDF, and source-specific licence and attribution conditions are retained without storing extracted text.

### User Story 3 - Inspect Parsed Data and EDA (Priority: P2)

As a reviewer, I can inspect canonical structure, transformations, caveats, and reproducible findings.

**Independent Test**: Rebuild canonical artifacts and both EDA outputs from the same approved snapshots and compare deterministic manifest hashes.

**Acceptance Scenarios**:

1. **AC-002-05** Given a structured source, When parsed, Then types, units, row keys, dimensions, missing-value meaning, and dictionary references are preserved.
2. **AC-002-06** Given a PDF/HTML/Markdown report, When parsed, Then page/section/block locations, offsets, parser version, and OCR limitations are retained.
3. **AC-002-07** Given acquired real data, When EDA runs, Then two findings or visualizations state their question, subset, transformation, result, caveats, and reproducible path.

## Functional Requirements

- **ACQ-002-01**: The pipeline MUST consume a versioned, explicit source registry and MUST NOT let a model choose arbitrary URLs.
- **ACQ-002-02**: Raw artifacts MUST be immutable by content hash when licensing permits; changed content creates a new corpus version.
- **ACQ-002-03**: The downloader MUST accept only approved source IDs and explicit allow-listed HTTPS hosts; redirects MUST remain on the allow-list.
- **ACQ-002-04**: The downloader MUST use a descriptive PolicyLens user agent, separate connection and read timeouts, a minimum 250 ms interval between outbound requests, bounded exponential backoff only for transient failures, and a configurable maximum file size.
- **ACQ-002-05**: The downloader MUST validate successful HTTP status, media type, JSON syntax and World Bank API response structure; PDFs MUST pass `application/pdf`, the `%PDF-` signature, structural readability, page-count, and transient text-extractability checks through PyMuPDF. It MUST discard validation text and MUST NOT emit parsed content.
- **ACQ-002-06**: Downloads MUST be streamed to a temporary `.part` file, validated before atomic placement, and have incomplete temporary files removed on failure.
- **ACQ-002-07**: The downloader MUST compute SHA-256, avoid retrieving unchanged sources when validators and a checksum-verified manifest allow a conditional request, and MUST retain changed content as a separate content-addressed snapshot rather than overwrite an existing raw file.
- **ACQ-002-08**: The JSON download manifest MUST record every attempted source's status, retrieval timestamp, HTTP status, final URL, content type, bytes, checksum, local path, elapsed time, and safe error details when applicable. After each attempt, `sources.yaml` MUST also record the actual latest `retrieved_at` and the latest successful checksum without deleting prior raw snapshots.
- **ACQ-002-09**: Any failed mandatory source MUST produce a non-zero command exit status. Requests MUST require no API key for these sources and MUST NOT place secrets in query strings.
- **ACQ-002-10**: Sources with unverified rights MUST be marked for manual review and MUST NOT be downloaded; World Bank noncommercial terms, CC BY attribution, third-party exclusions, and ILOSTAT upstream attribution for World Bank indicators MUST remain attached to their source records.
- **PARSE-002-01**: Parsers MUST emit the versioned canonical document representation and preserve provenance and structure.
- **DATA-002-01**: Quality checks MUST report duplicates, missingness, parse/OCR limitations, exclusions, units, and known data issues.
- **DATA-002-02**: Every stage MUST emit a machine-readable manifest of input/output hashes, tool versions, parameters, status, warnings, and rejected records.
- **EDA-002-01**: EDA MUST use acquired or synthetic data only, label synthetic lineage, and never treat model output as observations.

## Success Criteria

- **SC-002-01**: Both structured indicator responses and all four approved World Bank reports pass rights, checksum, media-type, size, and file-integrity checks; the Singapore MOM candidate remains undownloaded and no ILO-published PDFs are in the active corpus. Canonical parsing and DATA-002-01 quality reports preserve provenance, missingness, and parser limitations.
- **SC-002-02**: An unchanged acquisition/parse/EDA run reproduces the same artifact hashes and manifest decisions.
- **SC-002-03**: Two EDA outputs are reproducible, cite their actual inputs, and include limitations.
- **SC-002-04**: Downloader tests for validation, cleanup, idempotency, manifests, and failure status pass using local fixtures without live-network dependencies.

## Open Questions and Assumptions

- The bounded topic, countries, indicators, year range, and four active World Bank reports are resolved in `Initial Corpus and Source Rights` above. The Singapore MOM report remains disabled pending written permission.
- The existing Feature 002 is retained; this acquisition work does not create a new feature number or change the numbering of Features 003-010.
- Raw retention is allowed only where each source licence permits it; otherwise retain an approved reference/hash and document the restriction.
- World Bank report use in this prototype is noncommercial and requires full attribution; third-party components and any future commercial use or external redistribution require rights review.
- No causal conclusion is implied by descriptive EDA.

## Out of Scope

OCR, chunk generation, embeddings, Chroma or BM25 indexes, retrieval experiments, MCP statistics tools, agent execution, complete backend/frontend workflows, and generated answers remain outside Feature 002.