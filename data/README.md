# PolicyLens Initial Dataset

## Topic and scope

This corpus supports noncommercial policy research on employment and youth unemployment for Singapore (`SGP`), Malaysia (`MYS`), Indonesia (`IDN`), and India (`IND`). The structured World Bank indicators cover 2015-2025:

- `SL.UEM.1524.ZS`: youth unemployment, ages 15-24, percent of the youth labour force.
- `SL.UEM.TOTL.ZS`: total unemployment, percent of the labour force.

The two original World Bank Indicators API JSON responses are stored unchanged. Four approved World Bank PDFs add labour-market evidence for Indonesia, Malaysia, and India, plus historical Singapore workforce-development context. The 2015 India report examines skills programs in five states. ILO-authored reports are not included. The Singapore MOM youth report remains disabled pending rights review.

## Source selection and provenance

The active sources are defined in [`manifests/sources.yaml`](manifests/sources.yaml): two World Bank Indicators API JSON responses and four World Bank PDF reports. Each entry records publisher, canonical item/data URL, direct download URL, publication date when available, parser validation metadata, rights, attribution, use constraints, countries, years, and deterministic local path template.

The World Bank API supports JSON, country-list and year-range requests, pagination, and unauthenticated access. The two retained indicators are modeled ILO estimates, not national-estimate series; their pages identify ILOSTAT as upstream and CC BY 4.0 as the data licence. Attribute both ILOSTAT and World Bank Data, include the access date, and state any changes.

Statistics-tool permission is separate from retrieval permission in the source registry. Only `wb-youth-unemployment-1524-2015-2025` and `wb-total-unemployment-2015-2025` include `statistics` in `allowed_usage`. `query_statistics` may aggregate those two series only; it must preserve ILOSTAT/World Bank Data attribution and identify results as modeled ILO estimates. The PDF reports are not approved for this tool.

The Singapore SABER report and India skills-program report have verified CC BY 3.0 IGO records in the World Bank Open Knowledge Repository. Attribute the World Bank, cite DOI 10.1596/17646 for Singapore and DOI 10.1596/22391 for India, indicate changes, and review credited third-party content. The Indonesia and Malaysia World Bank reports permit whole or partial reproduction for noncommercial purposes with full attribution; they are not CC-licensed. Their copies remain local and are not redistributed. Do not reuse third-party components without checking their rights or use institutional logos or imply endorsement.

## Acquire and verify

```bash
make data-fetch
make data-verify
uv run --locked --package policylens pytest scripts/tests/test_download_data.py
```

No API key or secret is needed. The downloader uses only allow-listed HTTPS URLs, checks redirects, applies bounded timeouts/retries/request spacing and a 50 MiB default size cap, validates JSON/PDF responses, and writes through a temporary `.part` file before atomic placement.

Raw snapshots are stored under:

```text
data/raw/structured/<source_id>/<sha256>.json
data/raw/reports/<source_id>/<sha256>.pdf
```

`data/manifests/download-manifest.json` appends a record for every run and source attempt, including status, actual retrieval time, HTTP status, final URL, media type, bytes, SHA-256, local path, elapsed time, and safe failure details. The source registry's `retrieved_at`, latest successful `sha256`, and HTTP validators are updated from actual responses. A failed attempt is never labeled downloaded.

## Rights and attribution

`data-fetch` skips the Singapore MOM report: its PDF says all rights reserved and further reproduction requires written permission. For the World Bank indicator series, credit ILOSTAT and World Bank Data and identify the estimates as modeled. For the Singapore SABER and India skills reports, attribute the World Bank, include the DOI, indicate changes, and check third-party content. For the Indonesia and Malaysia World Bank reports, use full item-page attribution and noncommercially only. The two ILO-published PDFs are excluded from the current corpus.

## Data limitations and missing values

The World Bank series are modeled ILO estimates; they can be revised and are not national-estimate series. API `null` values remain null. The downloader does not impute, interpolate, aggregate, or transform observations. Each indicator response contains 44 country-year records for the four countries and 2015-2025 years.

In the 2026-10-25 snapshot, both 44-row indicator responses contained zero null values. This describes the retrieved version, not a promise about future revisions.

The World Bank India skills report covers Assam, Andhra Pradesh, Madhya Pradesh, Odisha, and Rajasthan; it is not nationally representative. The Singapore SABER report benchmarks workforce-development systems in 1970, 1990, and 2010; published in 2012, it is historical policy context rather than a current labour-market measure. The reports contextualize, rather than directly measure, every country-year indicator. Sampling, methodology, temporal, and coverage limitations described by publishers remain applicable. Acquisition-time PDF eligibility text is discarded; `make data-parse` subsequently extracts report text into canonical page/block records. No OCR is performed.

