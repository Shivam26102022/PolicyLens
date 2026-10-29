# Feature Specification: Bounded Agent Runtime

**Feature Branch**: `004-agent-runtime`  
**Created**: 2026-10-24  
**Status**: Draft  
**Input**: `POLICYLENS_MASTER_SPEC.md`, Section 8 and Section 20 Feature 004

## Product Outcome

An analyst can ask a supported policy question and receive a structured, evidence-grounded answer or an explicit clarification, abstention, conflict, blocked, or safe-failure outcome. The runtime uses one bounded agent only where choosing among evidence search and deterministic tools adds value.

## Scope and Dependencies

Depends on the typed answer/citation contracts from Feature 003 and the MCP tool/resource contract defined by Feature 005. Feature 004 owns a typed, mockable agent-facing adapter and its integration tests; the production MCP server and tools remain in Feature 005. Feature 004 also owns the OpenAI Agents SDK runtime, state machine, budgets, safe errors, schema validation, citation validation, and comparison with a non-agent baseline.

## Clarifications

### Session 2026-10-26

- Q: Should Feature 004 use a typed, mockable adapter for Feature 005's draft MCP contract and leave the production MCP server/tools to Feature 005? → A: Use the adapter and mocks; do not expand Feature 004 into Feature 005.
- Q: Which endpoint configuration should Feature 004 use with `OPENAI_DEPLOYMENT_MODEL=gpt-6-luna`? → A: Use `OPENAI_BASE_URL` for the OpenAI-compatible Foundry host and `OPENAI_DEPLOYMENT_MODEL` as the deployment ID; retain `OPENAI_MODEL` for the standard OpenAI route.

## User Scenarios & Testing

### User Story 1 - Answer from Evidence (Priority: P1)

As an analyst, I can get claims linked to evidence or a safe non-answer when evidence is inadequate.

**Independent Test**: Replay factual, ambiguous, unanswerable, conflicting, and out-of-scope cases through deterministic fixtures.

**Acceptance Scenarios**:

1. **AC-004-01** Given sufficient retrieved evidence, When the bounded run completes, Then each corpus-derived claim is a concise factual summary linked to one or more exact excerpts validated against current-run evidence; calculation-only claims are rendered deterministically from validated tool records.
2. **AC-004-02** Given ambiguity, insufficient evidence, or conflict, When evidence assessment completes, Then the run asks one focused question, abstains with a reason, or reports both sides respectively.
3. **AC-004-03** Given malformed structured output or an invented citation, When validation runs, Then the result becomes a safe failure and is not returned as answered.

### User Story 2 - Use Deterministic Tools Within Budgets (Priority: P1)

As a reviewer, I can inspect which approved tools ran and confirm finite stopping behavior without seeing hidden reasoning.

**Independent Test**: Exercise turn/tool/time/token budgets, invalid arguments, transient errors, timeout, and cancellation with fake tools.

**Acceptance Scenarios**:

1. **AC-004-04** Given a tool-required case, When a tool is selected, Then the typed allow-list and argument schema are enforced before execution.
2. **AC-004-05** Given invalid arguments or malformed tool output, When a tool call fails, Then it is not blindly retried and the run stops safely with a stable error code.
3. **AC-004-06** Given a transient failure, When bounded retry budget permits, Then only that failure is retried and the count is recorded.

### User Story 3 - Inspect a Run (Priority: P2)

As a governance reviewer, I can inspect the run ID, provider, state transitions, safe tool events, citations, and terminal reason.

**Independent Test**: Assert event schema and verify logs/traces contain no prompts, credentials, evidence bodies, or private reasoning.

**Acceptance Scenarios**:

1. **AC-004-07** Given a completed or safely terminated run, When the response is returned, Then it includes a stable trace ID, provider/model/prompt identity, ordered safe state/tool events, and terminal reason, while excluding hidden reasoning, prompts, credentials, raw queries, and evidence/tool bodies.

## Functional Requirements

- **AGENT-004-01**: Implement the finite state sequence from validated request through evidence search/assessment, optional bounded tool execution, output validation, citation validation, and a terminal state.
- **AGENT-004-02**: Enforce max turns, total/per-tool calls, retries, model/MCP/total timeouts, tokens/context, and response size.
- **AGENT-004-03**: Validate Pydantic answer output and status-specific invariants before returning it; every corpus-derived claim MUST link to at least one exact current-run citation excerpt, and calculation-derived claim text MUST be host-rendered from the validated deterministic calculation record.
- **AGENT-004-04**: Use deterministic code for calculations, filtering, policy checks, state transitions, and citation construction.
- **OBS-004-01**: Emit redacted trace events and concise safe tool summaries; never capture/display hidden chain-of-thought.
- **EVAL-004-01**: Compare bounded-agent behavior to non-agent RAG on tool-requiring cases using the same frozen cases.
- **SEC-004-01**: Treat user, retrieved, model, and tool content as untrusted data.
- **DOC-004-01**: Document agent setup, OpenAI/Foundry configuration, the Feature 005 adapter boundary, reproducible tests, and any unrun live comparison or evaluation limitation.

## Success Criteria

- **SC-004-01**: Every run terminates within configured budgets and returns a stable outcome/trace ID.
- **SC-004-02**: Invalid schemas/citations, unsafe tool choices, and injected instructions are rejected in deterministic tests.
- **SC-004-03**: The agent is retained only if a controlled comparison shows value over the non-agent baseline.

## Assumptions and Open Questions

- The first configured generation route is OpenAI; model IDs are pinned during planning. MLX routing belongs to Feature 006.
- The agent uses `OPENAI_DEPLOYMENT_MODEL` when configured and sends requests to `OPENAI_BASE_URL` when that endpoint is configured; otherwise it uses `OPENAI_MODEL` with the standard OpenAI endpoint. Missing or incompatible configuration fails safely; there is no provider fallback.
- Consequential write actions remain out of scope; approval controls are added only if an approved later feature introduces such an action.
- No hidden reasoning is persisted or exposed.

## Out of Scope

Retrieval/index implementation (003), production MCP tools/resources (005), provider parity (006), full evaluation set (007), and UI workflows (009).