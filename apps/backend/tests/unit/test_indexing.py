from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from policylens.ingestion.models import (
    CanonicalBlock,
    CanonicalDocument,
    DocumentPage,
    SourceMetadata,
)
from policylens.retrieval.citations import RetrievalRunRegistry
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.indexing import (
    IndexBuildError,
    IndexInputError,
    build_index,
    load_current_sources,
    rollback_active_index,
    verify_active_index,
)
from policylens.retrieval.models import (
    ChunkerConfig,
    EmbeddingDescriptor,
)
from policylens.retrieval.search import RetrievalError, RetrievalService


def _write_json(path: Path, value: Any) -> str:
    payload = json.dumps(value, sort_keys=True).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_source_registry(root: Path, *, allowed_usage: list[str]) -> tuple[str, str]:
    raw_path = root / "data/raw/structured/source/source.json"
    raw_sha256 = hashlib.sha256(b"raw-source").hexdigest()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"raw-source")

    source = {
        "source_id": "source",
        "title": "Source title",
        "publisher": "Publisher",
        "canonical_url": "https://example.test/source",
        "source_kind": "structured",
        "format": "json",
        "sha256": raw_sha256,
        "local_path": "data/raw/structured/source/source.json",
        "allowed_usage": allowed_usage,
        "license_review_status": "verified",
        "licence": "CC BY 4.0",
        "usage_constraints": None,
        "sensitivity": "public",
        "acquisition_enabled": True,
    }
    registry = root / "data/manifests/sources.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(yaml.safe_dump({"schema_version": "1.0", "sources": [source]}))

    canonical_path = "data/canonical/structured/source/parser/source.json"
    canonical_hash = _write_json(root / canonical_path, {"source_id": "source"})
    run = {
        "status": "completed",
        "attempts": [
            {
                "source_id": "source",
                "status": "parsed",
                "input_sha256": raw_sha256,
                "canonical_path": canonical_path,
                "canonical_sha256": canonical_hash,
                "parser_version": "parser",
                "quality_status": "pass",
            }
        ],
    }
    _write_json(
        root / "data/manifests/ingestion-manifest.json", {"schema_version": "1.0", "runs": [run]}
    )
    return raw_sha256, canonical_hash


def test_current_source_loader_preserves_verified_retrieval_provenance(tmp_path: Path) -> None:
    raw_sha256, canonical_hash = _write_source_registry(tmp_path, allowed_usage=["retrieval"])

    sources = load_current_sources(tmp_path)

    assert len(sources) == 1
    assert sources[0].source_id == "source"
    assert sources[0].source_content_sha256 == raw_sha256
    assert sources[0].canonical_sha256 == canonical_hash


def test_current_source_loader_excludes_sources_without_retrieval_permission(
    tmp_path: Path,
) -> None:
    _write_source_registry(tmp_path, allowed_usage=["evaluation"])

    assert load_current_sources(tmp_path) == ()


def test_current_source_loader_rejects_changed_canonical_artifact(tmp_path: Path) -> None:
    _write_source_registry(tmp_path, allowed_usage=["retrieval"])
    canonical_path = tmp_path / "data/canonical/structured/source/parser/source.json"
    canonical_path.write_text("changed")

    with pytest.raises(IndexInputError, match="canonical checksum"):
        load_current_sources(tmp_path)


def _write_indexable_report(root: Path) -> None:
    raw_payload = b"approved raw report snapshot"
    raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
    raw_path = root / "data/raw/reports/report" / f"{raw_sha256}.pdf"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw_payload)

    source_metadata = SourceMetadata(
        source_id="report",
        title="Employment policy report",
        publisher="World Bank",
        canonical_url="https://example.test/report",
        retrieved_at="2026-10-25T00:00:00Z",
        published_at="2024-01-01T00:00:00Z",
        licence="CC BY 4.0",
        usage_constraints="Research use",
        sensitivity="public",
        sha256=raw_sha256,
    )
    text = "Youth employment policy evidence covers skills, wages, and barriers."
    block = CanonicalBlock(
        block_id="p0001-b0001",
        block_type="paragraph",
        text=text,
        section_path=("1 Findings",),
        bbox=None,
        start_char=0,
        end_char=len(text),
    )
    document = CanonicalDocument(
        document_id=f"doc:report:{raw_sha256}",
        source_id="report",
        title=source_metadata.title,
        language="en",
        pages=(DocumentPage(page_number=1, blocks=(block,)),),
        provenance=source_metadata,
        content_sha256=raw_sha256,
        parser_version="report-1",
    )
    canonical_path = "data/canonical/reports/report/report-1/report.json"
    canonical_hash = _write_json(root / canonical_path, document.model_dump(mode="json"))
    registry = {
        "schema_version": "1.0",
        "sources": [
            {
                "source_id": "report",
                "title": source_metadata.title,
                "publisher": source_metadata.publisher,
                "canonical_url": source_metadata.canonical_url,
                "source_kind": "unstructured",
                "format": "pdf",
                "sha256": raw_sha256,
                "local_path": "data/raw/reports/report/{sha256}.pdf",
                "allowed_usage": ["retrieval"],
                "license_review_status": "verified",
                "licence": "CC BY 4.0",
                "usage_constraints": "Research use",
                "sensitivity": "public",
                "acquisition_enabled": True,
                "retrieved_at": "2026-10-25T00:00:00Z",
                "publication_date": "2024-01-01",
            }
        ],
    }
    registry_path = root / "data/manifests/sources.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    _write_json(
        root / "data/manifests/ingestion-manifest.json",
        {
            "schema_version": "1.0",
            "runs": [
                {
                    "status": "completed",
                    "attempts": [
                        {
                            "source_id": "report",
                            "status": "parsed",
                            "input_sha256": raw_sha256,
                            "canonical_path": canonical_path,
                            "canonical_sha256": canonical_hash,
                            "parser_version": "report-1",
                            "quality_status": "pass",
                        }
                    ],
                }
            ],
        },
    )


