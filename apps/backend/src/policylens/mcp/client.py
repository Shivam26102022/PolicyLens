from __future__ import annotations

import hashlib
import json
import logging
import re
import shlex
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any, Protocol
from uuid import uuid4

import anyio
from mcp import Client, StdioServerParameters
from pydantic import ValidationError

from policylens.agent_runtime.tools import (
    AgentToolAdapterError,
    StatisticsCalculation,
    StatisticsQueryRequest,
    StatisticsToolEvidence,
    StatisticsToolResult,
)
from policylens.mcp.models import (
    EXPECTED_INPUT_SCHEMA_SHA256,
    EXPECTED_MCP_PROTOCOL_VERSION,
    EXPECTED_MCP_RESOURCE_TEMPLATE,
    EXPECTED_MCP_SERVER_NAME,
    EXPECTED_MCP_SERVER_VERSION,
    EXPECTED_MCP_TOOL_NAME,
    EXPECTED_OUTPUT_SCHEMA_SHA256,
    MCPHostErrorCode,
    MCPPassageResourceError,
    MCPStatisticsQuery,
    MCPStatisticsToolError,
    MCPStatisticsToolResult,
    PassageRecord,
    PassageResourceResult,
)
from policylens.retrieval.models import StructuredRowKey
from policylens.settings import PROJECT_ROOT

logger = logging.getLogger("policylens-api")
PASSAGE_URI_PATTERN = re.compile(
    r"^policy://sources/([A-Za-z0-9._-]{1,200})/passages/(sha256:[a-f0-9]{64})$"
)
MAX_RESOURCE_RESPONSE_BYTES = 100_000


class MCPClientConfig(Protocol):
    mcp_server_command: str
    mcp_timeout_seconds: int


class MCPClientConnection(Protocol):
    server_info: Any
    protocol_version: str

    async def list_tools(self) -> Any: ...

    async def list_resource_templates(self) -> Any: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        read_timeout_seconds: float | None = None,
    ) -> Any: ...

    async def read_resource(self, uri: str) -> Any: ...


MCPClientFactory = Callable[[StdioServerParameters], Any]


