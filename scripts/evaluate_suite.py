from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import UUID, uuid4

from policylens.agent_runtime.fault_injection import (
    CATEGORY_FAULTS,
    FaultInjectingStatisticsAdapter,
)
from policylens.agent_runtime.models import AgentAnswerResponse, AgentCalculationRecord
from policylens.agent_runtime.runtime import AgentRetrievalService, AgentRuntime
from policylens.agent_runtime.tools import StatisticsToolAdapter
from policylens.mcp.client import MCPStatisticsAdapter
from policylens.retrieval.citations import CitationValidator, RetrievalRunRegistry
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import EmbeddingProvider, create_embedding_provider
from policylens.retrieval.evaluation import (
    EvaluationCaseResult,
    RetrievalCase,
    RetrievalCaseSet,
    evaluate_retrieval,
)
from policylens.retrieval.generation import (
    BaselineAnswerResponse,
    NonAgentRagBaseline,
)
from policylens.retrieval.models import (
    BlockLocation,
    RetrievalMode,
    RetrievalRequest,
    RetrievalRun,
    RetrievedEvidence,
)
from policylens.retrieval.reranking import create_reranker
from policylens.settings import PROJECT_ROOT, AppSettings
from scripts.evaluation_case_set import (
    EvaluationCase,
    EvaluationCaseSet,
    EvaluationSplit,
    release_gate_issues,
    validate_case_anchors,
)
from scripts.evaluation_errors import EvaluationErrorRecord, load_error_records, summarize_errors
from scripts.evaluation_judge import (
    AI_JUDGE_RUBRIC_VERSION,
    EvaluationJudge,
    EvaluationJudgeError,
    EvaluationJudgeObservation,
)
from scripts.evaluation_metrics import (
    CaseMetricRecord,
    ndcg_at_k,
    recall_at_k_by_group,
    reciprocal_rank,
    summarize_case_metrics,
)
from scripts.evaluation_registry import (
    DEFAULT_RUN_MANIFEST,
    EvaluationRunRecord,
    append_run_record,
    build_run_record,
    sha256_file,
)
from scripts.evaluation_review import (
    EvaluationReviewRecord,
    load_review_records,
    review_category_coverage,
    reviewer_agreement,
    summarize_output_reviews,
)

DEFAULT_CASES = PROJECT_ROOT / "data/evaluation/feature007-cases.json"
DEFAULT_REPORT = PROJECT_ROOT / "docs/evaluation/evaluation-report.md"
_RETRIEVAL_MODES: tuple[RetrievalMode, ...] = ("bm25", "dense", "hybrid")
_RERANKED_MODE = "hybrid+cross_encoder"
SplitSelector = Literal["all", "dev", "test"]
AnchorValidator = Callable[..., tuple[str, ...]]
EmbedderFactory = Callable[[RetrievalSettings], EmbeddingProvider]
RetrievalEvaluator = Callable[..., dict[str, Any]]
GenerationExecutor = Callable[..., tuple[tuple[CaseMetricRecord, ...], tuple[str, ...], bool]]


class EvaluationSuiteError(ValueError):
    """The suite cannot safely run with the provided evaluation inputs."""


class _CaseFixtureRetrievalService:
    def __init__(self, run: RetrievalRun) -> None:
        self._run = run

    def search(self, _request: RetrievalRequest) -> RetrievalRun:
        return self._run


