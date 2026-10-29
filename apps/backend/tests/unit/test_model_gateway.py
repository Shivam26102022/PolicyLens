from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import httpx2 as httpx
import pytest
from agents import ModelSettings
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI, BadRequestError
from openai.types.responses import ResponseReasoningItem
from openai.types.shared import Reasoning
from pydantic import AnyHttpUrl, SecretStr, TypeAdapter, ValidationError

from policylens.agent_runtime.gateway import ModelGatewayContext, OpenAIModelGateway
from policylens.agent_runtime.models import (
    AgentAnswerResponse,
    AgentDraft,
    AgentModelUsage,
    ModelCapabilities,
    ModelCapabilitySet,
    ModelLimits,
    ModelProviderName,
    ModelRunMetadata,
    ModelUsage,
    ReasoningEffort,
)
from policylens.agent_runtime.provider import build_openai_agent_model
from policylens.agent_runtime.state import AgentRunLedger
from policylens.agent_runtime.tools import StatisticsToolAdapter
from policylens.settings import AppSettings

HASH = "a" * 64


class FakeOpenAIClient:
    def __init__(self, **_kwargs: object) -> None:
        pass


def _capabilities(provider: ModelProviderName = "mlx") -> ModelCapabilities:
    return ModelCapabilities(
        schema_version="1.0",
        provider=provider,
        model_id="mlx-community/Mistral-7B-Instruct-v0.3-4bit",
        route="mlx_chat_completions",
        ready=True,
        capabilities=ModelCapabilitySet(
            native_tool_calls=False,
            native_json_schema=False,
            host_action_envelope=True,
            streaming=True,
            usage_reporting=True,
        ),
        limits=ModelLimits(
            max_input_chars=50000,
            max_output_tokens=1200,
            timeout_seconds=90,
        ),
        server_version=None,
        platform="Linux fake endpoint",
        limitations=("Fake endpoint; no MLX execution was performed.",),
    )


def test_model_capabilities_keep_native_and_host_capabilities_separate() -> None:
    capabilities = _capabilities()

    assert capabilities.capabilities.native_tool_calls is False
    assert capabilities.capabilities.native_json_schema is False
    assert capabilities.capabilities.host_action_envelope is True
    assert "base_url" not in ModelCapabilities.model_fields
    assert "api_key" not in ModelCapabilities.model_fields


def test_model_usage_allows_unmeasured_cost_and_memory() -> None:
    usage = ModelUsage(
        prompt_tokens=120,
        completion_tokens=30,
        total_tokens=150,
        cost_usd=None,
        memory_bytes=None,
    )

    assert usage.total_tokens == 150
    assert usage.cost_usd is None
    assert usage.memory_bytes is None
    with pytest.raises(ValidationError):
        ModelUsage(prompt_tokens=-1)


def test_agent_answer_response_supports_local_provider_metadata() -> None:
    capabilities = _capabilities()
    metadata = ModelRunMetadata(
        provider="mlx",
        model_id=capabilities.model_id,
        prompt_version="agent-v2",
        latency_ms=123.4,
        usage=AgentModelUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        capabilities=capabilities,
        fallback_decision="none",
    )
    response = AgentAnswerResponse(
        run_id=uuid4(),
        trace_id=uuid4(),
        index_version=HASH,
        status="abstained",
        abstention_reason="No evidence was sufficient.",
        provider="mlx",
        model=capabilities.model_id,
        model_metadata=metadata,
        events=(),
    )

    assert response.provider == "mlx"
    assert response.model_metadata is not None
    assert response.model_metadata.capabilities.capabilities.native_tool_calls is False


def test_mlx_provider_requires_explicit_model_and_loopback_url() -> None:
    with pytest.raises(ValidationError):
        AppSettings(
            _env_file=None,  # type: ignore[call-arg]
            model_provider="mlx",
            mlx_base_url=TypeAdapter(AnyHttpUrl).validate_python("https://api.example.test/v1"),
            mlx_model="test-model",
            embedding_provider="local",
        )

    with pytest.raises(ValidationError):
        AppSettings(
            model_provider="mlx",
            mlx_base_url=TypeAdapter(AnyHttpUrl).validate_python("http://127.0.0.1:8080/v1"),
            mlx_model=" ",
            embedding_provider="local",
        )


