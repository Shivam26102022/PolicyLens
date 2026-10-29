# Feature 003 Data Model

## Canonical Source Input

The indexer reads `data/manifests/ingestion-manifest.json` and `data/manifests/sources.yaml`. For each enabled source, it selects the latest successful parse record matching the registry's current raw SHA-256, then verifies the canonical file exists and matches its recorded hash. Stale parser-version folders and disabled/manual-review sources are not indexed. A source is eligible only when `allowed_usage` contains `retrieval` and provenance includes a verified source ID, source hash, licence, and sensitivity.

## Entities

### `SourceArtifact`

| Field | Type | Rules |
|---|---|---|
| `source_id` | string | Stable registry key. |
| `canonical_path` | relative path | Must remain under `data/canonical/`. |
| `canonical_sha256` | lowercase SHA-256 | Must match the file before indexing. |
| `source_content_sha256` | lowercase SHA-256 | Original raw snapshot hash. |
| `parser_version` | string | Exact parser version from canonical record. |
| `source_type` | `structured` or `report` | Selects row or block extraction. |
| `title`, `publisher`, `source_uri` | string | Preserved for retrieval/citations. |
| `licence`, `usage_constraints` | string/null | Preserved; not inferred or broadened. |
| `sensitivity` | `public`, `synthetic`, or `anonymised` | Copied from source metadata. |
| `allowed_usage` | tuple of strings | Must include `retrieval`; otherwise fail closed. |

### `BlockLocation`

Identifies one canonical report span: `page_number` (1-based), `block_id`, `start_char`, and `end_char`. Offsets refer to the canonical block text. A passage may preserve multiple locations when it joins adjacent blocks/pages; it never joins across documents or section boundaries.

### `StructuredRowKey`

Identifies one indicator observation using `dataset_id`, `observation_id`, `indicator_id`, `country_iso3`, and `year`. The retrieved text is a deterministic rendering of the canonical observation fields; the original structured row values remain authoritative.

### `CorpusPassage`

| Field | Type | Rules |
|---|---|---|
| `passage_id` | string | `sha256:` plus SHA-256 of source ID, source content hash, strategy version, ordered location/row keys, passage text hash, and deterministic table row/cell/fragment identity when present. |
| `source_id`, `document_id` | string | Stable provenance identifiers. |
| `title`, `publisher`, `source_uri` | string | Source display and citation metadata. |
| `text` | string | Verbatim bounded report text or deterministic structured-row rendering; this is the returned/cited text. |
| `embedding_text` | string | Title/section-prefixed representation sent to the embedder; never used as the citation excerpt. |
| `text_sha256` | lowercase SHA-256 | Hash of UTF-8 passage text. |
| `embedding_text_sha256` | lowercase SHA-256 | Hash of the exact contextual representation used for embedding and cache lookup. |
| `source_content_sha256` | lowercase SHA-256 | Immutable raw source hash. |
| `chunker_version` | string | Strategy and version included in ID. |
| `locations` | tuple of `BlockLocation` | Reports; at least one location. |
| `row_key` | `StructuredRowKey/null` | Structured data; required for structured rows. |
| `section_path` | tuple of strings | Canonical headings, empty only for a row without a section. |
| `token_count` | integer | Count of the actual contextual embedding representation; positive and at most 500 for the default local model. |
| `licence`, `usage_constraints` | string/null | Exact provenance copied from canonical source. |
| `sensitivity` | enum | Source sensitivity; never user-controlled. |
| `permission_scope` | string | Derived by the trusted indexer; current active corpus uses `public`. |
| `allowed_usage` | tuple of strings | Must include `retrieval`. |
| `country_iso3`, `year`, `indicator_id` | optional scalar metadata | Added for structured rows and searchable filters. |

Stable IDs change when source content, parser output, chunk strategy/version, block spans, row keys, or passage text changes. IDs do not depend on build time or query order.

### `ChunkerConfig`

