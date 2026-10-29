from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import tiktoken

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.models import CorpusPassage, EmbeddingDescriptor


class EmbeddingInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EmbeddingProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EmbeddingProvider(Protocol):
    @property
    def descriptor(self) -> EmbeddingDescriptor: ...

    @property
    def cache_identity(self) -> dict[str, str | None]: ...

    @property
    def max_input_tokens(self) -> int: ...

    def count_tokens(self, text: str) -> int: ...

    def embed_passages(self, passages: Sequence[CorpusPassage]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError as error:
        raise EmbeddingProviderError(
            "DEPENDENCY_MISSING", f"Required package {package} is unavailable"
        ) from error


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_vector(values: Iterable[Any], expected_dimension: int | None) -> list[float]:
    vector = [float(value) for value in values]
    if not vector or any(not math.isfinite(value) for value in vector):
        raise EmbeddingProviderError("EMBEDDING_INVALID", "Embedding vector is empty or non-finite")
    if expected_dimension is not None and len(vector) != expected_dimension:
        raise EmbeddingProviderError("EMBEDDING_DIMENSION_MISMATCH", "Embedding dimension changed")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise EmbeddingProviderError(
            "EMBEDDING_INVALID", "Embedding vector has zero or invalid norm"
        )
    return [value / norm for value in vector]


class FastEmbedProvider:
    def __init__(
        self,
        settings: RetrievalSettings,
        *,
        model: Any | None = None,
        package_version: str | None = None,
        max_input_tokens: int = 512,
    ) -> None:
        if settings.embedding_provider != "local":
            raise EmbeddingInputError(
                "PROVIDER_MISMATCH", "Local provider requires EMBEDDING_PROVIDER=local"
            )
        if max_input_tokens < 1:
            raise ValueError("max_input_tokens must be positive")
        if model is None:
            from fastembed import TextEmbedding

            model = TextEmbedding(
                model_name=settings.local_embedding_model,
                cache_dir=str(settings.model_cache_directory),
                cuda=False,
            )
        self._model = model
        self._model_id = settings.local_embedding_model
        self._package_version = package_version or _package_version("fastembed")
        self._max_input_tokens = max_input_tokens
        self._dimension = int(model.embedding_size)
        runtime_model = getattr(self._model, "model", None)
        model_description = getattr(runtime_model, "model_description", None)
        model_directory = getattr(runtime_model, "_model_dir", None)
        model_file = getattr(model_description, "model_file", None)
        model_artifact = (
            Path(model_directory) / model_file if model_directory and model_file else None
        )
        self._model_revision = Path(model_directory).name if model_directory else None
        self._model_sha256 = _file_sha256(model_artifact) if model_artifact else None
        self._licence = str(getattr(model_description, "license", "unknown"))
        self._pooling = (
            "first-token CLS" if self._model_id == "BAAI/bge-small-en-v1.5" else "model-defined"
        )
        self._tokenizer = self._model_id
        if self._dimension < 1:
            raise EmbeddingProviderError(
                "EMBEDDING_DIMENSION_INVALID", "Local embedding dimension must be positive"
            )

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    @property
    def descriptor(self) -> EmbeddingDescriptor:
        return EmbeddingDescriptor(
            provider="local",
            model_id=self._model_id,
            package_version=self._package_version,
            model_revision=self._model_revision,
            model_sha256=self._model_sha256,
            licence=self._licence,
            pooling=self._pooling,
            tokenizer=self._tokenizer,
            query_method="query_embed",
            passage_method="passage_embed",
            dimension=self._dimension,
            normalized=True,
            max_input_tokens=self._max_input_tokens,
        )

    @property
    def cache_identity(self) -> dict[str, str | None]:
        return {
            "provider": "local",
            "model_id": self._model_id,
            "package_version": self._package_version,
            "model_revision": self._model_revision,
            "model_sha256": self._model_sha256,
        }

    def count_tokens(self, text: str) -> int:
        return int(self._model.token_count(text))

    def _check_text(self, text: str) -> None:
        token_count = self.count_tokens(text)
        if token_count > self._max_input_tokens:
            raise EmbeddingInputError(
                "EMBEDDING_INPUT_TOO_LONG",
                f"Input exceeds token limit: {token_count} tokens; "
                f"maximum is {self._max_input_tokens}",
            )

    def embed_passages(self, passages: Sequence[CorpusPassage]) -> list[list[float]]:
        if not passages:
            return []
        texts = [passage.embedding_text for passage in passages]
        for text in texts:
            self._check_text(text)
        vectors = list(self._model.passage_embed(texts))
        if len(vectors) != len(passages):
            raise EmbeddingProviderError(
                "EMBEDDING_COUNT_MISMATCH", "Local provider returned an unexpected vector count"
            )
        return [_normalize_vector(vector, self._dimension) for vector in vectors]

    def embed_query(self, query: str) -> list[float]:
        normalized = query.strip()
        if not normalized:
            raise EmbeddingInputError("QUERY_EMPTY", "Query must not be empty")
        self._check_text(normalized)
        vectors = list(self._model.query_embed(normalized))
        if len(vectors) != 1:
            raise EmbeddingProviderError(
                "EMBEDDING_COUNT_MISMATCH",
                "Local provider returned an unexpected query vector count",
            )
        return _normalize_vector(vectors[0], self._dimension)


class OpenAIEmbeddingProvider:
    _SUPPORTED_MODEL = "text-embedding-3-small"
    _MAX_INPUT_TOKENS = 8191

    def __init__(
        self,
        settings: RetrievalSettings,
        *,
        client: Any | None = None,
        package_version: str | None = None,
    ) -> None:
        if settings.embedding_provider != "openai":
            raise EmbeddingInputError(
                "PROVIDER_MISMATCH", "OpenAI provider requires EMBEDDING_PROVIDER=openai"
            )
        if settings.openai_embedding_model != self._SUPPORTED_MODEL:
            raise EmbeddingInputError(
                "EMBEDDING_MODEL_UNSUPPORTED",
                f"Only {self._SUPPORTED_MODEL} is supported by this Feature 003 provider",
            )
        key = settings.openai_api_key.get_secret_value().strip() if settings.openai_api_key else ""
        if not key:
            raise EmbeddingInputError("OPENAI_KEY_MISSING", "OpenAI embeddings require an API key")
        self._model_id = self._SUPPORTED_MODEL
        self._package_version = package_version or _package_version("openai")
        self._client = client
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=key)
        try:
            self._encoding = tiktoken.encoding_for_model(self._model_id)
        except KeyError as error:
            raise EmbeddingProviderError(
                "EMBEDDING_TOKENIZER_UNAVAILABLE",
                "No tokenizer is registered for the configured embedding model",
            ) from error
        self._dimension: int | None = None

    @property
    def max_input_tokens(self) -> int:
        return self._MAX_INPUT_TOKENS

    @property
    def descriptor(self) -> EmbeddingDescriptor:
        if self._dimension is None:
            raise EmbeddingProviderError(
                "EMBEDDING_DIMENSION_UNKNOWN",
                "Embed at least one passage before reading the API model descriptor",
            )
        return EmbeddingDescriptor(
            provider="openai",
            model_id=self._model_id,
            package_version=self._package_version,
            licence="OpenAI API service terms",
            pooling="provider-managed",
            tokenizer="cl100k_base",
            query_method="embeddings.create",
            passage_method="embeddings.create",
            dimension=self._dimension,
            normalized=True,
            max_input_tokens=self._MAX_INPUT_TOKENS,
        )

    @property
    def cache_identity(self) -> dict[str, str | None]:
        return {
            "provider": "openai",
            "model_id": self._model_id,
            "package_version": self._package_version,
            "model_revision": None,
            "model_sha256": None,
        }

    def set_cached_dimension(self, dimension: int) -> None:
        if dimension < 1 or (self._dimension is not None and self._dimension != dimension):
            raise EmbeddingProviderError(
                "EMBEDDING_DIMENSION_MISMATCH", "Cached OpenAI dimension is incompatible"
            )
        self._dimension = dimension

    def set_expected_dimension(self, dimension: int) -> None:
        self.set_cached_dimension(dimension)

    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def _check_text(self, text: str) -> None:
        token_count = self.count_tokens(text)
        if token_count > self._MAX_INPUT_TOKENS:
            raise EmbeddingInputError(
                "EMBEDDING_INPUT_TOO_LONG",
                f"Input exceeds token limit: {token_count} tokens; "
                f"maximum is {self._MAX_INPUT_TOKENS}",
            )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for text in texts:
            self._check_text(text)
        client = self._client
        if client is None:
            raise EmbeddingProviderError("EMBEDDING_API_FAILED", "OpenAI client is unavailable")
        try:
            response = client.embeddings.create(input=texts, model=self._model_id)
        except Exception as error:
            raise EmbeddingProviderError(
                "EMBEDDING_API_FAILED", "OpenAI embedding request failed"
            ) from error
        items = list(response.data)
        if len(items) != len(texts):
            raise EmbeddingProviderError(
                "EMBEDDING_COUNT_MISMATCH", "OpenAI returned an unexpected vector count"
            )
        ordered = sorted(items, key=lambda item: getattr(item, "index", items.index(item)))
        vectors: list[list[float]] = []
        for item in ordered:
            raw_vector = getattr(item, "embedding", None)
            if raw_vector is None:
                raise EmbeddingProviderError(
                    "EMBEDDING_INVALID", "OpenAI response omitted an embedding vector"
                )
            vector = _normalize_vector(raw_vector, self._dimension)
            if self._dimension is None:
                self._dimension = len(vector)
            vectors.append(vector)
        return vectors

    def embed_passages(self, passages: Sequence[CorpusPassage]) -> list[list[float]]:
        return self._embed([passage.embedding_text for passage in passages])

    def embed_query(self, query: str) -> list[float]:
        normalized = query.strip()
        if not normalized:
            raise EmbeddingInputError("QUERY_EMPTY", "Query must not be empty")
        vectors = self._embed([normalized])
        return vectors[0]


