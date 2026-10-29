from __future__ import annotations

from uuid import uuid4

import pytest

from policylens.conversations.store import ConversationNotFoundError, ConversationStore


@pytest.fixture
def store(tmp_path):
    return ConversationStore(tmp_path / "conversations.sqlite3")


def test_store_isolates_sessions_by_workspace(store: ConversationStore) -> None:
    owner = uuid4()
    other_workspace = uuid4()
    store.create_workspace(owner, data_use_acknowledged=True)
    store.create_workspace(other_workspace, data_use_acknowledged=True)
    session = store.create_session(owner)

    assert store.get_session(owner, session.session_id) == session
    assert store.get_session(other_workspace, session.session_id) is None
    with pytest.raises(ConversationNotFoundError):
        store.create_turn(other_workspace, session.session_id, "foreign request")


def test_turn_positions_are_unique_and_ordered(store: ConversationStore) -> None:
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)

    first = store.create_turn(workspace_id, session.session_id, "first")
    second = store.create_turn(workspace_id, session.session_id, "second")

    assert (first.position, second.position) == (1, 2)


def test_whitespace_only_first_turn_keeps_default_title(store: ConversationStore) -> None:
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)

    store.create_turn(workspace_id, session.session_id, " \n ")

    updated_session = store.get_session(workspace_id, session.session_id)
    assert updated_session is not None
    assert updated_session.title == "New conversation"


def test_hot_context_selects_only_completed_turns(store: ConversationStore) -> None:
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    completed = store.create_turn(workspace_id, session.session_id, "completed question")
    store.complete_turn(
        workspace_id,
        session.session_id,
        completed.turn_id,
        assistant_content="completed answer",
    )
    failed = store.create_turn(workspace_id, session.session_id, "failed question")
    store.fail_turn(workspace_id, session.session_id, failed.turn_id)
    pending = store.create_turn(workspace_id, session.session_id, "pending question")

    recent = store.get_recent_completed_turns(workspace_id, session.session_id, limit=5)

    assert [turn.turn_id for turn in recent] == [completed.turn_id]
    assert recent[0].assistant_content == "completed answer"
    assert pending.status == "in_progress"


def test_transcript_pagination_is_bounded_to_one_hundred_turns(
    store: ConversationStore,
) -> None:
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    for index in range(101):
        store.create_turn(workspace_id, session.session_id, f"question {index}")

    page = store.list_turns(workspace_id, session.session_id, limit=100)

    assert len(page.items) == 100
    assert page.next_before_turn_id is not None
    older_page = store.list_turns(
        workspace_id,
        session.session_id,
        limit=100,
        before_turn_id=page.next_before_turn_id,
    )
    assert len(older_page.items) == 1
    assert older_page.next_before_turn_id is None


def test_deleting_session_cascades_to_transcript(store: ConversationStore) -> None:
    workspace_id = uuid4()
    store.create_workspace(workspace_id, data_use_acknowledged=True)
    session = store.create_session(workspace_id)
    store.create_turn(workspace_id, session.session_id, "saved question")

    assert store.delete_session(workspace_id, session.session_id) is True
    assert store.get_session(workspace_id, session.session_id) is None
    with pytest.raises(ConversationNotFoundError):
        store.list_turns(workspace_id, session.session_id)
