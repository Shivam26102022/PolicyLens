from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from policylens.retrieval.models import BlockLocation, SourceSensitivity, StructuredRowKey

MCPHostErrorCode = Literal[
    "MCP_UNAVAILABLE",
    "MCP_TIMEOUT",
    "MCP_IDENTITY_MISMATCH",
    "MCP_CAPABILITY_MISMATCH",
    "MCP_SCHEMA_INVALID",
    "MCP_MALFORMED_RESPONSE",
    "MCP_PERMISSION_DENIED",
    "MCP_RESOURCE_NOT_FOUND",
    "MCP_CATALOG_STALE",
    "MCP_INTERNAL_ERROR",
]
MCPStatisticsAggregation = Literal["none", "mean", "sum", "median"]
MCPStatisticsIndicator = Literal["SL.UEM.1524.ZS", "SL.UEM.TOTL.ZS"]
MCPStatisticsGroup = Literal["geography", "year"]
MCPHostCountryCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
EXPECTED_MCP_SERVER_NAME = "PolicyLens Policy Data Server"
EXPECTED_MCP_SERVER_VERSION = "0.1.0"
EXPECTED_MCP_PROTOCOL_VERSION = "2026-07-28"
EXPECTED_MCP_TOOL_NAME = "query_statistics"
EXPECTED_MCP_RESOURCE_TEMPLATE = "policy://sources/{source_id}/passages/{passage_id}"
EXPECTED_INPUT_SCHEMA_SHA256 = "05ccc560603964c9d2723d2da6ab63d6c5fd7e2f80a471326e0df04f677004a0"
EXPECTED_OUTPUT_SCHEMA_SHA256 = "aa505bc99655a8828e050e2c4752a4bed7bcdb04b87b3165c275d4a89ef956d0"

PassageResourceErrorCode = Literal[
    "MCP_RESOURCE_NOT_FOUND",
    "MCP_CATALOG_STALE",
    "MCP_SCHEMA_INVALID",
    "MCP_PERMISSION_DENIED",
    "MCP_INTERNAL_ERROR",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PassageRecord(StrictModel):
    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=1000)
    publisher: str = Field(min_length=1, max_length=500)
    source_uri: str | None = None
    text: str = Field(min_length=1, max_length=5000)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    locations: tuple[BlockLocation, ...] = Field(max_length=20)
    row_key: StructuredRowKey | None
    section_path: tuple[str, ...] = Field(max_length=20)
    licence: str = Field(min_length=1, max_length=1000)
    usage_constraints: str | None = Field(max_length=1000)
    sensitivity: SourceSensitivity
    permission_scope: str = Field(min_length=1, max_length=100)
    allowed_usage: tuple[str, ...] = Field(min_length=1)
    untrusted: Literal[True]

    @model_validator(mode="after")
    def validate_record(self) -> PassageRecord:
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("text_sha256 does not match passage text")
        if len(self.allowed_usage) != len(set(self.allowed_usage)):
            raise ValueError("allowed_usage must be unique")
        if "retrieval" not in self.allowed_usage:
            raise ValueError("passage is not permitted for retrieval")
        if bool(self.locations) == (self.row_key is not None):
            raise ValueError("passage must have locations or a row key")
        return self


class PassageCatalog(StrictModel):
    schema_version: Literal["1.0"]
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at: datetime
    passages: tuple[PassageRecord, ...] = Field(max_length=10000)

    @model_validator(mode="after")
    def require_unique_passage_ids(self) -> PassageCatalog:
        passage_ids = [passage.passage_id for passage in self.passages]
        if len(passage_ids) != len(set(passage_ids)):
            raise ValueError("catalog passage IDs must be unique")
        return self


class PassageResourceResult(StrictModel):
    schema_version: Literal["1.0"]
    passage: PassageRecord


class MCPHostError(StrictModel):
    schema_version: Literal["1.0"]
    error_code: MCPHostErrorCode
    message: str = Field(min_length=1, max_length=300)


class MCPAllowedTool(StrictModel):
    name: Literal["query_statistics"]
    schema_version: Literal["1.0"]
    input_schema_sha256: Literal["05ccc560603964c9d2723d2da6ab63d6c5fd7e2f80a471326e0df04f677004a0"]
    output_schema_sha256: Literal[
        "aa505bc99655a8828e050e2c4752a4bed7bcdb04b87b3165c275d4a89ef956d0"
    ]
    read_only: Literal[True]


