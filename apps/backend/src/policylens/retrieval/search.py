from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Any, Protocol

import bm25s
import chromadb
from chromadb.config import Settings

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import EmbeddingProvider
from policylens.retrieval.indexing import (
    BM25_TOKEN_PATTERN,
    IndexBuildError,
    IndexBuildManifest,
    _load_json,
    _path_under_root,
    _permission_where,
    runtime_chroma_path,
    verify_active_index,
)
from policylens.retrieval.models import (
    BlockLocation,
    EmbeddingDescriptor,
    RetrievalFilters,
    RetrievalRequest,
    RetrievalRerankingDiagnostics,
    RetrievalRun,
    RetrievedEvidence,
    StructuredRowKey,
)
from policylens.retrieval.reranking import Reranker, RerankerError, create_reranker


class RetrievalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RunRegistry(Protocol):
    def register(self, run: RetrievalRun) -> None: ...


@dataclass(frozen=True)
class IndexedPassage:
    passage_id: str
    source_id: str
    document_id: str
    title: str
    publisher: str
    source_uri: str | None
    text: str
    text_sha256: str
    source_content_sha256: str
    locations: tuple[BlockLocation, ...]
    row_key: StructuredRowKey | None
    section_path: tuple[str, ...]
    licence: str
    permission_scope: str
    allowed_usage: tuple[str, ...]
    country_iso3: str | None = None
    year: int | None = None
    indicator_id: str | None = None


@dataclass(frozen=True)
class _RankedResult:
    passage_id: str
    bm25_rank: int | None = None
    dense_rank: int | None = None
    bm25_score: float | None = None
    dense_score: float | None = None
    reranker_score: float | None = None


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return ()
    return tuple(value)


def _indexed_passage(
    passage_id: str,
    text: str,
    metadata: Mapping[str, Any],
) -> IndexedPassage:
    try:
        locations_raw = json.loads(metadata.get("locations_json", "[]"))
        row_key_raw = json.loads(metadata.get("row_key_json", "null"))
        section_raw = json.loads(metadata.get("section_path_json", "[]"))
        locations = tuple(BlockLocation.model_validate(item) for item in locations_raw)
        row_key = StructuredRowKey.model_validate(row_key_raw) if row_key_raw else None
        section_path = tuple(section_raw)
        passage = IndexedPassage(
            passage_id=passage_id,
            source_id=str(metadata["source_id"]),
            document_id=str(metadata["document_id"]),
            title=str(metadata["title"]),
            publisher=str(metadata["publisher"]),
            source_uri=metadata.get("source_uri"),
            text=text,
            text_sha256=str(metadata["text_sha256"]),
            source_content_sha256=str(metadata["content_sha256"]),
            locations=locations,
            row_key=row_key,
            section_path=section_path,
            licence=str(metadata["licence"]),
            permission_scope=str(metadata["permission_scope"]),
            allowed_usage=_string_list(metadata.get("allowed_usage")),
            country_iso3=metadata.get("country_iso3"),
            year=metadata.get("year"),
            indicator_id=metadata.get("indicator_id"),
        )
    except Exception as error:
        raise RetrievalError(
            "INDEX_METADATA_INVALID", "Index contains invalid passage metadata"
        ) from error
    if hashlib.sha256(passage.text.encode("utf-8")).hexdigest() != passage.text_sha256:
        raise RetrievalError(
            "INDEX_TEXT_HASH_MISMATCH", "Passage text does not match its indexed hash"
        )
    return passage


