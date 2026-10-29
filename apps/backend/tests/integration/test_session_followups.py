from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from policylens.agent_runtime.models import (
    AgentAnswerRequest,
    AgentAnswerResponse,
    AgentClaim,
)
from policylens.agent_runtime.runtime import AgentExecutionError
from policylens.api.app import create_app
from policylens.conversations.memory import ConversationMemory
from policylens.conversations.store import ConversationStore
from policylens.retrieval.models import Citation
from policylens.settings import AppSettings

HASH = "a" * 64


class RecordingAgentRuntime:
    def __init__(self, error: Exception | None = None) -> None:
        self.request: AgentAnswerRequest | None = None
        self.error = error

    async def answer(
        self,
        request: AgentAnswerRequest,
        *,
        event_listener=None,
        memory_context: tuple[ConversationMemory, ...] = (),
    ) -> AgentAnswerResponse:
        del memory_context
        self.request = request
        if self.error is not None:
            raise self.error
        claim = AgentClaim(
            claim_id="claim-1",
            text="Synthetic answer",
            citations=(
                Citation(
                    claim_id="claim-1",
                    source_id="synthetic-source",
                    title="Synthetic source",
                    passage_id="sha256:" + "b" * 64,
                    page_start=1,
                    page_end=1,
                    excerpt="Synthetic answer",
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


def _settings() -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-model",
        embedding_provider="local",
    )


def test_followup_persists_response_and_uses_only_last_five_pairs(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    other_session = store.create_session(workspace_id)
    for index in range(6):
        turn = store.create_turn(workspace_id, session.session_id, f"question {index}")
        store.complete_turn(
            workspace_id,
            session.session_id,
            turn.turn_id,
            assistant_content=f"answer {index}",
        )
    other_turn = store.create_turn(workspace_id, other_session.session_id, "other session secret")
    store.complete_turn(
        workspace_id,
        other_session.session_id,
        other_turn.turn_id,
        assistant_content="other session answer",
    )

    runtime = RecordingAgentRuntime()
    app = create_app(
        settings=_settings(),
        agent_runtime=runtime,
        conversation_store=store,
    )
    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={
                "schema_version": "1.0",
                "query": "next synthetic question",
                "mode": "hybrid",
                "session_id": str(session.session_id),
                "conversation": [{"role": "user", "content": "caller supplied context"}],
            },
        )
        restored = client.get(
            f"/sessions/{session.session_id}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert response.status_code == 200
    assert runtime.request is not None
    assert len(runtime.request.conversation) == 10
    assert [message.content for message in runtime.request.conversation] == [
        "question 1",
        "answer 1",
        "question 2",
        "answer 2",
        "question 3",
        "answer 3",
        "question 4",
        "answer 4",
        "question 5",
        "answer 5",
    ]
    assert all(
        "caller supplied context" not in message.content
        and "other session secret" not in message.content
        for message in runtime.request.conversation
    )
    assert len(restored.json()["turns"]) == 7
    assert restored.json()["turns"][-1]["user_content"] == "next synthetic question"
    assert restored.json()["turns"][-1]["assistant_content"] == "Synthetic answer"
    assert restored.json()["turns"][-1]["status"] == "completed"
    assert response.json()["session_context"]["persisted"] is True
    assert response.json()["session_context"]["turn_id"] == restored.json()["turns"][-1]["turn_id"]


def test_followup_context_is_loaded_after_reload_without_duplicate_submission(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    turn = store.create_turn(workspace_id, session.session_id, "saved question")
    store.complete_turn(
        workspace_id,
        session.session_id,
        turn.turn_id,
        assistant_content="saved answer",
    )
    app = create_app(settings=_settings(), conversation_store=store)

    with TestClient(app) as client:
        first_load = client.get(
            f"/sessions/{session.session_id}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        second_load = client.get(
            f"/sessions/{session.session_id}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert first_load.status_code == second_load.status_code == 200
    assert first_load.json()["turns"] == second_load.json()["turns"]
    assert len(second_load.json()["turns"]) == 1
    assert second_load.json()["turns"][0]["turn_id"] == str(turn.turn_id)


def test_session_turn_does_not_require_acknowledgement_and_hides_foreign_sessions(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    owner = uuid4()
    other_workspace = uuid4()
    store.create_workspace(owner, data_use_acknowledged=True)
    store.create_workspace(other_workspace, data_use_acknowledged=True)
    session = store.create_session(owner)
    store.update_workspace_preferences(owner, data_use_acknowledged=False)
    runtime = RecordingAgentRuntime()
    app = create_app(
        settings=_settings(),
        agent_runtime=runtime,
        conversation_store=store,
    )

    with TestClient(app) as client:
        unacknowledged = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(owner)},
            json={
                "schema_version": "1.0",
                "query": "synthetic question",
                "mode": "hybrid",
                "session_id": str(session.session_id),
            },
        )
        foreign = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(other_workspace)},
            json={
                "schema_version": "1.0",
                "query": "synthetic question",
                "mode": "hybrid",
                "session_id": str(session.session_id),
            },
        )

    assert unacknowledged.status_code == 200
    assert unacknowledged.json()["status"] == "answered"
    assert foreign.status_code == 404
    assert foreign.json()["error_code"] == "SESSION_NOT_FOUND"
    assert store.count_turns(owner, session.session_id) == 1
    assert runtime.request is not None


def test_missing_session_is_recreated_from_browser_context(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    session_id = uuid4()
    runtime = RecordingAgentRuntime()
    app = create_app(
        settings=_settings(),
        agent_runtime=runtime,
        conversation_store=store,
    )

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={
                "schema_version": "1.0",
                "query": "are you sure",
                "mode": "hybrid",
                "session_id": str(session_id),
                "conversation": [
                    {"role": "user", "content": "earlier question"},
                    {"role": "assistant", "content": "earlier answer"},
                ],
            },
        )

    assert response.status_code == 200
    assert store.count_turns(workspace_id, session_id) == 1
    assert runtime.request is not None
    assert [m.content for m in runtime.request.conversation] == [
        "earlier question",
        "earlier answer",
    ]


def test_failed_agent_run_is_retained_as_failed_turn(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    runtime = RecordingAgentRuntime(error=AgentExecutionError("MODEL_UNAVAILABLE", uuid4()))
    app = create_app(
        settings=_settings(),
        agent_runtime=runtime,
        conversation_store=store,
    )

    with TestClient(app) as client:
        response = client.post(
            "/agent/answer",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={
                "schema_version": "1.0",
                "query": "synthetic question",
                "mode": "hybrid",
                "session_id": str(session.session_id),
            },
        )
        history = client.get(
            f"/sessions/{session.session_id}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "MODEL_UNAVAILABLE"
    assert len(history.json()["turns"]) == 1
    assert history.json()["turns"][0]["status"] == "failed"
