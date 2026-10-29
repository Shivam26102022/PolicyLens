from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from policylens.api.app import create_app
from policylens.conversations.store import ConversationStore
from policylens.settings import AppSettings


def _settings() -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-only",
        embedding_provider="local",
    )


def _client(store: ConversationStore) -> TestClient:
    return TestClient(create_app(settings=_settings(), conversation_store=store))


def test_sessions_require_workspace_header_but_not_data_use_acknowledgement(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()

    with _client(store) as client:
        missing_workspace = client.post("/sessions", json={})
        created_without_acknowledgement = client.post(
            "/sessions",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={},
        )

    assert missing_workspace.status_code in {400, 422}
    assert created_without_acknowledgement.status_code == 201
    assert len(store.list_sessions(workspace_id).items) == 1


def test_cors_allows_workspace_header_for_browser_requests(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")

    with _client(store) as client:
        response = client.options(
            "/sessions",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Workspace-ID",
            },
        )

    assert response.status_code == 200
    assert "x-workspace-id" in response.headers["access-control-allow-headers"].lower()


def test_sessions_can_be_created_listed_and_read_with_ordered_history(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)

    with _client(store) as client:
        created = client.post(
            "/sessions",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={},
        )
        session_id = created.json()["session_id"]
        listed = client.get(
            "/sessions",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        turn = store.create_turn(workspace_id, UUID(session_id), "question")
        store.complete_turn(
            workspace_id,
            UUID(session_id),
            turn.turn_id,
            assistant_content="answer",
            answer_json={"answer": "answer"},
        )
        history = client.get(
            f"/sessions/{session_id}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["sessions"][0]["session_id"] == session_id
    assert history.status_code == 200
    assert [turn["user_content"] for turn in history.json()["turns"]] == ["question"]
    assert history.json()["turns"][0]["answer"]["answer"] == "answer"


def test_foreign_session_is_indistinguishable_from_missing_session(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    owner = uuid4()
    other_workspace = uuid4()
    store.create_workspace(owner, data_use_acknowledged=True)
    store.create_workspace(other_workspace, data_use_acknowledged=True)
    session = store.create_session(owner)

    with _client(store) as client:
        headers = {"X-Workspace-ID": str(other_workspace)}
        foreign = client.get(f"/sessions/{session.session_id}", headers=headers)
        missing = client.get(f"/sessions/{uuid4()}", headers=headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error_code"] == missing.json()["error_code"] == "SESSION_NOT_FOUND"
    assert foreign.json()["message"] == missing.json()["message"]


def test_session_history_paginates_at_one_hundred_turns(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    for index in range(101):
        store.create_turn(workspace_id, session.session_id, f"question {index}")

    with _client(store) as client:
        first = client.get(
            f"/sessions/{session.session_id}?limit=100",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        cursor = first.json()["next_before_turn_id"]
        second = client.get(
            f"/sessions/{session.session_id}?limit=100&before_turn_id={cursor}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert first.status_code == second.status_code == 200
    assert len(first.json()["turns"]) == 100
    assert len(second.json()["turns"]) == 1
    assert second.json()["next_before_turn_id"] is None
