from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.models import EmbeddingDescriptor
from policylens.settings import AppSettings


def test_local_retrieval_settings_need_no_generation_credentials() -> None:
    settings = RetrievalSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.embedding_provider == "local"
    assert settings.local_embedding_model == "BAAI/bge-small-en-v1.5"
    assert settings.openai_api_key is None
    assert settings.reranker_enabled is True
    assert settings.reranker_model == "jinaai/jina-reranker-v1-tiny-en"
    assert settings.reranker_candidate_count == 20


def test_openai_embeddings_require_explicit_key_and_model() -> None:
    with pytest.raises(ValidationError):
        RetrievalSettings(_env_file=None, embedding_provider="openai")  # type: ignore[call-arg]

    settings = RetrievalSettings(
        _env_file=None,  # type: ignore[call-arg]
        embedding_provider="openai",
        openai_api_key=SecretStr("test-key"),
        openai_embedding_model="text-embedding-3-small",
    )

    assert settings.embedding_provider == "openai"


def test_app_settings_map_without_coupling_local_embedding_to_generation() -> None:
    app_settings = AppSettings(  # type: ignore[call-arg]
        _env_file=None,
        model_provider="mlx",
        mlx_model="local-generation-model",
    )

    retrieval_settings = RetrievalSettings.from_app_settings(app_settings)

    assert retrieval_settings.embedding_provider == "local"
    assert retrieval_settings.openai_api_key is None
    assert retrieval_settings.reranker_enabled is True
    assert retrieval_settings.reranker_model == "jinaai/jina-reranker-v1-tiny-en"


def test_retrieval_settings_detect_provider_or_model_mismatch() -> None:
    settings = RetrievalSettings(_env_file=None)  # type: ignore[call-arg]
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="BAAI/bge-small-en-v1.5",
        package_version="0.9.1",
        dimension=384,
        normalized=True,
        max_input_tokens=512,
    )

    assert settings.matches_embedding_descriptor(descriptor)
    assert not settings.matches_embedding_descriptor(
        descriptor.model_copy(update={"model_id": "different-model"})
    )
