from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from policylens.agent_runtime.models import StrictModel
from policylens.settings import PROJECT_ROOT
from scripts.evaluation_registry import EvaluationRegistryError, append_manifest_record

ExpectedBehavior = Literal["answer", "clarify", "abstain", "conflict", "block"]
FailureLayer = Literal[
    "data",
    "parsing",
    "retrieval",
    "context",
    "generation",
    "tool_selection",
    "tool_execution",
    "mcp",
    "validation",
    "policy",
    "ui",
]
ErrorSeverity = Literal["critical", "high", "medium", "low"]

DEFAULT_ERROR_MANIFEST = PROJECT_ROOT / "data/manifests/evaluation-error-manifest.json"
DEFAULT_ERROR_REPORT = PROJECT_ROOT / "docs/evaluation/evaluation-errors.md"
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b[\w.-]*(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*"
        r"[\"']?[^\s,;\"']+"
    ),
    re.compile(r"https?://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
)


class EvaluationErrorStoreError(ValueError):
    """The error-analysis manifest is invalid or unsafe to update."""


def redact_error_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


class EvaluationErrorRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    error_id: str = Field(min_length=1, max_length=100)
    run_id: UUID
    case_id: str = Field(min_length=1, max_length=100)
    expected_behavior: ExpectedBehavior
    observed_outcome: str = Field(min_length=1, max_length=2000)
    failure_layer: FailureLayer
    trace_id: UUID | None = None
    severity: ErrorSeverity
    frequency: int = Field(ge=1)
    root_cause_hypothesis: str = Field(min_length=1, max_length=2000)
    supporting_trace_evidence: tuple[str, ...] = Field(default=(), max_length=20)
    proposed_intervention: str = Field(min_length=1, max_length=2000)
    predicted_metric_impact: str = Field(min_length=1, max_length=1000)
    regression_test: str = Field(min_length=1, max_length=500)

    @field_validator(
        "observed_outcome",
        "root_cause_hypothesis",
        "proposed_intervention",
        "predicted_metric_impact",
        "regression_test",
        mode="before",
    )
    @classmethod
    def redact_text_fields(cls, value: object) -> object:
        return redact_error_text(value) if isinstance(value, str) else value

    @field_validator("supporting_trace_evidence", mode="before")
    @classmethod
    def redact_evidence(cls, value: object) -> object:
        if isinstance(value, (tuple, list)):
            return tuple(
                redact_error_text(item) if isinstance(item, str) else item for item in value
            )
        return value


def append_error_record(
    record: EvaluationErrorRecord,
    *,
    manifest_path: Path = DEFAULT_ERROR_MANIFEST,
) -> None:
    try:
        append_manifest_record(
            record.model_dump(mode="json"),
            manifest_path=manifest_path,
            collection="errors",
            record_validator=EvaluationErrorRecord.model_validate,
        )
    except EvaluationRegistryError as error:
        raise EvaluationErrorStoreError("Evaluation error manifest is invalid") from error


def load_error_records(
    manifest_path: Path = DEFAULT_ERROR_MANIFEST,
) -> tuple[EvaluationErrorRecord, ...]:
    if not manifest_path.exists():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationErrorStoreError("Evaluation error manifest is invalid JSON") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or not isinstance(manifest.get("errors"), list)
    ):
        raise EvaluationErrorStoreError("Evaluation error manifest has an invalid shape")
    try:
        return tuple(EvaluationErrorRecord.model_validate(item) for item in manifest["errors"])
    except ValueError as error:
        raise EvaluationErrorStoreError("Evaluation error record is invalid") from error


def summarize_errors(records: tuple[EvaluationErrorRecord, ...]) -> dict[str, Any]:
    by_layer: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_case: Counter[str] = Counter()
    for record in records:
        by_layer[record.failure_layer] += record.frequency
        by_severity[record.severity] += record.frequency
        by_case[record.case_id] += record.frequency
    return {
        "error_record_count": len(records),
        "occurrence_count": sum(record.frequency for record in records),
        "by_failure_layer": dict(sorted(by_layer.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "by_case": dict(sorted(by_case.items())),
    }


def render_error_report(records: tuple[EvaluationErrorRecord, ...]) -> str:
    summary = summarize_errors(records)
    lines = [
        "# Feature 007 Error Analysis",
        "",
        f"Error records: {summary['error_record_count']}",
        f"Observed occurrences: {summary['occurrence_count']}",
        "",
        "## By failure layer",
        "",
        "| Failure layer | Occurrences |",
        "|---|---:|",
    ]
    for layer, count in summary["by_failure_layer"].items():
        lines.append(f"| {layer} | {count} |")
    lines.extend(
        [
            "",
            "## By severity",
            "",
            "| Severity | Occurrences |",
            "|---|---:|",
        ]
    )
    for severity, count in summary["by_severity"].items():
        lines.append(f"| {severity} | {count} |")
    lines.extend(["", "## Error records", ""])
    if not records:
        lines.append("No reviewed error records are available.")
    for record in records:
        lines.extend(
            [
                f"### {record.error_id}",
                "",
                (
                    f"Case: `{record.case_id}`; layer: `{record.failure_layer}`; "
                    f"severity: `{record.severity}`; frequency: {record.frequency}."
                ),
                f"Expected: `{record.expected_behavior}`. Observed: {record.observed_outcome}",
                f"Root-cause hypothesis: {record.root_cause_hypothesis}",
                f"Intervention: {record.proposed_intervention}",
                f"Predicted metric impact: {record.predicted_metric_impact}",
                f"Regression test: `{record.regression_test}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"
