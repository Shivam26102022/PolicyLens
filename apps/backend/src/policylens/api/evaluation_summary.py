from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from policylens.retrieval.models import StrictModel
from policylens.settings import PROJECT_ROOT

DEFAULT_CASE_SET_PATH = PROJECT_ROOT / "data/evaluation/feature007-cases.json"
DEFAULT_RUN_MANIFEST = PROJECT_ROOT / "data/manifests/evaluation-run-manifest.json"
DEFAULT_REVIEW_MANIFEST = PROJECT_ROOT / "data/manifests/evaluation-review-manifest.json"
DEFAULT_ERROR_MANIFEST = PROJECT_ROOT / "data/manifests/evaluation-error-manifest.json"

_MODEL_PRICES_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-6-luna": (Decimal("0.10"), Decimal("0.50")),
}
_COST_ESTIMATE_PRICING_AS_OF = date(2026, 10, 28)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class EvaluationSummaryUnavailable(ValueError):
    """The local evaluation artifacts cannot be summarized safely."""


class _ManifestRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _EvaluationCase(_ManifestRecord):
    case_id: str = ""
    category: str
    question: str = ""
    expected_behavior: str = "answer"
    difficulty: str = ""
    reference_claims: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    expected_anchors: tuple[dict[str, Any], ...] = ()
    split: Literal["dev", "test"]
    review_status: Literal["candidate", "in_review", "approved", "rejected"]


class _CaseSetManifest(_ManifestRecord):
    schema_version: Literal["1.0"]
    cases: tuple[_EvaluationCase, ...]


class _RunResultSummary(_ManifestRecord):
    case_id: str | None = Field(default=None, max_length=100)
    condition_id: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=80)
    provider: str | None = Field(default=None, max_length=50)
    model_id: str | None = Field(default=None, max_length=300)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    judge_status: Literal["completed", "failed", "skipped"] | None = None
    judge_model_id: str | None = Field(default=None, max_length=300)
    judge_input_tokens: int | None = Field(default=None, ge=0)
    judge_output_tokens: int | None = Field(default=None, ge=0)
    expected_behavior: Literal["answer", "clarify", "abstain", "conflict", "block"] | None = None
    observed_behavior: (
        Literal["answer", "clarify", "abstain", "conflict", "block", "failed"] | None
    ) = None
    retrieval_recall_at_k: float | None = Field(default=None, ge=0, le=1)
    retrieval_anchor_hits: int | None = Field(default=None, ge=0)
    retrieval_anchor_count: int | None = Field(default=None, ge=0)
    citation_correctness: float | None = Field(default=None, ge=0, le=1)
    citation_completeness: float | None = Field(default=None, ge=0, le=1)
    citation_anchor_matches: int | None = Field(default=None, ge=0)
    citation_anchor_count: int | None = Field(default=None, ge=0)
    groundedness: float | None = Field(default=None, ge=1, le=5)
    answer_relevance: float | None = Field(default=None, ge=1, le=5)
    validated_tool_result_count: int | None = Field(default=None, ge=0, le=8)
    latency_ms: float | None = Field(default=None, ge=0)


class _RunRecord(_ManifestRecord):
    run_id: UUID
    status: Literal["completed", "partial", "blocked", "failed"]
    started_at: datetime
    finished_at: datetime | None
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    live_requests_made: bool
    results: tuple[_RunResultSummary, ...] = ()


class _ReviewRecord(_ManifestRecord):
    case_id: str


class _ErrorRecord(_ManifestRecord):
    error_id: str
    failure_layer: str


class EvaluationCaseView(StrictModel):
    case_id: str
    category: str
    question: str
    expected_behavior: str
    difficulty: str
    split: Literal["dev", "test"]
    review_status: str
    reference_claims: tuple[str, ...]
    required_tools: tuple[str, ...]
    forbidden_behaviors: tuple[str, ...]
    expected_sources: tuple[str, ...]


class EvaluationCaseSetSummary(StrictModel):
    case_count: int = Field(ge=0)
    approved_case_count: int = Field(ge=0)
    category_count: int = Field(ge=0)
    category_counts: dict[str, int]
    split_counts: dict[Literal["dev", "test"], int]
    cases: tuple[EvaluationCaseView, ...] = ()


