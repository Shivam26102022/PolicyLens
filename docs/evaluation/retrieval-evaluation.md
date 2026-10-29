# Retrieval and Chunking Evaluation

Case set: `feature003-corpus-anchors-v1`
Case lineage: Author-curated engineering cases derived from the current Feature 002 canonical snapshots. Not independently human-reviewed and not representative of the Feature 007 evaluation set.
Embedding provider/model: `local` / `BAAI/bge-small-en-v1.5` (384 dimensions)
Embedding revision/hash: `aa8f8b060edb00e03bfdd08813a2949946c8ba55` / `51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431`
License/pooling/tokenizer: `mit` / `first-token CLS` / `BAAI/bge-small-en-v1.5`

The case set is author-curated engineering evidence tied to current canonical page/row anchors. It is not independently human-reviewed or representative of the later Feature 007 benchmark. Feature 003 includes a bounded extractive non-agent baseline whose answered claims exactly match current-run excerpts. This retrieval evaluation does not measure answer selection quality or source accuracy.

Dense evaluation uses exact in-memory cosine similarity over the same normalized vectors; production dense retrieval uses persistent Chroma.

The `hybrid+cross_encoder` row, when present, applies the configured local cross-encoder to up to 20 permission-filtered hybrid candidates before the final evidence cap. Its score only changes ordering; the original hybrid ranks and scores remain available.

| Chunker | Passages | Mode | Recall@6 | nDCG@6 | MRR | Empty rate | Citation completeness | Mean latency (ms) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| fixed-size:fixed-500-75-v4 | 730 | bm25 | 0.571 | 0.500 | 0.476 | 0.000 | 1.000 | 0.25 |
| fixed-size:fixed-500-75-v4 | 730 | dense | 0.429 | 0.429 | 0.429 | 0.000 | 1.000 | 5.70 |
| fixed-size:fixed-500-75-v4 | 730 | hybrid | 0.571 | 0.500 | 0.476 | 0.000 | 1.000 | 5.97 |
| fixed-size:fixed-500-75-v4 | 730 | hybrid+cross_encoder | 0.571 | 0.571 | 0.571 | 0.000 | 1.000 | 245.54 |
| structure-aware:structure-aware-450-v4 | 761 | bm25 | 0.571 | 0.519 | 0.500 | 0.000 | 1.000 | 0.26 |
| structure-aware:structure-aware-450-v4 | 761 | dense | 0.429 | 0.429 | 0.429 | 0.000 | 1.000 | 5.86 |
| structure-aware:structure-aware-450-v4 | 761 | hybrid | 0.571 | 0.519 | 0.500 | 0.000 | 1.000 | 6.31 |
| structure-aware:structure-aware-450-v4 | 761 | hybrid+cross_encoder | 0.714 | 0.643 | 0.619 | 0.000 | 1.000 | 244.33 |
| structure-aware:structure-aware-250-v4 | 1170 | bm25 | 0.571 | 0.500 | 0.476 | 0.000 | 1.000 | 0.30 |
| structure-aware:structure-aware-250-v4 | 1170 | dense | 0.429 | 0.429 | 0.429 | 0.000 | 1.000 | 7.91 |
| structure-aware:structure-aware-250-v4 | 1170 | hybrid | 0.571 | 0.571 | 0.571 | 0.000 | 1.000 | 8.93 |
| structure-aware:structure-aware-250-v4 | 1170 | hybrid+cross_encoder | 0.571 | 0.519 | 0.500 | 0.000 | 1.000 | 168.52 |

Reranker: `jinaai/jina-reranker-v1-tiny-en`; local inference; candidate cap `20`.
Reranking outcomes across chunk configurations: 21 completed, 0 failed, 0 not run (21 attempts).

## Limitations

- The engineering relevance set is small and author-curated; no quality threshold or superiority claim is inferred from it.
- `citation_completeness` measures retrieval source/hash/location metadata.
- Answer selection quality and source accuracy are `not_measured`; the baseline is extractive, but these cases are not an answer-quality or source-validity benchmark.
- Latency is measured locally in this run and is not a service-level objective.
- The cross-encoder model is run locally. Case counts report completed, failed, and not-run reranking attempts; a failed reranker retains hybrid order.
- The first cross-encoder query includes lazy model initialization; warm-cache latency will differ.
- OpenAI embeddings and baseline generation require explicit configuration; automated tests make no live calls.

## Non-Agent Baseline

`POST /retrieval/answer` makes one structured, tool-free OpenAI Responses call only when `MODEL_PROVIDER=openai` is explicitly configured. The request disables provider storage and retries, and bounds evidence input, output tokens, and timeout.

No evidence abstains before generation is initialized. Every returned claim is verbatim text exactly equal to a server-derived citation excerpt validated against the current retrieval run. Provider-backed responses report the provider, model ID, and prompt version. Baseline tests mock the SDK; this report contains no live generation result.

Reproduce with `make retrieval-eval` after `make retrieval-index` and `make retrieval-verify`.
