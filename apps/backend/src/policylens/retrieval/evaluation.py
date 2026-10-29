from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import bm25s
from pydantic import BaseModel, ConfigDict, Field, model_validator

from policylens.retrieval.chunking import (
    fixed_chunker_config,
    structure_aware_chunker_config,
)
from policylens.retrieval.citations import RetrievalRunRegistry
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import EmbeddingProvider
from policylens.retrieval.indexing import (
    BM25_TOKEN_PATTERN,
    _load_passages,
    load_current_sources,
)
from policylens.retrieval.models import (
    ChunkerConfig,
    CorpusPassage,
    RetrievalFilters,
    RetrievalMode,
    RetrievalRequest,
    StructuredRowKey,
)
from policylens.retrieval.reranking import Reranker
from policylens.retrieval.search import IndexedPassage, RetrievalService


class EvaluationCaseError(ValueError):
    pass


class EvidenceAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    marker: str | None = Field(default=None, min_length=1, max_length=300)
    row_key: StructuredRowKey | None = None

    @model_validator(mode="after")
    def require_location_anchor(self) -> EvidenceAnchor:
        row_anchor = self.row_key is not None
        page_anchor = self.page_number is not None and self.marker is not None
        if row_anchor == page_anchor:
            raise ValueError("anchor must contain either a row key or page number and text marker")
        return self


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=2000)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    expected_anchors: tuple[EvidenceAnchor, ...] = Field(min_length=1, max_length=20)


class RetrievalCaseSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    set_id: str
    lineage: str
    cases: tuple[RetrievalCase, ...] = Field(min_length=1, max_length=100)


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    expected_passage_groups: tuple[tuple[str, ...], ...]
    retrieved_passage_ids: tuple[str, ...]
    latency_ms: float = Field(ge=0)
    citation_complete: bool


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def load_retrieval_cases(path: Path) -> RetrievalCaseSet:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return RetrievalCaseSet.model_validate(value)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise EvaluationCaseError("Retrieval case set is missing or invalid") from error


def map_anchor_to_passages(
    anchor: EvidenceAnchor,
    passages: Sequence[CorpusPassage],
) -> tuple[str, ...]:
    matching: list[str] = []
    marker = " ".join(anchor.marker.casefold().split()) if anchor.marker else None
    for passage in passages:
        if passage.source_id != anchor.source_id:
            continue
        if anchor.row_key is not None:
            if passage.row_key == anchor.row_key:
                matching.append(passage.passage_id)
            continue
        if anchor.page_number is None or marker is None:
            continue
        normalized_text = " ".join(passage.text.casefold().split())
        if (
            any(location.page_number == anchor.page_number for location in passage.locations)
            and marker in normalized_text
        ):
            matching.append(passage.passage_id)
    return tuple(sorted(matching))


def compute_retrieval_metrics(
    cases: Sequence[EvaluationCaseResult],
    *,
    k: int = 5,
) -> dict[str, float | int | str]:
    if not cases:
        raise ValueError("at least one retrieval case is required")
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg_values: list[float] = []
    empty_count = 0
    latencies: list[float] = []
    citation_values: list[float] = []
    for case in cases:
        retrieved = case.retrieved_passage_ids[:k]
        if not retrieved:
            empty_count += 1
        expected = case.expected_passage_groups
        hits = [any(passage_id in retrieved for passage_id in group) for group in expected]
        recall_values.append(sum(hits) / len(expected) if expected else 0.0)
        remaining_groups = list(range(len(expected)))
        dcg = 0.0
        for rank, passage_id in enumerate(retrieved, 1):
            matching_group = next(
                (index for index in remaining_groups if passage_id in expected[index]),
                None,
            )
            if matching_group is not None:
                dcg += 1.0 / math.log2(rank + 1)
                remaining_groups.remove(matching_group)
        ideal_hits = min(len(expected), k)
        ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        ndcg_values.append(dcg / ideal_dcg if ideal_dcg else 0.0)
        first_relevant = next(
            (
                rank
                for rank, passage_id in enumerate(retrieved, 1)
                if any(passage_id in group for group in expected)
            ),
            None,
        )
        reciprocal_ranks.append(1.0 / first_relevant if first_relevant is not None else 0.0)
        latencies.append(case.latency_ms)
        citation_values.append(1.0 if case.citation_complete else 0.0)
    count = len(cases)
    return {
        "case_count": count,
        "recall_at_k": sum(recall_values) / count,
        "ndcg_at_k": sum(ndcg_values) / count,
        "mrr": sum(reciprocal_ranks) / count,
        "empty_result_rate": empty_count / count,
        "mean_latency_ms": sum(latencies) / count,
        "citation_completeness": sum(citation_values) / count,
        "groundedness": "not_measured",
    }


