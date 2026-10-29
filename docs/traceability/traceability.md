# PolicyLens Requirements Traceability Seed

**Source**: `POLICYLENS_MASTER_SPEC.md`  
**Prepared**: 2026-10-24  
**Status**: The matrix tracks full end-to-end requirements. Feature 001 foundation, Feature 002 corpus pipeline, and Feature 003 retrieval/indexing/citation evidence are recorded below. Feature 003 includes one bounded non-agent answer baseline; agent orchestration, production MCP, broader model routing, and final UI behavior remain unimplemented and are not claimed.

The machine-readable source of global requirement IDs and categories is [`requirements-inventory.json`](requirements-inventory.json). Global rows refer to the complete owning-feature acceptance scope; Feature 001 evidence does not complete later feature requirements. The checker rejects missing requirement IDs, missing acceptance/evidence mappings, and orphan rows.

## Global Requirement Matrix

| ID | Category | Target artifact/feature | Expected test, evaluation, inspection, or command | Status |
|---|---|---|---|---|
| PROD-001 | Product | Foundation, README, config contracts | Canonical-name config/contract inspection | Planned |
| PROD-002 | Product | Foundation, 009 UI, 007 evaluation | Intended-use and user-journey review | Planned |
| PROD-003 | Product | 003 retrieval, 004 agent, 007 evaluation | Citation, abstention, and conflict cases | Planned |
| PROD-004 | Product | 001 foundation, 008 security | Service-topology and tool-allow-list checks | Planned |
| FE-001 | Frontend | 009 minimal UI | Responsive, keyboard, screen-reader, and accessibility tests | Planned |
| FE-002 | Frontend | 009 minimal UI | Query/filter/progress/cancel Playwright journeys | Planned |
| FE-003 | Frontend | 003 citations, 009 UI | Claim-citation/evidence component and browser tests | Planned |
| FE-004 | Frontend | 008 security, 009 UI | Provider/trace/tool/approval state tests | Planned |
| FE-005 | Frontend | 001 API contract, 009 UI | OpenAPI type check and network-boundary/error-state tests | Planned |
| FE-006 | Frontend | 009 minimal UI | Vitest/React Testing Library and Playwright reports | Planned |
| BE-001 | Backend | 001 foundation | API schema, request validation, health, and OpenAPI tests | Planned |
| BE-002 | Backend | 003 retrieval, 004 agent | Boundary/state-machine integration tests | Planned |
| BE-003 | Backend | 004 agent, 003 citations | Structured-output and citation-validator tests | Planned |
| BE-004 | Backend | 001 foundation, 008 security, 010 observability | Redaction, error taxonomy, and trace-schema tests | Planned |
| RAG-001 | RAG | 003 retrieval and citations | End-to-end ingestion/retrieval/generation/citation integration test | Planned |
| RAG-002 | RAG | 003 retrieval, 008 security | Permission-filter and untrusted-context adversarial tests | Planned |
| RAG-003 | RAG | 003 retrieval, 004 agent, 007 evaluation | Non-agent baseline versus tool-requiring agent experiment | Planned |
| DATA-001 | Data acquisition | 002 corpus ingestion, data sheet, EDA | Validated structured/unstructured manifest and reproducible EDA | Implemented in Feature 002 |
| DATA-002 | Data acquisition | 002 corpus ingestion | Allow-list, checksum, MIME, licence, idempotency tests | Implemented in Feature 002 |
| DATA-003 | Data acquisition | 002 ingestion, 010 reproducibility | Stage replay and run-manifest schema tests | Partial: Feature 002 manifests verified; Feature 010 scope remains |
| PARSE-001 | Document parsing | 002 corpus ingestion | Canonical-record schema and parser-fixture tests | Implemented in Feature 002 |
| PARSE-002 | Document parsing | 002 data sheet/quality | Structured-row, missingness, OCR, and provenance inspection | Implemented; OCR limitation documented |
| CHUNK-001 | Chunking | 003 retrieval | Boundary, structure, offset, table-row/header, and stable-location tests | Implemented in Feature 003 |
| CHUNK-002 | Chunking | 003 retrieval, 007 evaluation | Deterministic-ID tests and registered chunking experiment | Implemented in Feature 003; Feature 007 review remains |
| EMB-001 | Embeddings | 003 retrieval | Independent local-or-OpenAI `EMBEDDING_PROVIDER` contract, no-fallback/provider-separation tests, and version metadata | Implemented in Feature 003 |
| EMB-002 | Embeddings | 003 retrieval | Cache-key, model revision/hash, dimension, finite-value, and input-limit tests | Implemented in Feature 003 |
| CHROMA-001 | Chroma indexing | 003 retrieval | Collection naming, metadata, backend ownership, and permission-filter tests | Implemented in Feature 003 |
| CHROMA-002 | Chroma indexing | 003 retrieval | Persistence/restart, compatibility, activation, and rollback tests | Implemented in Feature 003 |
| CHROMA-003 | Chroma indexing | 001 foundation, 003 retrieval | Ignore-rule inspection and clean rebuild test | Partial: ignore rules and local rebuild verified; Git tracking unavailable |
| HYBRID-001 | BM25 and hybrid retrieval | 003 retrieval | BM25 stable IDs, tokenizer/config, and filter tests | Implemented in Feature 003 |
| HYBRID-002 | BM25 and hybrid retrieval | 003 retrieval | Deterministic RRF fusion/order and retrieval-control tests | Implemented in Feature 003 |
| HYBRID-003 | BM25 and hybrid retrieval | 007 evaluation | BM25/dense/hybrid and chunk/filter comparison report | Implemented in Feature 003 on author-curated engineering cases; Feature 007 review remains |
| CITE-001 | Citations | 003 retrieval, 004 agent | Citation contract and evidence provenance tests | Implemented in Feature 003 for current-run evidence linkage |
| CITE-002 | Citations | 004 agent, 007 evaluation | Forged/unknown citation rejection and status-invariant cases | Partial: unknown/fabricated evidence rejected; answer-status integration remains |
| AGENT-001 | OpenAI Agents SDK | 004 agent runtime | Pinned SDK compatibility test and non-agent comparison | Planned |
| AGENT-002 | OpenAI Agents SDK | 004 agent runtime | State-transition, budget, timeout, and cancellation tests | Planned |
| AGENT-003 | OpenAI Agents SDK | 004 agent, 005 MCP | Deterministic tool and transient/permanent failure tests | Planned |
| MCP-001 | MCP | 005 MCP service | Host/client/server capability and resource/tool contract tests | Planned |
| MCP-002 | MCP | 005 MCP service | Input/output schema, identity, timeout, and malformed-response tests | Planned |
| MCP-003 | MCP | 005 MCP service, ADRs | Tool inventory review and MCP/direct-call comparison | Planned |
| OPENAI-001 | OpenAI model provider | 006 model routing | Provider config, missing-key, mock-default, and opt-in live tests | Planned |
| MLX-001 | MLX local model provider | 006 model routing | Apple-silicon health, capability, limit, and model metadata tests | Planned |
| MLX-002 | MLX local model provider | 006 model routing, 008 security | Tool envelope/unsupported-capability and no-fallback tests | Planned |
| MLX-003 | MLX local model provider | 007 evaluation | Same-subset OpenAI/MLX comparison with platform limitations | Planned |
| SEC-001 | Security | 008 threat model | Nine-boundary threat/control review and residual-risk report | Planned |
| SEC-002 | Security | 003 retrieval, 005 MCP, 008 security | User/retrieval/MCP injection, permission, and citation suite | Planned |
| SEC-003 | Security | 005 MCP, 008 security | Allow-list, timeout, rate/budget, approval, and identity tests | Planned |
| SEC-004 | Security | 001 foundation, 008 security | Secret scan, browser config, log/trace redaction tests | Planned |
| PRIV-001 | Privacy | 002 data, 008 security | Sensitivity/licence manifest and permission retrieval tests | Planned |
| PRIV-002 | Privacy | 006 routing, 008 security | Consent-gated provider switch and human-review inspection | Planned |
| OBS-001 | Observability | 010 observability | Safe event schema, correlation, and redaction tests | Planned |
| OBS-002 | Observability | 002 ingestion, 007 evaluation, 010 observability | Required run-manifest/experiment-registry field checks | Partial: Feature 002 manifests present; evaluation registry remains |
| EVAL-001 | Evaluation | 007 evaluation | Reviewed 30+ case manifest and leakage/deduplication review | Planned |
| EVAL-002 | Evaluation | 003 retrieval, 004 agent, 006 models, 007 evaluation | Registered controlled baseline/comparison experiments | Planned |
| EVAL-003 | Evaluation | 007 evaluation report | Metric definitions, stratified outputs, limitations, reproducibility | Planned |
| EVAL-004 | Evaluation | 007 evaluation report | Human-review rubric, judge calibration, error-analysis records | Planned |
| TEST-001 | Testing | All feature specs | Unit tests tagged/mapped to requirement IDs | Planned |
| TEST-002 | Testing | 001 foundation, 003-009 | Contract/integration and failure-injection reports | Planned |
| TEST-003 | Testing | CI, 008 security, 007 evaluation | Deterministic security smoke and baseline-gated regression evidence | Planned |
| REPRO-001 | Reproducibility | 001 foundation, CI | Locked clean install and runtime/version inspection | Planned |
| REPRO-002 | Reproducibility | 002-003 ingestion/indexing | Manifest completeness and deterministic rebuild tests | Planned |
| DOC-001 | Documentation | 001 README and local setup | Clean-checkout setup walkthrough and limitation review | Planned |
| DOC-002 | Documentation | 010 submission docs | Deliverable/link review and demo-runbook inspection | Planned |
| DOC-003 | Documentation | 001 traceability, 010 convergence | Checker tests, ADR review, and demo-scenario matrix | Planned |
| DEV-001 | Deployment and local development | 001 foundation | Independent service startup and health smoke tests | Planned |
| DEV-002 | Deployment and local development | 003 indexing, 006 model routing | Local-store ownership, loopback, and browser-boundary checks | Planned |
| DEV-003 | Deployment and local development | 001 foundation | Typed settings, env-name parity, bounds, and secret checks | Planned |

