from __future__ import annotations

from typing import Any

import pytest

from scripts.evaluation_metrics import (
    CaseMetricRecord,
    EvaluationSplit,
    ExpectedBehavior,
    ObservedBehavior,
    bootstrap_mean_interval,
    ndcg_at_k,
    paired_condition_comparisons,
    percentile,
    recall_at_k,
    recall_at_k_by_group,
    reciprocal_rank,
    summarize_case_metrics,
)


def _record(
    case_id: str,
    *,
    category: str = "factual",
    split: EvaluationSplit = "dev",
    expected_behavior: ExpectedBehavior = "answer",
    observed_behavior: ObservedBehavior | None = "answer",
    **overrides: Any,
) -> CaseMetricRecord:
    return CaseMetricRecord(
        case_id=case_id,
        category=category,
        split=split,
        expected_behavior=expected_behavior,
        observed_behavior=observed_behavior,
        **overrides,
    )


def test_ranked_retrieval_metrics_handle_hits_and_ungraded_cases() -> None:
    assert reciprocal_rank(("noise", "target"), {"target"}) == 0.5
    assert recall_at_k(("target", "noise"), {"target", "other"}, 1) == 0.5
    ndcg = ndcg_at_k(("noise", "target"), {"target": 3, "noise": 0}, 2)
    assert ndcg is not None
    assert ndcg < 1.0
    assert ndcg_at_k(("anything",), {}, 5) is None
    with pytest.raises(ValueError, match="k must be positive"):
        recall_at_k(("target",), {"target"}, 0)


def test_grouped_recall_counts_each_expected_anchor_once() -> None:
    groups = (("split-a", "split-b", "split-c"), ("other",))

    assert recall_at_k_by_group(("split-b",), groups, 5) == 0.5
    assert recall_at_k_by_group(("split-a", "split-b", "other"), groups, 5) == 1.0
    assert recall_at_k_by_group(("noise",), (), 5) == 0.0


def test_latency_percentiles_and_bootstrap_are_deterministic() -> None:
    values = [float(value) for value in range(30)]

    assert percentile(values, 0.5) == 14.5
    assert bootstrap_mean_interval(values, seed=17) == bootstrap_mean_interval(values, seed=17)
    assert bootstrap_mean_interval(values[:29]) is None


def test_stratified_metrics_include_behavior_tool_citation_and_safety() -> None:
    records = [
        _record(
            "a",
            condition_id="openai:agent",
            provider="openai",
            model_id="openai-test",
            index_version="a" * 64,
            category="calculation",
            split="test",
            expected_behavior="abstain",
            observed_behavior="answer",
            expected_tool_selection=True,
            observed_tool_selection=True,
            tool_arguments_valid=True,
            structured_valid=True,
            citation_correctness=1.0,
            citation_completeness=0.5,
            injection_attack_success=False,
            empty_result=False,
            latency_ms=100,
            input_tokens=20,
            output_tokens=8,
            estimated_cost_usd=0.01,
            groundedness=4,
            answer_relevance=5,
            judge_status="completed",
            judge_model_id="judge-model",
            judge_latency_ms=25,
            judge_input_tokens=40,
            judge_output_tokens=6,
            peak_memory_bytes=4096,
        ),
        _record(
            "b",
            condition_id="mlx:agent",
            provider="mlx",
            model_id="mlx-test",
            index_version="b" * 64,
            category="factual",
            split="dev",
            observed_behavior="abstain",
            expected_tool_selection=False,
            observed_tool_selection=True,
            tool_arguments_valid=False,
            structured_valid=False,
            citation_correctness=0.0,
            citation_completeness=0.0,
            injection_attack_success=True,
            empty_result=True,
            latency_ms=300,
            ndcg_at_k=0.75,
        ),
    ]

    summary = summarize_case_metrics(records)

    assert summary["case_count"] == 2
    assert summary["overall"]["expected_behavior_accuracy"] == 0.0
    assert summary["overall"]["tool_selection_accuracy"] == 0.5
    assert summary["overall"]["tool_argument_validity_rate"] == 0.5
    assert summary["overall"]["structured_validity_rate"] == 0.5
    assert summary["overall"]["citation_correctness_mean"] == 0.5
    assert summary["overall"]["citation_completeness_mean"] == 0.25
    assert summary["overall"]["abstention"]["false_positive"] == 1
    assert summary["overall"]["abstention"]["false_negative"] == 1
    assert summary["overall"]["empty_result_rate"] == 0.5
    assert summary["overall"]["injection_attack_success_rate"] == 0.5
    assert summary["overall"]["ndcg_at_k_mean"] == 0.75
    assert summary["overall"]["latency_ms"]["p50"] == 200
    assert summary["overall"]["groundedness_mean"] == 4
    assert summary["overall"]["answer_relevance_mean"] == 5
    assert summary["overall"]["ai_judge"] == {
        "attempted_count": 1,
        "scored_count": 1,
        "failed_count": 0,
        "skipped_count": 0,
        "ineligible_output_count": 0,
        "model_ids": ["judge-model"],
        "same_model_as_generator": False,
        "input_tokens_total": 40,
        "output_tokens_total": 6,
        "latency_ms_mean": 25,
    }
    assert summary["by_category"]["calculation"]["case_count"] == 1
    assert summary["by_split"]["test"]["case_count"] == 1
    assert summary["by_condition"]["openai:agent"]["case_count"] == 1
    assert (
        summary["by_condition_category"]["openai:agent"]["calculation"][
            "expected_behavior_accuracy"
        ]
        == 0.0
    )
    assert (
        summary["by_condition_category"]["mlx:agent"]["factual"]["expected_behavior_accuracy"]
        == 0.0
    )
    assert summary["by_condition_split"]["openai:agent"]["test"]["case_count"] == 1
    assert summary["by_provider"]["mlx"]["case_count"] == 1
    assert summary["overall"]["estimated_cost_usd_total"] is None
    assert summarize_case_metrics(records[:1])["overall"]["estimated_cost_usd_total"] == 0.01


