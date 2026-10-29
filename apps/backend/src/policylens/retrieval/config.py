from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from policylens.retrieval.models import EmbeddingDescriptor
from policylens.settings import PROJECT_ROOT, AppSettings


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    embedding_provider: Literal["local", "openai"] = "local"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_embedding_model: str | None = None
    openai_api_key: SecretStr | None = None
    chroma_persist_directory: Path = Path("data/indexes/chroma")
    bm25_index_directory: Path = Path("data/indexes/bm25")
    active_index_pointer_path: Path = Path("data/indexes/active-index.json")
    index_manifest_path: Path = Path("data/manifests/retrieval-index-manifest.json")
    evaluation_manifest_path: Path = Path("data/manifests/retrieval-evaluation-manifest.json")
    model_cache_directory: Path = Path("models/fastembed")
    embedding_cache_directory: Path = Path("data/indexes/embedding-cache")
    max_candidates: int = Field(default=20, ge=1, le=100)
    max_top_k: int = Field(default=20, ge=1, le=20)
    final_context_chunks: int = Field(default=6, ge=1, le=20)
    reranker_enabled: bool = True
    reranker_model: str = Field(
        default="jinaai/jina-reranker-v1-tiny-en", min_length=1, max_length=300
    )
    reranker_candidate_count: int = Field(default=20, ge=1, le=20)
    reranker_batch_size: int = Field(default=16, ge=1, le=64)
    max_context_chars: int = Field(default=12000, ge=1000, le=50000)
    max_excerpt_chars: int = Field(default=500, ge=1, le=500)
    per_source_cap: int = Field(default=3, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    bm25_k1: float = Field(default=1.5, gt=0, le=10)
    bm25_b: float = Field(default=0.75, ge=0, le=1)
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    retrieval_run_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    retrieval_run_registry_capacity: int = Field(default=1000, ge=10, le=10000)
    allowed_permission_scopes: tuple[str, ...] = ("public",)

    @model_validator(mode="after")
    def validate_provider_settings(self) -> "RetrievalSettings":
        if self.embedding_provider == "local" and not self.local_embedding_model.strip():
            raise ValueError("LOCAL_EMBEDDING_MODEL is required for local embeddings")
        if self.embedding_provider == "openai":
            key = self.openai_api_key.get_secret_value().strip() if self.openai_api_key else ""
            if not key:
                raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
            if not self.openai_embedding_model or not self.openai_embedding_model.strip():
                raise ValueError("OPENAI_EMBEDDING_MODEL is required for OpenAI embeddings")
        return self

    @classmethod
    def from_app_settings(cls, settings: AppSettings) -> "RetrievalSettings":
        return cls(
            embedding_provider=settings.embedding_provider,
            local_embedding_model=settings.local_embedding_model or "BAAI/bge-small-en-v1.5",
            openai_embedding_model=settings.openai_embedding_model,
            openai_api_key=settings.openai_api_key,
            chroma_persist_directory=settings.chroma_persist_directory,
            bm25_index_directory=settings.bm25_index_directory,
            max_candidates=settings.max_retrieval_candidates,
            final_context_chunks=settings.final_context_chunks,
            reranker_enabled=settings.reranker_enabled,
            reranker_model=settings.reranker_model,
            reranker_candidate_count=settings.reranker_candidate_count,
            reranker_batch_size=settings.reranker_batch_size,
        )

    def matches_embedding_descriptor(self, descriptor: EmbeddingDescriptor) -> bool:
        model_id = (
            self.local_embedding_model
            if self.embedding_provider == "local"
            else self.openai_embedding_model
        )
        return descriptor.provider == self.embedding_provider and descriptor.model_id == model_id
