from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, ValidationError

from policylens.agent_runtime.gateway import build_model_gateway
from policylens.agent_runtime.models import AgentAnswerResponse, ModelProviderName
from policylens.agent_runtime.runtime import AgentRuntime
from policylens.mcp.client import MCPStatisticsAdapter
from policylens.retrieval.models import StrictModel
from policylens.settings import PROJECT_ROOT, AppSettings

if TYPE_CHECKING:
    from scripts.evaluate_agent import AgentEvaluationCase, AgentEvaluationCaseSet

_CASE_MODULE: Any = import_module(
    f"{__package__}.evaluate_agent" if __package__ else "evaluate_agent"
)

ProviderName = ModelProviderName
RunStatus = Literal["succeeded", "failed", "skipped"]
QualityMetric = Annotated[float, Field(ge=0, le=1)] | Literal["not_measured"] | None
MemoryMetric = Annotated[int, Field(ge=0)] | Literal["not_measured"] | None
CostMetric = Annotated[float, Field(ge=0)] | Literal["not_measured"] | None

DEFAULT_CASES = PROJECT_ROOT / "data/evaluation/agent-tool-cases.json"
DEFAULT_JSON_REPORT = PROJECT_ROOT / "data/evaluation/provider-comparison.json"
DEFAULT_MARKDOWN_REPORT = PROJECT_ROOT / "docs/evaluation/provider-comparison.md"


class ProviderDescriptor(StrictModel):
    provider: ProviderName
    model_id: str = Field(min_length=1, max_length=300)
    route: str = Field(min_length=1, max_length=100)
    runtime_version: str | None = Field(default=None, max_length=100)


