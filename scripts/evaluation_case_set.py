from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from policylens.agent_runtime.models import AgentAnswerRequest
from policylens.retrieval.evaluation import EvidenceAnchor
from policylens.retrieval.models import RetrievalFilters, RetrievalMode, StrictModel
from policylens.settings import PROJECT_ROOT

MIN_APPROVED_CASES = 30
REQUIRED_CASE_CATEGORIES = frozenset(
    {
        "factual",
        "multi_source_synthesis",
        "structured_unstructured_synthesis",
        "deterministic_calculation",
        "multi_step_tool",
        "ambiguity",
        "unanswerable",
        "out_of_scope",
        "conflicting_evidence",
        "stale_time_sensitive",
        "user_prompt_injection",
        "retrieved_document_injection",
        "mcp_output_injection",
        "invalid_mcp_arguments",
        "mcp_timeout_unavailable",
        "malformed_tool_response",
        "sensitive_data_request",
        "unauthorized_source_request",
        "adversarial_citation",
        "local_model_tool_call_failure",
    }
)

ExpectedBehavior = Literal["answer", "clarify", "abstain", "conflict", "block"]
Difficulty = Literal["easy", "medium", "hard"]
EvaluationSplit = Literal["dev", "test"]
ReviewStatus = Literal["candidate", "in_review", "approved", "rejected"]
NON_HUMAN_REVIEWER_IDS = frozenset({"ai-assistant", "automated", "system", "bot"})
DEFAULT_CASE_SET_PATH = PROJECT_ROOT / "data/evaluation/feature007-cases.json"


class EvaluationCaseSetError(ValueError):
    """The frozen evaluation case set is missing or invalid."""


class RelevanceGrade(StrictModel):
    anchor: EvidenceAnchor
    grade: int = Field(ge=0, le=3)


class EvaluationCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=2000)
    mode: RetrievalMode
    top_k: int = Field(ge=1, le=20)
    filters: RetrievalFilters
    expected_behavior: ExpectedBehavior
    relevant_passage_ids: tuple[str, ...] = Field(max_length=50)
    expected_anchors: tuple[EvidenceAnchor, ...] = Field(max_length=20)
    relevance_grades: tuple[RelevanceGrade, ...] = Field(max_length=50)
    reference_claims: tuple[str, ...] = Field(max_length=20)
    required_tools: tuple[Literal["query_statistics"], ...] = Field(max_length=10)
    forbidden_behaviors: tuple[str, ...] = Field(max_length=20)
    adversarial_fixture: str | None = Field(default=None, max_length=2000)
    difficulty: Difficulty
    split: EvaluationSplit
    review_status: ReviewStatus
    reviewer_ids: tuple[str, ...] = Field(default=(), max_length=5)
    reviewed_at: datetime | None = None
    lineage: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_review_and_relevance(self) -> EvaluationCase:
        if len(self.reviewer_ids) != len(set(self.reviewer_ids)):
            raise ValueError("reviewer_ids must be unique")
        if self.review_status == "approved" and (not self.reviewer_ids or self.reviewed_at is None):
            raise ValueError("approved cases require reviewer IDs and reviewed_at")
        if self.review_status == "approved" and any(
            reviewer_id.casefold() in NON_HUMAN_REVIEWER_IDS for reviewer_id in self.reviewer_ids
        ):
            raise ValueError("approved cases require human reviewer IDs")
        anchor_ids = {
            json.dumps(anchor.model_dump(mode="json", exclude_none=True), sort_keys=True)
            for anchor in self.expected_anchors
        }
        if len(anchor_ids) != len(self.expected_anchors):
            raise ValueError("expected evidence anchors must be unique")
        grade_anchor_ids = [
            json.dumps(item.anchor.model_dump(mode="json", exclude_none=True), sort_keys=True)
            for item in self.relevance_grades
        ]
        if len(grade_anchor_ids) != len(set(grade_anchor_ids)):
            raise ValueError("relevance grades must have unique anchors")
        if not set(grade_anchor_ids).issubset(anchor_ids):
            raise ValueError("relevance grades must reference expected evidence anchors")
        if len(self.relevant_passage_ids) != len(set(self.relevant_passage_ids)):
            raise ValueError("relevant_passage_ids must be unique")
        return self

    def to_request(self) -> AgentAnswerRequest:
        return AgentAnswerRequest(
            query=self.question,
            mode=self.mode,
            top_k=self.top_k,
            filters=self.filters,
        )


