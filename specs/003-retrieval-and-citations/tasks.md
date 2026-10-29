# Tasks: Chunking, Indexing, Retrieval, and Citations

**Input**: Design documents from `/specs/003-retrieval-and-citations/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Execution boundary**: Complete Feature 003 only. Do not implement broader model-generation routing, agents, production MCP tools, or frontend workflows owned by Features 004, 005, and 009.

**Tests**: Required by the acceptance scenarios. Unit/API tests use deterministic fake embedders and temporary persistent indexes; OpenAI SDK calls are mocked. No automated test makes a live API call.

**Format**: `- [ ] T### [P?] [US#] Description with exact file path`

## Phase 1: Setup

**Purpose**: Add locked retrieval dependencies, settings defaults, and command wiring.

- [x] T001 Add version-constrained `chromadb`, `bm25s`, `fastembed`, direct `openai`, and `tiktoken` dependencies in `apps/backend/pyproject.toml`; refresh and verify `uv.lock` resolves for Python 3.12 (INDEX-003-01, RET-003-01, EMB-003-01).
- [x] T002 [P] Add `retrieval-index`, `retrieval-verify`, `retrieval-rollback`, and `retrieval-eval` targets to the root `Makefile`, invoking the planned scripts (SC-003-01, SC-003-02).
- [x] T003 [P] Set `LOCAL_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` in `.env.example` while keeping `EMBEDDING_PROVIDER=local` and API credentials blank (EMB-003-01).

## Phase 2: Foundational

**Purpose**: Define typed retrieval contracts, independent retrieval settings, and verified canonical input selection before user-story work.

- [x] T004 [P] Add Pydantic model/schema tests for passages, row keys, retrieval requests/results, index manifests, active pointers, and error codes in `apps/backend/tests/unit/test_retrieval_models.py` (AC-003-01 through AC-003-08).
- [x] T005 Implement the typed retrieval entities and validators in `apps/backend/src/policylens/retrieval/models.py` using `specs/003-retrieval-and-citations/data-model.md` (CHUNK-003-01, INDEX-003-01, RET-003-01, CITE-003-01).
- [x] T006 [P] Add settings tests proving local indexing does not require generation credentials and OpenAI embeddings fail closed without explicit key/model configuration in `apps/backend/tests/unit/test_retrieval_settings.py` (EMB-003-01).
- [x] T007 Implement `RetrievalSettings` and mapping from validated `AppSettings` in `apps/backend/src/policylens/retrieval/config.py`; set the local model default in `apps/backend/src/policylens/settings.py` without weakening generation-provider validation (EMB-003-01, INDEX-003-01).
- [x] T008 [P] Add canonical-source selection tests for latest successful manifest records, matching raw/canonical hashes, disabled-source exclusion, and `allowed_usage` in `apps/backend/tests/unit/test_indexing.py` (INDEX-003-01, SEC-003-01).
- [x] T009 Implement the Feature 002 manifest/registry loader and fail-closed source eligibility checks in `apps/backend/src/policylens/retrieval/indexing.py` (INDEX-003-01, SEC-003-01).

## Phase 3: User Story 1 - Rebuild and Inspect the Index (Priority: P1)

**Goal**: Create stable passages and isolated, validated local indexes whose activation and rollback are deterministic.

**Independent Test**: Rebuild using the same canonical inputs/configuration, verify stable passage IDs and round-trip metadata, inject build failure, and confirm the previous active pointer remains unchanged.

### Chunking

- [x] T010 [P] [US1] Add fixed-size/structure-aware chunk tests for stable IDs, token bounds, headings, tables, offsets, and no cross-document merges in `apps/backend/tests/unit/test_chunking.py` (AC-003-01, CHUNK-003-01).
- [x] T011 [US1] Implement fixed-size and structure-aware chunkers with versioned token budgets, block/row locations, context-aware embedding text, and deterministic passage IDs in `apps/backend/src/policylens/retrieval/chunking.py` (AC-003-01, CHUNK-003-01).

### Embedding Providers

