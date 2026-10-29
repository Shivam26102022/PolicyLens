from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from policylens.agent_runtime.models import (
    AgentAnswerRequest,
    AgentAnswerResponse,
    AgentConversationMessage,
    AgentEvent,
    AgentEventType,
    AgentRunState,
    AgentSessionContext,
)
from policylens.agent_runtime.provider import AgentConfigurationError
from policylens.agent_runtime.runtime import AgentExecutionError, AgentRuntime
from policylens.api.model_capabilities import build_model_options
from policylens.api.retrieval import get_retrieval_runtime
from policylens.conversations.memory import (
    ConversationMemory,
    ConversationMemoryError,
    ConversationMemoryService,
)
from policylens.conversations.store import (
    ConversationNotFoundError,
    ConversationStore,
)
from policylens.mcp.client import MCPStatisticsAdapter
from policylens.retrieval.citations import CitationValidator
from policylens.retrieval.search import RetrievalService
from policylens.settings import AppSettings

router = APIRouter(prefix="/agent", tags=["agent"])
AgentRuntimeFactory = Callable[
    [AppSettings, RetrievalService, CitationValidator, Any], AgentRuntime
]


def _create_agent_runtime(
    settings: AppSettings,
    service: RetrievalService,
    validator: CitationValidator,
    statistics_adapter: Any,
) -> AgentRuntime:
    return AgentRuntime(
        settings,
        service,
        validator,
        statistics_adapter=statistics_adapter,
        passage_reader=(
            statistics_adapter if isinstance(statistics_adapter, MCPStatisticsAdapter) else None
        ),
    )


def _error_response(
    code: str,
    message: str,
    status_code: int,
    trace_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": "1.0",
            "error_code": code,
            "message": message,
            "trace_id": trace_id,
        },
    )


def _session_error(code: str, message: str, status_code: int) -> JSONResponse:
    return _error_response(code, message, status_code)


def _session_event(
    *,
    sequence: int,
    state: AgentRunState,
    event_type: AgentEventType,
    status: Literal["started", "succeeded", "failed", "skipped"],
    error_code: str | None = None,
    item_count: int | None = None,
) -> AgentEvent:
    return AgentEvent(
        sequence=sequence,
        state=state,
        event_type=event_type,
        status=status,
        error_code=error_code,
        item_count=item_count,
    )


def _hot_context(
    store: ConversationStore,
    workspace_id: UUID,
    session_id: UUID,
) -> tuple[AgentConversationMessage, ...]:
    recent = store.get_recent_completed_turns(workspace_id, session_id, limit=5)
    selected_pairs: list[tuple[AgentConversationMessage, AgentConversationMessage]] = []
    total_characters = 0
    for turn in reversed(recent):
        user_message = AgentConversationMessage(role="user", content=turn.user_content)
        assistant_content = (turn.assistant_content or "")[:4000]
        if not assistant_content.strip():
            continue
        assistant_message = AgentConversationMessage(
            role="assistant",
            content=assistant_content,
        )
        pair_size = len(user_message.content) + len(assistant_message.content)
        if total_characters + pair_size > 12000:
            break
        selected_pairs.append((user_message, assistant_message))
        total_characters += pair_size
    return tuple(message for pair in reversed(selected_pairs) for message in pair)


def _sequence_session_events(
    events: tuple[AgentEvent, ...],
    *,
    persisted: bool,
    memory_retrieval_status: Literal[
        "used", "empty", "disabled", "unavailable", "embedding_mismatch"
    ],
    retrieved_memory_count: int,
    memory_retrieval_error: str | None,
    memory_write_status: Literal["stored", "skipped", "failed"],
    memory_write_error: str | None,
) -> tuple[AgentEvent, ...]:
    session_event = _session_event(
        sequence=1,
        state=AgentRunState.RECEIVED,
        event_type="session_context_loaded",
        status="succeeded",
    )
    retrieval_event = _session_event(
        sequence=2,
        state=AgentRunState.RETRIEVING,
        event_type="memory_retrieval_completed",
        status=(
            "skipped"
            if memory_retrieval_status == "disabled"
            else "failed"
            if memory_retrieval_status in {"unavailable", "embedding_mismatch"}
            else "succeeded"
        ),
        error_code=memory_retrieval_error,
        item_count=retrieved_memory_count,
    )
    sequenced_runtime = tuple(
        event.model_copy(update={"sequence": index + 3}) for index, event in enumerate(events[:196])
    )
    write_event = _session_event(
        sequence=len(sequenced_runtime) + 3,
        state=AgentRunState.OUTPUT_VALIDATION,
        event_type="memory_write_completed",
        status=(
            "succeeded"
            if memory_write_status == "stored"
            else "failed"
            if memory_write_status == "failed"
            else "skipped"
        ),
        error_code=memory_write_error,
    )
    persistence_event = _session_event(
        sequence=len(sequenced_runtime) + 4,
        state=AgentRunState.OUTPUT_VALIDATION,
        event_type="session_turn_persisted",
        status="succeeded" if persisted else "failed",
        error_code=None if persisted else "SESSION_PERSISTENCE_FAILED",
    )
    return (session_event, retrieval_event, *sequenced_runtime, write_event, persistence_event)


