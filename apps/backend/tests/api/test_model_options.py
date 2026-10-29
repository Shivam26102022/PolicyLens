from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import AnyHttpUrl, SecretStr, TypeAdapter

from policylens.api.app import create_app
from policylens.settings import PROJECT_ROOT, AppSettings

MODEL_OPTIONS_SCHEMA = PROJECT_ROOT / "specs/009-minimal-ui/contracts/model-options.schema.json"


def _settings(*, provider: str = "mlx", configure_openai: bool = False) -> AppSettings:
    values: dict[str, Any] = {
        "_env_file": None,
        "model_provider": provider,
        "embedding_provider": "local",
    }
    if provider == "mlx" or True:
        values["mlx_model"] = "test-local-model"
    if configure_openai or provider == "openai":
        values["openai_api_key"] = SecretStr("test-only-api-key")
        values["openai_model"] = "test-openai-model"
    return AppSettings(**values)  # type: ignore[call-arg]


def test_model_options_reports_only_configured_model_ids_without_secrets() -> None:
    app = create_app(settings=_settings(configure_openai=True))

    with TestClient(app) as client:
        response = client.get("/model/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_provider"] == "local"
    assert payload["embedding_consent_required"] is False
    schema = json.loads(MODEL_OPTIONS_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    options = {option["provider"]: option for option in payload["options"]}
    assert options["openai"] == {
        "provider": "openai",
        "route": "openai_responses",
        "model_id": "test-openai-model",
        "execution_scope": "external",
        "configured": True,
        "selected_by_default": False,
        "consent_required": True,
        "reasoning_efforts": ["none", "low", "medium", "high"],
    }
    assert options["mlx"]["configured"] is True
    assert options["mlx"]["route"] == "mlx_chat_completions"
    assert options["mlx"]["reasoning_efforts"] == ["none"]
    assert "api_key" not in json.dumps(payload)
    assert "test-only-api-key" not in json.dumps(payload)
    assert "base_url" not in json.dumps(payload)


def test_model_options_marks_unconfigured_provider_without_inventing_model() -> None:
    app = create_app(settings=_settings())

    with TestClient(app) as client:
        response = client.get("/model/options")

    assert response.status_code == 200
    payload = response.json()
    options = {option["provider"]: option for option in payload["options"]}
    assert payload["default_provider"] == "mlx"
    assert options["openai"]["configured"] is False
    assert options["openai"]["model_id"] is None
    assert options["mlx"]["configured"] is True


def test_model_options_advertises_reasoning_for_responses_enabled_foundry() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-api-key"),
        openai_deployment_model="test-foundry-model",
        openai_base_url=TypeAdapter(AnyHttpUrl).validate_python(
            "https://foundry.example.test/openai/v1"
        ),
        openai_use_responses_api=True,
        mlx_model="test-local-model",
        embedding_provider="local",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/model/options")

    assert response.status_code == 200
    options = {option["provider"]: option for option in response.json()["options"]}
    assert options["openai"]["reasoning_efforts"] == ["none", "low", "medium", "high"]
    assert options["openai"]["route"] == "openai_responses"


def test_model_options_limits_custom_chat_completions_to_no_reasoning_effort() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="openai",
        openai_api_key=SecretStr("test-only-api-key"),
        openai_deployment_model="test-foundry-model",
        openai_base_url=TypeAdapter(AnyHttpUrl).validate_python(
            "https://foundry.example.test/openai/v1"
        ),
        mlx_model="test-local-model",
        embedding_provider="local",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/model/options")

    assert response.status_code == 200
    options = {option["provider"]: option for option in response.json()["options"]}
    assert options["openai"]["route"] == "openai_chat_completions"
    assert options["openai"]["reasoning_efforts"] == ["none"]


def test_model_options_requires_fresh_consent_for_external_embeddings() -> None:
    settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-local-model",
        embedding_provider="openai",
        openai_api_key=SecretStr("test-only-api-key"),
        openai_embedding_model="text-embedding-3-small",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/model/options")

    assert response.status_code == 200
    assert response.json()["embedding_provider"] == "openai"
    assert response.json()["embedding_consent_required"] is True