def create_embedding_provider(settings: RetrievalSettings) -> EmbeddingProvider:
    if settings.embedding_provider == "local":
        provider: EmbeddingProvider = FastEmbedProvider(settings)
    else:
        provider = OpenAIEmbeddingProvider(settings)
    return CachedEmbeddingProvider(provider, settings.embedding_cache_directory)


class CachedEmbeddingProvider:
    def __init__(self, provider: EmbeddingProvider, cache_directory: Path) -> None:
        self._provider = provider
        self._cache_directory = cache_directory

    @property
    def descriptor(self) -> EmbeddingDescriptor:
        return self._provider.descriptor

    @property
    def cache_identity(self) -> dict[str, str | None]:
        return self._provider.cache_identity

    @property
    def max_input_tokens(self) -> int:
        return self._provider.max_input_tokens

    def count_tokens(self, text: str) -> int:
        return self._provider.count_tokens(text)

    def set_expected_dimension(self, dimension: int) -> None:
        set_expected_dimension = getattr(self._provider, "set_expected_dimension", None)
        if callable(set_expected_dimension):
            set_expected_dimension(dimension)

    def embed_query(self, query: str) -> list[float]:
        return self._provider.embed_query(query)

    def _cache_key(self, passage: CorpusPassage) -> str:
        key_value = {
            "identity": self.cache_identity,
            "embedding_text_sha256": passage.embedding_text_sha256,
        }
        encoded = json.dumps(key_value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self._cache_directory / key[:2] / f"{key}.json"

    def _read_cached(self, passage: CorpusPassage, key: str) -> list[float] | None:
        path = self._cache_path(key)
        if not path.is_file():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if (
                entry.get("schema_version") != "1.0"
                or entry.get("cache_key") != key
                or entry.get("identity") != self.cache_identity
                or entry.get("embedding_text_sha256") != passage.embedding_text_sha256
            ):
                return None
            vector = [float(value) for value in entry["vector"]]
            dimension = int(entry["dimension"])
            vector_bytes = json.dumps(vector, separators=(",", ":")).encode("utf-8")
            if hashlib.sha256(vector_bytes).hexdigest() != entry.get("vector_sha256"):
                return None
            if len(vector) != dimension:
                return None
            set_cached_dimension = getattr(self._provider, "set_cached_dimension", None)
            if callable(set_cached_dimension):
                set_cached_dimension(dimension)
            descriptor = self._provider.descriptor
            if descriptor.dimension != dimension:
                return None
            return _normalize_vector(vector, dimension)
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            EmbeddingProviderError,
        ):
            return None

    def _write_cached(self, passage: CorpusPassage, key: str, vector: list[float]) -> None:
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        vector_bytes = json.dumps(vector, separators=(",", ":")).encode("utf-8")
        entry = {
            "schema_version": "1.0",
            "cache_key": key,
            "identity": self.cache_identity,
            "embedding_text_sha256": passage.embedding_text_sha256,
            "dimension": len(vector),
            "vector_sha256": hashlib.sha256(vector_bytes).hexdigest(),
            "vector": vector,
        }
        payload = (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def embed_passages(self, passages: Sequence[CorpusPassage]) -> list[list[float]]:
        if not passages:
            return []
        vectors: list[list[float] | None] = [None] * len(passages)
        misses: list[tuple[int, CorpusPassage, str]] = []
        for index, passage in enumerate(passages):
            key = self._cache_key(passage)
            cached = self._read_cached(passage, key)
            if cached is None:
                misses.append((index, passage, key))
            else:
                vectors[index] = cached
        if misses:
            computed = self._provider.embed_passages([passage for _, passage, _ in misses])
            if len(computed) != len(misses):
                raise EmbeddingProviderError(
                    "EMBEDDING_COUNT_MISMATCH",
                    "Embedding provider returned an unexpected vector count",
                )
            descriptor = self._provider.descriptor
            for (index, passage, key), raw_vector in zip(misses, computed, strict=True):
                vector = _normalize_vector(raw_vector, descriptor.dimension)
                vectors[index] = vector
                self._write_cached(passage, key, vector)
        if any(vector is None for vector in vectors):
            raise EmbeddingProviderError(
                "EMBEDDING_CACHE_INVALID", "Embedding cache did not produce a full batch"
            )
        return [vector for vector in vectors if vector is not None]
