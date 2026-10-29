---
description: "Dependency-ordered implementation tasks for PolicyLens Foundation and Reproducibility"
---

# Tasks: PolicyLens Foundation and Reproducibility

**Input**: Design documents in `specs/001-foundation/`  
**Prerequisites**: `spec.md` and `plan.md`  
**Status**: Feature 001 implementation tasks are checked from local evidence. GitHub-hosted Actions, live OpenAI calls, and MLX inference were not run.

## Task Format

Each task lists its requirements and acceptance IDs, exact target paths, dependencies, validation action, and completion evidence. `[P]` means the task can run in parallel with other `[P]` tasks in its phase without editing the same files.

## Phase 1: Workspace Setup

**Purpose**: Create the locked package/workspace skeleton without product behavior.

- [x] **T001** Create the Python workspace and frontend package manifests with reviewed dependency pins.
  - Requirements/acceptance: `FR-001-01`, `FR-001-07`, `REPRO-001-01`, `AC-001-01`.
  - Targets: `pyproject.toml`, `.python-version`, `apps/backend/pyproject.toml`, `services/mcp-policy-data/pyproject.toml`, `uv.lock`, `.node-version`, `apps/frontend/package.json`, `apps/frontend/package-lock.json`.
  - Dependencies: None.
  - Parallel: No; this establishes package and lock ownership.
  - Validation: Verify release metadata and primary docs for every selected dependency; run locked resolution/install checks with installed uv/npm versions.
  - Completion evidence: `uv lock` resolved 58 packages; `uv sync --locked --all-packages --all-groups` built/installed both members; `npm ci --prefix apps/frontend` installed the frontend tree with zero reported vulnerabilities. The same setup passed in a clean source copy. No Chroma, BM25, embedding, or MLX runtime package was added.

## Phase 2: Contract Tests First

**Purpose**: Define observable service boundaries before implementing skeletons.

- [x] **T002** Add failing service startup/health contract tests for frontend, API, and MCP.
  - Requirements/acceptance: `FR-001-02` through `FR-001-04`, `FR-001-06`, `TEST-001-01`, `AC-001-02`, `AC-001-07`, `AC-001-08`.
  - Targets: `apps/frontend/tests/smoke.test.tsx`, `apps/backend/tests/api/test_health.py`, `services/mcp-policy-data/tests/test_startup.py`.
  - Dependencies: `T001`.
  - Parallel: Yes; the three tests are in distinct service test directories.
  - Validation: Run each focused test before its service implementation and confirm it fails for the expected missing contract.
  - Completion evidence: Red-first tests initially failed on the missing modules; frontend, backend health, and real MCP stdio identity tests now pass in `make check`.

- [x] **T003** Add the minimal React/TypeScript/Vite frontend shell.
  - Requirements/acceptance: `FR-001-02`, `AC-001-02`, `AC-001-10`.
  - Targets: `apps/frontend/index.html`, `apps/frontend/src/main.tsx`, `apps/frontend/src/App.tsx`, `apps/frontend/src/api/health.ts`, `apps/frontend/tests/smoke.test.tsx`, `apps/frontend/vite.config.ts`, `apps/frontend/tsconfig.json`, `apps/frontend/eslint.config.js`.
  - Dependencies: `T001`, `T002`.
  - Parallel: Yes, with `T004` and `T005` after the contracts exist.
  - Validation: Run frontend smoke test, type check, lint, and production build.
  - Completion evidence: Vitest smoke, TypeScript check, ESLint, Prettier, and Vite production build pass. Runtime frontend configuration contains only `VITE_API_BASE_URL`.

- [x] **T004** Add the FastAPI/Pydantic backend skeleton and safe health endpoints.
  - Requirements/acceptance: `FR-001-03`, `FR-001-06`, `AC-001-02`, `AC-001-05`, `AC-001-08`.
  - Targets: `apps/backend/src/policylens/__init__.py`, `apps/backend/src/policylens/api/app.py`, `apps/backend/src/policylens/api/health.py`, `apps/backend/tests/api/test_health.py`.
  - Dependencies: `T001`, `T002`.
  - Parallel: Yes, with `T003` and `T005` after the contracts exist.
  - Validation: Run focused API tests and inspect generated OpenAPI title/health schemas; no model call is permitted.
  - Completion evidence: Backend health/OpenAPI/redaction tests pass; live `/health/live` returned 200 and `/health/ready` returned 503 with `degraded`, `mcp=ready`, and unimplemented product components `not_configured`.

