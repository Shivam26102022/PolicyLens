from __future__ import annotations

from typing import Literal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from policylens.agent_runtime.models import (
    AgentAnswerRequest,
    AgentAnswerResponse,
    AgentClaim,
    AgentConflict,
    AgentConversationMessage,
    AgentDraft,
    AgentDraftClaim,
    AgentEvent,
    AgentEvidenceReference,
    AgentRunState,
)
from policylens.retrieval.models import Citation

HASH = "a" * 64
PASSAGE_ID = "sha256:" + "b" * 64
INDEX_VERSION = "c" * 64


def _citation(claim_id: str = "claim-1", excerpt: str = "Exact supporting excerpt") -> Citation:
    return Citation(
        claim_id=claim_id,
        source_id="source-1",
        title="Source title",
        passage_id=PASSAGE_ID,
        excerpt=excerpt,
        source_content_sha256=HASH,
        retrieval_rank=1,
        retrieval_score=0.5,
        retrieval_mode="hybrid",
    )


def test_agent_draft_requires_claim_provenance_for_answered_status() -> None:
    draft = AgentDraft(
        status="answered",
        claims=(
            AgentDraftClaim(
                claim_id="claim-1",
                text="A supported claim.",
                evidence=(
                    AgentEvidenceReference(
                        passage_id=PASSAGE_ID,
                        excerpt="Exact supporting excerpt",
                    ),
                ),
            ),
        ),
    )

    assert draft.status == "answered"
    assert draft.claims[0].evidence[0].passage_id == PASSAGE_ID

    with pytest.raises(ValidationError, match="citation or calculation"):
        AgentDraft(
            status="answered",
            claims=(AgentDraftClaim(claim_id="claim-1", text="Unsupported claim."),),
        )


def test_agent_draft_enforces_clarification_question() -> None:
    with pytest.raises(ValidationError, match="focused question"):
        AgentDraft(status="clarification_required", claims=())


def test_agent_draft_enforces_abstention_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        AgentDraft(status="abstained", claims=())


def test_agent_draft_blocked_requires_reason_and_no_claims() -> None:
    with pytest.raises(ValidationError, match="blocked draft requires a reason"):
        AgentDraft(status="blocked", claims=())


def test_agent_draft_enforces_conflict_sides() -> None:
    with pytest.raises(ValidationError, match="conflict sides"):
        AgentDraft(status="conflict", claims=())


def test_agent_response_requires_provider_metadata_and_supported_claims() -> None:
    claim = AgentClaim(
        claim_id="claim-1",
        text="A concise paraphrase of the supporting evidence.",
        citations=(_citation(),),
    )
    response = AgentAnswerResponse(
        run_id=uuid4(),
        trace_id=uuid4(),
        index_version=INDEX_VERSION,
        status="answered",
        answer=claim.text,
        claims=(claim,),
        provider="openai",
        model="gpt-6-luna",
        prompt_version="agent-v2",
        events=(),
    )

    assert response.status == "answered"
    assert response.model == "gpt-6-luna"
    assert response.prompt_version == "agent-v2"

    with pytest.raises(ValidationError, match="requires at least one claim"):
        AgentAnswerResponse(
            run_id=uuid4(),
            trace_id=uuid4(),
            index_version=INDEX_VERSION,
            status="answered",
            answer=None,
            claims=(),
            provider="openai",
            model="gpt-6-luna",
            prompt_version="agent-v1",
            events=(),
        )


def test_conflict_requires_two_cited_sides() -> None:
    claims = (
        AgentClaim(
            claim_id="claim-1",
            text="Side one.",
            citations=(_citation("claim-1", "Side one."),),
        ),
        AgentClaim(
            claim_id="claim-2",
            text="Side two.",
            citations=(_citation("claim-2", "Side two."),),
        ),
    )
    conflict = AgentConflict(summary="Sources disagree.", claim_ids=("claim-1", "claim-2"))
    response = AgentAnswerResponse(
        run_id=uuid4(),
        trace_id=uuid4(),
        index_version=INDEX_VERSION,
        status="conflict",
        answer=None,
        claims=claims,
        conflicts=(conflict,),
        provider="openai",
        model="gpt-6-luna",
        prompt_version="agent-v1",
        events=(),
    )

    assert response.conflicts[0].claim_ids == ("claim-1", "claim-2")
    with pytest.raises(ValidationError, match="conflicts require at least two sides"):
        AgentAnswerResponse(
            run_id=uuid4(),
            trace_id=uuid4(),
            index_version=INDEX_VERSION,
            status="conflict",
            answer=None,
            claims=(claims[0],),
            provider="openai",
            model="gpt-6-luna",
            prompt_version="agent-v1",
            events=(),
        )


def test_blocked_response_requires_reason_and_error_code() -> None:
    with pytest.raises(ValidationError, match="blocked response requires a reason"):
        AgentAnswerResponse(
            run_id=uuid4(),
            trace_id=uuid4(),
            index_version=INDEX_VERSION,
            status="blocked",
            answer=None,
            claims=(),
            provider="openai",
            model="gpt-6-luna",
            prompt_version="agent-v1",
            events=(),
            error_code="POLICY_BLOCKED",
        )


def test_session_request_supports_five_complete_pairs() -> None:
    roles: tuple[Literal["user"], Literal["assistant"]] = ("user", "assistant")
    conversation = tuple(
        AgentConversationMessage(role=role, content=f"{role} message {index}")
        for index in range(5)
        for role in roles
    )
    request = AgentAnswerRequest(
        query="follow-up",
        mode="hybrid",
        session_id=uuid4(),
        conversation=conversation,
    )
    event = AgentEvent(
        sequence=1,
        state=AgentRunState.RECEIVED,
        event_type="session_context_loaded",
        status="succeeded",
    )

    assert len(request.conversation) == 10
    assert request.session_id is not None
    assert event.event_type == "session_context_loaded"

    with pytest.raises(ValidationError):
        AgentAnswerRequest(
            query="follow-up",
            mode="hybrid",
            conversation=conversation + (AgentConversationMessage(role="user", content="extra"),),
        )
