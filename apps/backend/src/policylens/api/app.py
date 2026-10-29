import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from policylens.api.agent import router as agent_router
from policylens.api.evaluation_summary import router as evaluation_summary_router
from policylens.api.health import router as health_router
from policylens.api.mcp_probe import MCPProbeResult, probe_mcp
from policylens.api.model_capabilities import router as model_capabilities_router
from policylens.api.retrieval import router as retrieval_router
from policylens.api.sessions import router as sessions_router
from policylens.api.source_files import router as source_files_router
from policylens.conversations.memory import ConversationMemoryService
from policylens.conversations.store import ConversationStore
from policylens.mcp.client import MCPStatisticsAdapter
from policylens.observability.logging import configure_logging
from policylens.retrieval.citations import CitationValidator
from policylens.retrieval.search import RetrievalService
from policylens.settings import AppSettings, get_frontend_origin, get_settings

MCPProbe = Callable[[AppSettings], Awaitable[MCPProbeResult]]
RetrievalRuntimeFactory = Callable[[AppSettings], tuple[RetrievalService, CitationValidator]]
AgentRuntimeFactory = Callable[[AppSettings, RetrievalService, CitationValidator, Any], Any]


def _allowed_origins(frontend_origin: str) -> list[str]:
    # Vite dev binds 127.0.0.1 while the configured origin is usually localhost.
    origins = [frontend_origin]
    for a, b in (("//localhost:", "//127.0.0.1:"), ("//127.0.0.1:", "//localhost:")):
        if a in frontend_origin:
            origins.append(frontend_origin.replace(a, b))
    return origins


def create_app(
    settings: AppSettings | None = None,
    mcp_probe: MCPProbe = probe_mcp,
    retrieval_service: RetrievalService | Any | None = None,
    citation_validator: CitationValidator | None = None,
    retrieval_runtime_factory: RetrievalRuntimeFactory | None = None,
    answer_baseline: Any | None = None,
    answer_baseline_factory: Callable[[AppSettings, CitationValidator], Any] | None = None,
    agent_runtime: Any | None = None,
    agent_runtime_factory: AgentRuntimeFactory | None = None,
    statistics_tool_adapter: Any | None = None,
    conversation_store: ConversationStore | None = None,
    conversation_memory_service: ConversationMemoryService | None = None,
) -> FastAPI:
    state_initialization_lock = asyncio.Lock()

    def initialize_app_state(app: FastAPI) -> None:
        app_settings = settings if settings is not None else get_settings()
        app.state.settings = app_settings
        app.state.mcp_probe = mcp_probe
        app.state.retrieval_service = retrieval_service
        app.state.citation_validator = citation_validator
        app.state.retrieval_runtime_factory = retrieval_runtime_factory
        app.state.answer_baseline = answer_baseline
        app.state.answer_baseline_factory = answer_baseline_factory
        app.state.agent_runtime = agent_runtime
        app.state.agent_runtime_factory = agent_runtime_factory
        app.state.conversation_store = conversation_store or ConversationStore()
        app.state.conversation_memory_service = conversation_memory_service
        app.state.statistics_tool_adapter = (
            statistics_tool_adapter
            if statistics_tool_adapter is not None
            else MCPStatisticsAdapter(app_settings)
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_app_state(app)
        logger = configure_logging("policylens-api", app.state.settings.log_level)
        logger.info(
            "API service starting", extra={"event": "service_starting", "status": "starting"}
        )
        yield

    app = FastAPI(title="PolicyLens API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def initialize_vercel_state(request: Request, call_next: Any) -> Any:
        # Vercel's ASGI adapter does not send lifespan startup/shutdown events.
        if os.environ.get("VERCEL") and not hasattr(request.app.state, "settings"):
            async with state_initialization_lock:
                if not hasattr(request.app.state, "settings"):
                    initialize_app_state(request.app)
        return await call_next(request)

    frontend_origin = (
        str(settings.frontend_origin).rstrip("/") if settings is not None else get_frontend_origin()
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(frontend_origin),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Accept", "Content-Type", "Range", "X-Workspace-ID"],
        expose_headers=[
            "Accept-Ranges",
            "Content-Disposition",
            "Content-Length",
            "Content-Range",
        ],
    )
    app.include_router(health_router)
    app.include_router(model_capabilities_router)
    app.include_router(retrieval_router)
    app.include_router(agent_router)
    app.include_router(sessions_router)
    app.include_router(evaluation_summary_router)
    app.include_router(source_files_router)
    return app


app = create_app()
