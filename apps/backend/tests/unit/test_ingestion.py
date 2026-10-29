from __future__ import annotations

import hashlib
import json

import pymupdf
import pytest

from policylens.ingestion.models import SourceMetadata
from policylens.ingestion.quality import assess_report_document, assess_structured_dataset
from policylens.ingestion.reports import (
    REPORT_PARSER_VERSION,
    PdfParseError,
    parse_pdf_report,
)
from policylens.ingestion.structured import StructuredParseError, parse_world_bank_json

COUNTRY_NAMES = {
    "SGP": "Singapore",
    "MYS": "Malaysia",
    "IDN": "Indonesia",
    "IND": "India",
}
COUNTRY_CODES = tuple(COUNTRY_NAMES)
INDICATOR_ID = "SL.UEM.1524.ZS"
YEAR_RANGE = (2015, 2025)


def make_api_payload(
    *,
    indicator_id: str = INDICATOR_ID,
    omit_last_record: bool = False,
    duplicate_last_record: bool = False,
) -> bytes:
    observations = [
        {
            "indicator": {"id": indicator_id, "value": "Youth unemployment (%)"},
            "country": {"id": country_code[:2], "value": country_name},
            "countryiso3code": country_code,
            "date": str(year),
            "value": (
                None
                if (country_code, year) == ("IND", 2015)
                else 5.0
                if (country_code, year) == ("SGP", 2025)
                else 7.4
            ),
            "unit": "",
            "obs_status": "",
            "decimal": 1,
        }
        for country_code, country_name in COUNTRY_NAMES.items()
        for year in range(YEAR_RANGE[0], YEAR_RANGE[1] + 1)
    ]
    if omit_last_record:
        observations.pop()
    if duplicate_last_record:
        observations[-1] = observations[0]
    response = [
        {
            "page": 1,
            "pages": 1,
            "per_page": 1000,
            "total": len(observations),
            "sourceid": "2",
            "lastupdated": "2026-10-08",
        },
        observations,
    ]
    return json.dumps(response, separators=(",", ":")).encode("utf-8")


def make_source(payload: bytes, *, indicator_id: str = INDICATOR_ID) -> SourceMetadata:
    return SourceMetadata(
        source_id="wb-youth-unemployment-1524-2015-2025",
        title="Youth unemployment, ages 15-24, percent of the youth labour force",
        publisher="International Labour Organization (ILOSTAT), distributed via World Bank Data",
        canonical_url="https://data.worldbank.org/indicator/SL.UEM.1524.ZS",
        retrieved_at="2026-10-25T14:26:09Z",
        published_at=None,
        licence="CC BY 4.0",
        usage_constraints="Modeled ILO estimates; values may be revised.",
        sensitivity="public",
        sha256=hashlib.sha256(payload).hexdigest(),
        indicator_id=indicator_id,
        countries=COUNTRY_CODES,
        year_range=YEAR_RANGE,
    )


def make_report_pdf() -> bytes:
    document = pymupdf.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "India skills and employment", fontsize=20)
    first_page.insert_text((72, 112), "1 Findings", fontsize=16, fontname="hebo")
    first_page.insert_textbox(
        pymupdf.Rect(72, 130, 520, 260),
        "The report assesses skills development and employment outcomes. " * 8,
        fontsize=10,
    )
    first_page.draw_rect(pymupdf.Rect(72, 290, 250, 340), width=0.5)
    first_page.draw_line((160, 290), (160, 340), width=0.5)
    first_page.draw_line((72, 315), (250, 315), width=0.5)
    first_page.insert_text((80, 307), "Year", fontsize=9)
    first_page.insert_text((168, 307), "Participants", fontsize=9)
    first_page.insert_text((80, 332), "2024", fontsize=9)
    first_page.insert_text((168, 332), "120", fontsize=9)

    second_page = document.new_page()
    second_page.insert_text((72, 72), "2 Methodology", fontsize=16, fontname="hebo")
    second_page.insert_textbox(
        pymupdf.Rect(72, 92, 520, 280),
        "The analysis uses surveys of trainees, employers, and providers. " * 8,
        fontsize=10,
    )
    payload = document.tobytes()
    document.close()
    return payload


