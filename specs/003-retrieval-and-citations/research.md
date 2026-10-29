# Feature 003 Research

**Date**: 2026-10-25

## Decisions

### Local embeddings

Use FastEmbed with `BAAI/bge-small-en-v1.5` as the default local model. The official FastEmbed registry reports 384 dimensions, a 512-token input limit, MIT licensing, and an approximately 0.067 GB quantized ONNX artifact. FastEmbed uses ONNX Runtime, supports separate `query_embed` and `passage_embed` paths, exposes `embedding_size` and tokenizer-backed `token_count`, and supports a configurable local cache. Pin the FastEmbed package in `uv.lock`; record package version, model name, model-file SHA-256 where available, vector dimension, and normalization in each index manifest. Use CPU inference by default. Model files are downloaded on first use and remain outside the repository.

Rationale: this provides a genuinely local default without adding a Torch runtime, supports the required model-aware chunk token checks, and is small enough for the current corpus. Record the observed FastEmbed snapshot revision and ONNX file SHA-256, MIT license, first-token CLS pooling, and L2 normalization. Normalize vectors explicitly and validate finite values and dimensions before indexing. Persist passage vectors in the ignored local cache keyed by provider/model/package/revision/artifact hash plus the contextual embedding-text hash; never persist query embeddings.

### Optional API embeddings

Use the existing OpenAI SDK through an explicit `EMBEDDING_PROVIDER=openai` selection and the configured `OPENAI_EMBEDDING_MODEL`; keep the default local. Use `tiktoken` with the configured model's encoding to enforce the API input limit without truncation. No automatic fallback or API call is allowed in tests. The provider/model/dimension are part of the index identity, so local and API vectors never share a collection. Selecting the API provider sends passage/query text to OpenAI; document this data flow and require explicit configuration. Discover and record the returned vector dimension rather than assuming it.

### Dense storage

Use Chroma's Python `PersistentClient` under the configured local index root, with a separate persistence directory/collection per immutable index build and cosine distance configured at collection creation. Supply embeddings explicitly; do not use Chroma's implicit default embedder. Disable anonymized telemetry. Use Chroma metadata `where` filters for source, country/year, sensitivity, and retrieval permission; validate permission metadata before returning text. Chroma documents automatic persistence for `PersistentClient` and metadata filters on `query`/`get`.

Rationale: this follows the master specification, keeps the database backend-owned and local, and makes rebuild/rollback boundaries explicit without adding a service.

### Keyword retrieval and fusion

Use BM25S for the local BM25 index. Its documented API supports indexing tokenized documents, retrieval, and save/load. Use a versioned deterministic Unicode word tokenizer (case-fold, retain alphanumeric terms, no stemming or stopword list) and record its name and BM25 parameters. Use reciprocal-rank fusion with `k=60`; sort equal fused scores by stable passage ID.

Rationale: BM25S is a maintained local library built on NumPy/SciPy, persists its index, and avoids an external search service. A deliberately simple tokenizer limits hidden language-dependent behavior.

### Chunking experiment

Compare three configurations on the same frozen case set:

- Fixed baseline: 500-token target, 75-token overlap.
- Structure-aware baseline: 450-token target, 120-token minimum, 500-token maximum, 75-token overlap.
- Structure-aware alternate: 250-token target, 80-token minimum, 350-token maximum, 50-token overlap.

Use FastEmbed's tokenizer to count the actual embedding representation, including title/section context, and reject rather than silently truncate any passage over the BGE limit. Keep headings with their first body block, preserve table rows/units and source locations, and never merge across source documents. Tables remain atomic when feasible; oversized row groups repeat headers. If a single multi-column row cannot fit, split cells under repeated column labels and cite the whole canonical table block when exact cell offsets are unavailable. The current corpus is English, so the English BGE model is appropriate. Treat these as experiment settings, not quality claims; select a default from measured retrieval outcomes without inventing a pass threshold.

### Retrieval and citation contracts