- [x] T012 [P] [US1] Add local/OpenAI embedding adapter tests for query/passage methods, dimensions, finite normalized vectors, token limits, provider isolation, and no fallback in `apps/backend/tests/unit/test_embeddings.py` (AC-003-03, EMB-003-01).
- [x] T013 [US1] Implement FastEmbed local and OpenAI API embedding providers with explicit model identity, query/passage methods, model-aware token/dimension/finite-value validation, no automatic fallback, and a passage cache keyed by model identity plus contextual text hash in `apps/backend/src/policylens/retrieval/embeddings.py` (AC-003-03, EMB-003-01).

### Index Lifecycle

- [x] T014 [P] [US1] Add persistent Chroma/BM25S tests for version isolation, round-trip samples, manifest validation, failure rollback, and restart persistence in `apps/backend/tests/unit/test_indexing.py` (AC-003-02, SC-003-01, INDEX-003-01).
- [x] T015 [US1] Implement isolated Chroma/BM25S builds, deterministic fingerprints, validation, append-only manifests, atomic active-pointer activation, and rollback in `apps/backend/src/policylens/retrieval/indexing.py` (AC-003-02, INDEX-003-01, SC-003-01).
- [x] T016 [US1] Implement `build`, `verify`, and `rollback` CLI commands in `scripts/build_retrieval_index.py`; build the actual corpus with local FastEmbed and record the validated active index (SC-003-01, INDEX-003-01).

**Checkpoint**: A local index can be built from only current, rights-eligible Feature 002 artifacts; a failed build cannot replace the active index.

## Phase 4: User Story 2 - Retrieve Evidence with Filters (Priority: P1)

**Goal**: Return bounded evidence for BM25, dense, and hybrid searches with deterministic filters, ranks, scores, and explicit empty/failure states.

**Independent Test**: Run each mode against the same fixed cases, assert relevant location anchors and permission exclusions, and verify deterministic ordering/capping.

### Retrieval Engine

- [x] T017 [P] [US2] Add tests for BM25, dense, RRF ties, metadata/permission filters, top-k bounds, overlap deduplication, source caps, and no-result/failure distinction in `apps/backend/tests/unit/test_retrieval.py` (AC-003-04 through AC-003-06, RET-003-01, SEC-003-01).
- [x] T018 [US2] Implement BM25S/dense/hybrid search, deterministic reciprocal-rank fusion, permission/source filters before returning text, deduplication, source caps, and bounded untrusted-evidence context assembly in `apps/backend/src/policylens/retrieval/search.py` (AC-003-04 through AC-003-06, RET-003-01, SEC-003-01).

### Search API

- [x] T019 [P] [US2] Add FastAPI search/readiness contract tests for valid, empty, invalid, and unavailable-index requests in `apps/backend/tests/api/test_retrieval_api.py` (AC-003-04, AC-003-05, SEC-003-01).
- [x] T020 [US2] Implement `POST /retrieval/search`, stable error responses, CORS support, and retrieval readiness reporting in `apps/backend/src/policylens/api/retrieval.py`, `apps/backend/src/policylens/api/app.py`, and `apps/backend/src/policylens/api/health.py` (AC-003-04, AC-003-05, RET-003-01).

### Retrieval Evaluation

- [x] T021 [US2] Add the frozen, source/page/row-anchored engineering cases to `data/evaluation/retrieval-cases.json`; verify every label against canonical text and document that the set is not independently reviewed (EVAL-003-01, SC-003-02).
- [x] T022 [P] [US2] Add evaluator tests for anchor-to-passage mapping, Recall@k, MRR, latency, empty-result, and citation-completeness metrics in `scripts/tests/test_retrieval_evaluation.py` (AC-003-06, EVAL-003-01).
- [x] T023 [US2] Implement evaluation over all three retrieval modes and three chunk configurations in `apps/backend/src/policylens/retrieval/evaluation.py` and `scripts/evaluate_retrieval.py`; record index/config/input hashes and mark groundedness not measured (EVAL-003-01, SC-003-02).
- [x] T024 [US2] Run the retrieval/chunking comparison and write measured metrics, limitations, and local/API-provider availability to `docs/evaluation/retrieval-evaluation.md` and `data/manifests/retrieval-evaluation-manifest.json` (EVAL-003-01, SC-003-02).