## Feature 002 Acquisition, Parsing, Quality, and EDA Evidence

The active acquisition scope is two World Bank Indicators API JSON responses and four World Bank reports. The indicator series are modeled ILO estimates, so both ILOSTAT and World Bank Data attribution remain in the registry. The two ILO-published PDFs and their raw snapshots are excluded; their earlier attempts remain only in the append-only download manifest. The Singapore MOM report is retained in the registry as disabled pending written permission.

| Requirement | Evidence paths | Verification |
|---|---|---|
| ACQ-002-01, ACQ-002-10: Explicit source registry and rights gate | `data/manifests/sources.yaml`, `scripts/download_data.py`, `scripts/tests/test_download_data.py`, `data/README.md` | Registry and rights-gate tests; `make data-fetch` skips disabled MOM source |
| ACQ-002-02, ACQ-002-06, ACQ-002-07: Immutable, content-addressed snapshots and safe writes | `scripts/download_data.py`, `scripts/tests/test_download_data.py`, `data/raw/` | Atomic-write, cleanup, checksum, conditional-request, and no-overwrite tests |
| ACQ-002-03, ACQ-002-04, ACQ-002-09: Allow-listed HTTPS, bounded retries/timeouts/size, safe command status | `scripts/download_data.py`, `scripts/tests/test_download_data.py`, `Makefile` | URL, retry, pacing, size-limit, and exit-status tests |
| ACQ-002-05: JSON/PDF eligibility validation | `scripts/download_data.py`, `scripts/tests/test_download_data.py` | JSON envelope/coverage and PDF signature/structure/text-eligibility tests; validation text is discarded |
| ACQ-002-08: Append-only attempts and current snapshot metadata | `data/manifests/download-manifest.json`, `data/manifests/sources.yaml`, `scripts/tests/test_download_data.py` | Manifest, timestamp, checksum, and validator tests |
| AC-002-03, AC-002-04, AC-002-08, AC-002-09; SC-002-01, SC-002-04: Actual acquisition and verification | `data/README.md`, `data/raw/`, `data/manifests/download-manifest.json` | `make data-fetch` returns `unchanged` for all six enabled sources on repeat; `make data-verify` passes |
| AC-002-05, PARSE-002-01: Canonical structured observations | `apps/backend/src/policylens/ingestion/models.py`, `structured.py`, `apps/backend/tests/unit/test_ingestion.py`, `data/canonical/structured/` | Parser tests preserve 44 country/year rows per indicator, units/status/precision, nulls, ISO codes, API revision metadata, source hash, and provenance; `make data-parse` succeeds |
| AC-002-06, PARSE-001, PARSE-002: Canonical report documents | `apps/backend/src/policylens/ingestion/reports.py`, `apps/backend/tests/unit/test_ingestion.py`, `data/canonical/reports/` | Parser tests cover headings, page/block locations, offsets, version, source/licence provenance; all four PDFs parse without OCR |
| DATA-002-01: Source quality and documented limitations | `apps/backend/src/policylens/ingestion/quality.py`, `apps/backend/tests/unit/test_ingestion.py`, `data/processed/quality/`, `docs/02-data-sheet.md` | Both indicator datasets have 44 unique keys and zero nulls/duplicates/missing keys; PDF page/block/character, empty-page, duplicate-ID, and offset metrics are recorded |
| DATA-002-02, DATA-003: Stage input/output evidence | `data/manifests/ingestion-manifest.json`, `data/manifests/eda-manifest.json`, `data/manifests/download-manifest.json` | Acquisition, parse, and EDA manifests record stage inputs/outputs, hashes, versions, status, and findings; final clean-checkout and Feature 010 registry scope are not claimed |
| AC-002-07, EDA-002-01, DATA-001: Descriptive analyses | `scripts/eda/youth_employment.py`, `scripts/tests/test_youth_employment.py`, `docs/data/eda/results.md`, `docs/data/eda/*.png` | Two descriptive EDA outputs report questions, input hashes, values, caveats, and paths; repeat runs produced identical result/figure hashes |
| SC-002-02: Deterministic parse/EDA artifacts | `data/manifests/ingestion-manifest.json`, `data/manifests/eda-manifest.json`, `docs/data/eda/results.md` | `make data-parse` and `make data-eda` complete from local immutable snapshots; repeated EDA hashes match |

