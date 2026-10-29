# Feature 007 Quickstart

Feature 007 adds a reviewed evaluation set and reproducible suite runner. The current Feature 003/004 sets are small engineering fixtures and do not pass the 30-approved-case release gate.

The initial set at `data/evaluation/feature007-cases.json` contains 36 AI-assisted cases across all 20 required categories, sourced from local evaluation-cleared World Bank/ILO canonical records plus explicitly synthetic safety fixtures. On 2026-10-27, reviewer `reviewer-user` confirmed reviewing and approving all 36 case definitions. This approval does not constitute scored review of future model outputs; use [evaluation-review-rubric.md](../../docs/evaluation/evaluation-review-rubric.md) for those later reviews.

## Validate Cases Without Provider Calls

```bash
make evaluation-verify
uv run --locked --package policylens python -m scripts.evaluation_case_set --release
```

The validator reports case/review counts, source-anchor and duplicate findings, and release-gate status without invoking a model. `--release` fails unless at least 30 cases are approved across both splits.

## Run the Offline Suite

```bash
make evaluation-verify
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --release --run-retrieval --split test --seed 0
```

The case gate is eligible: 36 cases cover both splits and all 20 categories. Fresh run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` evaluated the current `agent-v2` prompt and `non-agent-v1` baseline. After excluding failed generations, expected-behavior accuracy was **0.750** for the agent (32 scored, 4 failed) and **0.548** for the baseline (31 scored, 5 failed). Failed generations remain visible in coverage counts but do not count as incorrect answers. OpenAI generation requires `--run-generation --provider openai --allow-openai-live`; local MLX requires `--run-generation --provider mlx --run-mlx` and a ready loopback model. MCP statistics calls additionally require `--allow-mcp-tools`. Labels, reference claims, relevance grades, and split metadata are never included in runtime requests.

## Run AI-Only Answer-Quality Scoring

The optional `--ai-judge` scores groundedness and answer relevance for generated agent answers with a bounded structured rubric. It receives the question, response, and cited excerpts, plus separately bounded validated deterministic calculation results when present; it does not receive expected behavior, reference claims, split, review labels, or raw tool arguments. Scores and judge model/rubric/usage metadata are recorded; raw answers and free-form judge rationale are not. Expected behavior, retrieval recall, and citation checks remain deterministic. Reports distinguish attempted, scored, failed, and skipped judge outputs and disclose whether the judge model ID matches generation. AI scores are not human-validated or release approval; case-definition approval remains human-owned.

```bash
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --release --split all --run-retrieval --run-generation \
  --provider openai --allow-openai-live --allow-mcp-tools --ai-judge
```

`--allow-openai-live` explicitly authorizes external model requests for both generation and judging. This judge uses the selected provider/model, so its scores are exploratory rather than independent validation. Cost remains `not measured` unless the provider reports complete cost data; an incomplete partial sum is never presented as a total. Use `--provider mlx --run-mlx` instead for a configured loopback model.

The latest registered run used rubric `feature007-ai-judge-v1` and scored **31 of 33 attempted** outputs, with **0 failed**, **3 skipped**, and **2 ineligible outputs excluded**. The judge model ID `gpt-6-luna` matched the generator for scored cases. Mean groundedness was **2.742/5** and answer relevance **4.226/5**. The run is partial because four agent and five baseline outputs failed safely; failed generations are excluded from answer-quality scoring. See the [registered report](../../docs/evaluation/evaluation-report.md) for per-condition metrics and limitations.

## Scoring and Denominator Notes

New retrieval runs group passage variants by their expected evidence anchor, so one anchor contributes at most one hit and one denominator unit. Recall@k is the average per-result anchor fraction; the summary also exposes pooled anchor hits/expected totals, which need not equal that average. The v1.4 read-only summary reports each metric's scored sample count and condition/category breakdowns. Historical runs without stored anchor totals retain their recorded recall and are not recalculated.

The current judge rubric is `feature007-ai-judge-v2`; it can assess deterministic calculation claims against separately supplied validated tool results. The historical run above used v1 and its groundedness score remains **2.742/5**. No generation or judge rerun was made for this documentation refresh, so historical metrics are unchanged until an explicitly authorized new run.

Re-run the offline scoring and display regressions with:

```bash
uv run --locked --package policylens pytest -q \
  scripts/tests/test_evaluation_metrics.py \
  scripts/tests/test_evaluation_suite.py \
  scripts/tests/test_evaluation_judge.py \
  apps/backend/tests/api/test_evaluation_summary.py \
  apps/backend/tests/api/test_feature009_contracts.py