def test_model_and_embedding_providers_remain_independent() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        model_provider="mlx",
        mlx_base_url=TypeAdapter(AnyHttpUrl).validate_python("http://[::1]:8080/v1"),
        mlx_model="local-model",
        embedding_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_embedding_model="text-embedding-3-small",
    )

    assert settings.model_provider == "mlx"
    assert settings.embedding_provider == "openai"


def test_openai_gateway_preserves_agents_sdk_run_and_records_usage() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_base_url=TypeAdapter(AnyHttpUrl).validate_python(
            "https://foundry.example.test/openai/v1/"
        ),
        openai_model="test-generation-model",
        embedding_provider="local",
    )
    ledger = AgentRunLedger(max_tool_calls=4, max_calls_per_tool=2, max_retries=1)
    runner_calls: list[tuple[object, object]] = []

    async def fake_runner(agent: object, model_input: object, **_kwargs: object) -> object:
        runner_calls.append((agent, model_input))
        return SimpleNamespace(
            final_output=AgentDraft(status="abstained", abstention_reason="No evidence."),
            context_wrapper=SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=120,
                    output_tokens=30,
                    total_tokens=150,
                )
            ),
        )

    gateway = OpenAIModelGateway(
        settings,
        runner=fake_runner,
        provider_builder=lambda provider_settings: build_openai_agent_model(
            provider_settings,
            client_factory=FakeOpenAIClient,
        ),
    )
    request = ModelGatewayContext(
        instructions="Return a typed draft.",
        input="A bounded test input.",
        ledger=ledger,
        statistics_adapter=cast(StatisticsToolAdapter, object()),
    )

    result = asyncio.run(gateway.run_agent(request))

    assert result.draft.status == "abstained"
    assert result.metadata.provider == "openai"
    assert result.metadata.model_id == "test-generation-model"
    assert result.metadata.usage.prompt_tokens == 120
    assert result.metadata.usage.completion_tokens == 30
    assert result.metadata.usage.total_tokens == 150
    assert result.metadata.fallback_decision == "none"
    assert runner_calls
    agent_settings = getattr(runner_calls[0][0], "model_settings")
    agent_tools = getattr(runner_calls[0][0], "tools")
    assert agent_settings.temperature is None
    assert agent_settings.reasoning.effort == "none"
    assert agent_settings.reasoning.summary is None
    assert agent_settings.max_tokens is None
    assert agent_settings.extra_args == {"max_completion_tokens": settings.max_agent_output_tokens}
    assert agent_settings.preserve_raw_usage is True
    assert len(agent_tools) == 1
    assert agent_tools[0].output_json_schema is None


@pytest.mark.parametrize(
    ("reasoning_effort", "expected_max_tokens"),
    [
        ("none", 1200),
        ("low", 2400),
        ("medium", 4800),
        ("high", 8000),
    ],
)
def test_responses_gateway_budgets_reasoning_and_preserves_provider_usage(
    reasoning_effort: ReasoningEffort,
    expected_max_tokens: int,
) -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_base_url=TypeAdapter(AnyHttpUrl).validate_python(
            "https://foundry.example.test/openai/v1/"
        ),
        openai_model="unused-standard-model",
        openai_deployment_model="test-foundry-model",
        openai_use_responses_api=True,
        embedding_provider="local",
    )
    ledger = AgentRunLedger(max_tool_calls=4, max_calls_per_tool=2, max_retries=1)
    runner_calls: list[tuple[object, object]] = []
    reasoning_item = ResponseReasoningItem.model_validate(
        {
            "id": "reasoning-1",
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "Compared the available evidence."}],
            "content": [{"type": "reasoning_text", "text": "Private reasoning must not surface."}],
        }
    )

    async def fake_runner(agent: object, model_input: object, **_kwargs: object) -> object:
        runner_calls.append((agent, model_input))
        return SimpleNamespace(
            final_output=AgentDraft(status="abstained", abstention_reason="No evidence."),
            context_wrapper=SimpleNamespace(
                usage=SimpleNamespace(
                    requests=2,
                    input_tokens=120,
                    output_tokens=30,
                    total_tokens=150,
                    input_tokens_details=SimpleNamespace(cached_tokens=4),
                    output_tokens_details=SimpleNamespace(reasoning_tokens=10),
                )
            ),
            raw_responses=(
                [SimpleNamespace(output=[reasoning_item])] if reasoning_effort != "none" else []
            ),
        )

    gateway = OpenAIModelGateway(
        settings,
        runner=fake_runner,
        provider_builder=lambda provider_settings: build_openai_agent_model(
            provider_settings,
            client_factory=FakeOpenAIClient,
        ),
    )
    request = ModelGatewayContext(
        instructions="Return a typed draft.",
        input="A bounded test input.",
        ledger=ledger,
        statistics_adapter=cast(StatisticsToolAdapter, object()),
        reasoning_effort=reasoning_effort,
    )

    result = asyncio.run(gateway.run_agent(request))

    assert result.metadata.capabilities.route == "openai_responses"
    assert result.metadata.reasoning_effort == reasoning_effort
    assert result.metadata.reasoning_summary == (
        "Compared the available evidence." if reasoning_effort != "none" else None
    )
    assert "Private reasoning" not in (result.metadata.reasoning_summary or "")
    assert result.metadata.usage.requests == 2
    assert result.metadata.usage.prompt_tokens == 120
    assert result.metadata.usage.completion_tokens == 30
    assert result.metadata.usage.total_tokens == 150
    assert result.metadata.usage.cached_input_tokens == 4
    assert result.metadata.usage.reasoning_tokens == 10
    agent_settings = getattr(runner_calls[0][0], "model_settings")
    assert agent_settings.reasoning.effort == reasoning_effort
    assert agent_settings.reasoning.summary is None
    assert agent_settings.max_tokens == expected_max_tokens
    assert result.metadata.capabilities.limits.max_output_tokens == 8000


