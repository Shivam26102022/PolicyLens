import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from policylens_mcp import statistics
from policylens_mcp.models import (
    Aggregation,
    CanonicalObservation,
    GroupField,
    StatisticsIndicator,
    StatisticsQueryRequest,
    StatisticsToolError,
    StatisticsToolResult,
)
from policylens_mcp.server import query_statistics_tool
from policylens_mcp.statistics import StatisticsDataError, query_statistics

SOURCE_ID = "wb-youth-unemployment-1524-2015-2025"
TOTAL_SOURCE_ID = "wb-total-unemployment-2015-2025"
INDICATOR_ID: StatisticsIndicator = "SL.UEM.1524.ZS"
TOTAL_INDICATOR_ID: StatisticsIndicator = "SL.UEM.TOTL.ZS"
RAW_SHA256 = "a" * 64
USAGE_CONSTRAINTS = (
    "Modeled ILO estimates; values may be revised. Do not present as national-estimate data."
)


def request(
    *,
    aggregation: Aggregation = "none",
    row_limit: int = 44,
    group_by: list[GroupField] | None = None,
    indicator: StatisticsIndicator = INDICATOR_ID,
) -> StatisticsQueryRequest:
    return StatisticsQueryRequest(
        schema_version="1.0",
        indicator=indicator,
        geographies=["IND"],
        start_year=2020,
        end_year=2022,
        aggregation=aggregation,
        group_by=group_by or [],
        row_limit=row_limit,
    )


