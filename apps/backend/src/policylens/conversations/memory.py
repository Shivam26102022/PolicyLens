from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import Field

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import create_embedding_provider
from policylens.retrieval.models import StrictModel
from policylens.settings import PROJECT_ROOT, AppSettings

MEMORY_SCHEMA_VERSION = "1.0"
MEMORY_COLLECTION_NAME = "policylens_chat_memory_v1"
MAX_MEMORY_RESULTS = 5
MAX_MEMORY_DOCUMENT_CHARS = 4000


class ConversationMemoryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MemoryCollection(Protocol):
    metadata: dict[str, Any] | None

    def count(self) -> int: ...

    def delete(
        self,
        *,
        where: dict[str, Any] | None = None,
        ids: list[str] | None = None,
    ) -> Any: ...

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...

    def upsert(self, **kwargs: Any) -> Any: ...


class MemoryClient(Protocol):
    def create_collection(
        self,
        *,
        name: str,
        metadata: dict[str, Any],
        embedding_function: None = None,
    ) -> MemoryCollection: ...

    def delete_collection(self, *, name: str) -> Any: ...

    def get_collection(
        self,
        *,
        name: str,
        embedding_function: None = None,
    ) -> MemoryCollection: ...

    def list_collections(self) -> list[Any]: ...


class MemoryEmbedder(Protocol):
    def embed_query(self, query: str) -> list[float]: ...


class ConversationMemory(StrictModel):
    memory_id: str = Field(min_length=1, max_length=100)
    workspace_id: UUID
    session_id: UUID
    content: str = Field(min_length=1, max_length=MAX_MEMORY_DOCUMENT_CHARS)
    created_at: str = Field(min_length=1, max_length=100)
    distance: float | None = Field(default=None, ge=0)


def memory_persist_directory(settings: AppSettings) -> Path:
    if os.environ.get("VERCEL"):
        # The deployed project directory is read-only; /tmp is the only writable path.
        return Path("/tmp/policylens_memory") / MEMORY_COLLECTION_NAME
    root = settings.chroma_persist_directory.expanduser()
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return root.resolve() / MEMORY_COLLECTION_NAME


