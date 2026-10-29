from __future__ import annotations

import re
from pathlib import Path

from pydantic import ValidationError

from policylens_mcp.models import (
    ActiveIndexPointer,
    PassageCatalog,
    PassageResourceErrorCode,
    PassageResourceResult,
)
from policylens_mcp.settings import PROJECT_ROOT

CATALOG_RELATIVE_PATH = "data/indexes/mcp-passage-catalog.json"
ACTIVE_INDEX_RELATIVE_PATH = "data/indexes/active-index.json"
MAX_CATALOG_BYTES = 64_000_000
MAX_POINTER_BYTES = 100_000
PASSAGE_ID_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


class PassageDataError(ValueError):
    def __init__(self, code: PassageResourceErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _read_index_file(project_root: Path, relative_path: str, maximum_bytes: int) -> bytes:
    root = project_root.resolve()
    index_root = root / "data/indexes"
    if (root / "data").is_symlink() or index_root.is_symlink():
        raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata path is invalid")
    if index_root.resolve(strict=False) != index_root:
        raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata path is invalid")
    candidate = root / relative_path
    current = root
    for part in Path(relative_path).parts:
        current /= part
        if current.is_symlink():
            raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata path is invalid")
    try:
        path = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise PassageDataError(
            "MCP_CATALOG_STALE", "Active passage catalog or index pointer is unavailable"
        ) from error
    except OSError as error:
        raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata could not be read") from error
    if not path.is_relative_to(index_root) or not path.is_file():
        raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata path is invalid")
    try:
        if path.stat().st_size > maximum_bytes:
            raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata exceeds its size limit")
        return path.read_bytes()
    except OSError as error:
        raise PassageDataError("MCP_SCHEMA_INVALID", "Index metadata could not be read") from error


def _load_active_index_version(project_root: Path) -> str:
    payload = _read_index_file(
        project_root,
        ACTIVE_INDEX_RELATIVE_PATH,
        MAX_POINTER_BYTES,
    )
    try:
        pointer = ActiveIndexPointer.model_validate_json(payload)
    except ValidationError as error:
        raise PassageDataError("MCP_SCHEMA_INVALID", "Active index pointer is malformed") from error
    return pointer.index_version


def _load_catalog(project_root: Path) -> PassageCatalog:
    payload = _read_index_file(project_root, CATALOG_RELATIVE_PATH, MAX_CATALOG_BYTES)
    try:
        return PassageCatalog.model_validate_json(payload)
    except ValidationError as error:
        raise PassageDataError("MCP_SCHEMA_INVALID", "Passage catalog is malformed") from error


def read_passage_resource(
    source_id: str,
    passage_id: str,
    *,
    project_root: Path | None = None,
) -> PassageResourceResult:
    if (
        not source_id
        or len(source_id) > 200
        or any(character in source_id for character in ("/", "\\", "\0"))
        or not PASSAGE_ID_PATTERN.fullmatch(passage_id)
    ):
        raise PassageDataError("MCP_RESOURCE_NOT_FOUND", "Passage resource was not found")

    root = (project_root or PROJECT_ROOT).resolve()
    catalog = _load_catalog(root)
    active_index_version = _load_active_index_version(root)
    if catalog.index_version != active_index_version:
        raise PassageDataError(
            "MCP_CATALOG_STALE", "Passage catalog does not match the active index"
        )

    passage = next(
        (
            record
            for record in catalog.passages
            if record.source_id == source_id and record.passage_id == passage_id
        ),
        None,
    )
    if passage is None:
        raise PassageDataError("MCP_RESOURCE_NOT_FOUND", "Passage resource was not found")
    if "retrieval" not in passage.allowed_usage:
        raise PassageDataError("MCP_PERMISSION_DENIED", "Passage is not approved for retrieval")
    return PassageResourceResult(schema_version="1.0", passage=passage)
