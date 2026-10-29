from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from policylens import __version__
from policylens.api.mcp_probe import MCPProbeResult
from policylens.api.model_capabilities import build_model_options
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.indexing import IndexBuildError, active_embedding_descriptor
from policylens.settings import PROJECT_ROOT, AppSettings

ComponentStatus = Literal["ready", "degraded", "not_configured", "unavailable"]
HealthStatus = Literal["alive", "ready", "degraded", "not_ready"]


class ServiceHealthV1(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    service: str = "policylens-api"
    version: str = __version__
    status: HealthStatus
    components: dict[str, ComponentStatus]
    error_code: str | None = None


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=ServiceHealthV1, response_model_exclude_none=True)
async def liveness() -> ServiceHealthV1:
    return ServiceHealthV1(status="alive", components={"api": "ready"})


@router.get("/ready", response_model=ServiceHealthV1, response_model_exclude_none=True)
async def readiness(request: Request) -> JSONResponse:
    settings: AppSettings = request.app.state.settings
    mcp_result: MCPProbeResult = await request.app.state.mcp_probe(settings)
    options = build_model_options(settings)
    generation_configured = any(
        option.provider == options.default_provider and option.configured
        for option in options.options
    )
    components: dict[str, ComponentStatus] = {
        "api": "ready",
        "generation": "ready" if generation_configured else "not_configured",
        "embedding": "not_configured",
        "retrieval": "not_configured",
        "mcp": mcp_result.status if mcp_result.status == "ready" else "unavailable",
    }
    error_code: str | None = mcp_result.error_code
    try:
        retrieval_settings = RetrievalSettings.from_app_settings(settings)
        descriptor = active_embedding_descriptor(PROJECT_ROOT, retrieval_settings)
    except IndexBuildError as error:
        if error.code != "INDEX_NOT_ACTIVE":
            components["embedding"] = "unavailable"
            components["retrieval"] = "unavailable"
            error_code = error.code
    except Exception:
        components["embedding"] = "unavailable"
        components["retrieval"] = "unavailable"
        error_code = "INDEX_INCOMPATIBLE"
    else:
        if retrieval_settings.matches_embedding_descriptor(descriptor):
            components["embedding"] = "ready"
            components["retrieval"] = "ready"
        else:
            components["embedding"] = "unavailable"
            components["retrieval"] = "unavailable"
            error_code = "INDEX_INCOMPATIBLE"
    health = ServiceHealthV1(
        status="ready" if all(value == "ready" for value in components.values()) else "degraded",
        components=components,
        error_code=error_code,
    )
    return JSONResponse(
        status_code=200 if health.status == "ready" else 503,
        content=health.model_dump(mode="json", exclude_none=True),
    )
