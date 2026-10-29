from pathlib import Path

import pytest
from pydantic import ValidationError

from policylens.settings import AppSettings, get_frontend_origin


def settings_without_dotenv() -> AppSettings:
    return AppSettings(_env_file=None)  # type: ignore[call-arg]


def test_env_example_matches_the_non_secret_configuration_contract() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    env_example = (repository_root / ".env.example").read_text(encoding="utf-8")
    values = {
        key: value
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, _, value in [line.partition("=")]
    }
    expected_keys = {
        "APP_NAME",
        "APP_ENV",
        "LOG_LEVEL",
        "FRONTEND_ORIGIN",
        "VITE_API_BASE_URL",
        "MODEL_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_USE_RESPONSES_API",
        "OPENAI_DEPLOYMENT_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "MLX_BASE_URL",
        "MLX_MODEL",
        "EMBEDDING_PROVIDER",
        "LOCAL_EMBEDDING_MODEL",
        "CHROMA_PERSIST_DIRECTORY",
        "CHROMA_COLLECTION_PREFIX",
        "BM25_INDEX_DIRECTORY",
        "ACTIVE_CORPUS_VERSION",
        "MCP_TRANSPORT",
        "MCP_SERVER_COMMAND",
        "MCP_SERVER_URL",
        "MCP_TIMEOUT_SECONDS",
        "MAX_AGENT_TURNS",
        "MAX_TOOL_CALLS",
        "MAX_TOOL_CALLS_PER_TOOL",
        "MAX_TOOL_RETRIES",
        "MAX_AGENT_OUTPUT_TOKENS",
        "MAX_RETRIEVAL_CANDIDATES",
        "FINAL_CONTEXT_CHUNKS",
        "RERANKER_ENABLED",
        "RERANKER_MODEL",
        "RERANKER_CANDIDATE_COUNT",
        "REQUEST_TIMEOUT_SECONDS",
    }

    assert set(values) == expected_keys
    assert values["APP_NAME"] == "PolicyLens"
    assert values["MODEL_PROVIDER"] == "openai"
    assert values["EMBEDDING_PROVIDER"] == "local"
    assert values["RERANKER_ENABLED"] == "true"
    assert values["RERANKER_MODEL"] == "jinaai/jina-reranker-v1-tiny-en"
    assert values["OPENAI_API_KEY"] == ""
    assert values["OPENAI_BASE_URL"] == ""
    assert values["OPENAI_USE_RESPONSES_API"] == "false"
    assert values["OPENAI_DEPLOYMENT_MODEL"] == "gpt-6-luna"
    assert {key for key in values if key.startswith("VITE_")} == {"VITE_API_BASE_URL"}
    assert "sk-" not in env_example


def test_frontend_origin_uses_the_typed_environment_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://research.local")

    assert get_frontend_origin() == "http://research.local"


def test_generation_and_embedding_providers_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-generation-model")
    monkeypatch.delenv("OPENAI_DEPLOYMENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    settings = settings_without_dotenv()

    assert settings.model_provider == "openai"
    assert settings.embedding_provider == "local"

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "test-embedding-model")

    settings = settings_without_dotenv()

    assert settings.model_provider == "openai"
    assert settings.embedding_provider == "openai"


def test_local_providers_do_not_require_an_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "local")
    monkeypatch.setenv("MLX_MODEL", "test-local-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_DEPLOYMENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = settings_without_dotenv()

    assert settings.model_provider == "mlx"
    assert settings.embedding_provider == "local"
    assert settings.openai_api_key is None


def test_openai_embedding_requires_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "mlx")
    monkeypatch.setenv("MLX_MODEL", "test-local-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "test-embedding-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        settings_without_dotenv()


@pytest.mark.parametrize(
    ("api_key", "generation_model"),
    [(None, "test-generation-model"), ("sk-test-not-a-real-key", None)],
)
def test_openai_generation_requires_key_and_model(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str | None,
    generation_model: str | None,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_DEPLOYMENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    if api_key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
    if generation_model is not None:
        monkeypatch.setenv("OPENAI_MODEL", generation_model)

    with pytest.raises(ValidationError, match="OPENAI_"):
        settings_without_dotenv()


def test_openai_embedding_requires_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "mlx")
    monkeypatch.setenv("MLX_MODEL", "test-local-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    with pytest.raises(ValidationError, match="OPENAI_EMBEDDING_MODEL"):
        settings_without_dotenv()


def test_unknown_model_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "unsupported")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")

    with pytest.raises(ValidationError):
        settings_without_dotenv()


def test_invalid_budget_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "mlx")
    monkeypatch.setenv("MLX_MODEL", "test-local-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValidationError):
        settings_without_dotenv()


def test_foundry_deployment_model_can_be_loaded_without_enabling_external_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_MODEL", "unused-standard-model")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = settings_without_dotenv()
    assert settings.effective_openai_model == "gpt-6-luna"
    assert settings.openai_base_url is None


def test_foundry_deployment_is_effective_model_when_explicitly_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_DEPLOYMENT_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://foundry.example.test/openai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "unused-standard-model")

    settings = settings_without_dotenv()

    assert settings.effective_openai_model == "gpt-6-luna"
    assert str(settings.openai_base_url) == "https://foundry.example.test/openai/v1"


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("MAX_TOOL_CALLS_PER_TOOL", "0"),
        ("MAX_TOOL_RETRIES", "4"),
        ("MAX_AGENT_OUTPUT_TOKENS", "0"),
    ],
)
def test_invalid_agent_budget_is_rejected(
    monkeypatch: pytest.MonkeyPatch, setting: str, value: str
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "mlx")
    monkeypatch.setenv("MLX_MODEL", "test-local-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv(setting, value)

    with pytest.raises(ValidationError):
        settings_without_dotenv()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://user:pass@127.0.0.1:8080/v1",
        "http://127.0.0.1:8080/v1?token=not-a-secret",
        "http://127.0.0.1:8080/v1#fragment",
        "http://127.0.0.1:8080/custom",
    ],
)
def test_mlx_endpoint_rejects_credentials_query_fragment_and_custom_path(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "mlx")
    monkeypatch.setenv("MLX_MODEL", "test-local-model")
    monkeypatch.setenv("MLX_BASE_URL", base_url)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")

    with pytest.raises(ValidationError):
        settings_without_dotenv()
