from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from policylens.mcp.models import PassageCatalog
from policylens.retrieval.models import BlockLocation, SourceArtifact
from policylens.retrieval.search import IndexedPassage
from scripts.export_mcp_passages import (
    PassageExportError,
    build_passage_catalog,
    write_passage_catalog,
)

INDEX_VERSION = "a" * 64
SOURCE_CONTENT_SHA256 = "b" * 64
CANONICAL_SHA256 = "c" * 64
PASSAGE_ID = "sha256:" + "d" * 64
SECOND_PASSAGE_ID = "sha256:" + "e" * 64


class FakeRetrievalService:
    def __init__(self, passages: tuple[IndexedPassage, ...]) -> None:
        self.index_version = INDEX_VERSION
        self.settings = SimpleNamespace(allowed_permission_scopes=("public",))
        self._passages = passages

    def iter_passages_for_mcp(self) -> tuple[IndexedPassage, ...]:
        return self._passages


def _source(
    *,
    source_id: str = "source-one",
    allowed_usage: tuple[str, ...] = ("retrieval",),
) -> SourceArtifact:
    return SourceArtifact(
        source_id=source_id,
        canonical_path=f"data/canonical/reports/{source_id}/1.0.0/source.json",
        canonical_sha256=CANONICAL_SHA256,
        source_content_sha256=SOURCE_CONTENT_SHA256,
        parser_version="1.0.0",
        source_type="report",
        title="Source title",
        publisher="World Bank Group",
        source_uri="https://example.test/source",
        retrieved_at=datetime(2026, 10, 25, tzinfo=UTC),
        published_at=None,
        licence="CC BY 4.0",
        usage_constraints="Attribution required.",
        sensitivity="public",
        allowed_usage=allowed_usage,
    )


def _passage(
    *,
    source_id: str = "source-one",
    passage_id: str = PASSAGE_ID,
    permission_scope: str = "public",
    source_content_sha256: str = SOURCE_CONTENT_SHA256,
) -> IndexedPassage:
    text = "A bounded policy passage with its original wording."
    return IndexedPassage(
        passage_id=passage_id,
        source_id=source_id,
        document_id="doc:source-one:content",
        title="Source title",
        publisher="World Bank Group",
        source_uri="https://example.test/source",
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_content_sha256=source_content_sha256,
        locations=(
            BlockLocation(
                page_number=2,
                block_id="page-2-block-4",
                start_char=10,
                end_char=10 + len(text),
            ),
        ),
        row_key=None,
        section_path=("Findings", "Employment"),
        licence="CC BY 4.0",
        permission_scope=permission_scope,
        allowed_usage=("retrieval",),
    )


def test_build_catalog_preserves_passage_identity_and_provenance() -> None:
    source = _source()
    service = FakeRetrievalService((_passage(),))

    catalog = build_passage_catalog(
        service,
        sources={source.source_id: source},
        generated_at=datetime(2026, 10, 26, tzinfo=UTC),
    )

    assert catalog.schema_version == "1.0"
    assert catalog.index_version == INDEX_VERSION
    assert len(catalog.passages) == 1
    record = catalog.passages[0]
    assert record.passage_id == PASSAGE_ID
    assert record.text == "A bounded policy passage with its original wording."
    assert record.source_content_sha256 == SOURCE_CONTENT_SHA256
    assert record.locations[0].page_number == 2
    assert record.section_path == ("Findings", "Employment")
    assert record.usage_constraints == "Attribution required."
    assert record.untrusted is True


def test_build_catalog_rejects_source_without_retrieval_permission() -> None:
    source = _source(allowed_usage=("evaluation",))
    service = FakeRetrievalService((_passage(),))

    with pytest.raises(PassageExportError) as error:
        build_passage_catalog(service, sources={source.source_id: source})

    assert error.value.code == "MCP_PERMISSION_DENIED"


def test_build_catalog_sorts_passages_by_exact_id() -> None:
    first_source = _source()
    second_source = _source(source_id="source-two")
    service = FakeRetrievalService(
        (
            _passage(source_id="source-two", passage_id=SECOND_PASSAGE_ID),
            _passage(),
        )
    )

    catalog = build_passage_catalog(
        service,
        sources={
            first_source.source_id: first_source,
            second_source.source_id: second_source,
        },
    )

    assert [passage.passage_id for passage in catalog.passages] == sorted(
        [PASSAGE_ID, SECOND_PASSAGE_ID]
    )


def test_build_catalog_rejects_stale_source_provenance() -> None:
    source = _source()
    service = FakeRetrievalService((_passage(source_content_sha256="e" * 64),))

    with pytest.raises(PassageExportError) as error:
        build_passage_catalog(service, sources={source.source_id: source})

    assert error.value.code == "MCP_SCHEMA_INVALID"


def test_catalog_write_uses_fixed_path_and_atomic_replace(tmp_path: Path) -> None:
    source = _source()
    service = FakeRetrievalService((_passage(),))
    catalog = build_passage_catalog(service, sources={source.source_id: source})

    output_path = write_passage_catalog(catalog, project_root=tmp_path)

    assert output_path == tmp_path / "data/indexes/mcp-passage-catalog.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert PassageCatalog.model_validate(payload).index_version == INDEX_VERSION
    assert list(output_path.parent.glob(".mcp-passage-catalog.*.tmp")) == []


def test_catalog_writer_rejects_indexes_directory_symlink(tmp_path: Path) -> None:
    source = _source()
    service = FakeRetrievalService((_passage(),))
    catalog = build_passage_catalog(service, sources={source.source_id: source})
    project_root = tmp_path / "project"
    data_directory = project_root / "data"
    data_directory.mkdir(parents=True)
    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    (data_directory / "indexes").symlink_to(outside_directory, target_is_directory=True)

    with pytest.raises(PassageExportError) as error:
        write_passage_catalog(catalog, project_root=project_root)

    assert error.value.code == "MCP_INTERNAL_ERROR"
    assert list(outside_directory.iterdir()) == []
