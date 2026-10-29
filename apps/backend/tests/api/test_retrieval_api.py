from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from policylens.api.app import create_app
from policylens.api.mcp_probe import MCPProbeResult
from policylens.retrieval.citations import CitationValidator, RetrievalRunRegistry
from policylens.retrieval.generation import (
    BaselineAnswerClaim,
    BaselineAnswerResponse,
    BaselineConfigurationError,
    BaselineGenerationMetadata,
)
from policylens.retrieval.indexing import IndexBuildError
from policylens.retrieval.models import (
    BlockLocation,
    Citation,
    EmbeddingDescriptor,
    RetrievalRequest,
    RetrievalRun,
    RetrievedEvidence,
)
from policylens.settings import AppSettings

HASH = "a" * 64
RUN_ID = UUID("9a734d29-8d52-4afe-97f6-14963f251f1b")


def _run() -> RetrievalRun:
    text = "Youth unemployment was 16 percent in the modeled 2025 estimate."
    evidence = RetrievedEvidence(
        passage_id="sha256:" + "b" * 64,
        source_id="wb-youth-unemployment-1524-2015-2025",
        title="Youth unemployment",
        publisher="World Bank Data",
        source_uri="https://data.worldbank.org/indicator/SL.UEM.1524.ZS",
        text=text,
        source_content_sha256=HASH,
        locations=(
            BlockLocation(page_number=1, block_id="row:IND:2025", start_char=0, end_char=len(text)),
        ),
        section_path=("Youth unemployment",),
        rank=1,
        score=0.8,
        bm25_rank=1,
        bm25_score=2.1,
        retrieval_mode="hybrid",
        licence="CC BY 4.0",
    )
    return RetrievalRun(
        run_id=RUN_ID,
        index_version=HASH,
        status="found",
        evidence=(evidence,),
        context="<UNTRUSTED_EVIDENCE>evidence</UNTRUSTED_EVIDENCE>",
    )


class FakeService:
    def __init__(self, run: RetrievalRun) -> None:
        self.run = run
        self.request: RetrievalRequest | None = None

    def search(self, request: RetrievalRequest) -> RetrievalRun:
        self.request = request
        return self.run


class FakeAnswerBaseline:
    def __init__(self) -> None:
        self.query: str | None = None
        self.run: RetrievalRun | None = None

    def answer(self, query: str, run: RetrievalRun) -> BaselineAnswerResponse:
        self.query = query
        self.run = run
        evidence = run.evidence[0]
        citation = Citation(
            claim_id="claim-1",
            source_id=evidence.source_id,
            title=evidence.title,
            source_uri=evidence.source_uri,
            passage_id=evidence.passage_id,
            page_start=1,
            page_end=1,
            section_path=evidence.section_path,
            excerpt="Youth unemployment was 16 percent",
            source_content_sha256=evidence.source_content_sha256,
            retrieval_rank=evidence.rank,
            retrieval_score=evidence.score,
            retrieval_mode=evidence.retrieval_mode,
        )
        return BaselineAnswerResponse(
            status="answered",
            run_id=run.run_id,
            index_version=run.index_version,
            claims=(
                BaselineAnswerClaim(
                    claim_id="claim-1",
                    text="Youth unemployment was 16 percent",
                    citations=(citation,),
                ),
            ),
            generation=BaselineGenerationMetadata(model_id="test-generation-model"),
        )


async def _ready_probe(_: AppSettings) -> MCPProbeResult:
    return MCPProbeResult(status="ready")


def _settings() -> AppSettings:
    return AppSettings(model_provider="mlx", mlx_model="test-model", embedding_provider="local")


def _app(
    service: object | None = None,
    validator: CitationValidator | None = None,
    factory: Any | None = None,
    answer_baseline: Any | None = None,
    answer_baseline_factory: Any | None = None,
):
    return create_app(
        settings=_settings(),
        mcp_probe=_ready_probe,
        retrieval_service=service,
        citation_validator=validator,
        retrieval_runtime_factory=factory,
        answer_baseline=answer_baseline,
        answer_baseline_factory=answer_baseline_factory,
    )


