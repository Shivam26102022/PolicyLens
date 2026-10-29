from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from policylens.retrieval.evaluation import EvidenceAnchor
from policylens.retrieval.models import RetrievalFilters
from scripts.evaluation_case_set import (
    REQUIRED_CASE_CATEGORIES,
    EvaluationCase,
    EvaluationCaseSet,
    EvaluationCaseSetError,
    EvaluationSplit,
    RelevanceGrade,
    ReviewStatus,
    find_possible_duplicate_pairs,
    main,
    release_gate_issues,
    validate_case_anchors,
)

ROOT = Path(__file__).resolve().parents[2]

requires_canonical_data = pytest.mark.skipif(
    not (ROOT / "data/canonical/structured").exists(),
    reason="needs git-ignored canonical data; run make data-fetch data-parse",
)
CASE_SCHEMA = ROOT / "specs/007-evaluation/contracts/evaluation-case-set.schema.json"


def _case(
    index: int,
    *,
    category: str | None = None,
    split: EvaluationSplit | None = None,
    review_status: ReviewStatus = "approved",
    question: str | None = None,
    adversarial_fixture: str | None = None,
) -> EvaluationCase:
    expected_anchor = EvidenceAnchor(
        source_id="test-report",
        page_number=1,
        marker=f"anchor-{index}",
    )
    return EvaluationCase(
        case_id=f"eval-{index:03d}",
        category=category
        or sorted(REQUIRED_CASE_CATEGORIES)[index % len(REQUIRED_CASE_CATEGORIES)],
        question=question or f"Evaluation question {index}?",
        mode="hybrid",
        top_k=5,
        filters=RetrievalFilters(),
        expected_behavior="answer",
        relevant_passage_ids=(f"passage-{index}",),
        expected_anchors=(expected_anchor,),
        relevance_grades=(RelevanceGrade(anchor=expected_anchor, grade=3),),
        reference_claims=(f"Reference claim {index}.",),
        required_tools=(),
        forbidden_behaviors=("fabricated citation",),
        adversarial_fixture=adversarial_fixture,
        difficulty="easy",
        split=split or ("dev" if index % 2 == 0 else "test"),
        review_status=review_status,
        reviewer_ids=("reviewer-a", "reviewer-b") if review_status == "approved" else (),
        reviewed_at=(datetime(2026, 10, 26, tzinfo=UTC) if review_status == "approved" else None),
        lineage="synthetic test fixture",
    )


def _case_set(cases: tuple[EvaluationCase, ...]) -> EvaluationCaseSet:
    return EvaluationCaseSet(
        schema_version="1.0",
        set_id="feature007-test-set",
        lineage="synthetic test fixture",
        runtime_label_access="prohibited",
        cases=cases,
    )


def test_runtime_request_excludes_evaluation_labels() -> None:
    case = _case(0, adversarial_fixture="Synthetic retrieved instruction fixture.")

    request = case.to_request().model_dump(mode="json")

    assert set(request) == {
        "schema_version",
        "query",
        "mode",
        "top_k",
        "filters",
        "provider",
        "allow_external_provider",
        "allow_external_embeddings",
        "reasoning_effort",
        "session_id",
        "conversation",
    }
    assert request["schema_version"] == "1.0"
    assert request["query"] == case.question
    assert request["mode"] == "hybrid"
    assert request["top_k"] == 5
    assert request["provider"] is None
    assert request["allow_external_provider"] is False
    assert request["allow_external_embeddings"] is False
    assert request["reasoning_effort"] == "none"
    assert request["session_id"] is None
    assert request["conversation"] == []
    assert request["filters"] == {
        "source_ids": [],
        "country_iso3": [],
        "years": [],
        "indicator_ids": [],
    }
    assert "expected_behavior" not in request
    assert "reference_claims" not in request
    assert "split" not in request
    assert "review_status" not in request
    assert "adversarial_fixture" not in request


def test_approved_case_requires_actual_review_record() -> None:
    with pytest.raises(ValidationError, match="reviewer IDs and reviewed_at"):
        EvaluationCase(
            **{
                **_case(0).model_dump(),
                "reviewer_ids": (),
                "reviewed_at": None,
            }
        )


def test_approved_case_rejects_automated_reviewer_identity() -> None:
    with pytest.raises(ValidationError, match="human reviewer IDs"):
        EvaluationCase(
            **{
                **_case(0).model_dump(),
                "reviewer_ids": ("ai-assistant",),
            }
        )


def test_release_gate_requires_30_approved_cases_and_category_split_coverage() -> None:
    candidates = _case_set(tuple(_case(index, review_status="candidate") for index in range(30)))
    candidate_issues = release_gate_issues(candidates)
    assert any("found 0" in issue for issue in candidate_issues)

    too_small = _case_set(tuple(_case(index) for index in range(29)))
    issues = release_gate_issues(too_small)
    assert any("at least 30 approved cases" in issue for issue in issues)

    incomplete = _case_set(
        tuple(_case(index, category="factual", split="dev") for index in range(30))
    )
    issues = release_gate_issues(incomplete)
    assert any("both dev and test splits" in issue for issue in issues)
    assert any("approved cases missing categories" in issue for issue in issues)


