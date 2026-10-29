# Feature 007 Traceability

| Requirement | Implementation / Evidence | Status and limitation |
|---|---|---|
| EVAL-007-01 | `data/evaluation/feature007-cases.json`; `scripts/evaluation_case_set.py`; `scripts/tests/test_evaluation_case_set.py` | 36 AI-assisted case definitions were reviewed and approved by pseudonymous reviewer `reviewer-user` on 2026-10-27; all 20 categories and both splits are covered. |
| EVAL-007-02 | `scripts/evaluation_case_set.py::EvaluationCase.to_request`; `scripts/tests/test_evaluation_case_set.py::test_runtime_request_excludes_evaluation_labels`; `validate_case_anchors` | Runtime adapter excludes labels. Source permissions and source/page/row anchors are checked locally. Exact duplicates and possible lexical duplicates are surfaced; human adjudication is still required. |
| EVAL-007-03 | `scripts/evaluation_metrics.py::recall_at_k_by_group`; `scripts/evaluate_suite.py`; `apps/backend/src/policylens/api/evaluation_summary.py`; `scripts/tests/test_evaluation_metrics.py`; `apps/backend/tests/api/test_evaluation_summary.py` | Retrieval recall counts each expected evidence anchor once despite multiple passage variants; per-metric sample counts, anchor hit/denominator totals, and condition/category breakdowns are exposed. Failed generations are excluded from answer-quality metrics while retrieval and operational metrics remain available. nDCG is null without relevance grades. |
| EVAL-007-04 | `scripts/evaluate_suite.py::_execute_generation`; `scripts/tests/test_evaluation_suite.py::test_openai_mlx_agent_and_baseline_use_identical_frozen_case_ids`; `apps/backend/src/policylens/retrieval/evaluation.py` | Run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` measures current `agent-v2` against `non-agent-v1`: failure-excluded expected-behavior accuracy is 0.750 (32 scored agent outputs) and 0.548 (31 baseline outputs). Retrieval varies BM25/dense/hybrid and chunking. No MLX/provider-parity claim is made. |
| EVAL-007-05 | `scripts/evaluation_judge.py`; `scripts/tests/test_evaluation_judge.py`; `scripts/evaluation_metrics.py`; `docs/evaluation/evaluation-review-rubric.md` | The pinned structured judge is identified per run. AI scores are labeled uncalibrated/not human-validated; deterministic oracle and retrieval metrics remain separate. Historical answer ratings remain separately scoped. |
| EVAL-007-06 | `scripts/evaluation_errors.py`; `scripts/analyze_evaluation_errors.py`; `scripts/tests/test_evaluation_errors.py` | Error schema, redaction, append-only storage, summary, and Markdown report are implemented. Eight error records/25 occurrences are linked to the earlier reviewed run and are scoped separately from the latest run. |
| EVAL-007-07 | `scripts/evaluation_judge.py`; `scripts/evaluate_suite.py::_validated_tool_evidence`; `scripts/tests/test_evaluation_judge.py`; `scripts/tests/test_evaluation_suite.py` | Bounded judge input contains question, output, cited excerpts, and separately typed validated deterministic calculation results when present. Expected labels/references and raw tool arguments are excluded; only scores and safe judge metadata are stored, and CLI use requires explicit provider opt-in. |
| REPRO-007-01 | `scripts/evaluation_registry.py`; `scripts/tests/test_evaluation_registry.py`; `scripts/evaluate_suite.py` | Case/corpus/config/lock/tool/prompt/model/index/source-tree fingerprints and artifacts are stored where available. Git revision remains unavailable in this non-Git checkout. |
| AC-007-01 | `specs/007-evaluation/contracts/evaluation-case-set.schema.json`; `scripts/tests/test_evaluation_case_set.py` | Required case fields and review status are schema-validated; all 36 cases have human approval metadata and meet category/split coverage. |
| AC-007-02 | `scripts/tests/test_evaluation_case_set.py::test_runtime_request_excludes_evaluation_labels`; `scripts/tests/test_evaluation_suite.py::test_retrieval_case_adapter_excludes_runtime_labels` | Expected behavior, claims, split, review state, relevance grades, and adversarial fixture are excluded from runtime requests. |
| AC-007-03 | `scripts/evaluation_case_set.py::release_gate_issues`; `scripts/tests/test_evaluation_case_set.py::test_case_validation_cli_is_offline_and_release_mode_fails_without_approvals`; `make evaluation-verify` | Gate test still proves unapproved sets are blocked; current set validates at 36 approved cases with no provider requests. |
| SC-007-01 | `data/evaluation/feature007-cases.json`; `make evaluation-verify`; `scripts/tests/test_evaluation_case_set.py`; `docs/evaluation/evaluation-report.md` | 36 approved case definitions across 20 categories and both splits validate. Registered run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` reports metrics across 297 rows; nine failed generation outputs are excluded from answer-quality scores. |
| SC-007-02 | `scripts/evaluation_registry.py`; `data/manifests/evaluation-run-manifest.json`; `scripts/tests/test_evaluation_registry.py` | Append-only registry retains blocked, retrieval, and historical generation runs with their available case-set, corpus, config, lock, tool, and source fingerprints. |
| SC-007-03 | `docs/evaluation/evaluation-review-rubric.md`; `docs/evaluation/evaluation-report.md`; `docs/evaluation/evaluation-errors.md`; `scripts/evaluation_review.py` | Case-definition sign-off and one AI-assisted, single-reviewer output-review set are disclosed separately. Reports disclose unmeasured metrics and make no provider-parity claim. |
| SC-007-04 | `scripts/evaluation_metrics.py`; `scripts/evaluation_suite.py`; `apps/backend/src/policylens/api/evaluation_summary.py`; Feature 009 UI contract/tests | The v1.4 summary exposes rubric/model identity, scored/failed output coverage, failure-exclusion status, and attempted/scored/failed/skipped/ineligible judge counts; report/UI state that AI quality scores are not human-validated and raw answers are not persisted. |
| SC-007-05 | `apps/backend/src/policylens/api/evaluation_summary.py`; Feature 009 v1.4 contract/UI; `apps/backend/tests/api/test_evaluation_summary.py`; `apps/frontend/tests/evaluations.test.tsx` | Per-metric sample counts, groundedness distributions, pooled retrieval/citation anchor totals, and condition/category comparisons are available. Historical recall without anchor totals is retained and explicitly not recalculated. |

