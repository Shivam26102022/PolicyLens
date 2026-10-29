from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from policylens.agent_runtime.gateway import ModelGatewayContext
from policylens.agent_runtime.mlx_actions import parse_mlx_action
from policylens.agent_runtime.mlx_provider import MLXModelGateway
from policylens.agent_runtime.models import AgentDraft
from policylens.agent_runtime.provider import AgentConfigurationError
from policylens.agent_runtime.state import AgentRunLedger, AgentRunState
from policylens.agent_runtime.tools import (
    AgentToolExecutionError,
    StatisticsCalculation,
    StatisticsQueryRequest,
    StatisticsToolEvidence,
    StatisticsToolResult,
)
from policylens.retrieval.models import StructuredRowKey
from policylens.settings import AppSettings

MODEL_ID = "mlx-community/Mistral-7B-Instruct-v0.3-4bit"
PASSAGE_ID = "sha256:" + "a" * 64
EXCERPT = "Exact source passage supporting a local-model answer."


def _settings(**overrides: Any) -> AppSettings:
    return AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        model_provider="mlx",
        mlx_model=MODEL_ID,
        embedding_provider="local",
        **overrides,
    )


def _ledger() -> AgentRunLedger:
    ledger = AgentRunLedger(max_tool_calls=4, max_calls_per_tool=2, max_retries=1)
    ledger.transition(AgentRunState.VALIDATED)
    ledger.transition(AgentRunState.RETRIEVING)
    ledger.transition(AgentRunState.ASSESSING)
    return ledger


def _final_action() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "action": "final",
            "draft": {
                "status": "answered",
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "text": EXCERPT,
                        "evidence": [{"passage_id": PASSAGE_ID, "excerpt": EXCERPT}],
                        "calculation_ids": [],
                    }
                ],
                "clarification_question": None,
                "abstention_reason": None,
                "conflicts": [],
                "uncertainty": [],
                "limitations": [],
            },
        }
    )


def _statistics_action() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "action": "query_statistics",
            "request": {
                "indicator": "SL.UEM.1524.ZS",
                "geographies": ["IND"],
                "start_year": 2020,
                "end_year": 2020,
                "aggregation": "mean",
                "group_by": ["geography"],
                "row_limit": 1,
            },
        }
    )


def _final_abstention_action() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "action": "final",
            "draft": {
                "status": "abstained",
                "claims": [],
                "clarification_question": None,
                "abstention_reason": "The returned calculation is not sufficient.",
                "conflicts": [],
                "uncertainty": [],
                "limitations": [],
            },
        }
    )


class FakeMLXClient:
    def __init__(
        self,
        *,
        model_ids: tuple[str, ...] = (MODEL_ID,),
        responses: tuple[str, ...] = (_final_action(),),
    ) -> None:
        self.models = SimpleNamespace(list=self.list_models)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create_completion))
        self.model_ids = model_ids
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    async def __aenter__(self) -> FakeMLXClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    async def list_models(self) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(id=item) for item in self.model_ids])

    async def create_completion(self, **kwargs: object) -> SimpleNamespace:
        self.requests.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(
            model=MODEL_ID,
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=25, total_tokens=125),
        )


class FakeClientFactory:
    def __init__(self, client: FakeMLXClient) -> None:
        self.client = client
        self.kwargs: dict[str, object] | None = None

    def __call__(self, **kwargs: object) -> FakeMLXClient:
        self.kwargs = kwargs
        return self.client


class FakeStatisticsAdapter:
    def __init__(self) -> None:
        self.requests: list[StatisticsQueryRequest] = []

    async def query_statistics(self, request: StatisticsQueryRequest) -> StatisticsToolResult:
        self.requests.append(request)
        return StatisticsToolResult(
            schema_version="1.0",
            query=request,
            rows=({"geography": "IND", "value": 1.5},),
            calculation=StatisticsCalculation(
                operation=request.aggregation,
                formula="Mean of non-null observations.",
                rounding="Six decimal places, half even.",
            ),
            evidence=(
                StatisticsToolEvidence(
                    source_id="wb-youth-unemployment-1524-2015-2025",
                    row_keys=(
                        StructuredRowKey(
                            dataset_id="youth-unemployment",
                            observation_id="IND-2020",
                            indicator_id=request.indicator,
                            country_iso3="IND",
                            year=2020,
                        ),
                    ),
                    content_sha256="a" * 64,
                ),
            ),
        )


def test_mlx_gateway_discovers_model_and_reports_local_capabilities() -> None:
    client = FakeMLXClient()
    gateway = MLXModelGateway(_settings(), client_factory=FakeClientFactory(client))

    capabilities = asyncio.run(gateway.discover_capabilities())

    assert capabilities.provider == "mlx"
    assert capabilities.model_id == MODEL_ID
    assert capabilities.route == "mlx_chat_completions"
    assert capabilities.ready is True
    assert capabilities.capabilities.native_tool_calls is False
    assert capabilities.capabilities.native_json_schema is False
    assert capabilities.capabilities.host_action_envelope is True
    assert client.closed is True