def test_release_gate_accepts_30_reviewed_cases_with_required_coverage() -> None:
    case_set = _case_set(tuple(_case(index) for index in range(30)))
    issues = release_gate_issues(case_set)

    assert issues == ()


def test_case_set_rejects_duplicate_ids_and_duplicate_runtime_requests() -> None:
    case = _case(0)
    with pytest.raises(ValidationError, match="case IDs must be unique"):
        _case_set((case, case))

    duplicate_request = _case(1, question=case.question)
    issues = release_gate_issues(_case_set((case, duplicate_request)))
    assert any("duplicate runtime request" in issue for issue in issues)

    fixture_variant = _case(
        2,
        question=case.question,
        adversarial_fixture="synthetic malformed tool response",
    )
    fixture_issues = release_gate_issues(_case_set((case, fixture_variant)))
    assert not any("duplicate runtime request" in issue for issue in fixture_issues)


def test_possible_duplicate_screen_flags_paraphrase_candidates() -> None:
    left = _case(
        0,
        category="factual",
        question="What role does tripartite cooperation play in workforce development?",
    )
    right = _case(
        1,
        category="factual",
        question="In workforce development, what role does tripartite cooperation play?",
    )

    candidates = find_possible_duplicate_pairs(_case_set((left, right)))

    assert candidates == ((left.case_id, right.case_id, 1.0),)


def test_loader_validates_case_contract_and_rejects_invalid_json(tmp_path: Path) -> None:
    case_set = _case_set(tuple(_case(index) for index in range(30)))
    schema = json.loads(CASE_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(case_set.model_dump(mode="json"))

    path = tmp_path / "cases.json"
    path.write_text(case_set.model_dump_json(), encoding="utf-8")
    assert EvaluationCaseSet.load(path) == case_set

    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(EvaluationCaseSetError):
        EvaluationCaseSet.load(path)


@requires_canonical_data
def test_candidate_document_anchors_map_to_evaluation_cleared_sources() -> None:
    case_set = EvaluationCaseSet.load(ROOT / "data/evaluation/feature007-cases.json")

    assert validate_case_anchors(case_set) == ()


def test_human_approved_ground_truth_set_has_category_coverage() -> None:
    case_set = EvaluationCaseSet.load(ROOT / "data/evaluation/feature007-cases.json")

    assert len(case_set.cases) == 67
    assert {case.category for case in case_set.cases} == REQUIRED_CASE_CATEGORIES
    assert {case.split for case in case_set.cases} == {"dev", "test"}
    assert {case.review_status for case in case_set.cases} == {"approved"}
    assert {case.reviewer_ids for case in case_set.cases} == {("reviewer-user",)}
    assert len(case_set.cases) == 67
    assert all(case.reviewed_at is not None for case in case_set.cases)
    assert find_possible_duplicate_pairs(case_set) == ()
    assert release_gate_issues(case_set) == ()


def test_case_anchor_rejects_source_without_evaluation_permission() -> None:
    restricted_anchor = EvidenceAnchor(
        source_id="mom-singapore-youths-labour-market-2025-manual-review",
        page_number=1,
        marker="synthetic rights fixture",
    )
    restricted_case = _case(0).model_copy(
        update={"expected_anchors": (restricted_anchor,), "relevance_grades": ()}
    )
    case_set = _case_set((restricted_case,))

    issues = validate_case_anchors(case_set)

    assert len(issues) == 1
    assert "is not cleared for evaluation" in issues[0]


@requires_canonical_data
def test_case_validation_cli_is_offline_and_release_mode_blocks_unapproved_cases(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(["--validate-only"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["status"] == "valid"
    assert validation["case_count"] == 67
    assert validation["live_requests_made"] is False

    approved_set = EvaluationCaseSet.load(ROOT / "data/evaluation/feature007-cases.json")
    candidate_set = approved_set.model_copy(
        update={
            "cases": tuple(
                case.model_copy(
                    update={"review_status": "candidate", "reviewer_ids": (), "reviewed_at": None}
                )
                for case in approved_set.cases
            )
        }
    )
    candidate_path = tmp_path / "candidate-cases.json"
    candidate_path.write_text(candidate_set.model_dump_json(), encoding="utf-8")

    assert main(["--cases", str(candidate_path), "--release"]) == 1
    release = json.loads(capsys.readouterr().out)
    assert release["status"] == "blocked"
    assert release["release_eligible"] is False
    assert release["review_status_counts"]["approved"] == 0
