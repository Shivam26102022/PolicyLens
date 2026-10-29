# PolicyLens Constitution

## Core Principles

### I. Evidence Before Fluency
Every factual answer MUST be supported by source passages or deterministic tool output available to the current run. Claims MUST link to their supporting evidence. When evidence is insufficient, ambiguous, conflicting, unavailable, or out of scope, the system MUST clarify, abstain, or present the conflict. User text, retrieved content, model output, MCP resources, and tool output are untrusted data; embedded instructions MUST NOT override application policy.

### II. Scientific Evaluation Before Complexity
Every material retrieval, chunking, prompting, model, or orchestration choice MUST be compared with a simple baseline. Evaluation data MUST be leakage-resistant, versioned, and separated from runtime prompts. Configurations, seeds where applicable, stratified metrics, latency, cost estimates, qualitative errors, and negative results MUST be retained. Small samples and judge limitations MUST be disclosed.

### III. Bounded Agency and Deterministic Computation
The default is one bounded agent with typed, allow-listed tools and explicit finite state transitions. Arithmetic, aggregation, filtering, transformations, validation, policy checks, citation assembly, and state changes MUST be deterministic. Runs MUST enforce turn, tool, retry, time, token, context, and output limits with safe stopping behavior.

### IV. Secure MCP Trust Boundaries
The MCP server is an independent trust boundary. The host MUST allow-list server identity, discover and validate capabilities, validate tool arguments and results, enforce timeouts and cancellation, redact logs, and use least privilege. MCP is read-only by default. Tool and resource content is untrusted and MUST NOT select tools or alter instructions. Arbitrary shell, generic SQL, filesystem, URL-fetch, and code-execution tools are prohibited.

### V. Provider Portability With Measured Parity
OpenAI API and local Apple-silicon MLX/MLX-LM routes MUST sit behind provider-neutral model interfaces. Provider choice and fallback MUST be explicit, observable, and privacy-aware; private/local requests MUST NOT be sent externally without user approval. Behavioral parity MUST NOT be claimed without comparable measurements of tool reliability, output validity, groundedness, answer quality, latency, memory, and cost.

### VI. Reproducibility Is a Product Feature
Dependencies, runtime versions, model identifiers, prompt versions, corpus and index versions, data manifests, experiment settings, and relevant seeds MUST be recorded. Derived indexes and evaluation results MUST be rebuildable from versioned inputs and configuration. Setup and verification instructions MUST work from a clean checkout or state their blockers.

### VII. Privacy, Responsible AI, and Human Oversight
Only public, synthetic, or appropriately anonymized data may be used. Data minimization, permissions, secret handling, redaction, retention, and human review MUST be explicit. Secrets MUST NOT enter browser bundles, source control, or unredacted traces. PolicyLens MUST NOT be presented as the final authority for consequential legal, regulatory, safety, eligibility, enforcement, benefits, or funding decisions.

### VIII. Minimal Service Complexity and Strong Contracts
The deployable architecture MUST remain three separately runnable services: `policylens-web`, `policylens-api`, and `policylens-mcp`. Interfaces MUST be typed, versioned, tested, observable, and failure-aware. Additional services or frameworks require an approved ADR demonstrating measurable value.

### IX. Testable Specifications and Traceability
Requirements MUST have stable identifiers. Every acceptance criterion MUST map to a test, evaluation case, inspection, or reproducible command, and every test MUST identify the requirements it verifies. Traceability MUST expose unmapped requirements and tasks before implementation is approved.

### X. Honest Reporting
No data, API, dependency behavior, citation, benchmark, test result, or implementation status may be invented. Unrun checks MUST be labeled unrun; mocks MUST be identified as mocks; known failure modes, unsupported capabilities, evaluation limits, and residual risks MUST remain visible. Documentation MUST reflect observable behavior.

## Additional Constraints

- Canonical identity: PolicyLens; tagline: "Evidence-grounded policy research with verifiable sources"; Python package: `policylens`; frontend package and service: `policylens-web`; backend service: `policylens-api`; MCP service: `policylens-mcp`; Chroma collection prefix: `policylens`; OpenAPI title: `PolicyLens API`; MCP server name: `PolicyLens Policy Data Server`.
- The frontend MUST use React 18+, TypeScript, and Vite. It MUST communicate only with the backend and MUST contain no provider credentials or direct model, Chroma, corpus, or MCP access.
- The backend MUST use Python 3.12+, FastAPI, Pydantic, and the OpenAI Agents SDK. The standalone MCP server MUST be a separate Python package and process.
- Local Chroma persistence, BM25, deterministic hybrid rank fusion, passage provenance, and provider-neutral model and embedding interfaces are architectural requirements, but MUST be implemented only by their approved feature specifications.
- Model, MCP, and external SDK behavior MUST be verified against the selected pinned versions and covered by compatibility tests; this constitution does not assert unverified SDK capabilities.
- Raw restricted data, credentials, model weights, generated indexes unsuitable for source control, and secret-bearing traces MUST NOT be committed.
- Feature 001 is limited to repository foundations, service skeletons, typed configuration, health, logging, tests, CI, documentation structure, and traceability. It MUST NOT implement the complete RAG pipeline, production MCP tools, complete agent logic, or final frontend experience.

## Development Workflow

1. Follow the Spec Kit SDD gates: Constitution -> Specify -> Clarify -> Plan -> Tasks -> Analyze -> Implement -> Converge. Use the installed Copilot skill names and generated project files as authoritative; Clarify and Analyze are required project gates even though Spec Kit labels them optional workflow commands.
2. Do not begin implementation until the feature specification, clarification record, plan, tasks, and cross-artifact analysis are mutually consistent and approved.
3. Work in small, reviewable vertical slices. Add focused tests with changes, run the narrowest meaningful check first, then the required broader gates.
4. Do not mark a task complete without recorded verification evidence. Update requirements traceability and documentation with the same change.
5. Record justified deviations and architecture choices in reviewed ADRs. Keep generated experiment outputs and negative results; do not tune on the frozen test set.

## Governance

This constitution governs all features and supersedes conflicting lower-level plans unless an approved amendment changes it. Feature specifications, plans, tasks, tests, and implementation must demonstrate compliance. A constitution amendment requires explicit review, a version update, and an explanation of affected artifacts. Complexity exceptions require an ADR; unresolved safety, data-rights, privacy, or evaluation blockers must be recorded rather than assumed away.

**Version**: 1.0.0 | **Ratified**: 2026-10-24 | **Last Amended**: 2026-10-24