Versioned configuration with `strategy`, `version`, `target_tokens`, `min_tokens`, `max_tokens`, `overlap_tokens`, tokenizer/model identifier, heading/list/table behavior, and contextual title/section settings. The required comparison is fixed-size 500/75, structure-aware 450 target/120 minimum/500 maximum/75 overlap, and structure-aware 250 target/80 minimum/350 maximum/50 overlap. All token counts include the contextual embedding representation. Tables remain atomic when they fit; oversized row groups repeat headers. A single oversized multi-column row is split into column-labelled cell fragments; when cell offsets cannot be mapped to the flattened PDF table text, each fragment cites the full canonical table-block span. No text is silently truncated.

### `EmbeddingDescriptor`

Contains `provider`, `model_id`, provider/library version, model artifact revision/hash when available, licence, pooling, tokenizer, output dimension, normalization, maximum input tokens, and query/document embedding methods. The local BGE descriptor records its FastEmbed snapshot revision, ONNX SHA-256, MIT licence, first-token CLS pooling, L2 normalization, and the distinct `query_embed`/`passage_embed` methods. A Chroma collection has exactly one descriptor; mismatch fails startup/build validation and requires a new full index.

### `EmbeddingCacheRecord`

An ignored local cache entry is keyed by a SHA-256 over provider, model ID, package version, model revision/artifact hash, and `embedding_text_sha256`. It stores only the normalized passage vector, dimension, cache-key inputs, and vector checksum. Reads validate the key, dimension, checksum, finite values, and normalization before reuse. Query vectors are never persisted; cache misses re-embed without truncation or provider fallback.
Contains `schema_version`, `build_id`, deterministic `index_version`, start/finish timestamps, status, sorted source IDs and canonical/raw input hashes, aggregate corpus hash, chunker configuration/version, tokenizer and BM25 parameters/version, embedding descriptor, Chroma configuration, document/row/passage counts, validation results, query smoke results, elapsed time, relative local output paths, and safe failure code. The Chroma output hash is a logical checksum over its sorted collection metadata, IDs, documents, record metadata, and vectors; it is stable across SQLite/WAL updates on restart. BM25S output uses a deterministic directory checksum. It contains no API keys, raw user queries, or passage text.

### `IndexBuildManifest`

Append-only record with `schema_version`, `build_id`, deterministic `index_version`, start/finish timestamps, status, sorted source IDs and canonical/raw input hashes, aggregate corpus hash, chunker configuration/version, tokenizer and BM25 parameters/version, embedding descriptor, Chroma configuration, document/row/passage counts, validation results, query smoke results, elapsed time, relative local output paths, and safe failure code. It contains no API keys, raw user queries, or passage text.

The deterministic `index_version` is SHA-256 over canonical input hashes, chunker/tokenizer config, embedder identity/dimension, and index schema version. The `build_id` is unique per attempt and is not used as a passage ID.

### `ActiveIndexPointer`

Atomic JSON at `data/indexes/active-index.json` with schema version, active `build_id`/`index_version`, the previous verified pointer, manifest path/hash, UTC update timestamp, and optional `previous_validation_error`. It is written only after all validation passes. A failed build never changes it. If the prior pointer is corrupt/incompatible, a newly validated build may activate but records that error and does not offer the unverified build for rollback. Rollback atomically restores a verified previous pointer; no build directory is deleted by rollback.

### `RetrievalFilters`

Optional restrictive filters for source IDs, country ISO3 codes, years, and indicator IDs. Callers cannot request or grant permission scopes. The API derives allowed scopes from trusted service configuration (currently `public`); Chroma and BM25 results are filtered by those scopes and by `allowed_usage` before passage text is returned. Missing permission metadata is ineligible.

### `RetrievalRequest`

Contains non-empty bounded `query`, `mode` (`bm25`, `dense`, or `hybrid`), `top_k` clamped to 1-20, and `RetrievalFilters`. It cannot select an embedding model, permission scope, index path, arbitrary source URL, or raw filesystem path.

