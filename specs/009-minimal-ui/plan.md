# Implementation Plan: PolicyLens Research Workbench

**Branch**: `009-minimal-ui` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Enhanced Feature 009 research workbench specification.

## Summary

Replace the status-only frontend with navigable Research, Evaluations, Architecture, and Settings/Status views. Keep answer/evidence rendering and model selection inside the existing backend contract: add safe configured model options, fixed Standard effort in the Research UI with backend capability validation, explicit per-run OpenAI consent, bounded follow-ups, typed SSE progress, provider-reported usage and optional Responses API summaries, and a read-only aggregate evaluation summary. Use a data-driven architecture guide that describes current implementation and state boundaries accurately.

## Technical Context

**Language/Version**: Python 3.12; TypeScript 5.9; React 18; Vite 8.

**Primary Dependencies**: Existing FastAPI, Pydantic, React, Vitest, React Testing Library; add React Router for the four views, Lucide React for interface icons, and Playwright for browser-level tests.

**Storage**: Existing versioned JSON manifests read by the backend only; ephemeral browser run and bounded conversation state plus non-sensitive provider preference. No server-side conversation history or provider-managed response IDs are required.

**Testing**: pytest, JSON Schema validation, Vitest/React Testing Library, Playwright with mocked API responses, Ruff, mypy, ESLint, TypeScript, and repository traceability.

**Target Platform**: Existing local assessment services on Linux/macOS and modern desktop/mobile browsers, down to 320 CSS pixels.

**Project Type**: Existing three-service web application; no new deployable service.

**Performance Goals**: Navigation among static views is immediate; answer requests stream typed operational progress; no UI action launches an evaluation or provider call except explicit answer submission.

**Constraints**: All provider options, reasoning capabilities, progress events, usage, and evaluation summaries come through typed backend APIs. OpenAI requires fresh consent for every turn. Model IDs are server-configured only. Effort values unsupported by a selected route are rejected. Standard OpenAI uses Responses API; custom endpoints default to Chat Completions and require `OPENAI_USE_RESPONSES_API=true` only when compatibility is confirmed. MLX remains loopback-only. Evaluation data is aggregate/read-only. Private reasoning, arbitrary HTML, silent provider fallback, and unbounded caller-supplied context are prohibited. The UI may show Responses API summary text, never private reasoning content. Feature 011 owns persisted session context; the Feature 009 request contract remains bounded to 8 prior messages, 4,000 characters per message, and 12,000 characters total.

**Scale/Scope**: Four primary views, one shared research workflow, configured provider options, aggregate Feature 007/008 results, nine architecture layers, and accessible responsive behavior.

## Constitution Check

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Corpus claims display claim-linked evidence; abstention/conflict states remain explicit. | PASS |
| II. Scientific Evaluation Before Complexity | Dashboard shows only measured aggregates and preserves null/blocked/limitation states. | PASS |
| III. Bounded Agency and Deterministic Computation | UI exposes safe tool summaries; backend retains budgets and deterministic tool validation. | PASS |
| IV. Secure MCP Trust Boundaries | MCP remains backend-only; tool/resource text is untrusted and never rendered as HTML. | PASS |
| V. Provider Portability With Measured Parity | Configured per-run selection is explicit; OpenAI consent required; no parity claims or fallback. | PASS |
| VI. Reproducibility Is a Product Feature | API models/options and evaluation summaries are versioned and contract-tested. | PASS |
| VII. Privacy, Responsible AI, and Human Oversight | No credentials in browser; no consequential decision feature; aggregate evaluation only. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | Extend existing API/web packages; add no service or state framework. | PASS |
| IX. Testable Specifications and Traceability | Each acceptance scenario maps to API, component, browser, or inspection evidence. | PASS |
| X. Honest Reporting | Implemented/configured/planned/unavailable labels; no fabricated metrics or memory claims. | PASS |

## Architecture

### Frontend