**Checkpoint**: All modes return bounded evidence with stable ranks, explicit no-result/failure states, source provenance, and permission filtering before text is exposed.

## Phase 5: User Story 3 - Verify Citations (Priority: P1)

**Goal**: Accept only claim-linked citations whose exact evidence was returned by the specified current retrieval run.

**Independent Test**: Validate exact citations, then reject unknown runs/IDs, fabricated or non-exact excerpts, source/hash/location mismatches, and expired runs.

### Tests for User Story 3

- [x] T025 [P] [US3] Add citation tests for current-run membership, exact excerpts, claim/source/hash/location matching, duplicates, expiry, unknown runs, and fabricated IDs in `apps/backend/tests/unit/test_citations.py` (AC-003-07, AC-003-08, CITE-003-01).

### Implementation for User Story 3

- [x] T026 [US3] Implement claim-linked citation models, exact excerpt/source/location validation, and a bounded expiring in-memory evidence-run registry in `apps/backend/src/policylens/retrieval/citations.py` (AC-003-07, AC-003-08, CITE-003-01).
- [x] T027 [P] [US3] Add citation-validation API tests for current, unknown, and expired runs plus rejected excerpts in `apps/backend/tests/api/test_retrieval_api.py` (AC-003-07, AC-003-08, CITE-003-01).
- [x] T028 [US3] Implement `POST /retrieval/citations/validate` against server-held run evidence in `apps/backend/src/policylens/api/retrieval.py` (AC-003-07, AC-003-08, CITE-003-01).
- [x] T029 [US3] Verify retrieval, per-build manifest, index-registry, active-pointer, and citation schemas in `specs/003-retrieval-and-citations/contracts/`; document evidence-link validation versus semantic entailment in `docs/evaluation/retrieval-evaluation.md` (CITE-003-01, SC-003-03).

**Checkpoint**: Every accepted citation resolves to evidence stored for the current run; fabricated/unknown/expired evidence is rejected.

## Phase 6: User Story 4 - Inspect a Non-Agent RAG Baseline (Priority: P2)

**Goal**: Produce one bounded answer from current-run retrieved evidence without an agent or tool loop, and expose it only after claim citations validate.

**Independent Test**: With mocked structured OpenAI output, verify a supported answer is returned with server-derived citations, no-evidence requests do not call the provider, and malformed/unsupported output fails safely.

### Tests for User Story 4

- [x] T030 [P] [US4] Add baseline service tests for no-evidence abstention/no provider call, structured request limits, extractive claim/citation equality, paraphrase rejection, generation metadata, untrusted-prompt handling, malformed output, and generation failure in `apps/backend/tests/unit/test_generation_baseline.py` (AC-003-09, AC-003-10, BASE-003-01, SEC-003-02).
- [x] T032 [P] [US4] Add answer API contract tests for answered, abstained, provider-unavailable, failed-safe, and generation metadata responses in `apps/backend/tests/api/test_retrieval_api.py` (AC-003-09, AC-003-10, BASE-003-01).

### Implementation for User Story 4

- [x] T031 [US4] Implement the bounded non-agent OpenAI Responses baseline using strict structured output, extractive claims, no tools, a versioned untrusted-evidence prompt, and current-run citation validation in `apps/backend/src/policylens/retrieval/generation.py` and `prompts/answer/non-agent-v1.md` (AC-003-09, AC-003-10, BASE-003-01, SEC-003-02).
- [x] T033 [US4] Implement `POST /retrieval/answer` with explicit provider checks, no-evidence short-circuit, stable generation errors, and lazy runtime wiring in `apps/backend/src/policylens/api/retrieval.py` and `apps/backend/src/policylens/api/app.py` (AC-003-09, AC-003-10, BASE-003-01).
- [x] T034 [US4] Add and validate the Pydantic/JSON Schema baseline answer contract, generation provider/model/prompt metadata, and failure states in `apps/backend/src/policylens/retrieval/generation.py` and `specs/003-retrieval-and-citations/contracts/baseline-answer.schema.json` (BASE-003-01, SC-003-04).

**Checkpoint**: The non-agent baseline is explicitly configured, makes one bounded structured request without tools, reports provider/model/prompt identity after generation, and returns `answered` only when every factual claim exactly equals a citation excerpt validated against current-run evidence.