This evidence covers the completed Feature 002 corpus pipeline. `DATA-003` and `OBS-002` remain partial because their global scope also includes later Feature 007/010 experiment and observability work. Feature 003 retrieval, evidence-link validation, and non-agent baseline evidence follows; no agent or production MCP behavior is claimed.

## Feature 003 Retrieval, Indexing, and Citation Evidence

The active local index is built from only current Feature 002 canonical artifacts whose registry permits `retrieval`. Local FastEmbed BGE-small is the default; OpenAI embeddings require explicit configuration, are tested with mocked SDK calls only, and would send indexed text/query content to OpenAI. Hybrid retrieval optionally reranks up to 20 already permission-filtered candidates with a local FastEmbed cross-encoder; failures retain hybrid order. The answer baseline separately requires explicit OpenAI generation configuration and sends the bounded query/evidence payload to that provider. Every returned claim is extractive and exactly matches its server-derived current-run citation excerpt. The seven-case engineering set is author-curated and not independently human-reviewed; answer selection quality and source accuracy are not evaluated.

| Requirement | Evidence paths | Verification |
|---|---|---|
| CHUNK-003-01; AC-003-01: Stable fixed/structure-aware chunks | `apps/backend/src/policylens/retrieval/chunking.py`, `apps/backend/tests/unit/test_chunking.py`, `data/evaluation/retrieval-cases.json` | Tests cover deterministic IDs, offsets, row keys, token bounds, table headers/rows, oversized cell fragments, and one-cell prose fallback; configured chunker IDs are v4 |
| EMB-003-01; AC-003-03: Local/API embedding boundary | `apps/backend/src/policylens/retrieval/embeddings.py`, `apps/backend/src/policylens/retrieval/config.py`, `apps/backend/tests/unit/test_embeddings.py`, `apps/backend/tests/unit/test_retrieval_settings.py` | Local BGE-small is default; mocked OpenAI calls verify explicit model/dimension; tests cover tokenizer limits, normalization, provider isolation/no fallback, and model-scoped passage-cache hits/misses |
| INDEX-003-01; AC-003-02; SC-003-01: Persistent lifecycle and rollback | `apps/backend/src/policylens/retrieval/indexing.py`, `apps/backend/tests/unit/test_indexing.py`, `data/indexes/active-index.json`, `data/manifests/retrieval-index-manifest.json` | Real v4 index build/restart verification passes; same-config index fingerprints match; failed build leaves pointer unchanged; valid previous build restores atomically |
| RET-003-01/02, SEC-003-01; AC-003-04 through AC-003-06/11: Filtered retrieval and reranking | `apps/backend/src/policylens/retrieval/search.py`, `apps/backend/src/policylens/retrieval/reranking.py`, `apps/backend/src/policylens/api/retrieval.py`, `apps/backend/tests/unit/test_retrieval.py`, `apps/backend/tests/unit/test_reranking.py`, `apps/backend/tests/api/test_retrieval_api.py` | BM25/dense/hybrid, RRF ordering, source/country/year/indicator filters, server-owned permission scopes, bounded local cross-encoder scoring, original-order fallback, safe diagnostics, provenance, caps, deduplication, and no-result/failure distinction are covered |
| CITE-003-01; AC-003-07/08; SC-003-03: Run-scoped citations | `apps/backend/src/policylens/retrieval/citations.py`, `apps/backend/tests/unit/test_citations.py`, `apps/backend/tests/api/test_retrieval_api.py`, `specs/003-retrieval-and-citations/contracts/citation.schema.json` | Exact excerpt/provenance/location checks accept only current-run evidence; fabricated IDs, altered quotes, mismatches, duplicates, unknown, and expired runs are rejected |
| BASE-003-01; AC-003-09/10; SC-003-04: Non-agent answer baseline | `apps/backend/src/policylens/retrieval/generation.py`, `apps/backend/src/policylens/api/retrieval.py`, `apps/backend/tests/unit/test_generation_baseline.py`, `apps/backend/tests/api/test_retrieval_api.py`, `prompts/answer/non-agent-v1.md`, `specs/003-retrieval-and-citations/contracts/baseline-answer.schema.json` | One explicitly configured structured OpenAI call, no tools, bounded untrusted evidence, no-evidence short-circuit, extractive claim text exactly matching server-derived current-run citations, returned provider/model/prompt-version metadata, and fail-safe paraphrase/malformed/invalid-output handling |
| EVAL-003-01; SC-003-02/05: Retrieval/chunk comparison | `data/evaluation/retrieval-cases.json`, `apps/backend/src/policylens/retrieval/evaluation.py`, `scripts/evaluate_retrieval.py`, `scripts/tests/test_retrieval_evaluation.py`, `docs/evaluation/retrieval-evaluation.md`, `data/manifests/retrieval-evaluation-manifest.json` | Seven frozen anchors compare BM25, dense, hybrid, and hybrid+cross_encoder across three chunkers; report records Recall@k, nDCG@k, MRR, latency, empty rate, citation completeness, reranker completion/failure counts, hashes, and limitations without claiming superiority |
| Feature 003 contracts and manifests | `specs/003-retrieval-and-citations/contracts/`, `data/manifests/retrieval-index-manifest.json`, `data/manifests/retrieval-index-builds/` | Six JSON Schema contracts validate as Draft 2020-12; real build manifests record canonical/model/chunker/index hashes and validation results |