@pytest.mark.parametrize("reasoning_effort", ["low", "medium", "high"])
def test_agents_sdk_serializes_reasoning_effort_to_responses_request(
    reasoning_effort: ReasoningEffort,
) -> None:
    captured_request: dict[str, object] = {}

    async def capture_request(request: httpx.Request) -> httpx.Response:
        captured_request.update(json.loads(request.content))
        return httpx.Response(
            400,
            json={"error": {"message": "synthetic rejection", "type": "test_error"}},
        )

    async def send_with_mock_transport() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(capture_request)) as transport:
            client = AsyncOpenAI(
                api_key="test-only-key",
                base_url="https://mock.invalid/v1",
                max_retries=0,
                http_client=transport,
            )
            model = OpenAIResponsesModel("test-model", client)
            create_kwargs = model._build_response_create_kwargs(
                system_instructions="Return a typed answer.",
                input="A test question.",
                model_settings=ModelSettings(
                    reasoning=Reasoning(effort=reasoning_effort),
                    max_tokens=2400,
                ),
                tools=[],
                output_schema=None,
                handoffs=[],
                stream=False,
            )
            try:
                await client.responses.create(**create_kwargs)
            except BadRequestError:
                pass
            await client.close()

    asyncio.run(send_with_mock_transport())

    assert captured_request["reasoning"] == {"effort": reasoning_effort}
    assert captured_request["max_output_tokens"] == 2400


def test_official_openai_responses_gateway_requests_sdk_reasoning_summary() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_model="test-openai-model",
        embedding_provider="local",
    )
    runner_calls: list[object] = []

    async def fake_runner(agent: object, _model_input: object, **_kwargs: object) -> object:
        runner_calls.append(agent)
        return SimpleNamespace(
            final_output=AgentDraft(status="abstained", abstention_reason="No evidence."),
            context_wrapper=SimpleNamespace(usage=SimpleNamespace()),
            raw_responses=[],
        )

    gateway = OpenAIModelGateway(
        settings,
        runner=fake_runner,
        provider_builder=lambda provider_settings: build_openai_agent_model(
            provider_settings,
            client_factory=FakeOpenAIClient,
        ),
    )

    asyncio.run(
        gateway.run_agent(
            ModelGatewayContext(
                instructions="Return a typed draft.",
                input="A bounded test input.",
                ledger=AgentRunLedger(max_tool_calls=4, max_calls_per_tool=2, max_retries=1),
                statistics_adapter=None,
                reasoning_effort="low",
            )
        )
    )

    agent_settings = getattr(runner_calls[0], "model_settings")
    assert agent_settings.reasoning.effort == "low"
    assert agent_settings.reasoning.summary == "auto"
