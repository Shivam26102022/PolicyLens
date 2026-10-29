import os
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FRONTEND_ORIGIN = TypeAdapter(AnyHttpUrl).validate_python("http://localhost:5173")
DEFAULT_MLX_BASE_URL = TypeAdapter(AnyHttpUrl).validate_python("http://127.0.0.1:8080/v1")
MAX_AGENT_OUTPUT_TOKENS_LIMIT = 8000


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: Literal["PolicyLens"] = "PolicyLens"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    frontend_origin: AnyHttpUrl = DEFAULT_FRONTEND_ORIGIN
    model_provider: Literal["openai", "mlx"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_deployment_model: str | None = None
    openai_base_url: AnyHttpUrl | None = None
    openai_use_responses_api: bool = False
    openai_embedding_model: str | None = None
    mlx_base_url: AnyHttpUrl = DEFAULT_MLX_BASE_URL
    mlx_model: str | None = None

    embedding_provider: Literal["local", "openai"] = "local"
    local_embedding_model: str | None = None

    chroma_persist_directory: Path = Path("./data/indexes/chroma")
    chroma_collection_prefix: str = "policylens"
    bm25_index_directory: Path = Path("./data/indexes/bm25")
    active_corpus_version: str = "v1"

    mcp_transport: Literal["stdio"] = "stdio"
    mcp_server_command: str = "uv run --package policylens-mcp python -m policylens_mcp"
    mcp_server_url: AnyHttpUrl | None = None
    mcp_timeout_seconds: int = Field(default=15, ge=1, le=120)

    max_agent_turns: int = Field(default=6, ge=1, le=50)
    max_tool_calls: int = Field(default=8, ge=1, le=100)
    max_tool_calls_per_tool: int = Field(default=4, ge=1, le=20)
    max_tool_retries: int = Field(default=1, ge=0, le=3)
    max_agent_output_tokens: int = Field(default=1200, ge=1, le=MAX_AGENT_OUTPUT_TOKENS_LIMIT)
    max_retrieval_candidates: int = Field(default=20, ge=1, le=100)
    final_context_chunks: int = Field(default=6, ge=1, le=20)
    reranker_enabled: bool = True
    reranker_model: str = Field(
        default="jinaai/jina-reranker-v1-tiny-en",
        min_length=1,
        max_length=300,
    )
    reranker_candidate_count: int = Field(default=20, ge=1, le=20)
    reranker_batch_size: int = Field(default=16, ge=1, le=64)
    request_timeout_seconds: int = Field(default=90, ge=1, le=300)

    @field_validator("model_provider", mode="before")
    @classmethod
    def normalize_model_provider(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        return "mlx" if normalized == "local" else normalized

    @field_validator("embedding_provider", mode="before")
    @classmethod
    def normalize_embedding_provider(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @property
    def effective_openai_model(self) -> str | None:
        deployment_model = (
            self.openai_deployment_model.strip() if self.openai_deployment_model else ""
        )
        standard_model = self.openai_model.strip() if self.openai_model else ""
        return deployment_model or standard_model or None

    @model_validator(mode="after")
    def validate_provider_requirements(self) -> "AppSettings":
        missing: list[str] = []
        api_key = self.openai_api_key.get_secret_value().strip() if self.openai_api_key else ""
        mlx_host = (self.mlx_base_url.host or "").strip("[]").lower()

        if self.model_provider == "openai":
            if not api_key:
                missing.append("OPENAI_API_KEY")
            if not self.effective_openai_model:
                missing.append("OPENAI_MODEL")
        elif not (self.mlx_model or "").strip():
            missing.append("MLX_MODEL")
        elif self.mlx_base_url.scheme != "http" or mlx_host not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("MLX_BASE_URL must use HTTP and a loopback host")
        elif self.mlx_base_url.username or self.mlx_base_url.password:
            raise ValueError("MLX_BASE_URL must not include credentials")
        elif self.mlx_base_url.query or self.mlx_base_url.fragment:
            raise ValueError("MLX_BASE_URL must not include a query or fragment")
        elif self.mlx_base_url.path not in {"", "/", "/v1"}:
            raise ValueError("MLX_BASE_URL path must be the API root or /v1")

        if self.embedding_provider == "openai":
            if not api_key and "OPENAI_API_KEY" not in missing:
                missing.append("OPENAI_API_KEY")
            if not self.openai_embedding_model or not self.openai_embedding_model.strip():
                missing.append("OPENAI_EMBEDDING_MODEL")

        # Serverless deployments should start even before provider secrets are added.
        # Provider construction still rejects missing configuration at request time.
        if missing and not os.environ.get("VERCEL"):
            fields = ", ".join(missing)
            raise ValueError(
                f"Required configuration is missing for the selected providers: {fields}"
            )

        return self


def get_settings() -> AppSettings:
    return AppSettings()


class FrontendOriginSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    frontend_origin: AnyHttpUrl = DEFAULT_FRONTEND_ORIGIN


def get_frontend_origin() -> str:
    return str(FrontendOriginSettings().frontend_origin).rstrip("/")