`CHROMA-003` remains partial because Git ignore rules and local rebuild behavior are present, but tracked/ignored status cannot be confirmed without Git metadata. Global `RAG-001`, `CITE-002`, `OBS-002`, `DATA-003`, and answer-level groundedness remain incomplete where their acceptance scope extends to Features 004, 007, 008, or 010; the Feature 003 baseline does not claim to complete those broader requirements.

## Feature 004 Bounded Agent Runtime Evidence

Feature 004 adds one request-scoped OpenAI Agents SDK agent with a typed, mockable `query_statistics` adapter, a strict state/budget ledger, exact-excerpt corpus claims, host-rendered deterministic calculation summaries, and redacted lifecycle events. Feature 005 implements the production MCP tool and passage resource. The separate Feature 004 readiness command remains blocked because it does not implement a comparison executor; historical generation comparisons are recorded under Feature 007 and do not measure the current `agent-v3` prompt.

| Requirement | Evidence paths | Verification |
|---|---|---|
| AGENT-004-01/02; SC-004-01: Finite state and bounded budgets | `apps/backend/src/policylens/agent_runtime/state.py`, `apps/backend/src/policylens/agent_runtime/runtime.py`, `apps/backend/tests/unit/test_agent_state.py`, `apps/backend/tests/unit/test_agent_runtime.py` | Typed transitions, total/per-tool calls, retries, context/output limits, cancellation, and stable outcomes covered with mocks |
| AGENT-004-03/04; AC-004-01/03: Output, evidence, and calculations | `apps/backend/src/policylens/agent_runtime/models.py`, `apps/backend/src/policylens/agent_runtime/runtime.py`, `apps/backend/tests/unit/test_agent_models.py`, `apps/backend/tests/unit/test_agent_runtime.py`, `specs/004-agent-runtime/contracts/agent-api.schema.json` | Corpus claims exactly match current-run excerpts; calculation claims are host-rendered from validated tool rows; malformed/fabricated references fail safely |
| AC-004-04/05/06; SEC-004-01: Allow-listed tool trust boundary | `apps/backend/src/policylens/agent_runtime/tools.py`, `apps/backend/tests/unit/test_agent_tools.py`, `apps/backend/tests/unit/test_agent_runtime.py` | Strict Agents SDK schema exposes only `query_statistics`; fake adapter tests cover validation, provenance, retries, timeout, empty results, and budgets |
| OBS-004-01; AC-004-07: Redacted traces | `apps/backend/src/policylens/agent_runtime/traces.py`, `apps/backend/src/policylens/agent_runtime/models.py`, `apps/backend/tests/unit/test_agent_state.py`, `apps/backend/tests/api/test_agent_api.py` | Lifecycle hooks emit safe event names only; tests verify prompts and sentinel user/model payloads are absent |
| Foundry configuration and no fallback | `apps/backend/src/policylens/settings.py`, `apps/backend/src/policylens/agent_runtime/provider.py`, `apps/backend/src/policylens/retrieval/generation.py`, `apps/backend/tests/unit/test_settings.py`, `apps/backend/tests/unit/test_agent_provider.py`, `apps/backend/tests/unit/test_generation_baseline.py` | Deployment ID precedence, explicit base URL, API-key header, Chat Completions selection, SDK retries disabled, and baseline/client parity are tested offline |
| EVAL-004-01; SC-004-03: Controlled comparison | `data/evaluation/agent-tool-cases.json`, `scripts/evaluate_agent.py`, `scripts/tests/test_agent_evaluation.py`, `data/manifests/agent-evaluation-manifest.json`, `docs/evaluation/agent-evaluation.md` | Deterministic comparator/case validation passes. The readiness-only command is blocked by `FEATURE_004_COMPARISON_NOT_IMPLEMENTED`; use Feature 007 for the separate historical comparison. No current `agent-v3` quality result is claimed; SC-004-03 remains unverified |
| DOC-004-01: Configuration and operation | `README.md`, `docs/architecture/architecture.md`, `specs/004-agent-runtime/quickstart.md`, `specs/README.md` | Foundry/standard OpenAI settings, agent route, adapter boundary, test commands, and evaluation blocker documented |

