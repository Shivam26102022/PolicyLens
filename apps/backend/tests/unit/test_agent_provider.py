from __future__ import annotations

from typing import Any

from pydantic import AnyHttpUrl, SecretStr, TypeAdapter

from policylens.agent_runtime.provider import AgentConfigurationError, build_openai_agent_model
from policylens.settings import AppSettings


class RecordingClient:
    last_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        type(self).last_kwargs = kwargs


def test_standard_openai_uses_configured_model_and_responses_api() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-key"),
        openai_model="standard-model",
    )

    provider, model = build_openai_agent_model(settings, client_factory=RecordingClient)

    assert provider is not None
    assert type(model).__name__ == "OpenAIResponsesModel"
    assert model.model == "standard-model"
    assert "base_url" not in RecordingClient.last_kwargs
    assert RecordingClient.last_kwargs["max_retries"] == 0


def test_foundry_uses_deployment_model_custom_endpoint_and_chat_completions() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-key"),
        openai_model="unused-standard-model",
        openai_deployment_model="gpt-6-luna",
        openai_base_url=TypeAdapter(AnyHttpUrl).validate_python(
            "https://foundry.example.test/openai/v1"
        ),
    )

    provider, model = build_openai_agent_model(settings, client_factory=RecordingClient)

    assert type(model).__name__ == "OpenAIChatCompletionsModel"
    assert model.model == "gpt-6-luna"
    assert str(RecordingClient.last_kwargs["base_url"]) == "https://foundry.example.test/openai/v1"
    assert RecordingClient.last_kwargs["max_retries"] == 0
    assert RecordingClient.last_kwargs["default_headers"]["api-key"] == "test-key"


def test_foundry_can_use_responses_api_when_explicitly_enabled() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-key"),
        openai_model="unused-standard-model",
        openai_deployment_model="gpt-6-luna",
        openai_base_url=TypeAdapter(AnyHttpUrl).validate_python(
            "https://foundry.example.test/openai/v1"
        ),
        openai_use_responses_api=True,
    )

    provider, model = build_openai_agent_model(settings, client_factory=RecordingClient)

    assert provider is not None
    assert type(model).__name__ == "OpenAIResponsesModel"
    assert model.model == "gpt-6-luna"
    assert str(RecordingClient.last_kwargs["base_url"]) == "https://foundry.example.test/openai/v1"


def test_foundry_deployment_without_base_url_fails_before_client_creation() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-key"),
        openai_deployment_model="gpt-6-luna",
    )

    def unexpected_client(**_kwargs: Any) -> Any:
        raise AssertionError("provider client must not be created without OPENAI_BASE_URL")

    try:
        build_openai_agent_model(settings, client_factory=unexpected_client)
    except AgentConfigurationError as error:
        assert "OPENAI_BASE_URL" in str(error)
    else:
        raise AssertionError("Foundry deployment without base URL must fail closed")
