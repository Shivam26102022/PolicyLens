from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from policylens.retrieval.models import StrictModel
from policylens.settings import PROJECT_ROOT
from scripts.evaluation_case_set import REQUIRED_CASE_CATEGORIES, EvaluationCaseSet
from scripts.evaluation_errors import redact_error_text
from scripts.evaluation_registry import EvaluationRegistryError, append_manifest_record

RATING_FIELDS = (
    "groundedness",
    "answer_relevance",
    "citation_correctness",
    "citation_completeness",
)
DEFAULT_REVIEW_MANIFEST = PROJECT_ROOT / "data/manifests/evaluation-review-manifest.json"


class EvaluationReviewError(ValueError):
    """The evaluation review manifest is invalid or unsafe to update."""


class EvaluationReviewRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    review_id: str = Field(min_length=1, max_length=300)
    run_id: UUID
    case_id: str = Field(min_length=1, max_length=100)
    reviewer_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,49}$")
    rubric_version: str = Field(min_length=1, max_length=100)
    reviewed_at: datetime
    groundedness: int = Field(ge=1, le=5)
    answer_relevance: int = Field(ge=1, le=5)
    citation_correctness: int = Field(ge=1, le=5)
    citation_completeness: int = Field(ge=1, le=5)
    expected_behavior_correct: bool
    safety_compliant: bool
    notes: str = Field(default="", max_length=2000)

    @field_validator("notes", mode="before")
    @classmethod
    def redact_notes(cls, value: object) -> object:
        return redact_error_text(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_review_identity(self) -> EvaluationReviewRecord:
        expected_id = f"{self.run_id}:{self.case_id}:{self.reviewer_id}"
        if self.review_id != expected_id:
            raise ValueError("review_id must uniquely identify run, case, and reviewer")
        return self


def append_review_record(
    record: EvaluationReviewRecord,
    *,
    manifest_path: Path = DEFAULT_REVIEW_MANIFEST,
) -> None:
    try:
        append_manifest_record(
            record.model_dump(mode="json"),
            manifest_path=manifest_path,
            collection="reviews",
            record_validator=EvaluationReviewRecord.model_validate,
        )
    except EvaluationRegistryError as error:
        raise EvaluationReviewError("Evaluation review manifest is invalid") from error


def load_review_records(
    manifest_path: Path = DEFAULT_REVIEW_MANIFEST,
) -> tuple[EvaluationReviewRecord, ...]:
    if not manifest_path.exists():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationReviewError("Evaluation review manifest is invalid JSON") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or not isinstance(manifest.get("reviews"), list)
    ):
        raise EvaluationReviewError("Evaluation review manifest has an invalid shape")
    try:
        return tuple(EvaluationReviewRecord.model_validate(item) for item in manifest["reviews"])
    except ValueError as error:
        raise EvaluationReviewError("Evaluation review record is invalid") from error


def review_category_coverage(
    case_set: EvaluationCaseSet,
    reviews: tuple[EvaluationReviewRecord, ...],
) -> dict[str, Any]:
    cases_by_id = {case.case_id: case for case in case_set.cases}
    unknown_case_ids = sorted({review.case_id for review in reviews} - set(cases_by_id))
    if unknown_case_ids:
        raise ValueError("reviews reference unknown cases: " + ", ".join(unknown_case_ids))
    reviewed_cases = {review.case_id for review in reviews}
    categories_with_reviews = {cases_by_id[case_id].category for case_id in reviewed_cases}
    return {
        "reviewed_case_count": len(reviewed_cases),
        "total_case_count": len(case_set.cases),
        "category_counts": {
            category: sum(
                case_id in reviewed_cases
                for case_id, case in cases_by_id.items()
                if case.category == category
            )
            for category in sorted({case.category for case in case_set.cases})
        },
        "missing_categories": tuple(sorted(REQUIRED_CASE_CATEGORIES - categories_with_reviews)),
    }


def reviewer_agreement(
    reviews: tuple[EvaluationReviewRecord, ...],
) -> dict[str, Any]:
    by_case: dict[str, list[EvaluationReviewRecord]] = defaultdict(list)
    for review in reviews:
        by_case[review.case_id].append(review)

    dimensions = (*RATING_FIELDS, "expected_behavior_correct", "safety_compliant")
    agreements: dict[str, list[bool]] = {field: [] for field in dimensions}
    reviewed_pairs = 0
    for case_reviews in by_case.values():
        distinct_reviewers = {review.reviewer_id for review in case_reviews}
        if len(distinct_reviewers) != len(case_reviews):
            raise ValueError("a reviewer may submit only one review per case")
        for left, right in combinations(case_reviews, 2):
            reviewed_pairs += 1
            for field in agreements:
                agreements[field].append(getattr(left, field) == getattr(right, field))

    per_field = {
        field: sum(values) / len(values) if values else None for field, values in agreements.items()
    }
    all_pairwise = [value for values in agreements.values() for value in values]
    return {
        "reviewed_case_count": sum(len(items) >= 2 for items in by_case.values()),
        "reviewer_pair_count": reviewed_pairs,
        "exact_agreement": sum(all_pairwise) / len(all_pairwise) if all_pairwise else None,
        "by_field": per_field,
    }


def summarize_output_reviews(
    reviews: tuple[EvaluationReviewRecord, ...],
) -> dict[str, Any]:
    review_count = len(reviews)
    return {
        "review_record_count": review_count,
        "reviewed_case_count": len({review.case_id for review in reviews}),
        "reviewer_count": len({review.reviewer_id for review in reviews}),
        "ai_assisted_record_count": sum(
            "ai-assisted" in review.notes.casefold()
            or "reviewer-ai-" in review.reviewer_id.casefold()
            for review in reviews
        ),
        "mean_scores": {
            field: (
                sum(getattr(review, field) for review in reviews) / review_count
                if review_count
                else None
            )
            for field in RATING_FIELDS
        },
        "expected_behavior_accuracy": (
            sum(review.expected_behavior_correct for review in reviews) / review_count
            if review_count
            else None
        ),
        "safety_compliance_rate": (
            sum(review.safety_compliant for review in reviews) / review_count
            if review_count
            else None
        ),
    }
