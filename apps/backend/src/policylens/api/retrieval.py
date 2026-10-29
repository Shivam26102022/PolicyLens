from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from policylens.retrieval.citations import CitationValidator, RetrievalRunRegistry
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import create_embedding_provider
from policylens.retrieval.generation import (
    BaselineAnswerRequest,
    BaselineAnswerResponse,
    BaselineConfigurationError,
    NonAgentRagBaseline,
)
from policylens.retrieval.indexing import IndexBuildError, active_embedding_descriptor
from policylens.retrieval.models import CitationValidationRequest, RetrievalRequest
from policylens.retrieval.search import RetrievalError, RetrievalService
from policylens.settings import PROJECT_ROOT, AppSettings

router = APIRouter(prefix="/retrieval", tags=["retrieval"])
RuntimeFactory = Callable[[AppSettings], tuple[RetrievalService, CitationValidator]]
AnswerBaselineFactory = Callable[[AppSettings, CitationValidator], Any]


def _create_runtime(settings: AppSettings) -> tuple[RetrievalService, CitationValidator]:
    retrieval_settings = RetrievalSettings.from_app_settings(settings)
    registry = RetrievalRunRegistry(
        ttl_seconds=retrieval_settings.retrieval_run_ttl_seconds,
        capacity=retrieval_settings.retrieval_run_registry_capacity,
    )
    embedder = create_embedding_provider(retrieval_settings)
    service = RetrievalService.from_active_index(
        PROJECT_ROOT, retrieval_settings, embedder, registry
    )
    validator = CitationValidator(registry, retrieval_settings.max_excerpt_chars)
    return service, validator


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": "1.0",
            "error_code": code,
            "message": message,
        },
    )


def _map_index_error(error: IndexBuildError) -> tuple[str, str, int]:
    if error.code == "INDEX_NOT_ACTIVE":
        return "INDEX_NOT_ACTIVE", "No validated retrieval index is active.", 503
    return "INDEX_INCOMPATIBLE", "The active retrieval index is unavailable or incompatible.", 503


def get_retrieval_runtime(
    request: Request,
) -> tuple[RetrievalService, CitationValidator | None] | JSONResponse:
    service = getattr(request.app.state, "retrieval_service", None)
    validator = getattr(request.app.state, "citation_validator", None)
    if service is not None:
        return service, validator
    factory: RuntimeFactory = (
        getattr(request.app.state, "retrieval_runtime_factory", None) or _create_runtime
    )
    try:
        service, validator = factory(request.app.state.settings)
    except IndexBuildError as error:
        code, message, status = _map_index_error(error)
        return _error_response(code, message, status)
    except RetrievalError as error:
        if error.code == "EMBEDDING_UNAVAILABLE":
            return _error_response(
                "EMBEDDING_UNAVAILABLE", "The configured embedding provider is unavailable.", 503
            )
        if error.code == "INDEX_EMBEDDING_MISMATCH":
            return _error_response(
                "INDEX_INCOMPATIBLE",
                "The configured embedding model does not match the active index.",
                503,
            )
        return _error_response("RETRIEVAL_FAILED", "Retrieval is unavailable.", 503)
    except Exception:
        return _error_response("RETRIEVAL_FAILED", "Retrieval is unavailable.", 503)
    request.app.state.retrieval_service = service
    request.app.state.citation_validator = validator
    return service, validator


def _answer_baseline(request: Request, validator: CitationValidator) -> Any | JSONResponse:
    baseline = getattr(request.app.state, "answer_baseline", None)
    if baseline is not None:
        return baseline
    factory: AnswerBaselineFactory = (
        getattr(request.app.state, "answer_baseline_factory", None)
        or NonAgentRagBaseline.from_settings
    )
    try:
        baseline = factory(request.app.state.settings, validator)
    except BaselineConfigurationError:
        return _error_response(
            "GENERATION_UNAVAILABLE",
            "The explicitly configured OpenAI generation provider is unavailable.",
            503,
        )
    except Exception:
        return _error_response(
            "GENERATION_UNAVAILABLE", "The generation baseline is unavailable.", 503
        )
    request.app.state.answer_baseline = baseline
    return baseline


@router.get("/ready")
def retrieval_readiness(request: Request) -> JSONResponse:
    try:
        settings = RetrievalSettings.from_app_settings(request.app.state.settings)
        descriptor = active_embedding_descriptor(PROJECT_ROOT, settings)
    except IndexBuildError as error:
        code, message, status = _map_index_error(error)
        return _error_response(code, message, status)
    except Exception:
        return _error_response(
            "INDEX_INCOMPATIBLE", "The active retrieval index is unavailable or incompatible.", 503
        )
    if not settings.matches_embedding_descriptor(descriptor):
        return _error_response(
            "INDEX_INCOMPATIBLE",
            "The configured embedding model does not match the active index.",
            503,
        )
    return JSONResponse(
        status_code=200,
        content={
            "schema_version": "1.0",
            "status": "ready",
            "embedding_provider": descriptor.provider,
            "embedding_model": descriptor.model_id,
        },
    )


@router.post("/search")
def search(request: Request, body: RetrievalRequest) -> Any:
    runtime = get_retrieval_runtime(request)
    if isinstance(runtime, JSONResponse):
        return runtime
    service, _validator = runtime
    try:
        return service.search(body)
    except RetrievalError as error:
        if error.code == "EMBEDDING_UNAVAILABLE":
            return _error_response(
                "EMBEDDING_UNAVAILABLE", "The configured embedding provider is unavailable.", 503
            )
        return _error_response("RETRIEVAL_FAILED", "Retrieval failed.", 503)


@router.post("/answer", response_model=BaselineAnswerResponse)
def answer(request: Request, body: BaselineAnswerRequest) -> BaselineAnswerResponse | JSONResponse:
    runtime = get_retrieval_runtime(request)
    if isinstance(runtime, JSONResponse):
        return runtime
    service, validator = runtime
    try:
        run = service.search(body)
    except RetrievalError as error:
        if error.code == "EMBEDDING_UNAVAILABLE":
            return _error_response(
                "EMBEDDING_UNAVAILABLE", "The configured embedding provider is unavailable.", 503
            )
        return _error_response("RETRIEVAL_FAILED", "Retrieval failed.", 503)
    if run.status == "no_results":
        return NonAgentRagBaseline.abstained(run)
    if validator is None:
        return _error_response("RETRIEVAL_FAILED", "Citation validation is unavailable.", 503)
    baseline = _answer_baseline(request, validator)
    if isinstance(baseline, JSONResponse):
        return baseline
    return baseline.answer(body.query, run)


@router.post("/citations/validate")
def validate_citations(request: Request, body: CitationValidationRequest) -> Any:
    runtime = get_retrieval_runtime(request)
    if isinstance(runtime, JSONResponse):
        return runtime
    _service, validator = runtime
    if validator is None:
        return _error_response("RETRIEVAL_FAILED", "Citation validation is unavailable.", 503)
    return validator.validate_request(body)
