from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from threading import RLock
from time import monotonic
from typing import Literal
from uuid import UUID

from policylens.retrieval.models import (
    Citation,
    CitationValidationRequest,
    CitationValidationResult,
    Claim,
    RejectedCitation,
    RetrievalRun,
    RetrievedEvidence,
)

CitationRejectionReason = Literal[
    "RUN_NOT_FOUND",
    "PASSAGE_NOT_RETURNED",
    "CLAIM_NOT_FOUND",
    "SOURCE_MISMATCH",
    "HASH_MISMATCH",
    "LOCATION_MISMATCH",
    "QUOTE_NOT_EXACT",
    "QUOTE_TOO_LONG",
    "DUPLICATE_CITATION",
]


class RetrievalRunRegistry:
    """Bounded in-memory evidence registry used only for current-run citation checks."""

    def __init__(
        self,
        ttl_seconds: int = 900,
        capacity: int = 1000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds < 1 or capacity < 1:
            raise ValueError("registry TTL and capacity must be positive")
        self._ttl_seconds = ttl_seconds
        self._capacity = capacity
        self._clock = clock
        self._runs: OrderedDict[UUID, tuple[float, RetrievalRun]] = OrderedDict()
        self._lock = RLock()

    def _purge_expired(self, now: float) -> None:
        expired = [
            run_id
            for run_id, (created_at, _run) in self._runs.items()
            if now - created_at >= self._ttl_seconds
        ]
        for run_id in expired:
            self._runs.pop(run_id, None)

    def register(self, run: RetrievalRun) -> None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            self._runs[run.run_id] = (now, run)
            self._runs.move_to_end(run.run_id)
            while len(self._runs) > self._capacity:
                self._runs.popitem(last=False)

    def get(self, run_id: UUID) -> RetrievalRun | None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            item = self._runs.get(run_id)
            return item[1] if item is not None else None


class CitationValidator:
    def __init__(self, registry: RetrievalRunRegistry, max_excerpt_chars: int = 500) -> None:
        if max_excerpt_chars < 1 or max_excerpt_chars > 500:
            raise ValueError("max_excerpt_chars must be between 1 and 500")
        self._registry = registry
        self._max_excerpt_chars = max_excerpt_chars

    def validate_request(self, request: CitationValidationRequest) -> CitationValidationResult:
        return self.validate(request.run_id, request.claims, request.citations)

    def validate(
        self,
        run_id: UUID,
        claims: tuple[Claim, ...],
        citations: tuple[Citation, ...],
    ) -> CitationValidationResult:
        run = self._registry.get(run_id)
        if run is None:
            rejected_for_unknown_run = tuple(
                RejectedCitation(citation=citation, reason_code="RUN_NOT_FOUND")
                for citation in citations
            )
            uncovered = tuple(claim.claim_id for claim in claims)
            return CitationValidationResult(
                run_id=run_id,
                status="invalid",
                accepted=(),
                rejected=rejected_for_unknown_run,
                uncovered_claim_ids=uncovered,
            )

        claims_by_id = {claim.claim_id: claim for claim in claims}
        evidence_by_id: dict[str, RetrievedEvidence] = {
            evidence.passage_id: evidence for evidence in run.evidence
        }
        accepted: list[Citation] = []
        rejected: list[RejectedCitation] = []
        accepted_claim_ids: set[str] = set()
        seen: set[tuple[str, str, str]] = set()

        for citation in citations:
            key = (citation.claim_id, citation.passage_id, citation.excerpt)
            reason = (
                "DUPLICATE_CITATION"
                if key in seen
                else self._validate_one(citation, claims_by_id, evidence_by_id)
            )
            if reason is not None:
                rejected.append(RejectedCitation(citation=citation, reason_code=reason))
                continue
            seen.add(key)
            accepted.append(citation)
            accepted_claim_ids.add(citation.claim_id)

        uncovered = tuple(
            claim_id for claim_id in claims_by_id if claim_id not in accepted_claim_ids
        )
        status: Literal["valid", "invalid"] = (
            "valid" if not rejected and not uncovered else "invalid"
        )
        return CitationValidationResult(
            run_id=run_id,
            status=status,
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            uncovered_claim_ids=uncovered,
        )

    def _validate_one(
        self,
        citation: Citation,
        claims: dict[str, Claim],
        evidence_by_id: dict[str, RetrievedEvidence],
    ) -> CitationRejectionReason | None:
        if citation.claim_id not in claims:
            return "CLAIM_NOT_FOUND"
        evidence = evidence_by_id.get(citation.passage_id)
        if evidence is None:
            return "PASSAGE_NOT_RETURNED"
        if citation.source_id != evidence.source_id or citation.title != evidence.title:
            return "SOURCE_MISMATCH"
        if citation.source_uri != evidence.source_uri:
            return "SOURCE_MISMATCH"
        if citation.source_content_sha256 != evidence.source_content_sha256:
            return "HASH_MISMATCH"
        if (
            citation.retrieval_rank != evidence.rank
            or citation.retrieval_mode != evidence.retrieval_mode
        ):
            return "LOCATION_MISMATCH"
        if not math.isclose(citation.retrieval_score, evidence.score, rel_tol=0.0, abs_tol=1e-9):
            return "LOCATION_MISMATCH"
        if evidence.row_key is not None:
            if (
                citation.row_key != evidence.row_key
                or citation.page_start is not None
                or citation.page_end is not None
            ):
                return "LOCATION_MISMATCH"
            if citation.section_path != evidence.section_path:
                return "LOCATION_MISMATCH"
        else:
            if not evidence.locations or citation.row_key is not None:
                return "LOCATION_MISMATCH"
            pages = [location.page_number for location in evidence.locations]
            if citation.page_start != min(pages) or citation.page_end != max(pages):
                return "LOCATION_MISMATCH"
            if citation.section_path != evidence.section_path:
                return "LOCATION_MISMATCH"
        if len(citation.excerpt) > self._max_excerpt_chars:
            return "QUOTE_TOO_LONG"
        if not citation.excerpt or citation.excerpt not in evidence.text:
            return "QUOTE_NOT_EXACT"
        return None
