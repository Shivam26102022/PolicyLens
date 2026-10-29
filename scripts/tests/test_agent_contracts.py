from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from policylens.agent_runtime.models import (
    AgentEvent,
    AgentModelUsage,
    AgentRunState,
    ModelCapabilities,
    ModelCapabilitySet,
    ModelLimits,
    ModelRunMetadata,
)
from policylens.retrieval.generation import BaselineAnswerResponse, BaselineGenerationMetadata
from policylens.retrieval.models import (
    BlockLocation,
    RetrievalRerankingDiagnostics,
    RetrievalRun,
    RetrievedEvidence,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "specs/004-agent-runtime/contracts"
FEATURE_003_CONTRACT_DIR = ROOT / "specs/003-retrieval-and-citations/contracts"
FEATURE_006_CONTRACT_DIR = ROOT / "specs/006-model-routing/contracts"


def _registry_and_schema() -> tuple[Registry[Any], dict[str, Any]]:
    paths = [
        CONTRACT_DIR / "agent-api.schema.json",
        FEATURE_003_CONTRACT_DIR / "citation.schema.json",
        FEATURE_003_CONTRACT_DIR / "retrieval-api.schema.json",
        FEATURE_006_CONTRACT_DIR / "model-run-metadata.schema.json",
        FEATURE_006_CONTRACT_DIR / "model-capabilities.schema.json",
    ]
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    registry: Registry[Any] = Registry()
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry, schemas[0]


def test_agent_contracts_resolve_feature003_references_and_valid_instances() -> None:
    registry, schema = _registry_and_schema()
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )
    passage_id = "sha256:" + "b" * 64
    citation = {
        "claim_id": "claim-1",
        "source_id": "source-1",
        "title": "Source title",
        "source_uri": "https://example.test/source",
        "passage_id": passage_id,
        "page_start": 1,
        "page_end": 1,
        "section_path": ["Section"],
        "row_key": None,
        "excerpt": "Exact supporting excerpt",
        "source_content_sha256": "a" * 64,
        "retrieval_rank": 1,
        "retrieval_score": 0.5,
        "retrieval_mode": "hybrid",
    }
    request = {
        "schema_version": "1.0",
        "query": "question",
        "mode": "hybrid",
        "top_k": 5,
        "filters": {},
    }
    draft = {
        "status": "answered",
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "Exact supporting excerpt",
                "evidence": [{"passage_id": passage_id, "excerpt": "Exact supporting excerpt"}],
                "calculation_ids": [],
            }
        ],
        "clarification_question": None,
        "abstention_reason": None,
        "conflicts": [],
        "uncertainty": [],
        "limitations": [],
    }
    response = {
        "schema_version": "1.0",
        "run_id": str(UUID("9a734d29-8d52-4afe-97f6-14963f251f1b")),
        "trace_id": str(UUID("7c03f0e0-9921-4b54-bb6b-4f048ad788cb")),
        "index_version": "c" * 64,
        "status": "answered",
        "answer": "Exact supporting excerpt",
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "Exact supporting excerpt",
                "citations": [citation],
                "calculation_ids": [],
            }
        ],
        "calculations": [],
        "uncertainty": [],
        "conflicts": [],
        "clarification_question": None,
        "limitations": [],
        "provider": "openai",
        "model": "gpt-6-luna",
        "session_context": None,
        "model_metadata": ModelRunMetadata(
            provider="openai",
            model_id="gpt-6-luna",
            prompt_version="agent-v2",
            latency_ms=42,
            usage=AgentModelUsage(
                requests=2,
                prompt_tokens=120,
                completion_tokens=30,
                total_tokens=150,
                cached_input_tokens=4,
                reasoning_tokens=10,
            ),
            capabilities=ModelCapabilities(
                provider="openai",
                model_id="gpt-6-luna",
                route="openai_responses",
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
                    max_output_tokens=1200,
                    timeout_seconds=90,
                ),
                platform="Linux test",
            ),
            reasoning_effort="low",
            reasoning_summary="Compared the available evidence.",
        ).model_dump(mode="json"),
        "prompt_version": "agent-v2",
        "events": [
            AgentEvent(
                sequence=1,
                state=AgentRunState.ASSESSING,
                event_type="model_completed",
                status="succeeded",
                model_route="openai_responses",
                reasoning_effort="low",
                model_usage=AgentModelUsage(
                    requests=1,
                    prompt_tokens=120,
                    completion_tokens=30,
                    total_tokens=150,
                    cached_input_tokens=4,
                    reasoning_tokens=10,
                ),
                reasoning_summary="Compared the available evidence.",
            ).model_dump(mode="json"),
            AgentEvent(
                sequence=2,
                state=AgentRunState.RETRIEVING,
                event_type="reranking_completed",
                status="succeeded",
                item_count=12,
                reranker_model="jinaai/jina-reranker-v1-tiny-en",
            ).model_dump(mode="json"),
        ],
        "error_code": None,
    }

    for instance in (request, draft, response):
        validator.validate(instance)


