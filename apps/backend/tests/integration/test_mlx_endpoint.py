from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import pytest
from openai import AsyncOpenAI
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from policylens.agent_runtime.gateway import ModelGatewayContext
from policylens.agent_runtime.mlx_provider import MLXModelGateway
from policylens.agent_runtime.provider import AgentConfigurationError
from policylens.agent_runtime.state import AgentRunLedger, AgentRunState
from policylens.agent_runtime.tools import AgentToolExecutionError
from policylens.settings import AppSettings

MODEL_ID = "mlx-community/Mistral-7B-Instruct-v0.3-4bit"
LOCAL_URL = "http://127.0.0.1:8080/v1"


def _settings(base_url: str = LOCAL_URL) -> AppSettings:
    return AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        model_provider="mlx",
        mlx_model=MODEL_ID,
        mlx_base_url=TypeAdapter(AnyHttpUrl).validate_python(base_url),
        embedding_provider="local",
    )


def _ledger() -> AgentRunLedger:
    ledger = AgentRunLedger(max_tool_calls=4, max_calls_per_tool=2, max_retries=1)
    ledger.transition(AgentRunState.VALIDATED)
    ledger.transition(AgentRunState.RETRIEVING)
    ledger.transition(AgentRunState.ASSESSING)
    return ledger


def _final_action() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "action": "final",
            "draft": {
                "status": "abstained",
                "claims": [],
                "clarification_question": None,
                "abstention_reason": "The endpoint fixture contains no retrieval evidence.",
                "conflicts": [],
                "uncertainty": [],
                "limitations": [],
            },
        }
    )


def _model_response() -> dict[str, object]:
    return {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "test"}],
    }


def _completion_response(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 24, "completion_tokens": 11, "total_tokens": 35},
    }


def _client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., AsyncOpenAI]:
    def create_client(**kwargs: Any) -> AsyncOpenAI:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return AsyncOpenAI(**kwargs, http_client=http_client)

    return create_client


def _context() -> ModelGatewayContext:
    return ModelGatewayContext(
        instructions="Use only the supplied evidence.",
        input="A bounded fake endpoint request.",
        ledger=_ledger(),
        statistics_adapter=None,
    )


def test_fake_http_endpoint_discovers_model_and_runs_bounded_completion() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(200, json=_model_response(), request=request)
        if request.method == "POST" and request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json=_completion_response(_final_action()), request=request)
        return httpx.Response(404, request=request)

    gateway = MLXModelGateway(_settings(), client_factory=_client_factory(handler))

    result = asyncio.run(gateway.run_agent(_context()))

    completion_request = requests[1]
    payload = json.loads(completion_request.content)
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/v1/models"),
        ("POST", "/v1/chat/completions"),
    ]
    assert all(request.url.host == "127.0.0.1" for request in requests)
    assert payload["model"] == MODEL_ID
    assert payload["temperature"] == 0
    assert payload["max_tokens"] <= 1200
    assert "response_format" not in payload
    assert "tools" not in payload
    assert result.draft.status == "abstained"
    assert result.metadata.usage.total_tokens == 35
    assert gateway.capabilities.capabilities.native_tool_calls is False
    assert gateway.capabilities.capabilities.native_json_schema is False


@pytest.mark.parametrize("failure", ["http_error", "timeout"])
def test_fake_http_endpoint_model_discovery_fails_safely(failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return httpx.Response(503, json={"error": "unavailable"}, request=request)

    gateway = MLXModelGateway(_settings(), client_factory=_client_factory(handler))

    with pytest.raises(AgentConfigurationError, match="local MLX model server is unavailable"):
        asyncio.run(gateway.discover_capabilities())


@pytest.mark.parametrize("content", ["", "not-json"])
def test_fake_http_endpoint_rejects_empty_or_malformed_content(content: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=_model_response(), request=request)
        return httpx.Response(200, json=_completion_response(content), request=request)

    gateway = MLXModelGateway(_settings(), client_factory=_client_factory(handler))

    with pytest.raises(AgentToolExecutionError) as error:
        asyncio.run(gateway.run_agent(_context()))

    assert error.value.code == "OUTPUT_SCHEMA_INVALID"


def test_non_loopback_endpoint_is_rejected_before_client_creation() -> None:
    client_created = False

    def create_client(**_kwargs: object) -> SimpleNamespace:
        nonlocal client_created
        client_created = True
        return SimpleNamespace()

    with pytest.raises(ValidationError):
        settings = _settings("http://example.test/v1")
        MLXModelGateway(settings, client_factory=create_client)

    assert client_created is False