class EvaluationCaseSet(StrictModel):
    schema_version: Literal["1.0"]
    set_id: str = Field(min_length=1, max_length=100)
    lineage: str = Field(min_length=1, max_length=2000)
    runtime_label_access: Literal["prohibited"]
    cases: tuple[EvaluationCase, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> EvaluationCaseSet:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")
        return self

    @classmethod
    def load(cls, path: Path) -> EvaluationCaseSet:
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise EvaluationCaseSetError("Evaluation case set is missing or invalid") from error


def release_gate_issues(case_set: EvaluationCaseSet) -> tuple[str, ...]:
    approved_cases = [case for case in case_set.cases if case.review_status == "approved"]
    issues: list[str] = []
    if len(approved_cases) < MIN_APPROVED_CASES:
        issues.append(
            f"release evaluation requires at least {MIN_APPROVED_CASES} approved cases; "
            f"found {len(approved_cases)}"
        )

    splits = {case.split for case in approved_cases}
    if splits != {"dev", "test"}:
        issues.append("approved cases must include both dev and test splits")

    categories = {case.category for case in approved_cases}
    missing_categories = sorted(REQUIRED_CASE_CATEGORIES - categories)
    if missing_categories:
        issues.append("approved cases missing categories: " + ", ".join(missing_categories))

    seen_requests: set[tuple[str, str, int, str, str]] = set()
    for case in case_set.cases:
        normalized_question = " ".join(case.question.casefold().split())
        normalized_filters = json.dumps(
            case.filters.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        normalized_fixture = " ".join((case.adversarial_fixture or "").casefold().split())
        fingerprint = (
            normalized_question,
            case.mode,
            case.top_k,
            normalized_filters,
            normalized_fixture,
        )
        if fingerprint in seen_requests:
            issues.append(f"duplicate runtime request found for case {case.case_id}")
        seen_requests.add(fingerprint)
    issues.extend(
        f"possible semantic duplicate: {left_id} and {right_id} (token Jaccard {score:.2f})"
        for left_id, right_id, score in find_possible_duplicate_pairs(case_set)
    )
    return tuple(issues)


def find_possible_duplicate_pairs(
    case_set: EvaluationCaseSet,
    *,
    minimum_similarity: float = 0.75,
) -> tuple[tuple[str, str, float], ...]:
    if not 0 < minimum_similarity <= 1:
        raise ValueError("minimum_similarity must be in (0, 1]")
    duplicate_pairs: list[tuple[str, str, float]] = []
    for index, left in enumerate(case_set.cases):
        left_tokens = set(re.findall(r"[a-z0-9]+", left.question.casefold()))
        if not left_tokens:
            continue
        left_sources = {anchor.source_id for anchor in left.expected_anchors}
        left_filters = json.dumps(
            left.filters.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        for right in case_set.cases[index + 1 :]:
            if left.question.casefold().strip() == right.question.casefold().strip():
                continue
            right_filters = json.dumps(
                right.filters.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )
            if left_filters != right_filters:
                continue
            right_sources = {anchor.source_id for anchor in right.expected_anchors}
            if left_sources and right_sources and not (left_sources & right_sources):
                continue
            if left.category != right.category:
                continue
            right_tokens = set(re.findall(r"[a-z0-9]+", right.question.casefold()))
            if not right_tokens:
                continue
            union = left_tokens | right_tokens
            similarity = len(left_tokens & right_tokens) / len(union)
            if similarity >= minimum_similarity:
                duplicate_pairs.append((left.case_id, right.case_id, similarity))
    return tuple(duplicate_pairs)


def validate_case_anchors(
    case_set: EvaluationCaseSet,
    *,
    project_root: Path = PROJECT_ROOT,
) -> tuple[str, ...]:
    import yaml

    root = project_root.resolve()
    try:
        manifest = yaml.safe_load(
            (root / "data/manifests/sources.yaml").read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as error:
        raise EvaluationCaseSetError("Source manifest is missing or invalid") from error

    source_records = manifest.get("sources") if isinstance(manifest, dict) else None
    if not isinstance(source_records, list):
        raise EvaluationCaseSetError("Source manifest has no source records")
    sources = {
        record.get("source_id"): record
        for record in source_records
        if isinstance(record, dict) and isinstance(record.get("source_id"), str)
    }

    issues: list[str] = []
    for case in case_set.cases:
        for anchor in case.expected_anchors:
            source = sources.get(anchor.source_id)
            if source is None:
                issues.append(f"{case.case_id}: unknown source {anchor.source_id}")
                continue
            allowed_usage = source.get("allowed_usage")
            if (
                source.get("license_review_status") != "verified"
                or not isinstance(allowed_usage, (list, tuple))
                or "evaluation" not in allowed_usage
            ):
                issues.append(
                    f"{case.case_id}: source {anchor.source_id} is not cleared for evaluation"
                )
                continue

            if anchor.row_key is not None:
                matches = False
                structured_root = root / "data/canonical/structured" / anchor.source_id
                for path in structured_root.rglob("*.json"):
                    try:
                        dataset = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if dataset.get("dataset_id") != anchor.row_key.dataset_id:
                        continue
                    observations = dataset.get("observations", ())
                    if any(
                        isinstance(item, dict)
                        and item.get("observation_id") == anchor.row_key.observation_id
                        for item in observations
                    ):
                        matches = True
                        break
                if not matches:
                    issues.append(
                        f"{case.case_id}: row anchor not found for source {anchor.source_id}"
                    )
                continue

            report_root = root / "data/canonical/reports" / anchor.source_id
            source_hash = source.get("sha256")
            document: dict[str, object] | None = None
            for path in report_root.rglob("*.json"):
                try:
                    candidate = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if candidate.get("content_sha256") == source_hash:
                    document = candidate
                    break
            pages = document.get("pages") if document else None
            page = None
            if isinstance(pages, list):
                page = next(
                    (
                        item
                        for item in pages
                        if isinstance(item, dict) and item.get("page_number") == anchor.page_number
                    ),
                    None,
                )
            if page is None:
                issues.append(
                    f"{case.case_id}: page anchor not found for source {anchor.source_id}"
                )
                continue
            marker = " ".join((anchor.marker or "").casefold().split())
            blocks = page.get("blocks")
            if not isinstance(blocks, list):
                issues.append(f"{case.case_id}: page blocks missing for source {anchor.source_id}")
                continue
            texts = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
                table_rows = block.get("table_rows")
                if isinstance(table_rows, list):
                    texts.extend(
                        cell
                        for row in table_rows
                        if isinstance(row, list)
                        for cell in row
                        if isinstance(cell, str)
                    )
            page_text = " ".join(" ".join(text.casefold().split()) for text in texts)
            if marker not in page_text:
                issues.append(
                    f"{case.case_id}: page marker not found for source {anchor.source_id}"
                )

    return tuple(issues)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Feature 007 case set offline.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASE_SET_PATH)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate cases and source anchors without provider calls.",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Fail unless at least 30 cases are human-approved across both splits.",
    )
    arguments = parser.parse_args(argv)

    try:
        case_set = EvaluationCaseSet.load(arguments.cases)
    except EvaluationCaseSetError:
        print(json.dumps({"status": "invalid", "case_set": str(arguments.cases)}))
        return 2

    anchor_issues = validate_case_anchors(case_set)
    release_issues = release_gate_issues(case_set)
    review_status_counts = {
        status: sum(case.review_status == status for case in case_set.cases)
        for status in ("candidate", "in_review", "approved", "rejected")
    }
    blocked = bool(anchor_issues) or (arguments.release and bool(release_issues))
    record = {
        "status": "blocked" if blocked else "valid",
        "case_set_id": case_set.set_id,
        "case_count": len(case_set.cases),
        "category_count": len({case.category for case in case_set.cases}),
        "review_status_counts": review_status_counts,
        "anchor_issues": anchor_issues,
        "possible_duplicate_pairs": find_possible_duplicate_pairs(case_set),
        "release_gate_issues": release_issues,
        "release_eligible": not release_issues,
        "live_requests_made": False,
    }
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