## Feature 001 Requirement Mapping

| Requirement ID | Task(s) | Expected evidence |
|---|---|---|
| FR-001-01 | T001, T003-T005 | Workspace/member manifests and canonical service identity tests |
| FR-001-02 | T001-T003 | Frontend smoke, type, lint, and build checks |
| FR-001-03 | T001, T002, T004 | API health tests and OpenAPI title/schema inspection |
| FR-001-04 | T001, T002, T005 | MCP stdio handshake and identity test; no product tools |
| FR-001-05 | T006-T007 | Settings success, failure, alias, bounds, and compatibility tests |
| FR-001-06 | T002, T004-T005, T011 | Safe health schema and bounded MCP readiness checks |
| FR-001-07 | T001, T008, T011 | Locked installs and working common Make targets |
| TEST-001-01 | T002, T006, T008, T011 | CI-run foundation tests without live API key or MLX hardware |
| DOC-001-01 | T009 | README, local setup, architecture, limitations, and ADR review |
| TRACE-001-01 | T010-T011 | Checker passes complete matrix and fails missing/orphan mapping fixtures |
| SEC-001-01 | T006-T008 | Placeholder-only env, browser boundary, secret scan, and log tests |
| SEC-001-02 | T005, T007 | MCP capability inventory and untrusted startup/error handling review |
| OBS-001-01 | T006-T007 | Structured correlation fields and redaction tests |
| REPRO-001-01 | T001, T007-T008, T011 | Runtime pins, lockfiles, config hash/inspection, clean-install evidence |