def _conversation_memory_service(request: Request) -> ConversationMemoryService:
    service = getattr(request.app.state, "conversation_memory_service", None)
    if service is None:
        service = ConversationMemoryService(request.app.state.settings)
        request.app.state.conversation_memory_service = service
    return service


async def _answer_with_session(
    request: Request,
    body: AgentAnswerRequest,
    runtime: AgentRuntime,
    *,
    event_listener: Callable[[AgentEvent], None] | None = None,
) -> AgentAnswerResponse | JSONResponse:
    if body.session_id is None:
        return await runtime.answer(body, event_listener=event_listener)

    raw_workspace_id = request.headers.get("X-Workspace-ID")
    if not raw_workspace_id:
        return _session_error(
            "WORKSPACE_REQUIRED",
            "Provide the workspace identifier for this session.",
            400,
        )
    try:
        workspace_id = UUID(raw_workspace_id)
    except ValueError:
        return _session_error(
            "INVALID_WORKSPACE_ID",
            "The workspace identifier is invalid.",
            400,
        )

    store: ConversationStore = request.app.state.conversation_store
    workspace = store.create_workspace(workspace_id)
    session = store.get_session(workspace_id, body.session_id)
    if session is None:
        # Serverless instances do not share local storage, so a session created on
        # another instance (or before a cold start) is recreated from the browser's
        # copy of the conversation instead of failing the chat.
        try:
            store.create_session(
                workspace_id,
                session_id=body.session_id,
                title=body.query.strip()[:60] or "New conversation",
            )
        except sqlite3.IntegrityError:
            # The id already belongs to another workspace; never expose or reuse it.
            return _session_error(
                "SESSION_NOT_FOUND",
                "The requested session is unavailable.",
                404,
            )
        except sqlite3.Error:
            return _session_error(
                "SESSION_PERSISTENCE_FAILED",
                "The session could not be restored.",
                503,
            )
    try:
        turn = store.create_turn(workspace_id, body.session_id, body.query)
        stored_context = _hot_context(store, workspace_id, body.session_id)
        conversation = (
            stored_context if len(stored_context) >= len(body.conversation) else body.conversation
        )
    except ConversationNotFoundError:
        return _session_error(
            "SESSION_NOT_FOUND",
            "The requested session is unavailable.",
            404,
        )
    except sqlite3.Error:
        return _session_error(
            "SESSION_PERSISTENCE_FAILED",
            "The session turn could not be saved.",
            503,
        )

    selected_request = body.model_copy(update={"conversation": conversation})
    memory_context: tuple[ConversationMemory, ...] = ()
    memory_retrieval_status: Literal[
        "used", "empty", "disabled", "unavailable", "embedding_mismatch"
    ] = "disabled"
    memory_retrieval_error: str | None = None
    if workspace.long_memory_enabled:
        try:
            memory_context = _conversation_memory_service(request).search(
                workspace_id,
                body.query,
                limit=5,
            )
            memory_retrieval_status = "used" if memory_context else "empty"
        except ConversationMemoryError as error:
            memory_retrieval_status = (
                "embedding_mismatch"
                if error.code == "MEMORY_EMBEDDING_IDENTITY_MISMATCH"
                else "unavailable"
            )
            memory_retrieval_error = error.code
        except Exception:
            memory_retrieval_status = "unavailable"
            memory_retrieval_error = "MEMORY_RETRIEVAL_UNAVAILABLE"
    session_loaded_event = _session_event(
        sequence=1,
        state=AgentRunState.RECEIVED,
        event_type="session_context_loaded",
        status="succeeded",
    )
    if event_listener is not None:
        event_listener(session_loaded_event)
        event_listener(
            _session_event(
                sequence=2,
                state=AgentRunState.RETRIEVING,
                event_type="memory_retrieval_completed",
                status=(
                    "skipped"
                    if memory_retrieval_status == "disabled"
                    else "failed"
                    if memory_retrieval_status in {"unavailable", "embedding_mismatch"}
                    else "succeeded"
                ),
                error_code=memory_retrieval_error,
                item_count=len(memory_context),
            )
        )
    try:
        runtime_events: list[AgentEvent] = []

        def emit_runtime_event(event: AgentEvent) -> None:
            if len(runtime_events) >= 196:
                return
            sequenced = event.model_copy(update={"sequence": len(runtime_events) + 3})
            runtime_events.append(sequenced)
            if event_listener is not None:
                event_listener(sequenced)

        response = await runtime.answer(
            selected_request,
            memory_context=memory_context,
            event_listener=emit_runtime_event if event_listener is not None else None,
        )
    except Exception:
        try:
            store.fail_turn(workspace_id, body.session_id, turn.turn_id)
        except sqlite3.Error:
            return _session_error(
                "SESSION_PERSISTENCE_FAILED",
                "The failed session turn could not be recorded.",
                503,
            )
        raise

    assistant_content = (
        response.answer
        or response.clarification_question
        or response.abstention_reason
        or f"The assistant completed the turn with status: {response.status}."
    )
    initial_context = AgentSessionContext(
        session_id=body.session_id,
        turn_id=turn.turn_id,
        persisted=False,
        long_memory_enabled=workspace.long_memory_enabled,
        memory_retrieval_status=memory_retrieval_status,
        retrieved_memory_count=len(memory_context),
        memory_write_status="skipped",
    )
    initial_response = AgentAnswerResponse.model_validate(
        {
            **response.model_dump(mode="python"),
            "session_context": initial_context,
        }
    )
    try:
        completed_turn = store.complete_turn(
            workspace_id,
            body.session_id,
            turn.turn_id,
            assistant_content=assistant_content,
            answer_json=initial_response.model_dump(mode="json"),
        )
    except sqlite3.Error:
        completed_turn = None
    memory_write_status: Literal["stored", "skipped", "failed"] = "skipped"
    memory_write_error: str | None = None
    persisted = completed_turn is not None
    if (
        completed_turn is not None
        and workspace.long_memory_enabled
        and response.status not in {"blocked", "failed_safe"}
    ):
        try:
            _conversation_memory_service(request).store(
                workspace_id,
                body.session_id,
                turn.turn_id,
                body.query,
                assistant_content,
                created_at=completed_turn.completed_at,
            )
            memory_write_status = "stored"
        except ConversationMemoryError as error:
            memory_write_status = "failed"
            memory_write_error = error.code
        except Exception:
            memory_write_status = "failed"
            memory_write_error = "MEMORY_WRITE_FAILED"
    context = AgentSessionContext(
        session_id=body.session_id,
        turn_id=turn.turn_id,
        persisted=persisted,
        long_memory_enabled=workspace.long_memory_enabled,
        memory_retrieval_status=memory_retrieval_status,
        retrieved_memory_count=len(memory_context),
        memory_write_status=memory_write_status,
    )
    response_events = _sequence_session_events(
        response.events,
        persisted=persisted,
        memory_retrieval_status=memory_retrieval_status,
        retrieved_memory_count=len(memory_context),
        memory_retrieval_error=memory_retrieval_error,
        memory_write_status=memory_write_status,
        memory_write_error=memory_write_error,
    )
    response_with_session = AgentAnswerResponse.model_validate(
        {
            **response.model_dump(mode="python"),
            "session_context": context,
            "events": response_events,
        }
    )
    if completed_turn is not None:
        try:
            store.update_completed_turn_answer(
                workspace_id,
                body.session_id,
                turn.turn_id,
                response_with_session.model_dump(mode="json"),
            )
        except sqlite3.Error:
            persisted = False
            context = context.model_copy(update={"persisted": False})
            response_events = _sequence_session_events(
                response.events,
                persisted=False,
                memory_retrieval_status=memory_retrieval_status,
                retrieved_memory_count=len(memory_context),
                memory_retrieval_error=memory_retrieval_error,
                memory_write_status=memory_write_status,
                memory_write_error=memory_write_error,
            )
            response_with_session = AgentAnswerResponse.model_validate(
                {
                    **response.model_dump(mode="python"),
                    "session_context": context,
                    "events": response_events,
                }
            )
    if event_listener is not None:
        event_listener(response_with_session.events[-2])
        event_listener(response_with_session.events[-1])
    return response_with_session


