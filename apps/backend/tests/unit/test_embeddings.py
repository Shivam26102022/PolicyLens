from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import (
    CachedEmbeddingProvider,
    EmbeddingInputError,
    FastEmbedProvider,
    OpenAIEmbeddingProvider,
)
from policylens.retrieval.models import CorpusPassage, EmbeddingDescriptor


class FakeFastEmbed:
    embedding_size = 3

    def token_count(self, texts: str | Iterable[str]) -> int:
        values = [texts] if isinstance(texts, str) else list(texts)
        return sum(len(text.split()) for text in values)

    def passage_embed(self, texts: Iterable[str]) -> Iterable[list[float]]:
        for _ in texts:
            yield [3.0, 4.0, 0.0]

    def query_embed(self, text: str) -> Iterable[list[float]]:
        yield [0.0, 5.0, 0.0]


def _passage(embedding_text: str = "Report title findings unemployment") -> CorpusPassage:
    from policylens.retrieval.models import BlockLocation, passage_text_sha256

    text = "Findings unemployment"
    return CorpusPassage(
        passage_id="sha256:" + "a" * 64,
        source_id="report",
        document_id="doc:report",
        title="Report title",
        publisher="World Bank",
        source_uri="https://example.test/report",
        text=text,
        embedding_text=embedding_text,
        text_sha256=passage_text_sha256(text),
        embedding_text_sha256=passage_text_sha256(embedding_text),
        source_content_sha256="b" * 64,
        chunker_version="structure-aware-v1",
        locations=(BlockLocation(page_number=1, block_id="b1", start_char=0, end_char=22),),
        section_path=("Findings",),
        token_count=4,
        licence="CC BY 4.0",
        sensitivity="public",
        permission_scope="public",
        allowed_usage=("retrieval",),
    )


def test_fastembed_provider_uses_passage_query_apis_and_normalizes_vectors() -> None:
    provider = FastEmbedProvider(
        RetrievalSettings(),
        model=FakeFastEmbed(),
        package_version="0.9.1-test",
    )

    passage_vectors = provider.embed_passages((_passage(),))
    query_vector = provider.embed_query("youth unemployment")

    assert passage_vectors == [[0.6, 0.8, 0.0]]
    assert query_vector == [0.0, 1.0, 0.0]
    assert provider.descriptor.dimension == 3
    assert provider.descriptor.provider == "local"


def test_fastembed_provider_rejects_over_limit_without_truncation() -> None:
    provider = FastEmbedProvider(
        RetrievalSettings(),
        model=FakeFastEmbed(),
        package_version="0.9.1-test",
        max_input_tokens=3,
    )

    with pytest.raises(EmbeddingInputError, match="token limit"):
        provider.embed_passages((_passage(),))


def test_openai_provider_uses_explicit_model_and_validates_dimension() -> None:
    requests: list[dict[str, object]] = []

    class FakeEmbeddings:
        def create(self, **kwargs: object) -> SimpleNamespace:
            requests.append(kwargs)
            inputs = kwargs["input"]
            assert isinstance(inputs, list)
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[3.0, 4.0, 0.0]) for _ in inputs]
            )

    client = SimpleNamespace(embeddings=FakeEmbeddings())
    provider = OpenAIEmbeddingProvider(
        RetrievalSettings(
            embedding_provider="openai",
            openai_api_key=SecretStr("test-key"),
            openai_embedding_model="text-embedding-3-small",
        ),
        client=client,
        package_version="3.37.0-test",
    )

    vectors = provider.embed_passages((_passage(),))

    assert vectors == [[0.6, 0.8, 0.0]]
    assert requests == [
        {"input": ["Report title findings unemployment"], "model": "text-embedding-3-small"}
    ]
    assert provider.descriptor.dimension == 3


class CountingProvider:
    def __init__(self, model_id: str = "cache-model-v1") -> None:
        self.model_id = model_id
        self.passage_calls = 0
        self.query_calls = 0
        self.descriptor = EmbeddingDescriptor(
            provider="local",
            model_id=model_id,
            package_version="cache-test-v1",
            dimension=3,
            normalized=True,
            max_input_tokens=512,
        )
        self.cache_identity = {
            "provider": "local",
            "model_id": model_id,
            "package_version": "cache-test-v1",
            "model_revision": None,
            "model_sha256": None,
        }

    @property
    def max_input_tokens(self) -> int:
        return 512

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def embed_passages(self, passages: Sequence[CorpusPassage]) -> list[list[float]]:
        self.passage_calls += 1
        return [[0.0, 1.0, 0.0] for _ in passages]

    def embed_query(self, query: str) -> list[float]:
        self.query_calls += 1
        return [1.0, 0.0, 0.0]


def test_cached_provider_reuses_model_scoped_passage_vectors(tmp_path: Path) -> None:
    passage = _passage()
    first_base = CountingProvider()
    first = CachedEmbeddingProvider(first_base, tmp_path)
    first_vector = first.embed_passages((passage,))

    second_base = CountingProvider()
    second = CachedEmbeddingProvider(second_base, tmp_path)
    second_vector = second.embed_passages((passage,))
    second.embed_query("youth unemployment")

    assert first_vector == second_vector == [[0.0, 1.0, 0.0]]
    assert first_base.passage_calls == 1
    assert second_base.passage_calls == 0
    assert second_base.query_calls == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1

    changed_model = CachedEmbeddingProvider(CountingProvider("cache-model-v2"), tmp_path)
    changed_model.embed_passages((passage,))
    assert len(list(tmp_path.rglob("*.json"))) == 2