class MCPAllowedResourceTemplate(StrictModel):
    uri_template: Literal["policy://sources/{source_id}/passages/{passage_id}"]
    schema_version: Literal["1.0"]
    read_only: Literal[True]


class MCPAllowedCapabilities(StrictModel):
    schema_version: Literal["1.0"]
    server_name: Literal["PolicyLens Policy Data Server"]
    server_version: Literal["0.1.0"]
    protocol_version: Literal["2026-07-28"]
    tools: tuple[MCPAllowedTool, ...] = Field(min_length=1, max_length=1)
    resource_templates: tuple[MCPAllowedResourceTemplate, ...] = Field(min_length=1, max_length=1)


class MCPStatisticsQuery(StrictModel):
    schema_version: Literal["1.0"]
    indicator: MCPStatisticsIndicator
    geographies: tuple[MCPHostCountryCode, ...] = Field(min_length=1, max_length=4)
    start_year: int = Field(ge=2015, le=2025)
    end_year: int = Field(ge=2015, le=2025)
    aggregation: MCPStatisticsAggregation
    group_by: tuple[MCPStatisticsGroup, ...] = Field(max_length=2)
    row_limit: int = Field(ge=1, le=44)

    @model_validator(mode="after")
    def validate_query(self) -> MCPStatisticsQuery:
        if self.start_year > self.end_year:
            raise ValueError("start_year must not exceed end_year")
        if len(self.geographies) != len(set(self.geographies)):
            raise ValueError("geographies must be unique")
        if len(self.group_by) != len(set(self.group_by)):
            raise ValueError("group_by fields must be unique")
        if self.aggregation == "none" and self.group_by:
            raise ValueError("group_by must be empty when aggregation is none")
        return self


class MCPStatisticsRowKey(StrictModel):
    observation_id: str = Field(min_length=1, max_length=500)
    country_iso3: MCPHostCountryCode
    year: int = Field(ge=2015, le=2025)


class MCPStatisticsResultRow(StrictModel):
    geography: MCPHostCountryCode | None
    country_name: str | None = Field(max_length=200)
    year: int | None = Field(ge=2015, le=2025)
    value: float | None
    unit: str = Field(max_length=100)
    observation_status: str = Field(max_length=100)
    decimal: int = Field(ge=0, le=10)


class MCPStatisticsCalculation(StrictModel):
    operation: MCPStatisticsAggregation
    formula: str = Field(min_length=1, max_length=500)
    rounding: str = Field(min_length=1, max_length=200)


class MCPStatisticsEvidence(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    row_keys: tuple[MCPStatisticsRowKey, ...] = Field(min_length=1, max_length=44)
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    canonical_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class MCPStatisticsAttribution(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=500)
    licence: str = Field(min_length=1, max_length=1000)
    attribution: str = Field(min_length=1, max_length=1000)
    usage_constraints: str = Field(min_length=1, max_length=1000)


class MCPStatisticsToolResult(StrictModel):
    schema_version: Literal["1.0"]
    query: MCPStatisticsQuery
    rows: tuple[MCPStatisticsResultRow, ...] = Field(max_length=44)
    calculation: MCPStatisticsCalculation
    evidence: tuple[MCPStatisticsEvidence, ...] = Field(min_length=1, max_length=2)
    attribution: tuple[MCPStatisticsAttribution, ...] = Field(min_length=1, max_length=2)
    warnings: tuple[str, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_result(self) -> MCPStatisticsToolResult:
        if len(self.rows) > self.query.row_limit:
            raise ValueError("statistics result exceeds request row limit")
        if self.calculation.operation != self.query.aggregation:
            raise ValueError("calculation operation differs from query")
        return self


class MCPStatisticsToolError(StrictModel):
    schema_version: Literal["1.0"]
    error_code: Literal[
        "STATISTICS_SOURCE_NOT_ALLOWED",
        "STATISTICS_INDICATOR_UNSUPPORTED",
        "STATISTICS_INVALID_ARGUMENTS",
        "STATISTICS_RANGE_INVALID",
        "STATISTICS_ROW_LIMIT_EXCEEDED",
        "STATISTICS_DATA_UNAVAILABLE",
        "STATISTICS_DATA_INVALID",
        "STATISTICS_NON_FINITE_VALUE",
    ]
    message: str = Field(min_length=1, max_length=300)


class MCPPassageResourceError(StrictModel):
    schema_version: Literal["1.0"]
    error_code: PassageResourceErrorCode
    message: str = Field(min_length=1, max_length=300)
