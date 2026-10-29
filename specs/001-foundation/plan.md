# Implementation Plan: PolicyLens Foundation and Reproducibility

**Branch**: `001-foundation` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification in `specs/001-foundation/spec.md`

## Summary

Establish a reproducible three-service monorepo foundation with independent frontend, backend, and MCP processes; typed configuration; safe health/readiness; structured redacted logging; focused tests; CI; documentation structure; and enforceable requirement traceability. Keep all product behavior beyond the foundation in later features.

## Technical Context

**Language/Version**: Python 3.12+; pin `.python-version` to the available uv-managed Python 3.12.14 for the initial workspace. Pin Node.js to the observed 24.21.0 in `.node-version`; Vite's current documented Node floor is 20.19+ or 22.12+.

**Primary Dependencies**: FastAPI, Pydantic, Pydantic Settings, OpenAI Agents SDK (`openai-agents` distribution), official MCP Python SDK (`mcp` distribution), React 18+, TypeScript, Vite, Vitest, React Testing Library, ESLint, and Prettier. Select exact compatible versions during setup, verify primary documentation/release metadata, and capture versions in lockfiles. Do not add Chroma, BM25, embedding, reranking, or MLX runtime dependencies in Feature 001.

**Storage**: None in Feature 001. Chroma, BM25, corpus files, and persistent run/evaluation data belong to later features.

**Testing**: pytest for the two Python service packages; Vitest and React Testing Library for the frontend; static type/lint/build checks in CI. Playwright product E2E coverage belongs to Feature 009.

**Target Platform**: Local Linux/macOS development and Linux CI. MLX runtime evidence requires Apple silicon and is not available on this Linux x86_64 host.

**Project Type**: One repository containing three separately runnable deployable services; two Python workspace members and one frontend npm package.

**Performance Goals**: No throughput or latency target is introduced for a skeleton. Health checks, subprocess checks, and request handling use bounded timeouts; later features own measured performance targets.

**Constraints**: Preserve canonical service/package identities; keep MCP stdio by default; do not expose credentials in the browser; do not add extra deployable services; do not make production or model-quality claims.

**Scale/Scope**: Development skeleton only; no corpus, index, production agent, or final research UI.

## Constitution Check

| Principle | Feature 001 evidence | Gate |
|---|---|---|
| I. Evidence Before Fluency | No generated research answers or evidence claims are implemented. | Pass by scope boundary |
| II. Scientific Evaluation Before Complexity | CI/smoke-test foundation only; no quality claim or tuning. | Pass; later evaluation features required |
| III. Bounded Agency and Deterministic Computation | No agent or calculation runtime is added. | Pass by scope boundary |
| IV. Secure MCP Trust Boundaries | Separate stdio process, no production tools, typed startup/health contract, bounded handshake. | Pass in plan; implementation tests required |
| V. Provider Portability With Measured Parity | Typed provider settings only; no model calls or parity claim. | Pass; provider routes remain later work |
| VI. Reproducibility Is a Product Feature | Python/npm locks, runtime pins, setup commands, and traceability validation. | Pass in plan; clean install evidence required |
| VII. Privacy, Responsible AI, and Human Oversight | Placeholder-only secrets, no browser keys, redacted logs, local-only assumption. | Pass in plan; redaction tests required |
| VIII. Minimal Service Complexity and Strong Contracts | Exactly three deployable services; versioned health/OpenAPI and MCP identity. | Pass |
| IX. Testable Specifications and Traceability | Stable FR/AC/global IDs, test/evidence mapping, checker in CI. | Pass in plan; checker test required |
| X. Honest Reporting | Tasks remain unchecked until validation; unsupported behavior remains explicitly unimplemented. | Pass |

## Research Findings and Version Policy

Documentation was consulted on 2026-10-24. These are planning findings, not installed PolicyLens dependencies or test results.

