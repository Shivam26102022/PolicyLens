from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseReasoningItem

from policylens.agent_runtime.state import (
    AgentRunLedger,
    AgentRunState,
    AgentStateError,
    AgentToolBudgetExceeded,
)
from policylens.agent_runtime.traces import SafeAgentRunHooks


def test_agent_ledger_enforces_finite_state_transitions() -> None:
    ledger = AgentRunLedger(max_tool_calls=2, max_calls_per_tool=1, max_retries=1)
    ledger.transition(AgentRunState.VALIDATED)
    ledger.transition(AgentRunState.RETRIEVING)
    ledger.transition(AgentRunState.ASSESSING)
    ledger.transition(AgentRunState.OUTPUT_VALIDATION)
    ledger.transition(AgentRunState.CITATION_VALIDATION)
    ledger.transition(AgentRunState.ANSWERED)

    assert ledger.state is AgentRunState.ANSWERED
    with pytest.raises(AgentStateError, match="terminal"):
        ledger.transition(AgentRunState.RETRIEVING)


def test_agent_ledger_rejects_skipped_transitions() -> None:
    ledger = AgentRunLedger(max_tool_calls=2, max_calls_per_tool=1, max_retries=1)

    with pytest.raises(AgentStateError, match="not allowed"):
        ledger.transition(AgentRunState.CITATION_VALIDATION)


def test_agent_ledger_enforces_total_and_per_tool_call_budgets() -> None:
    ledger = AgentRunLedger(max_tool_calls=2, max_calls_per_tool=1, max_retries=1)
    ledger.transition(AgentRunState.VALIDATED)
    ledger.transition(AgentRunState.RETRIEVING)
    ledger.transition(AgentRunState.ASSESSING)
    ledger.transition(AgentRunState.TOOL_EXECUTION)

    ledger.begin_tool_call("query_statistics")
    ledger.end_tool_call("query_statistics", status="succeeded", duration_ms=12.5)
    with pytest.raises(AgentToolBudgetExceeded, match="per-tool"):
        ledger.begin_tool_call("query_statistics")

    total_ledger = AgentRunLedger(max_tool_calls=1, max_calls_per_tool=2, max_retries=1)
    total_ledger.transition(AgentRunState.VALIDATED)
    total_ledger.transition(AgentRunState.RETRIEVING)
    total_ledger.transition(AgentRunState.ASSESSING)
    total_ledger.transition(AgentRunState.TOOL_EXECUTION)
    total_ledger.begin_tool_call("query_statistics")
    total_ledger.end_tool_call(
        "query_statistics", status="failed", duration_ms=12.5, error_code="MCP_TIMEOUT"
    )
    with pytest.raises(AgentToolBudgetExceeded, match="total"):
        total_ledger.begin_tool_call("query_statistics")


def test_agent_ledger_retries_only_transient_errors_within_budget() -> None:
    ledger = AgentRunLedger(max_tool_calls=4, max_calls_per_tool=4, max_retries=1)

    assert ledger.can_retry_tool("MCP_TIMEOUT", transient=True)
    ledger.consume_retry("query_statistics")
    assert not ledger.can_retry_tool("MCP_TIMEOUT", transient=True)
    assert not ledger.can_retry_tool("TOOL_INVALID_ARGUMENTS", transient=False)


def test_agent_events_never_accept_payload_fields() -> None:
    ledger = AgentRunLedger(max_tool_calls=1, max_calls_per_tool=1, max_retries=0)

    with pytest.raises(ValueError, match="unexpected event data"):
        ledger.record_event("state_transition", query="private question")

    event = ledger.record_event("state_transition", status="succeeded")
    dumped = event.model_dump(mode="json")
    assert "query" not in dumped
    assert "prompt" not in dumped


def test_agents_sdk_hooks_emit_only_redacted_lifecycle_events() -> None:
    ledger = AgentRunLedger(max_tool_calls=1, max_calls_per_tool=1, max_retries=0)
    hooks = SafeAgentRunHooks(
        ledger,
        model_route="mlx_chat_completions",
        reasoning_effort="none",
    )

    asyncio.run(
        hooks.on_llm_start(
            context=None,
            agent=None,
            system_prompt="SECRET_SYSTEM_PROMPT",
            input_items=[{"content": "SECRET_USER_QUERY"}],
        )
    )
    asyncio.run(
        hooks.on_llm_end(
            context=None,
            agent=None,
            response={"content": "SECRET_MODEL_OUTPUT"},
        )
    )

    serialized = " ".join(event.model_dump_json() for event in ledger.events)
    assert "model_started" in serialized
    assert "model_completed" in serialized
    assert "SECRET_" not in serialized


def test_agents_sdk_hooks_record_usage_and_only_the_reasoning_summary() -> None:
    ledger = AgentRunLedger(max_tool_calls=1, max_calls_per_tool=1, max_retries=0)
    hooks = SafeAgentRunHooks(
        ledger,
        model_route="openai_responses",
        reasoning_effort="low",
    )
    reasoning = ResponseReasoningItem.model_validate(
        {
            "id": "reasoning-1",
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "Compared the available evidence."}],
            "content": [{"type": "reasoning_text", "text": "PRIVATE_REASONING_CONTENT"}],
        }
    )

    asyncio.run(
        hooks.on_llm_end(
            context=None,
            agent=None,
            response=SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=12,
                    output_tokens=4,
                    total_tokens=16,
                    output_tokens_details=SimpleNamespace(reasoning_tokens=2),
                ),
                output=[reasoning],
            ),
        )
    )

    event = ledger.events[-1]
    assert event.model_route == "openai_responses"
    assert event.reasoning_effort == "low"
    assert event.model_usage is not None
    assert event.model_usage.prompt_tokens == 12
    assert event.model_usage.reasoning_tokens == 2
    assert event.reasoning_summary == "Compared the available evidence."
    assert "PRIVATE_REASONING_CONTENT" not in event.model_dump_json()
