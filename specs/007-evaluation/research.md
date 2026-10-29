# Feature 007 Research

## Decisions

### Reuse current evaluation entry points

**Decision**: Keep retrieval metric computation in `apps/backend/src/policylens/retrieval/evaluation.py` and reuse the current provider comparison builder in `scripts/evaluate_providers.py`. Add a suite orchestrator rather than copying those implementations.

**Rationale**: Retrieval already reports Recall@k, MRR, empty-result rate, citation completeness, and latency; provider reports already retain model/runtime identity, prompt version, retrieval index version, skipped/failed rows, and unmeasured metrics. The gap is a reviewed cross-feature case set, consistent run registry, generation execution, and error analysis.

**Alternatives considered**: Replacing both existing evaluators with one new framework was rejected because it would duplicate stable metric logic and increase review scope.

### Keep evaluation labels outside runtime input

**Decision**: Store expected behavior, reference claims, required/forbidden tools, split, and review metadata in the evaluation case record. Build runtime requests only from the case question and ordinary retrieval filters.

**Rationale**: The current `AgentEvaluationCase.to_request()` already excludes labels. Feature 007 makes this a contract and test invariant.

### Candidate versus approved case state

**Decision**: Case schemas permit `candidate`, `in_review`, and `approved`; the release gate counts only approved cases. Do not synthesize human-review status or infer approval from a valid schema.

**Rationale**: The repository has seven author-curated retrieval anchors and six Feature 004 engineering cases, but they explicitly state that they are not independently human-reviewed. They are useful seed material, not a 30-case approved benchmark.

### Deterministic metrics with bounded AI quality judging

**Decision**: Compute provenance, retrieval, numeric, schema, tool, abstention, and injection metrics deterministically. An explicit AI-judge option scores groundedness and answer relevance for generated agent answers using a pinned rubric and structured output. The judge receives only the bounded question, answer, and cited excerpts; it does not receive expected behavior, reference claims, or configuration labels. Record model/rubric/counts and do not persist answer text or free-form rationales.

**Rationale**: The user requested AI-scored answer quality rather than manual output scoring. Deterministic oracle, citation, and retrieval metrics remain separate; AI scores are clearly marked as uncalibrated and not release approval. A same-deployment judge is not independent validation, so reports disclose its model identity and limitations. Case-definition approval remains human-owned and is not inferred from AI output.

### Append-only run registry and honest artifacts

**Decision**: Append run records atomically to a versioned manifest. Hash case data, corpus inputs, index, configuration, and dependency lock; include code revision when available, otherwise fingerprint the relevant source tree and record the missing Git revision.

**Rationale**: This reuses `scripts/evaluate_retrieval.py` manifest practices and preserves negative results without overwriting prior experiments.

## Local Evidence

- `apps/backend/src/policylens/retrieval/evaluation.py` provides deterministic anchor mapping and retrieval metrics.
- `scripts/evaluate_retrieval.py` fingerprints case set, source inputs, configuration, and ephemeral index versions.
- `scripts/evaluate_providers.py` records provider/model/route/runtime, prompt version, case-set hash, per-case index version, and explicit no-live defaults.
- `scripts/evaluate_agent.py` currently records readiness only; it does not execute a real reviewed agent-versus-baseline run.
- `data/evaluation/retrieval-cases.json` contains seven author-curated cases; `data/evaluation/agent-tool-cases.json` contains six author-curated engineering cases. Neither meets Feature 007's 30 approved case gate.

## Open Implementation Questions

- Human reviewers and review dates must be assigned before cases are marked approved; the initial tooling will support pseudonymous reviewer IDs and will not invent them.
- Apple-silicon MLX metrics remain unavailable on Linux; such provider rows remain skipped or not measured until run on supported hardware.