npm --prefix apps/frontend test -- tests/evaluations.test.tsx
```

Regenerate the report for a registered run without rerunning retrieval or calling a provider:

```bash
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --render-run-id c5df0ed0-3b56-4be9-8cbb-6a5bee32537e
```

The renderer checks that the current case-set hash matches the run, recalculates stratified metrics from stored per-case results, and filters answer reviews and error records by run ID. If related earlier reviews exist for the same case-set hash, they are shown in a separate historical section rather than attributed to the selected run.

## Review and Error Analysis

Case-definition approval is recorded for all 36 cases under pseudonymous reviewer ID `reviewer-user`. Manual output review is not required for AI-only runs; retain the [evaluation-review-rubric.md](../../docs/evaluation/evaluation-review-rubric.md) for optional calibration and error investigation. Add each material failure to the error manifest and link it to a regression test. Keep all reports, including blocked and negative runs.

## Outputs and Reproduction

Each run appends to `data/manifests/evaluation-run-manifest.json`; human review and error records append to `data/manifests/evaluation-review-manifest.json` and `data/manifests/evaluation-error-manifest.json`. Reports are written to `docs/evaluation/evaluation-report.md` and `docs/evaluation/evaluation-errors.md`. Rebuild error summaries with:

```bash
make evaluation-errors
```

Run records include the case-set hash, corpus/index/prompt/model versions, code revision when available, source-tree fingerprint, lock hash, configuration fingerprint, and artifacts. Reports disclose skipped providers, small samples, reviewer disagreement, and unmeasured cost/resource fields.

## Verification Record (refreshed 2026-10-28)

- `make check` passed formatting, lint, Python mypy, TypeScript, repository traceability, **300 backend tests**, **39 MCP tests**, **131 script tests**, and **68 frontend tests**.
- `make security-verify` passed **148 selected backend/security/evaluation tests**, **13 MCP tests**, the production frontend build, **68 frontend tests**, and secret scanning with no findings.
- `make retrieval-verify` reported `status: ready`. `make evaluation-verify` validated **36 approved cases across 20 categories and both splits**, with `release_eligible=true`, no anchor or duplicate issues, and `live_requests_made=false`.
- `npm --prefix apps/frontend run test:e2e` passed **11 mocked Playwright tests**. These verification commands make no provider request; the explicitly authorized run above made live provider and MCP requests.
- The registered AI-judged run is `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` (`partial`, 297 metric rows, 36 unique cases). Failure-excluded expected-behavior accuracy was **0.651** across 63 scored outputs (**0.750 agent**, **0.548 baseline**); retrieval Recall@6 **0.566**, citation correctness **0.750**, groundedness **2.742/5**, answer relevance **4.226/5**, and latency p50/p95 **5.5/5168 ms**. Nine failed generations were excluded from answer-quality scores. Provider cost was not measured.
- The judge scored **31 of 33 attempted** outputs, with **0 failed**, **3 skipped**, and **2 ineligible outputs excluded**; judge and generator model IDs matched for scored cases. This is same-model exploratory scoring, not independent or human validation. The latency percentiles include retrieval and generation rows; the report provides per-condition latency.
- Fresh score-transparency regressions passed: **42 focused backend tests** and **6 evaluation UI tests**. Python formatting/lint/mypy, frontend formatting/ESLint/TypeScript/build, traceability, and offline case validation also passed. No provider or judge request was made. These checks cover grouped-anchor recall, bounded v2 judge evidence, v1.4 score counts/distribution/breakdowns, and historical denominator messaging.