# Feature 003 Retrieval Quickstart

## Prerequisites

- Python 3.12+ and the locked workspace environment.
- Feature 002 raw snapshots, canonical outputs, source registry, and ingestion manifest.
- Internet access for first-use downloads of the local FastEmbed embedding and cross-encoder models if they are not already cached. Subsequent inference uses the local model cache.
- No API key is required for local index build, CLI retrieval, or evaluation. Starting the FastAPI service requires the repository's existing valid `AppSettings` configuration. The baseline answer endpoint additionally requires explicit `MODEL_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL`; without these it is unavailable and never falls back to another provider. The optional OpenAI embedding provider is separately selected with `EMBEDDING_PROVIDER=openai` and `OPENAI_EMBEDDING_MODEL`; selecting it sends indexed passage/query text to OpenAI.

## Build and Evaluate

```bash
uv sync --locked --all-packages --all-groups
make data-parse
make retrieval-index
make retrieval-verify
make retrieval-eval
uv run --locked --package policylens pytest apps/backend/tests scripts/tests -q
```

Expected results:

- Two structured canonical datasets and four report documents are selected from the latest verified ingestion-manifest records.
- The index build reports its corpus fingerprint, chunk strategy, embedding identity/dimension, BM25 tokenizer/configuration, counts, and validation results.
- A validated build atomically updates `data/indexes/active-index.json`; a failed build leaves the previous pointer unchanged.
- Retrieval evaluation compares BM25, dense, hybrid, and (when enabled) hybrid plus local cross-encoder reranking across the frozen case set and each chunk configuration. It writes Recall@k, nDCG@k, MRR, latency, empty-result, citation-completeness and reranker outcome metrics with caveats to `docs/evaluation/retrieval-evaluation.md` and a machine-readable manifest under `data/manifests/`.
- This small case set is author-curated engineering evidence, not independent human review. No retrieval quality threshold or answer-level semantic groundedness result is claimed.
- Historical local v4 measurement on this seven-case set: BM25/hybrid Recall@5 was `0.571`, dense Recall@5 was `0.429`, and citation metadata completeness was `1.000` across configurations. See the latest results in `docs/evaluation/retrieval-evaluation.md` for the cross-encoder comparison; neither the historical nor the new values are a representative or independent quality claim.

## API Smoke Test

Start the backend with the existing valid `AppSettings` configuration after building the index:

```bash
make dev-api
```

Search using a mode and restrictive filters:

```bash
curl -sS http://127.0.0.1:8000/retrieval/search \
  -H 'Content-Type: application/json' \
  -d '{"schema_version":"1.0","query":"What is youth unemployment in India in 2025?","mode":"hybrid","top_k":5,"filters":{"country_iso3":["IND"],"years":[2025]}}'
```

The response includes a `run_id`, `index_version`, explicit `found`/`no_results` status, and evidence with exact passage text, source hash, page/section or row key, rank, and scores. The caller cannot set or broaden permission scopes. Provider/index errors use stable error codes and are not represented as empty search results.

Citation validation accepts `run_id`, claims, and claim-linked citations. It verifies each passage and excerpt against the bounded evidence returned by that run; unknown, expired, fabricated, or mismatched evidence is rejected. Semantic entailment is not asserted by this validator.

The non-agent baseline makes one bounded structured request over retrieved evidence and exposes no tools. Call `POST /retrieval/answer` with the same query/mode/filter fields as search:

```bash
curl -sS http://127.0.0.1:8000/retrieval/answer \
  -H 'Content-Type: application/json' \
  -d '{"schema_version":"1.0","query":"What is youth unemployment in India in 2025?","mode":"hybrid","top_k":5,"filters":{"country_iso3":["IND"],"years":[2025]}}'
```

The response is `answered` only when every returned claim is verbatim text exactly equal to a server-derived citation excerpt that resolves to evidence from that run. Provider-backed responses include the generation provider, model ID, and prompt version; no-evidence abstentions have no generation metadata. Paraphrases are rejected. No evidence returns `abstained` without a generation call; provider, malformed-output, and invalid-citation paths fail safely. Claims are extractive; the baseline does not evaluate answer selection quality or source accuracy.

## Provider Selection

Local is the default:

```dotenv
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

Passage vectors are cached under the ignored `data/indexes/embedding-cache/`, keyed by embedding provider/model identity and the exact contextual embedding-text hash. Query vectors are not persisted. Changing model identity creates a separate cache namespace and requires a full index build.

The API provider is an explicit opt-in and uses a separate full index:

```dotenv
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Never mix providers or vector dimensions in one collection. Changing provider/model or chunker configuration requires a full index build and validation. Automated tests mock the OpenAI SDK and do not call the live API.

Local hybrid reranking is enabled by default and can be configured independently:

```dotenv
RERANKER_ENABLED=true
RERANKER_MODEL=jinaai/jina-reranker-v1-tiny-en
RERANKER_CANDIDATE_COUNT=20
```

FastEmbed downloads model weights on first use; subsequent scoring runs locally and does not transmit queries or passages to a remote reranking API. Reranking applies only to hybrid search and only to already permission-filtered candidates. It changes ordering, not passage identity or citation provenance. If the cross-encoder is unavailable, the retrieval run keeps hybrid ordering and records a stable failure code; the agent trail exposes that fallback.

For the explicit answer baseline, set the existing generation settings independently of embedding selection:

```dotenv
MODEL_PROVIDER=openai
OPENAI_MODEL=<approved-generation-model>
OPENAI_API_KEY=<secret>
```

The baseline uses `store=false`, a strict response schema, a bounded output-token limit, and no tools. Automated tests mock the OpenAI SDK and make no live generation calls.

## Failure Checks

- Build a second index with an invalid/failing embedder and confirm the active pointer remains unchanged.
- Query with a source/country/year filter that has no eligible evidence and confirm `no_results`.
- Submit an unknown run ID, an unreturned passage ID, and a non-exact excerpt to citation validation; each must be rejected.
- Call the answer endpoint with no eligible evidence and verify it abstains without invoking the generation provider.
- Call the answer endpoint with generation unconfigured and verify it returns the stable unavailable state without fallback.
- Disable or make the local reranker unavailable; verify hybrid order is retained and run diagnostics report the safe failure code.
- Restart the backend and confirm the active Chroma/BM25S build remains queryable.