- [x] **T005** Add the standalone stdio MCP server skeleton and bounded protocol readiness check.
  - Requirements/acceptance: `FR-001-04`, `FR-001-06`, `SEC-001-02`, `AC-001-02`, `AC-001-07`.
  - Targets: `services/mcp-policy-data/src/policylens_mcp/__init__.py`, `services/mcp-policy-data/src/policylens_mcp/server.py`, `services/mcp-policy-data/src/policylens_mcp/__main__.py`, `services/mcp-policy-data/tests/test_startup.py`.
  - Dependencies: `T001`, `T002`.
  - Parallel: Yes, with `T003` and `T004` after the contracts exist.
  - Validation: Use the pinned MCP SDK's documented stdio lifecycle and exercise initialization with a timeout; do not expose a production tool/resource.
  - Completion evidence: The MCP subprocess handshake test and `make mcp-health` pass; the server reports `PolicyLens Policy Data Server` and exposes no product tool/resource.

## Phase 3: Configuration and Logging

**Purpose**: Make local settings typed, bounded, and safe before connecting providers.

- [x] **T006** Add failing configuration and logging-redaction tests.
  - Requirements/acceptance: `FR-001-05`, `OBS-001-01`, `SEC-001-01`, `SEC-001-02`, `AC-001-04` through `AC-001-06`, `AC-001-08`.
  - Targets: `apps/backend/tests/unit/test_settings.py`, `apps/backend/tests/unit/test_logging.py`, `services/mcp-policy-data/tests/test_settings.py`.
  - Dependencies: `T001`.
  - Parallel: Yes; these tests do not modify service implementation files.
  - Validation: Run each focused test before implementing settings/logging and confirm it fails for missing behavior.
  - Completion evidence: Ten backend settings tests cover independent selectors, local no-key mode, required OpenAI credentials/models, alias normalization, invalid provider/bounds, and `.env.example` key/secret checks; logging redaction tests pass.

- [x] **T007** Implement typed settings and structured redacted logging for each Python service.
  - Requirements/acceptance: `FR-001-05`, `OBS-001-01`, `SEC-001-01`, `REPRO-001-01`.
  - Targets: `.env.example`, `.gitignore`, `apps/backend/src/policylens/settings.py`, `apps/backend/src/policylens/observability/logging.py`, `services/mcp-policy-data/src/policylens_mcp/settings.py`, `services/mcp-policy-data/src/policylens_mcp/logging.py`.
  - Dependencies: `T004`, `T005`, `T006`.
  - Parallel: No; configuration names and log redaction policy are shared contracts.
  - Validation: Run settings/logging tests and compare `.env.example` keys with the declared configuration schema.
  - Completion evidence: Typed settings/logging tests pass; `.env.example` is placeholder-only, selects OpenAI generation, and retains local embeddings as the default with OpenAI independently selectable; `MODEL_PROVIDER=local` normalizes to `mlx`; log output omits message contents.

## Phase 4: Development Commands and CI

**Purpose**: Make the foundation reproducibly runnable and gate it in CI.

- [x] **T008** Add common Make targets, repository ignore rules, and deterministic CI.
  - Requirements/acceptance: `FR-001-07`, `TEST-001-01`, `SEC-001-01`, `REPRO-001-01`, `AC-001-01`, `AC-001-10`.
  - Targets: `Makefile`, `.gitignore`, `.github/workflows/ci.yml`.
  - Dependencies: `T003`, `T004`, `T005`, `T007`.
  - Parallel: No; targets must match actual service scripts and lockfiles.
  - Validation: Run the Make targets and every workflow-equivalent command locally; parse the workflow and verify immutable action refs. A GitHub-hosted run requires a GitHub remote.
  - Completion evidence: `make check`, `make mcp-health`, setup, and workflow-equivalent commands pass locally; YAML parses and all external actions are pinned to verified commits. GitHub-hosted Actions were not run because this workspace has no Git repository or remote.

## Phase 5: Documentation and Traceability

**Purpose**: Keep the workspace understandable and expose missing mappings before implementation is considered converged.