class _MemoryVectorCollection:
    def __init__(
        self, passages: Sequence[CorpusPassage], vectors: Sequence[Sequence[float]]
    ) -> None:
        if len(passages) != len(vectors):
            raise ValueError("passage/vector counts differ")
        self._records = [
            (passage, tuple(float(value) for value in vector))
            for passage, vector in zip(passages, vectors, strict=True)
        ]

    @staticmethod
    def _matches(metadata: dict[str, Any], where: dict[str, Any]) -> bool:
        for condition in where.get("$and", []):
            for key, expected in condition.items():
                value = metadata.get(key)
                if isinstance(expected, dict) and "$contains" in expected:
                    if not isinstance(value, list) or expected["$contains"] not in value:
                        return False
                elif isinstance(expected, dict) and "$in" in expected:
                    if value not in expected["$in"]:
                        return False
                elif value != expected:
                    return False
        return True

    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        where: dict[str, Any],
        **_kwargs: Any,
    ) -> dict[str, list[list[Any]]]:
        query = tuple(float(value) for value in query_embeddings[0])
        matches: list[tuple[str, float]] = []
        for passage, vector in self._records:
            metadata = {
                "source_id": passage.source_id,
                "permission_scope": passage.sensitivity,
                "allowed_usage": list(passage.allowed_usage),
                "country_iso3": passage.country_iso3,
                "year": passage.year,
                "indicator_id": passage.indicator_id,
            }
            if not self._matches(metadata, where):
                continue
            similarity = sum(left * right for left, right in zip(query, vector, strict=True))
            matches.append((passage.passage_id, 1.0 - similarity))
        matches.sort(key=lambda item: (item[1], item[0]))
        results = matches[:n_results]
        return {
            "ids": [[item[0] for item in results]],
            "distances": [[item[1] for item in results]],
        }


def _indexed_passage(passage: CorpusPassage) -> IndexedPassage:
    return IndexedPassage(
        passage_id=passage.passage_id,
        source_id=passage.source_id,
        document_id=passage.document_id,
        title=passage.title,
        publisher=passage.publisher,
        source_uri=passage.source_uri,
        text=passage.text,
        text_sha256=passage.text_sha256,
        source_content_sha256=passage.source_content_sha256,
        locations=passage.locations,
        row_key=passage.row_key,
        section_path=passage.section_path,
        licence=passage.licence,
        permission_scope=passage.permission_scope,
        allowed_usage=passage.allowed_usage,
        country_iso3=passage.country_iso3,
        year=passage.year,
        indicator_id=passage.indicator_id,
    )


def _build_bm25(
    passages: Sequence[CorpusPassage], settings: RetrievalSettings
) -> tuple[Any, list[str]]:
    passage_ids = [passage.passage_id for passage in passages]
    retriever = bm25s.BM25(
        corpus=passage_ids,
        k1=settings.bm25_k1,
        b=settings.bm25_b,
        method="lucene",
    )
    tokenized = bm25s.tokenize(
        [passage.text for passage in passages],
        lower=True,
        stopwords=[],
        token_pattern=BM25_TOKEN_PATTERN,
        return_ids=True,
        show_progress=False,
    )
    retriever.index(tokenized, show_progress=False)
    return retriever, passage_ids


