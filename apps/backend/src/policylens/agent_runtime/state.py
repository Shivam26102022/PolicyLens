from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from time import monotonic
from typing import Literal, cast
from uuid import UUID, uuid4

from policylens.agent_runtime.models import (
    AgentCalculationRecord,
    AgentErrorCode,
    AgentEvent,
    AgentEventType,
    AgentModelUsage,
    AgentRunState,
    ModelRoute,
    ReasoningEffort,
)

_TRANSITIONS: dict[AgentRunState, frozenset[AgentRunState]] = {
    AgentRunState.RECEIVED: frozenset({AgentRunState.VALIDATED, AgentRunState.FAILED_SAFE}),
    AgentRunState.VALIDATED: frozenset({AgentRunState.RETRIEVING, AgentRunState.FAILED_SAFE}),
    AgentRunState.RETRIEVING: frozenset({AgentRunState.ASSESSING, AgentRunState.FAILED_SAFE}),
    AgentRunState.ASSESSING: frozenset(
        {
            AgentRunState.TOOL_EXECUTION,
            AgentRunState.OUTPUT_VALIDATION,
            AgentRunState.CLARIFICATION_REQUIRED,
            AgentRunState.ABSTAINED,
            AgentRunState.CONFLICT,
            AgentRunState.BLOCKED,
            AgentRunState.FAILED_SAFE,
        }
    ),
    AgentRunState.TOOL_EXECUTION: frozenset(
        {AgentRunState.ASSESSING, AgentRunState.BLOCKED, AgentRunState.FAILED_SAFE}
    ),
    AgentRunState.OUTPUT_VALIDATION: frozenset(
        {AgentRunState.CITATION_VALIDATION, AgentRunState.FAILED_SAFE}
    ),
    AgentRunState.CITATION_VALIDATION: frozenset(
        {AgentRunState.ANSWERED, AgentRunState.CONFLICT, AgentRunState.FAILED_SAFE}
    ),
    AgentRunState.ANSWERED: frozenset(),
    AgentRunState.CLARIFICATION_REQUIRED: frozenset(),
    AgentRunState.ABSTAINED: frozenset(),
    AgentRunState.CONFLICT: frozenset(),
    AgentRunState.BLOCKED: frozenset(),
    AgentRunState.FAILED_SAFE: frozenset(),
}
_TRANSIENT_ERRORS = frozenset({"MCP_UNAVAILABLE", "MCP_TIMEOUT", "INTERNAL_ERROR"})
_EVENT_FIELDS = frozenset(
    {
        "status",
        "tool_name",
        "tool_call_id",
        "duration_ms",
        "retry_count",
        "item_count",
        "error_code",
        "reranker_model",
        "model_route",
        "reasoning_effort",
        "model_usage",
        "reasoning_summary",
    }
)


class AgentStateError(RuntimeError):
    """The host attempted an invalid run-state transition."""


class AgentToolBudgetExceeded(RuntimeError):
    """A run exceeded its total or per-tool call budget."""


