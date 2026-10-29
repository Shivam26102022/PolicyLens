from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from policylens.retrieval.models import Citation, RetrievalRequest, StrictModel, StructuredRowKey

AgentStatus = Literal[
    "answered",
    "clarification_required",
    "abstained",
    "conflict",
    "blocked",
    "failed_safe",
]
AgentDraftStatus = Literal["answered", "clarification_required", "abstained", "conflict", "blocked"]
ReasoningEffort = Literal["none", "low", "medium", "high"]


class AgentRunState(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    RETRIEVING = "retrieving"
    ASSESSING = "assessing"
    TOOL_EXECUTION = "tool_execution"
    OUTPUT_VALIDATION = "output_validation"
    CITATION_VALIDATION = "citation_validation"
    ANSWERED = "answered"
    CLARIFICATION_REQUIRED = "clarification_required"
    ABSTAINED = "abstained"
    CONFLICT = "conflict"
    BLOCKED = "blocked"
    FAILED_SAFE = "failed_safe"


AgentErrorCode = Literal[
    "INVALID_REQUEST",
    "AMBIGUOUS_REQUEST",
    "OUT_OF_SCOPE",
    "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_EVIDENCE",
    "RETRIEVAL_UNAVAILABLE",
    "MODEL_UNAVAILABLE",
    "MCP_UNAVAILABLE",
    "MCP_TIMEOUT",
    "MCP_IDENTITY_MISMATCH",
    "MCP_CAPABILITY_MISMATCH",
    "MCP_SCHEMA_INVALID",
    "MCP_MALFORMED_RESPONSE",
    "MCP_RESOURCE_NOT_FOUND",
    "MCP_CATALOG_STALE",
    "MCP_INTERNAL_ERROR",
    "MCP_PASSAGE_MISMATCH",
    "TOOL_INVALID_ARGUMENTS",
    "TOOL_MALFORMED_RESPONSE",
    "TOOL_BUDGET_EXCEEDED",
    "TOOL_PERMISSION_DENIED",
    "OUTPUT_SCHEMA_INVALID",
    "CITATION_INVALID",
    "POLICY_BLOCKED",
    "INTERNAL_ERROR",
]
AgentEventType = Literal[
    "state_transition",
    "retrieval_completed",
    "reranking_completed",
    "mcp_resource_started",
    "mcp_resource_completed",
    "tool_started",
    "tool_completed",
    "model_started",
    "model_completed",
    "output_validated",
    "citations_validated",
    "terminal",
    "session_context_loaded",
    "memory_retrieval_completed",
    "session_turn_persisted",
    "memory_write_completed",
]
ModelProviderName = Literal["openai", "mlx"]
ModelRoute = Literal["openai_responses", "openai_chat_completions", "mlx_chat_completions"]


class ModelCapabilitySet(StrictModel):
    native_tool_calls: bool
    native_json_schema: bool
    host_action_envelope: bool
    streaming: bool
    usage_reporting: bool


class ModelLimits(StrictModel):
    max_input_chars: int = Field(ge=1, le=50000)
    max_output_tokens: int = Field(ge=1, le=8000)
    timeout_seconds: float = Field(gt=0, le=300)


class ModelCapabilities(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provider: ModelProviderName
    model_id: str = Field(min_length=1, max_length=300)
    route: ModelRoute
    ready: bool
    capabilities: ModelCapabilitySet
    limits: ModelLimits
    server_version: str | None = Field(default=None, max_length=100)
    platform: str = Field(min_length=1, max_length=200)
    limitations: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_route_provider(self) -> ModelCapabilities:
        if (self.provider == "mlx") != (self.route == "mlx_chat_completions"):
            raise ValueError("MLX provider and route must agree")
        return self


class ModelUsage(StrictModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    memory_bytes: int | None = Field(default=None, ge=0)


class AgentModelUsage(ModelUsage):
    requests: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class ModelRunMetadata(StrictModel):
    provider: ModelProviderName
    model_id: str = Field(min_length=1, max_length=300)
    prompt_version: str = Field(min_length=1, max_length=100)
    latency_ms: float = Field(ge=0)
    usage: AgentModelUsage
    capabilities: ModelCapabilities
    reasoning_effort: ReasoningEffort = "none"
    reasoning_summary: str | None = Field(default=None, max_length=4000)
    fallback_decision: Literal["none"] = "none"

    @model_validator(mode="after")
    def validate_provider_identity(self) -> ModelRunMetadata:
        if (
            self.provider != self.capabilities.provider
            or self.model_id != self.capabilities.model_id
        ):
            raise ValueError("run metadata must match the selected provider descriptor")
        return self


class AgentConversationMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AgentSessionContext(StrictModel):
    session_id: UUID
    turn_id: UUID
    persisted: bool
    long_memory_enabled: bool = False
    memory_retrieval_status: Literal[
        "used", "empty", "disabled", "unavailable", "embedding_mismatch"
    ] = "disabled"
    retrieved_memory_count: int = Field(default=0, ge=0, le=5)
    memory_write_status: Literal["stored", "skipped", "failed"] = "skipped"


class AgentAnswerRequest(RetrievalRequest):
    """Validated request for one bounded agent run."""

    provider: ModelProviderName | None = None
    allow_external_provider: bool = False
    allow_external_embeddings: bool = False
    reasoning_effort: ReasoningEffort = "none"
    session_id: UUID | None = None
    conversation: tuple[AgentConversationMessage, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def validate_provider_consent_shape(self) -> AgentAnswerRequest:
        if self.provider == "mlx" and self.allow_external_provider:
            raise ValueError("local provider cannot request external processing consent")
        if sum(len(message.content) for message in self.conversation) > 12000:
            raise ValueError("conversation context exceeds its configured character limit")
        return self


class AgentEvidenceReference(StrictModel):
    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    excerpt: str = Field(min_length=1, max_length=500)


class AgentDraftClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "For corpus claims, provide a concise factual claim supported by the exact excerpts "
            "in evidence. For calculation-only claims, the host replaces this text with a "
            "deterministic calculation summary."
        ),
    )
    evidence: tuple[AgentEvidenceReference, ...] = Field(default=(), max_length=8)
    calculation_ids: tuple[UUID, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_provenance(self) -> AgentDraftClaim:
        if not self.evidence and not self.calculation_ids:
            raise ValueError("each claim requires a citation or calculation reference")
        return self


class StandaloneQuery(StrictModel):
    query: str = Field(min_length=1, max_length=500)


class AgentDraftConflict(StrictModel):
    summary: str = Field(min_length=1, max_length=1000)
    claim_ids: tuple[str, ...] = Field(min_length=2, max_length=8)


class AgentDraft(StrictModel):
    status: AgentDraftStatus
    claims: tuple[AgentDraftClaim, ...] = Field(default=(), max_length=12)
    clarification_question: str | None = Field(default=None, max_length=1000)
    abstention_reason: str | None = Field(default=None, max_length=1000)
    conflicts: tuple[AgentDraftConflict, ...] = Field(default=(), max_length=5)
    uncertainty: tuple[str, ...] = Field(default=(), max_length=10)
    limitations: tuple[str, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def validate_status(self) -> AgentDraft:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique")
        if self.status == "answered":
            if not self.claims:
                raise ValueError("answered draft requires at least one claim")
            if self.clarification_question or self.abstention_reason or self.conflicts:
                raise ValueError("answered draft contains fields for another status")
        elif self.status == "clarification_required":
            if self.claims or not (
                self.clarification_question and self.clarification_question.strip()
            ):
                raise ValueError("clarification status requires one focused question and no claims")
        elif self.status == "abstained":
            if self.claims or not (self.abstention_reason and self.abstention_reason.strip()):
                raise ValueError("abstained draft requires a reason and no claims")
        elif self.status == "conflict":
            if not self.conflicts or len(self.claims) < 2:
                raise ValueError("conflict draft requires conflict sides and claims")
            if any(not set(item.claim_ids).issubset(set(claim_ids)) for item in self.conflicts):
                raise ValueError("conflict sides must reference draft claims")
        elif self.status == "blocked":
            if self.claims or not (self.abstention_reason and self.abstention_reason.strip()):
                raise ValueError("blocked draft requires a reason and no claims")
        return self


class AgentClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "Concise factual claim linked to exact cited excerpts, or a host-generated "
            "deterministic calculation summary."
        ),
    )
    citations: tuple[Citation, ...] = Field(default=(), max_length=8)
    calculation_ids: tuple[UUID, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_claim_provenance(self) -> AgentClaim:
        if not self.citations and not self.calculation_ids:
            raise ValueError("each claim requires a citation or calculation reference")
        if any(citation.claim_id != self.claim_id for citation in self.citations):
            raise ValueError("citation claim IDs must match the claim")
        return self


class AgentCalculationEvidence(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    row_keys: tuple[StructuredRowKey, ...] = Field(min_length=1, max_length=100)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentCalculationRow(StrictModel):
    geography: str | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=100)


class AgentCalculationRecord(StrictModel):
    calculation_id: UUID = Field(default_factory=uuid4)
    tool_call_id: UUID
    tool_name: Literal["query_statistics"]
    operation: str = Field(min_length=1, max_length=100)
    formula: str = Field(min_length=1, max_length=500)
    rounding: str = Field(min_length=1, max_length=200)
    rows: tuple[AgentCalculationRow, ...] = Field(max_length=100)
    evidence: tuple[AgentCalculationEvidence, ...] = Field(min_length=1, max_length=20)
    warnings: tuple[str, ...] = Field(default=(), max_length=20)


class AgentConflict(StrictModel):
    summary: str = Field(min_length=1, max_length=1000)
    claim_ids: tuple[str, ...] = Field(min_length=2, max_length=8)


class AgentEvent(StrictModel):
    sequence: int = Field(ge=1, le=200)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    state: AgentRunState
    event_type: AgentEventType
    status: Literal["started", "succeeded", "failed", "skipped"]
    tool_name: Literal["query_statistics"] | None = None
    tool_call_id: UUID | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0, le=3)
    item_count: int | None = Field(default=None, ge=0, le=20)
    error_code: str | None = Field(default=None, max_length=80)
    reranker_model: str | None = Field(default=None, max_length=300)
    model_route: ModelRoute | None = None
    reasoning_effort: ReasoningEffort | None = None
    model_usage: AgentModelUsage | None = None
    reasoning_summary: str | None = Field(default=None, max_length=4000)


class AgentAnswerResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    trace_id: UUID
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: AgentStatus
    answer: str | None = Field(default=None, max_length=12000)
    claims: tuple[AgentClaim, ...] = Field(default=(), max_length=12)
    calculations: tuple[AgentCalculationRecord, ...] = Field(default=(), max_length=8)
    uncertainty: tuple[str, ...] = Field(default=(), max_length=10)
    conflicts: tuple[AgentConflict, ...] = Field(default=(), max_length=5)
    clarification_question: str | None = Field(default=None, max_length=1000)
    abstention_reason: str | None = Field(default=None, max_length=1000)
    limitations: tuple[str, ...] = Field(default=(), max_length=10)
    provider: ModelProviderName
    model: str = Field(min_length=1, max_length=300)
    session_context: AgentSessionContext | None = None
    model_metadata: ModelRunMetadata | None = None
    prompt_version: Literal["agent-v1", "agent-v2", "agent-v3", "agent-v4"] = "agent-v1"
    events: tuple[AgentEvent, ...] = Field(max_length=200)
    error_code: AgentErrorCode | None = None

    @model_validator(mode="after")
    def validate_terminal_status(self) -> AgentAnswerResponse:
        if self.model_metadata is not None and (
            self.model_metadata.provider != self.provider
            or self.model_metadata.model_id != self.model
        ):
            raise ValueError("model metadata must match the selected response provider")
        calculation_ids = {item.calculation_id for item in self.calculations}
        if any(not set(claim.calculation_ids).issubset(calculation_ids) for claim in self.claims):
            raise ValueError("claims cannot reference unknown calculation records")
        claim_ids = {claim.claim_id for claim in self.claims}

        if self.status == "answered":
            if not self.claims or self.error_code is not None:
                raise ValueError("answered response requires at least one claim and no error")
        elif self.status == "clarification_required":
            if self.claims or not self.clarification_question or self.error_code is not None:
                raise ValueError(
                    "clarification response requires one focused question and no claims"
                )
        elif self.status == "abstained":
            if self.claims or not self.abstention_reason:
                raise ValueError("abstained response requires a reason and no claims")
        elif self.status == "conflict":
            if not self.conflicts or len(self.claims) < 2 or self.error_code is not None:
                raise ValueError("conflicts require at least two sides and cited claims")
            if any(not set(item.claim_ids).issubset(claim_ids) for item in self.conflicts):
                raise ValueError("conflict sides must reference returned claims")
        elif self.status == "blocked":
            if self.claims or self.error_code is None or not self.abstention_reason:
                raise ValueError("blocked response requires a reason and error code")
        elif self.status == "failed_safe":
            if self.claims or self.error_code is None:
                raise ValueError("blocked/failed-safe responses require an error and no claims")
        return self
