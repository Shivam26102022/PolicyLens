from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from policylens.mcp.models import PassageCatalog, PassageRecord
from policylens.retrieval.citations import RetrievalRunRegistry
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import create_embedding_provider
from policylens.retrieval.indexing import IndexBuildError, IndexInputError, load_current_sources
from policylens.retrieval.models import SourceArtifact
from policylens.retrieval.search import IndexedPassage, RetrievalError, RetrievalService
from policylens.settings import PROJECT_ROOT

MAX_PASSAGE_CHARS = 5000
MAX_CATALOG_BYTES = 64_000_000
CATALOG_RELATIVE_PATH = Path("data/indexes/mcp-passage-catalog.json")


class PassageExportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PassageRetrievalService(Protocol):
    index_version: str

    def iter_passages_for_mcp(self) -> Iterable[IndexedPassage]: ...


def build_passage_catalog(
    service: PassageRetrievalService,
    *,
    sources: Mapping[str, SourceArtifact],
    generated_at: datetime | None = None,
) -> PassageCatalog:
    records: list[PassageRecord] = []
    for passage in service.iter_passages_for_mcp():
        source = sources.get(passage.source_id)
        if source is None or "retrieval" not in source.allowed_usage:
            raise PassageExportError(
                "MCP_PERMISSION_DENIED", "Passage source is not approved for retrieval"
            )
        if (
            passage.permission_scope != source.sensitivity
            or passage.source_content_sha256 != source.source_content_sha256
            or passage.title != source.title
            or passage.publisher != source.publisher
            or passage.source_uri != source.source_uri
            or passage.licence != source.licence
            or "retrieval" not in passage.allowed_usage
        ):
            raise PassageExportError(
                "MCP_SCHEMA_INVALID", "Active passage provenance does not match source metadata"
            )
        if len(passage.text) > MAX_PASSAGE_CHARS:
            raise PassageExportError(
                "MCP_SCHEMA_INVALID", "Active passage exceeds the resource text limit"
            )
        try:
            records.append(
                PassageRecord(
                    passage_id=passage.passage_id,
                    source_id=passage.source_id,
                    title=source.title,
                    publisher=source.publisher,
                    source_uri=source.source_uri,
                    text=passage.text,
                    text_sha256=passage.text_sha256,
                    source_content_sha256=passage.source_content_sha256,
                    locations=passage.locations,
                    row_key=passage.row_key,
                    section_path=passage.section_path,
                    licence=source.licence,
                    usage_constraints=source.usage_constraints,
                    sensitivity=source.sensitivity,
                    permission_scope=passage.permission_scope,
                    allowed_usage=source.allowed_usage,
                    untrusted=True,
                )
            )
        except ValidationError as error:
            raise PassageExportError(
                "MCP_SCHEMA_INVALID", "Active passage does not match the resource contract"
            ) from error

    records.sort(key=lambda record: record.passage_id)
    try:
        return PassageCatalog(
            schema_version="1.0",
            index_version=service.index_version,
            generated_at=generated_at or datetime.now(UTC),
            passages=tuple(records),
        )
    except ValidationError as error:
        raise PassageExportError(
            "MCP_SCHEMA_INVALID", "Active passage catalog does not match its contract"
        ) from error


def write_passage_catalog(
    catalog: PassageCatalog,
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    root = project_root.resolve()
    data_directory = root / "data"
    index_directory = data_directory / "indexes"
    if data_directory.is_symlink() or index_directory.is_symlink():
        raise PassageExportError("MCP_INTERNAL_ERROR", "Passage catalog output path is unsafe")
    if index_directory.resolve(strict=False) != index_directory:
        raise PassageExportError("MCP_INTERNAL_ERROR", "Passage catalog output path is unsafe")
    output_path = root / CATALOG_RELATIVE_PATH
    temporary_path = output_path.with_name(f".mcp-passage-catalog.{uuid4().hex}.tmp")
    payload = json.dumps(
        catalog.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(payload) > MAX_CATALOG_BYTES:
        raise PassageExportError("MCP_SCHEMA_INVALID", "Passage catalog exceeds its size limit")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
        directory_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as error:
        raise PassageExportError(
            "MCP_INTERNAL_ERROR", "Passage catalog could not be written"
        ) from error
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def export_active_passage_catalog(project_root: Path = PROJECT_ROOT) -> Path:
    root = project_root.resolve()
    settings = RetrievalSettings()
    run_registry = RetrievalRunRegistry(
        ttl_seconds=settings.retrieval_run_ttl_seconds,
        capacity=settings.retrieval_run_registry_capacity,
    )
    embedder = create_embedding_provider(settings)
    service = RetrievalService.from_active_index(root, settings, embedder, run_registry)
    sources = {source.source_id: source for source in load_current_sources(root)}
    catalog = build_passage_catalog(service, sources=sources)
    return write_passage_catalog(catalog, project_root=root)


def main() -> int:
    try:
        output_path = export_active_passage_catalog()
    except (IndexBuildError, IndexInputError, RetrievalError, PassageExportError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "MCP_CATALOG_INVALID",
                    "message": "Active passage catalog could not be exported safely",
                },
                separators=(",", ":"),
            )
        )
        return 1
    print(
        json.dumps(
            {"status": "ready", "catalog_path": str(output_path)},
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
