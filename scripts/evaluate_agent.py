from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal
from uuid import uuid4

from pydantic import Field

from policylens.agent_runtime.models import AgentAnswerRequest, AgentStatus, StrictModel
from policylens.retrieval.models import RetrievalFilters
from policylens.settings import PROJECT_ROOT, AppSettings

DEFAULT_CASES = PROJECT_ROOT / "data/evaluation/agent-tool-cases.json"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/manifests/agent-evaluation-manifest.json"
DEFAULT_REPORT = PROJECT_ROOT / "docs/evaluation/agent-evaluation.md"


class AgentEvaluationCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["bm25", "dense", "hybrid"]
    top_k: int = Field(ge=1, le=20)
    filters: dict[str, object]
    requires_tool: bool
    expected_status: AgentStatus
    expected_calculation: Literal["none", "mean", "sum", "median"] | None = None
    adversarial_fixture: str | None = Field(default=None, max_length=1000)

    def to_request(self) -> AgentAnswerRequest:
        return AgentAnswerRequest(
            query=self.query,
            mode=self.mode,
            top_k=self.top_k,
            filters=RetrievalFilters.model_validate(self.filters),
        )


class AgentEvaluationCaseSet(StrictModel):
    schema_version: Literal["1.0"]
    case_set_id: str = Field(min_length=1, max_length=100)
    lineage: str = Field(min_length=1, max_length=1000)
    runtime_label_access: Literal["prohibited"]
    cases: tuple[AgentEvaluationCase, ...] = Field(min_length=1, max_length=100)

    @classmethod
    def load(cls, path: Path) -> AgentEvaluationCaseSet:
        case_set = cls.model_validate_json(path.read_text(encoding="utf-8"))
        case_ids = [case.case_id for case in case_set.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("agent evaluation case IDs must be unique")
        return case_set


class EvaluationObservation(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    status: AgentStatus
    tool_calls: int = Field(ge=0, le=20)
    schema_valid: bool
    latency_ms: float = Field(ge=0)


class AgentComparisonSummary(StrictModel):
    case_set_id: str
    case_count: int = Field(ge=1)
    agent_expected_status_rate: float = Field(ge=0, le=1)
    baseline_expected_status_rate: float = Field(ge=0, le=1)
    agent_tool_compliance_rate: float = Field(ge=0, le=1)
    agent_schema_valid_rate: float = Field(ge=0, le=1)
    agent_mean_latency_ms: float = Field(ge=0)
    baseline_mean_latency_ms: float = Field(ge=0)
    answer_quality_value: Literal["not_measured"] = "not_measured"


def compare_observations(
    case_set: AgentEvaluationCaseSet,
    agent_observations: tuple[EvaluationObservation, ...],
    baseline_observations: tuple[EvaluationObservation, ...],
) -> AgentComparisonSummary:
    cases_by_id = {case.case_id: case for case in case_set.cases}
    agent_by_id = {item.case_id: item for item in agent_observations}
    baseline_by_id = {item.case_id: item for item in baseline_observations}
    expected_ids = set(cases_by_id)
    if set(agent_by_id) != expected_ids or set(baseline_by_id) != expected_ids:
        raise ValueError("agent and baseline observations must cover the same frozen case IDs")

    agent_status_matches = sum(
        agent_by_id[case_id].status == case.expected_status for case_id, case in cases_by_id.items()
    )
    baseline_status_matches = sum(
        baseline_by_id[case_id].status == case.expected_status
        for case_id, case in cases_by_id.items()
    )
    tool_cases = [case for case in case_set.cases if case.requires_tool]
    tool_compliance = sum(agent_by_id[case.case_id].tool_calls > 0 for case in tool_cases)
    latency_count = len(cases_by_id)

    return AgentComparisonSummary(
        case_set_id=case_set.case_set_id,
        case_count=latency_count,
        agent_expected_status_rate=agent_status_matches / latency_count,
        baseline_expected_status_rate=baseline_status_matches / latency_count,
        agent_tool_compliance_rate=tool_compliance / max(1, len(tool_cases)),
        agent_schema_valid_rate=sum(item.schema_valid for item in agent_by_id.values())
        / latency_count,
        agent_mean_latency_ms=sum(item.latency_ms for item in agent_by_id.values()) / latency_count,
        baseline_mean_latency_ms=sum(item.latency_ms for item in baseline_by_id.values())
        / latency_count,
    )


def _live_blocker(settings: AppSettings | None) -> tuple[str, str]:
    if settings is None:
        try:
            settings = AppSettings()
        except Exception:
            return "OPENAI_CONFIGURATION_UNAVAILABLE", "OpenAI configuration is unavailable."
    if settings.model_provider != "openai":
        return (
            "MODEL_PROVIDER_NOT_OPENAI",
            "Set MODEL_PROVIDER=openai explicitly for live comparison.",
        )
    if settings.openai_deployment_model and settings.openai_base_url is None:
        return "OPENAI_BASE_URL_REQUIRED", "Foundry deployment requires OPENAI_BASE_URL."
    return (
        "FEATURE_004_COMPARISON_NOT_IMPLEMENTED",
        "This readiness-only command does not execute agent or baseline runs; "
        "use the Feature 007 evaluation suite for an explicitly authorized comparison.",
    )


def _write_report(path: Path, record: dict[str, object], case_set: AgentEvaluationCaseSet) -> None:
    status = str(record["status"])
    reason = str(record["reason"])
    lines = [
        "# Feature 004 Agent Evaluation",
        "",
        f"Status: `{status}`",
        (
            f"Case set: `{case_set.case_set_id}` "
            f"({len(case_set.cases)} author-curated engineering cases)"
        ),
        f"Run ID: `{record['run_id']}`",
        f"Reason: {reason}",
        "",
        "No live OpenAI/Foundry request was made by this evaluation command.",
        "The case set is not independent human review and does not measure answer quality or "
        "establish agent value.",
        "The agent-versus-baseline comparison remains a release gate; an unrun or blocked "
        "comparison is not a success result.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write("\n".join(lines))
        temporary = Path(handle.name)
    temporary.replace(path)


def run_evaluation(
    *,
    project_root: Path = PROJECT_ROOT,
    cases_path: Path | None = None,
    live: bool = False,
    settings: AppSettings | None = None,
) -> dict[str, object]:
    root = project_root.resolve()
    resolved_cases = cases_path or root / "data/evaluation/agent-tool-cases.json"
    case_set = AgentEvaluationCaseSet.load(resolved_cases)
    reason_code, reason = (
        ("LIVE_COMPARISON_NOT_REQUESTED", "Live comparison was not requested.")
        if not live
        else _live_blocker(settings)
    )
    record: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "case_set_id": case_set.case_set_id,
        "case_set_sha256": hashlib.sha256(resolved_cases.read_bytes()).hexdigest(),
        "case_count": len(case_set.cases),
        "status": "blocked" if live else "not_run",
        "reason_code": reason_code,
        "reason": reason,
        "live_request_made": False,
        "metrics": None,
    }
    manifest_path = root / "data/manifests/agent-evaluation-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("runs"), list):
            raise ValueError("agent evaluation manifest is invalid")
    else:
        manifest = {"schema_version": "1.0", "runs": []}
    manifest["runs"].append(record)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=manifest_path.parent, delete=False
    ) as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary_manifest = Path(handle.name)
    temporary_manifest.replace(manifest_path)
    _write_report(root / "docs/evaluation/agent-evaluation.md", record, case_set)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Feature 004 evaluation readiness.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Check if a live comparison can run; never sends requests.",
    )
    arguments = parser.parse_args()
    record = run_evaluation(live=arguments.live)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
