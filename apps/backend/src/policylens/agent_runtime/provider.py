from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents import OpenAIProvider
from openai import AsyncOpenAI

from policylens.settings import AppSettings


class AgentConfigurationError(RuntimeError):
    """The explicitly configured agent provider cannot be initialized safely."""


def build_openai_agent_model(
    settings: AppSettings,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[OpenAIProvider, Any]:
    if settings.model_provider != "openai":
        raise AgentConfigurationError("Feature 004 requires MODEL_PROVIDER=openai")

    api_key = settings.openai_api_key.get_secret_value().strip() if settings.openai_api_key else ""
    model_id = settings.effective_openai_model
    if not api_key or not model_id:
        raise AgentConfigurationError("OpenAI agent requires a configured API key and model")

    base_url = str(settings.openai_base_url) if settings.openai_base_url else None
    if settings.openai_deployment_model and base_url is None:
        raise AgentConfigurationError("The Foundry deployment requires OPENAI_BASE_URL")
    if settings.openai_deployment_model and base_url is None:
        raise AgentConfigurationError("The Foundry deployment requires OPENAI_BASE_URL")

    if base_url is not None:
        client = (client_factory or AsyncOpenAI)(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
            timeout=settings.request_timeout_seconds,
            default_headers={"api-key": api_key},
        )
    else:
        client = (client_factory or AsyncOpenAI)(
            api_key=api_key,
            max_retries=0,
            timeout=settings.request_timeout_seconds,
        )
    provider = OpenAIProvider(
        openai_client=client,
        use_responses=base_url is None or settings.openai_use_responses_api,
    )
    return provider, provider.get_model(model_id)
