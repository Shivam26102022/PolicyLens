from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from scripts.evaluation_case_set import EvaluationCaseSet
from scripts.evaluation_review import (
    EvaluationReviewError,
    EvaluationReviewRecord,
    append_review_record,
    load_review_records,
    review_category_coverage,
    reviewer_agreement,
    summarize_output_reviews,
)

ROOT = Path(__file__).resolve().parents[2]
ROOT_CASES = ROOT / "data/evaluation/feature007-cases.json"
REVIEW_SCHEMA = ROOT / "specs/007-evaluation/contracts/evaluation-review.schema.json"


def _review(case_id: str, reviewer_id: str, *, score: int = 4) -> EvaluationReviewRecord:
    run_id = uuid4()
    return EvaluationReviewRecord(
        review_id=f"{run_id}:{case_id}:{reviewer_id}",
        run_id=run_id,
        case_id=case_id,
        reviewer_id=reviewer_id,
        rubric_version="feature007-review-v1",
        reviewed_at=datetime(2026, 10, 26, tzinfo=UTC),
        groundedness=score,
        answer_relevance=score,
        citation_correctness=score,
        citation_completeness=score,
        expected_behavior_correct=True,
        safety_compliant=True,
        notes="Reviewed source; OPENAI_API_KEY=sk-test-secret-value",
    )


def test_human_review_record_requires_pseudonymous_reviewer_and_bounded_scores() -> None:
    review = _review("factual-india-youth-2025", "reviewer-a")
    schema = json.loads(REVIEW_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        review.model_dump(mode="json")
    )
    assert "sk-test-secret-value" not in review.notes
    with pytest.raises(ValidationError):
        _review("factual-india-youth-2025", "reviewer@example.com")
    with pytest.raises(ValidationError):
        EvaluationReviewRecord(**{**review.model_dump(), "groundedness": 6})


def test_reviewer_agreement_is_pairwise_and_discloses_sample_count() -> None:
    reviews = (
        _review("case-1", "reviewer-a", score=4),
        _review("case-1", "reviewer-b", score=4),
        _review("case-2", "reviewer-a", score=5),
        _review("case-2", "reviewer-b", score=3),
    )

    agreement = reviewer_agreement(reviews)

    assert agreement["reviewed_case_count"] == 2
    assert agreement["reviewer_pair_count"] == 2
    assert agreement["exact_agreement"] == 2 / 3


def test_output_review_summary_reports_ratings_and_ai_assistance() -> None:
    reviews = (
        _review("case-1", "reviewer-ai-copilot", score=3),
        _review("case-2", "reviewer-human", score=5),
    )

    summary = summarize_output_reviews(reviews)

    assert summary["review_record_count"] == 2
    assert summary["reviewed_case_count"] == 2
    assert summary["reviewer_count"] == 2
    assert summary["ai_assisted_record_count"] == 1
    assert summary["mean_scores"]["groundedness"] == 4
    assert summary["expected_behavior_accuracy"] == 1
    assert summary["safety_compliance_rate"] == 1


def test_output_review_coverage_does_not_change_case_approval() -> None:
    case_set = EvaluationCaseSet.load(ROOT_CASES)
    statuses_before = tuple(
        (case.review_status, case.reviewer_ids, case.reviewed_at) for case in case_set.cases
    )
    reviews = (
        _review("factual-india-youth-2025", "reviewer-a"),
        _review("factual-india-youth-2025", "reviewer-b"),
    )

    coverage = review_category_coverage(case_set, reviews)

    assert coverage["reviewed_case_count"] == 1
    assert coverage["missing_categories"]
    assert (
        tuple((case.review_status, case.reviewer_ids, case.reviewed_at) for case in case_set.cases)
        == statuses_before
    )


def test_review_coverage_rejects_unknown_case_ids() -> None:
    case_set = EvaluationCaseSet.load(ROOT_CASES)

    with pytest.raises(ValueError, match="unknown cases"):
        review_category_coverage(case_set, (_review("not-a-case", "reviewer-a"),))


def test_review_manifest_appends_output_reviews_without_changing_case_approval(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "review-manifest.json"
    review = _review("factual-india-youth-2025", "reviewer-a")

    append_review_record(review, manifest_path=manifest)
    loaded = load_review_records(manifest)

    assert loaded == (review,)
    case_set = EvaluationCaseSet.load(ROOT_CASES)
    assert {case.review_status for case in case_set.cases} == {"approved"}
    assert {case.reviewer_ids for case in case_set.cases} <= {("reviewer-user",), ("ai-assistant",)}
    with pytest.raises(EvaluationReviewError):
        append_review_record(review, manifest_path=manifest)
