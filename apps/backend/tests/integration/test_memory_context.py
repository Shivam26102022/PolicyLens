from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from policylens.agent_runtime.models import (
    AgentAnswerRequest,
    AgentAnswerResponse,
    AgentClaim,
)
from policylens.api.app import create_app
from policylens.conversations.memory import (
    ConversationMemory,
    ConversationMemoryError,
)
from policylens.conversations.store import ConversationStore
from policylens.retrieval.models import Citation
from policylens.settings import AppSettings

HASH = "a" * 64


class MemoryRecordingRuntime:
    def __init__(self) -> None:
        self.request: AgentAnswerRequest | None = None
        self.memory_context: tuple[ConversationMemory, ...] = ()

    async def answer(
        self,
        request: AgentAnswerRequest,
        *,
        event_listener=None,
        memory_context: tuple[ConversationMemory, ...] = (),
    ) -> AgentAnswerResponse:
        del event_listener
        self.request = request
        self.memory_context = memory_context
        claim = AgentClaim(
            claim_id="claim-1",
            text="Synthetic current-run answer.",
            citations=(
                Citation(
                    claim_id="claim-1",
                    source_id="synthetic-source",
                    title="Synthetic source",
                    passage_id="sha256:" + "b" * 64,
                    page_start=1,
                    page_end=1,
                    excerpt="Synthetic current-run answer.",
                    source_content_sha256=HASH,
                    retrieval_rank=1,
                    retrieval_score=0.5,
                    retrieval_mode="hybrid",
                ),
            ),
        )
        return AgentAnswerResponse(
            run_id=uuid4(),
            trace_id=uuid4(),
            index_version=HASH,
            status="answered",
            answer=claim.text,
            claims=(claim,),
            provider="mlx",
            model="test-model",
            prompt_version="agent-v1",
            events=(),
        )


class FakeMemoryService:
    def __init__(
        self,
        memories: tuple[ConversationMemory, ...] = (),
        *,
        retrieval_error: ConversationMemoryError | None = None,
        write_error: ConversationMemoryError | None = None,
    ) -> None:
        self.memories = memories
        self.retrieval_error = retrieval_error
        self.write_error = write_error
        self.search_calls: list[tuple[UUID, str, int]] = []
        self.store_calls: list[tuple[UUID, UUID, UUID, str, str]] = []

    def search(
        self,
        workspace_id: UUID,
        query: str,
        *,
        limit: int,
    ) -> tuple[ConversationMemory, ...]:
        self.search_calls.append((workspace_id, query, limit))
        if self.retrieval_error is not None:
            raise self.retrieval_error
        return tuple(memory for memory in self.memories if memory.workspace_id == workspace_id)[
            :limit
        ]

    def store(
        self,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        user_content: str,
        assistant_content: str,
        *,
        created_at=None,
    ) -> None:
        del created_at
        if self.write_error is not None:
            raise self.write_error
        self.store_calls.append(
            (
                workspace_id,
                session_id,
                turn_id,
                user_content,
                assistant_content,
            )
        )


def _settings(*, embedding_provider: str = "local") -> AppSettings:
    values: dict[str, Any] = {
        "_env_file": None,
        "model_provider": "mlx",
        "mlx_model": "test-model",
        "embedding_provider": embedding_provider,
    }
    if embedding_provider == "openai":
        values["openai_api_key"] = SecretStr("test-only-api-key")
        values["openai_embedding_model"] = "text-embedding-3-small"
    return AppSettings(**values)  # type: ignore[call-arg]


def _memory(workspace_id: UUID, session_id: UUID) -> ConversationMemory:
    return ConversationMemory(
        memory_id=str(uuid4()),
        workspace_id=workspace_id,
        session_id=session_id,
        content="Synthetic prior conversation memory.",
        created_at="2026-10-27T00:00:00Z",
        distance=0.1,
    )


def _request(workspace_id: UUID, session_id: UUID, *, allow_embeddings: bool = False):
    return {
        "schema_version": "1.0",
        "query": "synthetic current question",
        "mode": "hybrid",
        "provider": "mlx",
        "reasoning_effort": "none",
        "session_id": str(session_id),
        "allow_external_embeddings": allow_embeddings,
    }


def _app(
    store: ConversationStore,
    runtime: MemoryRecordingRuntime,
    memory: FakeMemoryService,
    *,
    settings: AppSettings | None = None,
):
    return create_app(
        settings=settings or _settings(),
        agent_runtime=runtime,
        conversation_store=store,
        conversation_memory_service=memory,  # type: ignore[arg-type]
    )


def _workspace_session(
    store: ConversationStore,
    *,
    long_memory_enabled: bool = True,
) -> tuple[UUID, UUID]:
    workspace_id = uuid4()
    store.create_workspace(
        workspace_id,
        data_use_acknowledged=True,
        long_memory_enabled=long_memory_enabled,
    )
    session = store.create_session(workspace_id)
    return workspace_id, session.session_id


