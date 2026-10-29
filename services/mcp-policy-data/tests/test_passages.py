from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from policylens_mcp import server as mcp_server
from policylens_mcp.models import (
    PassageCatalog,
    PassageLocation,
    PassageRecord,
    PassageResourceError,
    PassageResourceResult,
)
from policylens_mcp.passages import PassageDataError, read_passage_resource

INDEX_VERSION = "a" * 64
PASSAGE_ID = "sha256:" + "b" * 64
TEXT = "A bounded passage with original source wording."


def passage_record() -> PassageRecord:
    return PassageRecord(
        passage_id=PASSAGE_ID,
        source_id="source-one",
        title="Source title",
        publisher="World Bank Group",
        source_uri="https://example.test/source",
        text=TEXT,
        text_sha256=hashlib.sha256(TEXT.encode("utf-8")).hexdigest(),
        source_content_sha256="c" * 64,
        locations=[
            PassageLocation(
                page_number=1,
                block_id="page-1-block-2",
                start_char=0,
                end_char=len(TEXT),
            ),
        ],
        row_key=None,
        section_path=["Findings"],
        licence="CC BY 4.0",
        usage_constraints="Attribution required.",
        sensitivity="public",
        permission_scope="public",
        allowed_usage=["retrieval"],
        untrusted=True,
    )


def write_catalog(
    project_root: Path,
    *,
    index_version: str = INDEX_VERSION,
    records: list[PassageRecord] | None = None,
) -> Path:
    index_directory = project_root / "data/indexes"
    index_directory.mkdir(parents=True)
    pointer = {
        "schema_version": "1.0",
        "index_version": index_version,
        "build_id": "test-build",
        "manifest_path": "data/indexes/test-manifest.json",
        "manifest_sha256": "d" * 64,
        "updated_at": "2026-10-26T00:00:00Z",
    }
    (index_directory / "active-index.json").write_text(json.dumps(pointer), encoding="utf-8")
    catalog = PassageCatalog(
        schema_version="1.0",
        index_version=INDEX_VERSION,
        generated_at=datetime(2026, 10, 26, tzinfo=UTC),
        passages=records or [passage_record()],
    )
    path = index_directory / "mcp-passage-catalog.json"
    path.write_text(catalog.model_dump_json(), encoding="utf-8")
    return path


def test_read_passage_returns_versioned_verbatim_provenance(tmp_path: Path) -> None:
    write_catalog(tmp_path)

    result = read_passage_resource(
        "source-one",
        PASSAGE_ID,
        project_root=tmp_path,
    )

    assert isinstance(result, PassageResourceResult)
    assert result.schema_version == "1.0"
    assert result.passage.passage_id == PASSAGE_ID
    assert result.passage.text == TEXT
    assert result.passage.source_content_sha256 == "c" * 64
    assert result.passage.untrusted is True


@pytest.mark.parametrize(
    ("source_id", "passage_id"),
    [
        ("missing-source", PASSAGE_ID),
        ("source-one", "../active-index.json"),
        ("../data", PASSAGE_ID),
    ],
)
def test_unknown_or_traversal_shaped_ids_do_not_resolve(
    tmp_path: Path,
    source_id: str,
    passage_id: str,
) -> None:
    write_catalog(tmp_path)

    with pytest.raises(PassageDataError) as error:
        read_passage_resource(source_id, passage_id, project_root=tmp_path)

    assert error.value.code == "MCP_RESOURCE_NOT_FOUND"


def test_stale_catalog_index_version_fails_closed(tmp_path: Path) -> None:
    write_catalog(tmp_path, index_version="e" * 64)

    with pytest.raises(PassageDataError) as error:
        read_passage_resource("source-one", PASSAGE_ID, project_root=tmp_path)

    assert error.value.code == "MCP_CATALOG_STALE"


def test_reader_rejects_symlinked_index_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    write_catalog(project_root)
    index_directory = project_root / "data/indexes"
    outside_directory = tmp_path / "outside-indexes"
    index_directory.rename(outside_directory)
    index_directory.symlink_to(outside_directory, target_is_directory=True)

    with pytest.raises(PassageDataError) as error:
        read_passage_resource("source-one", PASSAGE_ID, project_root=project_root)

    assert error.value.code == "MCP_SCHEMA_INVALID"


def test_catalog_text_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    path = write_catalog(tmp_path)
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    payload["passages"][0]["text"] = "Changed after indexing."
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PassageDataError) as error:
        read_passage_resource("source-one", PASSAGE_ID, project_root=tmp_path)

    assert error.value.code == "MCP_SCHEMA_INVALID"


def test_oversized_passage_fails_closed(tmp_path: Path) -> None:
    path = write_catalog(tmp_path)
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    oversized = "x" * 5001
    payload["passages"][0]["text"] = oversized
    payload["passages"][0]["text_sha256"] = hashlib.sha256(oversized.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PassageDataError) as error:
        read_passage_resource("source-one", PASSAGE_ID, project_root=tmp_path)

    assert error.value.code == "MCP_SCHEMA_INVALID"


def test_resource_handler_returns_stable_error_without_echoing_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_passage(_source_id: str, _passage_id: str) -> PassageResourceResult:
        raise PassageDataError("MCP_RESOURCE_NOT_FOUND", "Passage resource was not found")

    monkeypatch.setattr(mcp_server, "read_passage_resource", missing_passage)

    payload = json.loads(mcp_server.read_source_passage("../private", "../active-index.json"))
    error = PassageResourceError.model_validate(payload)

    assert error.error_code == "MCP_RESOURCE_NOT_FOUND"
    assert ".." not in error.message
