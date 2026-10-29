from __future__ import annotations

import asyncio

from policylens.agent_runtime.tools import (
    StatisticsCalculation,
    StatisticsQueryRequest,
    StatisticsToolEvidence,
    StatisticsToolResult,
)
from policylens.retrieval.models import StructuredRowKey
from scripts.evaluate_mcp_direct import evaluate_requests


def _request() -> StatisticsQueryRequest:
    return StatisticsQueryRequest(
        indicator="SL.UEM.1524.ZS",
        geographies=("IND",),
        start_year=2020,
        end_year=2020,
        aggregation="mean",
        group_by=(),
        row_limit=1,
    )


def _result(request: StatisticsQueryRequest, value: float = 1.5) -> StatisticsToolResult:
    return StatisticsToolResult(
        schema_version="1.0",
        query=request,
        rows=({"geography": "IND", "year": None, "value": value, "unit": "%"},),
        calculation=StatisticsCalculation(
            operation="mean",
            formula="Arithmetic mean of non-null observations.",
            rounding="ROUND_HALF_EVEN to six decimal places.",
        ),
        evidence=(
            StatisticsToolEvidence(
                source_id="wb-youth-unemployment-1524-2015-2025",
                row_keys=(
                    StructuredRowKey(
                        dataset_id="doc:wb-youth-unemployment-1524-2015-2025:" + "a" * 64,
                        observation_id="wb-youth-unemployment-1524-2015-2025:IND:2020",
                        indicator_id=request.indicator,
                        country_iso3="IND",
                        year=2020,
                    ),
                ),
                content_sha256="a" * 64,
            ),
        ),
        warnings=(),
    )


class FakeStatisticsAdapter:
    def __init__(self, result: StatisticsToolResult) -> None:
        self.result = result
        self.requests: list[StatisticsQueryRequest] = []

    async def query_statistics(self, request: StatisticsQueryRequest) -> StatisticsToolResult:
        self.requests.append(request)
        return self.result


def test_comparison_reports_parity_and_local_scope() -> None:
    request = _request()
    expected = _result(request)
    adapter = FakeStatisticsAdapter(expected)

    report = asyncio.run(
        evaluate_requests(
            adapter,
            cases=(("fixture", request),),
            direct_query=lambda _request: expected,
            repeats=2,
        )
    )

    assert report["parity_passed"] is True
    assert report["live_measurement"] is False
    assert "local" in report["measurement_scope"]
    assert report["cases"][0]["contract_parity"] is True
    assert report["cases"][0]["result_parity"] is True
    assert len(adapter.requests) == 2


def test_comparison_preserves_negative_result_parity() -> None:
    request = _request()
    adapter = FakeStatisticsAdapter(_result(request))

    report = asyncio.run(
        evaluate_requests(
            adapter,
            cases=(("negative-fixture", request),),
            direct_query=lambda query: _result(query, value=2.0),
            repeats=1,
        )
    )

    assert report["parity_passed"] is False
    assert report["cases"][0]["result_parity"] is False
