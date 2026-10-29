from __future__ import annotations

import hashlib
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.models import (
    BlockLocation,
    CorpusPassage,
    EmbeddingDescriptor,
    RetrievalFilters,
    RetrievalRequest,
    RetrievalRerankingDiagnostics,
    RetrievalRun,
)
from policylens.retrieval.reranking import RerankerError
from policylens.retrieval.search import IndexedPassage, RetrievalError, RetrievalService

HASH = "a" * 64


def _passage(
    marker: str,
    *,
    source_id: str = "source-one",
    text: str | None = None,
    page_number: int = 1,
    block_id: str | None = None,
    permission_scope: str = "public",
    allowed_usage: tuple[str, ...] = ("retrieval",),
    country: str = "IND",
    year: int = 2025,
) -> IndexedPassage:
    passage_text = text or f"Evidence passage {marker} about India youth employment."
    return IndexedPassage(
        passage_id="sha256:" + marker * 64,
        source_id=source_id,
        document_id=f"doc:{source_id}",
        title=f"Title {source_id}",
        publisher="World Bank",
        source_uri="https://example.test/source",
        text=passage_text,
        text_sha256=hashlib.sha256(passage_text.encode("utf-8")).hexdigest(),
        source_content_sha256=HASH,
        locations=(
            BlockLocation(
                page_number=page_number,
                block_id=block_id or f"block-{marker}",
                start_char=0,
                end_char=len(passage_text),
            ),
        ),
        row_key=None,
        section_path=("Findings",),
        licence="CC BY 4.0",
        permission_scope=permission_scope,
        allowed_usage=allowed_usage,
        country_iso3=country,
        year=year,
        indicator_id="SL.UEM.1524.ZS",
    )


class FakeVectorCollection:
    def __init__(self, ids: list[str], distances: list[float]) -> None:
        self.ids = ids
        self.distances = distances
        self.where: dict[str, object] | None = None
        self.last_n_results: int | None = None

    def query(self, **kwargs: object) -> dict[str, Any]:
        self.where = kwargs.get("where")  # type: ignore[assignment]
        self.last_n_results = kwargs.get("n_results")  # type: ignore[assignment]
        return {"ids": [self.ids], "distances": [self.distances]}


class FakeBM25:
    def __init__(self, ids: list[str], scores: list[float]) -> None:
        self.ids = ids
        self.scores = scores
        self.last_k: int | None = None

    def retrieve(
        self, _query_tokens: object, *, corpus: Sequence[str], k: int, **_kwargs: object
    ) -> SimpleNamespace:
        assert set(self.ids).issubset(set(corpus))
        self.last_k = k
        return SimpleNamespace(
            documents=[self.ids[:k]],
            scores=[self.scores[:k]],
        )


class FakeEmbedder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.descriptor = EmbeddingDescriptor(
            provider="local",
            model_id="fake-embedder",
            package_version="test",
            dimension=2,
            normalized=True,
            max_input_tokens=512,
        )
        self.cache_identity = {
            "provider": "local",
            "model_id": "fake-embedder",
            "package_version": "test",
            "model_revision": None,
            "model_sha256": None,
        }

    @property
    def max_input_tokens(self) -> int:
        return 512

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def embed_passages(self, passages: Sequence[CorpusPassage]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in passages]

    def embed_query(self, _query: str) -> list[float]:
        if self.fail:
            raise RuntimeError("provider unavailable")
        return [1.0, 0.0]


class FakeRunRegistry:
    def __init__(self) -> None:
        self.runs: list[RetrievalRun] = []

    def register(self, run: RetrievalRun) -> None:
        self.runs.append(run)


class FakeReranker:
    model_id = "test-cross-encoder"

    def __init__(self, scores: list[float] | Exception) -> None:
        self.scores = scores
        self.query: str | None = None
        self.documents: list[str] = []

    def rerank(self, query: str, documents: Sequence[str]) -> tuple[float, ...]:
        self.query = query
        self.documents = list(documents)
        if isinstance(self.scores, Exception):
            raise self.scores
        return tuple(self.scores)