async def _resolve_runtime(
    request: Request, body: AgentAnswerRequest
) -> AgentRuntime | JSONResponse:
    settings: AppSettings = request.app.state.settings
    if settings.embedding_provider == "openai" and not body.allow_external_embeddings:
        return _error_response(
            "EXTERNAL_EMBEDDING_CONSENT_REQUIRED",
            "Confirm external embedding processing before this run.",
            403,
        )
    provider = body.provider or settings.model_provider
    if provider == "openai" and not body.allow_external_provider:
        return _error_response(
            "EXTERNAL_PROVIDER_CONSENT_REQUIRED",
            "Confirm external processing before using OpenAI for this run.",
            403,
        )

    model_options = build_model_options(settings)
    option = next(item for item in model_options.options if item.provider == provider)
    if not option.configured or option.model_id is None:
        return _error_response(
            "MODEL_UNAVAILABLE",
            "The selected model provider is not configured.",
            503,
        )
    if body.reasoning_effort not in option.reasoning_efforts:
        return _error_response(
            "MODEL_CAPABILITY_UNSUPPORTED",
            "The selected model route does not support this reasoning effort.",
            422,
        )

    runtime_key = (provider, option.model_id)
    runtime = (
        getattr(request.app.state, "agent_runtime", None)
        if provider == settings.model_provider
        else None
    )
    runtimes: dict[tuple[str, str], AgentRuntime] = getattr(request.app.state, "agent_runtimes", {})
    if runtime is None:
        runtime = runtimes.get(runtime_key)
    if runtime is None:
        retrieval_runtime = get_retrieval_runtime(request)
        if isinstance(retrieval_runtime, JSONResponse):
            return retrieval_runtime
        service, validator = retrieval_runtime
        if validator is None:
            return _error_response(
                "RETRIEVAL_UNAVAILABLE", "Run-scoped citation validation is unavailable.", 503
            )
        factory: AgentRuntimeFactory = (
            getattr(request.app.state, "agent_runtime_factory", None) or _create_agent_runtime
        )
        runtime_settings = (
            settings
            if provider == settings.model_provider
            else settings.model_copy(update={"model_provider": provider})
        )
        try:
            runtime = factory(
                runtime_settings,
                service,
                validator,
                getattr(request.app.state, "statistics_tool_adapter", None),
            )
        except AgentConfigurationError:
            return _error_response(
                "MODEL_UNAVAILABLE", "The agent model configuration is unavailable.", 503
            )
        except Exception:
            return _error_response("INTERNAL_ERROR", "The agent runtime is unavailable.", 503)
        runtimes[runtime_key] = runtime
        request.app.state.agent_runtimes = runtimes
        if provider == settings.model_provider:
            request.app.state.agent_runtime = runtime

    return runtime