def _synthetic_conflict_evidence(
    *, source_id: str, value: int, rank: int, mode: RetrievalMode
) -> RetrievedEvidence:
    text = (
        f"SYNTHETIC EVALUATION DATA ONLY. India youth unemployment in 2025 was {value}%. "
        "This is a fabricated conflict fixture, not a real statistic."
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return RetrievedEvidence(
        passage_id=f"sha256:{digest}",
        source_id=source_id,
        title=f"Synthetic evaluation source {rank}",
        publisher="PolicyLens evaluation fixture",
        source_uri=f"urn:policylens:evaluation:{source_id}",
        text=text,
        source_content_sha256=digest,
        locations=(
            BlockLocation(
                page_number=1,
                block_id=source_id,
                start_char=0,
                end_char=len(text),
            ),
        ),
        section_path=("Synthetic evaluation fixture",),
        rank=rank,
        score=1.0 / rank,
        bm25_rank=rank,
        bm25_score=1.0 / rank,
        retrieval_mode=mode,
        licence="Synthetic evaluation data",
    )


def _fixture_context(evidence: Sequence[RetrievedEvidence]) -> str:
    return "\n\n".join(
        f'<UNTRUSTED_EVIDENCE source_id="{html.escape(item.source_id, quote=True)}" '
        f'passage_id="{html.escape(item.passage_id, quote=True)}">\n'
        f"{html.escape(item.text, quote=False)}\n</UNTRUSTED_EVIDENCE>"
        for item in evidence
    )


def _evaluation_fixture_run(run: RetrievalRun, case: EvaluationCase) -> RetrievalRun | None:
    if not case.adversarial_fixture:
        return None
    if case.category == "conflicting_evidence":
        evidence = (
            _synthetic_conflict_evidence(
                source_id="synthetic-conflict-source-a",
                value=10,
                rank=1,
                mode=case.mode,
            ),
            _synthetic_conflict_evidence(
                source_id="synthetic-conflict-source-b",
                value=12,
                rank=2,
                mode=case.mode,
            ),
        )
        return RetrievalRun(
            run_id=uuid4(),
            index_version=run.index_version,
            status="found",
            evidence=evidence,
            context=_fixture_context(evidence),
        )
    if case.category == "retrieved_document_injection":
        return run.model_copy(
            update={
                "context": f"{run.context}\n\n{case.adversarial_fixture}",
            }
        )
    return None


def to_retrieval_case_set(
    cases: Sequence[EvaluationCase], *, set_id: str, lineage: str
) -> RetrievalCaseSet:
    selected = tuple(case for case in cases if case.expected_anchors)
    if not selected:
        raise EvaluationSuiteError("No approved cases contain retrieval anchors")
    return RetrievalCaseSet(
        schema_version="1.0",
        set_id=set_id,
        lineage=lineage,
        cases=tuple(
            RetrievalCase(
                case_id=case.case_id,
                query=case.question,
                filters=case.filters,
                expected_anchors=case.expected_anchors,
            )
            for case in selected
        ),
    )


def _relevance_by_passage(case: EvaluationCase, result: EvaluationCaseResult) -> dict[str, int]:
    anchors_by_key = {
        json.dumps(anchor.model_dump(mode="json", exclude_none=True), sort_keys=True): index
        for index, anchor in enumerate(case.expected_anchors)
    }
    grades: dict[str, int] = {}
    for grade in case.relevance_grades:
        anchor_key = json.dumps(
            grade.anchor.model_dump(mode="json", exclude_none=True), sort_keys=True
        )
        group_index = anchors_by_key.get(anchor_key)
        if group_index is None or group_index >= len(result.expected_passage_groups):
            continue
        for passage_id in result.expected_passage_groups[group_index]:
            grades[passage_id] = grade.grade
    if not grades:
        # Cases without author grades fall back to binary relevance for nDCG.
        grades = {passage_id: 1 for group in result.expected_passage_groups for passage_id in group}
    return grades


def _retrieval_records(
    case_set: EvaluationCaseSet,
    evaluation: dict[str, Any],
    *,
    split: EvaluationSplit | None,
    top_k: int,
) -> tuple[CaseMetricRecord, ...]:
    cases_by_id = {case.case_id: case for case in case_set.cases}
    records: list[CaseMetricRecord] = []
    for configuration in evaluation.get("configurations", ()):
        chunker = configuration.get("chunker", {})
        chunker_id = str(chunker.get("version", "unknown"))
        index_version = configuration.get("index_version")
        for mode, mode_results in configuration.get("case_results", {}).items():
            if mode not in (*_RETRIEVAL_MODES, _RERANKED_MODE):
                continue
            for raw_result in mode_results:
                if not isinstance(raw_result, dict):
                    continue
                case = cases_by_id.get(str(raw_result.get("case_id", "")))
                if case is None or (split is not None and case.split != split):
                    continue
                result = EvaluationCaseResult.model_validate(raw_result)
                retrieved = result.retrieved_passage_ids
                retrieved_at_k = retrieved[:top_k]
                anchor_hits = sum(
                    bool(set(retrieved_at_k).intersection(group))
                    for group in result.expected_passage_groups
                )
                relevant_ids = {
                    passage_id for group in result.expected_passage_groups for passage_id in group
                }
                graded = _relevance_by_passage(case, result)
                records.append(
                    CaseMetricRecord(
                        case_id=case.case_id,
                        condition_id=f"retrieval:{chunker_id}:{mode}",
                        category=case.category,
                        split=case.split,
                        expected_behavior=case.expected_behavior,
                        retrieval_mode="hybrid" if mode == _RERANKED_MODE else mode,
                        index_version=index_version,
                        retrieval_recall_at_k=recall_at_k_by_group(
                            retrieved, result.expected_passage_groups, top_k
                        ),
                        retrieval_anchor_hits=anchor_hits,
                        retrieval_anchor_count=len(result.expected_passage_groups),
                        reciprocal_rank=reciprocal_rank(retrieved, relevant_ids),
                        ndcg_at_k=ndcg_at_k(retrieved, graded, top_k),
                        empty_result=not bool(retrieved),
                        citation_completeness=1.0 if result.citation_complete else 0.0,
                        latency_ms=result.latency_ms,
                    )
                )
    return tuple(records)


TOOL_FAULT_ERROR_CODES = frozenset({"MCP_TIMEOUT", "MCP_UNAVAILABLE", "TOOL_MALFORMED_RESPONSE"})


def _observed_behavior(
    status: str,
    error_code: str | None = None,
) -> Literal["answer", "clarify", "abstain", "conflict", "block", "failed"]:
    if error_code in {"TOOL_INVALID_ARGUMENTS", "TOOL_PERMISSION_DENIED", "POLICY_BLOCKED"}:
        return "block"
    mapping: dict[str, Literal["answer", "clarify", "abstain", "conflict", "block"]] = {
        "answered": "answer",
        "clarification_required": "clarify",
        "abstained": "abstain",
        "conflict": "conflict",
        "blocked": "block",
    }
    if status == "failed_safe" and error_code in TOOL_FAULT_ERROR_CODES:
        # A tool outage handled with no claims is a safe, explicit abstention.
        return "abstain"
    return mapping.get(status, "failed")


def _citation_metrics(
    case: EvaluationCase,
    claims: Sequence[Any],
    *,
    has_answer: bool,
    calculations: Sequence[AgentCalculationRecord] = (),
) -> tuple[float | None, float | None, int | None, int | None]:
    citations = [citation for claim in claims for citation in claim.citations]
    calculation_rows = {
        (evidence.source_id, row_key)
        for calculation in calculations
        for evidence in calculation.evidence
        for row_key in evidence.row_keys
    }
    has_validated_evidence = bool(citations or calculation_rows)
    if not case.expected_anchors:
        return (1.0 if has_validated_evidence else None), None, None, None
    if not has_validated_evidence:
        return (
            (0.0 if has_answer else None),
            0.0 if has_answer else None,
            0 if has_answer else None,
            len(case.expected_anchors) if has_answer else None,
        )

    correct = all(
        citation.passage_id.startswith("sha256:")
        and len(citation.source_content_sha256) == 64
        and citation.source_id
        for citation in citations
    )
    matched = 0
    for anchor in case.expected_anchors:
        for citation in citations:
            if citation.source_id != anchor.source_id:
                continue
            if anchor.row_key is not None and citation.row_key == anchor.row_key:
                matched += 1
                break
            if (
                anchor.page_number is not None
                and citation.page_start is not None
                and citation.page_end is not None
                and citation.page_start <= anchor.page_number <= citation.page_end
                and anchor.marker is not None
                and " ".join(anchor.marker.casefold().split())
                in " ".join(citation.excerpt.casefold().split())
            ):
                matched += 1
                break
        else:
            if (
                anchor.row_key is not None
                and (anchor.source_id, anchor.row_key) in calculation_rows
            ):
                matched += 1
    return (
        1.0 if correct else 0.0,
        matched / len(case.expected_anchors),
        matched,
        len(case.expected_anchors),
    )


def _validated_tool_evidence(response: AgentAnswerResponse) -> tuple[str, ...]:
    serialized: list[str] = []
    for calculation in response.calculations:
        payload = {
            "tool_name": calculation.tool_name,
            "operation": calculation.operation,
            "formula": calculation.formula,
            "rounding": calculation.rounding,
            "rows": [
                row.model_dump(mode="json", exclude_none=True) for row in calculation.rows[:8]
            ],
            "omitted_row_count": max(0, len(calculation.rows) - 8),
            "sources": [
                {
                    "source_id": item.source_id,
                    "row_keys": [
                        key.model_dump(mode="json", exclude_none=True) for key in item.row_keys[:8]
                    ],
                    "omitted_row_key_count": max(0, len(item.row_keys) - 8),
                }
                for item in calculation.evidence[:8]
            ],
        }
        serialized.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return tuple(serialized)


def _usage_values(usage: object | None) -> tuple[int | None, int | None]:
    input_tokens = getattr(usage, "prompt_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "output_tokens", None)
    return (
        input_tokens if isinstance(input_tokens, int) and input_tokens >= 0 else None,
        output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else None,
    )


def _agent_metric_record(
    case: EvaluationCase,
    response: AgentAnswerResponse | None,
    *,
    provider: Literal["openai", "mlx"],
    model_id: str,
    condition_id: str,
    latency_ms: float,
    judge_status: Literal["completed", "failed", "skipped"] | None = None,
    judge_observation: EvaluationJudgeObservation | None = None,
    judge_model_id: str | None = None,
) -> CaseMetricRecord:
    if response is None:
        return CaseMetricRecord(
            case_id=case.case_id,
            condition_id=condition_id,
            category=case.category,
            split=case.split,
            expected_behavior=case.expected_behavior,
            observed_behavior="failed",
            provider=provider,
            model_id=model_id,
            expected_tool_selection=bool(case.required_tools),
            latency_ms=latency_ms,
            judge_status=judge_status,
            judge_model_id=judge_model_id,
        )
    selected_tool = any(event.event_type == "tool_started" for event in response.events)
    usage = response.model_metadata.usage if response.model_metadata else None
    input_tokens, output_tokens = _usage_values(usage)
    (
        citation_correctness,
        citation_completeness,
        citation_anchor_matches,
        citation_anchor_count,
    ) = _citation_metrics(
        case,
        response.claims,
        has_answer=response.status in {"answered", "conflict"},
        calculations=response.calculations,
    )
    estimated_cost = usage.cost_usd if usage is not None else None
    if judge_status == "failed":
        estimated_cost = None
    elif judge_observation is not None:
        estimated_cost = (
            usage.cost_usd + judge_observation.cost_usd
            if usage is not None
            and usage.cost_usd is not None
            and judge_observation.cost_usd is not None
            else None
        )
    return CaseMetricRecord(
        case_id=case.case_id,
        condition_id=condition_id,
        category=case.category,
        split=case.split,
        expected_behavior=case.expected_behavior,
        observed_behavior=_observed_behavior(response.status, response.error_code),
        expected_tool_selection=bool(case.required_tools),
        observed_tool_selection=selected_tool,
        tool_arguments_valid=(
            response.error_code != "TOOL_INVALID_ARGUMENTS"
            if selected_tool or response.error_code == "TOOL_INVALID_ARGUMENTS"
            else None
        ),
        structured_valid=(
            response.error_code != "OUTPUT_SCHEMA_INVALID"
            if response.model_metadata is not None
            else None
        ),
        citation_correctness=citation_correctness,
        citation_completeness=citation_completeness,
        citation_anchor_matches=citation_anchor_matches,
        citation_anchor_count=citation_anchor_count,
        validated_tool_result_count=len(response.calculations),
        provider=provider,
        model_id=response.model or model_id,
        route=(response.model_metadata.capabilities.route if response.model_metadata else None),
        prompt_version=(
            response.model_metadata.prompt_version if response.model_metadata else None
        ),
        index_version=response.index_version,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost,
        groundedness=(
            judge_observation.scores.groundedness if judge_observation is not None else None
        ),
        answer_relevance=(
            judge_observation.scores.answer_relevance if judge_observation is not None else None
        ),
        judge_status=judge_status,
        judge_model_id=(
            judge_observation.model_id if judge_observation is not None else judge_model_id
        ),
        judge_latency_ms=(judge_observation.latency_ms if judge_observation is not None else None),
        judge_input_tokens=(
            judge_observation.input_tokens if judge_observation is not None else None
        ),
        judge_output_tokens=(
            judge_observation.output_tokens if judge_observation is not None else None
        ),
    )


def _baseline_metric_record(
    case: EvaluationCase,
    response: BaselineAnswerResponse | None,
    *,
    provider: Literal["openai", "mlx"],
    model_id: str,
    route: str,
    condition_id: str,
    latency_ms: float,
) -> CaseMetricRecord:
    if response is None:
        return CaseMetricRecord(
            case_id=case.case_id,
            condition_id=condition_id,
            category=case.category,
            split=case.split,
            expected_behavior=case.expected_behavior,
            observed_behavior="failed",
            provider=provider,
            model_id=model_id,
            route=route,
            latency_ms=latency_ms,
        )
    usage = response.generation.usage if response.generation else None
    input_tokens, output_tokens = _usage_values(usage)
    (
        citation_correctness,
        citation_completeness,
        citation_anchor_matches,
        citation_anchor_count,
    ) = _citation_metrics(
        case,
        response.claims,
        has_answer=response.status == "answered",
    )
    return CaseMetricRecord(
        case_id=case.case_id,
        condition_id=condition_id,
        category=case.category,
        split=case.split,
        expected_behavior=case.expected_behavior,
        observed_behavior=(
            "answer"
            if response.status == "answered"
            else "abstain"
            if response.status == "abstained"
            else "failed"
        ),
        structured_valid=(response.error_code != "INVALID_MODEL_OUTPUT")
        if response.generation
        else None,
        citation_correctness=citation_correctness,
        citation_completeness=citation_completeness,
        citation_anchor_matches=citation_anchor_matches,
        citation_anchor_count=citation_anchor_count,
        provider=provider,
        model_id=response.generation.model_id if response.generation else model_id,
        route=route,
        prompt_version=(response.generation.prompt_version if response.generation else None),
        index_version=response.index_version,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _execute_generation(
    cases: Sequence[EvaluationCase],
    *,
    providers: tuple[Literal["openai", "mlx"], ...],
    allow_openai_live: bool,
    allow_mlx: bool,
    allow_mcp_tools: bool,
    ai_judge: bool,
    project_root: Path,
) -> tuple[tuple[CaseMetricRecord, ...], tuple[str, ...], bool]:
    from policylens.api.retrieval import _create_runtime

    records: list[CaseMetricRecord] = []
    notes: list[str] = []
    live_requests_made = False
    for provider in providers:
        if provider == "openai" and not allow_openai_live:
            notes.append(
                "OpenAI cases skipped; pass --allow-openai-live to authorize external calls."
            )
            continue
        if provider == "mlx" and not allow_mlx:
            notes.append("MLX cases skipped; pass --run-mlx to authorize the local model run.")
            continue
        try:
            settings = AppSettings(model_provider=provider, embedding_provider="local")
            retrieval_service, citation_validator = _create_runtime(settings)
            statistics_adapter = MCPStatisticsAdapter(settings) if allow_mcp_tools else None
            agent_runtime = AgentRuntime(
                settings,
                retrieval_service,
                citation_validator,
                statistics_adapter=statistics_adapter,
            )
            baseline = NonAgentRagBaseline.from_settings(settings, citation_validator)
            model_id = (
                settings.effective_openai_model if provider == "openai" else settings.mlx_model
            )
            if not model_id:
                raise ValueError("Selected provider has no configured model")
            route = (
                "mlx_chat_completions"
                if provider == "mlx"
                else "openai_chat_completions"
                if settings.openai_base_url is not None
                else "openai_responses"
            )
        except Exception:
            notes.append(f"{provider} generation runtime could not initialize; details redacted.")
            continue

        judge: EvaluationJudge | None = None
        judge_init_error: EvaluationJudgeError | None = None
        if ai_judge:
            try:
                judge = EvaluationJudge(settings)
            except EvaluationJudgeError as error:
                judge_init_error = error
                notes.append(f"{provider} AI judge could not initialize: {error.error_code}.")

        agent_async_runner = asyncio.Runner()
        for case in cases:
            if case.required_tools and not allow_mcp_tools:
                notes.append(
                    f"{provider} agent skipped {case.case_id}; "
                    "use --allow-mcp-tools to run tool cases."
                )
                continue
            case_retrieval_service: AgentRetrievalService = retrieval_service
            case_citation_validator = citation_validator
            case_baseline = baseline
            case_statistics_adapter: StatisticsToolAdapter | None = statistics_adapter
            fixture_run: RetrievalRun | None = None
            if case.category in {"conflicting_evidence", "retrieved_document_injection"}:
                original_run = retrieval_service.search(case.to_request())
                fixture_run = _evaluation_fixture_run(original_run, case)
                if fixture_run is not None:
                    case_retrieval_service = _CaseFixtureRetrievalService(fixture_run)
                    if fixture_run.run_id != original_run.run_id:
                        registry = RetrievalRunRegistry()
                        registry.register(fixture_run)
                        case_citation_validator = CitationValidator(registry)
                        case_baseline = NonAgentRagBaseline.from_settings(
                            settings, case_citation_validator
                        )
            started = perf_counter()
            agent_response: AgentAnswerResponse | None = None
            fault_mode = CATEGORY_FAULTS.get(case.category)
            case_runtime = agent_runtime
            if fixture_run is not None or (
                fault_mode is not None and statistics_adapter is not None
            ):
                if fault_mode is not None and statistics_adapter is not None:
                    case_statistics_adapter = FaultInjectingStatisticsAdapter(
                        statistics_adapter, fault_mode
                    )
                case_runtime = AgentRuntime(
                    settings,
                    case_retrieval_service,
                    case_citation_validator,
                    statistics_adapter=case_statistics_adapter,
                )
            try:
                agent_response = agent_async_runner.run(case_runtime.answer(case.to_request()))
            except Exception:
                pass
            elapsed_ms = (perf_counter() - started) * 1000
            if agent_response is not None and agent_response.status == "failed_safe":
                event_codes = sorted({e.error_code for e in agent_response.events if e.error_code})
                notes.append(
                    f"{provider} agent {case.case_id} failed safe: {agent_response.error_code} "
                    f"(events: {event_codes})."
                )
            if agent_response is not None and (
                agent_response.model_metadata is not None
                or any(event.event_type == "model_started" for event in agent_response.events)
            ):
                live_requests_made = True
            judge_observation: EvaluationJudgeObservation | None = None
            judge_status: Literal["completed", "failed", "skipped"] | None = None
            judge_model_id = judge.model_id if judge is not None else None
            if ai_judge:
                if (
                    agent_response is None
                    or _observed_behavior(agent_response.status, agent_response.error_code)
                    == "failed"
                    or agent_response.model_metadata is None
                ):
                    judge_status = "skipped"
                elif judge is None:
                    judge_status = "failed" if judge_init_error is not None else "skipped"
                else:
                    evidence = tuple(
                        citation.excerpt
                        for claim in agent_response.claims
                        for citation in claim.citations
                    )
                    answer = agent_response.answer or "\n".join(
                        claim.text for claim in agent_response.claims
                    )
                    if not answer:
                        answer = (
                            agent_response.abstention_reason
                            or agent_response.clarification_question
                            or agent_response.status
                        )
                    try:
                        judge_observation = judge.score(
                            question=case.question,
                            response_status=agent_response.status,
                            answer=answer,
                            evidence=evidence,
                            tool_evidence=_validated_tool_evidence(agent_response),
                        )
                        judge_status = "completed"
                    except EvaluationJudgeError as error:
                        judge_status = "failed"
                        notes.append(
                            f"{provider} AI judge failed for {case.case_id}: {error.error_code}."
                        )
                    if provider == "openai":
                        live_requests_made = True
            records.append(
                _agent_metric_record(
                    case,
                    agent_response,
                    provider=provider,
                    model_id=model_id,
                    condition_id=f"{provider}:agent",
                    latency_ms=elapsed_ms,
                    judge_status=judge_status,
                    judge_observation=judge_observation,
                    judge_model_id=judge_model_id,
                )
            )

            baseline_response: BaselineAnswerResponse | None = None
            started = perf_counter()
            try:
                run = case_retrieval_service.search(case.to_request())
                if run.status == "no_results":
                    baseline_response = NonAgentRagBaseline.abstained(run)
                else:
                    baseline_response = case_baseline.answer(case.question, run)
            except Exception:
                pass
            elapsed_ms = (perf_counter() - started) * 1000
            if baseline_response is not None and baseline_response.generation is not None:
                live_requests_made = True
            records.append(
                _baseline_metric_record(
                    case,
                    baseline_response,
                    provider=provider,
                    model_id=model_id,
                    route=route,
                    condition_id=f"{provider}:non_agent",
                    latency_ms=elapsed_ms,
                )
            )
        if judge is not None:
            judge.close()
        agent_async_runner.close()
    return tuple(records), tuple(notes), live_requests_made


_PRICES_USD_PER_MILLION = {"gpt-6-luna": (0.10, 0.50)}


def _token_text(result: dict[str, Any]) -> str:
    tokens_in = result.get("input_tokens_total")
    tokens_out = result.get("output_tokens_total")
    if tokens_in is None or tokens_out is None:
        return "not measured"
    return f"{tokens_in}/{tokens_out}"


def _condition_cost_text(result: dict[str, Any], model_ids: Sequence[str]) -> str:
    """Estimate generator cost from tokens using the evaluation price table."""
    tokens_in = result.get("input_tokens_total")
    tokens_out = result.get("output_tokens_total")
    price = next(
        (_PRICES_USD_PER_MILLION[m] for m in model_ids if m in _PRICES_USD_PER_MILLION), None
    )
    if tokens_in is None or tokens_out is None or price is None:
        return "not measured"
    return f"{(tokens_in * price[0] + tokens_out * price[1]) / 1_000_000:.4f}"


def _format_metric(value: object) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _related_review_lines(
    current_run: EvaluationRunRecord,
    *,
    registered_runs: Sequence[EvaluationRunRecord],
    all_reviews: tuple[EvaluationReviewRecord, ...],
    all_errors: tuple[EvaluationErrorRecord, ...],
) -> list[str]:
    review_run_ids = {review.run_id for review in all_reviews}
    related = sorted(
        (
            run
            for run in registered_runs
            if run.run_id != current_run.run_id
            and run.case_set_sha256 == current_run.case_set_sha256
            and run.run_id in review_run_ids
        ),
        key=lambda run: run.started_at,
    )
    if not related:
        return []

    prior = related[-1]
    prior_reviews = tuple(review for review in all_reviews if review.run_id == prior.run_id)
    prior_errors = tuple(error for error in all_errors if error.run_id == prior.run_id)
    prior_records = tuple(CaseMetricRecord.model_validate(item) for item in prior.results)
    prior_metrics = summarize_case_metrics(prior_records, seed=prior.seed or 0)
    review_summary = summarize_output_reviews(prior_reviews)
    error_summary = summarize_errors(prior_errors)
    lines = [
        "",
        "## Related registered run with answer reviews",
        "",
        f"Run `{prior.run_id}` ({prior.started_at.isoformat()}) uses the same case-set hash.",
    ]
    for condition, result in prior_metrics.get("by_condition", {}).items():
        if result.get("scored_count", 0) or result.get("failed_count", 0):
            lines.append(
                f"- `{condition}`: scored={result['scored_count']}, "
                f"failed={result['failed_count']} excluded; expected-behavior "
                f"accuracy={_format_metric(result['expected_behavior_accuracy'])}."
            )
    means = review_summary["mean_scores"]
    lines.append(
        f"- Answer review: {review_summary['review_record_count']} ratings across "
        f"{review_summary['reviewed_case_count']} cases by "
        f"{review_summary['reviewer_count']} reviewer(s); means (1-5): "
        + ", ".join(
            f"{field}={_format_metric(means[field])}"
            for field in (
                "groundedness",
                "answer_relevance",
                "citation_correctness",
                "citation_completeness",
            )
        )
        + "."
    )
    if review_summary["ai_assisted_record_count"]:
        lines.append(
            f"- {review_summary['ai_assisted_record_count']} ratings are identified as "
            "AI-assisted and are not independent human validation."
        )
    if error_summary["error_record_count"]:
        lines.append(
            f"- Linked error analysis: {error_summary['error_record_count']} records, "
            f"{error_summary['occurrence_count']} occurrences."
        )
    return lines


def _write_report(
    path: Path,
    *,
    run_record: EvaluationRunRecord,
    case_set: EvaluationCaseSet,
    metrics: dict[str, Any],
    review_records: tuple[EvaluationReviewRecord, ...],
    error_records: tuple[EvaluationErrorRecord, ...],
    registered_runs: Sequence[EvaluationRunRecord] = (),
    all_reviews: tuple[EvaluationReviewRecord, ...] = (),
    all_errors: tuple[EvaluationErrorRecord, ...] = (),
    case_metadata_updated: bool = False,
) -> None:
    review_coverage = review_category_coverage(case_set, review_records)
    review_agreement_summary = reviewer_agreement(review_records)
    review_summary = summarize_output_reviews(review_records)
    error_summary = summarize_errors(error_records)
    approved_case_count = sum(case.review_status == "approved" for case in case_set.cases)
    case_definition_reviewers = {
        reviewer_id for case in case_set.cases for reviewer_id in case.reviewer_ids
    }
    generation_conditions = {
        condition: result
        for condition, result in metrics.get("by_condition", {}).items()
        if not condition.startswith("retrieval:") and result.get("observed_count", 0)
    }
    lines = [
        "# Feature 007 Evaluation Report",
        "",
        f"Run ID: `{run_record.run_id}`",
        f"Status: `{run_record.status}`",
        f"Started at: `{run_record.started_at.isoformat()}`",
        f"Case set: `{run_record.case_set_id}` (`{run_record.case_set_sha256}`)",
        f"Git revision: `{run_record.code_revision or 'not recorded'}`",
        f"Source tree SHA-256: `{run_record.source_tree_sha256 or 'not recorded'}`",
        "Prompt versions: "
        + (", ".join(f"`{item}`" for item in run_record.prompt_versions) or "not recorded"),
        "Model IDs: " + (", ".join(f"`{item}`" for item in run_record.model_ids) or "not recorded"),
        f"Live requests made: `{str(run_record.live_requests_made).lower()}`",
        "",
        "## Conditions",
        "",
        "| Condition | Results | Outputs scored | Failed excluded | Expected behavior accuracy | "
        "Recall@k | MRR | nDCG@k | Groundedness (AI, 1-5) | Relevance (AI, 1-5) | "
        "Mean latency ms | P95 latency ms | Tokens in/out | Est. cost USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition_id, result in metrics.get("by_condition", {}).items():
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                condition_id,
                result["case_count"],
                result["scored_count"],
                result["failed_count"],
                _format_metric(result["expected_behavior_accuracy"]),
                _format_metric(result["retrieval_recall_at_k_mean"]),
                _format_metric(result["mrr"]),
                _format_metric(result["ndcg_at_k_mean"]),
                _format_metric(result["groundedness_mean"]),
                _format_metric(result["answer_relevance_mean"]),
                _format_metric(result["latency_ms"]["mean"]),
                _format_metric(result["latency_ms"].get("p95")),
                _token_text(result),
                _condition_cost_text(result, run_record.model_ids),
            )
        )
    lines.extend(
        [
            "",
            "Failed generation outputs count as incorrect for expected-behavior accuracy and are "
            "excluded from AI answer-quality scores; retrieval and operational metrics remain "
            "measured.",
        ]
    )
    ai_judge_config = run_record.configuration.get("ai_judge", {})
    ai_judge_config = ai_judge_config if isinstance(ai_judge_config, dict) else {}
    ai_judge_metrics = metrics.get("overall", {}).get("ai_judge", {})
    ai_judge_metrics = ai_judge_metrics if isinstance(ai_judge_metrics, dict) else {}
    lines.extend(["", "## AI quality judging", ""])
    if ai_judge_config.get("enabled") is True:
        judge_models = ai_judge_config.get("model_ids", ())
        if not isinstance(judge_models, (list, tuple)):
            judge_models = ()
        judge_model_text = ", ".join(
            f"`{model_id}`" for model_id in judge_models if isinstance(model_id, str)
        )
        lines.extend(
            [
                f"Rubric: `{ai_judge_config.get('rubric_version', 'unknown')}`",
                f"Scope: `{ai_judge_config.get('scope', 'unknown')}`",
                f"Judge model(s): {judge_model_text or 'not recorded'}",
                f"Scored: {ai_judge_metrics.get('scored_count', 0)} / "
                f"{ai_judge_metrics.get('attempted_count', 0)} attempted; "
                f"failed: {ai_judge_metrics.get('failed_count', 0)}; "
                f"skipped: {ai_judge_metrics.get('skipped_count', 0)}; "
                "ineligible outputs excluded: "
                f"{ai_judge_metrics.get('ineligible_output_count', 0)}",
                (
                    "The judge model ID matched generation for all scored cases."
                    if ai_judge_metrics.get("same_model_as_generator") is True
                    else "At least one judge model ID differed from generation."
                    if ai_judge_metrics.get("same_model_as_generator") is False
                    else "The judge/generator model relationship was not measured."
                ),
                "Groundedness and relevance scores are AI-only, are not human-validated, "
                "and are not release approval. Raw answer text is not stored in run results.",
            ]
        )
    else:
        lines.append("- AI quality judging was not enabled for this run.")
    lines.extend(["", "## Confidence and sample limits", ""])
    for condition_id, result in metrics.get("by_condition", {}).items():
        intervals = result.get("retrieval_bootstrap_95", {})
        parts = [
            f"{name} [{interval['lower_95']:.3f}, {interval['upper_95']:.3f}]"
            for name, interval in intervals.items()
            if interval is not None
        ]
        if parts:
            lines.append(
                f"- `{condition_id}` 95% bootstrap (n={result['case_count']}, "
                f"retrieval metrics, minimum 20 cases): " + "; ".join(parts)
            )
    for condition_id, result in metrics.get("by_condition", {}).items():
        interval = result["latency_ms"]["mean_bootstrap_95"]
        if interval is None:
            lines.append(
                f"- `{condition_id}`: bootstrap interval omitted for fewer than 30 "
                "latency observations."
            )
        else:
            lines.append(
                f"- `{condition_id}`: latency mean 95% bootstrap interval "
                f"[{interval['lower_95']:.3f}, {interval['upper_95']:.3f}] ms "
                f"(n={interval['n']}, resamples={interval['samples']}, seed={interval['seed']})."
            )
    for pair in metrics.get("paired_comparisons", []):
        interval = pair["difference_bootstrap_95"]
        interval_text = (
            f" 95% bootstrap [{interval['lower_95']:+.3f}, {interval['upper_95']:+.3f}]"
            if interval
            else ""
        )
        lines.append(
            f"- Paired `{pair['condition_a']}` vs `{pair['condition_b']}` "
            f"(n={pair['paired_cases']}, failed attempts count as incorrect): accuracy difference "
            f"{pair['accuracy_difference_a_minus_b']:+.3f}{interval_text}; "
            f"discordant {pair['a_only_correct']}/{pair['b_only_correct']}; "
            f"exact McNemar p={pair['mcnemar_exact_p']:.4f}."
        )
    if not metrics.get("by_condition"):
        lines.append("- No condition had measured results; confidence intervals are not available.")
    lines.extend(["", "## Generation behavior by category", ""])
    if generation_conditions:
        for condition in generation_conditions:
            lines.append(f"### `{condition}`")
            lines.extend(
                f"- `{category}`: {result['scored_count']} scored; "
                f"{result['failed_count']} failed excluded; expected-behavior "
                f"accuracy={_format_metric(result['expected_behavior_accuracy'])}."
                for category, result in metrics.get("by_condition_category", {})
                .get(condition, {})
                .items()
                if result.get("observed_count", 0)
            )
    else:
        lines.append("- No generation results were measured.")
    lines.extend(["", "## Generation behavior by split", ""])
    if generation_conditions:
        for condition in generation_conditions:
            lines.append(f"### `{condition}`")
            lines.extend(
                f"- `{split}`: {result['scored_count']} scored; "
                f"{result['failed_count']} failed excluded; expected-behavior "
                f"accuracy={_format_metric(result['expected_behavior_accuracy'])}."
                for split, result in metrics.get("by_condition_split", {})
                .get(condition, {})
                .items()
                if result.get("observed_count", 0)
            )
    else:
        lines.append("- No generation results were measured.")
    lines.extend(
        [
            "",
            "## Evaluation-set review",
            "",
            f"Approved case definitions: {approved_case_count} / {len(case_set.cases)}",
            f"Case-definition reviewers recorded: {len(case_definition_reviewers)}",
            *(
                [
                    "Current case-set hash differs from the run hash; stored case IDs, categories, "
                    "splits, and expected behaviors were checked against this run. The original "
                    "execution hash is retained above."
                ]
                if case_metadata_updated
                else []
            ),
            "",
            "## Answer review for this run",
            "",
            f"Review records: {review_summary['review_record_count']}",
            f"Reviewed answer cases: {review_coverage['reviewed_case_count']} / "
            f"{review_coverage['total_case_count']}",
            f"Reviewers: {review_summary['reviewer_count']}",
            f"AI-assisted review records: {review_summary['ai_assisted_record_count']}",
            f"Cases with multiple reviewers: {review_agreement_summary['reviewed_case_count']}",
            f"Reviewer pairs: {review_agreement_summary['reviewer_pair_count']}",
            "Pairwise exact agreement: "
            f"{_format_metric(review_agreement_summary['exact_agreement'])}",
            "Mean scores (1-5): "
            + ", ".join(
                f"{field}={_format_metric(review_summary['mean_scores'][field])}"
                for field in (
                    "groundedness",
                    "answer_relevance",
                    "citation_correctness",
                    "citation_completeness",
                )
            ),
            "Expected-behavior rating accuracy: "
            f"{_format_metric(review_summary['expected_behavior_accuracy'])}",
            "Safety-compliance rating rate: "
            f"{_format_metric(review_summary['safety_compliance_rate'])}",
            "",
            "## Error analysis",
            "",
            f"Error records: {error_summary['error_record_count']}",
            f"Observed error occurrences: {error_summary['occurrence_count']}",
            f"By failure layer: `{error_summary['by_failure_layer']}`",
            f"By severity: `{error_summary['by_severity']}`",
        ]
    )
    lines.extend(
        _related_review_lines(
            run_record,
            registered_runs=registered_runs,
            all_reviews=all_reviews,
            all_errors=all_errors,
        )
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(
        f"- {limitation}"
        for limitation in metrics.get("limitations", ())
        if isinstance(limitation, str)
    )
    corrected_legacy_note = False
    for note in run_record.notes:
        if (
            generation_conditions
            and note
            == "This run measures retrieval only; generation/provider comparison was skipped."
        ):
            corrected_legacy_note = True
            continue
        lines.append(f"- {note}")
    if corrected_legacy_note:
        lines.append(
            "- A legacy run note incorrectly said generation was skipped; registered results "
            "contain generation conditions, which are reported above."
        )
    if not run_record.results:
        lines.append("- No case metrics were measured in this run.")
    if not generation_conditions:
        lines.append("- Generation/provider comparison was not measured in this run.")
    else:
        lines.append(
            "- Expected-behavior accuracy measures response type, not semantic grounding or "
            "answer relevance."
        )
    if not review_records:
        lines.append("- No answer-level reviews are linked to this run.")
    if review_summary["ai_assisted_record_count"]:
        lines.append("- AI-assisted review scores are not independent human validation.")
    if metrics.get("overall", {}).get("estimated_cost_usd_total") is None:
        if any(
            _condition_cost_text(
                metrics.get("by_condition", {}).get(condition, {}), run_record.model_ids
            )
            != "not measured"
            for condition in generation_conditions
        ):
            lines.append(
                "- Per-condition token-based costs are estimates; an aggregate cost is unavailable "
                "because usage data is incomplete."
            )
        else:
            lines.append("- Cost was not measured or estimated for this run.")
    if metrics.get("overall", {}).get("ndcg_measured_count", 0) == 0:
        lines.append("- nDCG is not measured because no graded relevance labels were available.")
    lines.append("- Candidate or unreviewed labels are never used as release ground truth.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temp_path = Path(handle.name)
            handle.write("\n".join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def run_suite(
    *,
    cases_path: Path = DEFAULT_CASES,
    project_root: Path = PROJECT_ROOT,
    manifest_path: Path = DEFAULT_RUN_MANIFEST,
    report_path: Path = DEFAULT_REPORT,
    review_manifest_path: Path | None = None,
    error_manifest_path: Path | None = None,
    split: SplitSelector = "test",
    run_retrieval: bool = False,
    use_reranker: bool = False,
    run_generation: bool = False,
    ai_judge: bool = False,
    providers: tuple[Literal["openai", "mlx"], ...] = ("openai", "mlx"),
    allow_openai_live: bool = False,
    allow_mlx: bool = False,
    allow_mcp_tools: bool = False,
    seed: int = 0,
    release: bool = False,
    case_ids: tuple[str, ...] = (),
    embedder_factory: EmbedderFactory = create_embedding_provider,
    retrieval_evaluator: RetrievalEvaluator = evaluate_retrieval,
    anchor_validator: AnchorValidator = validate_case_anchors,
    generation_executor: GenerationExecutor = _execute_generation,
) -> tuple[EvaluationRunRecord, dict[str, Any]]:
    started_at = datetime.now(UTC)
    case_set = EvaluationCaseSet.load(cases_path)
    anchor_issues = anchor_validator(case_set, project_root=project_root)
    release_issues = release_gate_issues(case_set)
    selected_cases = tuple(
        case
        for case in case_set.cases
        if case.review_status == "approved"
        and (split == "all" or case.split == split)
        and (not case_ids or case.case_id in case_ids)
    )
    notes: list[str] = []
    records: tuple[CaseMetricRecord, ...] = ()
    config: dict[str, Any] = {
        "split": split,
        "requested_retrieval": run_retrieval,
        "requested_generation": run_generation,
        "ai_judge": (
            {
                "enabled": True,
                "scope": "agent",
                "rubric_version": AI_JUDGE_RUBRIC_VERSION,
            }
            if ai_judge
            else {"enabled": False}
        ),
        "requested_providers": list(providers) if run_generation else [],
        "mcp_tools_allowed": allow_mcp_tools,
        "seed": seed,
        "provider_runs": "requested" if run_generation else "not_requested",
    }
    status: Literal["completed", "partial", "blocked", "failed"] = "blocked"
    live_requests_made = False
    if anchor_issues:
        notes.extend(anchor_issues)
    if release and release_issues:
        notes.extend(release_issues)
    if not selected_cases:
        notes.append("No approved cases are available for the selected split.")

    metrics: dict[str, Any] = summarize_case_metrics((), seed=seed)
    if not anchor_issues and selected_cases and (not release or not release_issues):
        if run_retrieval:
            settings = RetrievalSettings(embedding_provider="local", reranker_enabled=use_reranker)
            embedder = embedder_factory(settings)
            retrieval_cases = to_retrieval_case_set(
                selected_cases,
                set_id=case_set.set_id,
                lineage=case_set.lineage,
            )
            retrieval_result = retrieval_evaluator(
                project_root,
                settings,
                embedder,
                retrieval_cases,
                **({"reranker": create_reranker(settings)} if use_reranker else {}),
            )
            records = _retrieval_records(
                case_set,
                retrieval_result,
                split=split if split != "all" else None,
                top_k=settings.final_context_chunks,
            )
            config["embedding"] = embedder.descriptor.model_dump(mode="json")
            config["retrieval"] = {
                "modes": [*_RETRIEVAL_MODES, *([_RERANKED_MODE] if use_reranker else [])],
                "reranker": retrieval_result.get("reranker"),
                "chunkers": [item.get("chunker") for item in retrieval_result["configurations"]],
                "top_k": settings.final_context_chunks,
            }
            expected_retrieval_rows = (
                sum(bool(case.expected_anchors) for case in selected_cases)
                * len(retrieval_result.get("configurations", ()))
                * (len(_RETRIEVAL_MODES) + int(use_reranker))
            )
            status = "completed" if len(records) == expected_retrieval_rows else "partial"
            if not run_generation:
                notes.append(
                    "This run measures retrieval only; generation/provider comparison was skipped."
                )
        else:
            status = "blocked"
            notes.append("No execution mode selected; use --run-retrieval after case approval.")
        metrics = summarize_case_metrics(records, seed=seed)
    elif not anchor_issues and not release_issues and selected_cases:
        status = "blocked"
        notes.append("The release case gate passed, but no evaluation execution mode was selected.")

    if (
        not anchor_issues
        and selected_cases
        and (not release or not release_issues)
        and run_generation
    ):
        authorized_providers = tuple(
            provider
            for provider in providers
            if (provider == "openai" and allow_openai_live) or (provider == "mlx" and allow_mlx)
        )
        for provider in providers:
            if provider not in authorized_providers:
                opt_in = "--allow-openai-live" if provider == "openai" else "--run-mlx"
                notes.append(f"{provider} cases skipped; pass {opt_in} to authorize this route.")
        if authorized_providers:
            generation_records, generation_notes, live_requests_made = generation_executor(
                selected_cases,
                providers=authorized_providers,
                allow_openai_live=allow_openai_live,
                allow_mlx=allow_mlx,
                allow_mcp_tools=allow_mcp_tools,
                ai_judge=ai_judge,
                project_root=project_root,
            )
            records = (*records, *generation_records)
            notes.extend(generation_notes)
            if ai_judge:
                judge_configuration = config["ai_judge"]
                if isinstance(judge_configuration, dict):
                    judge_configuration["model_ids"] = sorted(
                        {
                            record.judge_model_id
                            for record in generation_records
                            if record.judge_model_id is not None
                        }
                    )
            if generation_records:
                eligible_cases = sum(
                    allow_mcp_tools or not case.required_tools for case in selected_cases
                )
                expected_generation_rows = eligible_cases * len(authorized_providers) * 2
                generation_complete = len(generation_records) == expected_generation_rows
                providers_complete = len(authorized_providers) == len(providers)
                if status != "partial" and generation_complete and providers_complete:
                    status = "completed"
                else:
                    status = "partial"
            elif not run_retrieval:
                status = "blocked"
                notes.append("No configured provider completed a generation case.")
            else:
                status = "partial"
        elif not run_retrieval:
            status = "blocked"
            notes.append("Generation was requested, but no provider opt-in was supplied.")
        metrics = summarize_case_metrics(records, seed=seed)

    finished_at = datetime.now(UTC)
    run_record = build_run_record(
        case_set=case_set,
        case_set_path=cases_path,
        project_root=project_root,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        configuration=config,
        index_versions=tuple(
            sorted({record.index_version for record in records if record.index_version})
        ),
        prompt_versions=tuple(
            sorted({record.prompt_version for record in records if record.prompt_version})
        ),
        model_ids=tuple(
            sorted(
                {
                    model_id
                    for record in records
                    for model_id in (record.model_id, record.judge_model_id)
                    if model_id
                }
            )
        ),
        seed=seed,
        metrics=metrics,
        results=tuple(record.model_dump(mode="json") for record in records),
        artifact_paths=(str(report_path.relative_to(project_root)),),
        notes=tuple(notes),
        live_requests_made=live_requests_made,
    )
    append_run_record(run_record, manifest_path=manifest_path)
    registered_runs = _load_registered_runs(manifest_path)
    all_reviews = load_review_records(
        review_manifest_path or project_root / "data/manifests/evaluation-review-manifest.json"
    )
    all_errors = load_error_records(
        error_manifest_path or project_root / "data/manifests/evaluation-error-manifest.json"
    )
    run_reviews = tuple(review for review in all_reviews if review.run_id == run_record.run_id)
    run_errors = tuple(error for error in all_errors if error.run_id == run_record.run_id)
    _write_report(
        report_path,
        run_record=run_record,
        case_set=case_set,
        metrics=metrics,
        review_records=run_reviews,
        error_records=run_errors,
        registered_runs=registered_runs,
        all_reviews=all_reviews,
        all_errors=all_errors,
    )
    return run_record, metrics


def _load_registered_runs(manifest_path: Path) -> tuple[EvaluationRunRecord, ...]:
    if not manifest_path.exists():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationSuiteError("Evaluation run manifest is invalid JSON") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or not isinstance(manifest.get("runs"), list)
    ):
        raise EvaluationSuiteError("Evaluation run manifest has an invalid shape")
    try:
        records = tuple(EvaluationRunRecord.model_validate(item) for item in manifest["runs"])
    except ValueError as error:
        raise EvaluationSuiteError("Evaluation run manifest contains an invalid run") from error
    run_ids = [record.run_id for record in records]
    if len(run_ids) != len(set(run_ids)):
        raise EvaluationSuiteError("Evaluation run manifest contains duplicate run IDs")
    return records


def render_registered_run_report(
    run_id: UUID,
    *,
    cases_path: Path = DEFAULT_CASES,
    project_root: Path = PROJECT_ROOT,
    manifest_path: Path = DEFAULT_RUN_MANIFEST,
    report_path: Path = DEFAULT_REPORT,
    review_manifest_path: Path | None = None,
    error_manifest_path: Path | None = None,
    allow_case_metadata_update: bool = False,
) -> tuple[EvaluationRunRecord, dict[str, Any]]:
    case_set = EvaluationCaseSet.load(cases_path)
    registered_runs = _load_registered_runs(manifest_path)
    matching_runs = tuple(record for record in registered_runs if record.run_id == run_id)
    if len(matching_runs) != 1:
        raise EvaluationSuiteError("Requested evaluation run was not found exactly once")
    run_record = matching_runs[0]
    case_hash_matches = sha256_file(cases_path) == run_record.case_set_sha256

    try:
        results = tuple(CaseMetricRecord.model_validate(item) for item in run_record.results)
    except ValueError as error:
        raise EvaluationSuiteError("Registered run contains an invalid case result") from error
    cases_by_id = {case.case_id: case for case in case_set.cases}
    identities_match = bool(results) and all(
        (case := cases_by_id.get(result.case_id)) is not None
        and case.category == result.category
        and case.split == result.split
        and case.expected_behavior == result.expected_behavior
        for result in results
    )
    if not case_hash_matches and (not allow_case_metadata_update or not identities_match):
        raise EvaluationSuiteError(
            "Current evaluation case set does not match the selected run's recorded hash; "
            "metadata-update rendering requires an explicit flag and matching recorded labels"
        )
    metrics = summarize_case_metrics(results, seed=run_record.seed or 0)
    all_reviews = load_review_records(
        review_manifest_path or project_root / "data/manifests/evaluation-review-manifest.json"
    )
    all_errors = load_error_records(
        error_manifest_path or project_root / "data/manifests/evaluation-error-manifest.json"
    )
    run_reviews = tuple(review for review in all_reviews if review.run_id == run_id)
    run_errors = tuple(error for error in all_errors if error.run_id == run_id)
    _write_report(
        report_path,
        run_record=run_record,
        case_set=case_set,
        metrics=metrics,
        review_records=run_reviews,
        error_records=run_errors,
        registered_runs=registered_runs,
        all_reviews=all_reviews,
        all_errors=all_errors,
        case_metadata_updated=not case_hash_matches,
    )
    return run_record, metrics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run reproducible PolicyLens Feature 007 evaluation."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--review-manifest", type=Path)
    parser.add_argument("--error-manifest", type=Path)
    parser.add_argument("--split", choices=("all", "dev", "test"), default="test")
    parser.add_argument("--render-run-id", type=UUID)
    parser.add_argument("--allow-case-metadata-update", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--run-retrieval", action="store_true")
    parser.add_argument("--run-generation", action="store_true")
    parser.add_argument(
        "--reranker",
        action="store_true",
        help="Also evaluate hybrid retrieval with the local cross-encoder reranker.",
    )
    parser.add_argument(
        "--ai-judge",
        action="store_true",
        help="AI-score groundedness and answer relevance for generated agent answers.",
    )
    parser.add_argument("--provider", action="append", choices=("openai", "mlx"))
    parser.add_argument("--allow-openai-live", action="store_true")
    parser.add_argument("--run-mlx", action="store_true")
    parser.add_argument("--allow-mcp-tools", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args(argv)

    if arguments.allow_case_metadata_update and arguments.render_run_id is None:
        parser.error("--allow-case-metadata-update requires --render-run-id")

    if arguments.render_run_id is not None:
        if (
            arguments.validate_only
            or arguments.run_retrieval
            or arguments.run_generation
            or arguments.allow_openai_live
            or arguments.run_mlx
            or arguments.allow_mcp_tools
            or arguments.ai_judge
            or arguments.release
            or arguments.provider is not None
        ):
            parser.error("--render-run-id cannot be combined with evaluation execution options")
        try:
            record, metrics = render_registered_run_report(
                arguments.render_run_id,
                cases_path=arguments.cases,
                manifest_path=arguments.manifest,
                report_path=arguments.report,
                review_manifest_path=arguments.review_manifest,
                error_manifest_path=arguments.error_manifest,
                allow_case_metadata_update=arguments.allow_case_metadata_update,
            )
        except EvaluationSuiteError as error:
            parser.error(str(error))
        print(
            json.dumps(
                {
                    "status": record.status,
                    "run_id": str(record.run_id),
                    "report": str(arguments.report),
                    "metric_case_count": metrics["case_count"],
                    "live_requests_made": record.live_requests_made,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.validate_only:
        try:
            case_set = EvaluationCaseSet.load(arguments.cases)
            anchor_issues = validate_case_anchors(case_set)
        except Exception:
            print(json.dumps({"status": "invalid", "case_set": str(arguments.cases)}))
            return 2
        release_issues = release_gate_issues(case_set)
        report = {
            "status": "blocked" if anchor_issues else "valid",
            "case_set_id": case_set.set_id,
            "case_count": len(case_set.cases),
            "anchor_issues": anchor_issues,
            "release_gate_issues": release_issues,
            "release_eligible": not release_issues,
            "live_requests_made": False,
        }
        print(json.dumps(report, sort_keys=True))
        return 1 if anchor_issues or (arguments.release and release_issues) else 0
    if (
        arguments.allow_openai_live or arguments.run_mlx or arguments.allow_mcp_tools
    ) and not arguments.run_generation:
        parser.error("provider opt-in flags require --run-generation")
    if arguments.ai_judge and not arguments.run_generation:
        parser.error("--ai-judge requires --run-generation")

    record, metrics = run_suite(
        cases_path=arguments.cases,
        manifest_path=arguments.manifest,
        report_path=arguments.report,
        review_manifest_path=arguments.review_manifest,
        error_manifest_path=arguments.error_manifest,
        split=arguments.split,
        run_retrieval=arguments.run_retrieval,
        use_reranker=arguments.reranker,
        run_generation=arguments.run_generation,
        ai_judge=arguments.ai_judge,
        providers=tuple(arguments.provider or ("openai", "mlx")),
        allow_openai_live=arguments.allow_openai_live,
        allow_mlx=arguments.run_mlx,
        allow_mcp_tools=arguments.allow_mcp_tools,
        seed=arguments.seed,
        release=arguments.release,
        case_ids=tuple(arguments.case_id),
    )
    print(
        json.dumps(
            {
                "status": record.status,
                "run_id": str(record.run_id),
                "case_set_id": record.case_set_id,
                "case_count": len(record.results),
                "metric_case_count": metrics.get("case_count", 0),
                "live_requests_made": record.live_requests_made,
            },
            sort_keys=True,
        )
    )
    return 1 if record.status in {"blocked", "failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
