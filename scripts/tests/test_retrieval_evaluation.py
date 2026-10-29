from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import policylens.retrieval.evaluation as evaluation
from policylens.retrieval.chunking import fixed_chunker_config
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.evaluation import (
    EvaluationCaseResult,
    EvidenceAnchor,
    RetrievalCase,
    RetrievalCaseSet,
    compute_retrieval_metrics,
    map_anchor_to_passages,
)
from policylens.retrieval.models import (
    BlockLocation,
    CorpusPassage,
    EmbeddingDescriptor,
    RetrievalRerankingDiagnostics,
    RetrievalRun,
    RetrievedEvidence,
    StructuredRowKey,
    passage_text_sha256,
)
from scripts.evaluate_retrieval import _write_report


def _passage(
    passage_id: str,
    *,
    source_id: str = "report",
    page: int = 3,
    text: str = "The report describes a tripartite workforce partnership.",
    row_key: StructuredRowKey | None = None,
) -> CorpusPassage:
    return CorpusPassage(
        passage_id=f"sha256:{passage_id * 64}",
        source_id=source_id,
        document_id=f"doc:{source_id}",
        title="Report title",
        publisher="World Bank",
        source_uri="https://example.test/source",
        text=text,
        embedding_text=text,
        text_sha256=passage_text_sha256(text),
        embedding_text_sha256=passage_text_sha256(text),
        source_content_sha256="b" * 64,
        chunker_version="chunker-v1",
        locations=(
            (BlockLocation(page_number=page, block_id="b1", start_char=0, end_char=len(text)),)
            if row_key is None
            else ()
        ),
        row_key=row_key,
        section_path=("Executive Summary",),
        token_count=10,
        licence="CC BY 4.0",
        sensitivity="public",
        permission_scope="public",
        allowed_usage=("retrieval",),
        country_iso3=row_key.country_iso3 if row_key else None,
        year=row_key.year if row_key else None,
        indicator_id=row_key.indicator_id if row_key else None,
    )


def test_report_anchor_maps_to_strategy_specific_passage_id() -> None:
    passage = _passage("a")
    anchor = EvidenceAnchor(
        source_id="report",
        page_number=3,
        marker="tripartite workforce partnership",
    )

    assert map_anchor_to_passages(anchor, [passage]) == (passage.passage_id,)
    assert map_anchor_to_passages(anchor.model_copy(update={"page_number": 4}), [passage]) == ()


def test_report_anchor_matching_normalizes_canonical_line_breaks() -> None:
    passage = _passage("d", text="The 15th ICLS introduced the notion of informal\nemployment.")
    anchor = EvidenceAnchor(
        source_id="report",
        page_number=3,
        marker="The 15th ICLS introduced the notion of informal employment",
    )

    assert map_anchor_to_passages(anchor, [passage]) == (passage.passage_id,)


def test_structured_anchor_maps_by_exact_row_key() -> None:
    key = StructuredRowKey(
        dataset_id="dataset:indicator",
        observation_id="indicator:IND:2025",
        indicator_id="SL.UEM.1524.ZS",
        country_iso3="IND",
        year=2025,
    )
    passage = _passage("c", source_id="indicator", row_key=key)
    anchor = EvidenceAnchor(source_id="indicator", row_key=key)

    assert map_anchor_to_passages(anchor, [passage]) == (passage.passage_id,)


def test_metrics_report_recall_mrr_latency_empty_and_citation_completeness() -> None:
    metrics = compute_retrieval_metrics(
        [
            EvaluationCaseResult(
                case_id="q1",
                expected_passage_groups=(("a", "a2"), ("b",)),
                retrieved_passage_ids=("noise", "a2"),
                latency_ms=10.0,
                citation_complete=True,
            ),
            EvaluationCaseResult(
                case_id="q2",
                expected_passage_groups=(("c",),),
                retrieved_passage_ids=(),
                latency_ms=20.0,
                citation_complete=False,
            ),
        ],
        k=5,
    )

    assert metrics["recall_at_k"] == 0.25
    assert metrics["mrr"] == 0.25
    assert metrics["empty_result_rate"] == 0.5
    assert metrics["mean_latency_ms"] == 15.0
    assert metrics["citation_completeness"] == 0.5
    assert round(float(metrics["ndcg_at_k"]), 6) == 0.193426
    assert metrics["groundedness"] == "not_measured"