class MCPClientError(RuntimeError):
    def __init__(
        self,
        code: MCPHostErrorCode,
        message: str,
        *,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.transient = transient


def _canonical_sha256(value: object) -> str:
    if not isinstance(value, dict):
        raise MCPClientError("MCP_SCHEMA_INVALID", "MCP schema is missing or malformed")
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MCPClientError("MCP_SCHEMA_INVALID", "MCP schema is malformed") from error
    return hashlib.sha256(encoded).hexdigest()


def _stdio_parameters(settings: MCPClientConfig) -> StdioServerParameters:
    if getattr(settings, "mcp_transport", "stdio") != "stdio":
        raise MCPClientError("MCP_CAPABILITY_MISMATCH", "Only stdio MCP transport is supported")
    try:
        command = shlex.split(settings.mcp_server_command)
    except ValueError as error:
        raise MCPClientError("MCP_UNAVAILABLE", "MCP server command is invalid") from error
    if not command:
        raise MCPClientError("MCP_UNAVAILABLE", "MCP server command is empty", transient=True)
    return StdioServerParameters(
        command=command[0],
        args=command[1:],
        cwd=str(PROJECT_ROOT),
    )


def _tool_schema(tool: Any, camel_name: str, snake_name: str) -> object:
    schema = getattr(tool, camel_name, None)
    if schema is None:
        schema = getattr(tool, snake_name, None)
    return schema


async def _validate_server_contract(client: MCPClientConnection) -> tuple[str, str]:
    server_info = client.server_info
    if (
        server_info is None
        or getattr(server_info, "name", None) != EXPECTED_MCP_SERVER_NAME
        or getattr(server_info, "version", None) != EXPECTED_MCP_SERVER_VERSION
        or client.protocol_version != EXPECTED_MCP_PROTOCOL_VERSION
    ):
        raise MCPClientError(
            "MCP_IDENTITY_MISMATCH", "MCP server identity or protocol is unexpected"
        )

    tools_response = await client.list_tools()
    tools = getattr(tools_response, "tools", None)
    if not isinstance(tools, list) or len(tools) != 1:
        raise MCPClientError("MCP_CAPABILITY_MISMATCH", "MCP tool allow-list does not match")
    tool = tools[0]
    if getattr(tool, "name", None) != EXPECTED_MCP_TOOL_NAME:
        raise MCPClientError("MCP_CAPABILITY_MISMATCH", "MCP tool allow-list does not match")
    if (
        _canonical_sha256(_tool_schema(tool, "inputSchema", "input_schema"))
        != EXPECTED_INPUT_SCHEMA_SHA256
        or _canonical_sha256(_tool_schema(tool, "outputSchema", "output_schema"))
        != EXPECTED_OUTPUT_SCHEMA_SHA256
    ):
        raise MCPClientError("MCP_SCHEMA_INVALID", "MCP tool schemas do not match the contract")

    resources_response = await client.list_resource_templates()
    templates = getattr(resources_response, "resource_templates", None)
    if not isinstance(templates, list) or len(templates) != 1:
        raise MCPClientError("MCP_CAPABILITY_MISMATCH", "MCP resource allow-list does not match")
    if getattr(templates[0], "uri_template", None) != EXPECTED_MCP_RESOURCE_TEMPLATE:
        raise MCPClientError("MCP_CAPABILITY_MISMATCH", "MCP resource allow-list does not match")
    return server_info.name, server_info.version


def _argument_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _log_request(
    *,
    server_name: str | None,
    server_version: str | None,
    operation_name: str,
    argument_hash: str,
    status: str,
    duration_ms: float,
    trace_id: str,
    error_code: str | None = None,
) -> None:
    logger.info(
        "MCP request completed",
        extra={
            "event": "mcp_request",
            "server_name": server_name or EXPECTED_MCP_SERVER_NAME,
            "server_version": server_version or "unknown",
            "tool_name": operation_name if operation_name == EXPECTED_MCP_TOOL_NAME else None,
            "resource_name": operation_name if operation_name != EXPECTED_MCP_TOOL_NAME else None,
            "argument_hash": argument_hash,
            "status": status,
            "duration_ms": round(duration_ms, 3),
            "trace_id": trace_id,
            "error_code": error_code,
        },
    )


def _map_adapter_error(error: MCPClientError) -> AgentToolAdapterError:
    if error.code == "MCP_TIMEOUT":
        return AgentToolAdapterError("MCP_TIMEOUT", transient=error.transient)
    if error.code == "MCP_UNAVAILABLE":
        return AgentToolAdapterError("MCP_UNAVAILABLE", transient=error.transient)
    if error.code == "MCP_PERMISSION_DENIED":
        return AgentToolAdapterError("TOOL_PERMISSION_DENIED", transient=False)
    if error.code in {
        "MCP_IDENTITY_MISMATCH",
        "MCP_CAPABILITY_MISMATCH",
        "MCP_SCHEMA_INVALID",
        "MCP_MALFORMED_RESPONSE",
        "MCP_RESOURCE_NOT_FOUND",
        "MCP_CATALOG_STALE",
        "MCP_INTERNAL_ERROR",
    }:
        return AgentToolAdapterError(error.code, transient=error.transient)
    return AgentToolAdapterError("TOOL_MALFORMED_RESPONSE", transient=False)


def _map_statistics_error(error: MCPStatisticsToolError) -> AgentToolAdapterError:
    if error.error_code == "STATISTICS_SOURCE_NOT_ALLOWED":
        return AgentToolAdapterError("TOOL_PERMISSION_DENIED", transient=False)
    if error.error_code in {
        "STATISTICS_INDICATOR_UNSUPPORTED",
        "STATISTICS_INVALID_ARGUMENTS",
        "STATISTICS_RANGE_INVALID",
        "STATISTICS_ROW_LIMIT_EXCEEDED",
    }:
        return AgentToolAdapterError("TOOL_INVALID_ARGUMENTS", transient=False)
    if error.error_code == "STATISTICS_DATA_UNAVAILABLE":
        return AgentToolAdapterError("MCP_UNAVAILABLE", transient=False)
    return AgentToolAdapterError("TOOL_MALFORMED_RESPONSE", transient=False)


def _to_agent_result(
    result: MCPStatisticsToolResult,
    request: StatisticsQueryRequest,
) -> StatisticsToolResult:
    expected_query = MCPStatisticsQuery(
        schema_version="1.0",
        indicator=request.indicator,
        geographies=tuple(sorted(request.geographies)),
        start_year=request.start_year,
        end_year=request.end_year,
        aggregation=request.aggregation,
        group_by=tuple(sorted(request.group_by)),
        row_limit=request.row_limit,
    )
    if result.query != expected_query:
        raise MCPClientError("MCP_MALFORMED_RESPONSE", "MCP result query differs from request")

    evidence = tuple(
        StatisticsToolEvidence(
            source_id=item.source_id,
            row_keys=tuple(
                StructuredRowKey(
                    dataset_id=f"doc:{item.source_id}:{item.raw_sha256}",
                    observation_id=row_key.observation_id,
                    indicator_id=request.indicator,
                    country_iso3=row_key.country_iso3,
                    year=row_key.year,
                )
                for row_key in item.row_keys
            ),
            content_sha256=item.raw_sha256,
        )
        for item in result.evidence
    )
    return StatisticsToolResult(
        schema_version="1.0",
        query=request,
        rows=tuple(row.model_dump(mode="json") for row in result.rows),
        calculation=StatisticsCalculation(
            operation=result.calculation.operation,
            formula=result.calculation.formula,
            rounding=result.calculation.rounding,
        ),
        evidence=evidence,
        warnings=result.warnings,
    )


class MCPStatisticsAdapter:
    def __init__(
        self,
        settings: MCPClientConfig,
        *,
        client_factory: MCPClientFactory = Client,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[tuple[MCPClientConnection, tuple[str, str]]]:
        parameters = _stdio_parameters(self._settings)
        try:
            with anyio.fail_after(self._settings.mcp_timeout_seconds):
                async with self._client_factory(parameters) as client:
                    identity = await _validate_server_contract(client)
                    yield client, identity
        except (AgentToolAdapterError, MCPClientError):
            raise
        except TimeoutError as error:
            raise MCPClientError("MCP_TIMEOUT", "MCP request timed out", transient=True) from error
        except Exception as error:
            raise MCPClientError(
                "MCP_UNAVAILABLE", "MCP server is unavailable", transient=True
            ) from error

    @staticmethod
    def _wire_request(request: StatisticsQueryRequest) -> dict[str, Any]:
        try:
            validated = MCPStatisticsQuery(
                schema_version="1.0",
                indicator=request.indicator,
                geographies=tuple(sorted(request.geographies)),
                start_year=request.start_year,
                end_year=request.end_year,
                aggregation=request.aggregation,
                group_by=tuple(sorted(request.group_by)),
                row_limit=request.row_limit,
            )
        except ValidationError as error:
            raise AgentToolAdapterError("TOOL_INVALID_ARGUMENTS", transient=False) from error
        return validated.model_dump(mode="json")

    async def query_statistics(self, request: StatisticsQueryRequest) -> StatisticsToolResult:
        argument_hash = _argument_hash(request.model_dump(mode="json"))
        trace_id = str(uuid4())
        started_at = monotonic()
        server_name: str | None = None
        server_version: str | None = None
        try:
            arguments = self._wire_request(request)
            async with self._connect() as (client, identity):
                server_name, server_version = identity
                tool_result = await client.call_tool(
                    EXPECTED_MCP_TOOL_NAME,
                    arguments,
                    read_timeout_seconds=float(self._settings.mcp_timeout_seconds),
                )
                if getattr(tool_result, "is_error", False):
                    raise MCPClientError("MCP_INTERNAL_ERROR", "MCP tool call failed")
                structured = getattr(tool_result, "structured_content", None)
                if not isinstance(structured, dict) or set(structured) != {"result"}:
                    raise MCPClientError("MCP_MALFORMED_RESPONSE", "MCP tool response is malformed")
                raw_result = structured["result"]
                if isinstance(raw_result, dict) and "error_code" in raw_result:
                    try:
                        parsed_error = MCPStatisticsToolError.model_validate(raw_result)
                    except ValidationError as error:
                        raise MCPClientError(
                            "MCP_MALFORMED_RESPONSE", "MCP tool error does not match its schema"
                        ) from error
                    raise _map_statistics_error(parsed_error)
                try:
                    parsed = MCPStatisticsToolResult.model_validate(raw_result)
                except ValidationError as error:
                    raise MCPClientError(
                        "MCP_MALFORMED_RESPONSE", "MCP tool result does not match its schema"
                    ) from error
                if isinstance(parsed, MCPStatisticsToolError):
                    raise _map_statistics_error(parsed)
                agent_result = _to_agent_result(parsed, request)
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name=EXPECTED_MCP_TOOL_NAME,
                argument_hash=argument_hash,
                status="succeeded",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
            )
            return agent_result
        except AgentToolAdapterError as error:
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name=EXPECTED_MCP_TOOL_NAME,
                argument_hash=argument_hash,
                status="failed",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
                error_code=error.code,
            )
            raise
        except MCPClientError as error:
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name=EXPECTED_MCP_TOOL_NAME,
                argument_hash=argument_hash,
                status="failed",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
                error_code=error.code,
            )
            raise _map_adapter_error(error) from error
        except Exception as error:
            mapped = AgentToolAdapterError("TOOL_MALFORMED_RESPONSE", transient=False)
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name=EXPECTED_MCP_TOOL_NAME,
                argument_hash=_argument_hash(arguments),
                status="failed",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
                error_code=mapped.code,
            )
            raise mapped from error

    async def probe(self) -> None:
        async with self._connect():
            return None

    @staticmethod
    def _validate_resource_uri(uri: str) -> tuple[str, str]:
        match = PASSAGE_URI_PATTERN.fullmatch(uri)
        if match is None or match.group(1) in {".", ".."}:
            raise MCPClientError("MCP_RESOURCE_NOT_FOUND", "Passage resource was not found")
        return match.group(1), match.group(2)

    @classmethod
    def _parse_passage_resource(cls, uri: str, response: Any) -> PassageRecord:
        source_id, passage_id = cls._validate_resource_uri(uri)
        contents = getattr(response, "contents", None)
        if not isinstance(contents, list) or len(contents) != 1:
            raise MCPClientError("MCP_MALFORMED_RESPONSE", "MCP resource response is malformed")
        content = contents[0]
        text = getattr(content, "text", None)
        mime_type = getattr(content, "mime_type", None)
        if (
            not isinstance(text, str)
            or mime_type != "application/json"
            or len(text.encode("utf-8")) > MAX_RESOURCE_RESPONSE_BYTES
        ):
            raise MCPClientError("MCP_MALFORMED_RESPONSE", "MCP resource response is malformed")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise MCPClientError(
                "MCP_MALFORMED_RESPONSE", "MCP resource does not match its schema"
            ) from error
        if isinstance(payload, dict) and "error_code" in payload:
            try:
                parsed_error = MCPPassageResourceError.model_validate(payload)
            except ValidationError as error:
                raise MCPClientError(
                    "MCP_MALFORMED_RESPONSE", "MCP resource error does not match its schema"
                ) from error
            raise MCPClientError(parsed_error.error_code, parsed_error.message)
        try:
            parsed = PassageResourceResult.model_validate(payload)
        except ValidationError as error:
            raise MCPClientError(
                "MCP_MALFORMED_RESPONSE", "MCP resource does not match its schema"
            ) from error
        if (
            parsed.passage.source_id != source_id
            or parsed.passage.passage_id != passage_id
            or not parsed.passage.untrusted
        ):
            raise MCPClientError(
                "MCP_MALFORMED_RESPONSE", "MCP resource does not match its requested ID"
            )
        return parsed.passage

    async def read_passage(self, uri: str) -> PassageRecord:
        trace_id = str(uuid4())
        started_at = monotonic()
        argument_hash = _argument_hash({"uri": uri})
        server_name: str | None = None
        server_version: str | None = None
        try:
            self._validate_resource_uri(uri)
            async with self._connect() as (client, identity):
                server_name, server_version = identity
                response = await client.read_resource(uri)
                passage = self._parse_passage_resource(uri, response)
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name="read_source_passage",
                argument_hash=argument_hash,
                status="succeeded",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
            )
            return passage
        except MCPClientError as error:
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name="read_source_passage",
                argument_hash=argument_hash,
                status="failed",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
                error_code=error.code,
            )
            raise

    async def read_passages(
        self,
        passage_keys: tuple[tuple[str, str], ...],
    ) -> tuple[PassageRecord, ...]:
        if not passage_keys:
            return ()
        if len(passage_keys) > 20 or len(set(passage_keys)) != len(passage_keys):
            raise AgentToolAdapterError("TOOL_INVALID_ARGUMENTS", transient=False)

        uris = tuple(
            f"policy://sources/{source_id}/passages/{passage_id}"
            for source_id, passage_id in passage_keys
        )
        trace_id = str(uuid4())
        started_at = monotonic()
        argument_hash = _argument_hash({"uris": uris})
        server_name: str | None = None
        server_version: str | None = None
        try:
            for uri in uris:
                self._validate_resource_uri(uri)
            async with self._connect() as (client, identity):
                server_name, server_version = identity
                passages_list: list[PassageRecord] = []
                for uri in uris:
                    response = await client.read_resource(uri)
                    passages_list.append(self._parse_passage_resource(uri, response))
                passages = tuple(passages_list)
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name="read_source_passage",
                argument_hash=argument_hash,
                status="succeeded",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
            )
            return passages
        except MCPClientError as error:
            mapped = _map_adapter_error(error)
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name="read_source_passage",
                argument_hash=argument_hash,
                status="failed",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
                error_code=mapped.code,
            )
            raise mapped from error
        except AgentToolAdapterError:
            raise
        except Exception as error:
            mapped = AgentToolAdapterError("TOOL_MALFORMED_RESPONSE", transient=False)
            _log_request(
                server_name=server_name,
                server_version=server_version,
                operation_name="read_source_passage",
                argument_hash=argument_hash,
                status="failed",
                duration_ms=(monotonic() - started_at) * 1000,
                trace_id=trace_id,
                error_code=mapped.code,
            )
            raise mapped from error
