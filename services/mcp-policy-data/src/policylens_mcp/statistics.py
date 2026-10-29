from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from policylens_mcp.models import (
    CanonicalObservation,
    CanonicalStructuredDataset,
    StatisticsAttribution,
    StatisticsCalculation,
    StatisticsEvidence,
    StatisticsQueryRequest,
    StatisticsResultRow,
    StatisticsRowKey,
    StatisticsToolErrorCode,
    StatisticsToolResult,
)
from policylens_mcp.settings import PROJECT_ROOT

APPROVED_SOURCE_INDICATORS = {
    "wb-youth-unemployment-1524-2015-2025": "SL.UEM.1524.ZS",
    "wb-total-unemployment-2015-2025": "SL.UEM.TOTL.ZS",
}
MAX_CANONICAL_BYTES = 2_000_000
MAX_MANIFEST_BYTES = 5_000_000
MAX_REGISTRY_BYTES = 1_000_000
ROUNDING_QUANTUM = Decimal("0.000001")


class StatisticsDataError(ValueError):
    def __init__(self, code: StatisticsToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class _ApprovedRegistrySource(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    source_id: str
    source_kind: Literal["structured"]
    title: str
    publisher: str
    canonical_url: str
    indicator_id: str
    countries: tuple[str, ...]
    year_range: tuple[int, int]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    license_review_status: Literal["verified"]
    licence: str
    attribution: str
    usage_constraints: str = Field(min_length=1)
    sensitivity: Literal["public"]
    allowed_usage: tuple[str, ...]


class _SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: str
    sources: tuple[dict[str, Any], ...]


class _IngestionAttempt(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    source_id: str
    status: str
    input_sha256: str | None = None
    canonical_path: str | None = None
    canonical_sha256: str | None = None
    quality_status: str | None = None
    parser_version: str | None = None


class _IngestionRun(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    finished_at: datetime | None = None
    status: str
    attempts: tuple[_IngestionAttempt, ...] = ()


class _IngestionManifest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: str
    runs: tuple[_IngestionRun, ...]


@dataclass(frozen=True)
class _StatisticsSource:
    registry: _ApprovedRegistrySource
    dataset: CanonicalStructuredDataset
    raw_sha256: str
    canonical_sha256: str
    unit: str


def _read_bytes(
    path: Path,
    *,
    maximum_bytes: int,
    code: StatisticsToolErrorCode,
    unavailable: bool = False,
) -> bytes:
    try:
        if path.stat().st_size > maximum_bytes:
            raise StatisticsDataError(code, "Approved statistics data exceeds its size limit")
        return path.read_bytes()
    except FileNotFoundError as error:
        error_code: StatisticsToolErrorCode = "STATISTICS_DATA_UNAVAILABLE" if unavailable else code
        message = (
            "Approved statistics data is unavailable"
            if unavailable
            else "Statistics data is invalid"
        )
        raise StatisticsDataError(error_code, message) from error
    except OSError as error:
        raise StatisticsDataError(code, "Statistics data could not be read") from error


def _load_registry(project_root: Path) -> _SourceRegistry:
    registry_path = project_root / "data/manifests/sources.yaml"
    raw = _read_bytes(
        registry_path,
        maximum_bytes=MAX_REGISTRY_BYTES,
        code="STATISTICS_DATA_INVALID",
        unavailable=True,
    )
    try:
        parsed: Any = yaml.safe_load(raw)
        registry = _SourceRegistry.model_validate(parsed)
    except (yaml.YAMLError, ValidationError, TypeError) as error:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Source registry is malformed"
        ) from error
    if registry.schema_version != "1.0":
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Source registry version is unsupported"
        )
    source_ids = [source.get("source_id") for source in registry.sources]
    if any(not isinstance(source_id, str) for source_id in source_ids):
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Source registry contains an invalid ID"
        )
    if len(source_ids) != len(set(source_ids)):
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Source registry contains duplicate IDs"
        )
    return registry


def _load_manifest(project_root: Path) -> _IngestionManifest:
    manifest_path = project_root / "data/manifests/ingestion-manifest.json"
    raw = _read_bytes(
        manifest_path,
        maximum_bytes=MAX_MANIFEST_BYTES,
        code="STATISTICS_DATA_INVALID",
        unavailable=True,
    )
    try:
        manifest = _IngestionManifest.model_validate_json(raw)
    except ValidationError as error:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Ingestion manifest is malformed"
        ) from error
    if manifest.schema_version != "1.0":
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Ingestion manifest version is unsupported"
        )
    return manifest


