from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from policylens.conversations.memory import (
    MEMORY_COLLECTION_NAME,
    MEMORY_SCHEMA_VERSION,
    ConversationMemoryError,
    ConversationMemoryService,
    MemoryClient,
    memory_persist_directory,
)
from policylens.settings import AppSettings


class FakeEmbedder:
    def __init__(self, *, model_id: str = "fake-embedder", dimension: int = 2) -> None:
        self.provider = "local"
        self.model_id = model_id
        self.dimension = dimension
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [1.0, 0.0][: self.dimension]


class FakeCollection:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.metadata = metadata
        self.records: dict[str, tuple[str, dict[str, Any], list[float]]] = {}
        self.query_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        for item_id, document, embedding, metadata in zip(
            ids, documents, embeddings, metadatas, strict=True
        ):
            self.records[item_id] = (
                document,
                metadata,
                list(embedding),
            )

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        where = kwargs["where"]
        workspace_id = where["workspace_id"]
        records = [
            (item_id, document, metadata)
            for item_id, (document, metadata, _embedding) in self.records.items()
            if metadata.get("workspace_id") == workspace_id
        ][: kwargs["n_results"]]
        return {
            "ids": [[record[0] for record in records]],
            "documents": [[record[1] for record in records]],
            "metadatas": [[record[2] for record in records]],
            "distances": [[0.1 for _record in records]],
        }

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        include: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        records = list(self.records.items())
        if where is not None:
            records = [record for record in records if self._matches(record[1][1], where)]
        result: dict[str, Any] = {"ids": [item_id for item_id, _record in records]}
        if include and "documents" in include:
            result["documents"] = [record[0] for _item_id, record in records]
        if include and "metadatas" in include:
            result["metadatas"] = [record[1] for _item_id, record in records]
        return result

    def delete(
        self,
        *,
        where: dict[str, Any] | None = None,
        ids: Sequence[str] | None = None,
    ) -> None:
        self.delete_calls.append({"where": where, "ids": ids})
        if where is None and ids is None:
            raise AssertionError("unscoped delete is prohibited")
        for item_id in list(self.records):
            _document, metadata, _embedding = self.records[item_id]
            matches = ids is not None and item_id in ids
            if where is not None:
                matches = matches or self._matches(metadata, where)
            if matches:
                del self.records[item_id]

    @classmethod
    def _matches(cls, metadata: dict[str, Any], where: dict[str, Any]) -> bool:
        conjunction = where.get("$and")
        if isinstance(conjunction, list):
            return all(cls._matches(metadata, condition) for condition in conjunction)
        return all(metadata.get(key) == value for key, value in where.items())

    def count(self) -> int:
        return len(self.records)


class FakeChromaClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.created: list[FakeCollection] = []
        self.deleted: list[str] = []

    def list_collections(self) -> list[FakeCollection]:
        return list(self.collections.values())

    def get_collection(self, *, name: str, embedding_function: None = None) -> FakeCollection:
        del embedding_function
        if name not in self.collections:
            raise KeyError(name)
        return self.collections[name]

    def create_collection(
        self,
        *,
        name: str,
        metadata: dict[str, Any],
        embedding_function: None = None,
    ) -> FakeCollection:
        del embedding_function
        collection = FakeCollection(name, metadata)
        self.collections[name] = collection
        self.created.append(collection)
        return collection

    def delete_collection(self, *, name: str) -> None:
        self.deleted.append(name)
        self.collections.pop(name, None)


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="test-only",
        embedding_provider="local",
        local_embedding_model="fake-embedder",
        chroma_persist_directory=tmp_path / "corpus-chroma",
    )


def _service(
    tmp_path: Path,
    *,
    embedder: FakeEmbedder | None = None,
    client: FakeChromaClient | None = None,
) -> tuple[ConversationMemoryService, FakeEmbedder, FakeChromaClient]:
    selected_embedder = embedder or FakeEmbedder()
    selected_client = client or FakeChromaClient()
    service = ConversationMemoryService(
        _settings(tmp_path),
        embedder=selected_embedder,
        client=cast(MemoryClient, selected_client),
    )
    return service, selected_embedder, selected_client


def test_memory_path_is_stable_and_collection_has_versioned_embedding_metadata(
    tmp_path: Path,
) -> None:
    service, _embedder, client = _service(tmp_path)
    workspace_id = uuid4()

    service.store(
        workspace_id,
        uuid4(),
        uuid4(),
        "Synthetic question",
        "Synthetic answer",
    )

    assert memory_persist_directory(_settings(tmp_path)) == (
        tmp_path / "corpus-chroma" / MEMORY_COLLECTION_NAME
    )
    collection = client.collections[MEMORY_COLLECTION_NAME]
    assert collection.metadata == {
        "hnsw:space": "cosine",
        "schema_version": MEMORY_SCHEMA_VERSION,
        "embedding_provider": "local",
        "embedding_model_id": "fake-embedder",
        "embedding_dimension": 2,
    }