def test_small_sample_has_no_bootstrap_interval_and_empty_metrics_are_explicit() -> None:
    summary = summarize_case_metrics([_record("single", latency_ms=10)])
    assert summary["overall"]["latency_ms"]["mean_bootstrap_95"] is None

    empty = summarize_case_metrics([])
    assert empty["overall"]["case_count"] == 0
    assert empty["limitations"] == ("No case results were measured.",)


def test_failed_generation_counts_as_incorrect_behavior() -> None:
    summary = summarize_case_metrics(
        [
            _record("success", expected_behavior="answer", observed_behavior="answer"),
            _record("failure", expected_behavior="answer", observed_behavior="failed"),
        ]
    )

    assert summary["overall"]["scored_count"] == 1
    assert summary["overall"]["failed_count"] == 1
    assert summary["overall"]["expected_behavior_accuracy"] == 0.5


def test_ai_judge_failures_are_counted_and_excluded_from_quality_scores() -> None:
    summary = summarize_case_metrics(
        [
            _record(
                "failed-judge",
                condition_id="openai:agent",
                provider="openai",
                model_id="test-model",
                judge_status="failed",
                judge_model_id="judge-model",
            )
        ]
    )

    assert summary["overall"]["groundedness_mean"] is None
    assert summary["overall"]["answer_relevance_mean"] is None
    assert summary["overall"]["ai_judge"]["attempted_count"] == 1
    assert summary["overall"]["ai_judge"]["scored_count"] == 0
    assert summary["overall"]["ai_judge"]["failed_count"] == 1
    assert any("judge requests failed" in item for item in summary["limitations"])


def test_failed_outputs_count_against_behavior_but_not_quality_and_judge_scores() -> None:
    summary = summarize_case_metrics(
        [
            _record(
                "successful",
                expected_behavior="answer",
                observed_behavior="answer",
                expected_tool_selection=True,
                observed_tool_selection=True,
                citation_correctness=1.0,
                citation_completeness=1.0,
                groundedness=5,
                answer_relevance=5,
                factual_accuracy=1.0,
                injection_attack_success=False,
                judge_status="completed",
            ),
            _record(
                "failed",
                expected_behavior="abstain",
                observed_behavior="failed",
                expected_tool_selection=False,
                observed_tool_selection=True,
                citation_correctness=0.0,
                citation_completeness=0.0,
                groundedness=1,
                answer_relevance=1,
                factual_accuracy=0.0,
                injection_attack_success=True,
                judge_status="completed",
            ),
        ]
    )
    overall = summary["overall"]

    assert overall["observed_count"] == 2
    assert overall["scored_count"] == 1
    assert overall["failed_count"] == 1
    assert overall["expected_behavior_accuracy"] == 0.5
    assert overall["abstention"]["false_negative"] == 1
    assert overall["tool_selection_accuracy"] == 1.0
    assert overall["citation_correctness_mean"] == 1.0
    assert overall["citation_completeness_mean"] == 1.0
    assert overall["groundedness_mean"] == 5
    assert overall["answer_relevance_mean"] == 5
    assert overall["factual_accuracy_mean"] == 1.0
    assert overall["injection_attack_success_rate"] == 0.0
    assert overall["ai_judge"]["attempted_count"] == 2
    assert overall["ai_judge"]["scored_count"] == 1
    assert overall["ai_judge"]["ineligible_output_count"] == 1
    assert any(
        "count as incorrect for expected-behavior" in item for item in summary["limitations"]
    )


def test_paired_condition_comparison_reports_mcnemar_and_bootstrap() -> None:
    def record(case: int, condition: str, ok: bool) -> CaseMetricRecord:
        return CaseMetricRecord(
            case_id=f"c{case}",
            condition_id=condition,
            category="factual",
            split="test",
            expected_behavior="answer",
            observed_behavior="answer" if ok else "abstain",
        )

    records = [record(i, "agent", True) for i in range(12)]
    records += [record(i, "base", i >= 8) for i in range(12)]

    (pair,) = paired_condition_comparisons(records)

    assert pair["a_only_correct"] == 8
    assert pair["b_only_correct"] == 0
    assert pair["mcnemar_exact_p"] == pytest.approx(2 * 0.5**8)
    assert pair["difference_bootstrap_95"] is not None