| Finding | Source and implication |
|---|---|
| uv workspaces use one shared lockfile; each member has a `pyproject.toml`, and the root is also a workspace member. A project can be initialized without a build package. | [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) and [uv project initialization](https://docs.astral.sh/uv/concepts/projects/init/). Use one root workspace lock and verify no-package root mode with installed uv 0.13.0 before locking. |
| A uv lockfile records exact cross-platform resolutions and is intended for version control. | [uv project structure and lockfile](https://docs.astral.sh/uv/concepts/projects/layout/#the-lockfile). Check in `uv.lock`; do not edit it manually. |
| Vite currently documents Node.js 20.19+ or 22.12+; the installed Node 24.21.0 satisfies that floor. | [Vite Getting Started](https://vite.dev/guide/). Pin the observed Node patch and re-check during dependency selection. |
| FastAPI uses Python type hints and Pydantic models for validation and OpenAPI generation; Pydantic is a core dependency. | [FastAPI documentation](https://fastapi.tiangolo.com/). Keep the foundation contract typed and test generated OpenAPI metadata. |
| Pydantic Settings reads typed settings from environment/dotenv sources and supports aliases; unknown process environment variables can be ignored rather than rejected. | [Pydantic Settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/). Validate declared fields and compare `.env.example` keys with the configuration contract. |
| The OpenAI Agents SDK distribution is `openai-agents`; its current MCP guide supports stdio and Streamable HTTP. Its current documentation states an MCP Python dependency range of `mcp>=1.19.0,<3`. | [Agents SDK](https://openai.github.io/openai-agents-python/) and [Agents SDK MCP guide](https://openai.github.io/openai-agents-python/mcp/). Confirm the exact pinned pair before enabling the client in a later feature. |
| The official MCP Python SDK distribution is `mcp`; current stable docs are v2, support Python 3.11+, and describe stdio, Streamable HTTP, and SSE. The current repository release listing shows v2.3.0. | [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) and [SDK repository](https://github.com/modelcontextprotocol/python-sdk). PolicyLens requires Python 3.12+; verify exact API signatures and version compatibility at implementation time. |
| MCP guidance treats tool content as untrusted, emphasizes consent/least privilege, and recommends stdio to limit local-server access to its client. | [MCP specification](https://modelcontextprotocol.io/specification/latest) and [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices). Keep stdio as the local default and do not add an auxiliary listener for health. |

No exact Python or npm package versions have been selected or installed for PolicyLens. The setup task must verify current release constraints and record selected versions in `uv.lock` and `apps/frontend/package-lock.json` before service implementation proceeds.

## Architecture and Decisions

### Workspace and Package Boundaries

- Use one uv workspace rooted at `pyproject.toml`, with members `apps/backend` and `services/mcp-policy-data`; maintain one root `uv.lock`.
- Use a no-package workspace root named for workspace administration only. It is not a deployable service or public Python API. Confirm exact configuration with the installed uv 0.13.0.
- Backend distribution/import identity is `policylens`; its source root is `apps/backend/src/policylens/`.
- MCP distribution identity is `policylens-mcp`; its import root is `services/mcp-policy-data/src/policylens_mcp/`.
- Frontend npm identity is `policylens-web`; own its lockfile at `apps/frontend/package-lock.json`, not at repository root.
- No shared service source package is introduced. The frontend consumes the backend OpenAPI contract; service-internal code is not imported across package boundaries.

### Service Contracts

| Service | Foundation surface | Local boundary |
|---|---|---|
| `policylens-web` | React/TypeScript/Vite shell with typed backend base URL only. | Development server defaults to `http://localhost:5173`; no model/data-store connections. |
| `policylens-api` | FastAPI app titled `PolicyLens API`; `GET /health/live`, `GET /health/ready`, and `/docs`. | Local development interface by default; health reports process/configuration state and explicit `not_configured` components. |
| `policylens-mcp` | Independent Python MCP server named `PolicyLens Policy Data Server`; no policy-data tool/resource in this feature. | stdio; `make mcp-health` performs a bounded protocol startup/capability handshake. No separate HTTP listener. |

Health responses use a typed, versioned non-secret schema with service identity, application version, overall status, and safe component statuses. Liveness means the process responds. Readiness means the skeleton can handle its defined foundation contract; it MUST NOT claim Chroma, corpus, model, or agent readiness before those components exist.

### Configuration Contract

Root `.env.example` is a documented contract, not a checked-in secret file. Include these names from Section 24A:

`APP_NAME`, `APP_ENV`, `LOG_LEVEL`, `FRONTEND_ORIGIN`, `VITE_API_BASE_URL`, `MODEL_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_DEPLOYMENT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `MLX_BASE_URL`, `MLX_MODEL`, `EMBEDDING_PROVIDER`, `LOCAL_EMBEDDING_MODEL`, `CHROMA_PERSIST_DIRECTORY`, `CHROMA_COLLECTION_PREFIX`, `BM25_INDEX_DIRECTORY`, `ACTIVE_CORPUS_VERSION`, `MCP_TRANSPORT`, `MCP_SERVER_COMMAND`, `MCP_SERVER_URL`, `MCP_TIMEOUT_SECONDS`, `MAX_AGENT_TURNS`, `MAX_TOOL_CALLS`, `MAX_TOOL_CALLS_PER_TOOL`, `MAX_TOOL_RETRIES`, `MAX_AGENT_OUTPUT_TOKENS`, `MAX_RETRIEVAL_CANDIDATES`, `FINAL_CONTEXT_CHUNKS`, and `REQUEST_TIMEOUT_SECONDS`.

For the first API-first developer setup, the example configuration selects `MODEL_PROVIDER=openai`; the supported generation values remain `openai|mlx`. Accept `local` only as an input alias for `mlx`. The MLX route is additive, not a replacement: Feature 001 validates its configuration boundary only, while the adapter/runtime and Apple-silicon verification belong to Feature 006. Selecting an unavailable provider fails safely; no automatic fallback is allowed.

`EMBEDDING_PROVIDER=local|openai` is an independent selector, so changing the generation provider never silently changes the embedding provider. Keep local embeddings as the default when the selector is absent, as required by Section 7.3; set `EMBEDDING_PROVIDER=openai` explicitly for API embeddings. Both choices remain supported and neither removes the other. OpenAI embedding selection requires the OpenAI key and embedding model. Standard OpenAI generation requires the key and `OPENAI_MODEL`; an OpenAI-compatible Foundry deployment requires the key, `OPENAI_BASE_URL`, and `OPENAI_DEPLOYMENT_MODEL`. Incomplete Foundry configuration fails safely without using another endpoint/provider. `VITE_*` contains public frontend configuration only. The backend validates these settings without making provider calls. Chroma, BM25, and agent-budget fields are contract-only until their owning features.

Each Python service owns typed settings for the values it consumes. If the root dotenv file is loaded, use a verified filter/alias strategy so frontend-only variables do not break backend settings; also test `.env.example` key parity. Do not enable settings debug output in normal runs because it can print secret values.

### Logging, Tests, and CI

- Use Python standard-library logging with structured JSON fields: timestamp, service, level, event, correlation ID, status, and stable error code. Default logs exclude query text, evidence bodies, prompts, credentials, and chain-of-thought.
- Python tests cover each service's health/startup/settings contracts. Frontend tests cover the typed skeleton/build. Keep external providers mocked in CI; MLX and live OpenAI tests are not foundation gates.
- Add one GitHub Actions CI workflow for locked installs, Python tests, frontend lint/typecheck/test/build, Spec Kit status, and traceability validation. Pin third-party workflow actions to reviewed immutable versions/SHAs during implementation.
- `make` targets are the stable human interface: `dev-frontend`, `dev-api`, `dev-mcp`, `mcp-health`, `test`, `lint`, `typecheck`, `traceability`, and `check`. Their implementation and README documentation must agree.

### Traceability and Documentation

- Keep the global inventory in `docs/traceability/requirements-inventory.json` and a row per inventory ID plus all ten demo scenarios in `docs/traceability/traceability.md`.
- Add a small standard-library `scripts/check_traceability.py` and tests; fail on missing IDs, orphan requirements, or missing evidence mappings.
- Create `README.md`, architecture/doc placeholders, and `docs/architecture/adr/README.md` plus a template. Record Feature 001 conventions (canonical names, provider values, uv/npm lock ownership, stdio transport) as the first ADR.
- Set `.specify/feature.json` to `{"feature_directory":"specs/001-foundation"}` using the installed helper or validated state format. This supports Spec Kit without Git branch state.

## Data and Interface Models

### `ServiceHealthV1`

- `schema_version`: fixed contract version.
- `service`: canonical service identity.
- `version`: application version or an explicit development marker.
- `status`: `alive`, `ready`, `degraded`, or `not_ready`.
- `components`: allow-listed component names with `ready`, `degraded`, or `not_configured` status.
- No credentials, paths, request text, model prompts, evidence content, or internal topology.

### `AppSettings`

Typed fields corresponding to the root environment contract. Validate provider enums/alias normalization, bounded numeric settings, URL shape, and cross-field requirements. Keep secret fields typed as secret values and serialize only redacted settings summaries.

### Requirement and Evidence Links

Each row in the inventory and traceability matrix uses stable IDs, explicit status (`not_implemented` for current product requirements), target artifact, acceptance/evidence reference, and unresolved-question IDs. Evidence is planned until a run is actually performed.

## API and MCP Contracts

- The only initial HTTP contract is liveness/readiness plus FastAPI-generated OpenAPI metadata; title is `PolicyLens API`.
- The only initial MCP contract is server identity and stdio protocol startup. Do not add `query_statistics`, passage resources, or any other product capability in Feature 001.
- Frontend types for the initial health contract are generated from or checked against OpenAPI. Streaming answer events belong to a later feature and are not implemented here.

## Runtime States and Failure Paths

Feature 001 has no agent state machine. Service startup states are `starting -> configuration_validated -> ready` or `failed_safe`. A malformed required setting stops startup with a stable redacted error. An unavailable MCP process makes the protocol probe fail within its configured timeout; it does not invoke another provider or mark the RAG system ready. Unsupported platform capability (MLX on Linux) is reported as unavailable, never silently routed to OpenAI.

## Trust Boundaries and Controls

- Browser to frontend/backend: browser config is public-only; API validates requests; no secret enters the browser bundle.
- Backend to providers: no provider call in this feature; settings and error paths must not expose secrets.
- Backend to MCP: stdio process command is fixed/allow-listed by configuration, not model-selected; handshake has a timeout; startup output is treated as untrusted.
- Source documents, retrieval evidence, and future tool output are outside Feature 001 and remain untrusted in later feature plans.
- Logs/CI: emit safe metadata only; do not upload `.env`, private traces, raw data, or indexes.

## Observability Event Schema

Foundation events contain `timestamp`, `service`, `level`, `event`, `trace_id` or correlation ID where applicable, `status`, and stable `error_code`. No hidden reasoning, full query, raw tool arguments, evidence body, token, or secret is logged. Provider/model/retrieval fields remain `not_configured` until their owning feature implements them.

## Evaluation Hypotheses

There are no answer-quality or performance hypotheses to claim in Feature 001. Measurable work is setup determinism, configuration validity, service identity/health, CI reproducibility, and traceability failure detection. Retrieval, provider, MCP overhead, and quality comparisons are registered in later features.

## Migration and Rollback

No persisted application schema or active index exists in this feature. Lock/config changes are reverted through reviewed file changes. Future data/index activation and rollback is owned by Feature 003; no migration mechanism is added here.

## Implementation Phases

1. Verify installed toolchain, exact dependency versions, package identities, and uv workspace configuration; produce locked manifests.
2. Add failing smoke/contract tests, then implement the frontend, API health, and stdio MCP skeletons as independent service slices.
3. Add typed settings, environment examples, redacted structured logging, and bounded MCP readiness check.
4. Add common Make targets, ignore rules, and deterministic CI.
5. Add README/architecture/ADR structure, traceability checker, and active Spec Kit feature state.
6. Validate locked clean setup, individual service startup, health/failure cases, CI commands, and traceability; stop before any later feature.

## Project Structure

The implementation targets `apps/frontend/`, `apps/backend/src/policylens/`, `services/mcp-policy-data/src/policylens_mcp/`, `docs/architecture/adr/`, `docs/traceability/traceability.md`, `scripts/check_traceability.py`, and `specs/001-foundation/`. The complete proposed tree is recorded in [repository-assessment.md](../../docs/internal/repository-assessment.md).

**Structure Decision**: Use the proposed monorepo layout in the repository assessment. Python services are separate uv workspace members; the frontend has its own npm lockfile. No fourth deployable service or shared runtime package is introduced.

## Complexity Tracking

| Exception | Why needed | Simpler alternative rejected because |
|---|---|---|
| Three separate service packages | Explicit product boundary and independent service lifecycle are assignment requirements. | A single process/package would erase the frontend/API/MCP trust boundaries. |
| One traceability checker script | The master spec requires generated traceability and CI-visible unmapped requirements. | Manual-only mapping cannot reliably detect omissions as the inventory grows. |