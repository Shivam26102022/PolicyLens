# Data Model: Acquisition and Canonical Ingestion

## Source Definition

One versioned registry entry describes one API response or one PDF.

| Field | Type | Rule |
|---|---|---|
| `source_id` | string | Stable unique identifier; used in deterministic local paths. |
| `title` | string | Official indicator/report title. |
| `publisher` | string | Responsible publisher; upstream provider is recorded separately when different. |
| `source_kind` | enum | `structured` or `unstructured`. |
| `format` | enum | `json` or `pdf` for this initial set. |
| `acquisition_method` | enum | `api` or `https_download`. |
| `canonical_url` | HTTPS URL | Official indicator or item page; report item URL is distinct from its file URL. |
| `download_url` | HTTPS URL | Exact API request or direct PDF URL. Host and path must be allow-listed. |
| `expected_media_type` | string | `application/json` or `application/pdf`. Parameters are ignored for comparison. |
| `indicator_id` | string/null | Required for structured indicator responses. |
| `countries` | string array | ISO3 codes; report sources may use an empty array when global. |
| `year_range` | two integers/null | `[2015, 2025]` for structured sources. |
| `publication_date` | ISO date/null | Official document date, or null for a live API dataset. |
| `retrieved_at` | ISO-8601 timestamp/null | Null before acquisition; updated in `sources.yaml` after every attempt and also retained in the append-only download manifest. |
| `sha256` | 64-character lowercase hex/null | Null before successful acquisition; latest successful snapshot checksum is recorded here and every attempt checksum remains in the download manifest. |
| `etag` | string/null | Latest successful response validator, when supplied by the origin. |
| `last_modified` | HTTP-date/null | Latest successful response validator, when supplied by the origin. |
| `parser` | string | Acquisition validation adapter, such as `worldbank-json-validation` or `pymupdf`. |
| `parser_version` | string | Locked validation dependency version; canonical parser versions are stored in derived artifacts. |
| `licence` | string/null | Exact observed licence or usage statement; never inferred. |
| `license_review_status` | enum | `verified` or `manual_review_required`. |
| `attribution` | string | Required citation/credit and change notice. |
| `usage_constraints` | string/null | Noncommercial restriction, third-party carve-out, or other terms. |
| `refresh_policy` | enum | `manual` for the initial immutable snapshot. |
| `sensitivity` | enum | `public`, `synthetic`, or `anonymised`; selected inputs are public. |
| `allowed_usage` | string array | `retrieval`, `evaluation` when rights permit. |
| `local_path` | path template | Includes source ID and SHA-256; no unstable server filename. |
| `acquisition_enabled` | boolean | False for manual-review candidates; only approved entries may be fetched. |
| `mandatory` | boolean | A failed enabled mandatory source makes the command exit nonzero. |

## Download Attempt

Each source attempt produces one manifest record with `source_id`, `status`, `retrieved_at`, `http_status`, `final_url`, `content_type`, `bytes`, `sha256`, `local_path`, `elapsed_seconds`, optional `etag`/`last_modified`, `error_code`, and a safe `error_message`.

Statuses are `downloaded`, `unchanged`, or `failed`. A failed/manual-review source is never labeled downloaded. `downloaded` and `unchanged` require a verified local file whose SHA-256 matches the record.

## Raw Snapshot

A raw snapshot is the exact response byte sequence accepted from an approved source. Its identity is `(source_id, sha256)`. Local paths are:

- `data/raw/structured/<source_id>/<sha256>.json`
- `data/raw/reports/<source_id>/<sha256>.pdf`

Files are written to a temporary `.part` file, validated, hashed, and atomically placed. Existing hash paths are verified and never overwritten. Changed upstream bytes create a distinct snapshot path.

## Canonical Structured Dataset

Each API response is parsed into one immutable `StructuredDataset` record at `data/canonical/structured/<source_id>/<parser_version>/<raw_sha256>.json`. The dataset stores its ID, source ID, title, indicator ID and label, source country/year dimensions, observations, API response metadata (including `lastupdated`), source provenance, raw content hash, missing-value semantics, and parser version.

Each observation has a stable key `<source_id>:<country_iso3>:<year>` and preserves ISO2/ISO3 codes, country name, integer year, numeric-or-null value, unit, observation status, and decimal precision. A JSON `null` remains null; no imputation or interpolation is performed.

## Canonical Report Document

Each PDF is parsed into a `CanonicalDocument` at `data/canonical/reports/<source_id>/<parser_version>/<raw_sha256>.json`. It contains the stable document ID, title, source ID, content type, language, raw content hash, parser version, provenance, and ordered pages. Pages contain typed blocks with stable IDs, text, section path, optional bounding box/table rows, and global character offsets. Extraction is text-only; OCR is not performed.

## Quality Report and Run Manifest

Each canonical output has a deterministic quality report at `data/processed/quality/<source_id>/<parser_version>/<raw_sha256>.json`. Structured checks record record/country/year counts, nulls, duplicate keys, missing keys, and unit consistency. Report checks record page/block/text counts, duplicate IDs, offset validity, empty pages, OCR limitations, and rights caveats.

`data/manifests/ingestion-manifest.json` is append-only by run and records raw input hashes, canonical/quality output paths and hashes, tool versions, status, findings, and safe failures. Canonical and quality outputs are regenerated from the immutable raw snapshots and versioned parsers.

## Validation Rules

- World Bank JSON must be a two-element API response `[metadata, records]`, have `pages == 1`, the expected indicator and countries, 44 rows spanning years 2015-2025, and preserve null values without imputation.
- During acquisition, a PDF must have HTTP 200, `application/pdf`, a `%PDF-` signature, readable structure, at least one page, and nontrivial extractable text; this transient eligibility text is discarded. The later parse stage extracts text into canonical page/block records and does not perform OCR.
- A source with `license_review_status != verified` or `acquisition_enabled != true` is never requested.
- Redirects to hosts outside the explicit allow-list are rejected before following them.

## Lifecycle

`registered -> approved -> fetching -> validated -> stored -> parsed -> quality_checked`

Alternative terminal states are `unchanged`, `failed`, and `manual_review_required`. Failed attempts do not replace prior snapshots or erase previous successful manifest records.