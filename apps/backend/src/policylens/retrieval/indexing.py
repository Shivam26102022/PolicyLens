from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import bm25s
import chromadb
import yaml
from chromadb.config import Settings

from policylens.ingestion.models import CanonicalDocument, StructuredDataset
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.models import (
    ActiveIndexPointer,
    ActiveIndexReference,
    ChunkerConfig,
    CorpusPassage,
    EmbeddingDescriptor,
    IndexBuildManifest,
    IndexCounts,
    IndexInput,
    IndexOutputs,
    IndexValidation,
    SourceArtifact,
)

INDEX_SCHEMA_VERSION = "1.0"
BM25_TOKEN_PATTERN = r"(?u)\b\w+\b"


class IndexBuildError(RuntimeError):
    """Raised when an index build or active-index operation fails safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Embedder(Protocol):
    @property
    def descriptor(self) -> EmbeddingDescriptor: ...

    @property
    def max_input_tokens(self) -> int: ...

    def count_tokens(self, text: str) -> int: ...

    def embed_passages(self, passages: list[CorpusPassage]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write_json(path: Path, value: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(value)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _append_manifest_entry(path: Path, key: str, entry: dict[str, Any]) -> None:
    with _exclusive_lock(path.with_suffix(path.suffix + ".lock")):
        if path.is_file():
            manifest = _load_json(path, "retrieval index manifest")
        else:
            manifest = {"schema_version": INDEX_SCHEMA_VERSION, "builds": [], "failures": []}
        if manifest.get("schema_version") != INDEX_SCHEMA_VERSION:
            raise IndexBuildError(
                "INDEX_MANIFEST_VERSION", "Retrieval index manifest version is unsupported"
            )
        entries = manifest.setdefault(key, [])
        if not isinstance(entries, list):
            raise IndexBuildError(
                "INDEX_MANIFEST_INVALID", "Retrieval index manifest entries are invalid"
            )
        entries.append(entry)
        _atomic_write_json(path, manifest)


def _directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(file_path)))
    return digest.hexdigest()


def _chroma_logical_sha256(collection: Any) -> str:
    records = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = records.get("ids", [])
    documents = records.get("documents", [])
    metadatas = records.get("metadatas", [])
    embeddings = records.get("embeddings", [])
    if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
        raise IndexBuildError(
            "CHROMA_RECORD_SHAPE_INVALID", "Chroma returned incomplete logical records"
        )
    logical_records = [
        {
            "id": passage_id,
            "document": document,
            "metadata": metadata,
            "embedding": [float(value) for value in embedding],
        }
        for passage_id, document, metadata, embedding in sorted(
            zip(ids, documents, metadatas, embeddings, strict=True),
            key=lambda item: item[0],
        )
    ]
    return _fingerprint(
        {
            "collection_metadata": collection.metadata or {},
            "records": logical_records,
        }
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def runtime_chroma_path(source_path: Path, manifest: IndexBuildManifest) -> Path:
    """Use a writable copy of Chroma on Vercel's read-only function filesystem."""
    if not os.environ.get("VERCEL"):
        return source_path

    destination = (
        Path(tempfile.gettempdir())
        / "policylens-chroma"
        / manifest.index_version
        / str(manifest.build_id)
    )
    if destination.is_dir():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{manifest.build_id}.{uuid4().hex}.tmp")
    try:
        shutil.copytree(source_path, staging)
        try:
            staging.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return destination


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