def evaluate_retrieval(
    project_root: Path,
    settings: RetrievalSettings,
    embedder: EmbeddingProvider,
    cases: RetrievalCaseSet,
    chunkers: Sequence[ChunkerConfig] | None = None,
    modes: Sequence[RetrievalMode] = ("bm25", "dense", "hybrid"),
    reranker: Reranker | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    sources = load_current_sources(root)
    chunker_configs = tuple(
        chunkers
        or (
            fixed_chunker_config(),
            structure_aware_chunker_config(target_tokens=450),
            structure_aware_chunker_config(target_tokens=250),
        )
    )
    results: dict[str, Any] = {
        "schema_version": "1.0",
        "set_id": cases.set_id,
        "case_lineage": cases.lineage,
        "dense_backend": (
            "in-memory exact cosine over normalized FastEmbed/OpenAI vectors; "
            "production retrieval uses Chroma"
        ),
        "groundedness": "not_measured",
        "top_k": settings.final_context_chunks,
        "reranker": {
            "enabled": reranker is not None and settings.reranker_enabled,
            "model_id": reranker.model_id if reranker is not None else None,
            "candidate_count": (
                settings.reranker_candidate_count
                if reranker is not None and settings.reranker_enabled
                else None
            ),
        },
        "configurations": [],
    }
    for chunker in chunker_configs:
        passages, inputs = _load_passages(root, sources, chunker, embedder)
        vectors: list[list[float]] = []
        for start in range(0, len(passages), settings.embedding_batch_size):
            vectors.extend(
                embedder.embed_passages(passages[start : start + settings.embedding_batch_size])
            )
        vector_store = _MemoryVectorCollection(passages, vectors)
        bm25, bm25_ids = _build_bm25(passages, settings)
        embedding_descriptor = embedder.descriptor
        bm25_config = {
            "method": "lucene",
            "k1": settings.bm25_k1,
            "b": settings.bm25_b,
            "token_pattern": BM25_TOKEN_PATTERN,
            "stopwords": [],
            "stemming": None,
        }
        input_records = [
            item.model_dump(mode="json") for item in sorted(inputs, key=lambda item: item.source_id)
        ]
        index_version = _fingerprint(
            {
                "schema_version": "evaluation-index-v1",
                "inputs": input_records,
                "chunker": chunker.model_dump(mode="json"),
                "embedding": embedding_descriptor.model_dump(mode="json"),
                "bm25": bm25_config,
            }
        )
        indexed_passages = [_indexed_passage(passage) for passage in passages]
        service = RetrievalService(
            settings=settings,
            index_version=index_version,
            passages=indexed_passages,
            vector_collection=vector_store,
            bm25_retriever=bm25,
            bm25_ids=bm25_ids,
            embedder=embedder,
            run_registry=RetrievalRunRegistry(),
        )
        reranked_service = (
            RetrievalService(
                settings=settings,
                index_version=index_version,
                passages=indexed_passages,
                vector_collection=vector_store,
                bm25_retriever=bm25,
                bm25_ids=bm25_ids,
                embedder=embedder,
                run_registry=RetrievalRunRegistry(),
                reranker=reranker,
            )
            if reranker is not None and settings.reranker_enabled
            else None
        )
        expected_by_case: dict[str, tuple[tuple[str, ...], ...]] = {}
        for case in cases.cases:
            groups = tuple(
                map_anchor_to_passages(anchor, passages) for anchor in case.expected_anchors
            )
            if any(not group for group in groups):
                raise EvaluationCaseError(
                    f"Case {case.case_id} has an unmapped source/page/row anchor "
                    f"for {chunker.version}"
                )
            expected_by_case[case.case_id] = groups
        configuration: dict[str, Any] = {
            "chunker": chunker.model_dump(mode="json"),
            "index_version": index_version,
            "inputs": input_records,
            "passage_set_sha256": _fingerprint(
                sorted(
                    (
                        {"passage_id": passage.passage_id, "text_sha256": passage.text_sha256}
                        for passage in passages
                    ),
                    key=lambda item: item["passage_id"],
                )
            ),
            "bm25": bm25_config,
            "passage_count": len(passages),
            "modes": {},
            "case_results": {},
        }
        evaluation_modes: list[tuple[str, RetrievalMode, RetrievalService]] = [
            (mode, mode, service) for mode in modes
        ]
        if reranked_service is not None:
            evaluation_modes.append(("hybrid+cross_encoder", "hybrid", reranked_service))
        for label, mode, mode_service in evaluation_modes:
            case_results: list[EvaluationCaseResult] = []
            reranking_statuses: list[str] = []
            for case in cases.cases:
                started = time.perf_counter()
                run = mode_service.search(
                    RetrievalRequest(
                        query=case.query,
                        mode=mode,
                        top_k=settings.final_context_chunks,
                        filters=case.filters,
                    )
                )
                if label == "hybrid+cross_encoder" and run.reranking is not None:
                    reranking_statuses.append(run.reranking.status)
                elapsed_ms = (time.perf_counter() - started) * 1000
                retrieved_ids = tuple(evidence.passage_id for evidence in run.evidence)
                complete = all(
                    evidence.source_id
                    and len(evidence.source_content_sha256) == 64
                    and (evidence.locations or evidence.row_key is not None)
                    and evidence.licence
                    for evidence in run.evidence
                )
                case_results.append(
                    EvaluationCaseResult(
                        case_id=case.case_id,
                        expected_passage_groups=expected_by_case[case.case_id],
                        retrieved_passage_ids=retrieved_ids,
                        latency_ms=elapsed_ms,
                        citation_complete=bool(complete),
                    )
                )
            configuration["modes"][label] = compute_retrieval_metrics(
                case_results, k=settings.final_context_chunks
            )
            configuration["case_results"][label] = [
                item.model_dump(mode="json") for item in case_results
            ]
            if label == "hybrid+cross_encoder":
                configuration["reranking"] = {
                    "attempted_case_count": len(reranking_statuses),
                    "completed_case_count": reranking_statuses.count("completed"),
                    "failed_case_count": reranking_statuses.count("failed"),
                    "not_run_case_count": len(case_results) - len(reranking_statuses),
                }
        results["configurations"].append(configuration)
    return results