Expose keyword, dense, and hybrid retrieval through typed backend contracts. Apply source/permission filters before any passage text is returned. Bound candidate count and final context, de-duplicate identical/overlapping evidence, cap per-source dominance, and order ties deterministically. Return an explicit `no_results` state distinct from an index/provider failure. The non-agent baseline makes one bounded structured OpenAI Responses call only when explicitly configured and only after evidence is retrieved. It uses no tools, treats passages as untrusted input, returns only claim text exactly matching a current-run excerpt, and fails safely on paraphrased or invalid output.

Citations are claim-linked and valid only when their passage ID is in the current retrieval run and the excerpt is an exact bounded substring of that passage. Preserve source URI/hash, page/section or structured row key, retrieval rank/score, and index version. Do not accept fabricated or previously retrieved-but-not-current-run evidence.

### Frozen retrieval cases

No retrieval relevance set exists in the repository. Add a small versioned, corpus-derived engineering set with source/page/row location anchors. The evaluator maps each anchor to the passages produced by each chunking strategy, allowing a fair comparison despite strategy-specific passage IDs. Label this set as author-curated engineering evidence, not independently human-reviewed or representative of the future Feature 007 evaluation set. Do not tune a quality threshold to it. Record answer selection quality and source accuracy as not measured: although baseline claims are verbatim cited excerpts, this retrieval set is not an answer-quality or source-validity evaluation.

### Index lifecycle and reproducibility

Compute an index fingerprint from sorted canonical input hashes, chunker/tokenizer versions and settings, embedding provider/model/dimension, and index schema. Build Chroma and BM25S in a new, unique local build directory. Validate source/chunk counts, metadata, dimensions, finite vectors, round-trip samples, persistence, permission filters, and smoke retrieval before atomically replacing `data/indexes/active-index.json`. Preserve the previous pointer for rollback; failed or partial builds never activate. Keep the active index and generated vector/BM25 files ignored by repository rules. Append build/evaluation metadata and hashes to machine-readable manifests.

## Local Cross-Encoder Reranking

Use FastEmbed's `TextCrossEncoder` with `jinaai/jina-reranker-v1-tiny-en` as a local, CPU-only second-stage reranker for hybrid retrieval. Rerank at most 20 already permission-filtered candidates, using title/section context plus passage text. Preserve hybrid channel ranks/scores and provenance; use the cross-encoder score only to order candidates. Record model ID, candidate count, duration, and stable error code in the retrieval run. If model initialization or inference fails, retain hybrid ordering and surface the failure to the agent trail; never send query/passages to a remote reranking service.

Rationale: this adds one bounded advanced-RAG technique without replacing the measured BM25+dense+RRF baseline or changing evidence/citation identity. The selected model is listed by FastEmbed as Apache-2.0 and is approximately 0.13 GB; inference is local after its first model download. Compare with the baseline using the frozen author-curated cases, including nDCG@k and latency, and make no superiority claim from the small set.

## Alternatives Considered

- **SentenceTransformers/PyTorch**: rejected for the default local provider because the current corpus is small and FastEmbed provides a lighter CPU/ONNX model with tokenizer and query/passage APIs.
- **Chroma implicit embedding function**: rejected because it hides model selection and risks inconsistent query/document vectors.
- **Elasticsearch or a remote vector service**: rejected because the feature calls for a local-first, independently runnable backend and the corpus is small.
- **A custom BM25 implementation**: rejected in favor of BM25S's tested scorer and persisted index format.
- **Query rewriting, HyDE, MMR, and GraphRAG**: deferred; no query transformation or graph technique is added without separate failure analysis and evaluation.

## References

- FastEmbed overview and usage: https://qdrant.github.io/fastembed/ and https://qdrant.github.io/fastembed/Getting%20Started/
- FastEmbed supported models: https://qdrant.github.io/fastembed/examples/Supported_Models/
- FastEmbed query/passage retrieval: https://qdrant.github.io/fastembed/qdrant/Retrieval_with_FastEmbed/
- Chroma clients: https://docs.trychroma.com/docs/run-chroma/clients
- Chroma metadata filtering: https://docs.trychroma.com/docs/querying-collections/metadata-filtering
- BM25S: https://bm25s.github.io/
- OpenAI embeddings: https://platform.openai.com/docs/guides/embeddings
- PolicyLens master specification, Sections 7.1-7.11: `POLICYLENS_MASTER_SPEC.md`
