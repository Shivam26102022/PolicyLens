# Feature Specification: PolicyLens Foundation and Reproducibility

**Feature Branch**: `001-foundation`  
**Created**: 2026-10-24  
**Status**: Ready for implementation review  
**Input**: User request for the first PolicyLens foundation feature, constrained by `POLICYLENS_MASTER_SPEC.md`

## Product Outcome

A contributor can set up and operate three independent PolicyLens service skeletons from a clean checkout, validate safe typed configuration, inspect service health, run focused tests and CI, and trace every requirement to planned evidence. The result is a reproducible starting point, not a functional research assistant.

## Scope

Feature 001 covers the workspace and package boundaries; React/TypeScript/Vite, FastAPI/Pydantic, and standalone Python MCP skeletons; typed environment configuration; lockfile and common-command strategy; backend health; MCP stdio protocol readiness; structured redacted logging foundations; tests and CI; documentation and ADR structure; stable requirement IDs; and traceability validation.

This feature MUST NOT implement corpus acquisition, document parsing, chunking, embeddings, Chroma, BM25, hybrid retrieval, production MCP tools/resources, complete agent logic, live provider calls, MLX runtime support, the finished frontend experience, or production deployment. Those belong to later feature specifications.

## User Scenarios & Testing

### User Story 1 - Reproducible Service Workspace (Priority: P1)

As a contributor, I can install the locked development dependencies and start each service independently so that work can proceed on one service without hiding its process boundary.

**Why this priority**: The three-service boundary and a clean setup path are prerequisites for every later feature and integration test.

**Independent Test**: Starting from a clean checkout, follow the documented setup and run each service's foundation smoke check without starting the other two.

**Acceptance Scenarios**:

1. **AC-001-01** Given a clean checkout and the documented supported runtimes, **When** a contributor installs locked dependencies, **Then** the frontend, backend, and MCP packages install without resolving unpinned dependency versions.
2. **AC-001-02** Given installed dependencies, **When** each service is started separately, **Then** its process uses its canonical service identity and does not require another service to be started first.
3. **AC-001-03** Given the workspace has no Git branch, **When** Spec Kit resolves the active feature from its configured feature directory, **Then** the feature scripts resolve `specs/001-foundation` without relying on a branch name.

### User Story 2 - Safe Local Configuration and Health (Priority: P1)

As a contributor or reviewer, I can validate non-secret settings and inspect liveness/readiness without exposing credentials or implying that unimplemented RAG components are available.

**Why this priority**: Invalid configuration and misleading health signals make local development and later service integration unsafe.

**Independent Test**: Exercise valid local settings, missing OpenAI credentials, invalid provider values, unavailable MCP process, and health responses with secret-shaped inputs.

**Acceptance Scenarios**:

1. **AC-001-04** Given local MLX and local embedding settings with no OpenAI key, **When** typed configuration is validated, **Then** configuration succeeds without selecting an external fallback.
2. **AC-001-05** Given OpenAI is selected without its required key/model settings, **When** backend startup validates settings, **Then** startup fails with a stable, redacted configuration error.
3. **AC-001-06** Given independent valid or invalid `MODEL_PROVIDER` and `EMBEDDING_PROVIDER` selections, **When** settings are loaded, **Then** each selector is validated independently, supported combinations remain available, and no provider is silently replaced or used as fallback.
4. **AC-001-07** Given the MCP stdio process is unavailable or its initialization handshake times out, **When** the health check runs, **Then** the result is a bounded unavailable/degraded status and not a fabricated ready state.
5. **AC-001-08** Given the backend is running, **When** a client requests liveness or readiness, **Then** the response uses a stable schema and contains no credentials, query text, or internal infrastructure detail.

### User Story 3 - Verifiable Foundation Changes (Priority: P1)

As a reviewer, I can run focused tests and CI and see how requirements map to implementation evidence, so that a task is not considered complete merely because files were generated.

**Why this priority**: Requirements without measurable evidence would make later evaluation and convergence unreliable.

**Independent Test**: Introduce an intentionally unmapped requirement or failing smoke test in a disposable test run and confirm the traceability check or CI fails.

**Acceptance Scenarios**:

1. **AC-001-09** Given the feature's requirements and test/evaluation plan, **When** the traceability checker runs, **Then** it identifies missing requirement, acceptance-criterion, or evidence mappings and exits unsuccessfully.
2. **AC-001-10** Given the foundation test suites, **When** the CI workflow runs on Linux, **Then** it executes the supported Python and frontend checks without live OpenAI credentials or MLX hardware.
3. **AC-001-11** Given the generated documentation skeleton, **When** a clean-checkout review is performed, **Then** local commands, service boundaries, unimplemented features, and known blockers are explicit.

## Clarifications and Assumptions

### Clarification Review - 2026-10-24

The user clarified the initial provider setup before implementation. The following source-text conflicts and defaults are resolved explicitly for this feature:

- Canonical model-provider values are `openai` and `mlx`, following Section 5.1. The `local` value shown in Section 24A MAY be accepted as an input alias for `mlx`; generated configuration and run metadata use `mlx`.
- OpenAI is the initial generation route. The MLX route is additive, not a replacement: the environment contract keeps `MODEL_PROVIDER=openai|mlx`, but Feature 001 only validates the setting. The MLX adapter/runtime is deferred until Apple-silicon validation; selecting an unavailable provider MUST fail safely without fallback.
- Embeddings have an independent `EMBEDDING_PROVIDER=local|openai` selector. Both implementations remain supported and coexist; choosing one for a run MUST NOT remove or silently replace the other. Preserve the master specification's local embedding default; set `EMBEDDING_PROVIDER=openai` explicitly for an API-based embedding run. Feature 001 validates the selector but does not implement embeddings.
- The Python import package is `policylens`, following the canonical identity table, rather than the illustrative `policy_assistant` path in Section 15.
- MCP uses stdio by default, as specified in Sections 9.2 and 24A. Its readiness check is a bounded protocol initialization/capability handshake; the backend provides HTTP health endpoints. No auxiliary MCP HTTP health listener is added.
- Feature 001 targets local development and assessment use only. A production target, public network exposure, and production authentication are not assumed.
- The supplied `POLICYLENS_MASTER_SPEC.md` is preserved. Its suggested `MASTER_SPEC_PROMPT.md` path is a documentation naming discrepancy, not permission to rename the supplied source in this run.

### Deferred Questions

| ID | Question | Effect on Feature 001 |
|---|---|---|
| Q-DATA-01 | Which challenge-provided or approved public corpus, policy theme, licence, and usage rights should Feature 002 use? | None; blocks Feature 002 source acquisition. |
| Q-DEPLOY-01 | Is a production deployment target required beyond local assessment use? | None while Feature 001 remains local-only; answer before production hosting/auth/network work. |
| Q-MLX-01 | Which Apple-silicon host and pinned MLX model will be used for local-provider verification? | None for the interface skeleton; blocks MLX runtime/parity evidence on this Linux host. |
| Q-MASTER-PATH-01 | Should the supplied master file be renamed or copied to `MASTER_SPEC_PROMPT.md`? | None for Feature 001; resolve before final README/clean-checkout instructions. |

## Edge Cases

- Missing or malformed settings, unknown enum values, negative or excessive budgets, and incompatible provider/model combinations fail validation with stable, redacted errors.
- Local MLX configuration does not require an OpenAI key and does not silently fall back to OpenAI when MLX is unavailable.
- An unavailable, timed-out, or identity-mismatched MCP process is reported as unavailable; it does not make an incomplete backend appear ready.
- Health responses and logs never include environment values, credentials, full queries, evidence bodies, or hidden reasoning.
- Vite browser configuration contains only non-secret values; attempts to place credentials in `VITE_*` configuration are rejected by review/tests.
- Absence of a corpus or Chroma index is an explicit not-configured condition, not a ready retrieval status.
- Linux CI does not claim to validate Apple-silicon MLX behavior.

## Functional Requirements