### `RetrievedEvidence` and `RetrievalRun`

`RetrievedEvidence` contains passage ID/text, source/title/publisher/URI/hash/licence, page/section or structured row key, rank and score per retrieval channel, fused score, optional cross-encoder score, retrieval mode, and index version. `RetrievalRun` contains a random `run_id`, index version, status (`found` or `no_results`), ordered evidence, bounded context assembled from evidence, and optional `RetrievalRerankingDiagnostics` (`method`, configured model ID, candidate count, duration, and stable error code). Diagnostics distinguish completed reranking from failure; failed reranking preserves the original hybrid order. Retrieval/provider/index failures use separate stable error codes and do not become `no_results`.

### `Citation`, `Claim`, and `CitationValidationResult`

A citation includes `claim_id`, source ID/title/URI, passage ID, page/section or row key, exact bounded excerpt, source content hash, retrieval rank/score, and retrieval mode. Validation accepts only citations whose passage belongs to the specified current run and whose excerpt is an exact substring of the stored passage text. It checks claim and citation IDs, source/hash/location consistency, excerpt length, and uniqueness. It validates evidence linkage, not semantic entailment; the result must not claim model-grounded truth.

### `RetrievalRunRegistry`

A bounded in-memory TTL registry maps recent random run IDs to the evidence returned for those runs. It is required by the citation-validation endpoint so the client cannot submit its own trusted evidence. Expired/unknown run IDs fail closed. Stored evidence is not logged or persisted; registry capacity and TTL are configuration constants with tests.

### `BaselineAnswerRequest`, `BaselineClaimDraft`, and `BaselineAnswerResponse`

The request contains the bounded retrieval query, mode, top-k, and restrictive filters; callers cannot select a generation provider or model. The OpenAI structured draft contains only an `answered`/`abstained` status and claim text with one or more `{passage_id, excerpt}` references. Each claim's text must exactly equal at least one excerpt, and each excerpt must be an exact substring of its referenced passage. The server resolves references against the current `RetrievalRun`, constructs full citations from trusted metadata, and passes them through `CitationValidator`; model-supplied source titles, URLs, hashes, ranks, or locations are never trusted. Provider-backed responses include generation provider, model ID, and prompt version; no-evidence abstentions have no generation metadata. The response also contains the retrieval run/index identity, status (`answered`, `abstained`, or `failed_safe`), extractive claims with server-derived citations, and an optional stable error code. No-evidence requests abstain before calling generation; malformed output, paraphrased claims, unknown passages, invalid excerpts, or uncovered factual claims fail safely.

### `RetrievalCase` and `RetrievalEvaluation`

A frozen engineering case contains `case_id`, query, restrictive metadata filters, and one or more expected location anchors (source ID plus page/section or structured row key and a verified text marker). The evaluator maps anchors to passages separately for each chunking strategy. The set is author-curated, versioned, not independently human-reviewed, and not representative of Feature 007's later evaluation set.

Evaluation output records per-mode/per-chunker `Recall@k`, binary `nDCG@k`, MRR, empty-result rate, citation-link completeness, query latency, counts, input/index hashes, configuration, and failures. `hybrid+cross_encoder` is measured separately from the unchanged hybrid baseline and reports reranking attempt/completion/failure/no-candidate counts. Answer selection quality and source accuracy are explicitly `not_measured`: the baseline returns only verbatim cited excerpts, but the author-curated retrieval cases are not an answer-quality or source-validity evaluation.

## Lifecycle

```text
canonical manifest + source registry
  -> verify current input hashes and retrieval permission
  -> extract structured rows and report blocks
  -> chunk and assign stable passage IDs
  -> embed and build isolated Chroma/BM25S artifacts
  -> validate metadata, dimensions, counts, samples, persistence, filters, smoke cases
  -> append build manifest
  -> atomically activate new pointer
  -> retain previous pointer for rollback
```

A build is never activated if any source, embedding, BM25S, Chroma, permission, or smoke validation fails.
