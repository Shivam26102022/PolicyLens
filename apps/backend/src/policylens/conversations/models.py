from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from policylens.retrieval.models import StrictModel

TurnStatus = Literal["in_progress", "completed", "failed"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Workspace(StrictModel):
    workspace_id: UUID
    # Retained for compatibility with existing preference records. It no longer gates chats.
    data_use_acknowledged: bool = True
    data_use_acknowledged_at: datetime | None = None
    long_memory_enabled: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class ConversationSession(StrictModel):
    session_id: UUID
    workspace_id: UUID
    title: str = Field(default="New conversation", min_length=1, max_length=80)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class ConversationTurn(StrictModel):
    turn_id: UUID
    session_id: UUID
    position: int = Field(ge=1)
    user_content: str = Field(min_length=1, max_length=4000)
    assistant_content: str | None = Field(default=None, max_length=12000)
    answer_json: dict[str, object] | None = None
    status: TurnStatus
    created_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_completed_response(self) -> ConversationTurn:
        if self.status == "completed" and not (
            self.assistant_content and self.assistant_content.strip()
        ):
            raise ValueError("completed turn requires an assistant response")
        return self


class SessionPage(StrictModel):
    items: tuple[ConversationSession, ...]
    next_cursor: str | None = None


class ConversationTurnPage(StrictModel):
    items: tuple[ConversationTurn, ...]
    next_before_turn_id: UUID | None = None