def _select_latest_attempt(
    manifest: _IngestionManifest, source: _ApprovedRegistrySource
) -> _IngestionAttempt:
    candidates: list[tuple[datetime, _IngestionAttempt]] = []
    for run in manifest.runs:
        if run.status != "completed" or run.finished_at is None or run.finished_at.tzinfo is None:
            continue
        for attempt in run.attempts:
            if (
                attempt.source_id == source.source_id
                and attempt.status == "parsed"
                and attempt.quality_status == "pass"
                and attempt.input_sha256 == source.sha256
                and attempt.canonical_path
                and attempt.canonical_sha256
                and attempt.parser_version
            ):
                candidates.append((run.finished_at, attempt))
    if not candidates:
        raise StatisticsDataError(
            "STATISTICS_DATA_UNAVAILABLE",
            "No successful ingestion record matches the approved source",
        )
    return max(candidates, key=lambda item: (item[0], item[1].canonical_path or ""))[1]


def _canonical_file(project_root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise StatisticsDataError("STATISTICS_DATA_INVALID", "Canonical data path is invalid")
    root = project_root.resolve()
    canonical_root = root / "data/canonical/structured"
    current = root
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise StatisticsDataError("STATISTICS_DATA_INVALID", "Canonical data path is invalid")
    try:
        resolved = (root / candidate).resolve(strict=True)
    except OSError as error:
        raise StatisticsDataError(
            "STATISTICS_DATA_UNAVAILABLE", "Approved canonical statistics data is unavailable"
        ) from error
    if not resolved.is_relative_to(canonical_root) or not resolved.is_file():
        raise StatisticsDataError("STATISTICS_DATA_INVALID", "Canonical data path is invalid")
    return resolved


def _validate_dataset(
    source: _ApprovedRegistrySource,
    dataset: CanonicalStructuredDataset,
    raw_sha256: str,
) -> None:
    if (
        dataset.source_id != source.source_id
        or dataset.indicator_id != source.indicator_id
        or dataset.content_sha256 != raw_sha256
        or dataset.provenance.sha256 != raw_sha256
        or dataset.provenance.source_id != source.source_id
        or dataset.provenance.indicator_id != source.indicator_id
        or dataset.provenance.licence != source.licence
        or dataset.provenance.sensitivity != source.sensitivity
        or dataset.provenance.title != source.title
        or dataset.provenance.publisher != source.publisher
        or dataset.provenance.canonical_url != source.canonical_url
        or dataset.provenance.usage_constraints != source.usage_constraints
        or set(dataset.country_codes) != set(source.countries)
        or set(dataset.provenance.countries) != set(source.countries)
        or dataset.year_range != source.year_range
        or dataset.provenance.year_range != source.year_range
    ):
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Canonical data do not match approved source metadata"
        )

    expected_observations = {
        (country, year)
        for country in source.countries
        for year in range(source.year_range[0], source.year_range[1] + 1)
    }
    actual_observations = {
        (observation.country_iso3, observation.year) for observation in dataset.observations
    }
    expected_ids = {
        f"{source.source_id}:{country}:{year}" for country, year in expected_observations
    }
    actual_ids = {observation.observation_id for observation in dataset.observations}
    if (
        len(dataset.observations) > 44
        or actual_observations != expected_observations
        or actual_ids != expected_ids
        or len(actual_ids) != len(dataset.observations)
    ):
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Canonical observations do not match approved dimensions"
        )


