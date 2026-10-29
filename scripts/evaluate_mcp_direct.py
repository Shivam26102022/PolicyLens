from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any, Protocol

from policylens.agent_runtime.tools import StatisticsQueryRequest, StatisticsToolResult
from policylens.mcp.client import MCPStatisticsAdapter, _to_agent_result
from policylens.mcp.models import MCPStatisticsToolResult
from policylens.settings import AppSettings
from policylens_mcp.models import StatisticsQueryRequest as ServiceStatisticsQueryRequest
from policylens_mcp.statistics import query_statistics as direct_statistics

ComparisonCase = tuple[str, StatisticsQueryRequest]

COMPARISON_CASES: tuple[ComparisonCase, ...] = (
    (
        "youth-mean-india-2020-2022",
        StatisticsQueryRequest(
            indicator="SL.UEM.1524.ZS",
            geographies=("IND",),
            start_year=2020,
            end_year=2022,
            aggregation="mean",
            group_by=(),
            row_limit=1,
        ),
    ),
    (
        "total-median-indonesia-2015-2025",
        StatisticsQueryRequest(
            indicator="SL.UEM.TOTL.ZS",
            geographies=("IDN",),
            start_year=2015,
            end_year=2025,
            aggregation="median",
            group_by=("geography",),
            row_limit=1,
        ),
    ),
    (
        "youth-observations-india-2020-2022",
        StatisticsQueryRequest(
            indicator="SL.UEM.1524.ZS",
            geographies=("IND",),
            start_year=2020,
            end_year=2022,
            aggregation="none",
            group_by=(),
            row_limit=3,
        ),
    ),
)


class StatisticsAdapter(Protocol):
    async def query_statistics(self, request: StatisticsQueryRequest) -> StatisticsToolResult: ...


def direct_query_statistics(request: StatisticsQueryRequest) -> StatisticsToolResult:
    direct_request = ServiceStatisticsQueryRequest(
        schema_version="1.0",
        indicator=request.indicator,
        geographies=sorted(request.geographies),
        start_year=request.start_year,
        end_year=request.end_year,
        aggregation=request.aggregation,
        group_by=sorted(request.group_by),
        row_limit=request.row_limit,
    )
    direct_result = direct_statistics(direct_request)
    host_result = MCPStatisticsToolResult.model_validate(direct_result.model_dump(mode="json"))
    return _to_agent_result(host_result, request)


async def evaluate_requests(
    adapter: StatisticsAdapter,
    *,
    cases: Sequence[ComparisonCase] = COMPARISON_CASES,
    direct_query: Callable[[StatisticsQueryRequest], StatisticsToolResult] = (
        direct_query_statistics
    ),
    repeats: int = 3,
) -> dict[str, Any]:
    if repeats < 1 or repeats > 20:
        raise ValueError("repeats must be between 1 and 20")
    comparisons: list[dict[str, object]] = []

    for case_name, request in cases:
        mcp_durations: list[float] = []
        direct_durations: list[float] = []
        paired_overheads: list[float] = []
        contract_parity = True
        result_parity = True
        for _ in range(repeats):
            direct_started = perf_counter()
            direct_result = await asyncio.to_thread(direct_query, request)
            direct_duration = (perf_counter() - direct_started) * 1000

            mcp_started = perf_counter()
            mcp_result = await adapter.query_statistics(request)
            mcp_duration = (perf_counter() - mcp_started) * 1000

            direct_payload = direct_result.model_dump(mode="json")
            mcp_payload = mcp_result.model_dump(mode="json")
            contract_parity = contract_parity and type(direct_result) is type(mcp_result)
            result_parity = result_parity and direct_payload == mcp_payload
            direct_durations.append(direct_duration)
            mcp_durations.append(mcp_duration)
            paired_overheads.append(mcp_duration - direct_duration)

        comparisons.append(
            {
                "case": case_name,
                "repeats": repeats,
                "contract_parity": contract_parity,
                "result_parity": result_parity,
                "direct_latency_ms_median": round(statistics.median(direct_durations), 3),
                "mcp_stdio_latency_ms_median": round(statistics.median(mcp_durations), 3),
                "paired_overhead_ms_median": round(statistics.median(paired_overheads), 3),
            }
        )

    return {
        "schema_version": "1.0",
        "comparison": "mcp_stdio_vs_direct_call",
        "measurement_scope": "local canonical datasets and local stdio process; no external calls",
        "live_measurement": False,
        "parity_passed": all(
            item["contract_parity"] and item["result_parity"] for item in comparisons
        ),
        "cases": comparisons,
    }


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        model_provider="mlx",
        mlx_model="local-evaluation-placeholder",
        embedding_provider="local",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare local MCP and direct statistics calls")
    parser.add_argument("--repeats", type=int, default=3)
    arguments = parser.parse_args()
    try:
        report = asyncio.run(
            evaluate_requests(MCPStatisticsAdapter(_settings()), repeats=arguments.repeats)
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "measurement_scope": "local only; no external calls",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["parity_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