class ConversationMemoryService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        embedder: MemoryEmbedder | None = None,
        client: MemoryClient | None = None,
        persist_directory: Path | None = None,
    ) -> None:
        self._settings = settings
        self._retrieval_settings = RetrievalSettings.from_app_settings(settings)
        self._embedder = embedder
        self._client = client
        self.persist_directory = persist_directory or memory_persist_directory(settings)

    def _provider_identity(self) -> tuple[str, str]:
        provider = self._retrieval_settings.embedding_provider
        model_id = (
            self._retrieval_settings.local_embedding_model
            if provider == "local"
            else self._retrieval_settings.openai_embedding_model
        )
        if not model_id:
            raise ConversationMemoryError(
                "MEMORY_EMBEDDING_UNAVAILABLE",
                "The configured conversation-memory embedding model is unavailable.",
            )
        return provider, model_id

    def _get_client(self) -> MemoryClient:
        if self._client is None:
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = cast(
                MemoryClient,
                chromadb.PersistentClient(
                    path=str(self.persist_directory),
                    settings=ChromaSettings(anonymized_telemetry=False),
                ),
            )
        return self._client

    def _get_embedder(self) -> MemoryEmbedder:
        if self._embedder is None:
            self._embedder = create_embedding_provider(self._retrieval_settings)
        return self._embedder

    def _existing_collection(self) -> MemoryCollection | None:
        client = self._get_client()
        try:
            collections = client.list_collections()
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_STORE_UNAVAILABLE",
                "The conversation-memory vector store is unavailable.",
            ) from error
        names = {
            item if isinstance(item, str) else getattr(item, "name", None) for item in collections
        }
        if MEMORY_COLLECTION_NAME not in names:
            return None
        try:
            return client.get_collection(
                name=MEMORY_COLLECTION_NAME,
                embedding_function=None,
            )
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_STORE_UNAVAILABLE",
                "The conversation-memory collection could not be opened.",
            ) from error

    def _validate_collection(
        self,
        collection: MemoryCollection,
        *,
        dimension: int | None = None,
    ) -> None:
        metadata = collection.metadata
        provider, model_id = self._provider_identity()
        if not isinstance(metadata, dict) or metadata.get("schema_version") != (
            MEMORY_SCHEMA_VERSION
        ):
            raise ConversationMemoryError(
                "MEMORY_COLLECTION_VERSION_MISMATCH",
                "The conversation-memory collection has an unsupported schema version.",
            )
        if (
            metadata.get("embedding_provider") != provider
            or metadata.get("embedding_model_id") != model_id
        ):
            raise ConversationMemoryError(
                "MEMORY_EMBEDDING_IDENTITY_MISMATCH",
                "Conversation memory is unavailable because its embedding identity changed.",
            )
        stored_dimension = metadata.get("embedding_dimension")
        if not isinstance(stored_dimension, int) or stored_dimension < 1:
            raise ConversationMemoryError(
                "MEMORY_COLLECTION_INVALID",
                "The conversation-memory collection has invalid embedding metadata.",
            )
        if dimension is not None and stored_dimension != dimension:
            raise ConversationMemoryError(
                "MEMORY_EMBEDDING_IDENTITY_MISMATCH",
                "Conversation memory is unavailable because its embedding dimension changed.",
            )

    def _embed(self, text: str) -> list[float]:
        try:
            vector = self._get_embedder().embed_query(text)
        except ConversationMemoryError:
            raise
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_EMBEDDING_UNAVAILABLE",
                "The configured conversation-memory embedding provider failed.",
            ) from error
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ConversationMemoryError(
                "MEMORY_EMBEDDING_INVALID",
                "The configured conversation-memory embedding provider returned an invalid vector.",
            )
        return vector

    def _create_collection(self, dimension: int) -> MemoryCollection:
        provider, model_id = self._provider_identity()
        try:
            return self._get_client().create_collection(
                name=MEMORY_COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",
                    "schema_version": MEMORY_SCHEMA_VERSION,
                    "embedding_provider": provider,
                    "embedding_model_id": model_id,
                    "embedding_dimension": dimension,
                },
                embedding_function=None,
            )
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_STORE_UNAVAILABLE",
                "The conversation-memory collection could not be created.",
            ) from error

    @staticmethod
    def _workspace_filter(workspace_id: UUID) -> dict[str, str]:
        return {"workspace_id": str(workspace_id)}

    @staticmethod
    def _scope_records(
        response: dict[str, Any],
        *,
        workspace_id: UUID,
    ) -> list[str]:
        ids = response.get("ids")
        if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
            raise ConversationMemoryError(
                "MEMORY_COLLECTION_INVALID",
                "The conversation-memory collection returned malformed record identifiers.",
            )
        return ids

    def _workspace_record_ids(
        self,
        collection: MemoryCollection,
        workspace_id: UUID,
    ) -> list[str]:
        try:
            records = collection.get(
                where=self._workspace_filter(workspace_id),
                include=["metadatas"],
            )
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_STORE_UNAVAILABLE",
                "Workspace conversation memories could not be inspected.",
            ) from error
        ids = self._scope_records(records, workspace_id=workspace_id)
        metadatas = records.get("metadatas")
        if not isinstance(metadatas, list) or len(metadatas) != len(ids):
            raise ConversationMemoryError(
                "MEMORY_COLLECTION_INVALID",
                "Workspace conversation memory metadata is incomplete.",
            )
        if any(
            not isinstance(metadata, dict) or metadata.get("workspace_id") != str(workspace_id)
            for metadata in metadatas
        ):
            raise ConversationMemoryError(
                "MEMORY_WORKSPACE_FILTER_INVALID",
                "The vector store returned a record outside the requested workspace.",
            )
        return ids

    def store(
        self,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        user_content: str,
        assistant_content: str,
        *,
        created_at: datetime | None = None,
    ) -> None:
        content = f"User: {user_content}\nAssistant: {assistant_content}"[
            :MAX_MEMORY_DOCUMENT_CHARS
        ]
        if not content.strip():
            raise ConversationMemoryError(
                "MEMORY_DOCUMENT_INVALID",
                "A conversation memory must contain a user message and response.",
            )
        collection = self._existing_collection()
        if collection is not None:
            self._validate_collection(collection)
        vector = self._embed(content)
        if collection is None:
            collection = self._create_collection(len(vector))
        else:
            self._validate_collection(collection, dimension=len(vector))
        provider, model_id = self._provider_identity()
        created = (created_at or datetime.now(UTC)).astimezone(UTC).isoformat()
        metadata = {
            "workspace_id": str(workspace_id),
            "session_id": str(session_id),
            "created_at": created,
            "embedding_provider": provider,
            "embedding_model_id": model_id,
            "embedding_dimension": len(vector),
        }
        try:
            collection.upsert(
                ids=[str(turn_id)],
                embeddings=[vector],
                documents=[content],
                metadatas=[metadata],
            )
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_STORE_UNAVAILABLE",
                "The completed conversation memory could not be stored.",
            ) from error

    def search(
        self,
        workspace_id: UUID,
        query: str,
        *,
        limit: int = MAX_MEMORY_RESULTS,
    ) -> tuple[ConversationMemory, ...]:
        bounded_limit = min(limit, MAX_MEMORY_RESULTS)
        if bounded_limit < 1:
            raise ValueError("memory result limit must be at least one")
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("memory query must not be empty")
        collection = self._existing_collection()
        if collection is None:
            return ()
        self._validate_collection(collection)
        workspace_ids = self._workspace_record_ids(collection, workspace_id)
        if not workspace_ids:
            return ()
        vector = self._embed(normalized_query)
        self._validate_collection(collection, dimension=len(vector))
        try:
            result = collection.query(
                query_embeddings=[vector],
                n_results=bounded_limit,
                where=self._workspace_filter(workspace_id),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_RETRIEVAL_UNAVAILABLE",
                "Workspace conversation memory could not be retrieved.",
            ) from error
        ids = _first_group(result, "ids")
        documents = _first_group(result, "documents")
        metadatas = _first_group(result, "metadatas")
        distances = _first_group(result, "distances")
        if not (
            len(ids) == len(documents) == len(metadatas) == len(distances)
            and len(ids) <= bounded_limit
        ):
            raise ConversationMemoryError(
                "MEMORY_COLLECTION_INVALID",
                "The conversation-memory query returned malformed results.",
            )
        memories: list[ConversationMemory] = []
        for item_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=True,
        ):
            if (
                not isinstance(item_id, str)
                or not isinstance(document, str)
                or len(document) > MAX_MEMORY_DOCUMENT_CHARS
                or not isinstance(metadata, dict)
                or metadata.get("workspace_id") != str(workspace_id)
                or not isinstance(metadata.get("session_id"), str)
                or not isinstance(metadata.get("created_at"), str)
                or not isinstance(distance, (int, float))
                or not math.isfinite(distance)
                or distance < 0
            ):
                raise ConversationMemoryError(
                    "MEMORY_COLLECTION_INVALID",
                    "The conversation-memory query returned an invalid record.",
                )
            memories.append(
                ConversationMemory(
                    memory_id=item_id,
                    workspace_id=workspace_id,
                    session_id=UUID(metadata["session_id"]),
                    content=document,
                    created_at=metadata["created_at"],
                    distance=float(distance),
                )
            )
        return tuple(memories)

    def delete_session(self, workspace_id: UUID, session_id: UUID) -> int:
        collection = self._existing_collection()
        if collection is None:
            return 0
        where = {
            "$and": [
                {"workspace_id": str(workspace_id)},
                {"session_id": str(session_id)},
            ]
        }
        try:
            records = collection.get(where=where, include=["metadatas"])
            ids = self._scope_records(records, workspace_id=workspace_id)
            metadatas = records.get("metadatas")
            if not isinstance(metadatas, list) or len(metadatas) != len(ids):
                raise ConversationMemoryError(
                    "MEMORY_COLLECTION_INVALID",
                    "Session memory metadata is incomplete.",
                )
            if any(
                not isinstance(metadata, dict)
                or metadata.get("workspace_id") != str(workspace_id)
                or metadata.get("session_id") != str(session_id)
                for metadata in metadatas
            ):
                raise ConversationMemoryError(
                    "MEMORY_WORKSPACE_FILTER_INVALID",
                    "The vector store returned a record outside the requested session.",
                )
            if ids:
                collection.delete(where=where)
        except ConversationMemoryError:
            raise
        except Exception as error:
            raise ConversationMemoryError(
                "MEMORY_DELETE_FAILED",
                "Session conversation memories could not be deleted.",
            ) from error
        return len(ids)

    def clear_workspace(self, workspace_id: UUID) -> int:
        collection = self._existing_collection()
        if collection is None:
            return 0
        ids = self._workspace_record_ids(collection, workspace_id)
        identity_mismatch = False
        try:
            self._validate_collection(collection)
        except ConversationMemoryError as error:
            if error.code != "MEMORY_EMBEDDING_IDENTITY_MISMATCH":
                raise
            identity_mismatch = True
        if identity_mismatch:
            try:
                total_records = collection.count()
            except Exception as error:
                raise ConversationMemoryError(
                    "MEMORY_STORE_UNAVAILABLE",
                    "The conversation-memory collection could not be inspected.",
                ) from error
            if total_records != len(ids):
                raise ConversationMemoryError(
                    "MEMORY_EMBEDDING_IDENTITY_MISMATCH",
                    "The embedding identity changed; other workspace records prevent a safe reset.",
                )
        if ids:
            try:
                collection.delete(where=self._workspace_filter(workspace_id))
            except Exception as error:
                raise ConversationMemoryError(
                    "MEMORY_DELETE_FAILED",
                    "Workspace conversation memories could not be cleared.",
                ) from error
        if identity_mismatch:
            try:
                self._get_client().delete_collection(name=MEMORY_COLLECTION_NAME)
            except Exception as error:
                raise ConversationMemoryError(
                    "MEMORY_RESET_FAILED",
                    "Workspace memories were removed, but the incompatible "
                    "collection could not be reset.",
                ) from error
        return len(ids)


def _first_group(result: dict[str, Any], key: str) -> list[Any]:
    groups = result.get(key)
    if not isinstance(groups, list) or not groups or not isinstance(groups[0], list):
        raise ConversationMemoryError(
            "MEMORY_COLLECTION_INVALID",
            "The conversation-memory query returned malformed results.",
        )
    return groups[0]
