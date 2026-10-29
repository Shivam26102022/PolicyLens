from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from policylens.agent_runtime.models import ModelUsage
from policylens.retrieval.citations import CitationValidator
from policylens.retrieval.models import (
    Citation,
    Claim,
    RetrievalRequest,
    RetrievalRun,
    RetrievedEvidence,
    StrictModel,
)
from policylens.settings import PROJECT_ROOT, AppSettings

BaselineStatus = Literal["answered", "abstained", "failed_safe"]
BaselineErrorCode = Literal[
    "NO_EVIDENCE",
    "MODEL_ABSTAINED",
    "GENERATION_UNAVAILABLE",
    "INVALID_MODEL_OUTPUT",
    "INVALID_CITATION",
]

_PROMPT_PATH = PROJECT_ROOT / "prompts/answer/non-agent-v1.md"
_PROMPT_VERSION: Literal["non-agent-v1"] = "non-agent-v1"
_MAX_EVIDENCE_COUNT = 6
_MAX_EVIDENCE_TEXT_CHARS = 12000
_MAX_INPUT_CHARS = 15000
_MAX_OUTPUT_TOKENS = 1200


class BaselineAnswerRequest(RetrievalRequest):
    """Request for one non-agent answer attempt over retrieval evidence."""


class BaselineEvidenceReference(StrictModel):
    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    excerpt: str = Field(
        min_length=1,
        max_length=500,
        description="Exact contiguous text copied from the referenced passage.",
    )


class BaselineDraftClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(
        min_length=1,
        max_length=500,
        description="Verbatim excerpt; must exactly equal one evidence excerpt.",
    )
    evidence: tuple[BaselineEvidenceReference, ...] = Field(min_length=1, max_length=4)


