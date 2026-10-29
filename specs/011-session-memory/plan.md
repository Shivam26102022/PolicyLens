# Implementation Plan: Session Chat and Memory

**Branch**: `011-session-memory` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-session-memory/spec.md`

## Summary

Implement persistent, workspace-scoped chat sessions with application-managed follow-up context. Store ordered transcript turns in SQLite, retain the last five completed user/assistant pairs as hot context, and keep the full transcript available through paginated session history. Store bounded conversation-pair representations in a separate Chroma collection and stable persistence path under the configured Chroma root, then retrieve at most five relevant memories within the same local workspace. Memories remain untrusted context, never evidence; every answer continues to retrieve and validate current corpus evidence. Add visible session controls, memory controls, safe progress states, and explicit handling for persistence and retrieval failures.

The browser will send an opaque workspace UUID and selected session ID to typed backend APIs. The backend, not the browser, loads hot context and long-term memories before model execution and persists the resulting turn. No provider-managed conversation ID or new service is introduced. External model or embedding processing remains subject to per-turn consent.

## Technical Context

**Language/Version**: Python 3.12+, TypeScript 5.9, React 18.3

**Primary Dependencies**: FastAPI 0.162, Pydantic 2, ChromaDB 1.x, existing provider-neutral embedding implementations, SQLite from Python's standard library; existing React/Vite frontend

**Storage**: SQLite at a fixed, ignored path beneath `data/indexes/`; a dedicated versioned Chroma conversation-memory collection in a stable local persistence path beneath the configured Chroma root, separate from per-build corpus databases

**Testing**: pytest for backend model, storage, API, runtime, and integration tests; Vitest and Playwright for frontend/session workflows; Ruff, mypy, ESLint, TypeScript, and repository traceability checks

**Target Platform**: Existing local Linux/macOS development deployment with the web client and API as separate processes

**Project Type**: Three-service web application; this feature changes only the API and web application and adds no service

**Performance Goals**: No new latency SLA; preserve the existing 90-second agent request timeout. Bound session-list pages to 50, transcript pages to 100 turns, hot context to five completed pairs, and long-term retrieval to five records.

**Constraints**: Local single-operator workspace; persistence requires acknowledgement that content is public, synthetic, or appropriately anonymized; long-term memory defaults off; transcript and memory persist until deletion; browser workspace IDs are not authentication; external model/embedding requests require explicit per-turn consent; full transcripts are not injected into prompts; memory is not citation evidence; no new runtime dependency or provider-managed conversation state; keep memory's Chroma persistence path separate from versioned corpus databases to avoid index-version coupling and cross-process Chroma writes

**Scale/Scope**: One browser-profile workspace per local operator, with session and memory data isolated by opaque UUID. Transcript pages are bounded and older turns remain fetchable; long-term storage is bounded per request but retained until the user clears it.

## Constitution Check

### Pre-Design Gate

- **I. Evidence Before Fluency — PASS**: Conversation memories are explicitly untrusted context. Only current-run retrieved passages and deterministic tool output can support claims.
- **II. Scientific Evaluation Before Complexity — PASS**: The feature adds no changes to evidence retrieval or ranking. Memory retrieval will use a versioned synthetic evaluation fixture and deterministic comparison against a no-memory baseline; configuration, applicable seeds, stratified metrics, retrieval latency, cost estimates, qualitative errors, limitations, and negative results will be retained outside runtime prompts. No answer-quality or provider-parity gain will be claimed.
- **III. Bounded Agency and Deterministic Computation — PASS**: Five-pair hot context, five retrieved memories, bounded API pages, the existing agent request/token limits, and the existing run timeout remain in force.
- **IV. Secure MCP Trust Boundaries — PASS**: No new MCP tools or trust boundary are introduced. Memory text is not allowed to select tools or alter policy.
- **V. Provider Portability With Measured Parity — PASS**: Session context is provider-neutral and application-managed. Existing local/OpenAI routes remain explicit; external embedding use must be consent-gated as well as external generation.
- **VI. Reproducibility Is a Product Feature — PASS**: Memory collection schema and embedding identity are versioned; quickstart steps and focused offline tests make the feature reproducible.
- **VII. Privacy, Responsible AI, and Human Oversight — PASS**: Persistence requires a recorded acknowledgement limiting content to public, synthetic, or appropriately anonymized data; long-term memory defaults off. Data is stored locally, scoped by workspace, excluded from raw logs, explicitly clearable, and disclosed before external processing. The workspace UUID is not represented as production authentication.
- **VIII. Minimal Service Complexity and Strong Contracts — PASS**: Uses the existing API, web app, SQLite standard library, and configured Chroma persistence; no fourth service or framework is added.
- **IX. Testable Specifications and Traceability — PASS**: Before implementation approval, each FR/SC and acceptance scenario will map to a planned test, evaluation, inspection, or command, and each planned test will map to requirement IDs. The traceability matrix will be updated with implemented verification evidence during polish.
- **X. Honest Reporting — PASS**: Validation results and any unavailable local model/index prerequisites will be reported as observed; no live provider call is required for the core test suite.

**Gate result**: PASS. No constitution exception or ADR is required.

### Post-Design Gate

- **I. Evidence Before Fluency — PASS**: The API contract keeps memory outside current-run evidence and citation-validation inputs.
- **II. Scientific Evaluation Before Complexity — PASS**: A versioned synthetic evaluation fixture and harness compare stratified precision@5/recall@5 to the no-memory baseline; configuration, applicable seeds, retrieval latency, cost estimates, qualitative errors, limitations, and negative results are retained. No answer-quality claim is authorized.
- **III. Bounded Agency and Deterministic Computation — PASS**: Both hot context and memory retrieval have fixed maxima; transcript pages and external calls remain bounded by existing limits.
- **IV. Secure MCP Trust Boundaries — PASS**: Memory is not passed to MCP tools or used to select tools.
- **V. Provider Portability With Measured Parity — PASS**: Context is host-managed and provider-neutral; external embedding use is gated by fresh per-turn consent.
- **VI. Reproducibility Is a Product Feature — PASS**: The memory collection has a stable schema/version and embedding identity, and its own persistence path prevents corpus-index rebuilds from replacing it.
- **VII. Privacy, Responsible AI, and Human Oversight — PASS**: Data-use acknowledgement is required before persistence and memory defaults off. Workspace filters are mandatory and exact-match; session deletion and memory clearing are explicit. The memory Chroma path is separate from corpus database paths to avoid concurrent Chroma writer risk.
- **VIII. Minimal Service Complexity and Strong Contracts — PASS**: Contracts add routes to the existing API and do not add a service, framework, or dependency.
- **IX. Testable Specifications and Traceability — PASS**: Session, memory, consent, citation-boundary, and UI behaviors have pre-implementation traceability to planned tests or checks; the final matrix records actual evidence and unmapped items.
- **X. Honest Reporting — PASS**: The plan requires updating the quickstart with actual results and explicitly reports skipped live-provider checks.

**Post-design gate result**: PASS. No unresolved design decision requires a constitution exception.

## Project Structure

### Documentation (this feature)

```text
specs/011-session-memory/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── sessions-api.md
│   └── agent-session-context.md
├── checklists/
│   └── requirements.md
├── traceability.md
├── evaluation-results.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/backend/src/policylens/
├── api/
│   ├── agent.py
│   ├── app.py
│   └── sessions.py
├── agent_runtime/
│   ├── models.py
│   └── runtime.py
└── conversations/
    ├── __init__.py
    ├── memory.py
    ├── models.py
    └── store.py

apps/backend/tests/
├── api/test_sessions_api.py
├── api/test_memory_api.py
├── fixtures/conversation_memory_eval_v1.json
├── integration/
│   ├── test_memory_context.py
│   └── test_session_followups.py
└── unit/
    ├── test_conversation_memory.py
    ├── test_conversation_models.py
    └── test_conversation_store.py

scripts/
└── evaluate_conversation_memory.py

apps/frontend/src/
├── api/client.ts
├── pages/ResearchPage.tsx
└── App.css

apps/frontend/tests/
├── api/client.test.ts
├── research-consent.test.tsx
├── research-memory.test.tsx
├── research.test.tsx
└── e2e/research.spec.ts
```

**Structure Decision**: Extend the existing Python API and React workbench. Keep session persistence and vector-memory behavior in a small backend conversations package; expose typed session routes and augment the existing agent route. Reuse existing backend/frontend test suites and current Chroma/embedding configuration.

## Complexity Tracking

No constitution violations. No extra service, framework, or dependency is proposed.
