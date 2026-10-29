# Acquisition Quickstart

## Prerequisites

- Python 3.12+ and the repository's pinned `uv` environment.
- Network access to the allow-listed World Bank hosts.
- No API keys or credentials.

## Commands

```bash
uv sync --locked --all-packages --all-groups
make data-fetch
make data-verify
make data-parse
make data-eda
uv run --locked --all-packages --all-groups pytest scripts/tests/test_download_data.py
uv run --locked --package policylens pytest apps/backend/tests/unit/test_ingestion.py scripts/tests/test_youth_employment.py
```

`data-fetch` downloads two World Bank JSON responses and four approved World Bank PDFs into `data/raw/`. `.gitignore` contains rules for raw and derived data; this workspace has no Git metadata, so tracked/ignored status is not verified. `data-verify` checks the enabled source hashes without network access.

## Expected Results

- Each indicator response contains 44 rows for the four ISO3 countries and years 2015-2025.
- Four World Bank PDF sources are verified and recorded. During acquisition, PyMuPDF checks structure and transient text extractability without retaining validation text; `data-parse` separately emits canonical text blocks without OCR. ILO-published PDFs are not part of the corpus. The Singapore MOM candidate remains disabled for rights review.
- `data-parse` writes content-addressed canonical structured/report outputs under `data/canonical/`, per-source quality reports under `data/processed/quality/`, and an append-only `data/manifests/ingestion-manifest.json`.
- `data-eda` writes two figures and a reproducible findings summary under `docs/data/eda/`, plus an append-only `data/manifests/eda-manifest.json`.
- The generated `data/manifests/download-manifest.json` records exact timestamps, response metadata, bytes, SHA-256, file paths, and any safe errors.
- Repeated acquisition uses HTTP validators when available and verifies the prior local hash before reporting `unchanged`.

Automated tests use fixtures and mocked HTTP; they do not contact live sources. This feature parses structured JSON and PDFs but does not run OCR, chunk, embed, index, retrieve, or generate answers.