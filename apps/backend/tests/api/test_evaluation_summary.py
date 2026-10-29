from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from policylens.api import evaluation_summary
from policylens.api.app import create_app
from policylens.settings import PROJECT_ROOT, AppSettings

CASE_SET_PATH = PROJECT_ROOT / "data/evaluation/feature007-cases.json"
SUMMARY_SCHEMA = PROJECT_ROOT / "specs/009-minimal-ui/contracts/evaluation-summary.schema.json"


def _settings() -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-local-model",
        embedding_provider="local",
    )


def _app() -> Any:
    return create_app(settings=_settings())


def _patch_manifest_paths(monkeypatch: Any, root: Path) -> None:
    monkeypatch.setattr(evaluation_summary, "DEFAULT_CASE_SET_PATH", CASE_SET_PATH)
    monkeypatch.setattr(evaluation_summary, "DEFAULT_RUN_MANIFEST", root / "runs.json")
    monkeypatch.setattr(evaluation_summary, "DEFAULT_REVIEW_MANIFEST", root / "reviews.json")
    monkeypatch.setattr(evaluation_summary, "DEFAULT_ERROR_MANIFEST", root / "errors.json")


def test_evaluation_summary_returns_valid_aggregates_with_case_oracles(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _patch_manifest_paths(monkeypatch, tmp_path)
    metrics = {
        "overall": {
            "case_count": 0,
            "expected_behavior_accuracy": None,
            "retrieval_recall_at_k_mean": None,
            "citation_correctness_mean": None,
            "groundedness_mean": None,
            "answer_relevance_mean": None,
            "latency_ms": {"p50": None, "p95": None},
            "estimated_cost_usd_total": None,
            "ai_judge": {
                "attempted_count": 0,
                "scored_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "ineligible_output_count": 0,
                "model_ids": [],
                "same_model_as_generator": None,
            },
        },
        "limitations": ["No case metrics were measured."],
    }
    record = {
        "run_id": str(uuid4()),
        "status": "blocked",
        "started_at": "2026-10-27T12:00:00Z",
        "finished_at": "2026-10-27T12:00:01Z",
        "configuration": {
            "split": "test",
            "ai_judge": {
                "enabled": True,
                "rubric_version": "feature007-ai-judge-v1",
                "model_ids": ["safe-judge-id"],
            },
        },
        "metrics": metrics,
        "live_requests_made": False,
        "results": [{"case_id": "SYNTHETIC: private case prompt"}],
        "artifact_paths": ["private/local/path"],
    }
    (tmp_path / "runs.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "runs": [record],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "reviews.json").write_text(
        json.dumps({"schema_version": "1.0", "reviews": []}), encoding="utf-8"
    )
    (tmp_path / "errors.json").write_text(
        json.dumps({"schema_version": "1.0", "errors": []}), encoding="utf-8"
    )

    with TestClient(_app()) as client:
        response = client.get("/evaluation/summary")

    assert response.status_code == 200
    payload = response.json()
    schema = json.loads(SUMMARY_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload["status"] == "available"
    assert payload["case_set"]["case_count"] == 67
    assert payload["runs"][0]["status"] == "blocked"
    assert payload["runs"][0]["metrics"]["expected_behavior_accuracy"] is None
    assert payload["runs"][0]["live_requests_made"] is False
    assert payload["runs"][0]["ai_judge"] == {
        "enabled": True,
        "rubric_version": "feature007-ai-judge-v1",
        "model_ids": ["safe-judge-id"],
        "same_model_as_generator": None,
        "attempted_count": 0,
        "scored_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "ineligible_output_count": 0,
    }
    serialized = json.dumps(payload)
    assert "SYNTHETIC: private case prompt" not in serialized
    cases = payload["case_set"]["cases"]
    india = next(case for case in cases if case["case_id"] == "factual-india-youth-2025")
    assert india["question"].startswith("What was India's modeled")
    assert india["expected_behavior"] == "answer"
    assert india["reference_claims"]
    assert "artifact_paths" not in serialized
    assert "feature007-cases.json" not in serialized


def test_evaluation_summary_separates_skipped_judge_outputs_from_attempts() -> None:
    record = evaluation_summary._RunRecord.model_validate(
        {
            "run_id": str(uuid4()),
            "status": "partial",
            "started_at": "2026-10-28T12:00:00Z",
            "finished_at": None,
            "configuration": {
                "split": "all",
                "ai_judge": {
                    "enabled": True,
                    "rubric_version": "feature007-ai-judge-v1",
                    "model_ids": ["safe-judge-id"],
                },
            },
            "metrics": {
                "overall": {
                    "case_count": 3,
                    "ai_judge": {
                        "attempted_count": 3,
                        "scored_count": 1,
                        "failed_count": 1,
                        "model_ids": ["safe-judge-id"],
                        "same_model_as_generator": True,
                    },
                },
            },
            "live_requests_made": True,
            "results": [
                {"case_id": "case-a", "judge_status": "completed"},
                {"case_id": "case-a", "judge_status": "failed"},
                {"case_id": "case-b", "judge_status": "skipped"},
            ],
        }
    )

    summary = evaluation_summary._run_summary(record)

    assert summary.case_count == 2
    assert summary.ai_judge.attempted_count == 2
    assert summary.ai_judge.scored_count == 1
    assert summary.ai_judge.failed_count == 1
    assert summary.ai_judge.skipped_count == 1
    assert summary.ai_judge.ineligible_output_count == 0
    assert summary.ai_judge.same_model_as_generator is True
    assert summary.metrics.groundedness_score_distribution is None


def test_evaluation_summary_estimates_known_model_cost_and_marks_usage_gaps() -> None:
    record = evaluation_summary._RunRecord.model_validate(
        {
            "run_id": str(uuid4()),
            "status": "partial",
            "started_at": "2026-10-28T12:00:00Z",
            "finished_at": None,
            "configuration": {"split": "all"},
            "metrics": {"overall": {"estimated_cost_usd_total": None}},
            "live_requests_made": True,
            "results": [
                {
                    "provider": "openai",
                    "model_id": "gpt-6-luna",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                },
                {
                    "provider": "openai",
                    "model_id": "gpt-6-luna",
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "judge_status": "completed",
                    "judge_model_id": "gpt-6-luna",
                    "judge_input_tokens": 50,
                    "judge_output_tokens": 30,
                },
                {
                    "provider": "openai",
                    "model_id": "gpt-6-luna",
                    "observed_behavior": "failed",
                },
            ],
        }
    )

    metrics = evaluation_summary._run_summary(record).metrics

    assert metrics.estimated_cost_usd_total == pytest.approx(0.00044)
    assert metrics.estimated_cost_basis == "partial_token_estimate"
    assert metrics.estimated_cost_pricing_as_of is not None
    assert metrics.estimated_cost_pricing_as_of.isoformat() == "2026-10-28"
    assert metrics.estimated_cost_usage_gap_count == 1
    assert metrics.estimated_cost_model_ids == ("gpt-6-luna",)


def test_evaluation_summary_prefers_provider_reported_cost() -> None:
    record = evaluation_summary._RunRecord.model_validate(
        {
            "run_id": str(uuid4()),
            "status": "completed",
            "started_at": "2026-10-28T12:00:00Z",
            "finished_at": None,
            "configuration": {"split": "all"},
            "metrics": {"overall": {"estimated_cost_usd_total": 0.25}},
            "live_requests_made": True,
            "results": [
                {
                    "provider": "openai",
                    "model_id": "future-model",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                }
            ],
        }
    )

    metrics = evaluation_summary._run_summary(record).metrics

    assert metrics.estimated_cost_usd_total == 0.25
    assert metrics.estimated_cost_basis == "provider_reported"
    assert metrics.estimated_cost_pricing_as_of is None


def test_evaluation_summary_does_not_price_unknown_models() -> None:
    record = evaluation_summary._RunRecord.model_validate(
        {
            "run_id": str(uuid4()),
            "status": "completed",
            "started_at": "2026-10-28T12:00:00Z",
            "finished_at": None,
            "configuration": {"split": "all"},
            "metrics": {"overall": {"estimated_cost_usd_total": None}},
            "live_requests_made": True,
            "results": [
                {
                    "provider": "openai",
                    "model_id": "future-model",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                }
            ],
        }
    )

    metrics = evaluation_summary._run_summary(record).metrics

    assert metrics.estimated_cost_usd_total is None
    assert metrics.estimated_cost_basis == "unavailable"
    assert metrics.estimated_cost_pricing_as_of is None
    assert metrics.estimated_cost_usage_gap_count == 1
    assert metrics.estimated_cost_model_ids == ()


def test_evaluation_summary_exposes_safe_score_coverage_and_condition_breakdowns(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _patch_manifest_paths(monkeypatch, tmp_path)
    record = {
        "run_id": str(uuid4()),
        "status": "partial",
        "started_at": "2026-10-28T12:00:00Z",
        "finished_at": None,
        "configuration": {
            "split": "all",
            "ai_judge": {
                "enabled": True,
                "rubric_version": "feature007-ai-judge-v2",
                "model_ids": ["judge-model"],
            },
        },
        "metrics": {"overall": {"case_count": 3}},
        "live_requests_made": False,
        "results": [
            {
                "case_id": "calc-supported",
                "condition_id": "mlx:agent",
                "category": "calculation",
                "expected_behavior": "answer",
                "observed_behavior": "answer",
                "groundedness": 5,
                "answer_relevance": 4,
                "citation_correctness": 1.0,
                "citation_completeness": 1.0,
                "citation_anchor_matches": 2,
                "citation_anchor_count": 2,
                "validated_tool_result_count": 1,
                "judge_status": "completed",
                "answer": "private generated answer",
                "judge_rationale": "private judge rationale",
            },
            {
                "case_id": "calc-unsupported",
                "condition_id": "mlx:agent",
                "category": "calculation",
                "expected_behavior": "answer",
                "observed_behavior": "answer",
                "groundedness": 1,
                "answer_relevance": 5,
                "citation_correctness": 0.0,
                "citation_completeness": 0.0,
                "citation_anchor_matches": 0,
                "citation_anchor_count": 2,
                "validated_tool_result_count": 0,
                "judge_status": "completed",
            },
            {
                "case_id": "failed-output",
                "condition_id": "mlx:agent",
                "category": "calculation",
                "expected_behavior": "answer",
                "observed_behavior": "failed",
                "groundedness": 1,
                "answer_relevance": 1,
                "citation_correctness": 0.0,
                "citation_completeness": 0.0,
                "judge_status": "completed",
            },
            {
                "case_id": "retrieval-case",
                "condition_id": "retrieval:chunker:hybrid",
                "category": "calculation",
                "retrieval_recall_at_k": 0.5,
                "retrieval_anchor_hits": 1,
                "retrieval_anchor_count": 2,
            },
        ],
    }
    (tmp_path / "runs.json").write_text(
        json.dumps({"schema_version": "1.0", "runs": [record]}), encoding="utf-8"
    )
    (tmp_path / "reviews.json").write_text(
        json.dumps({"schema_version": "1.0", "reviews": []}), encoding="utf-8"
    )
    (tmp_path / "errors.json").write_text(
        json.dumps({"schema_version": "1.0", "errors": []}), encoding="utf-8"
    )

    with TestClient(_app()) as client:
        response = client.get("/evaluation/summary")

    assert response.status_code == 200
    run = response.json()["runs"][0]
    metrics = run["metrics"]
    assert metrics["groundedness_mean"] == 3.0
    assert metrics["groundedness_scored_count"] == 2
    assert metrics["groundedness_score_distribution"] == [1, 0, 0, 0, 1]
    assert metrics["citation_completeness_mean"] == 0.5
    assert metrics["citation_completeness_scored_count"] == 2
    assert metrics["citation_anchor_matches"] == 2
    assert metrics["citation_anchor_count"] == 4
    assert metrics["validated_tool_result_output_count"] == 1
    assert run["condition_breakdowns"][0]["condition_id"] == "mlx:agent"
    category = run["condition_breakdowns"][0]["category_breakdowns"][0]
    assert category["category"] == "calculation"
    assert category["metrics"]["groundedness_score_distribution"] == [1, 0, 0, 0, 1]
    assert run["condition_breakdowns"][1]["metrics"]["retrieval_anchor_hits"] == 1
    assert run["condition_breakdowns"][1]["metrics"]["retrieval_anchor_count"] == 2
    serialized = json.dumps(response.json())
    assert "private generated answer" not in serialized
    assert "private judge rationale" not in serialized


def test_legacy_failed_generation_is_marked_and_not_counted_as_judge_scored() -> None:
    record = evaluation_summary._RunRecord.model_validate(
        {
            "run_id": str(uuid4()),
            "status": "partial",
            "started_at": "2026-10-28T12:00:00Z",
            "finished_at": None,
            "configuration": {"split": "all"},
            "metrics": {
                "overall": {
                    "case_count": 2,
                    "expected_behavior_accuracy": 0.5,
                    "ai_judge": {
                        "attempted_count": 1,
                        "scored_count": 1,
                        "failed_count": 0,
                        "skipped_count": 0,
                    },
                },
                "limitations": [],
            },
            "live_requests_made": True,
            "results": [
                {
                    "case_id": "successful-case",
                    "expected_behavior": "answer",
                    "observed_behavior": "answer",
                    "groundedness": 5,
                    "answer_relevance": 5,
                },
                {
                    "case_id": "failed-case",
                    "expected_behavior": "answer",
                    "observed_behavior": "failed",
                    "judge_status": "completed",
                    "groundedness": 1,
                    "answer_relevance": 1,
                },
            ],
        }
    )

    summary = evaluation_summary._run_summary(record)

    assert summary.metrics.expected_behavior_scored_count == 2
    assert summary.metrics.failed_output_count == 1
    assert summary.metrics.failure_exclusion_applied is True
    assert summary.metrics.expected_behavior_accuracy == 0.5
    assert summary.metrics.groundedness_mean == 5
    assert summary.metrics.answer_relevance_mean == 5
    assert summary.ai_judge.scored_count == 0
    assert summary.ai_judge.ineligible_output_count == 1
    assert any(
        "Expected-behavior accuracy counts failed outputs as incorrect" in item
        for item in summary.limitations
    )


def test_evaluation_summary_reports_empty_when_run_manifests_are_absent(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _patch_manifest_paths(monkeypatch, tmp_path)

    with TestClient(_app()) as client:
        response = client.get("/evaluation/summary")

    assert response.status_code == 200
    assert response.json()["status"] == "empty"
    assert response.json()["runs"] == []


def test_evaluation_summary_rejects_malformed_manifest_without_echoing_payload(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _patch_manifest_paths(monkeypatch, tmp_path)
    (tmp_path / "runs.json").write_text("private prompt content", encoding="utf-8")

    with TestClient(_app()) as client:
        response = client.get("/evaluation/summary")

    assert response.status_code == 503
    assert response.json()["error_code"] == "EVALUATION_SUMMARY_UNAVAILABLE"
    assert "private prompt content" not in response.text


def test_headline_metrics_use_agent_condition_only() -> None:
    from policylens.api.evaluation_summary import _RunResultSummary, _split_conditions

    rows = tuple(
        _RunResultSummary(case_id=f"c{i}", condition_id=condition)
        for i, condition in enumerate(("openai:agent", "openai:non_agent", "retrieval:fixed:bm25"))
    )

    headline, baseline, retrieval = _split_conditions(rows)

    assert [r.condition_id for r in headline] == ["openai:agent"]
    assert [r.condition_id for r in baseline] == ["openai:non_agent"]
    assert [r.condition_id for r in retrieval] == ["retrieval:fixed:bm25"]
