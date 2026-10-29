from __future__ import annotations

import platform
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from agents import Agent, ModelSettings, OpenAIProvider, RunConfig, Runner
from openai.types.shared import Reasoning
from pydantic import ValidationError

from policylens.agent_runtime.models import (
    AgentDraft,
    ModelCapabilities,
    ModelCapabilitySet,
    ModelLimits,
    ModelRoute,
    ModelRunMetadata,
    ReasoningEffort,
    StandaloneQuery,
)
from policylens.agent_runtime.provider import AgentConfigurationError, build_openai_agent_model
from policylens.agent_runtime.state import AgentRunLedger
from policylens.agent_runtime.tools import (
    AgentToolExecutionError,
    AgentToolExecutor,
    StatisticsToolAdapter,
    build_query_statistics_tool,
)
from policylens.agent_runtime.traces import SafeAgentRunHooks
from policylens.agent_runtime.usage import (
    model_usage_from_provider,
    reasoning_summary_from_responses,
)
from policylens.settings import MAX_AGENT_OUTPUT_TOKENS_LIMIT, AppSettings

RuntimeRunner = Callable[..., Awaitable[Any]]
ProviderBuilder = Callable[[AppSettings], tuple[OpenAIProvider, Any]]

_REASONING_OUTPUT_TOKEN_MULTIPLIERS = {
    "none": 1,
    "low": 2,
    "medium": 4,
    "high": 8,
}


@dataclass(frozen=True)
class ModelGatewayContext:
    instructions: str
    input: str
    ledger: AgentRunLedger
    statistics_adapter: StatisticsToolAdapter | None
    reasoning_effort: ReasoningEffort = "none"


@dataclass(frozen=True)
class ModelGatewayResult:
    draft: AgentDraft
    metadata: ModelRunMetadata


class ModelGateway(Protocol):
    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def discover_capabilities(self) -> ModelCapabilities: ...

    async def run_agent(self, context: ModelGatewayContext) -> ModelGatewayResult: ...


def _output_token_budget(settings: AppSettings, reasoning_effort: ReasoningEffort) -> int:
    multiplier = _REASONING_OUTPUT_TOKEN_MULTIPLIERS[reasoning_effort]
    return min(
        settings.max_agent_output_tokens * multiplier,
        MAX_AGENT_OUTPUT_TOKENS_LIMIT,
    )


