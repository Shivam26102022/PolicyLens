import sys

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from policylens.api.app import create_app
from policylens.api.mcp_probe import MCPProbeResult, MCPProbeSettings, probe_mcp
from policylens.mcp.client import MCPClientError
from policylens.retrieval.indexing import IndexBuildError
from policylens.retrieval.models import EmbeddingDescriptor
from policylens.settings import AppSettings


def test_liveness_returns_a_versioned_non_secret_contract() -> None:
    settings = AppSettings(
        model_provider="mlx",
        mlx_model="test-model",
        embedding_provider="local",
        mcp_server_command="uv run --package policylens-mcp python -m policylens_mcp",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "service": "policylens-api",
        "version": "0.1.0",
        "status": "alive",
        "components": {"api": "ready"},
    }


@pytest.mark.anyio
async def test_vercel_initializes_app_state_without_asgi_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_DEPLOYMENT_MODEL",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/model/options")

    assert response.status_code == 200
    openai_option = next(
        option for option in response.json()["options"] if option["provider"] == "openai"
    )
    assert openai_option["configured"] is False


def test_readiness_reports_mcp_timeout_and_missing_index_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings(
        model_provider="mlx",
        mlx_model="test-model",
        embedding_provider="local",
        mcp_server_command="uv run --package policylens-mcp python -m policylens_mcp",
    )

    async def timed_out_probe(_: AppSettings) -> MCPProbeResult:
        return MCPProbeResult(status="unavailable", error_code="MCP_TIMEOUT")

    def missing_index(*_: object) -> EmbeddingDescriptor:
        raise IndexBuildError("INDEX_NOT_ACTIVE", "No active index")

    monkeypatch.setattr("policylens.api.health.active_embedding_descriptor", missing_index)

    app = create_app(settings=settings, mcp_probe=timed_out_probe)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "schema_version": "1.0",
        "service": "policylens-api",
        "version": "0.1.0",
        "status": "degraded",
        "components": {
            "api": "ready",
            "generation": "ready",
            "embedding": "not_configured",
            "retrieval": "not_configured",
            "mcp": "unavailable",
        },
        "error_code": "MCP_TIMEOUT",
    }


def test_readiness_preserves_sanitized_index_validation_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings(
        model_provider="mlx",
        mlx_model="test-model",
        embedding_provider="local",
    )

    async def ready_probe(_: AppSettings) -> MCPProbeResult:
        return MCPProbeResult(status="ready")

    def incompatible_index(*_: object) -> EmbeddingDescriptor:
        raise IndexBuildError("CHROMA_CHECKSUM_MISMATCH", "internal path omitted")

    monkeypatch.setattr("policylens.api.health.active_embedding_descriptor", incompatible_index)
    app = create_app(settings=settings, mcp_probe=ready_probe)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error_code"] == "CHROMA_CHECKSUM_MISMATCH"
    assert response.json()["components"]["retrieval"] == "unavailable"


def test_readiness_reports_compatible_retrieval_index(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings(
        model_provider="mlx",
        mlx_model="test-model",
        embedding_provider="local",
        local_embedding_model="BAAI/bge-small-en-v1.5",
    )
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="BAAI/bge-small-en-v1.5",
        package_version="0.9.1",
        model_revision="snapshot",
        model_sha256="a" * 64,
        licence="mit",
        pooling="first-token CLS",
        tokenizer="BAAI/bge-small-en-v1.5",
        query_method="query_embed",
        passage_method="passage_embed",
        dimension=384,
        normalized=True,
        max_input_tokens=512,
    )

    async def ready_probe(_: AppSettings) -> MCPProbeResult:
        return MCPProbeResult(status="ready")

    monkeypatch.setattr(
        "policylens.api.health.active_embedding_descriptor",
        lambda *_: descriptor,
    )
    app = create_app(settings=settings, mcp_probe=ready_probe)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["components"]["embedding"] == "ready"
    assert response.json()["components"]["retrieval"] == "ready"
    assert response.json()["components"]["generation"] == "ready"
    assert response.json()["status"] == "ready"


def test_openapi_uses_the_canonical_api_title() -> None:
    settings = AppSettings(
        model_provider="mlx",
        mlx_model="test-model",
        embedding_provider="local",
        mcp_server_command="uv run --package policylens-mcp python -m policylens_mcp",
    )

    assert create_app(settings=settings).openapi()["info"]["title"] == "PolicyLens API"


def make_probe_settings(command: str, timeout: int = 10) -> MCPProbeSettings:
    return MCPProbeSettings(
        mcp_server_command=command,
        mcp_timeout_seconds=timeout,
        _env_file=None,  # type: ignore[call-arg]
    )


def test_mcp_probe_accepts_the_expected_server_identity() -> None:
    result = anyio.run(
        probe_mcp,
        make_probe_settings(f"{sys.executable} -m policylens_mcp"),
    )

    assert result.status == "ready"
    assert result.error_code is None


def test_mcp_probe_reports_empty_command() -> None:
    result = anyio.run(probe_mcp, make_probe_settings(""))

    assert result.status == "unavailable"
    assert result.error_code == "MCP_UNAVAILABLE"


def test_mcp_probe_rejects_an_unexpected_server_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAdapter:
        def __init__(self, _settings: MCPProbeSettings) -> None:
            pass

        async def probe(self) -> None:
            raise MCPClientError("MCP_IDENTITY_MISMATCH", "identity mismatch")

    monkeypatch.setattr("policylens.api.mcp_probe.MCPStatisticsAdapter", FakeAdapter)

    result = anyio.run(probe_mcp, make_probe_settings("python -m ignored"))

    assert result.status == "unavailable"
    assert result.error_code == "MCP_IDENTITY_MISMATCH"


def test_mcp_probe_reports_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimedOutAdapter:
        def __init__(self, _settings: MCPProbeSettings) -> None:
            pass

        async def probe(self) -> None:
            raise MCPClientError("MCP_TIMEOUT", "probe timed out", transient=True)

    monkeypatch.setattr("policylens.api.mcp_probe.MCPStatisticsAdapter", TimedOutAdapter)

    result = anyio.run(
        probe_mcp,
        make_probe_settings("python -m ignored", timeout=1),
    )

    assert result.status == "unavailable"
    assert result.error_code == "MCP_TIMEOUT"


def test_mcp_probe_sanitizes_startup_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailedAdapter:
        def __init__(self, _settings: MCPProbeSettings) -> None:
            pass

        async def probe(self) -> None:
            raise RuntimeError("sensitive subprocess output")

    monkeypatch.setattr("policylens.api.mcp_probe.MCPStatisticsAdapter", FailedAdapter)

    result = anyio.run(probe_mcp, make_probe_settings("python -m ignored"))

    assert result.status == "unavailable"
    assert result.error_code == "MCP_UNAVAILABLE"
    assert "sensitive" not in result.model_dump_json()