@router.post("/answer", response_model=AgentAnswerResponse)
async def answer(request: Request, body: AgentAnswerRequest) -> AgentAnswerResponse | JSONResponse:
    runtime = await _resolve_runtime(request, body)
    if isinstance(runtime, JSONResponse):
        return runtime
    try:
        return await _answer_with_session(request, body, runtime)
    except AgentExecutionError as error:
        return _error_response(
            error.code,
            "The agent run could not be completed safely.",
            503,
            trace_id=str(error.trace_id),
        )
    except Exception:
        return _error_response("INTERNAL_ERROR", "The agent run failed safely.", 500)


@router.post("/answer/stream")
async def answer_stream(request: Request, body: AgentAnswerRequest):
    runtime = await _resolve_runtime(request, body)
    if isinstance(runtime, JSONResponse):
        return runtime

    events: asyncio.Queue[AgentEvent] = asyncio.Queue()
    task = asyncio.create_task(
        _answer_with_session(request, body, runtime, event_listener=events.put_nowait)
    )
    background_tasks: set[asyncio.Task[AgentAnswerResponse | JSONResponse]] = getattr(
        request.app.state, "agent_stream_tasks", set()
    )
    request.app.state.agent_stream_tasks = background_tasks
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    async def stream():
        while not task.done() or not events.empty():
            try:
                event = await asyncio.wait_for(events.get(), timeout=0.25)
            except TimeoutError:
                continue
            payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
            yield f"event: progress\ndata: {payload}\n\n"
        try:
            result = await task
            if isinstance(result, JSONResponse):
                payload = bytes(result.body).decode("utf-8")
                yield f"event: error\ndata: {payload}\n\n"
            else:
                payload = json.dumps(result.model_dump(mode="json"), separators=(",", ":"))
                yield f"event: result\ndata: {payload}\n\n"
        except AgentExecutionError as error:
            payload = json.dumps(
                {
                    "error_code": error.code,
                    "message": "The agent run could not be completed safely.",
                    "trace_id": str(error.trace_id),
                },
                separators=(",", ":"),
            )
            yield f"event: error\ndata: {payload}\n\n"
        except Exception:
            payload = json.dumps(
                {"error_code": "INTERNAL_ERROR", "message": "The agent run failed safely."},
                separators=(",", ":"),
            )
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