- **FR-001-01**: The workspace MUST define three separately runnable packages with canonical identities: `policylens-web`, `policylens`/`policylens-api`, and `policylens-mcp`.
- **FR-001-02**: The frontend skeleton MUST use React 18+, TypeScript, and Vite, consume only typed/versioned backend contracts, and contain no provider keys or direct model, Chroma, corpus, or MCP access.
- **FR-001-03**: The backend skeleton MUST use Python 3.12+, FastAPI, and Pydantic, declare a verified OpenAI Agents SDK dependency boundary without executing agent logic, identify itself as `policylens-api`, and publish the API title `PolicyLens API`.
- **FR-001-04**: The MCP skeleton MUST be an independently runnable Python package/process using the verified Python MCP SDK, named `policylens-mcp`, use the `PolicyLens Policy Data Server` identity, default to stdio, and expose no production data tool in this feature.
- **FR-001-05**: Backend settings MUST be typed and validate independent `MODEL_PROVIDER=openai|mlx` and `EMBEDDING_PROVIDER=local|openai` selectors, provider aliases, required credentials, numeric bounds, and incompatible combinations. Standard OpenAI generation requires `OPENAI_API_KEY` and `OPENAI_MODEL`; OpenAI-compatible Foundry generation requires `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_DEPLOYMENT_MODEL`. Provider selection MUST NOT silently replace another configured provider or trigger fallback.
- **FR-001-06**: The backend MUST expose liveness and readiness endpoints with stable, non-secret responses. MCP readiness MUST use a bounded protocol handshake rather than an invented HTTP endpoint.
- **FR-001-07**: The workspace MUST define independent Python and frontend lockfile ownership and common commands for starting, testing, linting, type-checking, and checking the three services.
- **OBS-001-01**: Service logs MUST be structured and include safe service/correlation fields while excluding secrets, private evidence, full prompts, and hidden reasoning by default.
- **TEST-001-01**: The foundation MUST include focused tests for settings, health, service identity/readiness, frontend build/component smoke behavior, and traceability; CI MUST run deterministic tests without live provider credentials or MLX hardware.
- **DOC-001-01**: The repository MUST contain a PolicyLens README/local-development skeleton, architecture documentation entry points, limitations, and an ADR index/template.
- **TRACE-001-01**: Every global inventory requirement and every Feature 001 acceptance criterion MUST map to an artifact and planned test, evaluation, inspection, or reproducible command; a checker MUST detect missing and orphan mappings.
- **SEC-001-01**: `.env.example` MUST contain placeholders only; secret values MUST NOT enter browser configuration, logs, health responses, or checked-in files.
- **SEC-001-02**: User input, future retrieved evidence, model output, and future MCP output MUST be treated as untrusted data; no shell, generic SQL, arbitrary filesystem, URL-fetch, or code-execution capability is introduced by the foundation.
- **REPRO-001-01**: Runtime and dependency versions, lockfiles, local startup commands, and feature configuration assumptions MUST be documented; no task may be marked complete without verification evidence.

## Success Criteria

- **SC-001-01**: From a clean checkout with the documented runtimes, a contributor can install locked dependencies and start each of the three service skeletons independently using documented commands.
- **SC-001-02**: Backend liveness/readiness and MCP protocol readiness return bounded, machine-readable states without secrets or claims that unimplemented data/model components are ready.
- **SC-001-03**: Configuration tests cover supported generation/embedding selector combinations, missing API credentials, invalid values, bounds, and no-fallback behavior.
- **SC-001-04**: CI executes the foundation tests/build checks without an OpenAI key, a corpus, Chroma data, or Apple-silicon hardware.
- **SC-001-05**: A deterministic traceability check maps every Feature 001 requirement/acceptance criterion and all global inventory IDs, and fails on a deliberately missing mapping.

## Key Entities

- **ServiceHealth**: Service identity, readiness/liveness status, safe component statuses, and version; never includes credentials or user content.
- **AppSettings**: Typed, validated non-secret settings plus secret references sourced only from environment/secret configuration.
- **TraceContext**: Correlation/run identifiers and safe event fields, excluding hidden reasoning and raw sensitive content.
- **RequirementRecord**: Stable requirement ID, category, priority, acceptance criteria, evidence expectation, implementation status, and unresolved-question references.

## Out of Scope

- Feature 002 corpus selection, acquisition, parsing, data quality, or EDA.
- Feature 003 chunking, embedding, Chroma, BM25, hybrid retrieval, citations, and retrieval experiments.
- Feature 004 complete OpenAI Agents SDK workflow, state machine, production tools, and answer generation.
- Feature 005 production MCP tools/resources, capability policy, and MCP/direct-call comparison.
- Feature 006 live OpenAI or MLX adapter implementation and provider-parity benchmark.
- Feature 007 frozen evaluation dataset, full metrics, and human review.
- Feature 008 complete threat model and adversarial suite.
- Feature 009 final frontend workflows, streaming UI, approval UI, and browser-level product experience.
- Feature 010 final submission reports, demo fixtures, and convergence package.
- Production deployment, hosted authentication, and public network exposure.