## Feature 001 Acceptance Scenario Mapping

| Acceptance ID | Validation | Task(s) |
|---|---|---|
| AC-001-01 | Clean locked Python/npm install | T001, T008, T011 |
| AC-001-02 | Start frontend, API, and MCP independently with canonical identities | T002-T005, T011 |
| AC-001-03 | Resolve active feature from `.specify/feature.json` without a Git branch | T010 and Spec Kit prerequisite helper |
| AC-001-04 | Local MLX/local embeddings validate without OpenAI key and without external fallback | T006-T007 |
| AC-001-05 | OpenAI selected without required key/model fails safely and redacted | T006-T007 |
| AC-001-06 | Invalid provider or numeric budget is rejected | T006-T007 |
| AC-001-07 | Missing/timed-out MCP process returns bounded unavailable/degraded status | T002, T005, T011 |
| AC-001-08 | API health response is stable and contains no secrets or request content | T002, T004, T007 |
| AC-001-09 | Missing/orphan requirement or evidence mapping fails the checker | T010-T011 |
| AC-001-10 | Linux CI runs deterministic Python/frontend checks without API key or MLX | T008, T011 |
| AC-001-11 | Local commands, boundaries, limitations, and blockers are documented | T009, T011 |

## Definition of Done Mapping

| Success criterion | Evidence source | Task(s) |
|---|---|---|
| SC-001-01 | Clean setup and independent process smoke results | T001-T005, T008, T011 |
| SC-001-02 | Health/protocol schemas and bounded unavailable states | T002, T004-T005, T011 |
| SC-001-03 | Provider/config boundary test report | T006-T007 |
| SC-001-04 | Linux CI report without external provider or MLX | T008, T011 |
| SC-001-05 | Traceability checker report including negative fixtures | T010-T011 |

