from __future__ import annotations

import sqlite3
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from policylens.conversations.memory import (
    ConversationMemoryError,
    ConversationMemoryService,
)
from policylens.conversations.models import ConversationSession, ConversationTurn, Workspace
from policylens.conversations.store import (
    ConversationNotFoundError,
    ConversationStore,
)
from policylens.retrieval.models import StrictModel

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreateRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    title: str | None = Field(default=None, min_length=1, max_length=80)


class SessionSummaryResponse(StrictModel):
    session_id: UUID
    title: str
    created_at: str
    updated_at: str
    turn_count: int = Field(ge=0)


class SessionListResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    sessions: tuple[SessionSummaryResponse, ...]
    next_cursor: str | None = None


class SessionTurnResponse(StrictModel):
    turn_id: UUID
    position: int
    user_content: str
    assistant_content: str | None
    answer: dict[str, object] | None = None
    status: Literal["in_progress", "completed", "failed"]
    created_at: str
    completed_at: str | None


class SessionReadResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session: SessionSummaryResponse
    turns: tuple[SessionTurnResponse, ...]
    next_before_turn_id: UUID | None = None


class WorkspacePreferencesRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    data_use_acknowledged: bool | None = None
    long_memory_enabled: bool


class WorkspacePreferencesResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    data_use_acknowledged: bool
    data_use_acknowledged_at: str | None
    long_memory_enabled: bool


class MemoryClearResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["cleared"] = "cleared"
    deleted_count: int = Field(ge=0)


class SessionDeleteResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: UUID
    deleted: Literal[True] = True


def _store(request: Request) -> ConversationStore:
    return request.app.state.conversation_store


def _memory_service(request: Request) -> ConversationMemoryService:
    service = getattr(request.app.state, "conversation_memory_service", None)
    if service is None:
        service = ConversationMemoryService(request.app.state.settings)
        request.app.state.conversation_memory_service = service
    return service


def _workspace_preferences(workspace: Workspace) -> WorkspacePreferencesResponse:
    return WorkspacePreferencesResponse(
        data_use_acknowledged=workspace.data_use_acknowledged,
        data_use_acknowledged_at=(
            workspace.data_use_acknowledged_at.isoformat()
            if workspace.data_use_acknowledged_at
            else None
        ),
        long_memory_enabled=workspace.long_memory_enabled,
    )


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": "1.0",
            "error_code": code,
            "message": message,
        },
    )


def _summary(
    store: ConversationStore,
    workspace_id: UUID,
    session: ConversationSession,
) -> SessionSummaryResponse:
    return SessionSummaryResponse(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        turn_count=store.count_turns(workspace_id, session.session_id),
    )


def _turn_response(turn: ConversationTurn) -> SessionTurnResponse:
    return SessionTurnResponse(
        turn_id=turn.turn_id,
        position=turn.position,
        user_content=turn.user_content,
        assistant_content=turn.assistant_content,
        answer=turn.answer_json,
        status=turn.status,
        created_at=turn.created_at.isoformat(),
        completed_at=turn.completed_at.isoformat() if turn.completed_at else None,
    )


def _not_found() -> JSONResponse:
    return _error("SESSION_NOT_FOUND", "The requested session is unavailable.", 404)


@router.get("/preferences", response_model=WorkspacePreferencesResponse)
def get_workspace_preferences(
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
) -> WorkspacePreferencesResponse | JSONResponse:
    try:
        workspace = _store(request).create_workspace(workspace_id)
    except sqlite3.Error:
        return _error(
            "WORKSPACE_PREFERENCES_UNAVAILABLE",
            "Workspace preferences could not be loaded.",
            503,
        )
    return _workspace_preferences(workspace)


