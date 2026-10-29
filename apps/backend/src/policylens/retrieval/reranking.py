from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Any, Literal, Protocol

from policylens.retrieval.config import RetrievalSettings


class RerankerError(RuntimeError):
    def __init__(
        self,
        code: Literal["RERANKER_UNAVAILABLE", "RERANKER_INVALID_OUTPUT"],
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class Reranker(Protocol):
    @property
    def model_id(self) -> str: ...

    def rerank(self, query: str, documents: Sequence[str]) -> tuple[float, ...]: ...


class FastEmbedCrossEncoder:
    def __init__(
        self,
        settings: RetrievalSettings,
        *,
        model: Any | None = None,
    ) -> None:
        self.model_id = settings.reranker_model
        self._cache_directory = str(settings.model_cache_directory)
        self._batch_size = settings.reranker_batch_size
        self._model = model
        self._lock = threading.Lock()

    def _load_model(self) -> Any:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(
                model_name=self.model_id,
                cache_dir=self._cache_directory,
                cuda=False,
                lazy_load=True,
            )
        return self._model

    def rerank(self, query: str, documents: Sequence[str]) -> tuple[float, ...]:
        if not documents:
            return ()
        try:
            with self._lock:
                model = self._load_model()
                scores = tuple(
                    float(score)
                    for score in model.rerank(query, documents, batch_size=self._batch_size)
                )
        except Exception as error:
            raise RerankerError(
                "RERANKER_UNAVAILABLE",
                "The local cross-encoder reranker is unavailable.",
            ) from error
        if len(scores) != len(documents) or any(not math.isfinite(score) for score in scores):
            raise RerankerError(
                "RERANKER_INVALID_OUTPUT",
                "The local cross-encoder returned invalid relevance scores.",
            )
        return scores


def create_reranker(settings: RetrievalSettings) -> Reranker | None:
    if not settings.reranker_enabled:
        return None
    return FastEmbedCrossEncoder(settings)
