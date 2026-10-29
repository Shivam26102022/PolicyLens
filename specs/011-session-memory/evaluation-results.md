# Feature 011 Memory Evaluation Results

## Run Metadata

- **Evaluation**: `conversation-memory-v1`, schema `1.0`
- **Command**: `uv run --locked --package policylens python scripts/evaluate_conversation_memory.py`
- **Fixture**: `apps/backend/tests/fixtures/conversation_memory_eval_v1.json`
- **Environment**: Python 3.12.14, locked `policylens` package
- **Retriever**: deterministic BM25-style lexical fixture ranker, `k1=1.5`, `b=0.75`, `top_k=5`
- **Seed**: none; ranking is deterministic and does not sample
- **Provider cost estimate**: `$0.00`; no embedding or generation provider was called
- **Live provider checks**: skipped; no live provider requests were made

## Stratified Results

| Category | Candidates | Relevant | Memory precision@5 | Memory recall@5 | No-memory precision@5 | No-memory recall@5 |
|---|---:|---:|---:|---:|---:|---:|
| `same_topic_follow_up` | 6 | 2 | 0.4000 | 1.0000 | 0.0000 | 0.0000 |
| `cross_topic_preference` | 6 | 2 | 0.4000 | 1.0000 | 0.0000 | 0.0000 |
| `unrelated_query` | 6 | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| **Macro average** | — | — | **0.2667** | **0.6667** | **0.0000** | **0.0000** |

## Latency and Qualitative Results

- The latest fixture-ranking run (2026-10-28) measured a mean of **0.0730 ms** and a maximum of **0.1151 ms** across the three categories. These values measure in-process lexical fixture scoring only; they are not Chroma, embedding, or end-to-end retrieval latency and do not establish a performance target.
- Both categories with relevant memories placed all expected records in the top five, with three irrelevant records also included per category.
- The unrelated category had no relevant memories; the lexical harness still ranked five non-relevant candidates because it has no production similarity threshold. This is a negative result for interpreting raw top-five presence and a limitation of the synthetic ranker.
- The no-memory baseline returns no candidates, so its zero scores are a mechanical empty-result baseline, not evidence that memory improves answer quality.

## Scope and Limitations

- The harness is deterministic and uses synthetic text, but it does **not** call Chroma, the configured embedding provider, the agent runtime, or a generation model.
- These retrieval-mechanics metrics do not measure semantic embedding quality, factual accuracy, answer relevance, groundedness, or citation correctness. No quality or provider-parity gain is claimed.
- Unit/integration tests separately validate the Chroma adapter boundary, exact workspace filters, result bounds, consent gates, retrieval/write status, and citation isolation using fake adapters.
- `make retrieval-verify` completed with `status: ready`, so a validated local corpus index is present for a real local research run. The deterministic memory evaluation itself does not require that index.
- A real application answer still requires a configured model route and the verified local retrieval index. Live model/embedding requests were intentionally not made during this evaluation.