def test_search_uses_exact_workspace_filter_and_never_returns_more_than_five(
    tmp_path: Path,
) -> None:
    service, _embedder, client = _service(tmp_path)
    workspace_id = uuid4()
    other_workspace = uuid4()
    session_id = uuid4()
    for index in range(7):
        service.store(
            workspace_id,
            session_id,
            uuid4(),
            f"Synthetic question {index}",
            f"Synthetic answer {index}",
        )
    service.store(
        other_workspace,
        uuid4(),
        uuid4(),
        "Other workspace private prompt",
        "Other workspace private response",
    )

    memories = service.search(workspace_id, "synthetic follow-up", limit=99)

    assert len(memories) == 5
    collection = client.collections[MEMORY_COLLECTION_NAME]
    assert collection.query_calls[-1]["where"] == {"workspace_id": str(workspace_id)}
    assert collection.query_calls[-1]["n_results"] == 5
    assert all(memory.workspace_id == workspace_id for memory in memories)
    assert all("Other workspace" not in memory.content for memory in memories)


def test_memory_documents_are_bounded_and_include_source_scope_metadata(
    tmp_path: Path,
) -> None:
    service, _embedder, client = _service(tmp_path)
    workspace_id, session_id, turn_id = uuid4(), uuid4(), uuid4()

    service.store(
        workspace_id,
        session_id,
        turn_id,
        "Q" * 2500,
        "A" * 5000,
    )

    collection = client.collections[MEMORY_COLLECTION_NAME]
    document, metadata, _embedding = collection.records[str(turn_id)]
    assert len(document) <= 4000
    assert metadata["workspace_id"] == str(workspace_id)
    assert metadata["session_id"] == str(session_id)
    assert metadata["embedding_provider"] == "local"
    assert metadata["embedding_model_id"] == "fake-embedder"
    assert metadata["embedding_dimension"] == 2


def test_embedding_identity_mismatch_fails_before_embedding_or_retrieval(
    tmp_path: Path,
) -> None:
    wrong_collection = FakeCollection(
        MEMORY_COLLECTION_NAME,
        {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "embedding_provider": "local",
            "embedding_model_id": "old-embedder",
            "embedding_dimension": 2,
        },
    )
    client = FakeChromaClient()
    client.collections[MEMORY_COLLECTION_NAME] = wrong_collection
    service, embedder, _client = _service(tmp_path, client=client)

    with pytest.raises(ConversationMemoryError, match="embedding identity"):
        service.search(uuid4(), "synthetic query")

    assert embedder.calls == []
    assert wrong_collection.query_calls == []


def test_session_and_workspace_deletes_always_use_exact_non_empty_filters(
    tmp_path: Path,
) -> None:
    service, _embedder, client = _service(tmp_path)
    workspace_id, session_id = uuid4(), uuid4()
    other_session = uuid4()
    service.store(workspace_id, session_id, uuid4(), "Q1", "A1")
    service.store(workspace_id, other_session, uuid4(), "Q2", "A2")

    assert service.delete_session(workspace_id, session_id) == 1
    assert service.clear_workspace(workspace_id) == 1

    collection = client.collections[MEMORY_COLLECTION_NAME]
    assert collection.count() == 0
    assert collection.delete_calls == [
        {
            "where": {
                "$and": [
                    {"workspace_id": str(workspace_id)},
                    {"session_id": str(session_id)},
                ]
            },
            "ids": None,
        },
        {"where": {"workspace_id": str(workspace_id)}, "ids": None},
    ]


def test_clearing_incompatible_collection_resets_it_for_the_current_identity(
    tmp_path: Path,
) -> None:
    client = FakeChromaClient()
    incompatible = FakeCollection(
        MEMORY_COLLECTION_NAME,
        {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "embedding_provider": "local",
            "embedding_model_id": "old-embedder",
            "embedding_dimension": 2,
        },
    )
    workspace_id, session_id = uuid4(), uuid4()
    incompatible.records["old-memory"] = (
        "Synthetic old memory",
        {
            "workspace_id": str(workspace_id),
            "session_id": str(session_id),
            "created_at": "2026-10-27T00:00:00Z",
        },
        [1.0, 0.0],
    )
    client.collections[MEMORY_COLLECTION_NAME] = incompatible
    service, _embedder, _client = _service(tmp_path, client=client)

    assert service.clear_workspace(workspace_id) == 1
    assert client.deleted == [MEMORY_COLLECTION_NAME]
    assert MEMORY_COLLECTION_NAME not in client.collections

    service.store(workspace_id, session_id, uuid4(), "New question", "New answer")
    replacement = client.collections[MEMORY_COLLECTION_NAME]
    assert replacement.metadata["embedding_model_id"] == "fake-embedder"
    assert replacement.metadata["schema_version"] == MEMORY_SCHEMA_VERSION


def test_incompatible_collection_is_not_reset_if_other_workspace_has_records(
    tmp_path: Path,
) -> None:
    client = FakeChromaClient()
    incompatible = FakeCollection(
        MEMORY_COLLECTION_NAME,
        {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "embedding_provider": "local",
            "embedding_model_id": "old-embedder",
            "embedding_dimension": 2,
        },
    )
    workspace_id, other_workspace = uuid4(), uuid4()
    for index, owner in enumerate((workspace_id, other_workspace)):
        incompatible.records[f"old-memory-{index}"] = (
            "Synthetic old memory",
            {
                "workspace_id": str(owner),
                "session_id": str(uuid4()),
                "created_at": "2026-10-27T00:00:00Z",
            },
            [1.0, 0.0],
        )
    client.collections[MEMORY_COLLECTION_NAME] = incompatible
    service, _embedder, _client = _service(tmp_path, client=client)

    with pytest.raises(ConversationMemoryError, match="embedding identity changed"):
        service.clear_workspace(workspace_id)

    assert client.deleted == []
    assert incompatible.count() == 2
    assert incompatible.delete_calls == []