def _service(
    passages: list[IndexedPassage],
    *,
    bm25_order: list[str],
    dense_order: list[str],
    fail_query: bool = False,
    max_candidates: int = 20,
    reranker: FakeReranker | None = None,
    reranker_candidate_count: int = 20,
) -> tuple[RetrievalService, FakeVectorCollection, FakeRunRegistry]:
    ids = [passage.passage_id for passage in passages]
    dense_ids = [passage_id for passage_id in dense_order if passage_id in ids]
    vector = FakeVectorCollection(dense_ids, [0.1 + 0.1 * index for index in range(len(dense_ids))])
    bm25_ids = [passage_id for passage_id in bm25_order if passage_id in ids]
    bm25 = FakeBM25(bm25_ids, [float(len(bm25_ids) - index) for index in range(len(bm25_ids))])
    registry = FakeRunRegistry()
    service = RetrievalService(
        settings=RetrievalSettings(
            max_candidates=max_candidates,
            final_context_chunks=6,
            per_source_cap=3,
            reranker_enabled=reranker is not None,
            reranker_candidate_count=reranker_candidate_count,
        ),
        index_version=HASH,
        passages=passages,
        vector_collection=vector,
        bm25_retriever=bm25,
        bm25_ids=ids,
        embedder=FakeEmbedder(fail=fail_query),
        run_registry=registry,
        reranker=reranker,
    )
    return service, vector, registry


def test_hybrid_search_filters_permissions_before_return_and_fuses_deterministically() -> None:
    first = _passage("a")
    restricted = _passage("b", permission_scope="restricted")
    other_country = _passage("c", source_id="source-three", country="MYS")
    second_source = _passage("d", source_id="source-two")
    not_retrieval = _passage("e", source_id="source-four", allowed_usage=("evaluation",))
    passages = [first, restricted, other_country, second_source, not_retrieval]
    service, vector, registry = _service(
        passages,
        bm25_order=[
            second_source.passage_id,
            restricted.passage_id,
            first.passage_id,
            other_country.passage_id,
            not_retrieval.passage_id,
        ],
        dense_order=[
            first.passage_id,
            restricted.passage_id,
            second_source.passage_id,
            other_country.passage_id,
            not_retrieval.passage_id,
        ],
    )
    request = RetrievalRequest(
        query="youth employment in India",
        mode="hybrid",
        top_k=5,
        filters=RetrievalFilters(country_iso3=("IND",), years=(2025,)),
    )

    run = service.search(request)
    repeated = service.search(request)

    evidence_ids = [evidence.passage_id for evidence in run.evidence]
    assert evidence_ids == sorted([first.passage_id, second_source.passage_id])
    assert [evidence.passage_id for evidence in repeated.evidence] == evidence_ids
    assert all("restricted" not in evidence.text for evidence in run.evidence)
    assert "Evidence passage b" not in run.context
    assert run.status == "found"
    assert registry.runs[-1].run_id == repeated.run_id
    assert vector.where is not None
    assert "allowed_usage" in str(vector.where)
    assert "country_iso3" in str(vector.where)


def test_mcp_passage_iterator_is_sorted_and_filters_permissions() -> None:
    later = _passage("b", source_id="source-two")
    earlier = _passage("a", source_id="source-one")
    restricted = _passage("c", permission_scope="restricted")
    not_retrieval = _passage("d", allowed_usage=("evaluation",))
    service, _, _ = _service(
        [later, restricted, not_retrieval, earlier],
        bm25_order=[],
        dense_order=[],
    )

    passages = service.iter_passages_for_mcp()

    assert [passage.passage_id for passage in passages] == sorted(
        [earlier.passage_id, later.passage_id]
    )


def test_search_returns_explicit_no_results_and_separates_embedding_failure() -> None:
    passage = _passage("a")
    service, _, _ = _service(
        [passage],
        bm25_order=[],
        dense_order=[],
    )
    empty = service.search(
        RetrievalRequest(
            query="question",
            mode="hybrid",
            filters=RetrievalFilters(country_iso3=("SGP",)),
        )
    )

    assert empty.status == "no_results"
    assert empty.evidence == ()

    failed, _, _ = _service([passage], bm25_order=[], dense_order=[], fail_query=True)
    with pytest.raises(RetrievalError) as error:
        failed.search(RetrievalRequest(query="question", mode="dense"))
    assert error.value.code == "EMBEDDING_UNAVAILABLE"


def test_bm25_and_dense_candidate_pools_respect_configured_bound() -> None:
    passages = [
        _passage("a"),
        _passage("b", source_id="source-two"),
        _passage("c", source_id="source-three"),
    ]
    service, vector, _ = _service(
        passages,
        bm25_order=[item.passage_id for item in passages],
        dense_order=[item.passage_id for item in passages],
        max_candidates=2,
    )

    service.search(RetrievalRequest(query="youth employment", mode="bm25"))
    assert service._bm25_retriever.last_k == 2
    service.search(RetrievalRequest(query="youth employment", mode="dense"))
    assert vector.last_n_results == 2


