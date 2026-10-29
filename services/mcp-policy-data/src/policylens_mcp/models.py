from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
StatisticsIndicator = Literal["SL.UEM.1524.ZS", "SL.UEM.TOTL.ZS"]
Aggregation = Literal["none", "mean", "sum", "median"]
GroupField = Literal["geography", "year"]
StatisticsToolErrorCode = Literal[
    "STATISTICS_SOURCE_NOT_ALLOWED",
    "STATISTICS_INDICATOR_UNSUPPORTED",
    "STATISTICS_INVALID_ARGUMENTS",
    "STATISTICS_RANGE_INVALID",
    "STATISTICS_ROW_LIMIT_EXCEEDED",
    "STATISTICS_DATA_UNAVAILABLE",
    "STATISTICS_DATA_INVALID",
    "STATISTICS_NON_FINITE_VALUE",
]


class StatisticsQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    indicator: StatisticsIndicator
    geographies: list[CountryCode] = Field(min_length=1, max_length=4)
    start_year: int = Field(ge=2015, le=2025)
    end_year: int = Field(ge=2015, le=2025)
    aggregation: Aggregation
    group_by: list[GroupField] = Field(max_length=2)
    row_limit: int = Field(ge=1, le=44)

    @field_validator("geographies")
    @classmethod
    def require_unique_geographies(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Geographies must be unique")
        return values

    @model_validator(mode="after")
    def validate_query(self) -> StatisticsQueryRequest:
        if self.start_year > self.end_year:
            raise ValueError("start_year must be less than or equal to end_year")
        if len(self.group_by) != len(set(self.group_by)):
            raise ValueError("group_by fields must be unique")
        if self.aggregation == "none" and self.group_by:
            raise ValueError("group_by must be empty when aggregation is none")
        return self


class StatisticsRowKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = Field(min_length=1, max_length=500)
    country_iso3: CountryCode
    year: int = Field(ge=2015, le=2025)


class StatisticsResultRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    geography: CountryCode | None
    country_name: str | None = Field(max_length=200)
    year: int | None = Field(ge=2015, le=2025)
    value: float | None
    unit: str = Field(max_length=100)
    observation_status: str = Field(max_length=100)
    decimal: int = Field(ge=0, le=10)

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class StatisticsCalculation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Aggregation
    formula: str = Field(min_length=1, max_length=500)
    rounding: str = Field(min_length=1, max_length=200)


class StatisticsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=200)
    row_keys: list[StatisticsRowKey] = Field(min_length=1, max_length=44)
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    canonical_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class StatisticsAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=500)
    licence: str = Field(min_length=1, max_length=1000)
    attribution: str = Field(min_length=1, max_length=1000)
    usage_constraints: str = Field(min_length=1, max_length=1000)


class StatisticsToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    query: StatisticsQueryRequest
    rows: list[StatisticsResultRow] = Field(max_length=44)
    calculation: StatisticsCalculation
    evidence: list[StatisticsEvidence] = Field(min_length=1, max_length=2)
    attribution: list[StatisticsAttribution] = Field(min_length=1, max_length=2)
    warnings: list[str] = Field(max_length=20)


class StatisticsToolError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    error_code: StatisticsToolErrorCode
    message: str = Field(min_length=1, max_length=300)


class CanonicalSourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    title: str
    publisher: str
    canonical_url: str
    retrieved_at: str
    published_at: str | None
    licence: str
    usage_constraints: str | None
    sensitivity: Literal["public", "synthetic", "anonymised"]
    language: str = "en"
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    indicator_id: str | None = None
    countries: tuple[str, ...] = ()
    year_range: tuple[int, int] | None = None


class CanonicalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = Field(min_length=1, max_length=500)
    country_iso2: str
    country_iso3: CountryCode
    country_name: str = Field(min_length=1, max_length=200)
    year: int = Field(ge=2015, le=2025)
    value: float | None
    unit: str = Field(max_length=100)
    observation_status: str = Field(max_length=100)
    decimal: int = Field(ge=0, le=10)

    @field_validator("value", mode="before")
    @classmethod
    def reject_boolean_values(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("value must be numeric or null")
        return value

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite")
        return value

    @field_validator("decimal", mode="before")
    @classmethod
    def reject_boolean_decimal(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("decimal must be an integer")
        return value


class CanonicalStructuredDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    dataset_id: str
    source_id: str
    title: str
    indicator_id: str
    indicator_label: str
    country_codes: tuple[str, ...]
    year_range: tuple[int, int]
    api_metadata: dict[str, Any]
    observations: tuple[CanonicalObservation, ...]
    missing_value_semantics: str
    provenance: CanonicalSourceMetadata
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str


class PassageLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=300)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> PassageLocation:
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class PassageRowKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1, max_length=500)
    observation_id: str = Field(min_length=1, max_length=500)
    indicator_id: str = Field(min_length=1, max_length=100)
    country_iso3: CountryCode
    year: int = Field(ge=1900, le=2100)


class PassageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=1000)
    publisher: str = Field(min_length=1, max_length=500)
    source_uri: str | None
    text: str = Field(min_length=1, max_length=5000)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    locations: list[PassageLocation] = Field(max_length=20)
    row_key: PassageRowKey | None
    section_path: list[str] = Field(max_length=20)
    licence: str = Field(min_length=1, max_length=1000)
    usage_constraints: str | None = Field(max_length=1000)
    sensitivity: Literal["public", "synthetic", "anonymised"]
    permission_scope: str = Field(min_length=1, max_length=100)
    allowed_usage: list[str] = Field(min_length=1)
    untrusted: Literal[True]

    @model_validator(mode="after")
    def validate_passage(self) -> PassageRecord:
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("text_sha256 does not match passage text")
        if len(self.allowed_usage) != len(set(self.allowed_usage)):
            raise ValueError("allowed_usage must be unique")
        if "retrieval" not in self.allowed_usage:
            raise ValueError("passage is not permitted for retrieval")
        if bool(self.locations) == (self.row_key is not None):
            raise ValueError("passage must have locations or a row key")
        return self


class PassageCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at: datetime
    passages: list[PassageRecord] = Field(max_length=10000)

    @model_validator(mode="after")
    def validate_passage_ids(self) -> PassageCatalog:
        passage_ids = [passage.passage_id for passage in self.passages]
        if passage_ids != sorted(passage_ids) or len(passage_ids) != len(set(passage_ids)):
            raise ValueError("catalog passages must have unique sorted IDs")
        return self


class PassageResourceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    passage: PassageRecord


class ActiveIndexPointer(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: Literal["1.0"]
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")


PassageResourceErrorCode = Literal[
    "MCP_RESOURCE_NOT_FOUND",
    "MCP_CATALOG_STALE",
    "MCP_SCHEMA_INVALID",
    "MCP_PERMISSION_DENIED",
    "MCP_INTERNAL_ERROR",
]


class PassageResourceError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    error_code: PassageResourceErrorCode
    message: str = Field(min_length=1, max_length=300)