def _load_source(project_root: Path, indicator: str) -> _StatisticsSource:
    source_id = next(
        (
            approved_id
            for approved_id, approved_indicator in APPROVED_SOURCE_INDICATORS.items()
            if approved_indicator == indicator
        ),
        None,
    )
    if source_id is None:
        raise StatisticsDataError(
            "STATISTICS_INDICATOR_UNSUPPORTED", "Indicator is not approved for statistics"
        )

    registry = _load_registry(project_root)
    source_data = next(
        (item for item in registry.sources if item.get("source_id") == source_id),
        None,
    )
    if source_data is None:
        raise StatisticsDataError(
            "STATISTICS_SOURCE_NOT_ALLOWED", "Source is not approved for statistics"
        )
    allowed_usage = source_data.get("allowed_usage")
    if not isinstance(allowed_usage, list) or "statistics" not in allowed_usage:
        raise StatisticsDataError(
            "STATISTICS_SOURCE_NOT_ALLOWED", "Source is not approved for statistics"
        )
    if (
        source_data.get("source_kind") != "structured"
        or source_data.get("sensitivity") != "public"
        or source_data.get("license_review_status") != "verified"
        or source_data.get("indicator_id") != indicator
    ):
        raise StatisticsDataError(
            "STATISTICS_SOURCE_NOT_ALLOWED", "Source metadata does not meet statistics requirements"
        )
    try:
        source = _ApprovedRegistrySource.model_validate(source_data)
    except ValidationError as error:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Approved source registry entry is incomplete"
        ) from error
    if (
        len(source.countries) == 0
        or source.year_range[0] > source.year_range[1]
        or source.year_range[0] < 2015
        or source.year_range[1] > 2025
    ):
        raise StatisticsDataError(
            "STATISTICS_SOURCE_NOT_ALLOWED", "Source metadata does not meet statistics requirements"
        )
    if (
        "ilostat" not in source.attribution.casefold()
        or "world bank data" not in source.attribution.casefold()
        or "modeled" not in source.usage_constraints.casefold()
        or "national-estimate" not in source.usage_constraints.casefold()
    ):
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Approved source attribution or usage caveat is incomplete"
        )

    manifest = _load_manifest(project_root)
    attempt = _select_latest_attempt(manifest, source)
    canonical_path = _canonical_file(project_root, attempt.canonical_path or "")
    canonical_bytes = _read_bytes(
        canonical_path,
        maximum_bytes=MAX_CANONICAL_BYTES,
        code="STATISTICS_DATA_INVALID",
    )
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    if canonical_sha256 != attempt.canonical_sha256:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID",
            "Canonical data checksum does not match the ingestion manifest",
        )
    try:
        canonical_payload: Any = json.loads(canonical_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Canonical data are malformed"
        ) from error
    if isinstance(canonical_payload, dict):
        observations = canonical_payload.get("observations")
        if isinstance(observations, list):
            for observation in observations:
                if not isinstance(observation, dict):
                    continue
                value = observation.get("value")
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and not math.isfinite(float(value))
                ):
                    raise StatisticsDataError(
                        "STATISTICS_NON_FINITE_VALUE",
                        "Canonical observations contain a non-finite value",
                    )
    try:
        dataset = CanonicalStructuredDataset.model_validate(canonical_payload)
    except ValidationError as error:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Canonical data are malformed"
        ) from error
    _validate_dataset(source, dataset, source.sha256)

    units = {
        observation.unit.strip() for observation in dataset.observations if observation.unit.strip()
    }
    if len(units) > 1:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Canonical observations have mixed units"
        )
    unit = next(iter(units), "%")
    return _StatisticsSource(
        registry=source,
        dataset=dataset,
        raw_sha256=source.sha256,
        canonical_sha256=canonical_sha256,
        unit=unit,
    )


def _row_key(observation: CanonicalObservation) -> StatisticsRowKey:
    return StatisticsRowKey(
        observation_id=observation.observation_id,
        country_iso3=observation.country_iso3,
        year=observation.year,
    )


def _source_observation_row(observation: CanonicalObservation, unit: str) -> StatisticsResultRow:
    return StatisticsResultRow(
        geography=observation.country_iso3,
        country_name=observation.country_name,
        year=observation.year,
        value=observation.value,
        unit=unit,
        observation_status=observation.observation_status,
        decimal=observation.decimal,
    )


def _aggregate_value(
    values: list[CanonicalObservation], operation: str
) -> tuple[float | None, int]:
    numeric = [Decimal(str(item.value)) for item in values if item.value is not None]
    null_count = len(values) - len(numeric)
    if not numeric:
        return None, null_count
    ordered = sorted(numeric)
    try:
        if operation == "sum":
            value = sum(ordered, Decimal(0))
        elif operation == "mean":
            value = sum(ordered, Decimal(0)) / len(ordered)
        else:
            middle = len(ordered) // 2
            if len(ordered) % 2:
                value = ordered[middle]
            else:
                value = (ordered[middle - 1] + ordered[middle]) / 2
        rounded = value.quantize(ROUNDING_QUANTUM, rounding=ROUND_HALF_EVEN)
        output = float(rounded)
    except (InvalidOperation, OverflowError) as error:
        raise StatisticsDataError(
            "STATISTICS_NON_FINITE_VALUE", "Statistics calculation produced an invalid value"
        ) from error
    if not math.isfinite(output):
        raise StatisticsDataError(
            "STATISTICS_NON_FINITE_VALUE", "Statistics calculation produced a non-finite value"
        )
    return output, null_count