class AgentRunLedger:
    def __init__(
        self,
        *,
        max_tool_calls: int,
        max_calls_per_tool: int,
        max_retries: int,
        clock=monotonic,
        event_listener: Callable[[AgentEvent], None] | None = None,
    ) -> None:
        if max_tool_calls < 1 or max_calls_per_tool < 1 or max_retries < 0:
            raise ValueError("agent budgets must be non-negative and call limits positive")
        self.run_id: UUID = uuid4()
        self.trace_id: UUID = uuid4()
        self.state = AgentRunState.RECEIVED
        self._max_tool_calls = max_tool_calls
        self._max_calls_per_tool = max_calls_per_tool
        self._max_retries = max_retries
        self._clock = clock
        self._event_listener = event_listener
        self._started_at = clock()
        self._tool_calls = 0
        self._tool_counts: Counter[str] = Counter()
        self._retries = 0
        self._calculations: list[AgentCalculationRecord] = []
        self.tool_error_code: AgentErrorCode | None = None
        self._events: list[AgentEvent] = []
        self.record_event("state_transition", status="succeeded")

    @property
    def events(self) -> tuple[AgentEvent, ...]:
        return tuple(self._events)

    @property
    def calculations(self) -> tuple[AgentCalculationRecord, ...]:
        return tuple(self._calculations)

    @property
    def retry_count(self) -> int:
        return self._retries

    @property
    def elapsed_ms(self) -> float:
        return max(0.0, (self._clock() - self._started_at) * 1000.0)

    def transition(self, next_state: AgentRunState) -> AgentEvent:
        if next_state not in _TRANSITIONS[self.state]:
            if not _TRANSITIONS[self.state]:
                raise AgentStateError("run is terminal; no further transitions are allowed")
            raise AgentStateError(f"transition from {self.state} to {next_state} is not allowed")
        self.state = next_state
        return self.record_event("state_transition", status="succeeded")

    def record_event(self, event_type: AgentEventType, **fields: object) -> AgentEvent:
        unexpected = set(fields) - _EVENT_FIELDS
        if unexpected:
            raise ValueError("unexpected event data; raw payload fields are prohibited")
        status = cast(
            Literal["started", "succeeded", "failed", "skipped"],
            fields.get("status", "succeeded"),
        )
        event = AgentEvent(
            sequence=len(self._events) + 1,
            state=self.state,
            event_type=event_type,
            status=status,
            tool_name=cast(Literal["query_statistics"] | None, fields.get("tool_name")),
            tool_call_id=cast(UUID | None, fields.get("tool_call_id")),
            duration_ms=cast(float | None, fields.get("duration_ms")),
            retry_count=cast(int, fields.get("retry_count", 0)),
            item_count=cast(int | None, fields.get("item_count")),
            error_code=cast(str | None, fields.get("error_code")),
            reranker_model=cast(str | None, fields.get("reranker_model")),
            model_route=cast(ModelRoute | None, fields.get("model_route")),
            reasoning_effort=cast(ReasoningEffort | None, fields.get("reasoning_effort")),
            model_usage=cast(AgentModelUsage | None, fields.get("model_usage")),
            reasoning_summary=cast(str | None, fields.get("reasoning_summary")),
        )
        self._events.append(event)
        if len(self._events) > 200:
            raise AgentStateError("event budget exceeded")
        if self._event_listener is not None:
            self._event_listener(event)
        return event

    def begin_tool_call(self, tool_name: Literal["query_statistics"]) -> UUID:
        if self.state != "tool_execution":
            raise AgentStateError("tool calls are permitted only in tool_execution state")
        if self._tool_calls >= self._max_tool_calls:
            raise AgentToolBudgetExceeded("total tool-call budget exceeded")
        if self._tool_counts[tool_name] >= self._max_calls_per_tool:
            raise AgentToolBudgetExceeded("per-tool call budget exceeded")
        self._tool_calls += 1
        self._tool_counts[tool_name] += 1
        tool_call_id = uuid4()
        self.record_event(
            "tool_started",
            status="started",
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        return tool_call_id

    def record_calculation(self, calculation: AgentCalculationRecord) -> None:
        self._calculations.append(calculation)

    def mark_tool_failure(self, error_code: AgentErrorCode) -> None:
        self.tool_error_code = error_code

    def end_tool_call(
        self,
        tool_name: Literal["query_statistics"],
        *,
        status: Literal["started", "succeeded", "failed", "skipped"],
        duration_ms: float,
        tool_call_id: UUID | None = None,
        error_code: str | None = None,
        retry_count: int = 0,
    ) -> AgentEvent:
        return self.record_event(
            "tool_completed",
            status=status,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            duration_ms=duration_ms,
            error_code=error_code,
            retry_count=retry_count,
        )

    def can_retry_tool(self, error_code: str, *, transient: bool) -> bool:
        return transient and error_code in _TRANSIENT_ERRORS and self._retries < self._max_retries

    def consume_retry(self, tool_name: str) -> int:
        if self._retries >= self._max_retries:
            raise AgentToolBudgetExceeded("tool retry budget exceeded")
        self._retries += 1
        return self._retries
