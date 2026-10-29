# 2. Data Sheet: Data Preparation and Exploratory Analysis

> Assignment §2 and the "data sheet" deliverable: two source types, provenance, licences, schema, missing values, cleaning, transformations, quality checks, and at least two exploratory findings. No confidential or personal data is used or sent to any external service.

| Assignment item | Where |
|---|---|
| Two or more source types | Structured: 2 World Bank indicator JSON snapshots. Unstructured: 4 World Bank PDF reports. |
| Provenance and licences | [Sources and Provenance](#sources-and-provenance); full terms in `data/manifests/sources.yaml`. |
| Schema, missing values, cleaning, quality checks | [Schema and Units](#schema-and-units), [Missingness and Quality](#missingness-and-quality), [Transformations and Exclusions](#transformations-and-exclusions). |
| Two or more findings | [Exploratory Analysis](#exploratory-analysis): youth unemployment fell in three of four countries 2015–2025 (India −8.9 pp) and rose in Malaysia (+1.0 pp). In 2025 youth rates were 4.0–11.8 pp above total rates. |
| Known quality issues | PDFs parsed without OCR; two PDFs each have one empty text page; modelled estimates, not surveys; India report covers five states only; Singapore report is historical (1970, 1990, 2010). |

## Summary

This corpus contains two World Bank Indicators API JSON snapshots and four parsed World Bank PDF reports for Singapore, Malaysia, Indonesia, and India. It supports noncommercial policy research about unemployment, jobs, skills, informality, and workforce development. It is not a complete or representative account of any country's labor market and is not a final authority for consequential decisions.

No ILO-published report PDFs are included. The unemployment indicators are distributed by the World Bank but identify ILOSTAT as the upstream data source. The Singapore MOM youth report remains disabled because its PDF requires written permission for further reproduction.

## Sources and Provenance

| Source | Retrieved (UTC) | Publisher / publication date | Coverage | Licence and attribution | Snapshot |
|---|---|---|---|---|---|
| `wb-youth-unemployment-1524-2015-2025` | 2026-10-25T14:26:09Z | ILOSTAT, distributed via World Bank Data | SGP, MYS, IDN, IND; 2015-2025 | CC BY 4.0; credit ILOSTAT and World Bank Data, include access date and indicate changes | `data/raw/structured/wb-youth-unemployment-1524-2015-2025/5d9da42f9cabafe5788093910dbff45c684cba9a1baad0d4cab993790b281085.json`; 11,728 bytes; SHA-256 `5d9da42f9cabafe5788093910dbff45c684cba9a1baad0d4cab993790b281085` |
| `wb-total-unemployment-2015-2025` | 2026-10-25T14:26:09Z | ILOSTAT, distributed via World Bank Data | SGP, MYS, IDN, IND; 2015-2025 | CC BY 4.0; credit ILOSTAT and World Bank Data, include access date and indicate changes | `data/raw/structured/wb-total-unemployment-2015-2025/ff45778aa411adc612e8df5ae4856b63894c3c91e46c02b4be4e5e30709c722e.json`; 10,928 bytes; SHA-256 `ff45778aa411adc612e8df5ae4856b63894c3c91e46c02b4be4e5e30709c722e` |
| `wb-indonesia-jobs-action-2018` | 2026-10-25T13:32:28Z | World Bank Group; 2018-08-01 | Indonesia | Noncommercial whole/partial reproduction with full attribution; not a CC licence; third-party rights may differ | `data/raw/reports/wb-indonesia-jobs-action-2018/f98fce9bbc0f1485f04e2e6167fc157dcdf512223fab100428006ecacf39dcd6.pdf`; 5,070,687 bytes; SHA-256 `f98fce9bbc0f1485f04e2e6167fc157dcdf512223fab100428006ecacf39dcd6` |
| `wb-malaysia-informal-employment-2024` | 2026-10-25T13:32:28Z | World Bank Group; 2024-02-22 | Malaysia | Noncommercial whole/partial reproduction with full attribution; not a CC licence; third-party rights may differ | `data/raw/reports/wb-malaysia-informal-employment-2024/9b8c5d178441665072dbf7ff3700b1e016dc68a3c5fdfd24b8dfad040479f434.pdf`; 5,979,744 bytes; SHA-256 `9b8c5d178441665072dbf7ff3700b1e016dc68a3c5fdfd24b8dfad040479f434` |
| `wb-india-skills-programs-2015` | 2026-10-25T14:14:24Z | World Bank Group; 2015-04-01 | Assam, Andhra Pradesh, Madhya Pradesh, Odisha, Rajasthan | CC BY 3.0 IGO; cite DOI 10.1596/22391, attribute World Bank and indicate changes; third-party rights may differ | `data/raw/reports/wb-india-skills-programs-2015/6ba3938f4f02e26016169b99233f45688903580e5956f2bf8d16eb1c14437ce5.pdf`; 775,995 bytes; SHA-256 `6ba3938f4f02e26016169b99233f45688903580e5956f2bf8d16eb1c14437ce5` |
| `wb-singapore-workforce-development-2012` | 2026-10-25T14:10:53Z | World Bank; 2012-01-01 | Singapore; workforce-development benchmarks for 1970, 1990, and 2010 | CC BY 3.0 IGO; cite DOI 10.1596/17646, attribute World Bank and indicate changes; third-party rights may differ | `data/raw/reports/wb-singapore-workforce-development-2012/65375db3691597f0814c757e2ddc6163739180c2bfe6699ce021eaa1388c8db2.pdf`; 2,421,351 bytes; SHA-256 `65375db3691597f0814c757e2ddc6163739180c2bfe6699ce021eaa1388c8db2` |

The exact source URLs, retrieval timestamps, validators, and complete terms are maintained in `data/manifests/sources.yaml`. Per-run attempts, including the removed ILO report acquisitions, remain in the append-only `data/manifests/download-manifest.json`.

## Schema and Units

The structured sources each contain 44 records: four ISO3 country codes by 11 years. Each API record has an indicator ID and label, country code/name, year, numeric value or JSON `null`, unit, observation status, and decimal precision. The indicator labels define the values as percentages: youth unemployment is a percentage of the labor force ages 15-24; total unemployment is a percentage of the total labor force. The API `unit` field is empty in the retrieved snapshots and is preserved as received.

Structured data is converted to canonical observations with stable country/year keys, ISO2/ISO3 dimensions, units/status/decimal fields, API `lastupdated`, source provenance, and the raw response hash. PDFs are converted into canonical report documents containing page numbers, text blocks, section paths, bounding boxes, character offsets, parser version, content hash, and source/license provenance. PDF text is extracted for the canonical representation, but no OCR is performed.

## Missingness and Quality

Both retrieved indicator snapshots contain zero null values and 44 unique country/year keys each. These counts describe the current snapshots only; future upstream revisions may change values or introduce nulls. Quality checks preserve nulls, report missing country/year keys and duplicate keys, and do not impute or interpolate. Current quality output reports zero duplicate/missing keys for both indicators.

PDF quality checks record page count, text-block count, extracted-text character count, duplicate block IDs, empty pages, and offset validity. The current reports parsed as follows: Indonesia 26 pages/164 blocks/51,549 characters; Malaysia 102 pages/2,511 blocks/259,265 characters; India 39 pages/283 blocks/98,783 characters; Singapore 75 pages/911 blocks/285,336 characters. Indonesia and Malaysia each have one empty text page. Scanned-only content may be absent because OCR is not applied. Credited third-party content may have rights separate from the report licence and requires review before reuse.

## Transformations and Exclusions

Raw API response bytes and PDF snapshots are immutable and are not rewritten. Structured parsing converts year strings to integers and values to numeric-or-null fields while preserving dimensions and provenance. PDF parsing groups text into page-local blocks and assigns stable IDs, sections, and offsets. No causal inference, normalization of indicator values, or imputation is performed.

The four-country indicator panel is limited to SGP, MYS, IDN, and IND. The India skills-program report covers five states and is not nationally representative. The Singapore SABER report is historical rather than current labor-market evidence. The Singapore MOM youth report is excluded pending written reproduction permission. Two previously acquired ILO PDFs are excluded from the current corpus; their files were removed while their acquisition attempts remain auditable in the manifest.

## Refresh and Evaluation

The source registry uses manual refresh. A changed upstream file creates a new content-addressed snapshot; existing snapshots are not overwritten. The acquisition command uses conditional HTTP validators when available and verifies hashes before reporting `unchanged`.

The source documents are not split; the 67-case evaluation set (`data/evaluation/feature007-cases.json`) carries `dev` and `test` labels, is versioned separately, and must stay distinct from runtime prompts and tuning data (see [problem framing](01-problem-framing.md)).

## Exploratory Analysis

Two descriptive outputs are generated from the canonical structured datasets: youth unemployment trends by country from 2015-2025, and a 2025 comparison of youth and total unemployment rates. The comparison uses different denominators and is descriptive, not causal. Results, tables, caveats, and figure links are in [`docs/data/eda/results.md`](02-data-sheet.md).

## Reproduction

```bash
make data-fetch
make data-verify
make data-parse
make data-eda
```

The append-only acquisition, ingestion, and EDA manifests record input/output hashes, tool versions, parameters, and findings. Canonical and EDA outputs are reproducible from immutable raw snapshots and the parser/analysis code. `.gitignore` excludes `data/raw/`, `data/canonical/`, `data/processed/` and `data/indexes/`, so a fresh clone must run the commands above (and `make retrieval-index`) to rebuild them. Source manifests, evaluation cases and run manifests are tracked.