## Verification

```bash
make evaluation-verify
uv run --locked --package policylens pytest scripts/tests/test_evaluation_case_set.py scripts/tests/test_evaluation_registry.py scripts/tests/test_evaluation_metrics.py scripts/tests/test_evaluation_judge.py scripts/tests/test_evaluation_suite.py scripts/tests/test_evaluation_review.py scripts/tests/test_evaluation_errors.py
make format-check-python
make lint-python
make typecheck-python
make test-python
python3 scripts/check_traceability.py
```

## Verification Results (2026-10-28)

| Gate | Result |
|---|---|
| `make check` | PASS; format, lint, Python mypy, TypeScript, traceability, 300 backend, 39 MCP, 131 script, and 68 frontend tests passed. |
| `make security-verify` | PASS; 148 selected backend/security/evaluation tests, 13 MCP tests, production build, 68 frontend tests, and secret scan with no findings. |
| `npm --prefix apps/frontend run test:e2e` | PASS; 11 mocked Playwright tests. |
| `make retrieval-verify` | PASS; local index status `ready`. |
| `make evaluation-verify` | PASS; 36 approved cases across 20 categories and both splits, no anchor/permission issues or duplicate warnings, `release_eligible=true`, no live requests. |
| Offline registered-run report render | PASS; run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e`, 297 stored metric rows, and failure-excluded quality scores rendered from stored results without rerunning retrieval or calling a provider. |
| Fresh score-transparency regressions | PASS; 42 focused backend tests and 6 evaluation UI tests. No provider or judge request was made. |

## External Review Gate

The case set is AI-assisted material with human case-definition sign-off recorded for all 36 cases under reviewer `reviewer-user` on 2026-10-27. The approved set is release-eligible. The latest measured run uses `agent-v2` and is partial because nine outputs failed safely; those outputs are excluded from answer-quality metrics. Independent human answer reviews, provider parity, and a recorded MLX run remain outstanding. MOM 2025 material remains excluded because the source manifest has rights review pending, and the linked MOM press-release pages returned 404.

Automated checks, case validation, and offline report rendering made no live provider requests. Separately, a fresh session-backed Research smoke check made an explicitly consented OpenAI request and a local Policy Data MCP call; the endpoint answered the India state-rate question with the page-16 citation and persisted session context. Run `c5df0ed0-3b56-4be9-8cbb-6a5bee32537e` also records live requests; no MLX run is recorded. Independent human answer-quality scores, provider parity, and local resource measurements remain unmeasured.
