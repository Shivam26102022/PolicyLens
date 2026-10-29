# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
# Implementation Plan: Bounded Agent Runtime

**Branch**: `004-agent-runtime` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-agent-runtime/spec.md`

## Summary

Add one bounded OpenAI Agents SDK runtime to the existing FastAPI backend. It retrieves current-run evidence through Feature 003, exposes at most the typed deterministic `query_statistics` adapter defined for Feature 005, validates structured outcomes and citations server-side, and returns redacted trace events. The Foundry path uses `OPENAI_DEPLOYMENT_MODEL` with an explicit `OPENAI_BASE_URL`; standard OpenAI uses `OPENAI_MODEL`. No provider fallback, production MCP server, new service, or UI is included.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Existing FastAPI/Pydantic stack, `openai==3.37.0`, and `openai-agents==0.24.0`; no new package is required.

**Storage**: No persistent session store. Run state and redacted events are request-scoped and returned with the response; no prompts, raw evidence, credentials, or private reasoning are persisted.

**Testing**: pytest with injected fake model/runner and typed MCP adapters; SDK compatibility tests construct the pinned Agents SDK objects offline. No default test makes a live OpenAI/Foundry request.

**Target Platform**: Python 3.12 on Linux and macOS. OpenAI-compatible Foundry endpoints are configurable; MLX remains owned by Feature 006.

**Project Type**: Backend-owned async FastAPI route and agent runtime in the existing API service.

**Performance Goals**: No unmeasured latency SLO. Bound every run by `REQUEST_TIMEOUT_SECONDS`, `MAX_AGENT_TURNS`, `MAX_TOOL_CALLS`, per-tool call/retry limits, context limits, output tokens, and tool timeouts.

**Constraints**: One agent, no handoffs, no tool parallelism, one allow-listed deterministic statistics tool, strict structured output, concise corpus claims linked to exact current-run citation excerpts, host-rendered calculation claims, SDK retries disabled, SDK tracing disabled, and only sanitized application events. Citation checks verify exact quote and provenance but do not independently establish semantic entailment; the UI exposes the linked evidence for review. `OPENAI_DEPLOYMENT_MODEL` requires `OPENAI_BASE_URL`; it takes precedence over `OPENAI_MODEL`. `MODEL_PROVIDER` must explicitly select `openai`; no fallback is allowed.

**Scale/Scope**: One request-scoped run over the six approved Feature 002 sources and Feature 003 index. Feature 005's MCP process is not implemented here; tests use the typed adapter boundary until that feature supplies its server.

## Constitution Check

| Principle | Gate | Status |
|---|---|---|
| I. Evidence Before Fluency | Corpus claims require current-run citations; calculation claims require deterministic tool provenance; otherwise abstain/clarify/conflict. | PASS |
| II. Scientific Evaluation Before Complexity | Compare tool-requiring cases to Feature 003's non-agent baseline; do not claim agent value without measured output. | PASS, live comparison is an explicit gate |
| III. Bounded Agency and Deterministic Computation | One agent, finite state transitions, bounded calls/retries/time/tokens/output; host owns calculations and validation. | PASS |
| IV. Secure MCP Trust Boundaries | Adapter only invokes the allow-listed Feature 005 contract; production identity/capability lifecycle remains Feature 005. | PASS |
| V. Provider Portability With Measured Parity | Explicit OpenAI/Foundry configuration, model metadata, no fallback; MLX remains out of scope. | PASS |
| VI. Reproducibility Is a Product Feature | Record model, provider, prompt, index, run, budget, and tool metadata. | PASS |
| VII. Privacy and Responsible AI | Public corpus only; SDK tracing disabled; raw content and secrets omitted from events. | PASS |
| VIII. Minimal Service Complexity and Strong Contracts | Add routes/modules only to the existing backend; no fourth service or framework. | PASS |
| IX. Testable Specifications and Traceability | Every acceptance criterion maps to typed contracts, focused tests, or a reproducible gate. | PASS |
| X. Honest Reporting | Mocks and any unrun live Foundry comparison are explicitly identified. | PASS |

## Project Structure

### Documentation

```text
specs/004-agent-runtime/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source and Tests

```text
apps/backend/src/policylens/
├── api/agent.py
└── agent_runtime/
    ├── models.py
    ├── state.py
    ├── tools.py
    ├── runtime.py
    └── traces.py
apps/backend/tests/
├── api/test_agent_api.py
├── unit/test_agent_models.py
├── unit/test_agent_runtime.py
├── unit/test_agent_tools.py
├── unit/test_agent_provider.py
├── unit/test_agent_state.py
└── unit/test_settings.py
prompts/agent/system-v1.md             # historical extractive prompt
prompts/agent/system-v2.md             # concise claims with exact quote citations
scripts/evaluate_agent.py
scripts/tests/test_agent_contracts.py
scripts/tests/test_agent_evaluation.py
data/evaluation/agent-tool-cases.json
docs/evaluation/agent-evaluation.md
```

**Structure Decision**: Keep the runtime, API, and adapter in the existing backend package. Reuse Feature 003 retrieval and citation validation. Wrap one typed Feature 005 statistics operation as an Agents SDK function tool; the adapter is injectable and mockable. Return safe trace summaries inline rather than adding a run database or service.

## Implementation Boundary

Feature 004 owns the agent state machine, request/response contracts, OpenAI/Foundry client setup, budget enforcement, typed tool adapter protocol, output/citation validation, and redacted event summaries. Feature 003 continues to own retrieval/indexing/citations and the non-agent baseline; its baseline client will consume the same effective OpenAI deployment/base-URL settings so comparisons are comparable, without changing retrieval behavior. Feature 005 owns the production MCP server/tool/resource and server trust lifecycle. Feature 006 owns broader model gateway/MLX routing. Feature 007 owns the reviewed evaluation set and broader answer-quality comparison. Feature 009 owns UI workflows.

## Complexity Tracking

No additional service or framework is required.