- [x] **T009** Add the PolicyLens setup/architecture documentation and ADR template/convention decision.
  - Requirements/acceptance: `DOC-001-01`, `AC-001-11`.
  - Targets: `README.md`, `docs/architecture/architecture.md`, `docs/architecture/architecture-diagram.md`, `docs/overview/limitations.md`, `docs/architecture/adr/README.md`, `docs/architecture/adr/0000-template.md`, `docs/architecture/adr/0001-foundation-conventions.md`.
  - Dependencies: `T001` through `T008`.
  - Parallel: Yes, with `T010`; the target files do not overlap.
  - Validation: Follow setup instructions from a clean workspace and verify links/paths point to existing artifacts.
  - Completion evidence: README setup commands pass in a clean source copy; architecture, limitations, and ADR documents distinguish the implemented foundation from later features.

- [x] **T010** Add traceability validation and verify the active Spec Kit feature directory.
  - Requirements/acceptance: `TRACE-001-01`, `DOC-001-01`, `AC-001-03`, `AC-001-09`.
  - Targets: `scripts/check_traceability.py`, `scripts/tests/test_traceability.py`, `docs/traceability/traceability.md`, `.specify/feature.json`.
  - Dependencies: `T001` through `T008`; `docs/traceability/requirements-inventory.json` is the inventory source.
  - Parallel: Yes, with `T009`; the target files do not overlap.
  - Validation: Test complete coverage, a missing requirement, an orphan ID, and an acceptance criterion with no evidence; run the Spec Kit prerequisite helper against `specs/001-foundation`.
  - Completion evidence: Three checker tests pass, the real checker reports 67/67 global requirements, 14/14 Feature 001 requirements, 11/11 acceptance criteria, 5/5 success criteria, and 10 demo scenarios; the Spec Kit helper resolves `specs/001-foundation`.

## Phase 6: Clean-Checkout Acceptance

**Purpose**: Verify the implemented foundation and stop before any later feature.

- [x] **T011** Run the complete Feature 001 acceptance and document actual results/limitations.
  - Requirements/acceptance: All Feature 001 requirements and `SC-001-01` through `SC-001-05`.
  - Targets: `README.md`, `docs/traceability/traceability.md`, `specs/001-foundation/tasks.md`, CI evidence artifacts as configured.
  - Dependencies: `T001` through `T010`.
  - Parallel: No; this is the final integration/clean-checkout gate.
  - Validation: Locked setup and full Make gate in a clean source copy; independent frontend/API/MCP smoke checks; configuration failures; traceability checker; Spec Kit integration and prerequisite status.
  - Completion evidence: Actual commands, versions, test results, live health responses, and limitations are recorded. GitHub-hosted CI, live OpenAI, and MLX inference remain explicitly unverified. No Feature 002/RAG/agent/product MCP behavior was implemented.

## Dependencies and Execution Order

- `T001` is the toolchain/lockfile prerequisite.
- `T002` and `T006` define tests before their service/config implementations.
- `T003`, `T004`, and `T005` can run in parallel after `T001`/`T002` because they own disjoint service files.
- `T007` follows the service contract and failing settings/logging tests.
- `T008` follows real package commands; `T009` and `T010` may then run in parallel.
- `T011` is the final gate and depends on all other tasks.

## Implementation Strategy

1. Verify/pin dependencies and write failing service contract tests.
2. Build and validate each service skeleton independently.
3. Add configuration, redacted logging, common commands, CI, documentation, and traceability.
4. Validate from a clean checkout and update task statuses only with recorded evidence.
5. Stop at Feature 001; later feature work requires its own approved specification and gates.

## Phase 7: Convergence

**Purpose**: Close the hosted-CI evidence gap that cannot be verified without a GitHub repository remote.

- [ ] **T012** Run the GitHub-hosted CI workflow and record its result per `AC-001-10` and `SC-001-04` (partial).
  - Requirements/acceptance: `TEST-001-01`, `REPRO-001-01`, `AC-001-10`, `SC-001-04`.
  - Targets: `.github/workflows/ci.yml`, `docs/traceability/traceability.md`, `specs/001-foundation/tasks.md`.
  - Dependencies: `T008`, `T011`, and an approved Git repository remote containing this workspace.
  - Parallel: No; the workflow must run against the reviewed repository state.
  - Validation: Push the reviewed workspace to its approved GitHub repository, run the workflow on Linux, and verify both backend/MCP and frontend jobs without OpenAI credentials or MLX hardware.
  - Completion evidence: Record the workflow run URL, commit, action results, and any failures. The current workspace has no `.git` directory or remote, so this task is blocked here; local workflow-equivalent commands and YAML parsing already pass.