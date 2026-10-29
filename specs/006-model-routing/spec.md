# Feature Specification: OpenAI and Local MLX Model Routing

**Feature Branch**: `006-model-routing`  
**Created**: 2026-10-24  
**Status**: Draft; MLX runtime needs Apple silicon  
**Input**: User provider clarification and `POLICYLENS_MASTER_SPEC.md`, Sections 5 and 20 Feature 006

## Product Outcome

Contributors can select a generation provider through configuration, use OpenAI for the initial API-based path, and later opt into a local Apple-silicon MLX adapter without replacing the OpenAI route or silently sending local data externally.

## Scope and Dependencies

Depends on typed configuration and the bounded runtime contracts. Owns the provider-neutral `ModelGateway`, OpenAI generation adapter, MLX/MLX-LM local adapter, structured output/capability reporting, explicit provider routing/failure policy, and provider comparison on a frozen subset. `MODEL_PROVIDER` applies to both the bounded agent and the non-agent retrieval answer baseline; retrieval/citation ownership remains with Feature 003 and agent state/tool budgets remain with Feature 004. Embedding-provider choice remains independently controlled by `EMBEDDING_PROVIDER` and is implemented with Feature 003.

## Clarifications

### Session 2026-10-26

- Q: Which Apple-silicon hardware should guide the initial MLX model and quantization choice? → A: Target a system reported as having a 16-core GPU and 24 GB unified memory; prioritize the backend API first, keep `MLX_MODEL` configurable, and defer exact model/quantization pinning and on-device benchmarking until the exact Mac/model can be verified.

## User Scenarios & Testing

### User Story 1 - Use OpenAI Generation (Priority: P1)

As a contributor, I can configure an OpenAI model and receive typed usage/health information without putting credentials in the browser.

**Independent Test**: Use mocks for CI to validate missing keys/models, generation adapter errors, schema output, and redacted usage. Live calls are explicit opt-in only.

**Acceptance Scenarios**:

1. **AC-006-01** Given `MODEL_PROVIDER=openai` and valid backend-only credentials/model ID, When the gateway is invoked, Then the OpenAI adapter is selected and provider/model/usage/latency are recorded without logging credentials or full prompts.
2. **AC-006-02** Given missing OpenAI key/model settings, When startup validates settings, Then it fails safely with a stable redacted configuration error before an outbound call.

### User Story 2 - Select Local MLX Additively (Priority: P1)

As a MacBook user with Apple silicon, I can opt into local MLX generation while retaining OpenAI as a separate option.

**Independent Test**: On Apple silicon, validate configured model metadata, loopback endpoint, context/output limits, health/capabilities, and unsupported tool/structured-output behavior.

**Acceptance Scenarios**:

1. **AC-006-03** Given `MODEL_PROVIDER=mlx`, When the local adapter is selected, Then the adapter reports its exact model/capabilities and never makes an external request.
2. **AC-006-04** Given the MLX endpoint is unavailable or lacks a required capability, When a request is made, Then the run fails safely unless the user explicitly changes provider.
3. **AC-006-05** Given both generation providers are configured, When environment selection changes, Then the other adapter remains installed and selectable; no silent replacement occurs.

### User Story 3 - Compare Providers Honestly (Priority: P2)

As an evaluator, I can compare the same frozen cases across OpenAI and MLX and inspect capability and latency tradeoffs.

**Independent Test**: Run a pinned same-subset benchmark with identical prompts, evidence, schema, and tool cases; report platform limits.

## Functional Requirements

- **MODEL-006-01**: Define a provider-neutral typed interface for generation, structured generation, capability/health discovery, and usage reporting.
- **MODEL-006-02**: OpenAI is the initial generation route; pin the model ID in configuration/metadata after implementation-time selection.
- **MODEL-006-03**: MLX/MLX-LM is an additive local provider, loopback by default, with bounded context/output and explicit unsupported capabilities.
- **MODEL-006-04**: No automatic fallback may send local/private requests externally. Provider changes that alter data handling require explicit user choice.
- **MODEL-006-05**: `MODEL_PROVIDER` selects generation independently from `EMBEDDING_PROVIDER`; neither selector silently replaces the other.
- **EVAL-006-01**: Compare tool selection, structured validity, groundedness, answer quality, latency, memory, and cost where measurable; do not claim parity without results.
- **SEC-006-01**: Redact secrets and sensitive inputs from logs/traces and keep all credentials backend-side.

## Success Criteria

- **SC-006-01**: Both configured providers are independently selectable and unsupported/unavailable routes fail with a stable safe outcome.
- **SC-006-02**: No external request occurs on the MLX path or as implicit fallback.
- **SC-006-03**: Comparison report identifies exact models, configurations, platform, metrics, failures, and limitations.

## Assumptions and Open Questions

- Q-MLX-01: The current Linux x86_64 host cannot verify Apple-silicon MLX execution. The user reports 16 GPU cores and 24 GB unified memory, but the exact chip/model remains unconfirmed; record it before pinning model/quantization or claiming parity.
- OpenAI model IDs and revisions are chosen at implementation time from verified primary documentation and pinned configuration.
- Local embedding default remains unchanged; API embeddings require `EMBEDDING_PROVIDER=openai` independently.

## Out of Scope

Corpus ingestion, embedding implementation, retrieval, agent state machine, and UI provider controls.