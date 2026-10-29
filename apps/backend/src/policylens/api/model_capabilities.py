from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from policylens.agent_runtime.gateway import build_model_gateway
from policylens.agent_runtime.models import ModelCapabilities, ModelRoute
from policylens.agent_runtime.provider import AgentConfigurationError
from policylens.retrieval.models import StrictModel
from policylens.settings import AppSettings

router = APIRouter(prefix="/model", tags=["model"])


class ModelCapabilityError(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    error_code: Literal["MODEL_UNAVAILABLE", "MODEL_CAPABILITY_UNSUPPORTED"]
    message: str


class ModelOption(StrictModel):
    provider: Literal["openai", "mlx"]
    route: ModelRoute
    model_id: str | None = Field(default=None, min_length=1, max_length=300)
    execution_scope: Literal["external", "loopback"]
    configured: bool
    selected_by_default: bool
    consent_required: bool
    reasoning_efforts: tuple[Literal["none", "low", "medium", "high"], ...] = ("none",)


class ModelOptionsResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    default_provider: Literal["openai", "mlx"]
    embedding_provider: Literal["local", "openai"]
    embedding_consent_required: bool
    options: tuple[ModelOption, ModelOption]


def _mlx_is_loopback(settings: AppSettings) -> bool:
    url = settings.mlx_base_url
    host = (url.host or "").strip("[]").casefold()
    return (
        url.scheme == "http"
        and host in {"localhost", "127.0.0.1", "::1"}
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment
        and url.path in {"", "/", "/v1"}
    )


def build_model_options(settings: AppSettings) -> ModelOptionsResponse:
    openai_model = settings.effective_openai_model
    openai_configured = bool(
        settings.openai_api_key
        and settings.openai_api_key.get_secret_value().strip()
        and openai_model
    )
    mlx_model = (settings.mlx_model or "").strip()
    mlx_configured = bool(mlx_model and _mlx_is_loopback(settings))
    return ModelOptionsResponse(
        default_provider=settings.model_provider,
        embedding_provider=settings.embedding_provider,
        embedding_consent_required=settings.embedding_provider == "openai",
        options=(
            ModelOption(
                provider="openai",
                route=(
                    "openai_chat_completions"
                    if settings.openai_base_url is not None
                    and not settings.openai_use_responses_api
                    else "openai_responses"
                ),
                model_id=openai_model if openai_configured else None,
                execution_scope="external",
                configured=openai_configured,
                selected_by_default=settings.model_provider == "openai",
                consent_required=True,
                reasoning_efforts=(
                    ("none",)
                    if settings.openai_base_url is not None
                    and not settings.openai_use_responses_api
                    else ("none", "low", "medium", "high")
                ),
            ),
            ModelOption(
                provider="mlx",
                route="mlx_chat_completions",
                model_id=mlx_model if mlx_configured else None,
                execution_scope="loopback",
                configured=mlx_configured,
                selected_by_default=settings.model_provider == "mlx",
                consent_required=False,
                reasoning_efforts=("none",),
            ),
        ),
    )


@router.get("/options", response_model=ModelOptionsResponse)
async def model_options(request: Request) -> ModelOptionsResponse:
    return build_model_options(request.app.state.settings)


@router.get("/capabilities", response_model=ModelCapabilities)
async def model_capabilities(request: Request) -> ModelCapabilities | JSONResponse:
    try:
        gateway = build_model_gateway(request.app.state.settings)
        capabilities = await gateway.discover_capabilities()
    except AgentConfigurationError:
        error = ModelCapabilityError(
            error_code="MODEL_UNAVAILABLE",
            message="The selected model provider is unavailable or misconfigured.",
        )
        return JSONResponse(status_code=503, content=error.model_dump(mode="json"))
    except Exception:
        error = ModelCapabilityError(
            error_code="MODEL_UNAVAILABLE",
            message="The selected model provider is unavailable.",
        )
        return JSONResponse(status_code=503, content=error.model_dump(mode="json"))
    if not capabilities.ready:
        error = ModelCapabilityError(
            error_code="MODEL_UNAVAILABLE",
            message="The selected model provider is not ready.",
        )
        return JSONResponse(status_code=503, content=error.model_dump(mode="json"))
    return capabilities