## Ten Required Demonstration Scenarios

The scenario rows are planning fixtures only. Each must later record expected state transitions, required evidence, allowable tools, forbidden behavior, and a measurable success condition as required by Section 17.

| ID | Scenario | Expected state path and evidence | Allowed tool calls | Forbidden events | Success criteria | Status |
|---|---|---|---|---|---|---|
| DEMO-01 | Factual answer with a correct source passage and citation. | `RECEIVED -> VALIDATED -> EVIDENCE_SEARCH -> ANSWER_DRAFT -> CITATION_VALIDATION -> COMPLETE`; evidence IDs come from the frozen case manifest. | `search_evidence`; `get_source_passage` when needed. | Unsupported corpus facts; fabricated passage IDs; quotes absent from retrieved evidence. | Each claim maps to the exact retrieved source/passage and bounded quote accepted by the citation validator. | Planned |
| DEMO-02 | Synthesis across structured and unstructured sources. | Retrieval and evidence assessment include at least one permitted structured row set and one report passage from the case manifest. | `search_evidence`; `query_statistics`; `get_source_passage`. | Treating prose as exact statistical rows; omitting a source type or its provenance. | Both source types contribute, and citations distinguish row keys from passage locations. | Planned |
| DEMO-03 | Deterministic calculation with underlying-data citations. | `RECEIVED -> VALIDATED -> TOOL_SELECTION -> TOOL_EXECUTION -> TOOL_VALIDATION -> OUTPUT_VALIDATION -> CITATION_VALIDATION -> COMPLETE`; retain row keys and source hash. | `query_statistics`; `get_source_passage` only if needed to inspect a data definition. | Model-performed arithmetic; excessive row request; unsupported aggregation; uncited result. | Numeric result matches deterministic reference calculation and reports operation, formula, rounding, and input-row evidence. | Planned |
| DEMO-04 | Clarification or abstention for ambiguous/insufficient evidence. | Search, evidence assessment, then `CLARIFICATION_REQUIRED` or `ABSTAINED`; no answer draft is accepted without support. | Bounded `search_evidence`; no other tool unless the case explicitly requires it. | Guessing missing qualifiers; uncited factual answer; multiple unfocused questions. | One focused clarification question or a concise evidence-based abstention reason. | Planned |
| DEMO-05 | Conflicting sources explained with both sides cited. | `EVIDENCE_SEARCH -> EVIDENCE_ASSESSMENT -> CONFLICT -> OUTPUT_VALIDATION -> CITATION_VALIDATION -> COMPLETE`. | `search_evidence`; `get_source_passage`; `query_statistics` only when the case requires structured evidence. | Silently selecting one side; hiding disagreement; presenting incompatible measures as directly comparable. | Both positions, their provenance, and the reason for unresolved conflict are shown with valid citations. | Planned |
| DEMO-06 | Resist user, retrieved-document, and MCP prompt injection. | Input validation/evidence assessment keeps untrusted content within data boundaries; terminal outcome follows application policy. | Only allow-listed read-only tools required by the original user request. | Following embedded instructions; arbitrary URL/file/shell access; data exfiltration; unapproved provider switch. | Attack text does not alter policy, reveal protected data, or cause an unauthorized tool call. | Planned |
| DEMO-07 | Recover safely from failed retrieval or tool execution. | Transient failure may use configured bounded retry; otherwise transition to `FAILED_SAFE` or a documented unavailable/abstention state with trace ID. | Only the allow-listed tool required for the request; retry transient failures within configured budgets. | Unbounded retries; retrying invalid arguments blindly; unsafe external fallback; unsupported answer after failure. | User receives an honest safe status, stable error code, and trace ID; retry count stays within budget. | Planned |
| DEMO-08 | Discover MCP capabilities and invoke a valid operation. | MCP startup -> identity/version check -> capability/schema validation -> approved tool invocation -> output validation. | Only the discovered, version-allow-listed capability required by the case. | Invoking unknown or mismatched server capabilities; trusting tool descriptions as application policy. | Expected server identity and schemas match; invocation/result are recorded without private reasoning. | Planned |
| DEMO-09 | Handle invalid MCP arguments, timeout, unavailable server, and malformed response. | Invalid arguments fail without retry; transient timeout/unavailable paths use bounded policy; malformed output fails closed. | Only the named allow-listed tool for the case; no tool after schema/identity failure. | Blind retries for invalid input; accepting malformed output; logging raw secrets; provider fallback without approval. | Each fault maps to a stable error code, bounded completion, and no unsupported answer. | Planned |
| DEMO-10 | Ignore instructions embedded in untrusted MCP output. | MCP output is validated and delimited as data before evidence assessment; completion follows the original user request/policy. | Only tools independently justified by the original user request, not by MCP output instructions. | Tool output selecting another tool, changing provider, overriding system policy, or requesting data exfiltration. | Embedded instruction is ignored as an instruction and no unauthorized call or disclosure occurs. | Planned |

