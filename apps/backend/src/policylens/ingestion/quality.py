from typing import Literal

from pydantic import BaseModel, ConfigDict

from policylens.ingestion.models import CanonicalDocument, StructuredDataset


class QualityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Literal["info", "warning", "error"]
    message: str


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    source_id: str
    content_sha256: str
    source_kind: Literal["structured", "unstructured"]
    status: Literal["pass", "warning", "fail"]
    metrics: dict[str, int]
    findings: tuple[QualityFinding, ...]
    known_limitations: tuple[str, ...]


def _status_for(findings: list[QualityFinding]) -> Literal["pass", "warning", "fail"]:
    if any(finding.severity == "error" for finding in findings):
        return "fail"
    if any(finding.severity == "warning" for finding in findings):
        return "warning"
    return "pass"


def assess_structured_dataset(dataset: StructuredDataset) -> QualityReport:
    observations = dataset.observations
    keys = [(item.country_iso3, item.year) for item in observations]
    unique_keys = set(keys)
    expected_keys = {
        (country_code, year)
        for country_code in dataset.country_codes
        for year in range(dataset.year_range[0], dataset.year_range[1] + 1)
    }
    missing_keys = expected_keys - unique_keys
    unit_values = {item.unit for item in observations}
    findings: list[QualityFinding] = []

    null_value_count = sum(item.value is None for item in observations)
    duplicate_key_count = len(keys) - len(unique_keys)
    if null_value_count:
        findings.append(
            QualityFinding(
                code="NULL_VALUES_PRESERVED",
                severity="warning",
                message=(
                    f"{null_value_count} null indicator values are preserved; "
                    "no imputation or interpolation was applied."
                ),
            )
        )
    if duplicate_key_count:
        findings.append(
            QualityFinding(
                code="DUPLICATE_OBSERVATION_KEYS",
                severity="error",
                message=f"Found {duplicate_key_count} duplicate country/year keys.",
            )
        )
    if missing_keys:
        findings.append(
            QualityFinding(
                code="INCOMPLETE_COUNTRY_YEAR_COVERAGE",
                severity="error",
                message=f"{len(missing_keys)} expected country/year keys are missing.",
            )
        )
    if len(unit_values) > 1:
        findings.append(
            QualityFinding(
                code="INCONSISTENT_UNITS",
                severity="error",
                message="Observation unit values differ within one indicator dataset.",
            )
        )

    return QualityReport(
        source_id=dataset.source_id,
        content_sha256=dataset.content_sha256,
        source_kind="structured",
        status=_status_for(findings),
        metrics={
            "record_count": len(observations),
            "expected_record_count": len(expected_keys),
            "country_count": len(dataset.country_codes),
            "year_min": dataset.year_range[0],
            "year_max": dataset.year_range[1],
            "null_value_count": null_value_count,
            "duplicate_key_count": duplicate_key_count,
            "missing_key_count": len(missing_keys),
            "unit_value_count": len(unit_values),
        },
        findings=tuple(findings),
        known_limitations=(
            "World Bank-distributed modeled ILO estimates may be revised and are not "
            "national estimates.",
        ),
    )


def assess_report_document(document: CanonicalDocument) -> QualityReport:
    blocks = [block for page in document.pages for block in page.blocks]
    block_ids = [block.block_id for block in blocks]
    duplicate_block_count = len(block_ids) - len(set(block_ids))
    invalid_offset_count = sum(
        block.start_char < 0 or block.end_char <= block.start_char for block in blocks
    )
    empty_page_count = sum(not page.blocks for page in document.pages)
    text_character_count = sum(len(block.text) for block in blocks)
    findings = [
        QualityFinding(
            code="OCR_NOT_APPLIED",
            severity="warning",
            message="OCR was not run; scanned-only text may be absent.",
        )
    ]
    if duplicate_block_count:
        findings.append(
            QualityFinding(
                code="DUPLICATE_BLOCK_IDS",
                severity="error",
                message=f"Found {duplicate_block_count} duplicate block IDs.",
            )
        )
    if invalid_offset_count:
        findings.append(
            QualityFinding(
                code="INVALID_TEXT_OFFSETS",
                severity="error",
                message=f"Found {invalid_offset_count} blocks with invalid offsets.",
            )
        )
    if empty_page_count:
        findings.append(
            QualityFinding(
                code="EMPTY_PAGES",
                severity="warning",
                message=f"{empty_page_count} pages contain no extracted text blocks.",
            )
        )
    if (
        document.provenance.usage_constraints
        and "third-party" in document.provenance.usage_constraints.lower()
    ):
        findings.append(
            QualityFinding(
                code="THIRD_PARTY_RIGHTS_REVIEW",
                severity="info",
                message="Credited third-party content may have separate rights.",
            )
        )

    return QualityReport(
        source_id=document.source_id,
        content_sha256=document.content_sha256,
        source_kind="unstructured",
        status=_status_for(findings),
        metrics={
            "page_count": len(document.pages),
            "block_count": len(blocks),
            "text_character_count": text_character_count,
            "duplicate_block_count": duplicate_block_count,
            "invalid_offset_count": invalid_offset_count,
            "empty_page_count": empty_page_count,
        },
        findings=tuple(findings),
        known_limitations=(
            "Text extraction is validation/ingestion text only; OCR is not applied.",
            document.provenance.usage_constraints or "Source-specific usage constraints apply.",
        ),
    )