def test_agent_contract_rejects_unsafe_or_unbounded_tool_capabilities() -> None:
    registry, schema = _registry_and_schema()
    validator = Draft202012Validator(schema, registry=registry)
    request = {
        "schema_version": "1.0",
        "query": "question",
        "mode": "hybrid",
        "tool": "shell",
    }

    assert not validator.is_valid(request)


def test_retrieval_contract_accepts_reranked_evidence_and_diagnostics() -> None:
    registry, _agent_schema = _registry_and_schema()
    schema = json.loads(
        (FEATURE_003_CONTRACT_DIR / "retrieval-api.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )
    text = "Relevant policy evidence."
    run = RetrievalRun(
        index_version="c" * 64,
        status="found",
        context=text,
        evidence=(
            RetrievedEvidence(
                passage_id="sha256:" + "b" * 64,
                source_id="source-1",
                title="Source title",
                publisher="Publisher",
                source_uri="https://example.test/source",
                text=text,
                source_content_sha256="a" * 64,
                locations=(
                    BlockLocation(
                        page_number=1,
                        block_id="block-1",
                        start_char=0,
                        end_char=len(text),
                    ),
                ),
                section_path=("Section",),
                rank=1,
                score=0.9,
                bm25_rank=1,
                dense_rank=2,
                bm25_score=2.3,
                dense_score=0.7,
                reranker_score=0.9,
                retrieval_mode="hybrid",
                licence="CC BY 4.0",
            ),
        ),
        reranking=RetrievalRerankingDiagnostics(
            status="completed",
            model_id="jinaai/jina-reranker-v1-tiny-en",
            candidate_count=12,
            duration_ms=31.5,
        ),
    )
    validator.validate(run.model_dump(mode="json"))


def test_baseline_contract_accepts_openai_and_mlx_generation_metadata() -> None:
    registry, _agent_schema = _registry_and_schema()
    schema_path = ROOT / "specs/003-retrieval-and-citations/contracts/baseline-answer.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )

    for provider in ("openai", "mlx"):
        response = BaselineAnswerResponse(
            status="abstained",
            run_id=UUID("9a734d29-8d52-4afe-97f6-14963f251f1b"),
            index_version="c" * 64,
            claims=(),
            error_code="MODEL_ABSTAINED",
            generation=BaselineGenerationMetadata(
                provider=provider,
                model_id=f"{provider}-test-model",
            ),
        )
        validator.validate(response.model_dump(mode="json"))


def test_mlx_action_statistics_contract_matches_mcp_request_bounds() -> None:
    schema_path = FEATURE_006_CONTRACT_DIR / "mlx-action.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema["$defs"]["StatisticsQuery"])

    valid_request = {
        "indicator": "SL.UEM.1524.ZS",
        "geographies": ["IND", "SGP"],
        "start_year": 2020,
        "end_year": 2025,
        "aggregation": "none",
        "group_by": [],
        "row_limit": 44,
    }
    validator.validate(valid_request)

    invalid_requests = (
        valid_request | {"geographies": ["IND", "SGP", "MYS", "IDN", "THA"]},
        valid_request | {"start_year": 2014},
        valid_request | {"row_limit": 45},
        valid_request | {"geographies": ["IND", "IND"]},
        valid_request | {"group_by": ["year"]},
    )
    assert all(not validator.is_valid(request) for request in invalid_requests)
