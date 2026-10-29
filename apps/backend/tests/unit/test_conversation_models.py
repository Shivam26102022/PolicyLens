from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from policylens.conversations.models import ConversationSession, ConversationTurn, Workspace


def test_workspace_preferences_default_to_safe_values() -> None:
    workspace = Workspace(workspace_id=uuid4())

    assert workspace.data_use_acknowledged is True
    assert workspace.long_memory_enabled is False
    assert workspace.data_use_acknowledged_at is None


def test_workspace_requires_uuid_identifier() -> None:
    with pytest.raises(ValidationError):
        Workspace.model_validate({"workspace_id": "not-a-uuid"})


def test_session_title_is_bounded() -> None:
    workspace_id = uuid4()
    session = ConversationSession(
        session_id=uuid4(),
        workspace_id=workspace_id,
        title="x" * 80,
    )

    assert len(session.title) == 80
    with pytest.raises(ValidationError):
        ConversationSession(
            session_id=uuid4(),
            workspace_id=workspace_id,
            title="x" * 81,
        )


def test_turn_content_limits_and_statuses() -> None:
    session_id = uuid4()
    completed = ConversationTurn(
        turn_id=uuid4(),
        session_id=session_id,
        position=1,
        user_content="u" * 4000,
        assistant_content="a" * 12000,
        status="completed",
    )
    in_progress = ConversationTurn(
        turn_id=uuid4(),
        session_id=session_id,
        position=2,
        user_content="Question",
        status="in_progress",
    )
    failed = ConversationTurn(
        turn_id=uuid4(),
        session_id=session_id,
        position=3,
        user_content="Question",
        status="failed",
    )

    assert completed.status == "completed"
    assert in_progress.status == "in_progress"
    assert failed.status == "failed"

    with pytest.raises(ValidationError):
        ConversationTurn(
            turn_id=uuid4(),
            session_id=session_id,
            position=4,
            user_content="u" * 4001,
            status="in_progress",
        )
    with pytest.raises(ValidationError):
        ConversationTurn(
            turn_id=uuid4(),
            session_id=session_id,
            position=4,
            user_content="Question",
            assistant_content="a" * 12001,
            status="completed",
        )


def test_turn_requires_positive_position_and_known_state() -> None:
    session_id = uuid4()
    with pytest.raises(ValidationError):
        ConversationTurn(
            turn_id=uuid4(),
            session_id=session_id,
            position=0,
            user_content="Question",
            status="in_progress",
        )
    with pytest.raises(ValidationError):
        ConversationTurn.model_validate(
            {
                "turn_id": uuid4(),
                "session_id": session_id,
                "position": 1,
                "user_content": "Question",
                "status": "pending",
            }
        )