def test_memory_recall_is_same_workspace_and_cross_session_only(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id, active_session_id = _workspace_session(store)
    prior_session_id = uuid4()
    other_workspace = uuid4()
    same_workspace_memory = _memory(workspace_id, prior_session_id)
    foreign_memory = _memory(other_workspace, uuid4())
    memory = FakeMemoryService((same_workspace_memory, foreign_memory))
    runtime = MemoryRecordingRuntime()
    app = _app(store, runtime, memory)

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json=_request(workspace_id, active_session_id),
        )

    assert response.status_code == 200
    assert runtime.memory_context == (same_workspace_memory,)
    assert memory.search_calls == [(workspace_id, "synthetic current question", 5)]
    assert response.json()["session_context"]["memory_retrieval_status"] == "used"
    assert response.json()["session_context"]["retrieved_memory_count"] == 1
    assert response.json()["claims"][0]["citations"][0]["source_id"] == ("synthetic-source")
    assert "Synthetic prior conversation memory." not in response.text


def test_memory_retrieval_failure_is_visible_without_leaking_payloads(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id, session_id = _workspace_session(store)
    memory = FakeMemoryService(
        retrieval_error=ConversationMemoryError(
            "MEMORY_RETRIEVAL_UNAVAILABLE", "private adapter detail"
        )
    )
    runtime = MemoryRecordingRuntime()

    with TestClient(_app(store, runtime, memory)) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json=_request(workspace_id, session_id),
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "answered"
    assert payload["session_context"]["memory_retrieval_status"] == "unavailable"
    assert payload["session_context"]["retrieved_memory_count"] == 0
    retrieval_event = next(
        event for event in payload["events"] if event["event_type"] == "memory_retrieval_completed"
    )
    assert retrieval_event["status"] == "failed"
    assert retrieval_event["error_code"] == "MEMORY_RETRIEVAL_UNAVAILABLE"
    assert "private adapter detail" not in response.text


def test_embedding_identity_mismatch_is_reported_and_turn_completes_safely(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id, session_id = _workspace_session(store)
    memory = FakeMemoryService(
        retrieval_error=ConversationMemoryError(
            "MEMORY_EMBEDDING_IDENTITY_MISMATCH", "private mismatch details"
        )
    )
    runtime = MemoryRecordingRuntime()

    with TestClient(_app(store, runtime, memory)) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json=_request(workspace_id, session_id),
        )

    assert response.status_code == 200
    assert response.json()["session_context"]["memory_retrieval_status"] == ("embedding_mismatch")
    assert response.json()["events"][1]["error_code"] == ("MEMORY_EMBEDDING_IDENTITY_MISMATCH")
    assert "private mismatch details" not in response.text


def test_external_embedding_consent_is_required_before_any_session_processing(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id, session_id = _workspace_session(store)
    memory = FakeMemoryService((_memory(workspace_id, uuid4()),))
    runtime = MemoryRecordingRuntime()

    with TestClient(
        _app(
            store,
            runtime,
            memory,
            settings=_settings(embedding_provider="openai"),
        )
    ) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json=_request(workspace_id, session_id),
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "EXTERNAL_EMBEDDING_CONSENT_REQUIRED"
    assert runtime.request is None
    assert memory.search_calls == []
    assert store.count_turns(workspace_id, session_id) == 0


def test_external_embedding_consent_allows_this_turn_and_memory_write(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id, session_id = _workspace_session(store)
    memory = FakeMemoryService()
    runtime = MemoryRecordingRuntime()

    with TestClient(
        _app(
            store,
            runtime,
            memory,
            settings=_settings(embedding_provider="openai"),
        )
    ) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json=_request(workspace_id, session_id, allow_embeddings=True),
        )

    assert response.status_code == 200
    assert response.json()["session_context"]["memory_write_status"] == "stored"
    assert memory.store_calls[0][0:2] == (workspace_id, session_id)
    assert memory.store_calls[0][3:] == (
        "synthetic current question",
        "Synthetic current-run answer.",
    )


def test_memory_write_failure_is_reported_without_discarding_saved_answer(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id, session_id = _workspace_session(store)
    memory = FakeMemoryService(
        write_error=ConversationMemoryError("MEMORY_WRITE_FAILED", "private vector store detail")
    )
    runtime = MemoryRecordingRuntime()

    with TestClient(_app(store, runtime, memory)) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json=_request(workspace_id, session_id),
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "answered"
    assert payload["session_context"]["persisted"] is True
    assert payload["session_context"]["memory_write_status"] == "failed"
    write_event = next(
        event for event in payload["events"] if event["event_type"] == "memory_write_completed"
    )
    assert write_event["status"] == "failed"
    assert write_event["error_code"] == "MEMORY_WRITE_FAILED"
    assert store.list_turns(workspace_id, session_id).items[0].status == "completed"
    assert "private vector store detail" not in response.text
