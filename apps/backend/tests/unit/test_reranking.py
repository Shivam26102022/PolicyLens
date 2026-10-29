from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.reranking import FastEmbedCrossEncoder, RerankerError, create_reranker


class FakeCrossEncoder:
    def __init__(
        self,
        scores: Iterable[float] | Exception,
    ) -> None:
        self.scores = scores
        self.query: str | None = None
        self.documents: list[str] = []
        self.batch_size: int | None = None

    def rerank(
        self,
        query: str,
        documents: Iterable[str],
        *,
        batch_size: int,
    ) -> Iterable[float]:
        self.query = query
        self.documents = list(documents)
        self.batch_size = batch_size
        if isinstance(self.scores, Exception):
            raise self.scores
        return self.scores


def _settings(
    *,
    reranker_batch_size: int = 16,
    model_cache_directory: Path = Path("models/fastembed"),
    reranker_enabled: bool = True,
) -> RetrievalSettings:
    return RetrievalSettings(  # type: ignore[call-arg]
        _env_file=None,
        reranker_batch_size=reranker_batch_size,
        model_cache_directory=model_cache_directory,
        reranker_enabled=reranker_enabled,
    )


def test_fastembed_cross_encoder_returns_finite_scores_in_input_order() -> None:
    model = FakeCrossEncoder([0.1, 0.9])
    reranker = FastEmbedCrossEncoder(_settings(reranker_batch_size=4), model=model)

    scores = reranker.rerank("policy question", ["passage one", "passage two"])

    assert scores == (0.1, 0.9)
    assert model.query == "policy question"
    assert model.documents == ["passage one", "passage two"]
    assert model.batch_size == 4


@pytest.mark.parametrize(
    "scores",
    [[], [float("nan")], [float("inf")], [0.1, 0.2, 0.3]],
)
def test_fastembed_cross_encoder_rejects_invalid_scores(scores: list[float]) -> None:
    reranker = FastEmbedCrossEncoder(_settings(), model=FakeCrossEncoder(scores))

    with pytest.raises(RerankerError) as error:
        reranker.rerank("query", ["one", "two"])

    assert error.value.code == "RERANKER_INVALID_OUTPUT"


def test_fastembed_cross_encoder_maps_model_failures_to_safe_error() -> None:
    reranker = FastEmbedCrossEncoder(
        _settings(),
        model=FakeCrossEncoder(RuntimeError("private model exception")),
    )

    with pytest.raises(RerankerError) as error:
        reranker.rerank("query", ["passage"])

    assert error.value.code == "RERANKER_UNAVAILABLE"
    assert "private model exception" not in str(error.value)


def test_fastembed_cross_encoder_uses_local_model_cache_and_lazy_cpu_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import fastembed.rerank.cross_encoder as cross_encoder

    arguments: dict[str, object] = {}

    class Model:
        def __init__(self, **kwargs: object) -> None:
            arguments.update(kwargs)

        def rerank(
            self,
            _query: str,
            documents: Iterable[str],
            *,
            batch_size: int,
        ) -> Iterable[float]:
            del batch_size
            return [0.5 for _ in documents]

    monkeypatch.setattr(cross_encoder, "TextCrossEncoder", Model)
    settings = _settings(model_cache_directory=tmp_path)
    reranker = FastEmbedCrossEncoder(settings)

    assert reranker.rerank("query", ["passage"]) == (0.5,)
    assert arguments == {
        "model_name": settings.reranker_model,
        "cache_dir": str(tmp_path),
        "cuda": False,
        "lazy_load": True,
    }


def test_reranker_factory_respects_disabled_configuration() -> None:
    assert create_reranker(_settings(reranker_enabled=False)) is None