## Changed upstream sources

The downloader sends `If-None-Match` or `If-Modified-Since` when a prior manifest provides a validator and accepts `304 Not Modified` only if the referenced local snapshot still matches its SHA-256. If upstream bytes change, the new checksum creates a new path. Existing snapshots are never overwritten or deleted. The source registry points to the latest successful snapshot; the append-only download manifest preserves prior attempts and checksums.

## Intentionally excluded

This Feature 002 slice includes acquisition, canonical parsing, quality checks, a data sheet, and two descriptive EDA outputs. It does not run OCR, generate chunks or embeddings, build Chroma/BM25 indexes, run retrieval/RAG, implement MCP tools, or build the backend/frontend experience; those remain later feature work.

## Verified Acquisition Snapshot

The current corpus contains two structured World Bank JSON responses and four World Bank reports, totaling 14,270,433 raw bytes. The expanded quickstart was run in a fresh isolated Python 3.12.14 environment: locked sync installed 69 packages; `make data-fetch` returned `unchanged` for all six enabled sources and skipped the disabled MOM candidate; `make data-verify` passed for all six; `make data-parse` and `make data-eda` produced canonical datasets/documents, quality reports, two figures, and a results summary; the offline downloader suite passed (20 tests); and the focused ingestion/EDA suite passed (11 tests). The EDA outputs are in [`docs/data/eda/results.md`](../docs/data/eda/results.md). This used the existing workspace source tree, not a clean Git checkout; the workspace has no Git metadata, so ignore/tracking status could not be verified.

| Source ID | Retrieved at (UTC) | Local path | Bytes | SHA-256 |
|---|---|---|---:|---|
| `wb-youth-unemployment-1524-2015-2025` | 2026-10-25T14:26:09Z | `data/raw/structured/wb-youth-unemployment-1524-2015-2025/5d9da42f9cabafe5788093910dbff45c684cba9a1baad0d4cab993790b281085.json` | 11,728 | `5d9da42f9cabafe5788093910dbff45c684cba9a1baad0d4cab993790b281085` |
| `wb-total-unemployment-2015-2025` | 2026-10-25T14:26:09Z | `data/raw/structured/wb-total-unemployment-2015-2025/ff45778aa411adc612e8df5ae4856b63894c3c91e46c02b4be4e5e30709c722e.json` | 10,928 | `ff45778aa411adc612e8df5ae4856b63894c3c91e46c02b4be4e5e30709c722e` |
| `wb-indonesia-jobs-action-2018` | 2026-10-25T13:32:28Z | `data/raw/reports/wb-indonesia-jobs-action-2018/f98fce9bbc0f1485f04e2e6167fc157dcdf512223fab100428006ecacf39dcd6.pdf` | 5,070,687 | `f98fce9bbc0f1485f04e2e6167fc157dcdf512223fab100428006ecacf39dcd6` |
| `wb-malaysia-informal-employment-2024` | 2026-10-25T13:32:28Z | `data/raw/reports/wb-malaysia-informal-employment-2024/9b8c5d178441665072dbf7ff3700b1e016dc68a3c5fdfd24b8dfad040479f434.pdf` | 5,979,744 | `9b8c5d178441665072dbf7ff3700b1e016dc68a3c5fdfd24b8dfad040479f434` |
| `wb-india-skills-programs-2015` | 2026-10-25T14:14:24Z | `data/raw/reports/wb-india-skills-programs-2015/6ba3938f4f02e26016169b99233f45688903580e5956f2bf8d16eb1c14437ce5.pdf` | 775,995 | `6ba3938f4f02e26016169b99233f45688903580e5956f2bf8d16eb1c14437ce5` |
| `wb-singapore-workforce-development-2012` | 2026-10-25T14:10:53Z | `data/raw/reports/wb-singapore-workforce-development-2012/65375db3691597f0814c757e2ddc6163739180c2bfe6699ce021eaa1388c8db2.pdf` | 2,421,351 | `65375db3691597f0814c757e2ddc6163739180c2bfe6699ce021eaa1388c8db2` |

The four World Bank reports and two structured series form the active corpus. The Singapore MOM manual-review candidate remains disabled and was not downloaded. The append-only acquisition manifest retains historical attempts for the removed ILO reports; the current source registry contains only the active series, reports, and disabled MOM candidate. `data/manifests/ingestion-manifest.json` and `data/manifests/eda-manifest.json` record derived-stage inputs, outputs, versions, findings, and hashes.