@router.put("/preferences", response_model=WorkspacePreferencesResponse)
def update_workspace_preferences(
    body: WorkspacePreferencesRequest,
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
) -> WorkspacePreferencesResponse | JSONResponse:
    try:
        workspace = _store(request).update_workspace_preferences(
            workspace_id,
            data_use_acknowledged=body.data_use_acknowledged,
            long_memory_enabled=body.long_memory_enabled,
        )
    except sqlite3.Error:
        return _error(
            "WORKSPACE_PREFERENCES_UPDATE_FAILED",
            "Workspace preferences could not be saved.",
            503,
        )
    return _workspace_preferences(workspace)


@router.delete("/memories", response_model=MemoryClearResponse)
def clear_workspace_memories(
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
) -> MemoryClearResponse | JSONResponse:
    try:
        deleted_count = _memory_service(request).clear_workspace(workspace_id)
    except ConversationMemoryError as error:
        return _error(
            error.code,
            "Workspace memories could not be cleared safely.",
            503,
        )
    except Exception:
        return _error(
            "MEMORY_DELETE_FAILED",
            "Workspace memories could not be cleared safely.",
            503,
        )
    return MemoryClearResponse(deleted_count=deleted_count)


@router.post("", status_code=201, response_model=SessionSummaryResponse)
def create_session(
    body: SessionCreateRequest,
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
) -> SessionSummaryResponse | JSONResponse:
    store = _store(request)
    try:
        session = store.create_session(
            workspace_id,
            title=body.title or "New conversation",
        )
    except sqlite3.Error:
        return _error(
            "SESSION_CREATE_FAILED",
            "A new conversation could not be created.",
            503,
        )
    return _summary(store, workspace_id, session)


@router.get("", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
    limit: int = Query(default=50, ge=1, le=50),
    before: UUID | None = None,
) -> SessionListResponse:
    store = _store(request)
    page = store.list_sessions(
        workspace_id,
        limit=limit,
        before_session_id=before,
    )
    return SessionListResponse(
        sessions=tuple(_summary(store, workspace_id, session) for session in page.items),
        next_cursor=page.next_cursor,
    )


@router.get("/{session_id}", response_model=SessionReadResponse)
def read_session(
    session_id: UUID,
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
    limit: int = Query(default=100, ge=1, le=100),
    before_turn_id: UUID | None = None,
) -> SessionReadResponse | JSONResponse:
    store = _store(request)
    session = store.get_session(workspace_id, session_id)
    if session is None:
        return _not_found()
    try:
        page = store.list_turns(
            workspace_id,
            session_id,
            limit=limit,
            before_turn_id=before_turn_id,
        )
    except ConversationNotFoundError:
        return _not_found()
    return SessionReadResponse(
        session=_summary(store, workspace_id, session),
        turns=tuple(_turn_response(turn) for turn in page.items),
        next_before_turn_id=page.next_before_turn_id,
    )


@router.delete("/{session_id}", response_model=SessionDeleteResponse)
def delete_session(
    session_id: UUID,
    request: Request,
    workspace_id: UUID = Header(alias="X-Workspace-ID"),
) -> SessionDeleteResponse | JSONResponse:
    store = _store(request)
    try:
        session = store.get_session(workspace_id, session_id)
    except sqlite3.Error:
        return _error(
            "SESSION_DELETE_FAILED",
            "The session could not be checked before deletion.",
            503,
        )
    if session is None:
        return _not_found()
    try:
        _memory_service(request).delete_session(workspace_id, session_id)
    except ConversationMemoryError as error:
        return _error(
            error.code,
            "Session memories could not be deleted; the transcript was retained.",
            503,
        )
    except Exception:
        return _error(
            "SESSION_MEMORY_DELETE_FAILED",
            "Session memories could not be deleted; the transcript was retained.",
            503,
        )
    try:
        deleted = store.delete_session(workspace_id, session_id)
    except sqlite3.Error:
        return _error(
            "SESSION_DELETE_FAILED",
            "The session transcript could not be deleted.",
            503,
        )
    if not deleted:
        return _not_found()
    return SessionDeleteResponse(session_id=session_id)