class BaselineDraft(StrictModel):
    status: Literal["answered", "abstained"]
    claims: tuple[BaselineDraftClaim, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_draft(self) -> BaselineDraft:
        if (self.status == "answered") != bool(self.claims):
            raise ValueError(
                "answered drafts require claims and abstained drafts must not include them"
            )
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique")
        return self


class BaselineAnswerClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(
        min_length=1,
        max_length=500,
        description="Verbatim excerpt; must exactly equal one citation excerpt.",
    )
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_extractive_claim(self) -> BaselineAnswerClaim:
        if not any(citation.excerpt == self.text for citation in self.citations):
            raise ValueError("claim text must exactly match one citation excerpt")
        return self


class BaselineGenerationMetadata(StrictModel):
    provider: Literal["openai", "mlx"] = "openai"
    model_id: str = Field(min_length=1, max_length=300)
    prompt_version: Literal["non-agent-v1"] = _PROMPT_VERSION
    latency_ms: float = Field(default=0, ge=0)
    usage: ModelUsage = Field(default_factory=ModelUsage)
    fallback_decision: Literal["none"] = "none"


class BaselineAnswerResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: BaselineStatus
    run_id: UUID
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    claims: tuple[BaselineAnswerClaim, ...] = Field(max_length=12)
    error_code: BaselineErrorCode | None = None
    generation: BaselineGenerationMetadata | None

    @model_validator(mode="after")
    def validate_answer_state(self) -> BaselineAnswerResponse:
        if self.status == "answered":
            if not self.claims or self.error_code is not None or self.generation is None:
                raise ValueError("answered responses require claims and generation metadata")
        elif self.claims or self.error_code is None:
            raise ValueError("non-answered responses require an error code and no claims")
        elif self.error_code == "NO_EVIDENCE":
            if self.generation is not None:
                raise ValueError("no-evidence abstentions cannot include generation metadata")
        elif self.generation is None:
            raise ValueError("provider-backed results require generation metadata")
        return self


class BaselineConfigurationError(RuntimeError):
    """The explicitly selected generation provider is not configured for the baseline."""


class NonAgentRagBaseline:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        citation_validator: CitationValidator,
        provider: Literal["openai", "mlx"] = "openai",
        client: Any | None = None,
        base_url: str | None = None,
        prompt: str | None = None,
        max_input_chars: int = _MAX_INPUT_CHARS,
        max_output_tokens: int = _MAX_OUTPUT_TOKENS,
        request_timeout_seconds: int = 60,
    ) -> None:
        if not model.strip():
            raise BaselineConfigurationError("Selected provider requires a model ID")
        if provider == "openai" and not (api_key or "").strip():
            raise BaselineConfigurationError("OpenAI baseline requires an API key")
        if provider == "mlx" and not base_url:
            raise BaselineConfigurationError("MLX baseline requires a loopback endpoint")
        if not 1000 <= max_input_chars <= _MAX_INPUT_CHARS:
            raise ValueError("max_input_chars must be between 1000 and 15000")
        if not 1 <= max_output_tokens <= _MAX_OUTPUT_TOKENS:
            raise ValueError("max_output_tokens must be between 1 and 1200")
        if not 1 <= request_timeout_seconds <= 300:
            raise ValueError("request_timeout_seconds must be between 1 and 300")
        if prompt is None:
            try:
                prompt = _PROMPT_PATH.read_text(encoding="utf-8")
            except OSError as error:
                raise BaselineConfigurationError(
                    "The versioned baseline prompt is unavailable"
                ) from error
        if not prompt.strip():
            raise BaselineConfigurationError("The versioned baseline prompt is empty")

        self._model = model.strip()
        self._provider = provider
        self._base_url = base_url
        self._citation_validator = citation_validator
        self._prompt = prompt
        self._max_input_chars = max_input_chars
        self._max_output_tokens = max_output_tokens
        self._request_timeout_seconds = request_timeout_seconds
        if client is None:
            from openai import OpenAI

            if provider == "mlx":
                client = OpenAI(
                    api_key="mlx-local-no-auth-token",
                    base_url=base_url,
                    max_retries=0,
                    timeout=request_timeout_seconds,
                )
            elif base_url is not None:
                assert api_key is not None
                client = OpenAI(
                    api_key=api_key.strip(),
                    base_url=base_url,
                    max_retries=0,
                    timeout=request_timeout_seconds,
                    default_headers={"api-key": api_key.strip()},
                )
            else:
                assert api_key is not None
                client = OpenAI(
                    api_key=api_key.strip(),
                    max_retries=0,
                    timeout=request_timeout_seconds,
                )
        self._client = client

    @classmethod
    def from_settings(
        cls,
        settings: AppSettings,
        citation_validator: CitationValidator,
        *,
        client: Any | None = None,
    ) -> NonAgentRagBaseline:
        api_key: str | None
        base_url: str | None
        provider: Literal["openai", "mlx"]
        if settings.model_provider == "mlx":
            model = settings.mlx_model or ""
            api_key = None
            base_url = str(settings.mlx_base_url)
            provider = "mlx"
        else:
            api_key = (
                settings.openai_api_key.get_secret_value().strip()
                if settings.openai_api_key
                else ""
            )
            model = settings.effective_openai_model or ""
            base_url = str(settings.openai_base_url) if settings.openai_base_url else None
            provider = "openai"
            if settings.openai_deployment_model and base_url is None:
                raise BaselineConfigurationError("The Foundry deployment requires OPENAI_BASE_URL")
            if not api_key or not model:
                raise BaselineConfigurationError(
                    "The OpenAI generation provider is not explicitly configured"
                )
        return cls(
            model=model,
            api_key=api_key,
            provider=provider,
            citation_validator=citation_validator,
            client=client,
            base_url=base_url,
            request_timeout_seconds=settings.request_timeout_seconds,
        )

    @staticmethod
    def abstained(run: RetrievalRun) -> BaselineAnswerResponse:
        return BaselineAnswerResponse(
            status="abstained",
            run_id=run.run_id,
            index_version=run.index_version,
            claims=(),
            error_code="NO_EVIDENCE",
            generation=None,
        )

    @staticmethod
    def _usage_count(usage: object | None, *names: str) -> int | None:
        if usage is None:
            return None
        for name in names:
            value = getattr(usage, name, None)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    def _generation_metadata(
        self,
        *,
        response: object | None = None,
        latency_ms: float = 0.0,
    ) -> BaselineGenerationMetadata:
        usage = getattr(response, "usage", None)
        return BaselineGenerationMetadata(
            provider=self._provider,
            model_id=self._model,
            latency_ms=max(0.0, latency_ms),
            usage=ModelUsage(
                prompt_tokens=self._usage_count(usage, "prompt_tokens", "input_tokens"),
                completion_tokens=self._usage_count(usage, "completion_tokens", "output_tokens"),
                total_tokens=self._usage_count(usage, "total_tokens"),
                cost_usd=None,
                memory_bytes=None,
            ),
        )

    def _failed(
        self,
        run: RetrievalRun,
        code: BaselineErrorCode,
        *,
        response: object | None = None,
        latency_ms: float = 0.0,
    ) -> BaselineAnswerResponse:
        return BaselineAnswerResponse(
            status="failed_safe",
            run_id=run.run_id,
            index_version=run.index_version,
            claims=(),
            error_code=code,
            generation=self._generation_metadata(response=response, latency_ms=latency_ms),
        )

    def _request_input(self, query: str, evidence: tuple[RetrievedEvidence, ...]) -> str:
        entries: list[dict[str, str]] = []
        remaining_chars = _MAX_EVIDENCE_TEXT_CHARS
        for item in evidence[:_MAX_EVIDENCE_COUNT]:
            if remaining_chars <= 0:
                break
            text = item.text[:remaining_chars]
            entries.append({"passage_id": item.passage_id, "text": text})
            remaining_chars -= len(text)

        payload = {"query": query, "evidence": entries}
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        while len(serialized) > self._max_input_chars and entries:
            excess = len(serialized) - self._max_input_chars
            last_text = entries[-1]["text"]
            if len(last_text) <= excess:
                entries.pop()
            else:
                entries[-1]["text"] = last_text[: len(last_text) - excess - 1]
            payload["evidence"] = entries
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return serialized

    @staticmethod
    def _citation(
        claim_id: str,
        reference: BaselineEvidenceReference,
        evidence: RetrievedEvidence,
    ) -> Citation:
        pages = [location.page_number for location in evidence.locations]
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
            excerpt=reference.excerpt,
            source_content_sha256=evidence.source_content_sha256,
            retrieval_rank=evidence.rank,
            retrieval_score=evidence.score,
            retrieval_mode=evidence.retrieval_mode,
        )

    def answer(self, query: str, run: RetrievalRun) -> BaselineAnswerResponse:
        if run.status != "found" or not run.evidence:
            return self.abstained(run)
        started_at = perf_counter()
        response: object | None = None
        parsed_output: BaselineDraft | None = None
        try:
            messages = [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": self._request_input(query, run.evidence)},
            ]
            provider_messages = cast(Any, messages)
            if self._provider == "mlx":
                models_response = self._client.models.list()
                available_models = {
                    item_id
                    for item in getattr(models_response, "data", ())
                    if isinstance((item_id := getattr(item, "id", None)), str)
                }
                if self._model not in available_models:
                    return self._failed(
                        run,
                        "GENERATION_UNAVAILABLE",
                        latency_ms=(perf_counter() - started_at) * 1000,
                    )
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=provider_messages,
                    max_tokens=self._max_output_tokens,
                    temperature=0.0,
                    timeout=self._request_timeout_seconds,
                )
                content = response.choices[0].message.content
                if not isinstance(content, str):
                    return self._failed(
                        run,
                        "INVALID_MODEL_OUTPUT",
                        response=response,
                        latency_ms=(perf_counter() - started_at) * 1000,
                    )
                parsed_output = BaselineDraft.model_validate_json(content)
            elif self._base_url is not None:
                response = self._client.beta.chat.completions.parse(
                    model=self._model,
                    messages=provider_messages,
                    response_format=BaselineDraft,
                    max_completion_tokens=self._max_output_tokens,
                    timeout=self._request_timeout_seconds,
                )
                parsed_output = response.choices[0].message.parsed
            else:
                response = self._client.responses.parse(
                    model=self._model,
                    input=provider_messages,
                    text_format=BaselineDraft,
                    max_output_tokens=self._max_output_tokens,
                    timeout=self._request_timeout_seconds,
                    store=False,
                    tools=[],
                )
                parsed_output = response.output_parsed
        except ValidationError:
            return self._failed(
                run,
                "INVALID_MODEL_OUTPUT",
                response=response,
                latency_ms=(perf_counter() - started_at) * 1000,
            )
        except Exception:
            return self._failed(
                run,
                "GENERATION_UNAVAILABLE",
                response=response,
                latency_ms=(perf_counter() - started_at) * 1000,
            )

        try:
            draft = BaselineDraft.model_validate(parsed_output)
        except (AttributeError, TypeError, ValidationError):
            return self._failed(
                run,
                "INVALID_MODEL_OUTPUT",
                response=response,
                latency_ms=(perf_counter() - started_at) * 1000,
            )
        if draft.status == "abstained":
            return BaselineAnswerResponse(
                status="abstained",
                run_id=run.run_id,
                index_version=run.index_version,
                claims=(),
                error_code="MODEL_ABSTAINED",
                generation=self._generation_metadata(
                    response=response,
                    latency_ms=(perf_counter() - started_at) * 1000,
                ),
            )

        evidence_by_id = {item.passage_id: item for item in run.evidence}
        claims = tuple(Claim(claim_id=item.claim_id, text=item.text) for item in draft.claims)
        citations: list[Citation] = []
        citations_by_claim: dict[str, list[Citation]] = {}
        for claim in draft.claims:
            claim_citations: list[Citation] = []
            if not any(reference.excerpt == claim.text for reference in claim.evidence):
                return self._failed(
                    run,
                    "INVALID_CITATION",
                    response=response,
                    latency_ms=(perf_counter() - started_at) * 1000,
                )
            for reference in claim.evidence:
                evidence = evidence_by_id.get(reference.passage_id)
                if evidence is None:
                    return self._failed(
                        run,
                        "INVALID_CITATION",
                        response=response,
                        latency_ms=(perf_counter() - started_at) * 1000,
                    )
                citation = self._citation(claim.claim_id, reference, evidence)
                citations.append(citation)
                claim_citations.append(citation)
            citations_by_claim[claim.claim_id] = claim_citations

        validation = self._citation_validator.validate(run.run_id, claims, tuple(citations))
        if validation.status != "valid" or len(validation.accepted) != len(citations):
            return self._failed(
                run,
                "INVALID_CITATION",
                response=response,
                latency_ms=(perf_counter() - started_at) * 1000,
            )
        return BaselineAnswerResponse(
            status="answered",
            run_id=run.run_id,
            index_version=run.index_version,
            claims=tuple(
                BaselineAnswerClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    citations=tuple(citations_by_claim[claim.claim_id]),
                )
                for claim in draft.claims
            ),
            error_code=None,
            generation=self._generation_metadata(
                response=response,
                latency_ms=(perf_counter() - started_at) * 1000,
            ),
        )