- Shared shell with route-level Research, Evaluations, Architecture, and Settings/Status views.
- Typed API client for model options, answer requests, health, and evaluation summaries.
- `POST /agent/answer/stream` emits typed `progress`, `result`, and `error` SSE events. The UI maps allow-listed operational states to safe summaries and never displays hidden reasoning or raw event details. AbortController stops the browser wait; backend work may continue to its bounded timeout.
- The research composer always sends Hybrid retrieval and Standard reasoning (`none`) and exposes no search/filter/depth controls. PDF examples may apply their reviewed source ID; editing the question clears that source scope. Backend route-specific effort validation remains in place for typed API clients.
- Follow-up turns send the browser's bounded prior user/assistant messages explicitly in the answer request. Prior assistant text is untrusted context, not evidence; every turn performs fresh retrieval/evidence validation and every OpenAI turn requires fresh consent.
- Explicit response components for claims, evidence drawer, calculations, uncertainty, conflict, limitations, and safe events.
- Per-answer safe activity trails show the selected API route, reasoning effort, provider-reported usage, and a Responses API SDK summary when returned. The backend extracts only summary-text items, never private reasoning content.
- Architecture-layer content stored as reviewed static data and cross-linked to repository docs.
- UI state stores recent runs in memory. Only selected provider preference may be stored locally; consent is never stored.

### Backend

- `GET /model/options` reports configured model IDs and safe local/external/consent metadata, never credentials or endpoint URLs.
- `POST /agent/answer` accepts a provider choice and consent flag; the API resolves the choice against server configuration, validates consent, and caches runtimes by validated provider/model. The retrieval service remains provider-independent.
- `POST /agent/answer/stream` accepts the same typed answer request, including advertised `reasoning_effort` and bounded `conversation`, and emits typed operational progress followed by a result or safe error. Effort is passed only where supported; unsupported values are rejected before runtime execution.
- Conversation context is capped at 8 prior messages, 4,000 characters per message, and 12,000 characters total. It is not stored by the backend or delegated to provider-managed conversation state; OpenAI consent is checked independently on every streamed turn.
- `GET /evaluation/summary` validates existing manifests and returns an allow-listed aggregate model. It never returns prompts, raw case results, artifact paths, or mutates manifests.
- Existing `/health/ready` and `/model/capabilities` contracts remain the sources for component health and selected model capabilities.

## Project Structure

### Documentation

```text
specs/009-minimal-ui/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── agent-provider-selection.schema.json
│   ├── evaluation-summary.schema.json
│   └── model-options.schema.json
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
apps/backend/src/policylens/api/
├── agent.py                    # Per-request provider selection and runtime cache
├── model_capabilities.py       # Safe configured model options
└── evaluation_summary.py       # Read-only manifest aggregation
apps/backend/tests/api/
├── test_agent_api.py
├── test_model_capabilities.py
└── test_evaluation_summary.py
apps/frontend/src/
├── App.tsx / App.css           # Workbench shell and responsive visual system
├── api/                        # Typed backend client and contracts
├── components/                 # Composer, answer, evidence, status, navigation
├── data/architecture.ts        # Reviewed layer descriptions and references
└── pages/                      # Research, Evaluations, Architecture, Settings
apps/frontend/tests/
├── *.test.tsx                  # View/component and privacy tests
└── e2e/                        # Playwright browser workflows
docs/architecture/architecture.md           # Current implementation status and layer glossary
```

**Structure Decision**: Keep all changes within the existing frontend and backend services. Reuse current API response models, manifests, testing frameworks, and frontend package. React Router is justified by four distinct views; no global server-state library or new service is needed.

## Implementation Sequence

1. Freeze model-options/capabilities, per-run provider-selection and conversation bounds, progress events, and evaluation-summary contracts with backend tests.
2. Implement API options, consent validation, provider-specific runtime selection, and safe evaluation aggregation.
3. Build the shared shell, streamed research and bounded follow-up workflow, fixed Standard/Hybrid research defaults, settings, answer/evidence views, and responsive states.
4. Add read-only evaluation and architecture views; update architecture documentation to separate real and planned capabilities.
5. Add browser workflows, offline privacy checks, and run full repository validation.

## Complexity Tracking

No constitution exception. React Router is limited to navigation among the explicitly required views; the existing three-service architecture is unchanged.
