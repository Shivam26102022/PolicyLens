from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from policylens.settings import AppSettings
from scripts.evaluation_judge import (
    MAX_JUDGE_EVIDENCE_GROUP_CHARS,
    EvaluationJudge,
    EvaluationJudgeError,
    EvaluationJudgeScores,
)


def _settings() -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-key"),
        openai_model="test-judge-model",
    )


def test_ai_judge_uses_bounded_untrusted_inputs_and_extracts_typed_scores() -> None:
    payloads: list[object] = []
    loops: list[asyncio.AbstractEventLoop] = []
    temperatures: list[object] = []

    async def fake_runner(_agent: object, payload: str, **_kwargs: object) -> object:
        loops.append(asyncio.get_running_loop())
        payloads.append(json.loads(payload))
        run_config = _kwargs.get("run_config")
        model_settings = getattr(run_config, "model_settings", None)
        temperatures.append(getattr(model_settings, "temperature", "not-configured"))
        return SimpleNamespace(
            final_output={"groundedness": 4, "answer_relevance": 5},
            context_wrapper=SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=31, completion_tokens=8, cost_usd=0.002)
            ),
        )

    judge = EvaluationJudge(_settings(), runner=fake_runner)
    try:
        result = judge.score(
            question="What changed?",
            response_status="answered",
            answer="The estimate increased.",
            evidence=tuple(f"evidence-{index}: " + "x" * 1000 for index in range(10)),
            tool_evidence=("validated calculation result: 16.0%",),
        )
        judge.score(
            question="What changed next?",
            response_status="answered",
            answer="It continued to increase.",
            evidence=(),
        )
    finally:
        judge.close()

    assert result.model_id == "test-judge-model"
    assert result.scores == EvaluationJudgeScores(groundedness=4, answer_relevance=5)
    assert result.input_tokens == 31
    assert result.output_tokens == 8
    assert result.cost_usd == 0.002
    assert result.latency_ms >= 0
    assert len(loops) == 2
    assert loops[0] is loops[1]
    assert temperatures == [None, None]
    payload = payloads[0]
    assert isinstance(payload, dict)
    assert set(payload) == {
        "question",
        "response_status",
        "answer",
        "cited_evidence",
        "validated_tool_results",
    }
    assert len(payload["cited_evidence"]) == 6
    assert sum(map(len, payload["cited_evidence"])) == MAX_JUDGE_EVIDENCE_GROUP_CHARS
    assert payload["validated_tool_results"] == ["validated calculation result: 16.0%"]
    assert "expected_behavior" not in payload
    assert "reference_claims" not in payload


def test_ai_judge_rejects_scores_outside_the_anchored_rubric() -> None:
    async def fake_runner(_agent: object, _payload: str, **_kwargs: object) -> object:
        return SimpleNamespace(
            final_output={"groundedness": 6, "answer_relevance": 5},
            context_wrapper=SimpleNamespace(usage=None),
        )

    judge = EvaluationJudge(_settings(), runner=fake_runner)

    try:
        with pytest.raises(EvaluationJudgeError, match="EVAL_JUDGE_INVALID_OUTPUT"):
            judge.score(
                question="What changed?",
                response_status="answered",
                answer="It changed.",
                evidence=(),
            )
    finally:
        judge.close()


def test_ai_judge_reports_provider_failure_without_echoing_exception_text() -> None:
    async def failing_runner(_agent: object, _payload: str, **_kwargs: object) -> object:
        raise RuntimeError("sensitive provider response")

    judge = EvaluationJudge(_settings(), runner=failing_runner)

    try:
        with pytest.raises(EvaluationJudgeError, match="EVAL_JUDGE_REQUEST_FAILED") as error:
            judge.score(
                question="What changed?",
                response_status="answered",
                answer="It changed.",
                evidence=(),
            )
    finally:
        judge.close()

    assert "sensitive provider response" not in str(error.value)
