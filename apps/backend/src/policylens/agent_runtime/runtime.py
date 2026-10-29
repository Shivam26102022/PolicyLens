from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Callable
from time import monotonic
from typing import Literal, Protocol
from uuid import UUID

from agents import Runner
from pydantic import ValidationError

from policylens.agent_runtime.gateway import (
    ModelGateway,
    ModelGatewayContext,
    ModelGatewayResult,
    ProviderBuilder,
    RuntimeRunner,
    build_model_gateway,
)
from policylens.agent_runtime.models import (
    AgentAnswerRequest,
    AgentAnswerResponse,
    AgentCalculationRecord,
    AgentClaim,
    AgentConflict,
    AgentDraft,
    AgentErrorCode,
    AgentEvent,
    AgentEvidenceReference,
    AgentRunState,
    AgentStatus,
    ModelRunMetadata,
)
from policylens.agent_runtime.provider import (
    AgentConfigurationError,
    build_openai_agent_model,
)
from policylens.agent_runtime.state import AgentRunLedger, AgentStateError
from policylens.agent_runtime.tools import (
    AgentToolAdapterError,
    AgentToolExecutionError,
    StatisticsToolAdapter,
)
from policylens.conversations.memory import ConversationMemory
from policylens.mcp.models import PassageRecord
from policylens.retrieval.citations import CitationValidator
from policylens.retrieval.models import Citation, Claim, RetrievalRun, RetrievedEvidence
from policylens.retrieval.search import RetrievalError
from policylens.settings import PROJECT_ROOT, AppSettings

_PROMPT_VERSION: Literal["agent-v4"] = "agent-v4"
_PROMPT_PATH = PROJECT_ROOT / "prompts/agent/system-v4.md"
_REWRITE_PROMPT_PATH = PROJECT_ROOT / "prompts/agent/query-rewrite-v1.md"
_MAX_AGENT_INPUT_CHARS = 50000
_LOGGER = logging.getLogger("policylens-api")
_DRAWING_REQUEST = re.compile(
    r"\b(?:draw|paint|sketch|illustrate)\s+"
    r"(?:(?:me|my|our|a|an|the)\s+)?"
    r"(?:[\w-]+\s+)?"
    r"(?:cat|dog|animal|person|character|landscape|scene|face|image|picture|"
    r"illustration|drawing|painting|photo|portrait|logo|cartoon|artwork|graphic)\b",
    re.IGNORECASE,
)
_IMAGE_CREATION_REQUEST = re.compile(
    r"\b(?:create|generate|make)\b.{0,80}\b"
    r"(?:image|picture|illustration|drawing|painting|photo|portrait|logo|"
    r"cartoon|artwork|graphic|avatar|animation)\b",
    re.IGNORECASE | re.DOTALL,
)
_INSTRUCTION_INJECTION = re.compile(
    r"\b(?:system\s+override|ignore|disregard|forget|override)\b"
    r"[^.!?\n]{0,200}\b(?:instructions?|rules?|safeguards?|policy)\b[^.!?\n]*"
    r"|\b(?:reveal|show|print|disclose|expose)\b[^.!?\n]{0,120}"
    r"\b(?:hidden|system|developer|internal)\s+(?:instructions?|prompt|message)\b[^.!?\n]*"
    r"|\b(?:call|invoke|use)\b[^.!?\n]{0,80}"
    r"\b(?:shell|terminal|exec(?:ution)?)\s+(?:tool|command)\b[^.!?\n]*",
    re.IGNORECASE,
)
_SENSITIVE_DATA_REQUEST = re.compile(
    r"\b(?:named individuals?|personal(?:ly identifiable)?|private|confidential|classified)\b"
    r"[^.!?\n]{0,100}\b(?:records?|data|histories|history|identifiers?|benefits?|"
    r"employment|microdata|salary)\b"
    r"|\b(?:passwords?|api keys?|credentials?|secrets?)\b",
    re.IGNORECASE,
)
_INSTRUCTION_REMOVED = "[instruction-like text omitted]"


