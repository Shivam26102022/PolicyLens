from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import SecretStr

from policylens.agent_runtime.models import (
    ModelCapabilities,
    ModelCapabilitySet,
    ModelLimits,
)
from policylens.settings import PROJECT_ROOT, AppSettings

CAPABILITY_SCHEMA_PATH = (
    PROJECT_ROOT / "specs/006-model-routing/contracts/model-capabilities.schema.json"
)


def _validate_capability_contract(payload: dict[str, Any]) -> None:
    schema = json.loads(CAPABILITY_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def _settings(provider: str = "openai") -> AppSettings:
    if provider == "mlx":
        return AppSettings(  # type: ignore[call-arg]
            _env_file=None,
            model_provider="mlx",
            mlx_model="local-test-model",
            embedding_provider="local",
        )
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-key"),
        openai_model="standard-test-model",
        embedding_provider="local",
    )


class FakeGateway:
    def __init__(self, capabilities: ModelCapabilities) -> None:
        self._capabilities = capabilities
        self.discover_calls = 0

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    async def discover_capabilities(self) -> ModelCapabilities:
        self.discover_calls += 1
        return self._capabilities


def _mlx_capabilities(*, ready: bool = True) -> ModelCapabilities:
    return ModelCapabilities(
        provider="mlx",
        model_id="local-test-model",
        route="mlx_chat_completions",
        ready=ready,
        capabilities=ModelCapabilitySet(
            native_tool_calls=False,
            native_json_schema=False,
            host_action_envelope=True,
            streaming=False,
            usage_reporting=True,
        ),
        limits=ModelLimits(max_input_chars=50000, max_output_tokens=1200, timeout_seconds=90),
        platform="Linux test",
        limitations=("Fake local endpoint.",),
    )


def test_capability_endpoint_reports_openai_route_without_generation_request() -> None:
    from policylens.api.app import create_app

    app = create_app(settings=_settings("openai"))

    with TestClient(app) as client:
        response = client.get("/model/capabilities")

    assert response.status_code == 200
    payload = response.json()
    _validate_capability_contract(payload)
    assert payload["provider"] == "openai"
    assert payload["model_id"] == "standard-test-model"
    assert payload["route"] == "openai_responses"
    assert payload["ready"] is True
    assert payload["limits"]["max_output_tokens"] == 8000
    assert "base_url" not in payload
    assert "api_key" not in payload


def test_capability_endpoint_reports_selected_mlx_features_without_secret_fields(
    monkeypatch: Any,
) -> None:
    from policylens.api.app import create_app

    fake_gateway = FakeGateway(_mlx_capabilities())
    monkeypatch.setattr(
        "policylens.api.model_capabilities.build_model_gateway",
        lambda _settings: fake_gateway,
    )
    app = create_app(settings=_settings("mlx"))

    with TestClient(app) as client:
        response = client.get("/model/capabilities")

    assert response.status_code == 200
    payload = response.json()
    _validate_capability_contract(payload)
    assert payload["provider"] == "mlx"
    assert payload["model_id"] == "local-test-model"
    assert payload["capabilities"]["host_action_envelope"] is True
    assert payload["capabilities"]["native_tool_calls"] is False
    assert "base_url" not in payload
    assert "api_key" not in payload
    assert fake_gateway.discover_calls == 1


def test_capability_endpoint_returns_service_unavailable_when_model_is_not_ready(
    monkeypatch: Any,
) -> None:
    from policylens.api.app import create_app

    fake_gateway = FakeGateway(_mlx_capabilities(ready=False))
    monkeypatch.setattr(
        "policylens.api.model_capabilities.build_model_gateway",
        lambda _settings: fake_gateway,
    )
    app = create_app(settings=_settings("mlx"))

    with TestClient(app) as client:
        response = client.get("/model/capabilities")

    assert response.status_code == 503
    assert response.json()["error_code"] == "MODEL_UNAVAILABLE"
    assert "model_id" not in response.json()