def _aggregate_rows(
    observations: list[CanonicalObservation], request: StatisticsQueryRequest, unit: str
) -> tuple[list[StatisticsResultRow], int]:
    group_fields = sorted(request.group_by)
    groups: dict[tuple[str | int, ...], list[CanonicalObservation]] = defaultdict(list)
    for observation in observations:
        key: tuple[str | int, ...] = tuple(
            observation.country_iso3 if field == "geography" else observation.year
            for field in group_fields
        )
        groups[key].append(observation)

    rows: list[StatisticsResultRow] = []
    total_nulls = 0
    for key in sorted(groups):
        group = groups[key]
        value, null_count = _aggregate_value(group, request.aggregation)
        total_nulls += null_count
        grouped_values = dict(zip(group_fields, key, strict=True))
        geography_value = grouped_values.get("geography")
        geography = geography_value if isinstance(geography_value, str) else None
        country_name = next(
            (item.country_name for item in group if item.country_iso3 == geography), None
        )
        year_value = grouped_values.get("year")
        year = year_value if isinstance(year_value, int) else None
        rows.append(
            StatisticsResultRow(
                geography=geography,
                country_name=country_name,
                year=year,
                value=value,
                unit=unit,
                observation_status="aggregated",
                decimal=6,
            )
        )
    return rows, total_nulls


def query_statistics(
    request: StatisticsQueryRequest,
    *,
    project_root: Path | None = None,
) -> StatisticsToolResult:
    root = (project_root or PROJECT_ROOT).resolve()
    source = _load_source(root, request.indicator)
    dataset = source.dataset

    if request.start_year < dataset.year_range[0] or request.end_year > dataset.year_range[1]:
        raise StatisticsDataError(
            "STATISTICS_RANGE_INVALID", "Requested years are outside the approved source range"
        )
    available_geographies = set(dataset.country_codes)
    if not set(request.geographies).issubset(available_geographies):
        raise StatisticsDataError(
            "STATISTICS_DATA_UNAVAILABLE",
            "No approved observations exist for a requested geography",
        )
    selected = sorted(
        (
            observation
            for observation in dataset.observations
            if observation.country_iso3 in request.geographies
            and request.start_year <= observation.year <= request.end_year
        ),
        key=lambda item: (item.country_iso3, item.year, item.observation_id),
    )
    if not selected:
        raise StatisticsDataError(
            "STATISTICS_DATA_UNAVAILABLE", "No approved observations match the requested filters"
        )

    if request.aggregation == "none":
        rows = [_source_observation_row(item, source.unit) for item in selected]
        null_count = 0
        formula = "Source observations returned without aggregation."
        rounding = "Source precision preserved; no rounding applied."
    else:
        rows, null_count = _aggregate_rows(selected, request, source.unit)
        if request.aggregation == "sum":
            formula = "Sum of non-null observations within each requested group."
            rows = [row.model_copy(update={"unit": "percentage points"}) for row in rows]
        elif request.aggregation == "mean":
            formula = "Arithmetic mean of non-null observations within each requested group."
        else:
            formula = (
                "Median of sorted non-null observations within each requested group; "
                "the middle pair is averaged when the group size is even."
            )
        rounding = "ROUND_HALF_EVEN to six decimal places; output decimal is 6."

    if len(rows) > request.row_limit or len(rows) > 44:
        raise StatisticsDataError(
            "STATISTICS_ROW_LIMIT_EXCEEDED", "Complete result exceeds the requested row limit"
        )

    normalized_request = request.model_copy(
        update={
            "geographies": sorted(request.geographies),
            "group_by": sorted(request.group_by),
        }
    )
    warnings: list[str] = []
    if null_count:
        warnings.append(
            f"{null_count} null observation(s) excluded from {request.aggregation} aggregation."
        )
    if request.aggregation == "sum":
        warnings.append("Summed unemployment rates are percentage-point totals, not rates.")
    if not any(item.unit.strip() for item in dataset.observations):
        warnings.append("Source unit metadata is empty; the indicator values are percentages.")

    registry = source.registry
    attribution = registry.attribution.strip()
    if "ILOSTAT" not in attribution or "World Bank Data" not in attribution:
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Required source attribution is unavailable"
        )
    usage_constraints = (registry.usage_constraints or "").strip()
    if (
        "modeled" not in usage_constraints.casefold()
        or "national-estimate" not in usage_constraints
    ):
        raise StatisticsDataError(
            "STATISTICS_DATA_INVALID", "Required modeled-estimate caveat is unavailable"
        )

    row_keys = [_row_key(item) for item in selected]
    result = StatisticsToolResult(
        schema_version="1.0",
        query=normalized_request,
        rows=rows,
        calculation=StatisticsCalculation(
            operation=request.aggregation,
            formula=formula,
            rounding=rounding,
        ),
        evidence=[
            StatisticsEvidence(
                source_id=registry.source_id,
                row_keys=row_keys,
                raw_sha256=source.raw_sha256,
                canonical_sha256=source.canonical_sha256,
            )
        ],
        attribution=[
            StatisticsAttribution(
                source_id=registry.source_id,
                publisher=registry.publisher,
                licence=registry.licence,
                attribution=attribution,
                usage_constraints=usage_constraints,
            )
        ],
        warnings=warnings,
    )
    return result
