# 3. Retrieval-Augmented Generation

> Assignment §3: end-to-end ingestion and retrieval pipeline (parsing, chunking, metadata, indexing, retrieval, generation); at least two retrieval or ranking approaches compared; source-and-passage citations; safe handling of unanswerable, ambiguous, conflicting and out-of-scope questions.

Runtime flow: [5. Agentic workflow](05-agentic-workflow.md). Measured results: [6. Evaluation](06-evaluation-analysis.md).

## Pipeline

| Stage | What it does | Code |
|---|---|---|
| Acquire | Fetch allow-listed sources, pin SHA-256, record licence and attribution in an append-only manifest. | `scripts/download_data.py`, `data/manifests/sources.yaml` |
| Parse | PDFs become page-local text blocks with section path, bounding box and character offsets. Indicator JSON becomes typed observations (country, year, value or `null`, unit, status). No OCR, no imputation. | `ingestion/`, `scripts/parse_data.py` |
| Chunk | Passages carry stable IDs, page or row location, source hash, licence and a permission scope. | `retrieval/chunking.py` |
| Index | BM25S lexical index and a Chroma dense index. The active index is selected through a versioned pointer that supports rollback. | `retrieval/indexing.py`, `data/indexes/active-index.json` |
| Retrieve | BM25, dense or hybrid search with metadata and permission filters, optional re-rank, and a bounded context. | `retrieval/search.py`, `reranking.py` |
| Generate | A typed, structured answer: claims with verbatim excerpts, or a status (`abstained`, `clarification_required`, `conflict`, `blocked`). | `agent_runtime/`, `retrieval/generation.py` |
| Validate | Every claim excerpt must exactly match text in this run's retrieved passages. | `retrieval/citations.py` |

## Design choices and settings

| Choice | Setting | Rationale |
|---|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5`, 384 dimensions, local, MIT licence | Corpus text never leaves the machine. Small and fast on CPU. API embeddings are opt-in and need a separate index. |
| Similarity | Cosine over normalised vectors | Standard for BGE. |
| Lexical | BM25 (`k1=1.5`, `b=0.75`) | Strong on exact terms such as country names, years and indicator labels. It is the non-LLM baseline. |
| Fusion | Reciprocal rank fusion (`rrf_k=60`) | Combines ranks without tuning score scales. |
| Candidate pool | 20 candidates; final context 6 chunks; at most 3 per source in the first pass, then back-filled from the same ranking if slots remain | Bounds tokens and stops one source dominating a multi-source answer, without capping single-source questions at 3 (that was a bug fixed on 2026-10-29). |
| Context and excerpt caps | 12,000 characters of context; excerpts ≤ 500 characters | Keeps citations small and checkable. |
| Re-ranker (optional) | Local cross-encoder `jinaai/jina-reranker-v1-tiny-en` over at most 20 filtered candidates | Reorders only. Falls back to hybrid order on failure. |
| Permission filter | `allowed_permission_scopes=("public",)` applied before ranking | The model never sees passages outside the caller's scope. |
| Chunkers compared | `fixed-500-75` (500 tokens, 75 overlap), `structure-aware-250`, `structure-aware-450` | Tests whether respecting headings and table rows helps. |

## Comparison of retrieval approaches

Twelve configurations (3 chunkers × BM25, dense, hybrid, hybrid + cross-encoder) over 40 anchored cases at top 6. Run `7437acdc-972b-433b-b8ff-4f9f4dc31630`, retrieval only, after the per-source-cap fix. Source: [6. Evaluation](06-evaluation-analysis.md).

| Chunker | Mode | Recall@6 | MRR | nDCG@6 | Mean latency (ms) |
|---|---|---:|---:|---:|---:|
| fixed-500-75 | BM25 | 0.629 | 0.633 | 0.611 | 0.20 |
| fixed-500-75 | dense | 0.662 | 0.608 | 0.619 | 5.12 |
| fixed-500-75 | hybrid | 0.688 | 0.637 | 0.647 | 5.51 |
| fixed-500-75 | hybrid + cross-encoder | **0.750** | **0.692** | **0.701** | 202.64 |
| structure-aware-250 | BM25 | 0.675 | 0.631 | 0.631 | 0.20 |
| structure-aware-250 | dense | 0.637 | 0.600 | 0.608 | 7.33 |
| structure-aware-250 | hybrid | 0.713 | 0.647 | 0.661 | 7.81 |
| structure-aware-250 | hybrid + cross-encoder | **0.750** | **0.693** | **0.702** | 103.05 |
| structure-aware-450 | BM25 | 0.633 | 0.634 | 0.615 | 0.21 |
| structure-aware-450 | dense | 0.662 | 0.610 | 0.620 | 5.30 |
| structure-aware-450 | hybrid | 0.713 | 0.640 | 0.655 | 5.65 |
| structure-aware-450 | hybrid + cross-encoder | **0.750** | **0.694** | **0.703** | 159.28 |

By anchor type (all chunkers pooled): structured-row anchors reach 1.00 for dense, hybrid and the reranked mode (BM25 0.90), while narrative PDF-page anchors reach only 0.37 (BM25), 0.27 (dense), 0.38 (hybrid) and 0.47 (reranked).

**Reading the result**

- Before the fix, every source was capped at 3 passages even for single-source questions, so the earlier run (Recall@k 0.525–0.588, all modes statistically indistinguishable) understated every mode. Those numbers are superseded.
- Hybrid beats BM25 and dense by about 0.04–0.08 and the cross-encoder adds about +0.05–0.06 more, identically across chunkers. Chunker choice matters little. With 40 cases and no recomputed confidence intervals these are directional differences, not significance claims.
- The cross-encoder costs about 100–200 ms per query. It is enabled locally and in Docker with `RERANKER_ENABLED=true`. The Vercel demo runs the hybrid configuration only, by design: a cross-encoder needs a model download and memory that serverless cold starts do not suit, and the hybrid rows are the production-equivalent result.
- Narrative PDF retrieval is the hardest case (0.47 at best). Anchors name one exact marker on one page, so other valid passages count as misses; the remaining true misses are mostly executive-summary text outranking the specific page.
- nDCG uses binary relevance because no case has graded relevance labels.
- Reproduce: `uv run --locked --package policylens python -m scripts.evaluate_suite --run-retrieval --reranker --split all`.

## Citations

A citation identifies the source, passage ID, page or row location, content hash and an exact excerpt. The host checks each excerpt against the passages retrieved in the **current run**. Passages from earlier turns, memory or model output cannot be cited. A failed check ends the run as `failed_safe` (`CITATION_INVALID`) rather than releasing the claim. The UI shows the highlighted PDF page next to each claim.

Scope: an exact excerpt proves the text exists, not that the claim follows from it. Claim-to-excerpt support is checked by the AI judge and the 19-answer human review ([evaluation analysis](06-evaluation-analysis.md)).

## Unanswerable, ambiguous, conflicting and out-of-scope questions

| Situation | Behaviour | Agent accuracy (cases) |
|---|---|---|
| Unanswerable (no evidence) | `abstained` with a short reason | 1.000 (3) |
| Ambiguous | `clarification_required`, one focused question | 1.000 (3) |
| Out of scope | `blocked` | 1.000 (3) |
| Stale or time-sensitive | Abstain or state the data period | 1.000 (3) |
| Conflicting evidence | `conflict`, both sides cited. Differences in population, period or definition are flagged as "not directly comparable", not merged. | 1.000 (1, synthetic fixture) |

Accuracy here measures response type, not semantic quality, and each stratum is tiny. See [evaluation analysis](06-evaluation-analysis.md).
