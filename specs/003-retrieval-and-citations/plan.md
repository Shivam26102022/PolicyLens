# Implementation Plan: Chunking, Indexing, Retrieval, and Citations

**Branch**: `003-retrieval-and-citations` (feature identifier; this workspace has no Git metadata) | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-retrieval-and-citations/spec.md`

## Summary

Build reproducible passage and structured-row indexes from Feature 002 canonical artifacts. Compare fixed and structure-aware chunks with local BM25, local-default FastEmbed vectors, optional explicitly selected OpenAI vectors, deterministic reciprocal-rank fusion, and bounded local cross-encoder reranking after hybrid candidate filtering. Keep each build immutable, validate it before atomic activation, and preserve the previous active pointer for rollback. Expose bounded retrieval, run-scoped citation verification, and one bounded, tool-free OpenAI RAG baseline that returns only extractive claims. Do not add an agent, MCP tools, or UI work.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: FastAPI/Pydantic; Chroma `PersistentClient`; BM25S; FastEmbed with `BAAI/bge-small-en-v1.5` and its `TextCrossEncoder` adapter; the OpenAI Python SDK and `tiktoken` for optional embeddings and the explicitly configured baseline. All new dependencies are version-constrained and locked in `uv.lock`.

**Storage**: Canonical inputs under `data/canonical/`; ignored per-build Chroma/BM25S files below `data/indexes/`; atomically replaced `data/indexes/active-index.json`; append-only build/evaluation manifests under `data/manifests/`; versioned frozen engineering cases and evaluation report under `data/evaluation/` and `docs/`.

**Testing**: pytest with deterministic fake embedders/rerankers, temporary persistent Chroma directories, mocked OpenAI SDK calls, frozen corpus-derived location anchors, and API tests. No automated test calls a live embedding, reranking API, or generation API.

**Target Platform**: Python 3.12 on Linux and macOS; CPU-only local retrieval is supported. Apple Silicon acceleration is optional and is not required by this feature.

**Project Type**: Backend-owned retrieval library, local index-building/evaluation CLI, and typed FastAPI endpoint within the existing three-service architecture.

**Performance Goals**: No unmeasured latency SLO. Bound candidates and final context using existing settings, batch embeddings, and record index-build duration plus per-mode query latency, including cross-encoder reranking, on the frozen set.

**Constraints**: Local embeddings and local reranking are the defaults. OpenAI embeddings and baseline generation require explicit configuration and must never be selected as fallback. Model/provider/dimension changes require a distinct full index. Enforce model input limits without truncation. Apply `allowed_usage` and permission/source filters before reranking or returning text. Reranking is limited to 20 candidates, only affects hybrid ordering, preserves original channel ranks/scores, and records a safe fallback when unavailable. The baseline uses no tools, receives only bounded current-run evidence, returns only verbatim claim text exactly equal to a validated citation excerpt, and reports the generation model and prompt version. Indexes and model weights remain outside source control. The evaluation set is author-curated engineering evidence, not an independently reviewed Feature 007 benchmark.

**Scale/Scope**: Six active sources: two structured datasets with 44 observations each and four World Bank reports (242 pages total). Build full indexes first; no incremental updates, query rewriting, OCR, agent, production MCP tools, or frontend implementation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Every result is a verbatim canonical passage/row with provenance; citations resolve only against the current run. | PASS |
| II. Scientific Evaluation Before Complexity | BM25, dense, hybrid, hybrid plus cross-encoder, and chunk configurations share one frozen case set; report metrics and limitations without invented thresholds. | PASS |
| III. Bounded Agency and Deterministic Computation | This feature adds no agent; filters, fusion, context assembly, and citation checks are deterministic and bounded. | PASS |
| IV. Secure MCP Trust Boundaries | No MCP integration or tools are added. | PASS |
| V. Provider Portability With Measured Parity | Local default and optional API embedder have explicit identities; no automatic fallback or provider mixing. API use is opt-in and reported. | PASS |
| VI. Reproducibility Is a Product Feature | Canonical hashes, configs, model metadata, dependency versions, and build/evaluation manifests identify every index. | PASS |
| VII. Privacy and Responsible AI | Only approved public corpus text is indexed; local inference is default; no raw query/evidence logging or answer-authority claims. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | Retrieval stays in the existing backend and local CLI; no service or framework is added. | PASS |
| IX. Testable Specifications and Traceability | Each acceptance criterion maps to tests, frozen cases, inspection, or a reproducible command. | PASS |
| X. Honest Reporting | Engineering-case labels and unmeasured groundedness are disclosed; failed and unrun checks are recorded. | PASS |

No constitution exception is required.

## Project Structure

### Documentation (this feature)

```text
specs/003-retrieval-and-citations/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── retrieval-api.schema.json
│   ├── index-manifest.schema.json
│   ├── index-registry.schema.json
│   ├── active-index-pointer.schema.json
│   └── citation.schema.json
└── tasks.md
```

### Source Code (repository root)

```text
apps/backend/src/policylens/
├── api/retrieval.py
└── retrieval/
	├── config.py
	├── models.py
	├── chunking.py
	├── embeddings.py
	├── reranking.py
	├── indexing.py
	├── search.py
	├── citations.py
	├── generation.py
	└── evaluation.py
apps/backend/tests/
├── api/
│   └── test_retrieval_api.py
└── unit/
	├── test_chunking.py
	├── test_retrieval_models.py
	├── test_retrieval_settings.py
	├── test_embeddings.py
	├── test_reranking.py
	├── test_indexing.py
	├── test_retrieval.py
	├── test_citations.py
	└── test_generation_baseline.py
scripts/
├── build_retrieval_index.py
├── evaluate_retrieval.py
└── tests/test_retrieval_evaluation.py
prompts/answer/non-agent-v1.md
data/
├── evaluation/retrieval-cases.json
├── indexes/active-index.json
└── manifests/
	├── retrieval-index-manifest.json
	└── retrieval-evaluation-manifest.json
docs/evaluation/retrieval-evaluation.md

```

**Structure Decision**: Keep parsers, indexing, search, citation validation, and the baseline in the existing backend package; expose typed HTTP routes for search, citation validation, and baseline answers, and use scripts for local build/evaluation. Chroma and BM25S stay backend-owned and persist under existing ignored index roots. No frontend, MCP, or new service is added. A separate `RetrievalSettings` model lets the local index CLI operate without generation-provider credentials; API baseline wiring is lazy and uses validated `AppSettings` only after evidence is retrieved.

## Implementation Boundary

Feature 003 owns chunking, embedding adapters, local Chroma and BM25S indexes, build validation/activation/rollback, query filtering/fusion, bounded local cross-encoder reranking, context assembly, citations, retrieval evaluation, and one direct, tool-free OpenAI RAG baseline. It consumes verified canonical outputs and sources whose registry `allowed_usage` includes `retrieval`. Feature 002 acquisition/parsing remains unchanged. Feature 004 owns agent orchestration and broader answer/generation routing; Feature 005 owns production MCP tools; Feature 009 owns the user interface.

## Complexity Tracking

No constitution violations or additional services are required.
