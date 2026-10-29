import hashlib
import json
from typing import Any

from policylens.ingestion.models import (
    SourceMetadata,
    StructuredDataset,
    StructuredObservation,
)

STRUCTURED_PARSER_VERSION = "1.1.0"


class StructuredParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def parse_world_bank_json(payload: bytes, source: SourceMetadata) -> StructuredDataset:
    content_sha256 = hashlib.sha256(payload).hexdigest()
    if content_sha256 != source.sha256:
        raise StructuredParseError(
            "CHECKSUM_MISMATCH", "Payload hash does not match source metadata"
        )

    try:
        response: Any = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StructuredParseError("INVALID_JSON", "Payload is not valid UTF-8 JSON") from error

    if not isinstance(response, list) or len(response) != 2:
        raise StructuredParseError(
            "INVALID_ENVELOPE", "World Bank response must be [metadata, records]"
        )
    metadata, raw_observations = response
    if not isinstance(metadata, dict) or not isinstance(raw_observations, list):
        raise StructuredParseError(
            "INVALID_ENVELOPE", "World Bank response metadata or records are invalid"
        )
    if metadata.get("page") != 1 or metadata.get("pages") != 1:
        raise StructuredParseError(
            "INVALID_PAGINATION", "Expected a single-page World Bank response"
        )
    if metadata.get("total") != len(raw_observations):
        raise StructuredParseError("INVALID_TOTAL", "World Bank total does not match record count")
    if source.indicator_id is None or source.year_range is None or not source.countries:
        raise StructuredParseError("INVALID_SOURCE", "Structured source lacks indicator dimensions")

    observations: list[StructuredObservation] = []
    seen_keys: set[tuple[str, int]] = set()
    indicator_label: str | None = None
    expected_countries = set(source.countries)
    first_year, last_year = source.year_range

    for raw_observation in raw_observations:
        if not isinstance(raw_observation, dict):
            raise StructuredParseError("INVALID_RECORD", "World Bank record must be an object")
        indicator = raw_observation.get("indicator")
        country = raw_observation.get("country")
        if not isinstance(indicator, dict) or not isinstance(country, dict):
            raise StructuredParseError(
                "INVALID_RECORD", "Indicator or country dimensions are missing"
            )
        if indicator.get("id") != source.indicator_id:
            raise StructuredParseError(
                "INDICATOR_MISMATCH", "Record indicator differs from source metadata"
            )
        label = indicator.get("value")
        if not isinstance(label, str):
            raise StructuredParseError("INVALID_RECORD", "Indicator label must be a string")
        if indicator_label is None:
            indicator_label = label
        elif label != indicator_label:
            raise StructuredParseError(
                "INDICATOR_MISMATCH", "Indicator label changed within the response"
            )

        country_iso3 = raw_observation.get("countryiso3code")
        country_name = country.get("value")
        country_iso2 = country.get("id")
        if (
            not isinstance(country_iso3, str)
            or country_iso3 not in expected_countries
            or not isinstance(country_name, str)
            or not isinstance(country_iso2, str)
        ):
            raise StructuredParseError("INVALID_COUNTRY", "Record country is missing or unexpected")
        raw_year = raw_observation.get("date")
        if not isinstance(raw_year, str) or not raw_year.isdigit():
            raise StructuredParseError("INVALID_YEAR", "Record year must be a numeric string")
        year = int(raw_year)
        if not first_year <= year <= last_year:
            raise StructuredParseError(
                "INVALID_YEAR", "Record year is outside source metadata range"
            )

        key = (country_iso3, year)
        if key in seen_keys:
            raise StructuredParseError(
                "DUPLICATE_OBSERVATION", "Duplicate country/year observation"
            )
        seen_keys.add(key)

        value = raw_observation.get("value")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise StructuredParseError("INVALID_VALUE", "Observation value must be numeric or null")
        unit = raw_observation.get("unit")
        observation_status = raw_observation.get("obs_status")
        decimal = raw_observation.get("decimal")
        if not isinstance(unit, str) or not isinstance(observation_status, str):
            raise StructuredParseError(
                "INVALID_RECORD", "Unit and observation status must be strings"
            )
        if isinstance(decimal, bool) or not isinstance(decimal, int):
            raise StructuredParseError("INVALID_RECORD", "Decimal precision must be an integer")

        observations.append(
            StructuredObservation(
                observation_id=f"{source.source_id}:{country_iso3}:{year}",
                country_iso2=country_iso2,
                country_iso3=country_iso3,
                country_name=country_name,
                year=year,
                value=float(value) if value is not None else None,
                unit=unit,
                observation_status=observation_status,
                decimal=decimal,
            )
        )

    expected_keys = {
        (country_code, year)
        for country_code in source.countries
        for year in range(first_year, last_year + 1)
    }
    if seen_keys != expected_keys:
        raise StructuredParseError(
            "COVERAGE_MISMATCH", "Records do not cover the expected country/year grid"
        )
    if not observations or indicator_label is None:
        raise StructuredParseError("EMPTY_DATASET", "World Bank response contains no observations")

    return StructuredDataset(
        dataset_id=f"doc:{source.source_id}:{content_sha256}",
        source_id=source.source_id,
        title=source.title,
        indicator_id=source.indicator_id,
        indicator_label=indicator_label,
        country_codes=source.countries,
        year_range=source.year_range,
        api_metadata=dict(metadata),
        observations=tuple(observations),
        missing_value_semantics=(
            "JSON null is preserved as an unknown/missing observation; no imputation is applied."
        ),
        provenance=source,
        content_sha256=content_sha256,
        parser_version=STRUCTURED_PARSER_VERSION,
    )