## Assignment-Level Crosswalk

| Assessment requirement | Inventory IDs | Planned specification/evidence |
|---|---|---|
| Problem framing and intended-use boundary | PROD-002, PROD-003, PROD-004 | Foundation spec, README, 007 evaluation cases |
| Two source types, provenance, EDA | DATA-001, DATA-002, PARSE-001, PARSE-002 | 002 spec, source manifest, data sheet, reproducible EDA |
| End-to-end RAG and simple baseline | RAG-001, RAG-003 | 003 integration tests and non-agent baseline experiment |
| Two or more retrieval approaches | HYBRID-001, HYBRID-002, HYBRID-003 | 003 retrieval tests and registered comparison |
| Chunking and stable citations | CHUNK-001, CHUNK-002, CITE-001, CITE-002 | 003 chunk/citation contracts and tests |
| OpenAI and MLX configurations | OPENAI-001, MLX-001, MLX-002, MLX-003 | 006 provider contracts and 007 parity subset |
| Structured outputs and bounded agent | BE-003, AGENT-001, AGENT-002, AGENT-003 | 004 schemas/state-machine tests |
| Deterministic calculation and MCP tool/resource/client | MCP-001, MCP-002, MCP-003 | 005 tool/resource/protocol tests and ADR |
| 30+ frozen evaluation cases and human review | EVAL-001, EVAL-004 | 007 reviewed manifest, rubric, and review record |
| Retrieval/generation/safety/latency/cost metrics | EVAL-002, EVAL-003, MLX-003 | 007 reproducible report and limitations |
| Threat model, security, privacy, and redaction | SEC-001 through SEC-004, PRIV-001, PRIV-002 | 008 threat model/adversarial tests; 001 secret smoke tests |
| Reproducible setup and locked dependencies | REPRO-001, REPRO-002, DEV-001, DEV-003 | 001 locks, clean setup, CI, and pipeline manifests |
| Ten demo scenarios | DEMO-01 through DEMO-10 | Later feature fixtures and 20-minute runbook |
| Submission reports and innovation assessment | DOC-001, DOC-002, DOC-003 | 010 deliverable checklist and convergence review |

## Feature 001 Implementation Evidence

| Check | Observed result |
|---|---|
| Locked setup | `make setup` passed in the workspace and a clean source copy; uv built both Python workspace members and `npm ci` completed with zero reported vulnerabilities. |
| Full local gate | `make check` passed: 14 backend tests, 3 MCP tests, 3 traceability tests, 1 frontend test, Python/TypeScript type checks, lint, and formatting. |
| Frontend production build | `npm --prefix apps/frontend run build` passed with Vite 8.3.5. |
| MCP stdio probe | The historical Feature 001 probe checked the initial server identity before Feature 005 added product capabilities. The current Feature 005 server exposes the read-only `query_statistics` tool and policy-passage resource template. |
| Live API | `/health/live` returned HTTP 200. `/health/ready` returned HTTP 503 with `degraded`, MCP `ready`, and generation/embedding/retrieval `not_configured`. The run used a configuration-only MLX placeholder and made no model call. |
| Frontend dev server | `http://127.0.0.1:5173/` returned HTTP 200. |
| CI workflow | YAML parsed successfully; all actions are pinned to verified immutable commits. GitHub-hosted Actions were not run because the workspace has no Git repository or remote; the equivalent local commands passed. |
| Spec Kit | The generated prerequisite helper resolves `specs/001-foundation`; final integration status is `OK`. Spec Kit's implementation/converge chat skills were not separately invoked; implementation followed the generated task list and was manually checked against the artifacts. |