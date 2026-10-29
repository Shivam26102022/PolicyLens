# Feature 007 Data Model

## EvaluationCaseSet

Versioned, immutable set with `set_id`, schema version, lineage, and unique cases. A release set must contain at least 30 cases with `review_status=approved`; 40-60 is the preferred range. The seven retrieval and six agent cases currently in the repository are engineering fixtures, not approved Feature 007 cases.

## EvaluationCase

Each case records:

- stable `case_id`, category, question, and expected behavior (`answer`, `clarify`, `abstain`, `conflict`, or `block`);
- retrieval mode, top-k, filters, strategy-independent page/marker or row anchors, optional relevance grades (integer 0-3) attached to anchors, and reference claims where applicable;
- relevant passage IDs when available for the recorded index version; source anchors remain authoritative across chunking changes;
- required tools, forbidden behaviors, and difficulty;
- optional controlled `adversarial_fixture` text for synthetic user/retrieved/MCP injection tests; it is harness metadata and is never part of the ordinary runtime request;
- split (`dev` or `test`), case lineage, review status, reviewer references, and review time.

The case-to-runtime adapter exposes only the ordinary question and retrieval filters. It never includes expected behavior, reference claims, split, review status, or labels in model, retrieval, tool, or prompt input. Duplicate case IDs are rejected; exact and semantic duplicate checks are recorded before approval.

## ExperimentRegistration

Captures a named hypothesis, principal variable, baseline, split, filters, chunking/retrieval/provider configuration, random seed where applicable, and approved case-set hash. Change one principal variable at a time where feasible.

## EvaluationRun

An append-only run record with `run_id`, status (`completed`, `partial`, `blocked`, `failed`), timestamps, case-set and corpus hashes, index versions, prompt/model/provider versions, code revision when available or `source_tree_sha256` otherwise, `uv.lock` hash, configuration and fingerprint, seed, tool versions, per-case results, metrics, artifact paths, and notes. Live OpenAI and MLX requests are false by default and explicit when enabled.

## CaseResult and Metrics

Per-case output preserves expected and observed behavior, retrieval anchors, trace ID, provider/model, index/prompt versions, latency, tokens, cost/resource measures where available, schema/tool/citation outcomes, and failure status. Retrieval recall groups passage variants belonging to the same expected evidence anchor; each anchor contributes at most one hit and one denominator unit. Per-case results record retrieval anchor hits/count, citation anchor matches/count, and validated deterministic tool-result count when available.

Optional AI-judge fields store only groundedness/relevance scores, judge status/model/rubric, judge latency, and token counts; raw answer text and judge rationale are not retained. The judge may receive validated deterministic calculation results as a separate bounded evidence input from cited corpus excerpts; it does not receive expected labels, reference claims, or raw tool arguments. Aggregates are reported overall and by category, split, difficulty, and provider where sample size supports the breakdown. Every metric reports its own scored sample count. Report confidence intervals only with method and sample count; do not claim statistical significance from small samples.

Retrieval metrics include Recall@k, MRR, nDCG@k when graded passage labels exist, empty-result rate, and latency distribution. Cases without grades leave nDCG unmeasured. Generation/system metrics include groundedness, relevance, citation correctness/completeness, factual/numeric accuracy, abstention/conflict behavior, structured/tool validity, injection success, token use, cost, and local throughput/memory when measurable.

## HumanReview

Human review records use pseudonymous reviewer IDs and rubric version and remain separate from automated run scores. AI-judge groundedness and answer relevance use the anchored 1-5 scale and are not human validation; deterministic retrieval, expected-behavior, and citation checks remain separate. Human review can be used for calibration or error investigation, but an AI score never approves cases or substitutes for case-definition review.

## ErrorRecord

Each failure stores case/run IDs, redacted observed outcome, expected behavior, failure layer (`data`, `parsing`, `retrieval`, `context`, `generation`, `tool_selection`, `tool_execution`, `mcp`, `validation`, `policy`, or `ui`), trace evidence, severity/frequency, root-cause hypothesis, intervention, predicted metric impact, and regression-test reference. Do not persist secrets or restricted raw content.