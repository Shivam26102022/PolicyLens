# Feature Specification: Chunking, Indexing, Retrieval, and Citations

**Feature Branch**: `003-retrieval-and-citations`  
**Created**: 2026-10-24  
**Status**: Implemented locally; bounded local cross-encoder reranking and the non-agent baseline are included; broader Feature 007 evaluation remains out of scope
**Input**: `POLICYLENS_MASTER_SPEC.md`, Section 7 and Section 20 Feature 003

## Product Outcome

A researcher can retrieve relevant bounded evidence from the approved corpus using keyword, dense, or hybrid search, optionally refine hybrid ordering with a bounded local cross-encoder, inspect provenance, and verify that each returned claim citation points to evidence actually present in that run.

## Scope and Dependencies

Depends on Feature 002's approved, canonical corpus. Owns structure-aware/fixed chunking, stable passage IDs, provider-neutral local/API embeddings, local persistent Chroma, local BM25, deterministic fusion, bounded local hybrid reranking, metadata/permission filters, index lifecycle/rollback, a non-agent RAG baseline, citations, and retrieval evaluation.

## Clarifications

### Implementation clarification (2026-10-25)

- No frozen retrieval relevance set was present in the repository. Feature 003 adds a small versioned, source/page/row-anchored engineering set for deterministic comparisons. It is author-curated and is not represented as independent human review or a representative benchmark; Feature 007 owns the broader reviewed evaluation set.
- Feature 003 includes only a bounded, extractive non-agent baseline using an explicitly configured OpenAI generation model. It has no tools or agent loop; each returned factual claim is verbatim text that exactly equals a current-run citation excerpt, and the server validates that excerpt against retrieved evidence. It fails safely on paraphrased or unsupported output. Broader answer/generation routing belongs to Feature 004/006; answer-selection evaluation belongs to Feature 007.
- Local BGE-small embeddings remain the default. OpenAI embeddings are implemented as an explicit opt-in; no API calls or provider-parity claim are made without explicit configuration and an authorized evaluation run.

## User Scenarios & Testing

### User Story 1 - Rebuild and Inspect the Index (Priority: P1)

As a maintainer, I can rebuild versioned local indexes from canonical artifacts and verify that failed builds never replace the active index.

**Independent Test**: Rebuild twice from identical input and verify stable chunk IDs, metadata, and round-trip records; inject a failed validation and confirm the active pointer is unchanged.

**Acceptance Scenarios**:

1. **AC-003-01** Given the same canonical document and chunker configuration, When chunking runs twice, Then passage text and IDs are identical and preserve page/section/offset metadata.
2. **AC-003-02** Given a valid build, When Chroma/BM25 validation succeeds, Then the versioned index may activate; on partial failure, the previous active version remains selected.
3. **AC-003-03** Given local or API embedding selection, When vectors are built, Then dimensions/model version/limits are verified and providers are not mixed within a collection.

### User Story 2 - Retrieve Evidence with Filters (Priority: P1)

As a researcher, I can search the approved sources and receive bounded, filtered passages with stable ranks and provenance.

**Independent Test**: Run each frozen retrieval case through BM25, dense, and hybrid modes; map its stable source/page/row anchors to the strategy-specific passage IDs and assert relevant evidence plus permission exclusions.

**Acceptance Scenarios**:

1. **AC-003-04** Given query/filter/top-k input, When hybrid retrieval runs, Then permission filters apply before text is returned and deterministic rank fusion resolves ties consistently.
2. **AC-003-05** Given no eligible evidence or retrieval failure, When retrieval completes, Then it returns an explicit no-result/failure state distinct from generation failure.
3. **AC-003-06** Given candidate overlap or source dominance, When context is assembled, Then duplicates are removed, source dominance is capped, and evidence ordering/truncation is deterministic.
4. **AC-003-11** Given hybrid candidates that pass source and permission filters, When local cross-encoder reranking is enabled, Then at most the configured candidate cap is scored before the final evidence cap, reranker scores and safe run diagnostics are returned, and a reranker failure retains the original hybrid order with a stable error code.

### User Story 3 - Verify Citations (Priority: P1)

As a reviewer, I can trace each factual claim to its exact passage or row evidence.

**Independent Test**: Supply known, unknown, and fabricated evidence IDs and verify only returned evidence can pass citation validation.

**Acceptance Scenarios**:

1. **AC-003-07** Given a claim and returned passage/row, When citation validation runs, Then source ID, passage/row keys, location, excerpt, URI where available, and content hash are preserved.
2. **AC-003-08** Given an unknown run/passage ID or excerpt not exactly present in the current run's evidence, When validation runs, Then the citation is rejected and the result cannot be marked citation-valid. Semantic entailment is not evaluated by this feature.

### User Story 4 - Inspect a Non-Agent RAG Baseline (Priority: P2)

As a researcher, I can compare retrieved evidence with one bounded, extractive non-agent answer whose claims reproduce only evidence returned by that run.

**Independent Test**: Use mocked structured OpenAI responses to verify current-run citations are accepted, fabricated/unsupported references fail safely, and no-evidence requests do not call the generation provider.

**Acceptance Scenarios**:

1. **AC-003-09** Given eligible retrieved evidence and explicit OpenAI generation configuration, When the non-agent baseline runs, Then it makes one bounded structured request without tools, returns each factual claim as verbatim text exactly equal to a current-run citation excerpt, reports the generation provider/model/prompt version, and returns `answered` only after citation validation succeeds.
2. **AC-003-10** Given no eligible evidence, unavailable generation, malformed output, or invalid citations, When the baseline runs, Then it returns `abstained`/`failed_safe` or a stable failure response and never presents unsupported output as citation-valid.

## Functional Requirements

- **CHUNK-003-01**: Compare fixed-size and structure-aware strategies plus one alternate size on the frozen set; preserve structure, stable IDs, and citation locations.
- **EMB-003-01**: Support local-default and optional OpenAI embeddings through independent `EMBEDDING_PROVIDER=local|openai`; changing providers requires a versioned full re-index.
- **INDEX-003-01**: Backend-owned Chroma MUST be persistent, versioned, cosine-configured, permission-filtered, validated before activation, and rebuildable.
- **RET-003-01**: Provide BM25, dense, and deterministic hybrid retrieval; record ranks/scores and implement bounded top-k, deduplication, per-source caps, and context budgets.
- **RET-003-02**: Optionally rerank no more than 20 permission-filtered hybrid candidates with the configured local cross-encoder; preserve original hybrid ranks/scores and provenance, report safe diagnostics, and retain hybrid order on model failure.
- **CITE-003-01**: Citations MUST be claim-linked and limited to evidence returned by the current run.
- **EVAL-003-01**: Compare BM25, dense, hybrid, hybrid plus cross-encoder, and chunking using Recall@k, nDCG@k, MRR, latency, empty-result rate, citation completeness, and groundedness where measurable; report the reranker model, candidate bound, and success/failure counts.
- **SEC-003-01**: Permission and source filters MUST prevent unauthorized passages from reaching context or responses.
- **BASE-003-01**: Provide a bounded non-agent RAG baseline through the explicitly configured OpenAI generation model, with no tools, strict structured output, extractive claim text exactly equal to a cited excerpt, current-run citation validation, generation provider/model/prompt-version metadata, and no generation call when retrieval returns no evidence.
- **SEC-003-02**: Retrieved passages MUST be delimited as untrusted evidence; instructions within them MUST NOT be followed as application instructions.

## Success Criteria

- **SC-003-01**: Deterministic rebuild reproduces active IDs/metadata and preserves rollback on failure.
- **SC-003-02**: Keyword, dense, and hybrid modes run on the same frozen retrieval cases with reproducible metrics.
- **SC-003-03**: Every accepted citation resolves to evidence returned by the current run; unauthorized/unknown IDs are rejected.
- **SC-003-04**: The non-agent baseline returns `answered` only when every factual claim exactly equals a citation excerpt validated against evidence from that run; no-evidence, paraphrased, and invalid-output paths fail safely.
- **SC-003-05**: The local reranker has a reproducible baseline comparison and safe fallback; its measured quality is reported without a superiority claim on the small author-curated set.

## Assumptions and Open Questions

- Feature 002 supplies rights-cleared canonical artifacts. Feature 003 supplies a frozen engineering relevance set; Feature 007 supplies independent review and the representative evaluation set.
- Model identifiers, tokenization, chunk sizes, and retrieval defaults are selected in the plan from verified current documentation and measured retrieval results. No threshold or provider-quality superiority is assumed before measurement.
- No quality threshold is invented before a baseline exists.

## Out of Scope

Corpus acquisition/parsing (Feature 002), query rewriting, HyDE, MMR, GraphRAG, agent/tool orchestration beyond this baseline (004), model-generation gateways beyond the explicit baseline call (006), production MCP tools (005), broad evaluation (007), and final answer UI (009).