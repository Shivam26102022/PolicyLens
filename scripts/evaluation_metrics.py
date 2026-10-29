from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field

from policylens.retrieval.models import StrictModel

ExpectedBehavior = Literal["answer", "clarify", "abstain", "conflict", "block"]
ObservedBehavior = Literal["answer", "clarify", "abstain", "conflict", "block", "failed"]
EvaluationSplit = Literal["dev", "test"]
ProviderName = Literal["openai", "mlx"]
RetrievalModeName = Literal["bm25", "dense", "hybrid"]
JudgeStatus = Literal["completed", "failed", "skipped"]


class CaseMetricRecord(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    condition_id: str = Field(default="default", min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    split: EvaluationSplit
    expected_behavior: ExpectedBehavior
    observed_behavior: ObservedBehavior | None = None
    provider: ProviderName | None = None
    model_id: str | None = Field(default=None, max_length=300)
    route: str | None = Field(default=None, max_length=100)
    prompt_version: str | None = Field(default=None, max_length=100)
    retrieval_mode: RetrievalModeName | None = None
    index_version: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    expected_tool_selection: bool | None = None
    observed_tool_selection: bool | None = None
    tool_arguments_valid: bool | None = None
    structured_valid: bool | None = None
    citation_correctness: float | None = Field(default=None, ge=0, le=1)
    citation_completeness: float | None = Field(default=None, ge=0, le=1)
    citation_anchor_matches: int | None = Field(default=None, ge=0)
    citation_anchor_count: int | None = Field(default=None, ge=0)
    groundedness: float | None = Field(default=None, ge=1, le=5)
    answer_relevance: float | None = Field(default=None, ge=1, le=5)
    factual_accuracy: float | None = Field(default=None, ge=0, le=1)
    injection_attack_success: bool | None = None
    retrieval_recall_at_k: float | None = Field(default=None, ge=0, le=1)
    retrieval_anchor_hits: int | None = Field(default=None, ge=0)
    retrieval_anchor_count: int | None = Field(default=None, ge=0)
    validated_tool_result_count: int | None = Field(default=None, ge=0, le=8)
    reciprocal_rank: float | None = Field(default=None, ge=0, le=1)
    ndcg_at_k: float | None = Field(default=None, ge=0, le=1)
    empty_result: bool | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    judge_status: JudgeStatus | None = None
    judge_model_id: str | None = Field(default=None, max_length=300)
    judge_latency_ms: float | None = Field(default=None, ge=0)
    judge_input_tokens: int | None = Field(default=None, ge=0)
    judge_output_tokens: int | None = Field(default=None, ge=0)
    local_tokens_per_second: float | None = Field(default=None, ge=0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: set[str]) -> float:
    for rank, item_id in enumerate(ranked_ids, start=1):
        if item_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    if not relevant_ids:
        return 0.0
    return len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids)


def recall_at_k_by_group(
    ranked_ids: Sequence[str],
    relevant_groups: Sequence[Sequence[str]],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    if not relevant_groups:
        return 0.0
    retrieved = set(ranked_ids[:k])
    matched_groups = sum(bool(retrieved.intersection(group)) for group in relevant_groups)
    return matched_groups / len(relevant_groups)


def ndcg_at_k(
    ranked_ids: Sequence[str], relevance_grades: Mapping[str, int], k: int
) -> float | None:
    if k < 1:
        raise ValueError("k must be positive")
    grades = {item_id: grade for item_id, grade in relevance_grades.items() if grade > 0}
    if not grades:
        return None

    def gain_at_rank(grade: int, rank: int) -> float:
        return (2**grade - 1) / math.log2(rank + 1)

    dcg = sum(
        gain_at_rank(grades[item_id], rank)
        for rank, item_id in enumerate(ranked_ids[:k], start=1)
        if item_id in grades
    )
    ideal_grades = sorted(grades.values(), reverse=True)[:k]
    ideal_dcg = sum(gain_at_rank(grade, rank) for rank, grade in enumerate(ideal_grades, start=1))
    return dcg / ideal_dcg if ideal_dcg else None


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def bootstrap_mean_interval(
    values: Sequence[float], *, seed: int = 0, samples: int = 2000, minimum: int = 30
) -> dict[str, float | int] | None:
    if len(values) < minimum:
        return None
    if samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    generator = random.Random(seed)
    means = [sum(generator.choices(values, k=len(values))) / len(values) for _ in range(samples)]
    return {
        "lower_95": percentile(means, 0.025) or 0.0,
        "upper_95": percentile(means, 0.975) or 0.0,
        "n": len(values),
        "samples": samples,
        "seed": seed,
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(values: Sequence[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _classification_metrics(
    records: Sequence[CaseMetricRecord], label: ExpectedBehavior
) -> dict[str, float | int | None]:
    pairs = [
        (record.expected_behavior == label, record.observed_behavior == label)
        for record in records
        if record.observed_behavior is not None
    ]
    true_positive = sum(expected and observed for expected, observed in pairs)
    false_positive = sum(not expected and observed for expected, observed in pairs)
    false_negative = sum(expected and not observed for expected, observed in pairs)
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return {
        "precision": true_positive / precision_denominator if precision_denominator else None,
        "recall": true_positive / recall_denominator if recall_denominator else None,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def _aggregate(records: Sequence[CaseMetricRecord], *, seed: int) -> dict[str, Any]:
    observed = [record for record in records if record.observed_behavior is not None]
    scored = [record for record in observed if record.observed_behavior != "failed"]
    failed = [record for record in observed if record.observed_behavior == "failed"]
    behavior_matches = [record.expected_behavior == record.observed_behavior for record in observed]
    tool_pairs = [
        (record.expected_tool_selection, record.observed_tool_selection)
        for record in records
        if record.observed_behavior != "failed"
        and record.expected_tool_selection is not None
        and record.observed_tool_selection is not None
    ]
    latencies = [record.latency_ms for record in records if record.latency_ms is not None]
    groundedness = [
        record.groundedness
        for record in records
        if record.observed_behavior != "failed" and record.groundedness is not None
    ]
    factual = [
        record.factual_accuracy
        for record in records
        if record.observed_behavior != "failed" and record.factual_accuracy is not None
    ]
    citation_correctness = [
        record.citation_correctness
        for record in records
        if record.observed_behavior != "failed" and record.citation_correctness is not None
    ]
    citation_completeness = [
        record.citation_completeness
        for record in records
        if record.observed_behavior != "failed" and record.citation_completeness is not None
    ]
    injection_results = [
        record.injection_attack_success
        for record in records
        if record.observed_behavior != "failed" and record.injection_attack_success is not None
    ]
    retrieval_recall = [
        record.retrieval_recall_at_k
        for record in records
        if record.retrieval_recall_at_k is not None
    ]
    reciprocal_ranks = [
        record.reciprocal_rank for record in records if record.reciprocal_rank is not None
    ]
    ndcg_values = [record.ndcg_at_k for record in records if record.ndcg_at_k is not None]
    nonempty = [record.empty_result for record in records if record.empty_result is not None]
    tool_argument_results = [
        record.tool_arguments_valid
        for record in records
        if record.observed_behavior != "failed" and record.tool_arguments_valid is not None
    ]
    structured_results = [
        record.structured_valid
        for record in records
        if record.observed_behavior != "failed" and record.structured_valid is not None
    ]
    input_tokens = [record.input_tokens for record in records if record.input_tokens is not None]
    output_tokens = [record.output_tokens for record in records if record.output_tokens is not None]
    judge_input_tokens = [
        record.judge_input_tokens for record in records if record.judge_input_tokens is not None
    ]
    judge_output_tokens = [
        record.judge_output_tokens for record in records if record.judge_output_tokens is not None
    ]
    judge_latencies = [
        record.judge_latency_ms for record in records if record.judge_latency_ms is not None
    ]
    judge_attempts = [
        record for record in records if record.judge_status in {"completed", "failed"}
    ]
    judge_scored = [
        record
        for record in records
        if record.judge_status == "completed" and record.observed_behavior != "failed"
    ]
    judge_failed = [record for record in records if record.judge_status == "failed"]
    judge_skipped = [record for record in records if record.judge_status == "skipped"]
    judge_ineligible = [record for record in judge_attempts if record.observed_behavior == "failed"]
    judge_model_ids = sorted(
        {record.judge_model_id for record in records if record.judge_model_id is not None}
    )
    provider_records = [record for record in records if record.provider is not None]
    cost_is_complete = bool(provider_records) and all(
        record.estimated_cost_usd is not None for record in provider_records
    )
    estimated_cost_total = (
        sum(
            record.estimated_cost_usd or 0
            for record in provider_records
            if record.estimated_cost_usd is not None
        )
        if cost_is_complete
        else None
    )
    memory = [
        record.peak_memory_bytes for record in records if record.peak_memory_bytes is not None
    ]
    throughputs = [
        record.local_tokens_per_second
        for record in records
        if record.local_tokens_per_second is not None
    ]

    expected_behaviors = [record.expected_behavior for record in records]
    observed_behaviors = [record.observed_behavior for record in records]
    return {
        "case_count": len(records),
        "observed_count": len(observed),
        "scored_count": len(scored),
        "failed_count": len(failed),
        "expected_behavior_accuracy": _rate(behavior_matches),
        "abstention": _classification_metrics(records, "abstain"),
        "conflict_detection": _classification_metrics(records, "conflict"),
        "tool_selection_accuracy": _rate([expected == actual for expected, actual in tool_pairs]),
        "tool_argument_validity_rate": _rate(tool_argument_results),
        "structured_validity_rate": _rate(structured_results),
        "citation_correctness_mean": _mean(citation_correctness),
        "citation_completeness_mean": _mean(citation_completeness),
        "groundedness_mean": _mean(groundedness),
        "answer_relevance_mean": _mean(
            [
                record.answer_relevance
                for record in records
                if record.observed_behavior != "failed" and record.answer_relevance is not None
            ]
        ),
        "factual_accuracy_mean": _mean(factual),
        "injection_attack_success_rate": _rate(injection_results),
        "retrieval_recall_at_k_mean": _mean(retrieval_recall),
        "mrr": _mean(reciprocal_ranks),
        "ndcg_at_k_mean": _mean(ndcg_values),
        "nDCG_measured_count": len(ndcg_values),
        "retrieval_bootstrap_95": {
            name: bootstrap_mean_interval(values, seed=seed, minimum=20)
            for name, values in (
                ("recall_at_k", retrieval_recall),
                ("mrr", reciprocal_ranks),
                ("ndcg_at_k", ndcg_values),
            )
        },
        "empty_result_rate": _rate(nonempty),
        "latency_ms": {
            "count": len(latencies),
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "mean": _mean(latencies),
            "mean_bootstrap_95": bootstrap_mean_interval(latencies, seed=seed),
        },
        "input_tokens_total": sum(input_tokens) if input_tokens else None,
        "output_tokens_total": sum(output_tokens) if output_tokens else None,
        "ai_judge": {
            "attempted_count": len(judge_attempts),
            "scored_count": len(judge_scored),
            "failed_count": len(judge_failed),
            "skipped_count": len(judge_skipped),
            "ineligible_output_count": len(judge_ineligible),
            "model_ids": judge_model_ids,
            "same_model_as_generator": (
                all(record.judge_model_id == record.model_id for record in judge_scored)
                if judge_scored
                else None
            ),
            "input_tokens_total": sum(judge_input_tokens) if judge_input_tokens else None,
            "output_tokens_total": sum(judge_output_tokens) if judge_output_tokens else None,
            "latency_ms_mean": _mean(judge_latencies),
        },
        "estimated_cost_usd_total": estimated_cost_total,
        "peak_memory_bytes_max": max(memory) if memory else None,
        "local_tokens_per_second_mean": _mean(throughputs),
        "expected_behavior_counts": _count_values(expected_behaviors),
        "observed_behavior_counts": _count_values(observed_behaviors),
    }


def _mcnemar_exact_p(only_a: int, only_b: int) -> float:
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)


def paired_condition_comparisons(
    records: Sequence[CaseMetricRecord], *, seed: int = 0
) -> list[dict[str, Any]]:
    """Paired exact McNemar test on expected-behaviour correctness between conditions."""
    by_condition: dict[str, dict[str, bool]] = defaultdict(dict)
    for record in records:
        if record.observed_behavior is None:
            continue
        by_condition[record.condition_id][record.case_id] = (
            record.expected_behavior == record.observed_behavior
        )
    ids = sorted(by_condition)
    results: list[dict[str, Any]] = []
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            shared = sorted(set(by_condition[left]) & set(by_condition[right]))
            if len(shared) < 10:
                continue
            only_left = sum(by_condition[left][c] and not by_condition[right][c] for c in shared)
            only_right = sum(by_condition[right][c] and not by_condition[left][c] for c in shared)
            diffs = [float(by_condition[left][c]) - float(by_condition[right][c]) for c in shared]
            results.append(
                {
                    "condition_a": left,
                    "condition_b": right,
                    "paired_cases": len(shared),
                    "a_only_correct": only_left,
                    "b_only_correct": only_right,
                    "accuracy_difference_a_minus_b": sum(diffs) / len(diffs),
                    "difference_bootstrap_95": bootstrap_mean_interval(
                        diffs, seed=seed, minimum=10
                    ),
                    "mcnemar_exact_p": _mcnemar_exact_p(only_left, only_right),
                }
            )
    return results


def _count_values(values: Sequence[object]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        if value is not None:
            counts[str(value)] += 1
    return dict(sorted(counts.items()))


def summarize_case_metrics(records: Sequence[CaseMetricRecord], *, seed: int = 0) -> dict[str, Any]:
    if not records:
        return {
            "case_count": 0,
            "overall": _aggregate((), seed=seed),
            "by_category": {},
            "by_split": {},
            "limitations": ("No case results were measured.",),
        }
    has_failed_outputs = any(record.observed_behavior == "failed" for record in records)
    category_groups: dict[str, list[CaseMetricRecord]] = defaultdict(list)
    split_groups: dict[str, list[CaseMetricRecord]] = defaultdict(list)
    condition_groups: dict[str, list[CaseMetricRecord]] = defaultdict(list)
    condition_category_groups: dict[str, dict[str, list[CaseMetricRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    condition_split_groups: dict[str, dict[str, list[CaseMetricRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    provider_groups: dict[str, list[CaseMetricRecord]] = defaultdict(list)
    for record in records:
        category_groups[record.category].append(record)
        split_groups[record.split].append(record)
        condition_groups[record.condition_id].append(record)
        condition_category_groups[record.condition_id][record.category].append(record)
        condition_split_groups[record.condition_id][record.split].append(record)
        if record.provider is not None:
            provider_groups[record.provider].append(record)
    return {
        "case_count": len(records),
        "overall": _aggregate(records, seed=seed),
        "by_category": {
            key: _aggregate(group, seed=seed) for key, group in sorted(category_groups.items())
        },
        "by_split": {
            key: _aggregate(group, seed=seed) for key, group in sorted(split_groups.items())
        },
        "by_condition": {
            key: _aggregate(group, seed=seed) for key, group in sorted(condition_groups.items())
        },
        "by_condition_category": {
            condition: {
                category: _aggregate(group, seed=seed)
                for category, group in sorted(categories.items())
            }
            for condition, categories in sorted(condition_category_groups.items())
        },
        "by_condition_split": {
            condition: {
                split: _aggregate(group, seed=seed) for split, group in sorted(splits.items())
            }
            for condition, splits in sorted(condition_split_groups.items())
        },
        "by_provider": {
            key: _aggregate(group, seed=seed) for key, group in sorted(provider_groups.items())
        },
        "paired_comparisons": paired_condition_comparisons(records, seed=seed),
        "limitations": tuple(
            [
                (
                    "Groundedness and answer relevance are AI-judged; they are not human-"
                    "validated or calibrated for this run."
                    if any(record.judge_status == "completed" for record in records)
                    else "Groundedness and answer relevance are not measured unless an AI judge "
                    "completes successfully."
                ),
                "Bootstrap intervals are omitted for fewer than 30 observations.",
                "Cost and local resource metrics are null when unavailable.",
                "nDCG uses binary relevance for cases without graded relevance labels.",
            ]
            + (
                ["Some AI judge requests failed; unscored outputs are excluded from quality means."]
                if any(record.judge_status == "failed" for record in records)
                else []
            )
            + (
                [
                    "Failed generation outputs count as incorrect for expected-behavior accuracy; "
                    "they are excluded from answer-quality judge scores."
                ]
                if has_failed_outputs
                else []
            )
        ),
    }
