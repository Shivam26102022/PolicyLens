from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import pymupdf

from policylens.ingestion.models import (
    CanonicalDocument,
    SourceMetadata,
    StructuredDataset,
)
from policylens.ingestion.quality import (
    QualityReport,
    assess_report_document,
    assess_structured_dataset,
)
from policylens.ingestion.reports import REPORT_PARSER_VERSION, parse_pdf_report
from policylens.ingestion.structured import STRUCTURED_PARSER_VERSION, parse_world_bank_json
from scripts.download_data import (
    DownloadError,
    SourceDefinition,
    load_manifest,
    load_source_registry,
    sha256_file,
    write_manifest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INGESTION_MANIFEST = Path("data/manifests/ingestion-manifest.json")


class IngestionRunError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snapshot_retrieved_at(
    download_manifest: dict[str, Any], source_id: str, content_sha256: str
) -> str:
    for run in download_manifest["runs"]:
        if not isinstance(run, dict):
            continue
        for attempt in run.get("attempts", []):
            if (
                isinstance(attempt, dict)
                and attempt.get("source_id") == source_id
                and attempt.get("sha256") == content_sha256
                and attempt.get("status") == "downloaded"
                and isinstance(attempt.get("retrieved_at"), str)
            ):
                return attempt["retrieved_at"]
    raise IngestionRunError(
        "DOWNLOAD_PROVENANCE_MISSING",
        f"No original download attempt found for {source_id} and its current checksum",
    )


def _source_metadata(source: SourceDefinition, retrieved_at: str) -> SourceMetadata:
    if not source.sha256 or not source.licence:
        raise IngestionRunError(
            "SOURCE_METADATA_INCOMPLETE", "Enabled source lacks checksum or licence"
        )
    if source.sensitivity not in {"public", "synthetic", "anonymised"}:
        raise IngestionRunError("SOURCE_METADATA_INVALID", "Enabled source has invalid sensitivity")
    return SourceMetadata(
        source_id=source.source_id,
        title=source.title,
        publisher=source.publisher,
        canonical_url=source.canonical_url,
        retrieved_at=retrieved_at,
        published_at=source.publication_date,
        licence=source.licence,
        usage_constraints=source.usage_constraints,
        sensitivity=cast(Literal["public", "synthetic", "anonymised"], source.sensitivity),
        language="en",
        sha256=source.sha256,
        indicator_id=source.indicator_id,
        countries=source.countries,
        year_range=source.year_range,
    )


def _relative_path(project_root: Path, path: Path) -> str:
    return path.relative_to(project_root).as_posix()


def _write_content_addressed(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise IngestionRunError(
                "DERIVED_OUTPUT_CONFLICT",
                "A content-addressed derived output already exists with different bytes",
            )
    else:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".part", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as file_handle:
                file_handle.write(payload)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _parse_source(
    project_root: Path,
    source: SourceDefinition,
    download_manifest: dict[str, Any],
) -> dict[str, Any]:
    if not source.sha256:
        raise IngestionRunError(
            "SOURCE_CHECKSUM_MISSING", "Enabled source has no successful checksum"
        )
    raw_path = project_root / source.local_path.format(sha256=source.sha256)
    if not raw_path.is_file() or sha256_file(raw_path) != source.sha256:
        raise IngestionRunError("LOCAL_CHECKSUM_MISMATCH", "Raw snapshot is missing or has changed")

    raw_payload = raw_path.read_bytes()
    retrieved_at = _snapshot_retrieved_at(download_manifest, source.source_id, source.sha256)
    metadata = _source_metadata(source, retrieved_at)
    canonical: StructuredDataset | CanonicalDocument
    quality: QualityReport
    if source.source_kind == "structured":
        canonical = parse_world_bank_json(raw_payload, metadata)
        quality = assess_structured_dataset(canonical)
        output_kind = "structured"
    else:
        canonical = parse_pdf_report(raw_payload, metadata)
        quality = assess_report_document(canonical)
        output_kind = "reports"

    parser_version = canonical.parser_version
    canonical_path = (
        project_root
        / "data/canonical"
        / output_kind
        / source.source_id
        / parser_version
        / f"{source.sha256}.json"
    )
    quality_path = (
        project_root
        / "data/processed/quality"
        / source.source_id
        / parser_version
        / f"{source.sha256}.json"
    )
    canonical_hash = _write_content_addressed(canonical_path, _canonical_bytes(canonical))
    quality_hash = _write_content_addressed(quality_path, _canonical_bytes(quality))
    return {
        "source_id": source.source_id,
        "status": "parsed",
        "input_sha256": source.sha256,
        "input_path": _relative_path(project_root, raw_path),
        "canonical_path": _relative_path(project_root, canonical_path),
        "canonical_sha256": canonical_hash,
        "quality_path": _relative_path(project_root, quality_path),
        "quality_sha256": quality_hash,
        "quality_status": quality.status,
        "quality_findings": [finding.model_dump(mode="json") for finding in quality.findings],
        "parser_version": parser_version,
    }


def run_parse(project_root: Path = PROJECT_ROOT) -> int:
    registry_path = project_root / "data/manifests/sources.yaml"
    download_manifest_path = project_root / "data/manifests/download-manifest.json"
    ingestion_manifest_path = project_root / INGESTION_MANIFEST
    try:
        _, sources = load_source_registry(registry_path)
        download_manifest = load_manifest(download_manifest_path)
        ingestion_manifest = load_manifest(ingestion_manifest_path)
    except DownloadError as error:
        print(f"ERROR {error.code}: {error.safe_message}")
        return 2

    run_record: dict[str, Any] = {
        "run_id": str(uuid.uuid4()),
        "started_at": _timestamp(),
        "finished_at": None,
        "tool_versions": {
            "python": platform.python_version(),
            "pymupdf": pymupdf.VersionBind,
            "report_parser": REPORT_PARSER_VERSION,
            "structured_parser": STRUCTURED_PARSER_VERSION,
        },
        "status": "completed",
        "attempts": [],
    }
    failures = 0
    for source in sources:
        if not source.acquisition_enabled:
            run_record["attempts"].append(
                {"source_id": source.source_id, "status": "skipped", "reason": "disabled"}
            )
            continue
        try:
            attempt = _parse_source(project_root, source, download_manifest)
        except (DownloadError, IngestionRunError, OSError, ValueError) as error:
            failures += 1
            code = getattr(error, "code", "INGESTION_FAILED")
            attempt = {
                "source_id": source.source_id,
                "status": "failed",
                "error_code": code,
                "error_message": "Source parsing or quality validation failed.",
            }
        run_record["attempts"].append(attempt)
        print(f"{source.source_id}: {attempt['status']}")

    if failures:
        run_record["status"] = "failed"
    run_record["finished_at"] = _timestamp()
    ingestion_manifest["runs"].append(run_record)
    try:
        write_manifest(ingestion_manifest_path, ingestion_manifest)
    except (DownloadError, OSError) as error:
        error_code = getattr(error, "code", "INGESTION_MANIFEST_WRITE_FAILED")
        print(f"ERROR {error_code}: ingestion manifest could not be written")
        return 1
    return 1 if failures else 0


def main() -> int:
    return run_parse()


if __name__ == "__main__":
    raise SystemExit(main())