def test_generated_report_describes_baseline_without_claiming_groundedness(tmp_path) -> None:
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="BAAI/bge-small-en-v1.5",
        package_version="0.9.1",
        dimension=384,
        normalized=True,
        max_input_tokens=512,
    )
    report_path = tmp_path / "retrieval-evaluation.md"

    _write_report(
        report_path,
        "case-set",
        "author-curated lineage",
        {
            "top_k": 5,
            "reranker": {
                "enabled": True,
                "model_id": "test-reranker",
                "candidate_count": 20,
            },
            "configurations": [
                {
                    "chunker": {"strategy": "fixed-size", "version": "test-v1"},
                    "passage_count": 1,
                    "modes": {
                        "hybrid+cross_encoder": {
                            "recall_at_k": 1.0,
                            "ndcg_at_k": 1.0,
                            "mrr": 1.0,
                            "empty_result_rate": 0.0,
                            "citation_completeness": 1.0,
                            "mean_latency_ms": 3.0,
                        }
                    },
                    "reranking": {
                        "attempted_case_count": 1,
                        "completed_case_count": 1,
                        "failed_case_count": 0,
                        "not_run_case_count": 0,
                    },
                }
            ],
        },
        SimpleNamespace(descriptor=descriptor),
    )

    report = report_path.read_text(encoding="utf-8")
    assert "Feature 003 includes a bounded extractive non-agent baseline" in report
    assert "`POST /retrieval/answer`" in report
    assert "disables provider storage and retries" in report
    assert "exactly equal to a server-derived citation excerpt" in report
    assert "report the provider, model ID, and prompt version" in report
    assert "This retrieval evaluation does not measure answer selection quality" in report
    assert "source accuracy are `not_measured`" in report
    assert "Feature 003 does not generate answers" not in report
    table_row = "| fixed-size:test-v1 | 1 | hybrid+cross_encoder |"
    assert report.index(table_row) < report.index("Reranking outcomes")
    assert "Reranker: `test-reranker`" in report


def test_evaluator_reports_cross_encoder_as_separate_hybrid_comparison(monkeypatch) -> None:
    passage = _passage("e")
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="BAAI/bge-small-en-v1.5",
        package_version="0.9.1",
        dimension=384,
        normalized=True,
        max_input_tokens=512,
    )
    embedder = SimpleNamespace(
        descriptor=descriptor,
        embed_passages=lambda _passages: [[1.0]],
    )
    reranker = SimpleNamespace(model_id="test-reranker")
    case_set = RetrievalCaseSet(
        schema_version="1.0",
        set_id="test-cases",
        lineage="test lineage",
        cases=(
            RetrievalCase(
                case_id="case-1",
                query="workforce partnership",
                expected_anchors=(
                    EvidenceAnchor(
                        source_id="report",
                        page_number=3,
                        marker="tripartite workforce partnership",
                    ),
                ),
            ),
        ),
    )

    class FakeService:
        def __init__(self, *, reranker=None, **_kwargs) -> None:
            self.reranker = reranker

        def search(self, _request):
            return RetrievalRun(
                index_version="c" * 64,
                status="found",
                evidence=(
                    RetrievedEvidence(
                        passage_id=passage.passage_id,
                        source_id=passage.source_id,
                        title=passage.title,
                        publisher=passage.publisher,
                        source_uri=passage.source_uri,
                        text=passage.text,
                        source_content_sha256=passage.source_content_sha256,
                        locations=passage.locations,
                        row_key=None,
                        section_path=passage.section_path,
                        rank=1,
                        score=0.5,
                        retrieval_mode="hybrid",
                        licence=passage.licence,
                    ),
                ),
                context=passage.text,
                reranking=(
                    RetrievalRerankingDiagnostics(
                        status="completed",
                        model_id="test-reranker",
                        candidate_count=1,
                        duration_ms=2.0,
                    )
                    if self.reranker is not None
                    else None
                ),
            )

    monkeypatch.setattr(evaluation, "load_current_sources", lambda _root: [])
    monkeypatch.setattr(evaluation, "_load_passages", lambda *_args: ([passage], []))
    monkeypatch.setattr(evaluation, "_build_bm25", lambda *_args: (object(), [passage.passage_id]))
    monkeypatch.setattr(evaluation, "RetrievalService", FakeService)

    result = evaluation.evaluate_retrieval(
        project_root=Path("."),
        settings=RetrievalSettings(),
        embedder=embedder,
        cases=case_set,
        chunkers=[fixed_chunker_config()],
        reranker=reranker,
    )

    configuration = result["configurations"][0]
    assert "hybrid+cross_encoder" in configuration["modes"]
    assert configuration["reranking"] == {
        "attempted_case_count": 1,
        "completed_case_count": 1,
        "failed_case_count": 0,
        "not_run_case_count": 0,
    }