class EvaluationScoreMetrics(StrictModel):
    expected_behavior_accuracy: float | None = None
    expected_behavior_scored_count: int = Field(default=0, ge=0)
    retrieval_recall_at_k_scored_count: int | None = Field(default=None, ge=0)
    retrieval_anchor_hits: int | None = Field(default=None, ge=0)
    retrieval_anchor_count: int | None = Field(default=None, ge=0)
    citation_correctness_scored_count: int | None = Field(default=None, ge=0)
    citation_completeness_mean: float | None = None
    citation_completeness_scored_count: int | None = Field(default=None, ge=0)
    citation_anchor_matches: int | None = Field(default=None, ge=0)
    citation_anchor_count: int | None = Field(default=None, ge=0)
    groundedness_scored_count: int | None = Field(default=None, ge=0)
    groundedness_score_distribution: tuple[int, int, int, int, int] | None = None
    answer_relevance_scored_count: int | None = Field(default=None, ge=0)
    validated_tool_result_output_count: int | None = Field(default=None, ge=0)
    latency_sample_count: int | None = Field(default=None, ge=0)
    retrieval_recall_at_k_mean: float | None = None
    citation_correctness_mean: float | None = None
    groundedness_mean: float | None = None
    answer_relevance_mean: float | None = None


class EvaluationMetricsSummary(EvaluationScoreMetrics):
    failed_output_count: int = Field(default=0, ge=0)
    failure_exclusion_applied: bool = False
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    estimated_cost_usd_total: float | None = None
    estimated_cost_basis: Literal[
        "provider_reported", "token_estimate", "partial_token_estimate", "unavailable"
    ] = "unavailable"
    estimated_cost_pricing_as_of: date | None = None
    estimated_cost_usage_gap_count: int | None = Field(default=None, ge=0)
    estimated_cost_model_ids: tuple[str, ...] = Field(default=(), max_length=10)
    headline_condition_id: str | None = None
    baseline_condition_id: str | None = None
    baseline_expected_behavior_accuracy: float | None = None
    baseline_expected_behavior_scored_count: int | None = Field(default=None, ge=0)
    paired_accuracy_difference: float | None = None
    paired_accuracy_difference_lower_95: float | None = None
    paired_accuracy_difference_upper_95: float | None = None
    paired_mcnemar_p: float | None = None
    paired_case_count: int | None = Field(default=None, ge=0)


class EvaluationCategoryBreakdown(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    result_count: int = Field(ge=0)
    failed_output_count: int = Field(ge=0)
    metrics: EvaluationScoreMetrics


class EvaluationConditionBreakdown(StrictModel):
    condition_id: str = Field(min_length=1, max_length=200)
    result_count: int = Field(ge=0)
    failed_output_count: int = Field(ge=0)
    metrics: EvaluationScoreMetrics
    category_breakdowns: tuple[EvaluationCategoryBreakdown, ...] = Field(max_length=40)


class EvaluationJudgeSummary(StrictModel):
    enabled: bool
    rubric_version: str | None = Field(default=None, max_length=100)
    model_ids: tuple[str, ...] = Field(default=(), max_length=10)
    same_model_as_generator: bool | None = None
    attempted_count: int = Field(default=0, ge=0)
    scored_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    ineligible_output_count: int = Field(default=0, ge=0)


class EvaluationRunSummary(StrictModel):
    run_id: UUID
    status: Literal["completed", "partial", "blocked", "failed"]
    started_at: datetime
    finished_at: datetime | None
    split: Literal["all", "dev", "test"]
    case_count: int = Field(ge=0)
    live_requests_made: bool
    metrics: EvaluationMetricsSummary
    condition_breakdowns: tuple[EvaluationConditionBreakdown, ...] = Field(max_length=100)
    ai_judge: EvaluationJudgeSummary
    limitations: tuple[str, ...] = Field(max_length=50)


class EvaluationSummaryResponse(StrictModel):
    schema_version: Literal["1.5"] = "1.5"
    status: Literal["available", "empty"]
    case_set: EvaluationCaseSetSummary
    runs: tuple[EvaluationRunSummary, ...] = Field(max_length=50)
    reviewed_case_count: int = Field(ge=0)
    error_record_count: int = Field(ge=0)


def _load_manifest_records(path: Path, collection: str) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationSummaryUnavailable("Evaluation records are unavailable.") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or not isinstance(manifest.get(collection), list)
    ):
        raise EvaluationSummaryUnavailable("Evaluation summary records are unavailable.")
    records = manifest[collection]
    if any(not isinstance(item, dict) for item in records):
        raise EvaluationSummaryUnavailable("Evaluation summary records are unavailable.")
    return tuple(records)


