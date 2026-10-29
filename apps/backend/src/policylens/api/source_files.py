from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

from policylens.settings import PROJECT_ROOT

router = APIRouter(prefix="/sources", tags=["sources"])
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_ALLOWED_SENSITIVITY = {"public", "synthetic", "anonymised"}


class _SourceNotFound(Exception):
    pass


class _SourceUnavailable(Exception):
    pass


def _read_registry(project_root: Path) -> list[Any]:
    registry_path = project_root / "data/manifests/sources.yaml"
    try:
        contents = registry_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise _SourceUnavailable from error

    try:
        registry = yaml.safe_load(contents)
    except yaml.YAMLError as error:
        raise _SourceUnavailable from error

    sources = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(sources, list):
        raise _SourceUnavailable
    return sources


def _raw_pdf_path(source_id: str, project_root: Path) -> Path:
    sources = _read_registry(project_root)
    matches = [
        source
        for source in sources
        if isinstance(source, dict) and source.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise _SourceNotFound

    source = matches[0]
    allowed_usage = source.get("allowed_usage")
    if (
        source.get("acquisition_enabled") is not True
        or source.get("license_review_status") != "verified"
        or source.get("source_kind") != "unstructured"
        or source.get("format") != "pdf"
        or source.get("sensitivity") not in _ALLOWED_SENSITIVITY
        or not isinstance(allowed_usage, list)
        or "retrieval" not in allowed_usage
    ):
        raise _SourceNotFound

    expected_hash = source.get("sha256")
    path_template = source.get("local_path")
    if (
        not isinstance(expected_hash, str)
        or not _SHA256_RE.fullmatch(expected_hash)
        or not isinstance(path_template, str)
    ):
        raise _SourceUnavailable
    try:
        relative_path = path_template.format(sha256=expected_hash)
    except (KeyError, ValueError) as error:
        raise _SourceUnavailable from error

    posix_path = PurePosixPath(relative_path)
    if (
        posix_path.is_absolute()
        or ".." in posix_path.parts
        or posix_path.parts[:3] != ("data", "raw", "reports")
        or posix_path.suffix.lower() != ".pdf"
    ):
        raise _SourceUnavailable

    root = project_root.resolve()
    reports_root = (root / "data/raw/reports").resolve()
    try:
        pdf_path = (root / Path(*posix_path.parts)).resolve(strict=True)
        pdf_path.relative_to(reports_root)
        if not pdf_path.is_file():
            raise _SourceUnavailable
        digest = hashlib.sha256()
        with pdf_path.open("rb") as pdf_file:
            for block in iter(lambda: pdf_file.read(1024 * 1024), b""):
                digest.update(block)
    except (OSError, RuntimeError, ValueError) as error:
        raise _SourceUnavailable from error
    if digest.hexdigest() != expected_hash:
        raise _SourceUnavailable
    return pdf_path


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": "1.0",
            "error_code": code,
            "message": message,
        },
    )


@router.get(
    "/{source_id}/pdf",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Hash-verified local PDF served inline.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
        404: {
            "description": "Source is missing or not approved for retrieval.",
            "content": {
                "application/json": {
                    "example": {
                        "schema_version": "1.0",
                        "error_code": "SOURCE_NOT_FOUND",
                        "message": "The requested PDF source is unavailable.",
                    }
                }
            },
        },
        503: {
            "description": "Local source file or registry is unavailable.",
            "content": {
                "application/json": {
                    "example": {
                        "schema_version": "1.0",
                        "error_code": "SOURCE_FILE_UNAVAILABLE",
                        "message": "The requested PDF source is unavailable.",
                    }
                }
            },
        },
    },
)
def source_pdf(source_id: str) -> Response:
    try:
        pdf_path = _raw_pdf_path(source_id, PROJECT_ROOT)
    except _SourceNotFound:
        return _error_response(
            "SOURCE_NOT_FOUND",
            "The requested PDF source is unavailable.",
            404,
        )
    except _SourceUnavailable:
        return _error_response(
            "SOURCE_FILE_UNAVAILABLE",
            "The requested PDF source is unavailable.",
            503,
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename="source.pdf",
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
