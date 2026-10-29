from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Callable
from time import monotonic
from typing import Annotated, Literal, Protocol
from uuid import UUID

from agents import function_tool
from pydantic import Field, ValidationError, model_validator

from policylens.agent_runtime.models import (
    AgentCalculationEvidence,
    AgentCalculationRecord,
    AgentCalculationRow,
    AgentErrorCode,
    AgentRunState,
    StrictModel,
)
from policylens.agent_runtime.state import (
    AgentRunLedger,
    AgentStateError,
    AgentToolBudgetExceeded,
)
from policylens.retrieval.models import StructuredRowKey
from policylens.settings import AppSettings

IndicatorId = Literal["SL.UEM.1524.ZS", "SL.UEM.TOTL.ZS"]
StatisticsAggregation = Literal["none", "mean", "sum", "median"]
StatisticsGroup = Literal["geography", "year"]
CountryISO3 = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
AdapterErrorCode = Literal[
    "MCP_UNAVAILABLE",
    "MCP_TIMEOUT",
    "MCP_IDENTITY_MISMATCH",
    "MCP_CAPABILITY_MISMATCH",
    "MCP_SCHEMA_INVALID",
    "MCP_MALFORMED_RESPONSE",
    "MCP_RESOURCE_NOT_FOUND",
    "MCP_CATALOG_STALE",
    "MCP_INTERNAL_ERROR",
    "MCP_PASSAGE_MISMATCH",
    "TOOL_INVALID_ARGUMENTS",
    "TOOL_MALFORMED_RESPONSE",
    "TOOL_PERMISSION_DENIED",
]


class StatisticsQueryRequest(StrictModel):
    indicator: IndicatorId
    geographies: tuple[CountryISO3, ...] = Field(min_length=1, max_length=4)
    start_year: int = Field(ge=2015, le=2025)
    end_year: int = Field(ge=2015, le=2025)
    aggregation: StatisticsAggregation
    group_by: tuple[StatisticsGroup, ...] = Field(default=(), max_length=2)
    row_limit: int = Field(default=44, ge=1, le=44)

    @model_validator(mode="after")
    def validate_ranges_and_uniqueness(self) -> StatisticsQueryRequest:
        if self.start_year > self.end_year:
            raise ValueError("start_year must not exceed end_year")
        if len(set(self.geographies)) != len(self.geographies):
            raise ValueError("geographies must be unique")
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("group_by fields must be unique")
        if self.aggregation == "none" and self.group_by:
            raise ValueError("group_by must be empty when aggregation is none")
        return self


class StatisticsCalculation(StrictModel):
    operation: StatisticsAggregation
    formula: str = Field(min_length=1, max_length=500)
    rounding: str = Field(min_length=1, max_length=200)


