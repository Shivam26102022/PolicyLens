from __future__ import annotations

import json
from pathlib import Path

from pydantic import SecretStr

from policylens.settings import AppSettings
from scripts.evaluate_agent import (
    AgentEvaluationCaseSet,
    EvaluationObservation,
    compare_observations,
    run_evaluation,
)

CASE_PATH = Path(__file__).resolve().parents[2] / "data/evaluation/agent-tool-cases.json"


def test_agent_case_set_is_versioned_and_covers_tool_and_safe_outcomes() -> None:
    case_set = AgentEvaluationCaseSet.load(CASE_PATH)

    assert case_set.case_set_id == "feature004-agent-tool-engineering-v1"
    assert len(case_set.cases) == 6
    assert sum(case.requires_tool for case in case_set.cases) == 2
    assert {case.expected_status for case in case_set.cases} >= {
        "answered",
        "clarification_required",
        "abstained",
    }
    assert case_set.runtime_label_access == "prohibited"


def test_comparison_uses_same_cases_and_reports_behavior_not_quality_value() -> None:
    case_set = AgentEvaluationCaseSet.load(CASE_PATH)
    agent_observations = tuple(
        EvaluationObservation(
            case_id=case.case_id,
            status=case.expected_status,
            tool_calls=1 if case.requires_tool else 0,
            schema_valid=True,
            latency_ms=100.0,
        )
        for case in case_set.cases
    )
    baseline_observations = tuple(
        EvaluationObservation(
            case_id=case.case_id,
            status=case.expected_status,
            tool_calls=0,
            schema_valid=True,
            latency_ms=80.0,
        )
        for case in case_set.cases
    )

    summary = compare_observations(case_set, agent_observations, baseline_observations)

    assert summary.case_count == 6
    assert summary.agent_expected_status_rate == 1.0
    assert summary.baseline_expected_status_rate == 1.0
    assert summary.agent_tool_compliance_rate == 1.0
    assert summary.agent_mean_latency_ms == 100.0
    assert summary.baseline_mean_latency_ms == 80.0
    assert summary.answer_quality_value == "not_measured"


def test_evaluation_defaults_to_not_run_without_network_calls(tmp_path: Path) -> None:
    record = run_evaluation(project_root=tmp_path, cases_path=CASE_PATH)

    assert record["status"] == "not_run"
    assert record["reason_code"] == "LIVE_COMPARISON_NOT_REQUESTED"
    assert record["live_request_made"] is False
    manifest = json.loads(
        (tmp_path / "data/manifests/agent-evaluation-manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["runs"]) == 1
    report = (tmp_path / "docs/evaluation/agent-evaluation.md").read_text(encoding="utf-8")
    assert "No live OpenAI/Foundry request was made" in report


def test_readiness_only_live_check_is_blocked_without_comparison_executor(tmp_path: Path) -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_model="test-model",
    )

    record = run_evaluation(
        project_root=tmp_path,
        cases_path=CASE_PATH,
        live=True,
        settings=settings,
    )

    assert record["status"] == "blocked"
    assert record["reason_code"] == "FEATURE_004_COMPARISON_NOT_IMPLEMENTED"
    reason = record["reason"]
    assert isinstance(reason, str)
    assert "Feature 007 evaluation suite" in reason
    assert record["live_request_made"] is False


def test_live_foundry_comparison_requires_base_url(tmp_path: Path) -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_deployment_model="gpt-6-luna",
    )

    record = run_evaluation(
        project_root=tmp_path,
        cases_path=CASE_PATH,
        live=True,
        settings=settings,
    )

    assert record["status"] == "blocked"
    assert record["reason_code"] == "OPENAI_BASE_URL_REQUIRED"
    assert record["live_request_made"] is False