def _load_run_records(path: Path) -> tuple[_RunRecord, ...]:
    records = _load_manifest_records(path, "runs")
    try:
        validated = tuple(_RunRecord.model_validate(item) for item in records)
    except ValidationError as error:
        raise EvaluationSummaryUnavailable("Evaluation run records are unavailable.") from error
    return tuple(sorted(validated, key=lambda item: item.started_at, reverse=True)[:50])


def _safe_metric(value: object, *, maximum: float | None = None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        return None
    if maximum is not None and numeric > maximum:
        return None
    return numeric


def _safe_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _cost_summary(
    results: tuple[_RunResultSummary, ...],
    overall: dict[str, Any],
) -> tuple[
    float | None,
    Literal["provider_reported", "token_estimate", "partial_token_estimate", "unavailable"],
    date | None,
    int | None,
    tuple[str, ...],
]:
    reported_cost = _safe_metric(overall.get("estimated_cost_usd_total"))
    if reported_cost is not None:
        return reported_cost, "provider_reported", None, None, ()

    total = Decimal(0)
    usage_gap_count = 0
    priced_model_ids: set[str] = set()

    def add_usage(
        model_id: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        nonlocal total, usage_gap_count
        if input_tokens is None and output_tokens is None:
            usage_gap_count += 1
            return
        normalized_model_id = model_id.strip().lower() if model_id else ""
        prices = _MODEL_PRICES_USD_PER_MILLION.get(normalized_model_id)
        if prices is None:
            usage_gap_count += 1
            return

        priced_model_ids.add(normalized_model_id)
        input_price, output_price = prices
        if input_tokens is None or output_tokens is None:
            usage_gap_count += 1
        if input_tokens is not None:
            total += Decimal(input_tokens) * input_price / Decimal(1_000_000)
        if output_tokens is not None:
            total += Decimal(output_tokens) * output_price / Decimal(1_000_000)

    for result in results:
        has_generation_record = (
            result.provider is not None
            or result.model_id is not None
            or result.input_tokens is not None
            or result.output_tokens is not None
        )
        if has_generation_record:
            add_usage(result.model_id, result.input_tokens, result.output_tokens)

        judge_was_attempted = result.judge_status in {"completed", "failed"}
        has_judge_usage = (
            result.judge_input_tokens is not None or result.judge_output_tokens is not None
        )
        if judge_was_attempted or has_judge_usage:
            add_usage(
                result.judge_model_id,
                result.judge_input_tokens,
                result.judge_output_tokens,
            )

    if not priced_model_ids:
        return (
            None,
            "unavailable",
            None,
            usage_gap_count or None,
            (),
        )
    basis: Literal["token_estimate", "partial_token_estimate"] = (
        "partial_token_estimate" if usage_gap_count else "token_estimate"
    )
    return (
        float(total),
        basis,
        _COST_ESTIMATE_PRICING_AS_OF,
        usage_gap_count,
        tuple(sorted(priced_model_ids)),
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _score_metrics(
    results: tuple[_RunResultSummary, ...] | list[_RunResultSummary],
    *,
    fallback_overall: dict[str, Any] | None = None,
) -> EvaluationScoreMetrics:
    fallback = fallback_overall or {}
    eligible = [result for result in results if result.observed_behavior != "failed"]
    behavior_results = [
        result
        for result in results
        if result.expected_behavior is not None and result.observed_behavior is not None
    ]
    retrieval_values = [
        result.retrieval_recall_at_k
        for result in results
        if result.retrieval_recall_at_k is not None
    ]
    citation_values = [
        result.citation_correctness
        for result in eligible
        if result.citation_correctness is not None
    ]
    citation_completeness_values = [
        result.citation_completeness
        for result in eligible
        if result.citation_completeness is not None
    ]
    groundedness_values = [
        result.groundedness for result in eligible if result.groundedness is not None
    ]
    relevance_values = [
        result.answer_relevance for result in eligible if result.answer_relevance is not None
    ]
    groundedness_distribution: tuple[int, int, int, int, int] | None = (
        (
            sum(value == 1 for value in groundedness_values),
            sum(value == 2 for value in groundedness_values),
            sum(value == 3 for value in groundedness_values),
            sum(value == 4 for value in groundedness_values),
            sum(value == 5 for value in groundedness_values),
        )
        if groundedness_values
        else None
    )
    expected_behavior_accuracy = (
        sum(result.expected_behavior == result.observed_behavior for result in behavior_results)
        / len(behavior_results)
        if behavior_results
        else _safe_metric(fallback.get("expected_behavior_accuracy"), maximum=1)
        if not results
        else None
    )

    def available_count(values: Sequence[object]) -> int | None:
        return len(values) if results else None

    def anchor_total(
        name: Literal[
            "retrieval_anchor_hits",
            "retrieval_anchor_count",
            "citation_anchor_matches",
            "citation_anchor_count",
        ],
    ) -> int | None:
        values = [getattr(result, name) for result in eligible if getattr(result, name) is not None]
        return sum(values) if values else None

    tool_count_available = any(result.validated_tool_result_count is not None for result in results)
    tool_output_count = (
        sum(
            result.validated_tool_result_count > 0
            for result in eligible
            if result.validated_tool_result_count is not None
        )
        if tool_count_available
        else None
    )
    return EvaluationScoreMetrics(
        expected_behavior_accuracy=expected_behavior_accuracy,
        expected_behavior_scored_count=(
            len(behavior_results) if results else _safe_count(fallback.get("scored_count"))
        ),
        retrieval_recall_at_k_scored_count=available_count(retrieval_values),
        retrieval_anchor_hits=anchor_total("retrieval_anchor_hits"),
        retrieval_anchor_count=anchor_total("retrieval_anchor_count"),
        citation_correctness_scored_count=available_count(citation_values),
        citation_completeness_mean=_mean(citation_completeness_values)
        if results
        else _safe_metric(fallback.get("citation_completeness_mean"), maximum=1),
        citation_completeness_scored_count=available_count(citation_completeness_values),
        citation_anchor_matches=anchor_total("citation_anchor_matches"),
        citation_anchor_count=anchor_total("citation_anchor_count"),
        groundedness_scored_count=available_count(groundedness_values),
        groundedness_score_distribution=groundedness_distribution,
        answer_relevance_scored_count=available_count(relevance_values),
        validated_tool_result_output_count=tool_output_count,
        latency_sample_count=sum(result.latency_ms is not None for result in results)
        if results
        else None,
        retrieval_recall_at_k_mean=_mean(retrieval_values)
        if results
        else _safe_metric(fallback.get("retrieval_recall_at_k_mean"), maximum=1),
        citation_correctness_mean=_mean(citation_values)
        if results
        else _safe_metric(fallback.get("citation_correctness_mean"), maximum=1),
        groundedness_mean=_mean(groundedness_values)
        if results
        else _safe_metric(fallback.get("groundedness_mean"), maximum=5),
        answer_relevance_mean=_mean(relevance_values)
        if results
        else _safe_metric(fallback.get("answer_relevance_mean"), maximum=5),
    )


def _condition_breakdowns(
    results: tuple[_RunResultSummary, ...],
) -> tuple[EvaluationConditionBreakdown, ...]:
    grouped: dict[str, list[_RunResultSummary]] = {}
    categories: dict[str, dict[str, list[_RunResultSummary]]] = {}
    for result in results:
        condition_id = (result.condition_id or "unspecified")[:200]
        category = (result.category or "unclassified")[:80]
        grouped.setdefault(condition_id, []).append(result)
        categories.setdefault(condition_id, {}).setdefault(category, []).append(result)
    summaries: list[EvaluationConditionBreakdown] = []
    for condition_id in sorted(grouped)[:100]:
        condition_results = grouped[condition_id]
        summaries.append(
            EvaluationConditionBreakdown(
                condition_id=condition_id,
                result_count=len(condition_results),
                failed_output_count=sum(
                    result.observed_behavior == "failed" for result in condition_results
                ),
                metrics=_score_metrics(condition_results),
                category_breakdowns=tuple(
                    EvaluationCategoryBreakdown(
                        category=category,
                        result_count=len(category_results),
                        failed_output_count=sum(
                            result.observed_behavior == "failed" for result in category_results
                        ),
                        metrics=_score_metrics(category_results),
                    )
                    for category, category_results in sorted(categories[condition_id].items())[:40]
                ),
            )
        )
    return tuple(summaries)


def _quantile(ordered: list[float], quantile: float) -> float:
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _split_conditions(
    results: tuple[_RunResultSummary, ...],
) -> tuple[list[_RunResultSummary], list[_RunResultSummary], list[_RunResultSummary]]:
    """Return (headline agent rows, baseline rows, retrieval rows); legacy runs use all rows."""
    retrieval = [r for r in results if (r.condition_id or "").startswith("retrieval:")]
    generation = [r for r in results if r not in retrieval]
    agent = [r for r in generation if (r.condition_id or "").endswith(":agent")]
    baseline = [r for r in generation if (r.condition_id or "").endswith(":non_agent")]
    if not agent:
        return generation or list(results), [], retrieval
    return agent, baseline, retrieval


def _baseline_comparison(
    record: _RunRecord, baseline_results: list[_RunResultSummary]
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if not baseline_results:
        return payload
    scored = [
        r
        for r in baseline_results
        if r.observed_behavior is not None and r.expected_behavior is not None
    ]
    payload["baseline_condition_id"] = baseline_results[0].condition_id
    payload["baseline_expected_behavior_scored_count"] = len(scored)
    if scored:
        payload["baseline_expected_behavior_accuracy"] = sum(
            r.expected_behavior == r.observed_behavior for r in scored
        ) / len(scored)
    pairs = record.metrics.get("paired_comparisons")
    pair = pairs[0] if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict) else None
    if pair is not None:
        interval = pair.get("difference_bootstrap_95")
        interval = interval if isinstance(interval, dict) else {}
        payload.update(
            {
                "paired_accuracy_difference": pair.get("accuracy_difference_a_minus_b"),
                "paired_accuracy_difference_lower_95": interval.get("lower_95"),
                "paired_accuracy_difference_upper_95": interval.get("upper_95"),
                "paired_mcnemar_p": pair.get("mcnemar_exact_p"),
                "paired_case_count": pair.get("paired_cases"),
            }
        )
    return payload


def _run_summary(record: _RunRecord) -> EvaluationRunSummary:
    split_value = record.configuration.get("split")
    split: Literal["all", "dev", "test"] = (
        split_value if split_value in {"all", "dev", "test"} else "all"
    )
    overall = record.metrics.get("overall", {})
    overall = overall if isinstance(overall, dict) else {}
    latency = overall.get("latency_ms", {})
    latency = latency if isinstance(latency, dict) else {}
    metric_row_count = overall.get("case_count", 0)
    metric_row_count = (
        metric_row_count if isinstance(metric_row_count, int) and metric_row_count >= 0 else 0
    )
    unique_case_ids = {result.case_id for result in record.results if result.case_id}
    case_count = len(unique_case_ids) if unique_case_ids else metric_row_count
    observed_results = [
        result
        for result in (_split_conditions(record.results)[0] if record.results else record.results)
        if result.observed_behavior is not None
    ]
    failed_results = [result for result in observed_results if result.observed_behavior == "failed"]
    behavior_results = [
        result for result in observed_results if result.expected_behavior is not None
    ]
    has_observed_results = bool(observed_results)
    failure_exclusion_applied = has_observed_results or (
        "scored_count" in overall and "failed_count" in overall
    )
    expected_behavior_scored_count = len(behavior_results)
    failed_output_count = len(failed_results)
    if not has_observed_results and failure_exclusion_applied:
        expected_behavior_scored_count = _safe_count(overall.get("scored_count"))
        failed_output_count = _safe_count(overall.get("failed_count"))
    headline_results, baseline_results, retrieval_results = _split_conditions(record.results)
    metrics_payload_headline = (
        headline_results[0].condition_id if headline_results and baseline_results else None
    )
    score_metrics = _score_metrics(
        headline_results if record.results else record.results, fallback_overall=overall
    )
    metrics_payload = score_metrics.model_dump()
    if retrieval_results:
        retrieval_metrics = _score_metrics(retrieval_results)
        for name in (
            "retrieval_recall_at_k_mean",
            "retrieval_recall_at_k_scored_count",
            "retrieval_anchor_hits",
            "retrieval_anchor_count",
        ):
            metrics_payload[name] = getattr(retrieval_metrics, name)
    latencies = sorted(
        result.latency_ms for result in headline_results if result.latency_ms is not None
    )
    if latencies:
        latency = {
            "p50": _quantile(latencies, 0.5),
            "p95": _quantile(latencies, 0.95),
        }
        metrics_payload["latency_sample_count"] = len(latencies)
    metrics_payload["headline_condition_id"] = metrics_payload_headline
    metrics_payload.update(_baseline_comparison(record, baseline_results))
    cost, cost_basis, cost_pricing_as_of, cost_usage_gap_count, cost_model_ids = _cost_summary(
        record.results, overall
    )
    metrics_payload.update(
        {
            "expected_behavior_scored_count": (
                expected_behavior_scored_count
                if has_observed_results
                else score_metrics.expected_behavior_scored_count
            ),
            "failed_output_count": failed_output_count,
            "failure_exclusion_applied": failure_exclusion_applied,
            "latency_p50_ms": _safe_metric(latency.get("p50")),
            "latency_p95_ms": _safe_metric(latency.get("p95")),
            "estimated_cost_usd_total": cost,
            "estimated_cost_basis": cost_basis,
            "estimated_cost_pricing_as_of": cost_pricing_as_of,
            "estimated_cost_usage_gap_count": cost_usage_gap_count,
            "estimated_cost_model_ids": cost_model_ids,
        }
    )
    raw_limitations = record.metrics.get("limitations", ())
    limitations = (
        tuple(
            item[:1000] for item in raw_limitations[:50] if isinstance(item, str) and item.strip()
        )
        if isinstance(raw_limitations, (list, tuple))
        else ()
    )
    if failed_output_count and not failure_exclusion_applied:
        limitations = (
            *limitations,
            "Legacy scores may include failed generation outputs; rerun to apply "
            "failure-excluded scoring.",
        )
    elif failed_output_count and "scored_count" not in overall and has_observed_results:
        limitations = (
            *limitations,
            "Expected-behavior accuracy counts failed outputs as incorrect; failed outputs are "
            "excluded only from answer-quality metrics. Original run provenance and status are "
            "unchanged.",
        )
    judge_configuration = record.configuration.get("ai_judge", {})
    judge_configuration = judge_configuration if isinstance(judge_configuration, dict) else {}
    judge_metrics = overall.get("ai_judge", {})
    judge_metrics = judge_metrics if isinstance(judge_metrics, dict) else {}
    raw_model_ids = judge_metrics.get("model_ids", ())
    configuration_model_ids = judge_configuration.get("model_ids", ())
    judge_model_ids = tuple(
        sorted(
            {
                item[:300]
                for values in (raw_model_ids, configuration_model_ids)
                if isinstance(values, (list, tuple))
                for item in values
                if isinstance(item, str) and item.strip()
            }
        )
    )[:10]
    raw_rubric_version = judge_configuration.get("rubric_version")
    judge_result_counts = {
        status: sum(result.judge_status == status for result in record.results)
        for status in ("completed", "failed", "skipped")
    }
    has_judge_results = any(judge_result_counts.values())
    ineligible_output_count = sum(
        result.observed_behavior == "failed" and result.judge_status in {"completed", "failed"}
        for result in record.results
    )
    eligible_judge_scored_count = max(
        0,
        judge_result_counts["completed"]
        - sum(
            result.observed_behavior == "failed" and result.judge_status == "completed"
            for result in record.results
        ),
    )
    return EvaluationRunSummary(
        run_id=record.run_id,
        status=record.status,
        started_at=record.started_at,
        finished_at=record.finished_at,
        split=split,
        case_count=case_count,
        live_requests_made=record.live_requests_made,
        metrics=EvaluationMetricsSummary(**metrics_payload),
        condition_breakdowns=_condition_breakdowns(record.results),
        ai_judge=EvaluationJudgeSummary(
            enabled=judge_configuration.get("enabled") is True,
            rubric_version=(
                raw_rubric_version[:100]
                if isinstance(raw_rubric_version, str) and raw_rubric_version.strip()
                else None
            ),
            model_ids=judge_model_ids,
            same_model_as_generator=(
                judge_metrics.get("same_model_as_generator")
                if isinstance(judge_metrics.get("same_model_as_generator"), bool)
                else None
            ),
            attempted_count=(
                judge_result_counts["completed"] + judge_result_counts["failed"]
                if has_judge_results
                else _safe_count(judge_metrics.get("attempted_count"))
            ),
            scored_count=(
                eligible_judge_scored_count
                if has_judge_results
                else _safe_count(judge_metrics.get("scored_count"))
            ),
            failed_count=(
                judge_result_counts["failed"]
                if has_judge_results
                else _safe_count(judge_metrics.get("failed_count"))
            ),
            skipped_count=(
                judge_result_counts["skipped"]
                if has_judge_results
                else _safe_count(judge_metrics.get("skipped_count"))
            ),
            ineligible_output_count=(
                ineligible_output_count
                if has_judge_results
                else _safe_count(judge_metrics.get("ineligible_output_count"))
            ),
        ),
        limitations=limitations,
    )


def _case_set_summary(path: Path) -> EvaluationCaseSetSummary:
    if not path.exists():
        return EvaluationCaseSetSummary(
            case_count=0,
            approved_case_count=0,
            category_count=0,
            category_counts={},
            split_counts={"dev": 0, "test": 0},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        case_set = _CaseSetManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise EvaluationSummaryUnavailable("Evaluation case coverage is unavailable.") from error
    return EvaluationCaseSetSummary(
        case_count=len(case_set.cases),
        approved_case_count=sum(case.review_status == "approved" for case in case_set.cases),
        category_count=len({case.category for case in case_set.cases}),
        category_counts={
            category: sum(case.category == category for case in case_set.cases)
            for category in sorted({case.category for case in case_set.cases})
        },
        split_counts={
            "dev": sum(case.split == "dev" for case in case_set.cases),
            "test": sum(case.split == "test" for case in case_set.cases),
        },
        cases=tuple(
            EvaluationCaseView(
                case_id=case.case_id,
                category=case.category,
                question=case.question,
                expected_behavior=case.expected_behavior,
                difficulty=case.difficulty,
                split=case.split,
                review_status=case.review_status,
                reference_claims=case.reference_claims,
                required_tools=case.required_tools,
                forbidden_behaviors=case.forbidden_behaviors,
                expected_sources=tuple(
                    sorted(
                        {
                            str(anchor["source_id"])
                            for anchor in case.expected_anchors
                            if "source_id" in anchor
                        }
                    )
                ),
            )
            for case in case_set.cases
        ),
    )


def build_evaluation_summary(
    *,
    case_set_path: Path | None = None,
    run_manifest_path: Path | None = None,
    review_manifest_path: Path | None = None,
    error_manifest_path: Path | None = None,
) -> EvaluationSummaryResponse:
    case_set_path = case_set_path or DEFAULT_CASE_SET_PATH
    run_manifest_path = run_manifest_path or DEFAULT_RUN_MANIFEST
    review_manifest_path = review_manifest_path or DEFAULT_REVIEW_MANIFEST
    error_manifest_path = error_manifest_path or DEFAULT_ERROR_MANIFEST
    runs = _load_run_records(run_manifest_path)
    try:
        reviews = tuple(
            _ReviewRecord.model_validate(item)
            for item in _load_manifest_records(review_manifest_path, "reviews")
        )
        errors = tuple(
            _ErrorRecord.model_validate(item)
            for item in _load_manifest_records(error_manifest_path, "errors")
        )
    except ValidationError as error:
        raise EvaluationSummaryUnavailable("Evaluation review data is unavailable.") from error
    reviewed_case_count = len({record.case_id for record in reviews})
    error_record_count = len(errors)
    return EvaluationSummaryResponse(
        status="available" if runs else "empty",
        case_set=_case_set_summary(case_set_path),
        runs=tuple(_run_summary(record) for record in runs),
        reviewed_case_count=reviewed_case_count,
        error_record_count=error_record_count,
    )


@router.get("/summary", response_model=EvaluationSummaryResponse)
async def evaluation_summary_endpoint() -> EvaluationSummaryResponse | JSONResponse:
    try:
        return build_evaluation_summary()
    except EvaluationSummaryUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "schema_version": "1.0",
                "error_code": "EVALUATION_SUMMARY_UNAVAILABLE",
                "message": "Evaluation summary is unavailable.",
            },
        )