class StatisticsToolEvidence(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    row_keys: tuple[StructuredRowKey, ...] = Field(min_length=1, max_length=100)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class StatisticsToolResult(StrictModel):
    schema_version: Literal["1.0"]
    query: StatisticsQueryRequest
    rows: tuple[dict[str, object], ...] = Field(max_length=100)
    calculation: StatisticsCalculation
    evidence: tuple[StatisticsToolEvidence, ...] = Field(default=(), max_length=20)
    warnings: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_result(self) -> StatisticsToolResult:
        if len(self.rows) > self.query.row_limit:
            raise ValueError("tool returned more rows than requested")
        if self.rows and not self.evidence:
            raise ValueError("non-empty statistics results require source-row evidence")
        if self.calculation.operation != self.query.aggregation:
            raise ValueError("calculation operation must match the requested aggregation")
        for row in self.rows:
            if not _is_finite_json_value(row):
                raise ValueError("tool rows must contain only finite JSON values")
        return self


class AgentStatisticsToolOutput(StrictModel):
    status: Literal["succeeded", "no_results", "failed"]
    calculation: AgentToolCalculationSummary | None = None
    error_code: AgentErrorCode | None = None

    @model_validator(mode="after")
    def validate_output_state(self) -> AgentStatisticsToolOutput:
        if self.status == "succeeded":
            if self.calculation is None or self.error_code is not None:
                raise ValueError("succeeded tool output requires a calculation record")
        elif self.calculation is not None or self.error_code is None:
            raise ValueError("failed tool output requires an error code and no calculation")
        return self


class AgentToolCalculationSummary(StrictModel):
    calculation_id: UUID
    operation: str = Field(min_length=1, max_length=100)
    formula: str = Field(min_length=1, max_length=500)
    rounding: str = Field(min_length=1, max_length=200)
    rows: tuple[AgentCalculationRow, ...] = Field(max_length=100)
    evidence: tuple[AgentCalculationEvidence, ...] = Field(min_length=1, max_length=20)
    warnings: tuple[str, ...] = Field(default=(), max_length=20)


class AgentToolAdapterError(RuntimeError):
    def __init__(self, code: AdapterErrorCode, *, transient: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.transient = transient


class AgentToolExecutionError(RuntimeError):
    def __init__(self, code: AgentErrorCode) -> None:
        super().__init__(code)
        self.code = code


class StatisticsToolAdapter(Protocol):
    async def query_statistics(
        self, request: StatisticsQueryRequest
    ) -> StatisticsToolResult | dict[str, object]: ...


def _is_finite_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_finite_json_value(item) for key, item in value.items()
        )
    if isinstance(value, (tuple, list)):
        return all(_is_finite_json_value(item) for item in value)
    return False


def _safe_tool_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    safe: list[str] = []
    for warning in warnings:
        if warning == "Summed unemployment rates are percentage-point totals, not rates.":
            safe.append("Summed rates are percentage-point totals, not rates.")
        elif warning == "Source unit metadata is empty; the indicator values are percentages.":
            safe.append("Source unit metadata is empty; the indicator values are percentages.")
        elif re.fullmatch(
            r"\d+ null observation\(s\) excluded from (mean|sum|median) aggregation\.", warning
        ):
            safe.append("Null observations were excluded from the aggregation.")
        else:
            safe.append("Unrecognized tool warning text was omitted as untrusted.")
    return tuple(dict.fromkeys(safe))


def _calculation_row(
    row: dict[str, object], request: StatisticsQueryRequest
) -> AgentCalculationRow:
    geography = row.get("geography", row.get("country_iso3"))
    year = row.get("year")
    value = row.get("value")
    unit = row.get("unit")
    status = row.get("status", row.get("value_status"))
    if geography is not None and (
        not isinstance(geography, str) or geography not in request.geographies
    ):
        raise ValueError("statistics result contains an unrequested geography")
    if year is not None and (
        isinstance(year, bool)
        or not isinstance(year, int)
        or not request.start_year <= year <= request.end_year
    ):
        raise ValueError("statistics result contains an invalid year")
    if unit is not None and (
        not isinstance(unit, str) or unit not in {"", "percent", "%", "percentage points"}
    ):
        raise ValueError("statistics result contains an unrecognized unit")
    if status is not None and (
        not isinstance(status, str)
        or (status not in {"", "aggregated"} and not re.fullmatch(r"[A-Z]{1,3}", status))
    ):
        raise ValueError("statistics result contains an unrecognized status")
    return AgentCalculationRow(
        geography=geography if isinstance(geography, str) else None,
        year=year if isinstance(year, int) and not isinstance(year, bool) else None,
        value=(
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        ),
        unit=unit if isinstance(unit, str) else None,
        status=status if isinstance(status, str) else None,
    )


class AgentToolExecutor:
    def __init__(
        self,
        adapter: StatisticsToolAdapter,
        ledger: AgentRunLedger,
        settings: AppSettings,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._adapter = adapter
        self._ledger = ledger
        self._settings = settings
        self._clock = clock
        self._cache: dict[str, AgentCalculationRecord | None] = {}

    async def execute(self, request: StatisticsQueryRequest) -> AgentCalculationRecord | None:
        key = request.model_dump_json()
        if key in self._cache:
            return self._cache[key]
        outcome = await self._execute_uncached(request)
        self._cache[key] = outcome
        return outcome

    async def _execute_uncached(
        self, request: StatisticsQueryRequest
    ) -> AgentCalculationRecord | None:
        if self._ledger.state == AgentRunState.ASSESSING:
            self._ledger.transition(AgentRunState.TOOL_EXECUTION)
        elif self._ledger.state != AgentRunState.TOOL_EXECUTION:
            raise AgentStateError("statistics tool is not allowed in the current run state")
        attempt = 0
        while True:
            provider_error: Exception | None = None
            try:
                tool_call_id = self._ledger.begin_tool_call("query_statistics")
            except AgentToolBudgetExceeded as error:
                self._fail("TOOL_BUDGET_EXCEEDED")
                raise AgentToolExecutionError("TOOL_BUDGET_EXCEEDED") from error

            started_at = self._clock()
            try:
                raw_result = await asyncio.wait_for(
                    self._adapter.query_statistics(request),
                    timeout=self._settings.mcp_timeout_seconds,
                )
                result = StatisticsToolResult.model_validate(raw_result)
                if result.query != request:
                    raise ValueError("tool result query does not match its request")
            except AgentToolAdapterError as error:
                code = error.code
                transient = error.transient
            except TimeoutError:
                code = "MCP_TIMEOUT"
                transient = True
            except ValidationError as error:
                self._record_failed_call(
                    tool_call_id, started_at, "TOOL_MALFORMED_RESPONSE", attempt
                )
                self._ledger.mark_tool_failure("TOOL_MALFORMED_RESPONSE")
                raise AgentToolExecutionError("TOOL_MALFORMED_RESPONSE") from error
            except ValueError as error:
                self._record_failed_call(
                    tool_call_id, started_at, "TOOL_MALFORMED_RESPONSE", attempt
                )
                self._ledger.mark_tool_failure("TOOL_MALFORMED_RESPONSE")
                raise AgentToolExecutionError("TOOL_MALFORMED_RESPONSE") from error
            except Exception as error:
                code = "MCP_UNAVAILABLE"
                transient = True
                provider_error = error
            else:
                if not result.rows:
                    self._ledger.end_tool_call(
                        "query_statistics",
                        status="succeeded",
                        duration_ms=max(0.0, (self._clock() - started_at) * 1000),
                        tool_call_id=tool_call_id,
                        retry_count=attempt,
                    )
                    self._ledger.transition(AgentRunState.ASSESSING)
                    return None
                try:
                    calculation_rows = tuple(_calculation_row(row, request) for row in result.rows)
                except ValueError as error:
                    self._record_failed_call(
                        tool_call_id, started_at, "TOOL_MALFORMED_RESPONSE", attempt
                    )
                    self._ledger.mark_tool_failure("TOOL_MALFORMED_RESPONSE")
                    raise AgentToolExecutionError("TOOL_MALFORMED_RESPONSE") from error
                calculation = AgentCalculationRecord(
                    tool_call_id=tool_call_id,
                    tool_name="query_statistics",
                    operation=result.calculation.operation,
                    formula=result.calculation.formula,
                    rounding=result.calculation.rounding,
                    rows=calculation_rows,
                    evidence=tuple(
                        AgentCalculationEvidence(
                            source_id=item.source_id,
                            row_keys=item.row_keys,
                            content_sha256=item.content_sha256,
                        )
                        for item in result.evidence
                    ),
                    warnings=_safe_tool_warnings(result.warnings),
                )
                self._ledger.record_calculation(calculation)
                self._ledger.end_tool_call(
                    "query_statistics",
                    status="succeeded",
                    duration_ms=max(0.0, (self._clock() - started_at) * 1000),
                    tool_call_id=tool_call_id,
                    retry_count=attempt,
                )
                self._ledger.transition(AgentRunState.ASSESSING)
                return calculation

            self._record_failed_call(tool_call_id, started_at, code, attempt)
            if self._ledger.can_retry_tool(code, transient=transient):
                self._ledger.consume_retry("query_statistics")
                attempt += 1
                continue
            self._fail(code)
            if provider_error is not None:
                raise AgentToolExecutionError(code) from provider_error
            raise AgentToolExecutionError(code)

    def _fail(self, code: AgentErrorCode) -> None:
        self._ledger.mark_tool_failure(code)
        terminal_state = (
            AgentRunState.BLOCKED
            if code in {"TOOL_INVALID_ARGUMENTS", "TOOL_PERMISSION_DENIED"}
            else AgentRunState.FAILED_SAFE
        )
        if self._ledger.state not in {
            AgentRunState.ANSWERED,
            AgentRunState.CLARIFICATION_REQUIRED,
            AgentRunState.ABSTAINED,
            AgentRunState.CONFLICT,
            AgentRunState.BLOCKED,
            AgentRunState.FAILED_SAFE,
        }:
            self._ledger.transition(terminal_state)

    def _record_failed_call(
        self, tool_call_id: UUID, started_at: float, code: AgentErrorCode, attempt: int
    ) -> None:
        self._ledger.end_tool_call(
            "query_statistics",
            status="failed",
            duration_ms=max(0.0, (self._clock() - started_at) * 1000),
            tool_call_id=tool_call_id,
            error_code=code,
            retry_count=attempt,
        )


def build_query_statistics_tool(
    executor: AgentToolExecutor,
    *,
    structured_output_schema: bool = True,
):
    def format_output(output: AgentStatisticsToolOutput) -> AgentStatisticsToolOutput | str:
        return output if structured_output_schema else output.model_dump_json()

    @function_tool(
        name_override="query_statistics",
        description_override=(
            "Run the approved deterministic statistics aggregation for validated indicators "
            "and geographies. Use only when a calculation is needed. Geographies must be "
            "uppercase ISO3 codes, years must be from 2015 through 2025, and row_limit must "
            "be from 1 through 44. If aggregation is none, group_by must be empty."
        ),
        strict_mode=True,
        timeout=executor._settings.mcp_timeout_seconds,
        failure_error_function=None,
        output_type=AgentStatisticsToolOutput if structured_output_schema else None,
    )
    async def query_statistics(
        indicator: IndicatorId,
        geographies: Annotated[
            list[CountryISO3],
            Field(
                min_length=1,
                max_length=4,
                description="One to four unique uppercase ISO3 geography codes.",
            ),
        ],
        start_year: Annotated[int, Field(ge=2015, le=2025)],
        end_year: Annotated[int, Field(ge=2015, le=2025)],
        aggregation: StatisticsAggregation,
        group_by: Annotated[
            list[StatisticsGroup],
            Field(
                max_length=2,
                description="Unique grouping fields; must be empty when aggregation is none.",
            ),
        ],
        row_limit: Annotated[int, Field(ge=1, le=44)],
    ) -> AgentStatisticsToolOutput | str:
        if executor._ledger.tool_error_code is not None:
            return format_output(
                AgentStatisticsToolOutput(
                    status="failed", error_code=executor._ledger.tool_error_code
                )
            )
        try:
            request = StatisticsQueryRequest(
                indicator=indicator,
                geographies=tuple(geographies),
                start_year=start_year,
                end_year=end_year,
                aggregation=aggregation,
                group_by=tuple(group_by),
                row_limit=row_limit,
            )
            calculation = await executor.execute(request)
        except ValidationError as error:
            executor._fail("TOOL_INVALID_ARGUMENTS")
            raise AgentToolExecutionError("TOOL_INVALID_ARGUMENTS") from error
        except AgentToolExecutionError:
            raise
        if calculation is None:
            return format_output(
                AgentStatisticsToolOutput(status="no_results", error_code="INSUFFICIENT_EVIDENCE")
            )
        return format_output(
            AgentStatisticsToolOutput(
                status="succeeded",
                calculation=AgentToolCalculationSummary(
                    calculation_id=calculation.calculation_id,
                    operation=calculation.operation,
                    formula=calculation.formula,
                    rounding=calculation.rounding,
                    rows=calculation.rows,
                    evidence=calculation.evidence,
                    warnings=calculation.warnings,
                ),
            )
        )

    return query_statistics