class UsageMetrics(StrictModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class ProviderCaseObservation(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    index_version: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    provider: ProviderName
    status: RunStatus
    tool_selected: bool | None = None
    arguments_valid: bool | None = None
    structured_valid: bool
    latency_ms: float | None = Field(default=None, ge=0)
    usage: UsageMetrics | None = None
    groundedness: QualityMetric = "not_measured"
    answer_quality: QualityMetric = "not_measured"
    memory_bytes: MemoryMetric = "not_measured"
    cost_usd: CostMetric = "not_measured"


class ProviderCaseResult(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    index_version: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    provider: ProviderName
    status: RunStatus
    tool_selected: bool | None
    arguments_valid: bool | None
    structured_valid: bool
    latency_ms: float | None = Field(ge=0)
    usage: UsageMetrics | None
    groundedness: QualityMetric
    answer_quality: QualityMetric
    memory_bytes: MemoryMetric
    cost_usd: CostMetric


class ProviderComparisonSummary(StrictModel):
    structured_valid_rate: float | None = Field(ge=0, le=1)
    tool_selection_rate: float | None = Field(ge=0, le=1)
    groundedness: QualityMetric
    answer_quality: QualityMetric
    mean_latency_ms: float | None = Field(ge=0)
    memory_bytes: MemoryMetric
    cost_usd: CostMetric


class ProviderComparisonReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    case_set_id: str = Field(min_length=1, max_length=100)
    case_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_version: Literal["agent-v1", "agent-v2"] = "agent-v2"
    created_at: datetime
    platform: str = Field(min_length=1, max_length=200)
    providers: tuple[ProviderDescriptor, ...] = Field(min_length=1, max_length=2)
    case_count: int = Field(ge=1, le=100)
    results: tuple[ProviderCaseResult, ...] = Field(max_length=200)
    summary: ProviderComparisonSummary
    limitations: tuple[str, ...] = Field(max_length=30)
    live_requests_made: bool


def _load_case_set(path: Path) -> AgentEvaluationCaseSet:
    return _CASE_MODULE.AgentEvaluationCaseSet.load(path)


def _skipped_observation(case_id: str, provider: ProviderName) -> ProviderCaseObservation:
    return ProviderCaseObservation(
        case_id=case_id,
        provider=provider,
        status="skipped",
        structured_valid=False,
    )


def _average_quality(values: list[QualityMetric]) -> QualityMetric:
    scores = [value for value in values if isinstance(value, (int, float))]
    if scores:
        return sum(scores) / len(scores)
    return "not_measured"


def _summary(
    results: tuple[ProviderCaseResult, ...],
    cases_by_id: dict[str, AgentEvaluationCase],
) -> ProviderComparisonSummary:
    attempted = [result for result in results if result.status != "skipped"]
    structured_rate = (
        sum(result.structured_valid for result in attempted) / len(attempted) if attempted else None
    )
    tool_results = [
        (result.tool_selected, cases_by_id[result.case_id].requires_tool)
        for result in attempted
        if result.tool_selected is not None
    ]
    tool_rate = (
        sum(selected == expected for selected, expected in tool_results) / len(tool_results)
        if tool_results
        else None
    )
    latencies = [result.latency_ms for result in attempted if result.latency_ms is not None]

    groundedness = _average_quality([result.groundedness for result in attempted])
    answer_quality = _average_quality([result.answer_quality for result in attempted])
    measured_memory = [
        result.memory_bytes
        for result in attempted
        if isinstance(result.memory_bytes, int) and not isinstance(result.memory_bytes, bool)
    ]
    memory_bytes: MemoryMetric = "not_measured"
    if attempted and len(measured_memory) == len(attempted):
        memory_bytes = max(measured_memory)
    measured_cost = [
        result.cost_usd
        for result in attempted
        if isinstance(result.cost_usd, (int, float)) and not isinstance(result.cost_usd, bool)
    ]
    cost_usd: CostMetric = "not_measured"
    if attempted and len(measured_cost) == len(attempted):
        cost_usd = sum(measured_cost)

    return ProviderComparisonSummary(
        structured_valid_rate=structured_rate,
        tool_selection_rate=tool_rate,
        groundedness=groundedness,
        answer_quality=answer_quality,
        mean_latency_ms=sum(latencies) / len(latencies) if latencies else None,
        memory_bytes=memory_bytes,
        cost_usd=cost_usd,
    )


def build_provider_comparison(
    *,
    case_set: AgentEvaluationCaseSet,
    case_set_sha256: str,
    providers: tuple[ProviderDescriptor, ...],
    observations: tuple[ProviderCaseObservation, ...] = (),
    limitations: tuple[str, ...] = (),
    live_requests_made: bool = False,
    platform_name: str | None = None,
) -> ProviderComparisonReport:
    provider_names = [item.provider for item in providers]
    if len(provider_names) != len(set(provider_names)):
        raise ValueError("provider descriptors must not contain duplicates")

    cases_by_id = {case.case_id: case for case in case_set.cases}
    observations_by_key: dict[tuple[str, ProviderName], ProviderCaseObservation] = {}
    for incoming_observation in observations:
        key = (incoming_observation.case_id, incoming_observation.provider)
        if incoming_observation.case_id not in cases_by_id:
            raise ValueError("observation contains a case outside the frozen case set")
        if incoming_observation.provider not in provider_names:
            raise ValueError("observation provider has no matching descriptor")
        if key in observations_by_key:
            raise ValueError("duplicate provider observation for a frozen case")
        observations_by_key[key] = incoming_observation

    results: list[ProviderCaseResult] = []
    for provider in providers:
        for case in case_set.cases:
            observation = observations_by_key.get((case.case_id, provider.provider))
            if observation is None:
                observation = _skipped_observation(case.case_id, provider.provider)
            results.append(ProviderCaseResult(**observation.model_dump()))

    result_tuple = tuple(results)
    report_limitations = list(dict.fromkeys(limitations))
    if any(item.provider == "mlx" for item in providers) and sys.platform.startswith("linux"):
        report_limitations.append(
            "This Linux host cannot verify Apple-silicon MLX execution or hardware parity."
        )
    report_limitations.extend(
        [
            "Groundedness and answer quality require human review and are not inferred from "
            "schema validity.",
            "Memory and cost remain not_measured unless the provider supplies trustworthy "
            "measurements.",
            "A succeeded case means its response status matched the frozen expected_status; "
            "calculation values are not scored.",
        ]
    )

    return ProviderComparisonReport(
        case_set_id=case_set.case_set_id,
        case_set_sha256=case_set_sha256,
        created_at=datetime.now(UTC),
        platform=(platform_name or platform.platform())[:200],
        providers=providers,
        case_count=len(case_set.cases),
        results=result_tuple,
        summary=_summary(result_tuple, cases_by_id),
        limitations=tuple(dict.fromkeys(report_limitations))[:30],
        live_requests_made=live_requests_made,
    )


def _distribution_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _provider_settings(provider: ProviderName) -> AppSettings | None:
    try:
        return AppSettings(model_provider=provider)
    except ValidationError:
        return None


def provider_descriptor(
    provider: ProviderName,
    *,
    mlx_runtime_version: str | None = None,
) -> ProviderDescriptor:
    settings = _provider_settings(provider)
    if provider == "openai":
        if settings is not None:
            model_id = settings.effective_openai_model or "not_configured"
            route = (
                "openai_chat_completions"
                if settings.openai_base_url is not None
                else "openai_responses"
            )
        else:
            model_id = (
                os.environ.get("OPENAI_DEPLOYMENT_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or "not_configured"
            )
            route = (
                "openai_chat_completions"
                if os.environ.get("OPENAI_BASE_URL")
                else "openai_responses"
            )
        agents_version = _distribution_version("openai-agents")
        openai_version = _distribution_version("openai")
        runtime_version = (
            f"openai-agents {agents_version}; openai {openai_version}"
            if agents_version and openai_version
            else None
        )
    else:
        if settings is not None:
            model_id = (settings.mlx_model or "").strip() or "not_configured"
        else:
            model_id = (os.environ.get("MLX_MODEL") or "").strip() or "not_configured"
        route = "mlx_chat_completions"
        runtime_version = mlx_runtime_version or os.environ.get("MLX_RUNTIME_VERSION")

    return ProviderDescriptor(
        provider=provider,
        model_id=model_id,
        route=route,
        runtime_version=runtime_version,
    )


def _empty_observations(
    case_set: AgentEvaluationCaseSet,
    provider: ProviderName,
    status: Literal["failed", "skipped"],
) -> list[ProviderCaseObservation]:
    return [
        ProviderCaseObservation(
            case_id=case.case_id,
            provider=provider,
            status=status,
            structured_valid=False,
        )
        for case in case_set.cases
    ]


def _observation_from_response(
    case_id: str,
    expected_status: str,
    response: AgentAnswerResponse,
    elapsed_ms: float,
) -> ProviderCaseObservation:
    metadata = response.model_metadata
    tool_selected = any(event.event_type == "tool_started" for event in response.events)
    if response.error_code == "TOOL_INVALID_ARGUMENTS":
        tool_selected = True
    arguments_valid = response.error_code != "TOOL_INVALID_ARGUMENTS" if tool_selected else None
    if metadata is None and response.status != "failed_safe":
        status: RunStatus = "skipped"
    elif response.status == expected_status:
        status = "succeeded"
    else:
        status = "failed"

    usage = None
    latency_ms = None
    memory_bytes: MemoryMetric = "not_measured"
    cost_usd: CostMetric = "not_measured"
    if metadata is not None:
        usage = UsageMetrics(
            prompt_tokens=metadata.usage.prompt_tokens,
            completion_tokens=metadata.usage.completion_tokens,
            total_tokens=metadata.usage.total_tokens,
        )
        latency_ms = metadata.latency_ms
        if metadata.usage.memory_bytes is not None:
            memory_bytes = metadata.usage.memory_bytes
        if metadata.usage.cost_usd is not None:
            cost_usd = metadata.usage.cost_usd

    return ProviderCaseObservation(
        case_id=case_id,
        index_version=response.index_version,
        provider=response.provider,
        status=status,
        tool_selected=tool_selected,
        arguments_valid=arguments_valid,
        structured_valid=(metadata is not None and response.error_code != "OUTPUT_SCHEMA_INVALID"),
        latency_ms=(
            latency_ms if latency_ms is not None else (elapsed_ms if status == "failed" else None)
        ),
        usage=usage,
        memory_bytes=memory_bytes,
        cost_usd=cost_usd,
    )


async def _execute_provider(
    provider: ProviderName,
    case_set: AgentEvaluationCaseSet,
    *,
    allow_openai_live: bool,
) -> tuple[list[ProviderCaseObservation], list[str], bool]:
    live_requests_made = False
    try:
        settings = AppSettings(model_provider=provider)
    except ValidationError:
        return (
            _empty_observations(case_set, provider, "failed"),
            [f"{provider} configuration is incomplete or invalid; details were redacted."],
            False,
        )

    if settings.embedding_provider == "openai" and not allow_openai_live:
        return (
            _empty_observations(case_set, provider, "skipped"),
            [
                "OpenAI embeddings are configured; pass --allow-openai-live to permit "
                "external requests."
            ],
            False,
        )

    try:
        from policylens.api.retrieval import _create_runtime

        service, citation_validator = _create_runtime(settings)
        if citation_validator is None:
            raise RuntimeError("citation validator unavailable")
        statistics_adapter = MCPStatisticsAdapter(settings)
        gateway = build_model_gateway(settings)
        if provider == "mlx":
            live_requests_made = True
            capabilities = await gateway.discover_capabilities()
            if not capabilities.ready:
                raise RuntimeError("local model is not ready")
        runtime = AgentRuntime(
            settings,
            service,
            citation_validator,
            statistics_adapter=statistics_adapter,
            model_gateway=gateway,
        )
    except Exception:
        return (
            _empty_observations(case_set, provider, "failed"),
            [f"{provider} runtime initialization failed; details were redacted."],
            live_requests_made,
        )

    observations: list[ProviderCaseObservation] = []
    for case in case_set.cases:
        started_at = perf_counter()
        try:
            response = await runtime.answer(case.to_request())
            live_requests_made = (
                live_requests_made
                or response.model_metadata is not None
                or any(
                    event.event_type in {"model_started", "model_completed"}
                    for event in response.events
                )
            )
        except Exception:
            observations.append(
                ProviderCaseObservation(
                    case_id=case.case_id,
                    provider=provider,
                    status="failed",
                    structured_valid=False,
                    latency_ms=(perf_counter() - started_at) * 1000,
                )
            )
            continue
        observations.append(
            _observation_from_response(
                case.case_id,
                case.expected_status,
                response,
                (perf_counter() - started_at) * 1000,
            )
        )
    return observations, [], live_requests_made


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def _markdown_cell(value: object) -> str:
    if value is None:
        return "not measured"
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_reports(
    report: ProviderComparisonReport,
    *,
    json_path: Path = DEFAULT_JSON_REPORT,
    markdown_path: Path = DEFAULT_MARKDOWN_REPORT,
) -> None:
    report_json = report.model_dump(mode="json")
    _atomic_write(
        json_path,
        json.dumps(report_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    lines = [
        "# Feature 006 Provider Comparison",
        "",
        f"Case set: `{report.case_set_id}` (`{report.case_set_sha256}`)",
        f"Prompt version: `{report.prompt_version}`",
        f"Platform: `{report.platform}`",
        f"Live provider requests made: `{str(report.live_requests_made).lower()}`",
        "",
        "## Providers",
        "",
        "| Provider | Model ID | Route | Runtime |",
        "|---|---|---|---|",
    ]
    for descriptor in report.providers:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    descriptor.provider,
                    descriptor.model_id,
                    descriptor.route,
                    descriptor.runtime_version,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Case | Index version | Provider | Status | Tool selected | "
            "Structured valid | Latency ms |",
            "|---|---|---|---|---|---|---:|",
        ]
    )
    for result in report.results:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    result.case_id,
                    result.index_version,
                    result.provider,
                    result.status,
                    result.tool_selected,
                    result.structured_valid,
                    result.latency_ms,
                )
            )
            + " |"
        )
    lines.extend(["", "## Summary", ""])
    for key, value in report.summary.model_dump(mode="json").items():
        lines.append(f"- `{key}`: `{_markdown_cell(value)}`")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append("")
    _atomic_write(markdown_path, "\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare configured generation providers safely.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--providers",
        action="append",
        choices=("openai", "mlx"),
        help="Provider to include; repeat to compare both (default: both).",
    )
    parser.add_argument(
        "--allow-openai-live",
        action="store_true",
        help="Explicitly allow live OpenAI generation and configured OpenAI embeddings.",
    )
    parser.add_argument(
        "--run-mlx",
        action="store_true",
        help="Explicitly probe and run the configured loopback MLX provider.",
    )
    parser.add_argument(
        "--mlx-runtime-version",
        help="MLX-LM version reported by the separate server environment.",
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    arguments = parser.parse_args(argv)

    case_set = _load_case_set(arguments.cases)
    provider_names: tuple[ProviderName, ...] = tuple(arguments.providers or ("openai", "mlx"))
    if len(provider_names) != len(set(provider_names)):
        parser.error("--providers may name each provider only once")
    descriptors = tuple(
        provider_descriptor(name, mlx_runtime_version=arguments.mlx_runtime_version)
        for name in provider_names
    )

    observations: list[ProviderCaseObservation] = []
    limitations: list[str] = []
    live_requests_made = False
    for provider in provider_names:
        run_provider = (provider == "openai" and arguments.allow_openai_live) or (
            provider == "mlx" and arguments.run_mlx
        )
        if not run_provider:
            observations.extend(_empty_observations(case_set, provider, "skipped"))
            if provider == "openai":
                limitations.append("OpenAI was not invoked; pass --allow-openai-live to opt in.")
            else:
                limitations.append("MLX was not invoked; pass --run-mlx to opt in.")
            continue
        provider_observations, provider_limitations, requests_made = asyncio.run(
            _execute_provider(
                provider,
                case_set,
                allow_openai_live=arguments.allow_openai_live,
            )
        )
        observations.extend(provider_observations)
        limitations.extend(provider_limitations)
        live_requests_made = live_requests_made or requests_made

    report = build_provider_comparison(
        case_set=case_set,
        case_set_sha256=hashlib.sha256(arguments.cases.read_bytes()).hexdigest(),
        providers=descriptors,
        observations=tuple(observations),
        limitations=tuple(limitations),
        live_requests_made=live_requests_made,
    )
    write_reports(
        report,
        json_path=arguments.json_output,
        markdown_path=arguments.markdown_output,
    )
    print(
        json.dumps(
            {
                "case_count": report.case_count,
                "case_set_id": report.case_set_id,
                "live_requests_made": report.live_requests_made,
                "provider_count": len(report.providers),
                "report": str(arguments.markdown_output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
