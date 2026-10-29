from __future__ import annotations

import pytest

from policylens.ingestion.models import (
    SourceMetadata,
    StructuredDataset,
    StructuredObservation,
)
from scripts.eda.youth_employment import build_eda_results


def make_dataset(
    source_id: str,
    indicator_id: str,
    values: dict[tuple[str, int], float | None],
) -> StructuredDataset:
    country_codes = tuple(dict.fromkeys(country for country, _ in values))
    years = [year for _, year in values]
    source = SourceMetadata(
        source_id=source_id,
        title=indicator_id,
        publisher="World Bank Data; upstream ILOSTAT",
        canonical_url=f"https://data.worldbank.org/indicator/{indicator_id}",
        retrieved_at="2026-10-25T14:26:09Z",
        published_at=None,
        licence="CC BY 4.0",
        usage_constraints="Modeled ILO estimates.",
        sensitivity="synthetic",
        sha256="a" * 64,
        indicator_id=indicator_id,
        countries=country_codes,
        year_range=(min(years), max(years)),
    )
    observations = tuple(
        StructuredObservation(
            observation_id=f"{source_id}:{country}:{year}",
            country_iso2=country[:2],
            country_iso3=country,
            country_name=country,
            year=year,
            value=value,
            unit="",
            observation_status="",
            decimal=1,
        )
        for (country, year), value in values.items()
    )
    return StructuredDataset(
        dataset_id=f"doc:{source_id}:{source.sha256}",
        source_id=source_id,
        title=indicator_id,
        indicator_id=indicator_id,
        indicator_label=indicator_id,
        country_codes=country_codes,
        year_range=(min(years), max(years)),
        api_metadata={"pages": 1, "lastupdated": "2026-10-08"},
        observations=observations,
        missing_value_semantics="Null is missing; no imputation.",
        provenance=source,
        content_sha256=source.sha256,
        parser_version="1.0.0",
    )


def test_eda_aligns_indicators_and_preserves_nulls() -> None:
    youth = make_dataset(
        "youth",
        "SL.UEM.1524.ZS",
        {("SGP", 2024): 8.0, ("SGP", 2025): 7.0, ("IND", 2024): None, ("IND", 2025): 10.0},
    )
    total = make_dataset(
        "total",
        "SL.UEM.TOTL.ZS",
        {("SGP", 2024): 3.0, ("SGP", 2025): 2.5, ("IND", 2024): 4.0, ("IND", 2025): 4.5},
    )

    results = build_eda_results(youth, total)

    assert results["latest_year"] == 2025
    assert results["latest_comparison"] == [
        {
            "country_iso3": "SGP",
            "youth_rate": 7.0,
            "total_rate": 2.5,
            "difference_percentage_points": 4.5,
        },
        {
            "country_iso3": "IND",
            "youth_rate": 10.0,
            "total_rate": 4.5,
            "difference_percentage_points": 5.5,
        },
    ]
    change_by_country = {item["country_iso3"]: item for item in results["youth_change"]}
    assert change_by_country["SGP"]["change_percentage_points"] == -1.0
    assert change_by_country["IND"]["change_percentage_points"] is None


def test_eda_rejects_mismatched_country_sets() -> None:
    youth = make_dataset("youth", "SL.UEM.1524.ZS", {("SGP", 2025): 7.0})
    total = make_dataset("total", "SL.UEM.TOTL.ZS", {("IND", 2025): 4.5})

    with pytest.raises(ValueError, match="country sets"):
        build_eda_results(youth, total)