class IndexInputError(ValueError):
    """Raised when a canonical source is missing, stale, or not eligible."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IndexInputError("INVALID_MANIFEST", f"Could not read {label}") from error
    if not isinstance(value, dict):
        raise IndexInputError("INVALID_MANIFEST", f"{label} must contain a JSON object")
    return value


def _path_under_root(root: Path, relative_path: str, label: str) -> Path:
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise IndexInputError("UNSAFE_PATH", f"{label} must stay within the project root")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _current_parse_attempt(
    runs: list[Any], source_id: str, raw_sha256: str
) -> dict[str, Any] | None:
    for run in reversed(runs):
        if not isinstance(run, dict):
            continue
        attempts = run.get("attempts", [])
        if not isinstance(attempts, list):
            continue
        for attempt in reversed(attempts):
            if (
                isinstance(attempt, dict)
                and attempt.get("source_id") == source_id
                and attempt.get("status") == "parsed"
                and attempt.get("input_sha256") == raw_sha256
            ):
                return attempt
    return None


def load_current_sources(project_root: Path) -> tuple[SourceArtifact, ...]:
    root = project_root.resolve()
    registry_path = _path_under_root(root, "data/manifests/sources.yaml", "source registry")
    manifest_path = _path_under_root(
        root, "data/manifests/ingestion-manifest.json", "ingestion manifest"
    )
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise IndexInputError("INVALID_REGISTRY", "Could not read source registry") from error
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
        raise IndexInputError("INVALID_REGISTRY", "Source registry has an invalid shape")
    manifest = _load_json(manifest_path, "ingestion manifest")
    runs = manifest.get("runs")
    if not isinstance(runs, list):
        raise IndexInputError("INVALID_MANIFEST", "Ingestion manifest has no runs list")

    artifacts: list[SourceArtifact] = []
    for source in registry["sources"]:
        if not isinstance(source, dict) or not source.get("acquisition_enabled", False):
            continue
        allowed_usage = source.get("allowed_usage", [])
        if not isinstance(allowed_usage, list) or "retrieval" not in allowed_usage:
            continue
        if source.get("license_review_status") != "verified":
            continue
        source_id = source.get("source_id")
        raw_sha256 = source.get("sha256")
        if not isinstance(source_id, str) or not isinstance(raw_sha256, str):
            raise IndexInputError(
                "SOURCE_METADATA_INVALID", "Enabled source lacks identity or hash"
            )
        if len(raw_sha256) != 64 or any(char not in "0123456789abcdef" for char in raw_sha256):
            raise IndexInputError("SOURCE_METADATA_INVALID", "Enabled source hash is invalid")

        local_path_template = source.get("local_path")
        if not isinstance(local_path_template, str):
            raise IndexInputError("SOURCE_METADATA_INVALID", "Enabled source lacks a raw path")
        try:
            raw_relative_path = local_path_template.format(sha256=raw_sha256)
        except (KeyError, ValueError) as error:
            raise IndexInputError(
                "SOURCE_METADATA_INVALID", "Enabled source path is invalid"
            ) from error
        raw_path = _path_under_root(root, raw_relative_path, "raw source path")
        if not raw_path.is_file() or _sha256(raw_path) != raw_sha256:
            raise IndexInputError("RAW_CHECKSUM_MISMATCH", f"Raw checksum mismatch for {source_id}")

        attempt = _current_parse_attempt(runs, source_id, raw_sha256)
        if attempt is None:
            raise IndexInputError(
                "CANONICAL_SOURCE_MISSING", f"No current canonical parse for {source_id}"
            )
        if attempt.get("quality_status") == "fail":
            raise IndexInputError(
                "CANONICAL_QUALITY_FAILED", f"Canonical quality failed for {source_id}"
            )
        canonical_relative_path = attempt.get("canonical_path")
        canonical_sha256 = attempt.get("canonical_sha256")
        parser_version = attempt.get("parser_version")
        if (
            not isinstance(canonical_relative_path, str)
            or not canonical_relative_path
            or not isinstance(canonical_sha256, str)
            or not canonical_sha256
            or not isinstance(parser_version, str)
            or not parser_version
        ):
            raise IndexInputError(
                "CANONICAL_METADATA_INVALID", f"Canonical metadata is incomplete for {source_id}"
            )
        canonical_path = _path_under_root(root, canonical_relative_path, "canonical path")
        if not canonical_path.is_relative_to(root / "data/canonical"):
            raise IndexInputError("UNSAFE_PATH", "Canonical path must stay below data/canonical")
        if not canonical_path.is_file() or _sha256(canonical_path) != canonical_sha256:
            raise IndexInputError(
                "CANONICAL_CHECKSUM_MISMATCH", f"canonical checksum mismatch for {source_id}"
            )

        source_kind = source.get("source_kind")
        if source_kind not in {"structured", "unstructured"}:
            raise IndexInputError(
                "SOURCE_METADATA_INVALID", f"Unsupported source kind for {source_id}"
            )
        year_range = source.get("year_range")
        artifacts.append(
            SourceArtifact(
                source_id=source_id,
                canonical_path=canonical_relative_path,
                canonical_sha256=canonical_sha256,
                source_content_sha256=raw_sha256,
                parser_version=parser_version,
                source_type="structured" if source_kind == "structured" else "report",
                title=source.get("title", ""),
                publisher=source.get("publisher", ""),
                source_uri=source.get("canonical_url"),
                retrieved_at=source.get("retrieved_at"),
                published_at=source.get("publication_date"),
                licence=source.get("licence", ""),
                usage_constraints=source.get("usage_constraints"),
                sensitivity=source.get("sensitivity", "public"),
                allowed_usage=tuple(allowed_usage),
                indicator_id=source.get("indicator_id"),
                countries=tuple(source.get("countries", [])),
                year_range=tuple(year_range) if isinstance(year_range, list) else None,
            )
        )
    return tuple(artifacts)


def _load_passages(
    root: Path,
    sources: tuple[SourceArtifact, ...],
    chunker: ChunkerConfig,
    embedder: _Embedder,
) -> tuple[list[CorpusPassage], list[IndexInput]]:
    from policylens.retrieval.chunking import chunk_report, chunk_structured_dataset

    passages: list[CorpusPassage] = []
    inputs: list[IndexInput] = []
    for source in sources:
        canonical_path = _path_under_root(root, source.canonical_path, "canonical path")
        try:
            payload = json.loads(canonical_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise IndexBuildError(
                "CANONICAL_READ_FAILED", f"Could not read canonical source {source.source_id}"
            ) from error
        try:
            if source.source_type == "structured":
                canonical_dataset = StructuredDataset.model_validate(payload)
                source_passages = chunk_structured_dataset(
                    source, canonical_dataset, chunker, embedder
                )
            else:
                canonical_document = CanonicalDocument.model_validate(payload)
                source_passages = chunk_report(source, canonical_document, chunker, embedder)
        except Exception as error:
            code = getattr(error, "code", "CANONICAL_INVALID")
            raise IndexBuildError(
                code, f"Could not prepare canonical source {source.source_id}"
            ) from error
        if not source_passages:
            raise IndexBuildError(
                "CANONICAL_EMPTY", f"Canonical source {source.source_id} produced no passages"
            )
        passages.extend(source_passages)
        inputs.append(
            IndexInput(
                source_id=source.source_id,
                raw_sha256=source.source_content_sha256,
                canonical_path=source.canonical_path,
                canonical_sha256=source.canonical_sha256,
                parser_version=source.parser_version,
            )
        )
    if not passages:
        raise IndexBuildError(
            "NO_ELIGIBLE_SOURCES", "No canonical sources are eligible for retrieval"
        )
    passage_ids = [passage.passage_id for passage in passages]
    if len(passage_ids) != len(set(passage_ids)):
        raise IndexBuildError("DUPLICATE_PASSAGE_ID", "Chunker produced duplicate passage IDs")
    return passages, inputs


def _passage_metadata(passage: CorpusPassage) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source_id": passage.source_id,
        "document_id": passage.document_id,
        "title": passage.title,
        "publisher": passage.publisher,
        "source_type": "structured" if passage.row_key is not None else "pdf",
        "section_path": " > ".join(passage.section_path),
        "section_path_json": json.dumps(passage.section_path, ensure_ascii=False),
        "locations_json": json.dumps(
            [location.model_dump(mode="json") for location in passage.locations],
            ensure_ascii=False,
            sort_keys=True,
        ),
        "row_key_json": json.dumps(
            passage.row_key.model_dump(mode="json") if passage.row_key is not None else None,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "licence": passage.licence,
        "sensitivity": passage.sensitivity,
        "permission_scope": passage.permission_scope,
        "allowed_usage": list(passage.allowed_usage),
        "content_sha256": passage.source_content_sha256,
        "text_sha256": passage.text_sha256,
        "embedding_text_sha256": passage.embedding_text_sha256,
        "chunker_version": passage.chunker_version,
    }
    if passage.source_uri:
        metadata["source_uri"] = passage.source_uri
    if passage.locations:
        metadata["page_start"] = min(location.page_number for location in passage.locations)
        metadata["page_end"] = max(location.page_number for location in passage.locations)
        metadata["block_ids"] = sorted({location.block_id for location in passage.locations})
    if passage.row_key is not None:
        metadata.update(
            {
                "dataset_id": passage.row_key.dataset_id,
                "observation_id": passage.row_key.observation_id,
                "indicator_id": passage.row_key.indicator_id,
                "country_iso3": passage.row_key.country_iso3,
                "year": passage.row_key.year,
            }
        )
    for key, value in (
        ("country_iso3", passage.country_iso3),
        ("year", passage.year),
        ("indicator_id", passage.indicator_id),
    ):
        if value is not None:
            metadata[key] = value
    return metadata


def _permission_where(allowed_scopes: tuple[str, ...]) -> dict[str, Any]:
    if not allowed_scopes:
        raise IndexBuildError(
            "PERMISSION_SCOPES_EMPTY", "No trusted permission scopes are configured"
        )
    return {
        "$and": [
            {"allowed_usage": {"$contains": "retrieval"}},
            {"permission_scope": {"$in": list(allowed_scopes)}},
        ]
    }


def _collection_name(index_version: str) -> str:
    return f"policylens_{index_version[:24]}"


def _tokenize_bm25(texts: str | list[str]) -> Any:
    return bm25s.tokenize(
        texts,
        lower=True,
        stopwords=[],
        token_pattern=BM25_TOKEN_PATTERN,
        return_ids=True,
        show_progress=False,
    )


def _validate_vectors(vectors: list[list[float]], expected_count: int, dimension: int) -> None:
    import math

    if len(vectors) != expected_count:
        raise IndexBuildError(
            "EMBEDDING_COUNT_MISMATCH", "Embedder returned an unexpected number of vectors"
        )
    for vector in vectors:
        if len(vector) != dimension or any(not math.isfinite(value) for value in vector):
            raise IndexBuildError(
                "EMBEDDING_INVALID", "Embedder returned an invalid dimension or non-finite value"
            )
        norm = math.sqrt(sum(value * value for value in vector))
        if abs(norm - 1.0) > 1e-5:
            raise IndexBuildError(
                "EMBEDDING_NOT_NORMALIZED", "Embedder returned a non-normalized vector"
            )


def _build_chroma(
    path: Path,
    index_version: str,
    descriptor: EmbeddingDescriptor,
    passages: list[CorpusPassage],
    vectors: list[list[float]],
    scopes: tuple[str, ...],
) -> tuple[int, str]:
    client = chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.create_collection(
        name=_collection_name(index_version),
        metadata={
            "hnsw:space": "cosine",
            "index_version": index_version,
            "embedding_provider": descriptor.provider,
            "embedding_model": descriptor.model_id,
            "embedding_dimension": descriptor.dimension,
            "schema_version": INDEX_SCHEMA_VERSION,
        },
        embedding_function=None,
    )
    collection.add(
        ids=[passage.passage_id for passage in passages],
        embeddings=cast(Any, vectors),
        documents=[passage.text for passage in passages],
        metadatas=[_passage_metadata(passage) for passage in passages],
    )
    count = collection.count()
    if count != len(passages):
        raise IndexBuildError(
            "CHROMA_COUNT_MISMATCH", "Chroma record count differs from passage count"
        )
    result = collection.query(
        query_embeddings=cast(Any, [vectors[0]]),
        n_results=min(3, len(passages)),
        where=_permission_where(scopes),
        include=["documents", "metadatas", "distances"],
    )
    result_ids = result.get("ids")
    result_documents = result.get("documents")
    if not result_ids or not result_ids[0]:
        raise IndexBuildError(
            "CHROMA_SMOKE_FAILED", "Chroma permission-filter smoke query returned no results"
        )
    if result_documents is None or not result_documents[0]:
        raise IndexBuildError("CHROMA_ROUND_TRIP_FAILED", "Chroma returned no round-trip documents")
    if any(item is None for item in result_documents[0]):
        raise IndexBuildError(
            "CHROMA_ROUND_TRIP_FAILED", "Chroma returned a missing passage document"
        )
    return count, _chroma_logical_sha256(collection)


def _build_bm25(
    path: Path,
    passages: list[CorpusPassage],
    k1: float,
    b: float,
) -> int:
    passage_ids = [passage.passage_id for passage in passages]
    retriever = bm25s.BM25(corpus=passage_ids, k1=k1, b=b, method="lucene")
    retriever.index(_tokenize_bm25([passage.text for passage in passages]), show_progress=False)
    retriever.save(path, corpus=passage_ids, show_progress=False)
    loaded = bm25s.BM25.load(path, load_corpus=True, show_progress=False)
    query = _tokenize_bm25("employment skills policy")
    results = loaded.retrieve(
        query,
        corpus=passage_ids,
        k=min(3, len(passages)),
        show_progress=False,
    )
    if not len(results.documents[0]):
        raise IndexBuildError("BM25_SMOKE_FAILED", "BM25S smoke query returned no results")
    if any(passage_id not in set(passage_ids) for passage_id in results.documents[0]):
        raise IndexBuildError("BM25_ROUND_TRIP_FAILED", "BM25S returned an unknown passage ID")
    return len(passage_ids)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _read_pointer(path: Path) -> ActiveIndexPointer | None:
    if not path.is_file():
        return None
    value = _load_json(path, "active index pointer")
    try:
        return ActiveIndexPointer.model_validate(value)
    except Exception as error:
        raise IndexBuildError(
            "ACTIVE_POINTER_INVALID", "Active index pointer is invalid"
        ) from error


def _pointer_path(root: Path, settings: RetrievalSettings) -> Path:
    return _path_under_root(
        root, settings.active_index_pointer_path.as_posix(), "active index pointer"
    )


def _index_manifest_path(root: Path, settings: RetrievalSettings) -> Path:
    return _path_under_root(
        root, settings.index_manifest_path.as_posix(), "retrieval index manifest"
    )


def _build_manifest_path(root: Path, build_id: UUID) -> Path:
    return _path_under_root(
        root,
        f"data/manifests/retrieval-index-builds/{build_id}.json",
        "per-build manifest",
    )


def _index_directory(root: Path, configured: Path, index_version: str, build_id: UUID) -> Path:
    parent = _path_under_root(root, configured.as_posix(), "index directory")
    if not parent.is_relative_to(root / "data/indexes"):
        raise IndexBuildError("UNSAFE_PATH", "Index directory must stay below data/indexes")
    return parent / index_version / str(build_id)


def _activate_pointer(
    root: Path,
    settings: RetrievalSettings,
    build_id: UUID,
    index_version: str,
    manifest_path: str,
    manifest_sha256: str,
) -> ActiveIndexPointer:
    pointer_path = _pointer_path(root, settings)
    with _exclusive_lock(pointer_path.with_suffix(pointer_path.suffix + ".lock")):
        current = _read_pointer(pointer_path)
        previous_error: str | None = None
        if current is not None:
            try:
                _verify_pointer(root, settings, current)
            except IndexBuildError as error:
                previous = None
                previous_error = error.code
            else:
                previous = ActiveIndexReference(
                    build_id=current.build_id,
                    index_version=current.index_version,
                    manifest_path=current.manifest_path,
                    manifest_sha256=current.manifest_sha256,
                )
        else:
            previous = None
        pointer = ActiveIndexPointer(
            build_id=build_id,
            index_version=index_version,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            previous=previous,
            previous_validation_error=previous_error,
        )
        _atomic_write_json(pointer_path, pointer.model_dump(mode="json"))
    return pointer


def _verify_pointer(
    root: Path,
    settings: RetrievalSettings,
    pointer: ActiveIndexPointer,
) -> IndexBuildManifest:
    manifest_path = _path_under_root(root, pointer.manifest_path, "build manifest")
    try:
        manifest_bytes = manifest_path.read_bytes()
        value = json.loads(manifest_bytes)
        manifest = IndexBuildManifest.model_validate(value)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise IndexBuildError(
            "INDEX_MANIFEST_INVALID", "Active build manifest is missing or invalid"
        ) from error
    if hashlib.sha256(manifest_bytes).hexdigest() != pointer.manifest_sha256:
        raise IndexBuildError(
            "INDEX_MANIFEST_CHECKSUM_MISMATCH", "Active build manifest hash does not match"
        )
    if manifest.build_id != pointer.build_id or manifest.index_version != pointer.index_version:
        raise IndexBuildError(
            "INDEX_POINTER_MISMATCH", "Active pointer and build manifest disagree"
        )
    if not manifest.validation.passed:
        raise IndexBuildError(
            "INDEX_VALIDATION_FAILED", "Active index manifest does not pass validation"
        )

    chroma_path = _path_under_root(root, manifest.outputs.chroma_path, "Chroma index path")
    bm25_path = _path_under_root(root, manifest.outputs.bm25_path, "BM25 index path")
    if not chroma_path.is_relative_to(root / "data/indexes") or not bm25_path.is_relative_to(
        root / "data/indexes"
    ):
        raise IndexBuildError("UNSAFE_PATH", "Index output path must stay below data/indexes")
    if not chroma_path.is_dir() or not bm25_path.is_dir():
        raise IndexBuildError("INDEX_FILES_MISSING", "Active index files are missing")
    if _directory_sha256(bm25_path) != manifest.outputs.bm25_sha256:
        raise IndexBuildError("BM25_CHECKSUM_MISMATCH", "Active BM25 files changed")

    try:
        chroma_runtime_path = runtime_chroma_path(chroma_path, manifest)
        client = chromadb.PersistentClient(
            path=str(chroma_runtime_path),
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_collection(
            name=_collection_name(manifest.index_version),
            embedding_function=None,
        )
    except Exception as error:
        raise IndexBuildError(
            "CHROMA_UNAVAILABLE", "Active Chroma collection cannot be opened"
        ) from error
    if collection.count() != manifest.counts.chroma_records:
        raise IndexBuildError(
            "CHROMA_COUNT_MISMATCH", "Active Chroma count differs from its manifest"
        )
    if (
        collection.metadata is None
        or collection.metadata.get("index_version") != manifest.index_version
    ):
        raise IndexBuildError("CHROMA_VERSION_MISMATCH", "Active Chroma metadata is incompatible")
    if collection.metadata.get("embedding_dimension") != manifest.embedding.dimension:
        raise IndexBuildError(
            "EMBEDDING_DIMENSION_MISMATCH", "Active Chroma dimension differs from its manifest"
        )
    # Vercel runs Linux/x86_64 while indexes may be built on macOS/arm64. Chroma
    # stores vectors in a platform-native ANN index, so its retrieved float values
    # can differ at the last bits. The deployed artifact is immutable; still verify
    # its count, index version, dimension, and exact passage-ID agreement with BM25.
    if (
        not os.environ.get("VERCEL")
        and _chroma_logical_sha256(collection) != manifest.outputs.chroma_sha256
    ):
        raise IndexBuildError("CHROMA_CHECKSUM_MISMATCH", "Active Chroma logical records changed")

    try:
        retriever = bm25s.BM25.load(bm25_path, load_corpus=True, show_progress=False)
        corpus = list(retriever.corpus)
        corpus_ids = [item.get("text") if isinstance(item, dict) else item for item in corpus]
    except Exception as error:
        raise IndexBuildError("BM25_UNAVAILABLE", "Active BM25 index cannot be opened") from error
    if (
        len(corpus_ids) != manifest.counts.bm25_records
        or any(not isinstance(passage_id, str) for passage_id in corpus_ids)
        or set(corpus_ids) != set(collection.get(include=[])["ids"])
    ):
        raise IndexBuildError(
            "BM25_COUNT_MISMATCH", "Active BM25 IDs differ from the active Chroma collection"
        )
    return manifest


def _active_reference(pointer: ActiveIndexPointer) -> ActiveIndexReference:
    return ActiveIndexReference(
        build_id=pointer.build_id,
        index_version=pointer.index_version,
        manifest_path=pointer.manifest_path,
        manifest_sha256=pointer.manifest_sha256,
    )


def build_index(
    project_root: Path,
    settings: RetrievalSettings,
    embedder: _Embedder,
    chunker: ChunkerConfig,
) -> ActiveIndexPointer:
    root = project_root.resolve()
    build_id = uuid4()
    started_at = _utcnow()
    clock_start = time.perf_counter()
    chroma_path: Path | None = None
    bm25_path: Path | None = None
    manifest_written = False
    try:
        try:
            sources = load_current_sources(root)
        except IndexInputError as error:
            raise IndexBuildError(error.code, str(error)) from error
        passages, inputs = _load_passages(root, sources, chunker, embedder)
        vectors: list[list[float]] = []
        for start in range(0, len(passages), settings.embedding_batch_size):
            batch = passages[start : start + settings.embedding_batch_size]
            vectors.extend(embedder.embed_passages(batch))
        descriptor = embedder.descriptor
        _validate_vectors(vectors, len(passages), descriptor.dimension)

        inputs = sorted(inputs, key=lambda item: item.source_id)
        corpus_sha256 = _fingerprint([item.model_dump(mode="json") for item in inputs])
        bm25_parameters: dict[str, object] = {
            "package_version": importlib.metadata.version("bm25s"),
            "method": "lucene",
            "k1": settings.bm25_k1,
            "b": settings.bm25_b,
            "tokenizer": "unicode-word-v1",
            "token_pattern": BM25_TOKEN_PATTERN,
            "stopwords": [],
            "stemming": None,
        }
        tokenizer: dict[str, str] = {
            "name": chunker.tokenizer,
            "version": f"{descriptor.provider}:{descriptor.model_id}:{descriptor.package_version}",
        }
        fingerprint_payload = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "inputs": [item.model_dump(mode="json") for item in inputs],
            "chunker": chunker.model_dump(mode="json"),
            "tokenizer": tokenizer,
            "embedding": descriptor.model_dump(mode="json"),
            "bm25": bm25_parameters,
        }
        index_version = _fingerprint(fingerprint_payload)
        chroma_path = _index_directory(
            root, settings.chroma_persist_directory, index_version, build_id
        )
        bm25_path = _index_directory(root, settings.bm25_index_directory, index_version, build_id)
        chroma_path.mkdir(parents=True, exist_ok=False)
        bm25_path.mkdir(parents=True, exist_ok=False)
        scopes = tuple(sorted({source.sensitivity for source in sources}))
        chroma_count, chroma_sha256 = _build_chroma(
            chroma_path, index_version, descriptor, passages, vectors, scopes
        )
        bm25_count = _build_bm25(bm25_path, passages, settings.bm25_k1, settings.bm25_b)
        bm25_sha256 = _directory_sha256(bm25_path)
        finished_at = _utcnow()
        manifest_path = _build_manifest_path(root, build_id)
        manifest = IndexBuildManifest(
            build_id=build_id,
            index_version=index_version,
            status="validated",
            started_at=started_at,
            finished_at=finished_at,
            corpus_sha256=corpus_sha256,
            inputs=tuple(inputs),
            chunker=chunker.model_dump(mode="json"),
            tokenizer=tokenizer,
            embedding=descriptor,
            bm25=bm25_parameters,
            counts=IndexCounts(
                sources=len(sources),
                documents=len({passage.document_id for passage in passages}),
                structured_rows=sum(passage.row_key is not None for passage in passages),
                passages=len(passages),
                chroma_records=chroma_count,
                bm25_records=bm25_count,
            ),
            validation=IndexValidation(
                passed=True,
                checks=(
                    "canonical hashes verified",
                    "passage IDs unique",
                    "embedding dimensions and norms verified",
                    "Chroma count and permission-filter smoke query verified",
                    "BM25S save/load and passage-ID smoke query verified",
                ),
                smoke_case_ids=(),
            ),
            elapsed_seconds=time.perf_counter() - clock_start,
            outputs=IndexOutputs(
                chroma_path=_relative_path(root, chroma_path),
                bm25_path=_relative_path(root, bm25_path),
                chroma_sha256=chroma_sha256,
                bm25_sha256=bm25_sha256,
            ),
        )
        manifest_payload = _atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
        manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
        _append_manifest_entry(
            _index_manifest_path(root, settings),
            "builds",
            {
                "build_id": str(build_id),
                "index_version": index_version,
                "status": "validated",
                "manifest_path": _relative_path(root, manifest_path),
                "manifest_sha256": manifest_sha256,
            },
        )
        manifest_written = True
        pointer = _activate_pointer(
            root,
            settings,
            build_id,
            index_version,
            _relative_path(root, manifest_path),
            manifest_sha256,
        )
        return pointer
    except Exception as error:
        if not manifest_written:
            for output_path in (chroma_path, bm25_path):
                if output_path is not None and output_path.exists():
                    shutil.rmtree(output_path)
        code = getattr(error, "code", "INDEX_BUILD_FAILED")
        try:
            _append_manifest_entry(
                _index_manifest_path(root, settings),
                "failures",
                {
                    "build_id": str(build_id),
                    "started_at": started_at.isoformat(),
                    "finished_at": _utcnow().isoformat(),
                    "error_code": code,
                    "message": "Index build failed; active pointer was not changed.",
                },
            )
        except Exception:
            pass
        if isinstance(error, IndexBuildError):
            raise
        raise IndexBuildError(code, "Index build failed; active pointer was not changed") from error


def verify_active_index(project_root: Path, settings: RetrievalSettings) -> ActiveIndexPointer:
    root = project_root.resolve()
    pointer = _read_pointer(_pointer_path(root, settings))
    if pointer is None:
        raise IndexBuildError("INDEX_NOT_ACTIVE", "No retrieval index is active")
    _verify_pointer(root, settings, pointer)
    return pointer


def active_embedding_descriptor(
    project_root: Path,
    settings: RetrievalSettings,
) -> EmbeddingDescriptor:
    root = project_root.resolve()
    pointer = _read_pointer(_pointer_path(root, settings))
    if pointer is None:
        raise IndexBuildError("INDEX_NOT_ACTIVE", "No retrieval index is active")
    return _verify_pointer(root, settings, pointer).embedding


def rollback_active_index(project_root: Path, settings: RetrievalSettings) -> ActiveIndexPointer:
    root = project_root.resolve()
    pointer_path = _pointer_path(root, settings)
    with _exclusive_lock(pointer_path.with_suffix(pointer_path.suffix + ".lock")):
        current = _read_pointer(pointer_path)
        if current is None or current.previous is None:
            raise IndexBuildError(
                "ROLLBACK_UNAVAILABLE", "No previous validated index is available"
            )
        previous = current.previous
        candidate = ActiveIndexPointer(
            build_id=previous.build_id,
            index_version=previous.index_version,
            manifest_path=previous.manifest_path,
            manifest_sha256=previous.manifest_sha256,
        )
        _verify_pointer(root, settings, candidate)
        restored = ActiveIndexPointer(
            build_id=candidate.build_id,
            index_version=candidate.index_version,
            manifest_path=candidate.manifest_path,
            manifest_sha256=candidate.manifest_sha256,
            previous=_active_reference(current),
        )
        _atomic_write_json(pointer_path, restored.model_dump(mode="json"))
        return restored