def _sanitize_untrusted_text(text: str) -> tuple[str, bool]:
    sanitized, count = _INSTRUCTION_INJECTION.subn(_INSTRUCTION_REMOVED, text)
    return sanitized, count > 0


def _sanitized_query(query: str) -> tuple[str, bool]:
    sanitized, detected = _sanitize_untrusted_text(query)
    sanitized = sanitized.replace(_INSTRUCTION_REMOVED, "")
    if detected:
        sanitized = re.sub(r"(?<=[.!?])\s*[.!?]+$", "", sanitized)
        if not re.search(r"[A-Za-z0-9]", sanitized):
            sanitized = ""
    return sanitized.strip(" \t\r\n,;:-"), detected


def _requests_image_generation(query: str) -> bool:
    return bool(_DRAWING_REQUEST.search(query) or _IMAGE_CREATION_REQUEST.search(query))


def _is_provider_content_filter(error: Exception) -> bool:
    if getattr(error, "status_code", None) != 400:
        return False
    code = getattr(error, "code", None)
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict):
            code = inner.get("code", code)
    return code in {"content_filter", "ResponsibleAIPolicyViolation"} or "content_filter" in str(
        error
    )


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _material_numbers(text: str) -> set[str]:
    numbers: set[str] = set()
    for token in _NUMBER.findall(text):
        normalized = token.replace(",", "").rstrip(".")
        bare = normalized.rstrip("%")
        is_year = bare.isdigit() and len(bare) == 4 and 1900 <= int(bare) <= 2100
        small_integer = bare.isdigit() and len(bare) < 2 and not normalized.endswith("%")
        if bare and not is_year and not small_integer:
            numbers.add(bare)
    return numbers


def _numbers_supported(claim_text: str, excerpts: list[str]) -> bool:
    cited = {number for excerpt in excerpts for number in _material_numbers(excerpt)}
    return _material_numbers(claim_text) <= cited


_CALCULATION_REQUEST = re.compile(
    r"\b(mean|average|median|sum|calculate|compute|statistic\w*|percentage[- ]point)\b", re.I
)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_STATISTICS_YEAR_RANGE = (2015, 2025)


def _requests_out_of_range_calculation_years(query: str) -> bool:
    if not _CALCULATION_REQUEST.search(query):
        return False
    low, high = _STATISTICS_YEAR_RANGE
    return any(not low <= int(year) <= high for year in _YEAR.findall(query))


_FORMAT_REPAIR_MESSAGE = (
    "Your previous reply was not a valid draft object. Reply only with the structured draft. "
    "If the request is out of scope, asks for restricted sources or personal decisions, or "
    "cannot be supported by evidence, return status blocked or abstained with an "
    "abstention_reason and no claims instead of prose. This is the only repair attempt."
)


def _repair_message(error: Exception) -> str:
    reason = getattr(error, "reason_code", "VALIDATION_FAILED")
    return (
        f"Your previous draft failed host citation validation ({reason}). Return a corrected "
        "draft: copy each excerpt exactly and contiguously from a passage in untrusted_evidence, "
        "every figure in a claim must appear verbatim in its cited excerpt, so choose the exact "
        "sentence that contains the figure rather than the start of the passage, "
        "use only passage IDs from this run and calculation IDs already returned by tools, and "
        "drop any claim you cannot support. Abstain if nothing can be supported. This is the "
        "only repair attempt."
    )


def _log_model_failure(trace_id: UUID, error: Exception) -> None:
    status_code = getattr(error, "status_code", None)
    _LOGGER.warning(
        "Agent model call failed safely (%s, http_status=%s)",
        type(error).__name__,
        status_code if isinstance(status_code, int) else None,
        extra={
            "event": "agent_model_failed",
            "trace_id": str(trace_id),
            "error_code": "MODEL_UNAVAILABLE",
            "exception_type": type(error).__name__,
            "http_status": status_code
            if isinstance(status_code, int) and not isinstance(status_code, bool)
            else None,
        },
    )


class AgentCitationValidationError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class AgentRetrievalService(Protocol):
    def search(self, request: AgentAnswerRequest) -> RetrievalRun: ...


