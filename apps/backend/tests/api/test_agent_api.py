from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from policylens.agent_runtime.models import (
    AgentAnswerRequest,
    AgentAnswerResponse,
    AgentClaim,
    AgentEvent,
    AgentRunState,
)
from policylens.agent_runtime.runtime import AgentExecutionError
from policylens.api.app import create_app
from policylens.api.mcp_probe import MCPProbeResult
from policylens.conversations.memory import ConversationMemory
from policylens.retrieval.citations import CitationValidator, RetrievalRunRegistry
from policylens.retrieval.models import Citation
from policylens.settings import AppSettings

HASH = "a" * 64
RUN_ID = UUID("9a734d29-8d52-4afe-97f6-14963f251f1b")
TRACE_ID = UUID("7c03f0e0-9921-4b54-bb6b-4f048ad788cb")


class FakeAgentRuntime:
    def __init__(self, response: AgentAnswerResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.request: AgentAnswerRequest | None = None

    async def answer(
        self,
        request: AgentAnswerRequest,
        *,
        event_listener=None,
        memory_context: tuple[ConversationMemory, ...] = (),
    ) -> AgentAnswerResponse:
        del memory_context
        self.request = request
        if event_listener is not None:
            event_listener(
                AgentEvent(
                    sequence=1,
                    state=AgentRunState.RETRIEVING,
                    event_type="state_transition",
                    status="succeeded",
                )
            )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


async def _ready_probe(_: AppSettings) -> MCPProbeResult:
    return MCPProbeResult(status="ready")


def _settings() -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-only",
        embedding_provider="local",
    )


def _response() -> AgentAnswerResponse:
    citation = Citation(
        claim_id="claim-1",
        source_id="wb-youth-unemployment-1524-2015-2025",
        title="Youth unemployment",
        passage_id="sha256:" + "b" * 64,
        page_start=1,
        page_end=1,
        section_path=("Youth unemployment",),
        excerpt="Youth unemployment was 16 percent",
        source_content_sha256=HASH,
        retrieval_rank=1,
        retrieval_score=0.8,
        retrieval_mode="hybrid",
    )
    return AgentAnswerResponse(
        run_id=RUN_ID,
        trace_id=TRACE_ID,
        index_version=HASH,
        status="answered",
        answer="Youth unemployment was 16 percent",
        claims=(
            AgentClaim(
                claim_id="claim-1",
                text="Youth unemployment was 16 percent",
                citations=(citation,),
            ),
        ),
        provider="openai",
        model="test-generation-model",
        prompt_version="agent-v1",
        events=(),
    )


def _app(agent_runtime: Any):
    return create_app(
        settings=_settings(),
        mcp_probe=_ready_probe,
        agent_runtime=agent_runtime,
    )


def test_agent_answer_endpoint_returns_typed_claims_and_trace_metadata() -> None:
    runtime = FakeAgentRuntime(response=_response())
    app = _app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            json={
                "schema_version": "1.0",
                "query": "youth unemployment",
                "mode": "hybrid",
                "top_k": 4,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["run_id"] == str(RUN_ID)
    assert response.json()["trace_id"] == str(TRACE_ID)
    assert response.json()["claims"][0]["citations"][0]["passage_id"] == "sha256:" + "b" * 64
    assert runtime.request is not None
    assert runtime.request.query == "youth unemployment"


def test_agent_answer_endpoint_returns_stable_runtime_error() -> None:
    runtime = FakeAgentRuntime(error=AgentExecutionError("MODEL_UNAVAILABLE", TRACE_ID))
    app = _app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            json={"schema_version": "1.0", "query": "question", "mode": "bm25"},
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "MODEL_UNAVAILABLE"
    assert response.json()["trace_id"] == str(TRACE_ID)


def test_agent_answer_stream_emits_typed_progress_and_final_result() -> None:
    runtime = FakeAgentRuntime(response=_response())
    app = _app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer/stream",
            json={
                "schema_version": "1.0",
                "query": "youth unemployment",
                "mode": "hybrid",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress\n" in response.text
    assert '"event_type":"state_transition"' in response.text
    assert "event: result\n" in response.text
    assert '"status":"answered"' in response.text
    assert runtime.request is not None


def test_agent_answer_rejects_unsupported_effort_before_runtime() -> None:
    runtime = FakeAgentRuntime(response=_response())
    app = _app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            json={
                "schema_version": "1.0",
                "query": "question",
                "mode": "bm25",
                "reasoning_effort": "high",
            },
        )

    assert response.status_code == 422
    assert response.json()["error_code"] == "MODEL_CAPABILITY_UNSUPPORTED"
    assert runtime.request is None


def test_agent_answer_endpoint_rejects_caller_permission_scope() -> None:
    app = _app(FakeAgentRuntime(response=_response()))

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            json={
                "schema_version": "1.0",
                "query": "question",
                "mode": "bm25",
                "filters": {"permission_scope": ["restricted"]},
            },
        )

    assert response.status_code == 422


def test_agent_answer_rejects_external_provider_without_per_run_consent() -> None:
    runtime = FakeAgentRuntime(response=_response())
    app = _app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            json={
                "schema_version": "1.0",
                "query": "SYNTHETIC: research question",
                "mode": "hybrid",
                "provider": "openai",
                "allow_external_provider": False,
            },
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "EXTERNAL_PROVIDER_CONSENT_REQUIRED"
    assert runtime.request is None


def test_agent_answer_rejects_unconfigured_provider_before_runtime() -> None:
    runtime = FakeAgentRuntime(response=_response())
    app = _app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            json={
                "schema_version": "1.0",
                "query": "SYNTHETIC: research question",
                "mode": "hybrid",
                "provider": "openai",
                "allow_external_provider": True,
            },
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "MODEL_UNAVAILABLE"
    assert runtime.request is None


def test_agent_answer_uses_explicitly_selected_configured_provider_and_caches_runtime() -> None:
    from pydantic import SecretStr

    settings = AppSettings(
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-local-model",
        openai_api_key=SecretStr("test-only-api-key"),
        openai_model="test-openai-model",
        embedding_provider="local",
    )  # type: ignore[call-arg]
    factory_providers: list[str] = []
    runtime = FakeAgentRuntime(response=_response())

    def runtime_factory(selected_settings, _service, _validator, _adapter):
        factory_providers.append(selected_settings.model_provider)
        return runtime

    app = create_app(
        settings=settings,
        agent_runtime_factory=runtime_factory,
        retrieval_service=object(),
        citation_validator=CitationValidator(RetrievalRunRegistry()),
    )
    request = {
        "schema_version": "1.0",
        "query": "SYNTHETIC: research question",
        "mode": "hybrid",
        "provider": "openai",
        "allow_external_provider": True,
    }

    with TestClient(app) as client:
        first = client.post("/agent/answer", json=request)
        second = client.post("/agent/answer", json=request)

    assert first.status_code == 200
    assert second.status_code == 200
    assert factory_providers == ["openai"]