def make_project_root(
    tmp_path: Path,
    *,
    source_id: str = SOURCE_ID,
    indicator_id: StatisticsIndicator = INDICATOR_ID,
) -> tuple[Path, Path]:
    title = "Youth unemployment rate" if indicator_id == INDICATOR_ID else "Total unemployment rate"
    observations = [
        {
            "observation_id": f"{source_id}:IND:{year}",
            "country_iso2": "IN",
            "country_iso3": "IND",
            "country_name": "India",
            "year": year,
            "value": value,
            "unit": "",
            "observation_status": "",
            "decimal": 1,
        }
        for year, value in ((2022, 2.0), (2020, 1.0), (2021, None))
    ]
    source_metadata = {
        "source_id": source_id,
        "title": title,
        "publisher": "ILOSTAT, distributed via World Bank Data",
        "canonical_url": f"https://data.worldbank.org/indicator/{indicator_id}",
        "retrieved_at": "2026-10-25T15:31:44Z",
        "published_at": None,
        "licence": "CC BY 4.0",
        "usage_constraints": USAGE_CONSTRAINTS,
        "sensitivity": "public",
        "language": "en",
        "sha256": RAW_SHA256,
        "indicator_id": indicator_id,
        "countries": ["IND"],
        "year_range": [2020, 2022],
    }
    dataset = {
        "schema_version": "1.0",
        "dataset_id": f"doc:{source_id}:{RAW_SHA256}",
        "source_id": source_id,
        "title": title,
        "indicator_id": indicator_id,
        "indicator_label": title,
        "country_codes": ["IND"],
        "year_range": [2020, 2022],
        "api_metadata": {"page": 1, "pages": 1, "total": 3},
        "observations": observations,
        "missing_value_semantics": "Null is unknown; no imputation.",
        "provenance": source_metadata,
        "content_sha256": RAW_SHA256,
        "parser_version": "1.1.0",
    }
    canonical_path = Path("data/canonical/structured") / source_id / "1.1.0" / f"{RAW_SHA256}.json"
    canonical_bytes = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode()
    resolved_canonical_path = tmp_path / canonical_path
    resolved_canonical_path.parent.mkdir(parents=True)
    resolved_canonical_path.write_bytes(canonical_bytes)
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()

    source_entry = {
        **source_metadata,
        "source_kind": "structured",
        "format": "json",
        "acquisition_method": "api",
        "download_url": "https://api.worldbank.org/v2/example",
        "expected_media_type": "application/json",
        "license_review_status": "verified",
        "attribution": (
            "Attribute ILOSTAT and World Bank Data; include access date and indicate changes."
        ),
        "allowed_usage": ["retrieval", "evaluation", "statistics"],
        "refresh_policy": "manual",
        "local_path": f"data/raw/structured/{source_id}/{{sha256}}.json",
    }
    manifest = {
        "schema_version": "1.0",
        "runs": [
            {
                "run_id": "test-run",
                "started_at": "2026-10-26T00:00:00Z",
                "finished_at": "2026-10-26T00:01:00Z",
                "status": "completed",
                "attempts": [
                    {
                        "source_id": source_id,
                        "status": "parsed",
                        "input_sha256": RAW_SHA256,
                        "canonical_path": canonical_path.as_posix(),
                        "canonical_sha256": canonical_sha256,
                        "quality_status": "pass",
                        "parser_version": "1.1.0",
                    }
                ],
            }
        ],
    }
    manifests = tmp_path / "data/manifests"
    manifests.mkdir(parents=True)
    (manifests / "sources.yaml").write_text(
        yaml.safe_dump({"schema_version": "1.0", "sources": [source_entry]}),
        encoding="utf-8",
    )
    (manifests / "ingestion-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, resolved_canonical_path


def rewrite_canonical(
    project_root: Path,
    canonical_path: Path,
    update: Callable[[dict[str, Any]], None],
) -> None:
    dataset = json.loads(canonical_path.read_text(encoding="utf-8"))
    update(dataset)
    canonical_bytes = json.dumps(
        dataset,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
    ).encode()
    canonical_path.write_bytes(canonical_bytes)
    manifest_path = project_root / "data/manifests/ingestion-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runs"][-1]["attempts"][0]["canonical_sha256"] = hashlib.sha256(
        canonical_bytes
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_query_statistics_returns_deterministic_rows_and_provenance(tmp_path: Path) -> None:
    project_root, canonical_path = make_project_root(tmp_path)
    query = request()

    result = query_statistics(query, project_root=project_root)

    assert [row.year for row in result.rows] == [2020, 2021, 2022]
    assert [row.value for row in result.rows] == [1.0, None, 2.0]
    assert result.evidence[0].source_id == SOURCE_ID
    assert result.evidence[0].raw_sha256 == RAW_SHA256
    assert (
        result.evidence[0].canonical_sha256
        == hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    )
    assert [row.observation_id for row in result.evidence[0].row_keys] == [
        f"{SOURCE_ID}:IND:2020",
        f"{SOURCE_ID}:IND:2021",
        f"{SOURCE_ID}:IND:2022",
    ]
    assert result.attribution[0].licence == "CC BY 4.0"
    assert "ILOSTAT" in result.attribution[0].attribution
    assert "World Bank Data" in result.attribution[0].attribution
    assert "modeled" in result.attribution[0].usage_constraints.casefold()
    assert query_statistics(query, project_root=project_root) == result


def test_total_unemployment_series_is_approved(tmp_path: Path) -> None:
    project_root, _ = make_project_root(
        tmp_path,
        source_id=TOTAL_SOURCE_ID,
        indicator_id=TOTAL_INDICATOR_ID,
    )

    result = query_statistics(
        request(indicator=TOTAL_INDICATOR_ID),
        project_root=project_root,
    )

    assert result.evidence[0].source_id == TOTAL_SOURCE_ID


def test_registered_tool_returns_typed_success_and_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root, _ = make_project_root(tmp_path)
    monkeypatch.setattr(statistics, "PROJECT_ROOT", project_root)
    arguments: dict[str, Any] = {
        "schema_version": "1.0",
        "indicator": INDICATOR_ID,
        "geographies": ["IND"],
        "start_year": 2020,
        "end_year": 2022,
        "aggregation": "none",
        "group_by": [],
        "row_limit": 44,
    }

    result = query_statistics_tool(**arguments)
    error = query_statistics_tool(**{**arguments, "end_year": 2019})

    assert isinstance(result, StatisticsToolResult)
    assert isinstance(error, StatisticsToolError)
    assert error.error_code == "STATISTICS_INVALID_ARGUMENTS"


def test_mean_ignores_null_values_and_reports_their_count(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)
    query = request(aggregation="mean")

    result = query_statistics(query, project_root=project_root)

    assert len(result.rows) == 1
    assert result.rows[0].value == 1.5
    assert result.calculation.operation == "mean"
    assert any("1 null" in warning for warning in result.warnings)
    assert len(result.evidence[0].row_keys) == 3


def test_sum_returns_percentage_point_total_not_a_rate(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)

    result = query_statistics(
        request(aggregation="sum"),
        project_root=project_root,
    )

    assert result.rows[0].value == 3.0
    assert result.rows[0].unit == "percentage points"
    assert result.calculation.operation == "sum"
    assert any("not rates" in warning for warning in result.warnings)
    assert any("1 null" in warning for warning in result.warnings)


def test_median_averages_the_middle_pair_for_even_groups(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)

    result = query_statistics(
        request(aggregation="median"),
        project_root=project_root,
    )

    assert result.rows[0].value == 1.5
    assert result.calculation.operation == "median"


def test_grouped_mean_includes_only_requested_group_fields(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)

    result = query_statistics(
        request(aggregation="mean", group_by=["geography"]),
        project_root=project_root,
    )

    assert len(result.rows) == 1
    assert result.rows[0].geography == "IND"
    assert result.rows[0].country_name == "India"
    assert result.rows[0].year is None
    assert result.rows[0].value == 1.5


def test_group_field_order_does_not_change_aggregate_row_order() -> None:
    observations = [
        CanonicalObservation(
            observation_id=f"{country}:{year}",
            country_iso2=iso2,
            country_iso3=country,
            country_name=name,
            year=year,
            value=value,
            unit="%",
            observation_status="",
            decimal=1,
        )
        for country, iso2, name, year, value in (
            ("IND", "IN", "India", 2020, 1.0),
            ("MYS", "MY", "Malaysia", 2020, 2.0),
            ("IND", "IN", "India", 2021, 3.0),
            ("MYS", "MY", "Malaysia", 2021, 4.0),
        )
    ]
    geography_then_year = request(
        aggregation="mean",
        group_by=["geography", "year"],
    )
    year_then_geography = request(
        aggregation="mean",
        group_by=["year", "geography"],
    )

    first_rows, _ = statistics._aggregate_rows(observations, geography_then_year, "%")
    second_rows, _ = statistics._aggregate_rows(observations, year_then_geography, "%")

    assert first_rows == second_rows


def test_mean_uses_six_place_round_half_even(tmp_path: Path) -> None:
    project_root, canonical_path = make_project_root(tmp_path)

    def set_tie_values(dataset: dict[str, Any]) -> None:
        dataset["observations"][0]["value"] = 1.234566
        dataset["observations"][1]["value"] = 1.234567

    rewrite_canonical(project_root, canonical_path, set_tie_values)
    result = query_statistics(request(aggregation="mean"), project_root=project_root)

    assert result.rows[0].value == 1.234566
    assert result.rows[0].decimal == 6


def test_invalid_aggregation_range_and_grouping_are_rejected() -> None:
    valid = request().model_dump(mode="json")

    for invalid in (
        {**valid, "aggregation": "mode"},
        {**valid, "start_year": 2022, "end_year": 2020},
        {**valid, "group_by": ["year"]},
    ):
        with pytest.raises(ValidationError):
            StatisticsQueryRequest.model_validate(invalid)


def test_query_model_enforces_geography_and_year_bounds() -> None:
    valid = request().model_dump(mode="json")
    invalid_requests = (
        {**valid, "geographies": []},
        {**valid, "geographies": ["IND"] * 5},
        {**valid, "geographies": ["IND", "IND"]},
        {**valid, "geographies": ["in1"]},
        {**valid, "start_year": 2014},
        {**valid, "end_year": 2026},
        {**valid, "row_limit": 45},
    )

    for invalid in invalid_requests:
        with pytest.raises(ValidationError):
            StatisticsQueryRequest.model_validate(invalid)


def test_row_limit_fails_instead_of_truncating_provenance(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(row_limit=2), project_root=project_root)

    assert error.value.code == "STATISTICS_ROW_LIMIT_EXCEEDED"


def test_unapproved_indicator_is_rejected_by_request_model() -> None:
    with pytest.raises(ValidationError):
        StatisticsQueryRequest.model_validate(
            {
                **request().model_dump(mode="json"),
                "indicator": "SL.UEM.TOTL.ZS; DROP TABLE observations",
            }
        )


def test_source_without_statistics_permission_is_rejected(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)
    source_path = project_root / "data/manifests/sources.yaml"
    registry = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    registry["sources"][0]["allowed_usage"] = ["retrieval", "evaluation"]
    source_path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_SOURCE_NOT_ALLOWED"


def test_unrelated_registry_entry_with_null_fields_does_not_block_statistics(
    tmp_path: Path,
) -> None:
    project_root, _ = make_project_root(tmp_path)
    source_path = project_root / "data/manifests/sources.yaml"
    registry = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    registry["sources"].append(
        {
            "source_id": "disabled-manual-source",
            "sha256": None,
            "licence": None,
        }
    )
    source_path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    result = query_statistics(request(), project_root=project_root)

    assert result.evidence[0].source_id == SOURCE_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_kind", "unstructured"),
        ("sensitivity", "synthetic"),
        ("license_review_status", "pending"),
    ],
)
def test_source_must_be_structured_public_and_verified(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    project_root, _ = make_project_root(tmp_path)
    source_path = project_root / "data/manifests/sources.yaml"
    registry = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    registry["sources"][0][field] = value
    source_path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_SOURCE_NOT_ALLOWED"


def test_manifest_raw_hash_mismatch_is_unavailable(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)
    manifest_path = project_root / "data/manifests/ingestion-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runs"][0]["attempts"][0]["input_sha256"] = "b" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_DATA_UNAVAILABLE"


