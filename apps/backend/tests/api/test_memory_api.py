from __future__ import annotations

import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from policylens.api.app import create_app
from policylens.conversations.memory import ConversationMemoryError
from policylens.conversations.store import ConversationStore
from policylens.settings import AppSettings


class MemoryServiceStub:
    def __init__(self) -> None:
        self.clear_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.clear_calls: list[UUID] = []
        self.delete_calls: list[tuple[UUID, UUID]] = []
        self.events: list[str] = []

    def clear_workspace(self, workspace_id: UUID) -> int:
        self.events.append("clear_memories")
        self.clear_calls.append(workspace_id)
        if self.clear_error is not None:
            raise self.clear_error
        return 3

    def delete_session(self, workspace_id: UUID, session_id: UUID) -> int:
        self.events.append("delete_session_memories")
        self.delete_calls.append((workspace_id, session_id))
        if self.delete_error is not None:
            raise self.delete_error
        return 1


def _settings() -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-only",
        embedding_provider="local",
    )


def _client(
    store: ConversationStore,
    memory: MemoryServiceStub,
) -> TestClient:
    app = create_app(
        settings=_settings(),
        conversation_store=store,
        conversation_memory_service=memory,  # type: ignore[arg-type]
    )
    return TestClient(app)


def _headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


def test_workspace_preferences_are_scoped_and_memory_is_independently_opt_in(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    memory = MemoryServiceStub()
    workspace_id = uuid4()
    other_workspace = uuid4()
    store.update_workspace_preferences(other_workspace, data_use_acknowledged=False)

    with _client(store, memory) as client:
        initial = client.get(
            "/sessions/preferences",
            headers=_headers(workspace_id),
        )
        enabled_without_ack = client.put(
            "/sessions/preferences",
            headers=_headers(other_workspace),
            json={
                "schema_version": "1.0",
                "long_memory_enabled": True,
            },
        )
        other_preferences = client.get(
            "/sessions/preferences",
            headers=_headers(other_workspace),
        )
        acknowledged = client.put(
            "/sessions/preferences",
            headers=_headers(workspace_id),
            json={
                "schema_version": "1.0",
                "data_use_acknowledged": True,
                "long_memory_enabled": True,
            },
        )

    assert initial.status_code == 200
    assert enabled_without_ack.status_code == 200
    assert enabled_without_ack.json()["long_memory_enabled"] is True
    assert acknowledged.status_code == 200
    assert acknowledged.json()["long_memory_enabled"] is True
    assert other_preferences.status_code == 200
    assert other_preferences.json()["long_memory_enabled"] is True


def test_memory_clear_uses_literal_route_and_returns_workspace_result(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    memory = MemoryServiceStub()
    workspace_id = uuid4()

    with _client(store, memory) as client:
        response = client.delete(
            "/sessions/memories",
            headers=_headers(workspace_id),
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "cleared",
        "deleted_count": 3,
    }
    assert memory.clear_calls == [workspace_id]


def test_memory_clear_failure_is_not_reported_as_success(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    memory = MemoryServiceStub()
    memory.clear_error = ConversationMemoryError(
        "MEMORY_DELETE_FAILED", "private vector store detail"
    )

    with _client(store, memory) as client:
        response = client.delete(
            "/sessions/memories",
            headers=_headers(uuid4()),
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "MEMORY_DELETE_FAILED"
    assert "private vector store detail" not in response.text


def test_session_delete_removes_memories_before_transcript_and_is_workspace_scoped(
    tmp_path,
) -> None:
    class OrderedStore(ConversationStore):
        def delete_session(self, workspace_id: UUID, session_id: UUID) -> bool:
            memory.events.append("delete_transcript")
            return super().delete_session(workspace_id, session_id)

    memory = MemoryServiceStub()
    store = OrderedStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)

    with _client(store, memory) as client:
        response = client.delete(
            f"/sessions/{session.session_id}",
            headers=_headers(workspace_id),
        )

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert memory.events == ["delete_session_memories", "delete_transcript"]
    assert memory.delete_calls == [(workspace_id, session.session_id)]
    assert store.get_session(workspace_id, session.session_id) is None


def test_session_memory_delete_failure_retains_transcript(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    memory = MemoryServiceStub()
    memory.delete_error = ConversationMemoryError(
        "MEMORY_DELETE_FAILED", "private vector store detail"
    )
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)

    with _client(store, memory) as client:
        response = client.delete(
            f"/sessions/{session.session_id}",
            headers=_headers(workspace_id),
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "MEMORY_DELETE_FAILED"
    assert store.get_session(workspace_id, session.session_id) is not None
    assert "private vector store detail" not in response.text


def test_transcript_delete_failure_is_explicit_after_vector_deletion(tmp_path) -> None:
    class FailingStore(ConversationStore):
        def delete_session(self, workspace_id: UUID, session_id: UUID) -> bool:
            raise sqlite3.OperationalError("private database detail")

    memory = MemoryServiceStub()
    store = FailingStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)

    with _client(store, memory) as client:
        response = client.delete(
            f"/sessions/{session.session_id}",
            headers=_headers(workspace_id),
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "SESSION_DELETE_FAILED"
    assert store.get_session(workspace_id, session.session_id) is not None
    assert memory.delete_calls == [(workspace_id, session.session_id)]
    assert "private database detail" not in response.text


def test_session_lookup_failure_does_not_attempt_vector_deletion(tmp_path) -> None:
    class FailingLookupStore(ConversationStore):
        def get_session(self, workspace_id: UUID, session_id: UUID) -> None:
            raise sqlite3.OperationalError("private database detail")

    memory = MemoryServiceStub()
    store = FailingLookupStore(tmp_path / "conversations.sqlite3")

    with _client(store, memory) as client:
        response = client.delete(
            f"/sessions/{uuid4()}",
            headers=_headers(uuid4()),
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "SESSION_DELETE_FAILED"
    assert memory.delete_calls == []
    assert "private database detail" not in response.text


def test_foreign_session_delete_is_indistinguishable_and_does_not_touch_memory(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    memory = MemoryServiceStub()
    owner = uuid4()
    stranger = uuid4()
    store.create_workspace(owner, data_use_acknowledged=True)
    store.create_workspace(stranger, data_use_acknowledged=True)
    session = store.create_session(owner)

    with _client(store, memory) as client:
        foreign = client.delete(
            f"/sessions/{session.session_id}",
            headers=_headers(stranger),
        )
        missing = client.delete(
            f"/sessions/{uuid4()}",
            headers=_headers(stranger),
        )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert memory.delete_calls == []
    assert store.get_session(owner, session.session_id) is not None