class AgentPassageReader(Protocol):
    async def read_passages(
        self,
        passage_keys: tuple[tuple[str, str], ...],
    ) -> tuple[PassageRecord, ...]: ...


class AgentExecutionError(RuntimeError):
    def __init__(self, code: AgentErrorCode, trace_id: UUID) -> None:
        super().__init__(code)
        self.code = code
        self.trace_id = trace_id


class AgentRuntime:
    def __init__(
        self,
        settings: AppSettings,
        retrieval_service: AgentRetrievalService,
        citation_validator: CitationValidator,
        *,
        statistics_adapter: StatisticsToolAdapter | None = None,
        passage_reader: AgentPassageReader | None = None,
        runner: RuntimeRunner | None = None,
        provider_builder: ProviderBuilder = build_openai_agent_model,
        model_gateway: ModelGateway | None = None,
        model_gateway_factory: Callable[..., ModelGateway] = build_model_gateway,
        timeout_seconds: float | None = None,
        prompt: str | None = None,
    ) -> None:
        self._settings = settings
        self._retrieval_service = retrieval_service
        self._citation_validator = citation_validator
        self._statistics_adapter = statistics_adapter
        self._passage_reader = passage_reader
        self._runner = runner or Runner.run
        self._provider_builder = provider_builder
        self._model_gateway = model_gateway
        self._model_gateway_factory = model_gateway_factory
        self._timeout_seconds = timeout_seconds or settings.request_timeout_seconds
        if self._timeout_seconds <= 0:
            raise ValueError("agent timeout must be positive")
        if prompt is None:
            try:
                prompt = _PROMPT_PATH.read_text(encoding="utf-8")
            except OSError as error:
                raise AgentConfigurationError(
                    "The versioned agent prompt is unavailable"
                ) from error
        if not prompt.strip():
            raise AgentConfigurationError("The versioned agent prompt is empty")
        self._prompt = prompt

    def _model_id(self) -> str:
        model_id = (
            self._settings.effective_openai_model
            if self._settings.model_provider == "openai"
            else self._settings.mlx_model
        )
        return model_id or "unconfigured"

    @staticmethod
    def _validate_mcp_passages(
        evidence: tuple[RetrievedEvidence, ...],
        passages: tuple[PassageRecord, ...],
    ) -> None:
        if len(evidence) != len(passages):
            raise AgentToolAdapterError("MCP_PASSAGE_MISMATCH", transient=False)

        for indexed, passage in zip(evidence, passages, strict=True):
            text_hash = hashlib.sha256(passage.text.encode("utf-8")).hexdigest()
            if (
                passage.source_id != indexed.source_id
                or passage.passage_id != indexed.passage_id
                or passage.title != indexed.title
                or passage.publisher != indexed.publisher
                or passage.source_uri != indexed.source_uri
                or passage.text != indexed.text
                or text_hash != passage.text_sha256
                or passage.source_content_sha256 != indexed.source_content_sha256
                or passage.locations != indexed.locations
                or passage.row_key != indexed.row_key
                or passage.section_path != indexed.section_path
                or passage.licence != indexed.licence
                or "retrieval" not in passage.allowed_usage
                or not passage.untrusted
            ):
                raise AgentToolAdapterError("MCP_PASSAGE_MISMATCH", transient=False)

    def _response(
        self,
        run: RetrievalRun,
        ledger: AgentRunLedger,
        status: AgentStatus,
        *,
        answer: str | None = None,
        claims: tuple[AgentClaim, ...] = (),
        calculations: tuple[AgentCalculationRecord, ...] = (),
        uncertainty: tuple[str, ...] = (),
        conflicts: tuple[AgentConflict, ...] = (),
        clarification_question: str | None = None,
        abstention_reason: str | None = None,
        limitations: tuple[str, ...] = (),
        error_code: AgentErrorCode | None = None,
        model_metadata: ModelRunMetadata | None = None,
    ) -> AgentAnswerResponse:
        return AgentAnswerResponse(
            run_id=run.run_id,
            trace_id=ledger.trace_id,
            index_version=run.index_version,
            status=status,
            answer=answer,
            claims=claims,
            calculations=calculations,
            uncertainty=uncertainty,
            conflicts=conflicts,
            clarification_question=clarification_question,
            abstention_reason=abstention_reason,
            limitations=limitations,
            provider=self._settings.model_provider,
            model=self._model_id(),
            model_metadata=model_metadata,
            prompt_version=_PROMPT_VERSION,
            events=ledger.events,
            error_code=error_code,
        )

    def _failed(
        self,
        run: RetrievalRun,
        ledger: AgentRunLedger,
        code: AgentErrorCode,
        model_metadata: ModelRunMetadata | None = None,
    ) -> AgentAnswerResponse:
        if ledger.state not in {
            AgentRunState.ANSWERED,
            AgentRunState.CLARIFICATION_REQUIRED,
            AgentRunState.ABSTAINED,
            AgentRunState.CONFLICT,
            AgentRunState.BLOCKED,
            AgentRunState.FAILED_SAFE,
        }:
            ledger.transition(AgentRunState.FAILED_SAFE)
        ledger.record_event("terminal", status="failed", error_code=code)
        return self._response(
            run,
            ledger,
            "failed_safe",
            error_code=code,
            model_metadata=model_metadata,
        )

    @staticmethod
    def _model_input(
        request: AgentAnswerRequest,
        run: RetrievalRun,
        memory_context: tuple[ConversationMemory, ...] = (),
        repair_feedback: str | None = None,
        user_message: str | None = None,
    ) -> str:
        safe_query, _ = _sanitize_untrusted_text(request.query)
        payload: dict[str, object] = {
            "query": safe_query,
            "untrusted_conversation_context": [
                {
                    "role": message.role,
                    "content": _sanitize_untrusted_text(message.content)[0],
                }
                for message in request.conversation
            ],
            "untrusted_long_term_memory_context": [
                {
                    "session_id": str(memory.session_id),
                    "content": _sanitize_untrusted_text(memory.content)[0],
                }
                for memory in memory_context[:5]
            ],
            "retrieval_run_id": str(run.run_id),
            "index_version": run.index_version,
            "untrusted_evidence": _sanitize_untrusted_text(run.context)[0],
        }
        if user_message is not None:
            payload["user_message"] = _sanitize_untrusted_text(user_message)[0]
        if repair_feedback is not None:
            payload["host_repair_feedback"] = repair_feedback
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > _MAX_AGENT_INPUT_CHARS:
            raise ValueError("bounded agent input exceeds its configured character limit")
        return serialized

    @staticmethod
    def _citation(
        claim_id: str, reference: AgentEvidenceReference, evidence: RetrievedEvidence
    ) -> Citation:
        pages = [location.page_number for location in evidence.locations]
        excerpt = reference.excerpt
        if excerpt not in evidence.text:
            excerpt = evidence.text[:500]
        return Citation(
            claim_id=claim_id,
            source_id=evidence.source_id,
            title=evidence.title,
            source_uri=evidence.source_uri,
            passage_id=evidence.passage_id,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            section_path=evidence.section_path,
            row_key=evidence.row_key,
            excerpt=excerpt,
            source_content_sha256=evidence.source_content_sha256,
            retrieval_rank=evidence.rank,
            retrieval_score=evidence.score,
            retrieval_mode=evidence.retrieval_mode,
        )

    async def _standalone_request(self, request: AgentAnswerRequest) -> AgentAnswerRequest:
        """Let the model resolve a follow-up into a standalone question; fail open."""
        if not request.conversation:
            return request
        try:
            gateway = self._model_gateway or self._model_gateway_factory(
                self._settings,
                runner=self._runner,
                provider_builder=self._provider_builder,
                statistics_adapter=self._statistics_adapter,
            )
            rewrite = getattr(gateway, "rewrite_query", None)
            if rewrite is None:
                return request
            payload = json.dumps(
                {
                    "untrusted_conversation_context": [
                        {"role": m.role, "content": _sanitize_untrusted_text(m.content)[0][:1500]}
                        for m in request.conversation[-6:]
                    ],
                    "latest_message": _sanitize_untrusted_text(request.query)[0],
                },
                ensure_ascii=False,
            )
            rewritten = await rewrite(self._rewrite_prompt(), payload)
        except Exception as error:
            logging.getLogger(__name__).warning(
                "query rewrite failed; using the original message: %s", type(error).__name__
            )
            return request
        safe_query, injected = _sanitized_query(rewritten.strip())
        if injected or not safe_query:
            return request
        return request.model_copy(update={"query": safe_query})

    @staticmethod
    def _rewrite_prompt() -> str:
        return _REWRITE_PROMPT_PATH.read_text(encoding="utf-8")

    async def _run_agent(
        self,
        request: AgentAnswerRequest,
        run: RetrievalRun,
        ledger: AgentRunLedger,
        memory_context: tuple[ConversationMemory, ...],
        repair_feedback: str | None = None,
        user_message: str | None = None,
    ) -> ModelGatewayResult:
        gateway = self._model_gateway or self._model_gateway_factory(
            self._settings,
            runner=self._runner,
            provider_builder=self._provider_builder,
            statistics_adapter=self._statistics_adapter,
        )
        return await gateway.run_agent(
            ModelGatewayContext(
                instructions=self._prompt,
                input=self._model_input(
                    request, run, memory_context, repair_feedback, user_message
                ),
                ledger=ledger,
                statistics_adapter=self._statistics_adapter,
                reasoning_effort=request.reasoning_effort,
            )
        )

    def _validate_citations(
        self, run: RetrievalRun, draft: AgentDraft, ledger: AgentRunLedger
    ) -> tuple[AgentClaim, ...]:
        evidence_by_id = {evidence.passage_id: evidence for evidence in run.evidence}
        calculations_by_id = {record.calculation_id: record for record in ledger.calculations}
        validation_claims: list[Claim] = []
        citations: list[Citation] = []
        claims: list[AgentClaim] = []

        for draft_claim in draft.claims:
            calculation_records = [
                calculations_by_id[calculation_id]
                for calculation_id in draft_claim.calculation_ids
                if calculation_id in calculations_by_id
            ]
            if len(calculation_records) != len(draft_claim.calculation_ids):
                raise AgentCitationValidationError("CALCULATION_REFERENCE_INVALID")
            claim_text = (
                draft_claim.text
                if draft_claim.evidence
                else self._calculation_claim_text(calculation_records)
            )
            claim_citations: list[Citation] = []
            for reference in draft_claim.evidence:
                evidence = evidence_by_id.get(reference.passage_id)
                if evidence is None:
                    raise AgentCitationValidationError("PASSAGE_NOT_RETURNED")
                citation = self._citation(draft_claim.claim_id, reference, evidence)
                citations.append(citation)
                claim_citations.append(citation)
            if claim_citations and not _numbers_supported(
                draft_claim.text,
                [evidence_by_id[reference.passage_id].text for reference in draft_claim.evidence],
            ):
                raise AgentCitationValidationError("CLAIM_NUMBER_UNSUPPORTED")
            if claim_citations:
                validation_claims.append(Claim(claim_id=draft_claim.claim_id, text=claim_text))
            claims.append(
                AgentClaim(
                    claim_id=draft_claim.claim_id,
                    text=claim_text,
                    citations=tuple(claim_citations),
                    calculation_ids=draft_claim.calculation_ids,
                )
            )

        validation = self._citation_validator.validate(
            run.run_id, tuple(validation_claims), tuple(citations)
        )
        if validation.status != "valid" or len(validation.accepted) != len(citations):
            reason_code = (
                validation.rejected[0].reason_code if validation.rejected else "UNCOVERED_CLAIM"
            )
            raise AgentCitationValidationError(reason_code)
        return tuple(claims)

    @staticmethod
    def _calculation_claim_text(calculations: list[AgentCalculationRecord]) -> str:
        summaries: list[str] = []
        omitted_rows = 0
        for calculation in calculations:
            row_summaries: list[str] = []
            for row in calculation.rows[:2]:
                location = " ".join(
                    item
                    for item in (
                        row.geography or "All geographies",
                        str(row.year) if row.year is not None else "all years",
                    )
                    if item
                )
                value = "not reported" if row.value is None else str(row.value)
                unit = f" {row.unit}" if row.unit else ""
                row_summaries.append(f"{location}: {value}{unit}")
            omitted_rows += max(0, len(calculation.rows) - len(row_summaries))
            operation = (
                "source observations"
                if calculation.operation == "none"
                else f"{calculation.operation} result"
            )
            summaries.append(f"{operation}: {', '.join(row_summaries)}")
        if omitted_rows:
            summaries.append(f"{omitted_rows} additional rows are in the calculation details")
        return "Deterministic calculation results: " + "; ".join(summaries)

    def _response_from_draft(
        self,
        run: RetrievalRun,
        ledger: AgentRunLedger,
        draft: AgentDraft,
        model_metadata: ModelRunMetadata,
    ) -> AgentAnswerResponse:
        ledger.record_event("output_validated", status="succeeded")
        if draft.status == "clarification_required":
            ledger.transition(AgentRunState.CLARIFICATION_REQUIRED)
            ledger.record_event("terminal", status="succeeded")
            return self._response(
                run,
                ledger,
                "clarification_required",
                clarification_question=draft.clarification_question,
                uncertainty=draft.uncertainty,
                limitations=draft.limitations,
                model_metadata=model_metadata,
            )
        if draft.status == "abstained":
            ledger.transition(AgentRunState.ABSTAINED)
            ledger.record_event("terminal", status="succeeded")
            return self._response(
                run,
                ledger,
                "abstained",
                abstention_reason=draft.abstention_reason,
                uncertainty=draft.uncertainty,
                limitations=draft.limitations,
                model_metadata=model_metadata,
            )
        if draft.status == "blocked":
            ledger.transition(AgentRunState.BLOCKED)
            ledger.record_event("terminal", status="failed", error_code="POLICY_BLOCKED")
            return self._response(
                run,
                ledger,
                "blocked",
                abstention_reason=draft.abstention_reason,
                limitations=draft.limitations,
                error_code="POLICY_BLOCKED",
                model_metadata=model_metadata,
            )

        ledger.transition(AgentRunState.OUTPUT_VALIDATION)
        ledger.transition(AgentRunState.CITATION_VALIDATION)
        try:
            claims = self._validate_citations(run, draft, ledger)
        except AgentCitationValidationError as error:
            ledger.record_event(
                "citations_validated",
                status="failed",
                error_code=error.reason_code,
            )
            return self._failed(run, ledger, "CITATION_INVALID", model_metadata)
        except ValueError:
            ledger.record_event(
                "citations_validated",
                status="failed",
                error_code="VALIDATION_FAILED",
            )
            return self._failed(run, ledger, "CITATION_INVALID", model_metadata)
        status: AgentStatus = "conflict" if draft.status == "conflict" else "answered"
        terminal_state = AgentRunState.CONFLICT if status == "conflict" else AgentRunState.ANSWERED
        conflicts = tuple(
            AgentConflict(summary=item.summary, claim_ids=item.claim_ids)
            for item in draft.conflicts
        )
        ledger.record_event("citations_validated", status="succeeded")
        ledger.transition(terminal_state)
        ledger.record_event("terminal", status="succeeded")
        answer = "\n".join(claim.text for claim in claims)
        return self._response(
            run,
            ledger,
            status,
            answer=answer,
            claims=claims,
            calculations=ledger.calculations,
            uncertainty=draft.uncertainty,
            conflicts=conflicts,
            limitations=draft.limitations,
            model_metadata=model_metadata,
        )

    async def answer(
        self,
        request: AgentAnswerRequest,
        *,
        event_listener: Callable[[AgentEvent], None] | None = None,
        memory_context: tuple[ConversationMemory, ...] = (),
    ) -> AgentAnswerResponse:
        ledger = AgentRunLedger(
            max_tool_calls=self._settings.max_tool_calls,
            max_calls_per_tool=self._settings.max_tool_calls_per_tool,
            max_retries=self._settings.max_tool_retries,
            event_listener=event_listener,
        )
        run: RetrievalRun | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                safe_query, injection_detected = _sanitized_query(request.query)
                safe_request = (
                    request.model_copy(update={"query": safe_query})
                    if injection_detected and safe_query
                    else request
                )
                original_query = safe_request.query
                safe_request = await self._standalone_request(safe_request)
                user_message = original_query if safe_request.query != original_query else None
                ledger.transition(AgentRunState.VALIDATED)
                ledger.transition(AgentRunState.RETRIEVING)
                run = await asyncio.to_thread(self._retrieval_service.search, safe_request)
                if run.reranking is not None:
                    ledger.record_event(
                        "reranking_completed",
                        status=("failed" if run.reranking.status == "failed" else "succeeded"),
                        duration_ms=run.reranking.duration_ms,
                        item_count=run.reranking.candidate_count,
                        error_code=run.reranking.error_code,
                        reranker_model=run.reranking.model_id,
                    )
                if run.evidence and self._passage_reader is not None:
                    started_at = monotonic()
                    ledger.record_event("mcp_resource_started", status="started")
                    try:
                        passages = await self._passage_reader.read_passages(
                            tuple(
                                (evidence.source_id, evidence.passage_id)
                                for evidence in run.evidence
                            )
                        )
                        self._validate_mcp_passages(run.evidence, passages)
                    except AgentToolAdapterError as error:
                        ledger.record_event(
                            "mcp_resource_completed",
                            status="failed",
                            duration_ms=(monotonic() - started_at) * 1000,
                            error_code=error.code,
                        )
                        ledger.record_event(
                            "retrieval_completed",
                            status="failed",
                            error_code=error.code,
                        )
                        return self._failed(run, ledger, error.code)
                    ledger.record_event(
                        "mcp_resource_completed",
                        status="succeeded",
                        duration_ms=(monotonic() - started_at) * 1000,
                        item_count=len(passages),
                    )
                ledger.record_event("retrieval_completed", status="succeeded")
                ledger.transition(AgentRunState.ASSESSING)
                if _SENSITIVE_DATA_REQUEST.search(request.query) or (
                    injection_detected and not safe_query
                ):
                    ledger.transition(AgentRunState.BLOCKED)
                    ledger.record_event("terminal", status="succeeded", error_code="POLICY_BLOCKED")
                    return self._response(
                        run,
                        ledger,
                        "blocked",
                        abstention_reason=(
                            "This request seeks sensitive data or contains no safe research "
                            "question after removing instruction-like text."
                        ),
                        error_code="POLICY_BLOCKED",
                    )
                if _requests_image_generation(safe_request.query):
                    ledger.transition(AgentRunState.BLOCKED)
                    ledger.record_event(
                        "terminal",
                        status="succeeded",
                        error_code="OUT_OF_SCOPE",
                    )
                    return self._response(
                        run,
                        ledger,
                        "blocked",
                        abstention_reason=(
                            "PolicyLens answers evidence-based policy questions and "
                            "cannot draw or generate images. Ask a policy or evidence "
                            "question instead."
                        ),
                        error_code="OUT_OF_SCOPE",
                    )
                if _requests_out_of_range_calculation_years(safe_request.query):
                    ledger.transition(AgentRunState.ABSTAINED)
                    ledger.record_event("terminal", status="succeeded")
                    return self._response(
                        run,
                        ledger,
                        "abstained",
                        abstention_reason=(
                            "The structured statistics cover 2015 through 2025 only, so a "
                            "calculation for years outside that range cannot be answered."
                        ),
                    )
                if run.status == "no_results" and self._statistics_adapter is None:
                    ledger.transition(AgentRunState.ABSTAINED)
                    ledger.record_event("terminal", status="succeeded")
                    return self._response(
                        run,
                        ledger,
                        "abstained",
                        abstention_reason="No eligible evidence was retrieved.",
                    )
                model_metadata: ModelRunMetadata | None = None
                try:
                    try:
                        gateway_result = await self._run_agent(
                            safe_request,
                            run,
                            ledger,
                            memory_context,
                            user_message=user_message,
                        )
                    except Exception as first_error:
                        if type(first_error).__name__ != "ModelBehaviorError":
                            raise
                        if "Invalid JSON input for tool" in str(first_error):
                            # Out-of-range tool arguments must be blocked, not silently
                            # repaired into different arguments by a model retry.
                            raise AgentToolExecutionError("TOOL_INVALID_ARGUMENTS") from first_error
                        _log_model_failure(ledger.trace_id, first_error)
                        gateway_result = await self._run_agent(
                            safe_request,
                            run,
                            ledger,
                            memory_context,
                            repair_feedback=_FORMAT_REPAIR_MESSAGE,
                            user_message=user_message,
                        )
                    draft = gateway_result.draft
                    model_metadata = gateway_result.metadata
                    if draft.status in {"answered", "conflict"}:
                        try:
                            self._validate_citations(run, draft, ledger)
                        except (AgentCitationValidationError, ValueError) as invalid:
                            ledger.record_event(
                                "citations_validated",
                                status="failed",
                                error_code=getattr(invalid, "reason_code", "VALIDATION_FAILED"),
                            )
                            gateway_result = await self._run_agent(
                                safe_request,
                                run,
                                ledger,
                                memory_context,
                                repair_feedback=_repair_message(invalid),
                                user_message=user_message,
                            )
                            draft = gateway_result.draft
                            model_metadata = gateway_result.metadata
                except AgentConfigurationError:
                    return self._failed(run, ledger, "MODEL_UNAVAILABLE")
                except AgentToolExecutionError as error:
                    if error.code in {"TOOL_INVALID_ARGUMENTS", "TOOL_PERMISSION_DENIED"}:
                        if ledger.state != AgentRunState.BLOCKED:
                            ledger.transition(AgentRunState.BLOCKED)
                        ledger.record_event("terminal", status="succeeded", error_code=error.code)
                        return self._response(
                            run,
                            ledger,
                            "blocked",
                            abstention_reason=(
                                "The requested tool operation was rejected by host validation."
                            ),
                            error_code=error.code,
                        )
                    return self._failed(run, ledger, error.code, model_metadata)
                except ValidationError:
                    return self._failed(run, ledger, "OUTPUT_SCHEMA_INVALID", model_metadata)
                except Exception as error:
                    if ledger.tool_error_code is not None:
                        return self._failed(run, ledger, ledger.tool_error_code, model_metadata)
                    if _is_provider_content_filter(error):
                        ledger.transition(AgentRunState.BLOCKED)
                        ledger.record_event(
                            "terminal", status="succeeded", error_code="POLICY_BLOCKED"
                        )
                        return self._response(
                            run,
                            ledger,
                            "blocked",
                            abstention_reason=(
                                "The model provider's safety policy declined this request, "
                                "so no answer was generated. Rephrase it as an "
                                "evidence-based policy question."
                            ),
                            error_code="POLICY_BLOCKED",
                            model_metadata=model_metadata,
                        )
                    _log_model_failure(ledger.trace_id, error)
                    return self._failed(run, ledger, "MODEL_UNAVAILABLE", model_metadata)
                return self._response_from_draft(run, ledger, draft, model_metadata)
        except TimeoutError as error:
            if run is None:
                raise AgentExecutionError("RETRIEVAL_UNAVAILABLE", ledger.trace_id) from None
            _log_model_failure(ledger.trace_id, error)
            return self._failed(run, ledger, "MODEL_UNAVAILABLE")
        except RetrievalError as error:
            raise AgentExecutionError("RETRIEVAL_UNAVAILABLE", ledger.trace_id) from error
        except AgentStateError as error:
            raise AgentExecutionError("INTERNAL_ERROR", ledger.trace_id) from error