def test_manifest_canonical_path_cannot_escape_structured_data(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)
    manifest_path = project_root / "data/manifests/ingestion-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runs"][0]["attempts"][0]["canonical_path"] = (
        "data/canonical/structured/../../raw/unapproved.json"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_DATA_INVALID"


def test_canonical_directory_symlink_is_rejected(tmp_path: Path) -> None:
    project_root, _ = make_project_root(tmp_path)
    canonical_directory = project_root / "data/canonical/structured"
    outside_directory = tmp_path / "canonical-outside"
    canonical_directory.rename(outside_directory)
    canonical_directory.symlink_to(outside_directory, target_is_directory=True)

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_DATA_INVALID"


def test_canonical_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    project_root, canonical_path = make_project_root(tmp_path)
    canonical_path.write_bytes(canonical_path.read_bytes() + b" ")

    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_DATA_INVALID"


def test_non_finite_observation_returns_specific_error(tmp_path: Path) -> None:
    project_root, canonical_path = make_project_root(tmp_path)

    def set_infinite_value(dataset: dict[str, Any]) -> None:
        dataset["observations"][0]["value"] = float("inf")

    rewrite_canonical(project_root, canonical_path, set_infinite_value)
    with pytest.raises(StatisticsDataError) as error:
        query_statistics(request(), project_root=project_root)

    assert error.value.code == "STATISTICS_NON_FINITE_VALUE"