class FakeIndexEmbedder:
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="fake-embedder",
        package_version="test",
        dimension=2,
        normalized=True,
        max_input_tokens=512,
    )
    cache_identity = {
        "provider": "local",
        "model_id": "fake-embedder",
        "package_version": "test",
        "model_revision": None,
        "model_sha256": None,
    }
    max_input_tokens = 512

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def embed_passages(self, passages: Any) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("injected embedding failure")
        return [[1.0, 0.0] for _ in passages]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


class MismatchedIndexEmbedder(FakeIndexEmbedder):
    descriptor = FakeIndexEmbedder.descriptor.model_copy(update={"model_id": "different-model"})


def _index_chunker(version: str) -> ChunkerConfig:
    return ChunkerConfig(
        strategy="structure-aware",
        version=version,
        target_tokens=100,
        min_tokens=10,
        max_tokens=100,
        overlap_tokens=5,
        tokenizer="fake-tokenizer",
    )


def test_index_build_is_persistent_and_rollback_restores_previous_pointer(tmp_path: Path) -> None:
    _write_indexable_report(tmp_path)
    settings = RetrievalSettings(
        chroma_persist_directory=Path("data/indexes/chroma"),
        bm25_index_directory=Path("data/indexes/bm25"),
        active_index_pointer_path=Path("data/indexes/active-index.json"),
        index_manifest_path=Path("data/manifests/retrieval-index-manifest.json"),
    )
    embedder = FakeIndexEmbedder()

    first = build_index(tmp_path, settings, embedder, _index_chunker("chunker-v1"))
    assert verify_active_index(tmp_path, settings) == first
    second = build_index(tmp_path, settings, embedder, _index_chunker("chunker-v1"))
    assert second.index_version == first.index_version
    assert second.build_id != first.build_id
    assert second.previous is not None
    assert second.previous.build_id == first.build_id
    assert verify_active_index(tmp_path, settings) == second

    third = build_index(tmp_path, settings, embedder, _index_chunker("chunker-v2"))
    assert third.previous is not None
    assert third.previous.build_id == second.build_id
    assert verify_active_index(tmp_path, settings) == third

    rolled_back = rollback_active_index(tmp_path, settings)

    assert rolled_back.build_id == second.build_id
    assert verify_active_index(tmp_path, settings) == rolled_back


def test_failed_index_build_does_not_replace_active_pointer(tmp_path: Path) -> None:
    _write_indexable_report(tmp_path)
    settings = RetrievalSettings()
    active = build_index(tmp_path, settings, FakeIndexEmbedder(), _index_chunker("chunker-v1"))

    with pytest.raises(IndexBuildError):
        build_index(tmp_path, settings, FakeIndexEmbedder(fail=True), _index_chunker("chunker-v2"))

    assert verify_active_index(tmp_path, settings) == active


def test_active_index_rejects_different_embedding_identity(tmp_path: Path) -> None:
    _write_indexable_report(tmp_path)
    settings = RetrievalSettings()
    build_index(tmp_path, settings, FakeIndexEmbedder(), _index_chunker("chunker-v1"))

    with pytest.raises(RetrievalError) as error:
        RetrievalService.from_active_index(
            tmp_path,
            settings,
            MismatchedIndexEmbedder(),
            RetrievalRunRegistry(),
        )

    assert error.value.code == "INDEX_EMBEDDING_MISMATCH"