def test_mlx_gateway_runs_validated_action_with_bounded_deterministic_request() -> None:
    client = FakeMLXClient()
    factory = FakeClientFactory(client)
    gateway = MLXModelGateway(_settings(), client_factory=factory)
    context = ModelGatewayContext(
        instructions="Use only the provided evidence.",
        input=json.dumps({"query": "question", "untrusted_evidence": "Evidence text."}),
        ledger=_ledger(),
        statistics_adapter=None,
    )

    result = asyncio.run(gateway.run_agent(context))

    assert isinstance(result.draft, AgentDraft)
    assert result.draft.status == "answered"
    assert result.metadata.provider == "mlx"
    assert result.metadata.model_id == MODEL_ID
    assert result.metadata.usage.prompt_tokens == 100
    assert result.metadata.usage.completion_tokens == 25
    assert result.metadata.fallback_decision == "none"
    assert factory.kwargs is not None
    assert factory.kwargs["base_url"] == "http://127.0.0.1:8080/v1"
    assert factory.kwargs["max_retries"] == 0
    assert client.requests[0]["temperature"] == 0
    assert client.requests[0]["max_tokens"] == 1200
    assert client.requests[0]["model"] == MODEL_ID


def test_mlx_gateway_routes_only_statistics_action_through_host_adapter() -> None:
    client = FakeMLXClient(responses=(_statistics_action(), _final_abstention_action()))
    gateway = MLXModelGateway(_settings(), client_factory=FakeClientFactory(client))
    statistics_adapter = FakeStatisticsAdapter()
    context = ModelGatewayContext(
        instructions="Use the approved statistics tool only when needed.",
        input="Calculate the youth unemployment mean.",
        ledger=_ledger(),
        statistics_adapter=statistics_adapter,
    )

    result = asyncio.run(gateway.run_agent(context))

    assert result.draft.status == "abstained"
    assert result.metadata.usage.requests == 2
    assert result.metadata.usage.prompt_tokens == 200
    assert result.metadata.usage.completion_tokens == 50
    assert result.metadata.usage.total_tokens == 250
    assert len(statistics_adapter.requests) == 1
    assert statistics_adapter.requests[0].indicator == "SL.UEM.1524.ZS"
    assert len(context.ledger.calculations) == 1
    assert "untrusted_tool_result" in client.requests[1]["messages"][-1]["content"]


def test_mlx_gateway_rejects_model_mismatch_before_completion() -> None:
    client = FakeMLXClient(model_ids=("different-model",))
    gateway = MLXModelGateway(_settings(), client_factory=FakeClientFactory(client))

    with pytest.raises(AgentConfigurationError, match="Configured MLX_MODEL"):
        asyncio.run(gateway.discover_capabilities())

    assert client.requests == []


@pytest.mark.parametrize("content", ["not-json", '{"action":"shell"}'])
def test_mlx_gateway_rejects_malformed_or_unapproved_actions(content: str) -> None:
    client = FakeMLXClient(responses=(content,))
    gateway = MLXModelGateway(_settings(), client_factory=FakeClientFactory(client))
    context = ModelGatewayContext(
        instructions="Use evidence.",
        input="question",
        ledger=_ledger(),
        statistics_adapter=None,
    )

    with pytest.raises(AgentToolExecutionError) as error:
        asyncio.run(gateway.run_agent(context))

    assert error.value.code == "OUTPUT_SCHEMA_INVALID"
    assert len(client.requests) == 1


@pytest.mark.parametrize(
    "content",
    [
        "",
        "x" * 50_001,
        '{"schema_version":"1.0","action":"final","draft":{},"extra":true}',
        (
            '{"schema_version":"1.0","action":"query_statistics","request":'
            '{"indicator":"SL.UEM.1524.ZS","geographies":["IND"],"start_year":2020,'
            '"end_year":2025,"aggregation":"mean","group_by":[],"row_limit":45}}'
        ),
        (
            '{"schema_version":"1.0","action":"query_statistics","request":'
            '{"indicator":"SL.UEM.1524.ZS","geographies":["IND"],"start_year":2014,'
            '"end_year":2025,"aggregation":"mean","group_by":[],"row_limit":10}}'
        ),
        (
            '{"schema_version":"1.0","action":"query_statistics","request":'
            '{"indicator":"SL.UEM.1524.ZS","geographies":["IND"],"start_year":2020,'
            '"end_year":2025,"aggregation":"none","group_by":["year"],"row_limit":10}}'
        ),
    ],
)
def test_mlx_action_parser_rejects_empty_oversized_extra_or_invalid_arguments(
    content: str,
) -> None:
    with pytest.raises(AgentToolExecutionError) as error:
        parse_mlx_action(content)

    assert error.value.code == "OUTPUT_SCHEMA_INVALID"
