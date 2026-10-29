# Research: Initial Dataset Acquisition

## Decisions

### Structured indicators

- Use the official World Bank Indicators API v2 and preserve the returned JSON response bytes unchanged.
- Issue one request per indicator, with `country/SGP;MYS;IDN;IND`, `date=2015:2025`, `format=json`, and `per_page=1000`.
- Official API documentation confirms JSON output, semicolon-delimited multiple countries, date-range syntax, pagination, and that API keys are not required.
- The exact request was tested against the live API on 2026-10-25. Each response contained one page, 44 records, the four requested ISO3 country codes, and years 2015-2025.
- Official indicator pages identify ILOSTAT as the source and CC BY 4.0. Cite ILOSTAT and World Bank Data, record the retrieval date, and indicate any changes. The API payload itself is retained as received.

Primary references:

- [World Bank Indicators API documentation](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
- [World Bank API call structure](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures)
- [Youth unemployment indicator](https://data.worldbank.org/indicator/SL.UEM.1524.ZS)
- [Total unemployment indicator](https://data.worldbank.org/indicator/SL.UEM.TOTL.ZS)
- [World Bank Data Access and Licensing](https://datacatalog.worldbank.org/public-licenses)

### Active World Bank Reports

1. **Indonesia Jobs Action Program Towards Win-Win: A Labor Reform Strategy to Benefit All** (document date 1 August 2018). The report permits whole or partial reproduction for noncommercial purposes with full attribution; this is not a CC licence. It discusses Indonesia jobs, youth unemployment, skills, and labour reform.
2. **Informal Employment in Malaysia: Trends, Challenges and Opportunities for Reform** (22 February 2024). The report permits whole or partial reproduction for noncommercial purposes with full attribution; this is not a CC licence. It documents employment characteristics, vulnerabilities, methods, and policy reforms.
3. **Labor Market Impacts and Effectiveness of Skills Development Programs in 5 States in India** (April 2015). The World Bank Open Knowledge Repository record lists CC BY 3.0 IGO. It analyzes employment and earnings outcomes of skills programs across Assam, Andhra Pradesh, Madhya Pradesh, Odisha, and Rajasthan; it is not nationally representative.
4. **SABER Workforce Development Country Report: Singapore 2012**. The World Bank Open Knowledge Repository record lists CC BY 3.0 IGO. It benchmarks workforce-development systems in 1970, 1990, and 2010 and should be treated as historical policy context.

The active report set contains these four World Bank PDFs only. CC BY reports require attribution and change indication; credited third-party material may have separate rights. For the Indonesia and Malaysia reports, use is noncommercial with full attribution. All report files remain local and are not redistributed.

### Manual-review candidates

**Youths In The Labour Market 2025** (Singapore Ministry of Manpower, released 26 March 2026). Official item page: <https://stats.mom.gov.sg/Pages/Youths-In-The-Labour-Market-2025.aspx>. Direct PDF: <https://stats.mom.gov.sg/iMAS_PdfLibrary/mrsd-Youths-in-the-Labour-Market-2025.pdf>. The item page confirms youth employment/skills content; the PDF copyright page states “All rights reserved” and says further reproduction requires written permission. MOM's general Terms of Use identify fair-dealing exceptions for private study/research only as permitted by Singapore law. Because applicability to corpus storage and retrieval is unclear, the source remains disabled for manual rights review and is not downloaded.

Primary rights references:

- [World Bank Documents & Reports API](https://documents.worldbank.org/en/publication/documents-reports/api)
- [World Bank Open Knowledge Repository Terms of Use](https://openknowledge.worldbank.org/pages/terms-of-use/en)

## Acquisition Design Decisions

- Use only the explicit hosts needed by active sources: `api.worldbank.org`, `data.worldbank.org`, `documents.worldbank.org`, and `documents1.worldbank.org`; validate redirect destinations against the same allow-list.
- Fetch sources sequentially with at least 250 ms between requests; this small explicit rate limit is part of the acquisition configuration.
- Use existing locked `httpx2` for independent connection/read timeouts and deterministic mocked HTTP tests. Add PyYAML and PyMuPDF as locked development dependencies only.
- Store original files under content-addressed source paths. Never overwrite a snapshot; a changed response creates a new SHA-256 path.
- Send `If-Modified-Since`/`If-None-Match` when a prior successful manifest record provides a validator. A 304 is accepted only after the prior local file's SHA-256 is rechecked.
- Download JSON bytes unchanged; parse only in memory for schema/coverage validation. For PDFs, validate content type, signature, structural readability, page count, and nontrivial extractable text; do not generate parsed documents or OCR.
- The downloader processes only registry entries with verified rights and `acquisition_enabled: true`. The active corpus is two World Bank-distributed structured indicator responses and four World Bank reports; ILO-published PDFs are excluded. A manual-review source is never fetched.
- The download manifest is append-only by run and updated atomically after each source attempt. `sources.yaml` receives the actual latest `retrieved_at` and latest successful `sha256`; prior content-addressed snapshots and attempt records remain. It stores safe errors and no secrets. Since the workspace is not a Git repository, `git_commit` is null and the downloader script hash is recorded instead.

## Alternatives Considered

- **World Bank CSV/ZIP download:** not selected because the request explicitly requires original JSON API responses and the API supports that format directly.
- **World Bank India skills report:** initially held for manual review, then selected after the Open Knowledge Repository record confirmed CC BY 3.0 IGO.
- **U.S. Bureau of Labor Statistics data:** not selected because it does not match the four-country scope.
- **Web crawling or search-result scraping:** rejected; use official item pages and direct file links only.
- **Parsing/canonicalization during acquisition:** rejected; these run as separate Feature 002 stages against verified immutable snapshots. OCR and indexing remain out of scope for Feature 002.

## Unresolved Limitations

- The Singapore report is historical and does not provide a current labour-market series.
- Indicator values are modeled ILO estimates and may be revised. The raw response's `lastupdated`, retrieval timestamp, and hash must be retained; values may be null and are not imputed. No ILO-published report PDFs are in the active corpus.
- World Bank noncommercial terms and third-party-content exclusions must be respected. Commercial use, external redistribution, or reuse of third-party components requires additional rights review.