## Phase 7: Polish and Cross-Cutting Concerns

- [x] T035 [P] Update the root `README.md`, `specs/README.md`, `docs/architecture/architecture.md`, `docs/traceability/traceability.md`, and `specs/003-retrieval-and-citations/quickstart.md` with the baseline endpoint, provider/privacy boundary, measured results, and limitations (DATA-003, DOC-003, BASE-003-01).
- [x] T036 Run the expanded quickstart in a fresh isolated locked environment and record actual build/search/evaluation/baseline/test outcomes in `docs/evaluation/retrieval-evaluation.md` and this task verification block (SC-003-01 through SC-003-04).
- [x] T037 Run `make test-python`, `make lint-python`, `make typecheck-python`, `make format-check-python`, `make traceability`, and `make retrieval-verify`; record failures and residual risks in `specs/003-retrieval-and-citations/tasks.md` (SC-003-01 through SC-003-04).
- [x] T038 Run the initial Feature 003 convergence review against `spec.md`, `plan.md`, `tasks.md`, contracts, tests, and outputs; record the remaining bounded-reranking and nDCG comparison gaps in this task file (SC-003-01 through SC-003-04).
- [x] T039 Add deterministic tests for local cross-encoder configuration, bounded candidate scoring, invalid output, and safe hybrid fallback in `apps/backend/tests/unit/test_reranking.py` and `apps/backend/tests/unit/test_retrieval.py` (AC-003-11, RET-003-02).
- [x] T040 Implement the local FastEmbed cross-encoder adapter and attach reranker scores plus safe run diagnostics after hybrid permission filtering in `apps/backend/src/policylens/retrieval/reranking.py`, `apps/backend/src/policylens/retrieval/search.py`, and `apps/backend/src/policylens/retrieval/models.py` (AC-003-11, RET-003-02).
- [x] T041 Add binary nDCG@k and a separate hybrid-plus-cross-encoder comparison with completion/failure/no-candidate counts in `apps/backend/src/policylens/retrieval/evaluation.py`, `scripts/evaluate_retrieval.py`, and `scripts/tests/test_retrieval_evaluation.py` (EVAL-003-01, SC-003-05).
- [x] T042 Emit safe reranking diagnostics through the agent API, update retrieval/agent contracts, and render model, candidate count, duration, and fallback state in `apps/frontend/src/components/AgentTrail.tsx` and `apps/frontend/src/data/architecture.ts` (AC-003-11, UI-009-16).
- [x] T043 Update Feature 003/009 quickstarts, architecture, and traceability; run and record a fresh local reranker evaluation in `docs/evaluation/retrieval-evaluation.md` and `data/manifests/retrieval-evaluation-manifest.json` (SC-003-05, DOC-003).
- [x] T044 Run the final Feature 003 convergence review against specifications, plan, tasks, contracts, implementation, tests, UI, and measured outputs; reconcile remaining gaps in this task file (SC-003-01 through SC-003-05).

**Final Verification**:

- `make test-python`: 118 passed across backend (82), MCP (4), and scripts (32).
- `make lint-python`, `make typecheck-python`, and `make format-check-python`: passed; mypy checked 57 source/test files and Ruff confirmed 49 backend/script plus 8 MCP files formatted.
- `make traceability`: passed with 67 global requirements, 14 feature requirements, 11 acceptance criteria, 5 success criteria, and 10 demo scenarios.
- `make data-verify`: all six Feature 002 source hashes passed. `make retrieval-verify`: active v4 index passed restart/logical-content checks at index version `45935afc940a7489563a38c32bbac909b0d8e6a9fb58182fb5c14e86ff130ea4`.
- All six Feature 003 JSON Schema contracts passed Draft 2020-12 validation; representative baseline request, provider draft, and cited response instances also validated. Pydantic additionally enforces exact claim/citation excerpt equality.
- Fresh isolated Python 3.12.14 quickstart installed 126 locked packages; `make data-parse`, `make data-verify`, `make retrieval-index`, `make retrieval-verify`, `make retrieval-eval`, and all 118 Python tests passed. No live OpenAI calls were made; this was not a clean Git checkout.
- Real API smoke with local retrieval: `GET /retrieval/ready` returned 200; no eligible evidence returned `abstained`/`NO_EVIDENCE`; evidence with `MODEL_PROVIDER=mlx` returned 503/`GENERATION_UNAVAILABLE`, confirming no provider fallback. No generation request was made. Provider-backed answer responses include OpenAI model ID and `non-agent-v1` prompt metadata; this path is covered with mocked SDK tests.
- Evaluation on the seven author-curated engineering cases measured final v4 BM25/hybrid Recall@5 `0.571`, dense Recall@5 `0.429`, citation metadata completeness `1.000`, and zero empty results. The case set is not independent review; the baseline is extractive, but answer selection quality and source accuracy remain unmeasured.
- Git-tracked/ignored status remains unverified because the workspace has no Git metadata.