class RetrievalService:
    def __init__(
        self,
        *,
        settings: RetrievalSettings,
        index_version: str,
        passages: tuple[IndexedPassage, ...] | list[IndexedPassage],
        vector_collection: Any,
        bm25_retriever: Any,
        bm25_ids: list[str],
        embedder: EmbeddingProvider,
        run_registry: RunRegistry,
        reranker: Reranker | None = None,
    ) -> None:
        self.settings = settings
        self.index_version = index_version
        self._passages = {passage.passage_id: passage for passage in passages}
        self._table_captions = {
            (passage.source_id, location.page_number, location.block_id): passage.text
            for passage in passages
            if re.match(r"^\s*Table\s+(?:\d+|[A-Z])\b", passage.text, re.IGNORECASE)
            for location in passage.locations
        }
        self._vector_collection = vector_collection
        self._bm25_retriever = bm25_retriever
        self._bm25_ids = bm25_ids
        self._embedder = embedder
        self._run_registry = run_registry
        self._reranker = reranker if settings.reranker_enabled else None
        if len(self._passages) != len(passages) or len(self._bm25_ids) != len(self._passages):
            raise RetrievalError(
                "INDEX_COUNT_MISMATCH", "Index stores disagree about active passage IDs"
            )

    @classmethod
    def from_active_index(
        cls,
        project_root: Path,
        settings: RetrievalSettings,
        embedder: EmbeddingProvider,
        run_registry: RunRegistry,
    ) -> RetrievalService:
        root = project_root.resolve()
        try:
            pointer = verify_active_index(root, settings)
            manifest_path = _path_under_root(root, pointer.manifest_path, "build manifest")
            manifest = _load_json(manifest_path, "build manifest")
            expected_embedding = EmbeddingDescriptor.model_validate(manifest["embedding"])
            set_expected_dimension = getattr(embedder, "set_expected_dimension", None)
            if callable(set_expected_dimension):
                set_expected_dimension(expected_embedding.dimension)
            if embedder.descriptor != expected_embedding:
                raise RetrievalError(
                    "INDEX_EMBEDDING_MISMATCH",
                    "Configured embedding model does not match the active index",
                )
            output = manifest["outputs"]
            chroma_path = _path_under_root(root, output["chroma_path"], "Chroma index path")
            chroma_manifest = IndexBuildManifest.model_validate(manifest)
            chroma_path = runtime_chroma_path(chroma_path, chroma_manifest)
            bm25_path = _path_under_root(root, output["bm25_path"], "BM25 index path")
            client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
            collection = client.get_collection(
                name=f"policylens_{pointer.index_version[:24]}",
                embedding_function=None,
            )
            records = collection.get(include=["documents", "metadatas"])
            record_ids = records.get("ids")
            documents = records.get("documents")
            metadatas = records.get("metadatas")
            if record_ids is None or documents is None or metadatas is None:
                raise RetrievalError("INDEX_METADATA_INVALID", "Index records are incomplete")
            passages = tuple(
                _indexed_passage(passage_id, text, metadata)
                for passage_id, text, metadata in zip(record_ids, documents, metadatas, strict=True)
            )
            bm25 = bm25s.BM25.load(bm25_path, load_corpus=True, show_progress=False)
            bm25_ids: list[str] = []
            for entry in bm25.corpus:
                passage_id = entry.get("text") if isinstance(entry, dict) else entry
                if not isinstance(passage_id, str):
                    raise RetrievalError(
                        "BM25_METADATA_INVALID", "BM25 index contains invalid passage IDs"
                    )
                bm25_ids.append(passage_id)
        except (RetrievalError, IndexBuildError):
            raise
        except Exception as error:
            raise RetrievalError(
                "INDEX_UNAVAILABLE", "Active retrieval index could not be loaded"
            ) from error
        return cls(
            settings=settings,
            index_version=pointer.index_version,
            passages=passages,
            vector_collection=collection,
            bm25_retriever=bm25,
            bm25_ids=bm25_ids,
            embedder=embedder,
            run_registry=run_registry,
            reranker=create_reranker(settings),
        )

    def _matches_filters(self, passage: IndexedPassage, filters: RetrievalFilters) -> bool:
        if passage.permission_scope not in self.settings.allowed_permission_scopes:
            return False
        if "retrieval" not in passage.allowed_usage:
            return False
        if filters.source_ids and passage.source_id not in filters.source_ids:
            return False
        if filters.country_iso3 and passage.country_iso3 not in filters.country_iso3:
            return False
        if filters.years and passage.year not in filters.years:
            return False
        if filters.indicator_ids and passage.indicator_id not in filters.indicator_ids:
            return False
        return True

    def iter_passages_for_mcp(self) -> Iterator[IndexedPassage]:
        filters = RetrievalFilters()
        for passage_id in sorted(self._passages):
            passage = self._passages[passage_id]
            if self._matches_filters(passage, filters):
                yield passage

    def _where_filter(self, filters: RetrievalFilters) -> dict[str, Any]:
        where = _permission_where(self.settings.allowed_permission_scopes)
        conditions: list[dict[str, Any]] = list(where["$and"])
        for key, values in (
            ("source_id", filters.source_ids),
            ("country_iso3", filters.country_iso3),
            ("year", filters.years),
            ("indicator_id", filters.indicator_ids),
        ):
            if values:
                conditions.append({key: {"$in": list(values)}})
        return {"$and": conditions}

    def _bm25_results(self, query: str) -> list[tuple[str, int, float]]:
        query_tokens = bm25s.tokenize(
            query,
            lower=True,
            stopwords=[],
            token_pattern=BM25_TOKEN_PATTERN,
            return_ids=True,
            show_progress=False,
        )
        if not self._bm25_ids:
            return []
        results = self._bm25_retriever.retrieve(
            query_tokens,
            corpus=self._bm25_ids,
            k=min(self.settings.max_candidates, len(self._bm25_ids)),
            show_progress=False,
        )
        documents = list(results.documents[0])
        scores = list(results.scores[0])
        return [
            (str(passage_id), rank, float(score))
            for rank, (passage_id, score) in enumerate(zip(documents, scores, strict=True), 1)
        ]

    def _dense_results(self, query: str, filters: RetrievalFilters) -> list[tuple[str, int, float]]:
        if not self._passages:
            return []
        try:
            query_embedding = self._embedder.embed_query(query)
        except Exception as error:
            raise RetrievalError(
                "EMBEDDING_UNAVAILABLE", "Query embedding is unavailable"
            ) from error
        try:
            result = self._vector_collection.query(
                query_embeddings=[query_embedding],
                n_results=min(self.settings.max_candidates, len(self._passages)),
                where=self._where_filter(filters),
                include=["distances"],
            )
        except Exception as error:
            raise RetrievalError("DENSE_RETRIEVAL_FAILED", "Dense retrieval failed") from error
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            (str(passage_id), rank, 1.0 - float(distance))
            for rank, (passage_id, distance) in enumerate(zip(ids, distances, strict=True), 1)
        ]

    def _ranked_candidates(self, request: RetrievalRequest) -> dict[str, _RankedResult]:
        bm25_results = (
            self._bm25_results(request.query) if request.mode in {"bm25", "hybrid"} else []
        )
        dense_results = (
            self._dense_results(request.query, request.filters)
            if request.mode in {"dense", "hybrid"}
            else []
        )
        bm25_candidates: dict[str, tuple[int, float]] = {}
        dense_candidates: dict[str, tuple[int, float]] = {}
        for passage_id, rank, score in bm25_results:
            passage = self._passages.get(passage_id)
            if passage is None or not self._matches_filters(passage, request.filters):
                continue
            bm25_candidates[passage_id] = (rank, score)
        for passage_id, rank, score in dense_results:
            passage = self._passages.get(passage_id)
            if passage is None or not self._matches_filters(passage, request.filters):
                continue
            dense_candidates[passage_id] = (rank, score)
        return {
            passage_id: _RankedResult(
                passage_id=passage_id,
                bm25_rank=bm25_candidates.get(passage_id, (None, None))[0],
                dense_rank=dense_candidates.get(passage_id, (None, None))[0],
                bm25_score=bm25_candidates.get(passage_id, (None, None))[1],
                dense_score=dense_candidates.get(passage_id, (None, None))[1],
            )
            for passage_id in bm25_candidates.keys() | dense_candidates.keys()
        }

    def _score(self, result: _RankedResult, mode: str) -> float:
        if result.reranker_score is not None:
            return result.reranker_score
        if mode == "bm25":
            return float(result.bm25_score or 0.0)
        if mode == "dense":
            return float(result.dense_score or 0.0)
        score = 0.0
        if result.bm25_rank is not None:
            score += 1.0 / (self.settings.rrf_k + result.bm25_rank)
        if result.dense_rank is not None:
            score += 1.0 / (self.settings.rrf_k + result.dense_rank)
        return score

    def _reranker_text(self, passage: IndexedPassage) -> str:
        sections = " > ".join(passage.section_path)
        captions: list[str] = []
        for location in passage.locations:
            match = re.fullmatch(r"b(\d+)", location.block_id)
            if match is None:
                continue
            number = int(match.group(1))
            if number < 1:
                continue
            previous_block = f"b{number - 1:0{len(match.group(1))}d}"
            caption = self._table_captions.get(
                (passage.source_id, location.page_number, previous_block)
            )
            if caption and caption not in captions:
                captions.append(caption)
        table_context = "\n".join(f"Table caption: {caption}" for caption in captions)
        return "\n".join(
            item for item in (passage.title, sections, table_context, passage.text) if item
        )

    def _rerank(
        self,
        request: RetrievalRequest,
        ordered: list[_RankedResult],
    ) -> tuple[list[_RankedResult], RetrievalRerankingDiagnostics | None]:
        if self._reranker is None or request.mode != "hybrid" or not ordered:
            return ordered, None

        candidates = ordered[: self.settings.reranker_candidate_count]
        documents = [self._reranker_text(self._passages[item.passage_id]) for item in candidates]
        started = monotonic()
        try:
            scores = tuple(self._reranker.rerank(request.query, documents))
            if len(scores) != len(candidates) or any(not isfinite(score) for score in scores):
                raise RerankerError(
                    "RERANKER_INVALID_OUTPUT",
                    "The local cross-encoder returned invalid relevance scores.",
                )
        except RerankerError as error:
            return ordered, RetrievalRerankingDiagnostics(
                status="failed",
                model_id=self._reranker.model_id,
                candidate_count=len(candidates),
                duration_ms=max(0.0, (monotonic() - started) * 1000.0),
                error_code=error.code,
            )

        scored_candidates = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: (-item[1], item[0].passage_id),
        )
        reranked = [
            replace(candidate, reranker_score=score) for candidate, score in scored_candidates
        ]
        candidate_ids = {result.passage_id for result in candidates}
        diagnostics = RetrievalRerankingDiagnostics(
            status="completed",
            model_id=self._reranker.model_id,
            candidate_count=len(candidates),
            duration_ms=max(0.0, (monotonic() - started) * 1000.0),
        )
        return (
            [*reranked, *(item for item in ordered if item.passage_id not in candidate_ids)],
            diagnostics,
        )

    @staticmethod
    def _overlaps(left: IndexedPassage, right: IndexedPassage) -> bool:
        if left.text_sha256 == right.text_sha256:
            return True
        for left_location in left.locations:
            for right_location in right.locations:
                if (
                    left_location.page_number != right_location.page_number
                    or left_location.block_id != right_location.block_id
                ):
                    continue
                overlap = max(
                    0,
                    min(left_location.end_char, right_location.end_char)
                    - max(left_location.start_char, right_location.start_char),
                )
                shorter = min(
                    left_location.end_char - left_location.start_char,
                    right_location.end_char - right_location.start_char,
                )
                if shorter and overlap / shorter >= 0.5:
                    return True
        return False

    def _context(self, evidence: tuple[RetrievedEvidence, ...]) -> str:
        parts: list[str] = []
        length = 0
        for item in evidence:
            source_id = html.escape(item.source_id, quote=True)
            passage_id = html.escape(item.passage_id, quote=True)
            body = html.escape(item.text, quote=False)
            part = (
                f'<UNTRUSTED_EVIDENCE source_id="{source_id}" passage_id="{passage_id}">\n'
                f"{body}\n</UNTRUSTED_EVIDENCE>"
            )
            addition = len(part) + (2 if parts else 0)
            if length + addition > self.settings.max_context_chars:
                break
            parts.append(part)
            length += addition
        return "\n\n".join(parts)

    def search(self, request: RetrievalRequest) -> RetrievalRun:
        try:
            ranked = self._ranked_candidates(request)
        except RetrievalError:
            raise
        except Exception as error:
            raise RetrievalError("RETRIEVAL_FAILED", "Retrieval failed") from error
        ordered = sorted(
            ranked.values(),
            key=lambda result: (-self._score(result, request.mode), result.passage_id),
        )
        ordered, reranking = self._rerank(request, ordered)
        selected: list[RetrievedEvidence] = []
        selected_passages: list[IndexedPassage] = []
        source_counts: dict[str, int] = {}
        limit = min(request.top_k, self.settings.final_context_chunks)
        # The diversity pass enforces the per-source cap; the back-fill pass then uses
        # remaining slots so single-source questions are not capped below top_k.
        for enforce_source_cap in (True, False):
            for result in ordered:
                passage = self._passages[result.passage_id]
                if len(selected) >= limit:
                    break
                if any(passage.passage_id == prior.passage_id for prior in selected_passages):
                    continue
                if (
                    enforce_source_cap
                    and source_counts.get(passage.source_id, 0) >= self.settings.per_source_cap
                ):
                    continue
                if any(self._overlaps(passage, prior) for prior in selected_passages):
                    continue
                score = self._score(result, request.mode)
                evidence = RetrievedEvidence(
                    passage_id=passage.passage_id,
                    source_id=passage.source_id,
                    title=passage.title,
                    publisher=passage.publisher,
                    source_uri=passage.source_uri,
                    text=passage.text,
                    source_content_sha256=passage.source_content_sha256,
                    locations=passage.locations,
                    row_key=passage.row_key,
                    section_path=passage.section_path,
                    rank=len(selected) + 1,
                    score=score,
                    bm25_rank=result.bm25_rank,
                    dense_rank=result.dense_rank,
                    bm25_score=result.bm25_score,
                    dense_score=result.dense_score,
                    reranker_score=result.reranker_score,
                    retrieval_mode=request.mode,
                    licence=passage.licence,
                )
                selected.append(evidence)
                selected_passages.append(passage)
                source_counts[passage.source_id] = source_counts.get(passage.source_id, 0) + 1
        evidence_tuple = tuple(selected)
        run = RetrievalRun(
            index_version=self.index_version,
            status="found" if evidence_tuple else "no_results",
            evidence=evidence_tuple,
            context=self._context(evidence_tuple),
            reranking=reranking,
        )
        self._run_registry.register(run)
        return run
