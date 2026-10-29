from __future__ import annotations

from time import perf_counter
from typing import Any

from agents import RunHooks

from policylens.agent_runtime.models import ModelRoute, ReasoningEffort
from policylens.agent_runtime.state import AgentRunLedger
from policylens.agent_runtime.usage import (
    model_usage_from_provider,
    reasoning_summary_from_responses,
)


class SafeAgentRunHooks(RunHooks[Any]):
    """Record model lifecycle only; deliberately ignore sensitive callback payloads."""

    def __init__(
        self,
        ledger: AgentRunLedger,
        *,
        model_route: ModelRoute,
        reasoning_effort: ReasoningEffort,
    ) -> None:
        self._ledger = ledger
        self._model_route = model_route
        self._reasoning_effort = reasoning_effort
        self._model_started_at: float | None = None

    async def on_llm_start(
        self,
        context: Any,
        agent: Any,
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        self._model_started_at = perf_counter()
        self._ledger.record_event(
            "model_started",
            status="started",
            model_route=self._model_route,
            reasoning_effort=self._reasoning_effort,
        )

    async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
        duration_ms = (
            max(0.0, (perf_counter() - self._model_started_at) * 1000)
            if self._model_started_at is not None
            else None
        )
        self._model_started_at = None
        self._ledger.record_event(
            "model_completed",
            status="succeeded",
            duration_ms=duration_ms,
            model_route=self._model_route,
            reasoning_effort=self._reasoning_effort,
            model_usage=model_usage_from_provider(
                getattr(response, "usage", None),
                default_requests=1,
            ),
            reasoning_summary=reasoning_summary_from_responses([response]),
        )