### Advanced RAG Convergence Verification (2026-10-28)

- Fresh retrieval evaluation `52910cc4-f8a4-4f8f-a374-d2a9b110cb1a` completed on seven author-curated cases across three chunk configurations. All 21 local cross-encoder attempts completed; zero failed and zero had no candidates. Mean hybrid vs. hybrid+cross-encoder Recall@6 was `0.571` vs. `0.619`, nDCG@6 `0.530` vs. `0.578`, MRR `0.516` vs. `0.563`, and local latency `7.07 ms` vs. `219.46 ms`. The mixed per-chunker results and latency are recorded without a superiority claim in `docs/evaluation/retrieval-evaluation.md`.
- The answer-trail diagnostics are represented in backend models, retrieval and agent JSON Schemas, API events, frontend labels, architecture details, Feature 003/009 requirements, and quickstarts. Tests cover success, stable fallback, exact response-contract serialization, and UI display.
- `make check` passed: 297 backend, 39 MCP, 124 script, and 67 frontend tests; format, lint, typecheck, and traceability checks passed. `make security-verify` passed 145 selected backend/security/evaluation and 13 MCP tests, frontend build/tests, and secret scan with no findings. The 11 mocked Playwright tests passed.
- No live generation provider or remote reranking inference request was made. The cross-encoder inference used a local model; first-use model artifacts are cached locally.

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001-T003 are independent setup tasks.
- **Foundational (Phase 2)**: Depends on setup; typed models/config and verified canonical-source selection block all user stories.
- **User Story 1 (Phase 3)**: Depends on the foundation; creates the passage and index lifecycle used by later stories.
- **User Story 2 (Phase 4)**: Depends on a validated active index from User Story 1.
- **User Story 3 (Phase 5)**: Depends on retrieval runs and server-held evidence from User Story 2.
- **User Story 4 (Phase 6)**: Depends on a validated retrieval run and current-run citation validation from User Stories 2 and 3.
- **Polish (Phase 7)**: Depends on all four user stories, the measured retrieval evaluation, and baseline verification.

### Parallel Opportunities

- T001-T003 can run in parallel because they touch separate setup files.
- In Phase 2, T004, T006, and T008 are independent test files; implementation tasks follow their tests.
- In User Story 1, chunker and embedding tests/implementations can proceed in parallel; index lifecycle depends on both.
- In User Story 2, retrieval unit tests, API contract tests, and evaluator tests use separate files and can be prepared in parallel; their implementations follow the relevant tests.
- User Story 3 starts only after the retrieval-run contract is stable.
- User Story 4 starts only after retrieval runs and current-run citation validation are stable.

## Implementation Strategy

1. Complete setup and foundational contracts.
2. Deliver User Story 1 as the first independently testable increment: chunking, providers, local index, validation, activation, and rollback.
3. Deliver User Story 2: filtered BM25/dense/hybrid retrieval, typed API, and measured comparison.
4. Deliver User Story 3: current-run citation validation and safe rejection cases.
5. Deliver User Story 4: bounded non-agent answer generation gated by current-run citation validation.
6. Reconcile docs/traceability, run the isolated quickstart and all required gates, then converge against the feature artifacts.

Feature 003 includes only the direct non-agent baseline. No agent, production MCP tool, broader model gateway, or frontend implementation is included.