def test_search_endpoint_returns_versioned_evidence_and_passes_typed_request() -> None:
    run = _run()
    service = FakeService(run)
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/search",
            json={
                "schema_version": "1.0",
                "query": "youth unemployment",
                "mode": "hybrid",
                "top_k": 4,
            },
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == str(RUN_ID)
    assert response.json()["evidence"][0]["passage_id"] == run.evidence[0].passage_id
    assert service.request is not None
    assert service.request.query == "youth unemployment"


def test_search_endpoint_rejects_caller_permission_scope() -> None:
    app = _app(FakeService(_run()))

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/search",
            json={
                "schema_version": "1.0",
                "query": "youth unemployment",
                "mode": "hybrid",
                "filters": {"permission_scope": ["restricted"]},
            },
        )

    assert response.status_code == 422


def test_retrieval_readiness_requires_matching_active_embedding(monkeypatch) -> None:
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="BAAI/bge-small-en-v1.5",
        package_version="0.9.1",
        model_revision="snapshot",
        model_sha256="a" * 64,
        licence="mit",
        pooling="first-token CLS",
        tokenizer="BAAI/bge-small-en-v1.5",
        query_method="query_embed",
        passage_method="passage_embed",
        dimension=384,
        normalized=True,
        max_input_tokens=512,
    )
    monkeypatch.setattr(
        "policylens.api.retrieval.active_embedding_descriptor",
        lambda _root, _settings: descriptor,
    )
    app = _app(FakeService(_run()))

    with TestClient(app) as client:
        response = client.get("/retrieval/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["embedding_model"] == descriptor.model_id


def test_retrieval_readiness_rejects_embedding_model_mismatch(monkeypatch) -> None:
    descriptor = EmbeddingDescriptor(
        provider="local",
        model_id="different-model",
        package_version="0.9.1",
        dimension=384,
        normalized=True,
        max_input_tokens=512,
    )
    monkeypatch.setattr(
        "policylens.api.retrieval.active_embedding_descriptor",
        lambda _root, _settings: descriptor,
    )
    app = _app(FakeService(_run()))

    with TestClient(app) as client:
        response = client.get("/retrieval/ready")

    assert response.status_code == 503
    assert response.json()["error_code"] == "INDEX_INCOMPATIBLE"


def test_citation_endpoint_uses_server_held_run_evidence() -> None:
    run = _run()
    registry = RetrievalRunRegistry(ttl_seconds=60, capacity=10)
    registry.register(run)
    validator = CitationValidator(registry)
    app = _app(FakeService(run), validator)
    citation = Citation(
        claim_id="claim-1",
        source_id=run.evidence[0].source_id,
        title=run.evidence[0].title,
        source_uri=run.evidence[0].source_uri,
        passage_id=run.evidence[0].passage_id,
        page_start=1,
        page_end=1,
        section_path=run.evidence[0].section_path,
        excerpt="Youth unemployment was 16 percent",
        source_content_sha256=HASH,
        retrieval_rank=1,
        retrieval_score=0.8,
        retrieval_mode="hybrid",
    )

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/citations/validate",
            json={
                "schema_version": "1.0",
                "run_id": str(RUN_ID),
                "claims": [{"claim_id": "claim-1", "text": "Youth unemployment was 16 percent."}],
                "citations": [citation.model_dump(mode="json")],
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    assert response.json()["accepted"][0]["passage_id"] == citation.passage_id


def test_citation_endpoint_rejects_unknown_and_expired_run_ids() -> None:
    now = [100.0]

    def clock() -> float:
        return now[0]

    run = _run()
    registry = RetrievalRunRegistry(ttl_seconds=60, capacity=10, clock=clock)
    registry.register(run)
    app = _app(FakeService(run), CitationValidator(registry))
    citation = {
        "claim_id": "claim-1",
        "source_id": run.evidence[0].source_id,
        "title": run.evidence[0].title,
        "source_uri": run.evidence[0].source_uri,
        "passage_id": run.evidence[0].passage_id,
        "page_start": 1,
        "page_end": 1,
        "section_path": list(run.evidence[0].section_path),
        "excerpt": "Youth unemployment was 16 percent",
        "source_content_sha256": HASH,
        "retrieval_rank": 1,
        "retrieval_score": 0.8,
        "retrieval_mode": "hybrid",
    }

    with TestClient(app) as client:
        unknown = client.post(
            "/retrieval/citations/validate",
            json={
                "schema_version": "1.0",
                "run_id": "00000000-0000-4000-8000-000000000000",
                "claims": [{"claim_id": "claim-1", "text": "The rate is 16 percent."}],
                "citations": [citation],
            },
        )
        now[0] += 61
        expired = client.post(
            "/retrieval/citations/validate",
            json={
                "schema_version": "1.0",
                "run_id": str(RUN_ID),
                "claims": [{"claim_id": "claim-1", "text": "The rate is 16 percent."}],
                "citations": [citation],
            },
        )

    assert unknown.status_code == 200
    assert unknown.json()["rejected"][0]["reason_code"] == "RUN_NOT_FOUND"
    assert expired.status_code == 200
    assert expired.json()["rejected"][0]["reason_code"] == "RUN_NOT_FOUND"


def test_search_endpoint_returns_stable_unavailable_index_error() -> None:
    def unavailable(_: AppSettings) -> object:
        raise IndexBuildError("INDEX_NOT_ACTIVE", "No active index")

    app = _app(factory=unavailable)

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/search",
            json={"schema_version": "1.0", "query": "youth unemployment", "mode": "bm25"},
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "INDEX_NOT_ACTIVE"


def test_answer_endpoint_returns_non_agent_baseline_result() -> None:
    run = _run()
    service = FakeService(run)
    baseline = FakeAnswerBaseline()
    app = _app(service, CitationValidator(RetrievalRunRegistry()), answer_baseline=baseline)

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/answer",
            json={
                "schema_version": "1.0",
                "query": "youth unemployment",
                "mode": "hybrid",
                "top_k": 4,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["claims"][0]["citations"][0]["source_id"] == run.evidence[0].source_id
    assert response.json()["generation"]["prompt_version"] == "non-agent-v1"
    assert baseline.query == "youth unemployment"
    assert baseline.run == run


def test_answer_endpoint_skips_generation_for_no_evidence() -> None:
    run = RetrievalRun(
        run_id=RUN_ID,
        index_version=HASH,
        status="no_results",
        evidence=(),
        context="",
    )

    def unexpected_factory(*_args: object) -> object:
        raise AssertionError("generation must not be initialized for empty evidence")

    app = _app(
        FakeService(run),
        CitationValidator(RetrievalRunRegistry()),
        answer_baseline_factory=unexpected_factory,
    )

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/answer",
            json={"schema_version": "1.0", "query": "no match", "mode": "bm25"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "abstained"
    assert response.json()["error_code"] == "NO_EVIDENCE"
    assert response.json()["generation"] is None


def test_answer_endpoint_reports_unconfigured_generation_without_fallback() -> None:
    run = _run()

    def unconfigured_provider(*_args: object) -> object:
        raise BaselineConfigurationError("Selected generation provider is not configured")

    app = _app(
        FakeService(run),
        CitationValidator(RetrievalRunRegistry()),
        answer_baseline_factory=unconfigured_provider,
    )

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/answer",
            json={"schema_version": "1.0", "query": "youth unemployment", "mode": "bm25"},
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "GENERATION_UNAVAILABLE"