def test_hybrid_reranking_reorders_only_bounded_permitted_candidates() -> None:
    first = _passage("a")
    second = _passage("b", source_id="source-two")
    third = _passage("c", source_id="source-three")
    restricted = _passage("d", permission_scope="restricted")
    reranker = FakeReranker([0.1, 0.9])
    service, _, _ = _service(
        [first, second, third, restricted],
        bm25_order=[
            restricted.passage_id,
            first.passage_id,
            second.passage_id,
            third.passage_id,
        ],
        dense_order=[
            restricted.passage_id,
            first.passage_id,
            second.passage_id,
            third.passage_id,
        ],
        max_candidates=4,
        reranker=reranker,
        reranker_candidate_count=2,
    )

    run = service.search(RetrievalRequest(query="youth employment", mode="hybrid", top_k=3))

    assert [item.passage_id for item in run.evidence] == [
        second.passage_id,
        first.passage_id,
        third.passage_id,
    ]
    assert reranker.query == "youth employment"
    assert len(reranker.documents) == 2
    assert all("Evidence passage d" not in text for text in reranker.documents)
    assert run.evidence[0].reranker_score == 0.9
    assert run.evidence[1].reranker_score == 0.1
    assert run.reranking == RetrievalRerankingDiagnostics(
        method="cross_encoder",
        status="completed",
        model_id="test-cross-encoder",
        candidate_count=2,
        duration_ms=run.reranking.duration_ms if run.reranking else 0,
    )


def test_single_source_search_backfills_beyond_per_source_cap() -> None:
    passages = [_passage(marker, page_number=index + 1) for index, marker in enumerate("abcdef")]
    order = [passage.passage_id for passage in passages]
    service, _vector, _registry = _service(passages, bm25_order=order, dense_order=order)

    run = service.search(RetrievalRequest(query="question", mode="hybrid", top_k=6))

    assert [item.passage_id for item in run.evidence] == order


def test_reranker_receives_adjacent_table_caption_with_table_rows() -> None:
    caption = _passage(
        "a",
        text="Table 8 - Placement and employment rates by state",
        page_number=16,
        block_id="b0132",
    )
    rows = _passage(
        "b",
        text=(
            "Assam Madhya Pradesh Rajasthan Odisha Andhra Pradesh\n"
            "Initial Placement Rate 26 32 20 12 50\n"
            "Employment Rate 1-2 years later 42 28 13 18 55"
        ),
        page_number=16,
        block_id="b0133",
    )
    reranker = FakeReranker([0.9, 0.8])
    service, _, _ = _service(
        [caption, rows],
        bm25_order=[caption.passage_id, rows.passage_id],
        dense_order=[caption.passage_id, rows.passage_id],
        reranker=reranker,
    )

    service.search(RetrievalRequest(query="placement rates by state", mode="hybrid"))

    assert any(
        "Table caption: Table 8 - Placement and employment rates by state" in document
        and "Assam Madhya Pradesh" in document
        for document in reranker.documents
    )


def test_reranker_failure_is_reported_and_keeps_hybrid_order() -> None:
    first = _passage("a")
    second = _passage("b", source_id="source-two")
    reranker = FakeReranker(RerankerError("RERANKER_UNAVAILABLE", "not available"))
    service, _, _ = _service(
        [first, second],
        bm25_order=[first.passage_id, second.passage_id],
        dense_order=[first.passage_id, second.passage_id],
        reranker=reranker,
    )

    run = service.search(RetrievalRequest(query="youth employment", mode="hybrid"))

    assert [item.passage_id for item in run.evidence] == [first.passage_id, second.passage_id]
    assert run.reranking is not None
    assert run.reranking.status == "failed"
    assert run.reranking.error_code == "RERANKER_UNAVAILABLE"
    assert all(item.reranker_score is None for item in run.evidence)


def test_reranker_is_not_applied_to_non_hybrid_modes() -> None:
    passage = _passage("a")
    reranker = FakeReranker([1.0])
    service, _, _ = _service(
        [passage],
        bm25_order=[passage.passage_id],
        dense_order=[passage.passage_id],
        reranker=reranker,
    )

    run = service.search(RetrievalRequest(query="youth employment", mode="bm25"))

    assert run.reranking is None
    assert reranker.documents == []
