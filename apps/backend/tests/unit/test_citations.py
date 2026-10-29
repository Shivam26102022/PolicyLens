from __future__ import annotations

from uuid import UUID

from policylens.retrieval.citations import CitationValidator, RetrievalRunRegistry
from policylens.retrieval.models import (
    BlockLocation,
    Citation,
    Claim,
    RetrievalRun,
    RetrievedEvidence,
)

HASH = "a" * 64
TEXT = "Youth unemployment was 16 percent in the modeled 2025 estimate."


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def _run() -> RetrievalRun:
    evidence = RetrievedEvidence(
        passage_id="sha256:" + "b" * 64,
        source_id="wb-youth-unemployment-1524-2015-2025",
        title="Youth unemployment",
        publisher="World Bank Data",
        source_uri="https://data.worldbank.org/indicator/SL.UEM.1524.ZS",
        text=TEXT,
        source_content_sha256=HASH,
        locations=(
            BlockLocation(
                page_number=1,
                block_id="row:IND:2025",
                start_char=0,
                end_char=len(TEXT),
            ),
        ),
        section_path=("Youth unemployment",),
        rank=1,
        score=0.8,
        bm25_rank=1,
        bm25_score=2.1,
        retrieval_mode="bm25",
        licence="CC BY 4.0",
    )
    return RetrievalRun(
        run_id=UUID("9a734d29-8d52-4afe-97f6-14963f251f1b"),
        index_version=HASH,
        status="found",
        evidence=(evidence,),
        context="evidence",
    )


def _citation(run: RetrievalRun) -> Citation:
    evidence = run.evidence[0]
    return Citation(
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
        retrieval_mode="bm25",
    )


def test_citation_validator_accepts_exact_current_run_excerpt() -> None:
    run = _run()
    registry = RetrievalRunRegistry(ttl_seconds=60, capacity=10)
    registry.register(run)
    validator = CitationValidator(registry)

    result = validator.validate(
        run_id=run.run_id,
        claims=(Claim(claim_id="claim-1", text="Youth unemployment in 2025 was 16 percent."),),
        citations=(_citation(run),),
    )

    assert result.status == "valid"
    assert len(result.accepted) == 1
    assert not result.rejected
    assert not result.uncovered_claim_ids


def test_citation_validator_rejects_fabricated_ids_and_non_exact_quotes() -> None:
    run = _run()
    registry = RetrievalRunRegistry(ttl_seconds=60, capacity=10)
    registry.register(run)
    validator = CitationValidator(registry)
    claim = Claim(claim_id="claim-1", text="Youth rate was 16 percent.")
    fabricated = _citation(run).model_copy(update={"passage_id": "sha256:" + "c" * 64})
    altered_quote = _citation(run).model_copy(
        update={"excerpt": "Youth unemployment was 99 percent"}
    )

    result = validator.validate(
        run_id=run.run_id, claims=(claim,), citations=(fabricated, altered_quote)
    )

    assert result.status == "invalid"
    assert {item.reason_code for item in result.rejected} == {
        "PASSAGE_NOT_RETURNED",
        "QUOTE_NOT_EXACT",
    }


def test_citation_validator_rejects_source_location_and_duplicate_mismatches() -> None:
    run = _run()
    registry = RetrievalRunRegistry(ttl_seconds=60, capacity=10)
    registry.register(run)
    validator = CitationValidator(registry)
    claim = Claim(claim_id="claim-1", text="Youth rate was 16 percent.")
    source_mismatch = _citation(run).model_copy(update={"source_id": "other-source"})
    location_mismatch = _citation(run).model_copy(update={"page_start": 2, "page_end": 2})
    exact = _citation(run)

    result = validator.validate(
        run_id=run.run_id,
        claims=(claim,),
        citations=(source_mismatch, location_mismatch, exact, exact),
    )

    assert {item.reason_code for item in result.rejected} == {
        "SOURCE_MISMATCH",
        "LOCATION_MISMATCH",
        "DUPLICATE_CITATION",
    }
    assert result.status == "invalid"


def test_citation_validator_rejects_unknown_and_expired_runs() -> None:
    clock = FakeClock()
    registry = RetrievalRunRegistry(ttl_seconds=60, capacity=10, clock=clock)
    run = _run()
    registry.register(run)
    validator = CitationValidator(registry)
    claim = Claim(claim_id="claim-1", text="Youth rate was 16 percent.")
    citation = _citation(run)

    unknown = validator.validate(
        run_id=UUID("00000000-0000-4000-8000-000000000000"),
        claims=(claim,),
        citations=(citation,),
    )
    clock.value += 61
    expired = validator.validate(run_id=run.run_id, claims=(claim,), citations=(citation,))

    assert unknown.rejected[0].reason_code == "RUN_NOT_FOUND"
    assert expired.rejected[0].reason_code == "RUN_NOT_FOUND"
