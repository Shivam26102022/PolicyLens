from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from scripts import evaluate_providers
from scripts.evaluate_agent import AgentEvaluationCaseSet
from scripts.evaluate_providers import (
    ProviderCaseObservation,
    ProviderDescriptor,
    UsageMetrics,
    build_provider_comparison,
)

ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT / "data/evaluation/agent-tool-cases.json"
SCHEMA_PATH = ROOT / "specs/006-model-routing/contracts/provider-comparison.schema.json"


def _case_set() -> AgentEvaluationCaseSet:
    return AgentEvaluationCaseSet.load(CASE_PATH)


def _providers() -> tuple[ProviderDescriptor, ...]:
    return (
        ProviderDescriptor(
            provider="openai",
            model_id="configured-openai-model",
            route="openai_responses",
            runtime_version="openai-agents test; openai test",
        ),
        ProviderDescriptor(
            provider="mlx",
            model_id="configured-local-model",
            route="mlx_chat_completions",
            runtime_version=None,
        ),
    )


def test_report_hashes_frozen_cases_and_validates_against_contract() -> None:
    case_set = _case_set()
    first_case = case_set.cases[0]
    observations = (
        ProviderCaseObservation(
            case_id=first_case.case_id,
            index_version="c" * 64,
            provider="openai",
            status="succeeded",
            tool_selected=True,
            arguments_valid=True,
            structured_valid=True,
            latency_ms=125.0,
            usage=UsageMetrics(prompt_tokens=42, completion_tokens=16, total_tokens=58),
        ),
        ProviderCaseObservation(
            case_id=first_case.case_id,
            index_version="c" * 64,
            provider="mlx",
            status="failed",
            tool_selected=False,
            arguments_valid=None,
            structured_valid=False,
            latency_ms=310.0,
            groundedness="not_measured",
            answer_quality="not_measured",
            memory_bytes="not_measured",
            cost_usd="not_measured",
        ),
    )

    report = build_provider_comparison(
        case_set=case_set,
        case_set_sha256=hashlib.sha256(CASE_PATH.read_bytes()).hexdigest(),
        providers=_providers(),
        observations=observations,
        live_requests_made=True,
        platform_name="test-platform",
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        report.model_dump(mode="json")
    )

    assert report.case_set_sha256 == hashlib.sha256(CASE_PATH.read_bytes()).hexdigest()
    assert report.prompt_version == "agent-v2"
    assert [(item.provider, item.model_id) for item in report.providers] == [
        ("openai", "configured-openai-model"),
        ("mlx", "configured-local-model"),
    ]
    results_by_key = {(item.case_id, item.provider): item for item in report.results}
    assert results_by_key[(first_case.case_id, "openai")].status == "succeeded"
    assert results_by_key[(first_case.case_id, "mlx")].status == "failed"
    assert results_by_key[(first_case.case_id, "openai")].index_version == "c" * 64
    assert results_by_key[(case_set.cases[1].case_id, "openai")].status == "skipped"
    assert report.summary.structured_valid_rate == 0.5
    assert report.summary.tool_selection_rate == 0.5
    assert report.summary.mean_latency_ms == 217.5
    assert report.summary.groundedness == "not_measured"
    assert report.summary.answer_quality == "not_measured"
    assert report.summary.memory_bytes == "not_measured"
    assert report.summary.cost_usd == "not_measured"
    assert report.live_requests_made


def test_report_rejects_duplicate_or_unknown_provider_observations() -> None:
    case_set = _case_set()
    observation = ProviderCaseObservation(
        case_id=case_set.cases[0].case_id,
        provider="openai",
        status="succeeded",
        tool_selected=False,
        arguments_valid=None,
        structured_valid=True,
    )
    case_set_sha256 = hashlib.sha256(CASE_PATH.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="duplicate provider observation"):
        build_provider_comparison(
            case_set=case_set,
            case_set_sha256=case_set_sha256,
            providers=_providers(),
            observations=(observation, observation),
        )
    with pytest.raises(ValueError, match="no matching descriptor"):
        build_provider_comparison(
            case_set=case_set,
            case_set_sha256=case_set_sha256,
            providers=(_providers()[0],),
            observations=(observation.model_copy(update={"provider": "mlx"}),),
        )


def test_report_without_observations_is_explicitly_not_measured() -> None:
    case_set = _case_set()

    report = build_provider_comparison(
        case_set=case_set,
        case_set_sha256=hashlib.sha256(CASE_PATH.read_bytes()).hexdigest(),
        providers=_providers(),
        platform_name="Linux test host",
    )

    assert all(result.status == "skipped" for result in report.results)
    assert report.summary.structured_valid_rate is None
    assert report.summary.tool_selection_rate is None
    assert report.summary.groundedness == "not_measured"
    assert report.summary.answer_quality == "not_measured"
    assert report.summary.mean_latency_ms is None
    assert report.summary.memory_bytes == "not_measured"
    assert report.summary.cost_usd == "not_measured"
    assert any("cannot verify Apple-silicon MLX" in item for item in report.limitations)
    assert not report.live_requests_made


def test_observation_rejects_out_of_contract_metric_values() -> None:
    with pytest.raises(ValidationError):
        ProviderCaseObservation(
            case_id="case-1",
            provider="openai",
            status="succeeded",
            structured_valid=True,
            groundedness=1.1,
        )


def test_default_cli_writes_skipped_rows_without_entering_provider_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_provider_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("default evaluation must not run a provider")

    monkeypatch.setattr(evaluate_providers, "_execute_provider", unexpected_provider_run)
    json_path = tmp_path / "provider-comparison.json"
    markdown_path = tmp_path / "provider-comparison.md"

    result = evaluate_providers.main(
        [
            "--cases",
            str(CASE_PATH),
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    )

    record = json.loads(json_path.read_text(encoding="utf-8"))
    assert result == 0
    assert record["live_requests_made"] is False
    assert {item["status"] for item in record["results"]} == {"skipped"}
    assert markdown_path.exists()