class OpenAIModelGateway:
    def __init__(
        self,
        settings: AppSettings,
        *,
        runner: RuntimeRunner = Runner.run,
        provider_builder: ProviderBuilder = build_openai_agent_model,
    ) -> None:
        if settings.model_provider != "openai":
            raise AgentConfigurationError("OpenAI gateway requires MODEL_PROVIDER=openai")
        self._settings = settings
        self._runner = runner
        self._provider_builder = provider_builder
        model_id = settings.effective_openai_model
        if not model_id:
            raise AgentConfigurationError("OpenAI gateway requires a configured model ID")
        self._model_id = model_id

    @property
    def capabilities(self) -> ModelCapabilities:
        uses_chat_completions = (
            self._settings.openai_base_url is not None
            and not self._settings.openai_use_responses_api
        )
        route: ModelRoute = (
            "openai_chat_completions" if uses_chat_completions else "openai_responses"
        )
        max_output_tokens = _output_token_budget(
            self._settings,
            "high" if route == "openai_responses" else "none",
        )
        return ModelCapabilities(
            provider="openai",
            model_id=self._model_id,
            route=route,
            ready=True,
            capabilities=ModelCapabilitySet(
                native_tool_calls=True,
                native_json_schema=True,
                host_action_envelope=False,
                streaming=True,
                usage_reporting=True,
            ),
            limits=ModelLimits(
                max_input_chars=50000,
                max_output_tokens=max_output_tokens,
                timeout_seconds=self._settings.request_timeout_seconds,
            ),
            server_version=None,
            platform=f"{platform.system()} {platform.machine()}",
            limitations=(),
        )

    async def discover_capabilities(self) -> ModelCapabilities:
        return self.capabilities

    async def rewrite_query(self, instructions: str, input: str) -> str:
        provider, model = self._provider_builder(self._settings)
        uses_custom_chat_completions = self._settings.openai_base_url is not None and not (
            self._settings.openai_use_responses_api
        )
        model_settings = ModelSettings(
            temperature=None if uses_custom_chat_completions else 0.0,
            reasoning=Reasoning(effort="none"),
            max_tokens=None if uses_custom_chat_completions else 200,
            extra_args=({"max_completion_tokens": 200} if uses_custom_chat_completions else None),
            timeout=self._settings.request_timeout_seconds,
            store=False if self._settings.openai_base_url is None else None,
        )
        agent = Agent(
            name="PolicyLens query rewriter",
            instructions=instructions,
            model=model,
            model_settings=model_settings,
            output_type=StandaloneQuery,
        )
        result = await self._runner(
            agent,
            input,
            max_turns=1,
            run_config=RunConfig(
                model_provider=provider,
                model_settings=model_settings,
                tracing_disabled=True,
                trace_include_sensitive_data=False,
                workflow_name="PolicyLens query rewriter",
            ),
        )
        return StandaloneQuery.model_validate(result.final_output).query

    async def run_agent(self, context: ModelGatewayContext) -> ModelGatewayResult:
        provider, model = self._provider_builder(self._settings)
        uses_custom_endpoint = self._settings.openai_base_url is not None
        uses_custom_chat_completions = uses_custom_endpoint and not (
            self._settings.openai_use_responses_api
        )
        effective_reasoning_effort = (
            "none" if uses_custom_chat_completions else context.reasoning_effort
        )
        max_output_tokens = _output_token_budget(
            self._settings,
            effective_reasoning_effort,
        )
        tools: list[Any] = []
        if context.statistics_adapter is not None:
            executor = AgentToolExecutor(
                context.statistics_adapter,
                context.ledger,
                self._settings,
            )
            tools.append(
                build_query_statistics_tool(
                    executor,
                    structured_output_schema=not uses_custom_chat_completions,
                )
            )
        model_settings = ModelSettings(
            temperature=None if uses_custom_chat_completions else 0.0,
            reasoning=Reasoning(
                effort=effective_reasoning_effort,
                summary=(
                    "auto"
                    if not uses_custom_endpoint and effective_reasoning_effort != "none"
                    else None
                ),
            ),
            max_tokens=(None if uses_custom_chat_completions else max_output_tokens),
            extra_args=(
                {"max_completion_tokens": self._settings.max_agent_output_tokens}
                if uses_custom_chat_completions
                else None
            ),
            parallel_tool_calls=False,
            timeout=self._settings.request_timeout_seconds,
            store=False if self._settings.openai_base_url is None else None,
            preserve_raw_usage=True,
        )
        agent = Agent(
            name="PolicyLens bounded research agent",
            instructions=context.instructions,
            model=model,
            model_settings=model_settings,
            tools=tools,
            output_type=AgentDraft,
        )
        run_config = RunConfig(
            model_provider=provider,
            model_settings=model_settings,
            tracing_disabled=True,
            trace_include_sensitive_data=False,
            workflow_name="PolicyLens bounded research agent",
        )
        started_at = perf_counter()
        result = await self._runner(
            agent,
            context.input,
            context=context.ledger,
            max_turns=self._settings.max_agent_turns,
            run_config=run_config,
            hooks=SafeAgentRunHooks(
                context.ledger,
                model_route=self.capabilities.route,
                reasoning_effort=effective_reasoning_effort,
            ),
        )
        if context.ledger.tool_error_code is not None:
            raise AgentToolExecutionError(context.ledger.tool_error_code)
        try:
            draft = AgentDraft.model_validate(result.final_output)
        except ValidationError:
            raise
        sdk_usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        usage = model_usage_from_provider(sdk_usage)
        reasoning_summary = reasoning_summary_from_responses(getattr(result, "raw_responses", ()))
        metadata = ModelRunMetadata(
            provider="openai",
            model_id=self._model_id,
            prompt_version="agent-v4",
            latency_ms=(perf_counter() - started_at) * 1000,
            usage=usage,
            capabilities=self.capabilities,
            reasoning_effort=effective_reasoning_effort,
            reasoning_summary=reasoning_summary,
            fallback_decision="none",
        )
        return ModelGatewayResult(draft=draft, metadata=metadata)


def build_model_gateway(
    settings: AppSettings,
    *,
    runner: RuntimeRunner = Runner.run,
    provider_builder: ProviderBuilder = build_openai_agent_model,
    statistics_adapter: StatisticsToolAdapter | None = None,
) -> ModelGateway:
    if settings.model_provider == "openai":
        return OpenAIModelGateway(
            settings,
            runner=runner,
            provider_builder=provider_builder,
        )
    from policylens.agent_runtime.mlx_provider import MLXModelGateway

    return MLXModelGateway(settings)