def make_report_source(payload: bytes) -> SourceMetadata:
    return SourceMetadata(
        source_id="wb-india-skills-programs-2015",
        title="Labor Market Impacts and Effectiveness of Skills Development Programs in India",
        publisher="World Bank Group",
        canonical_url="https://documents.worldbank.org/en/publication/documents-reports/documentdetail/798601468034846280",
        retrieved_at="2026-10-25T14:14:24Z",
        published_at="2015-04-01",
        licence="CC BY 3.0 IGO",
        usage_constraints="Attribute the World Bank and indicate changes.",
        sensitivity="public",
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_structured_parser_preserves_rows_keys_nulls_units_and_provenance() -> None:
    payload = make_api_payload()
    dataset = parse_world_bank_json(payload, make_source(payload))

    assert dataset.dataset_id == f"doc:{dataset.source_id}:{hashlib.sha256(payload).hexdigest()}"
    assert dataset.source_id == "wb-youth-unemployment-1524-2015-2025"
    assert dataset.indicator_id == INDICATOR_ID
    assert dataset.indicator_label == "Youth unemployment (%)"
    assert dataset.country_codes == COUNTRY_CODES
    assert dataset.year_range == YEAR_RANGE
    assert len(dataset.observations) == 44
    assert dataset.api_metadata["lastupdated"] == "2026-10-08"
    assert dataset.provenance.publisher.startswith("International Labour Organization")
    assert dataset.provenance.licence == "CC BY 4.0"
    assert dataset.provenance.retrieved_at == "2026-10-25T14:26:09Z"
    assert dataset.content_sha256 == hashlib.sha256(payload).hexdigest()

    observations = {item.observation_id: item for item in dataset.observations}
    singapore_2025 = observations[f"{dataset.source_id}:SGP:2025"]
    india_2015 = observations[f"{dataset.source_id}:IND:2015"]

    assert singapore_2025.country_name == "Singapore"
    assert singapore_2025.country_iso2 == "SG"
    assert singapore_2025.year == 2025
    assert singapore_2025.value == 5.0
    assert singapore_2025.unit == ""
    assert singapore_2025.observation_status == ""
    assert singapore_2025.decimal == 1
    assert india_2015.value is None


def test_structured_parser_rejects_indicator_mismatch() -> None:
    payload = make_api_payload(indicator_id="SL.UEM.TOTL.ZS")

    with pytest.raises(StructuredParseError, match="INDICATOR_MISMATCH"):
        parse_world_bank_json(payload, make_source(payload))


def test_structured_parser_rejects_missing_country_year_coverage() -> None:
    payload = make_api_payload(omit_last_record=True)

    with pytest.raises(StructuredParseError, match="COVERAGE_MISMATCH"):
        parse_world_bank_json(payload, make_source(payload))


def test_structured_parser_rejects_duplicate_observation_keys() -> None:
    payload = make_api_payload(duplicate_last_record=True)

    with pytest.raises(StructuredParseError, match="DUPLICATE_OBSERVATION"):
        parse_world_bank_json(payload, make_source(payload))


def test_structured_parser_rejects_payload_checksum_mismatch() -> None:
    payload = make_api_payload()
    source = make_source(payload)
    changed_payload = payload.replace(b"7.4", b"7.5", 1)

    with pytest.raises(StructuredParseError, match="CHECKSUM_MISMATCH"):
        parse_world_bank_json(changed_payload, source)


def test_report_parser_preserves_pages_headings_offsets_and_provenance() -> None:
    payload = make_report_pdf()
    source = make_report_source(payload)

    document = parse_pdf_report(payload, source)

    assert document.document_id == f"doc:{source.source_id}:{source.sha256}"
    assert document.source_id == source.source_id
    assert document.title == source.title
    assert document.content_sha256 == source.sha256
    assert document.parser_version == REPORT_PARSER_VERSION
    assert document.provenance.licence == "CC BY 3.0 IGO"
    assert document.provenance.usage_constraints == source.usage_constraints
    assert [page.page_number for page in document.pages] == [1, 2]

    blocks = [block for page in document.pages for block in page.blocks]
    findings_heading = next(block for block in blocks if block.text == "1 Findings")
    methodology_heading = next(block for block in blocks if block.text == "2 Methodology")
    assert findings_heading.block_type == "heading"
    assert findings_heading.section_path == ("1 Findings",)
    assert methodology_heading.section_path == ("2 Methodology",)
    assert findings_heading.start_char < findings_heading.end_char
    assert methodology_heading.start_char > findings_heading.start_char
    assert findings_heading.bbox is not None
    assert any(block.block_type == "table" for block in blocks)


def test_report_parser_rejects_invalid_pdf_bytes() -> None:
    payload = b"not a PDF"

    with pytest.raises(PdfParseError, match="INVALID_PDF"):
        parse_pdf_report(payload, make_report_source(payload))


def test_structured_quality_reports_missingness_without_imputation() -> None:
    payload = make_api_payload()
    dataset = parse_world_bank_json(payload, make_source(payload))

    quality = assess_structured_dataset(dataset)

    assert quality.source_id == dataset.source_id
    assert quality.content_sha256 == dataset.content_sha256
    assert quality.status == "warning"
    assert quality.metrics["record_count"] == 44
    assert quality.metrics["null_value_count"] == 1
    assert quality.metrics["duplicate_key_count"] == 0
    assert "NULL_VALUES_PRESERVED" in {finding.code for finding in quality.findings}
    assert next(item for item in dataset.observations if item.value is None).value is None


def test_report_quality_reports_pages_blocks_and_no_ocr() -> None:
    payload = make_report_pdf()
    document = parse_pdf_report(payload, make_report_source(payload))

    quality = assess_report_document(document)

    assert quality.source_id == document.source_id
    assert quality.content_sha256 == document.content_sha256
    assert quality.status == "warning"
    assert quality.metrics["page_count"] == 2
    assert quality.metrics["block_count"] > 0
    assert quality.metrics["text_character_count"] > 200
    assert "OCR_NOT_APPLIED" in {finding.code for finding in quality.findings}
