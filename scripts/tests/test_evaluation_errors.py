from __future__ import annotations

import json
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scripts.analyze_evaluation_errors import main
from scripts.evaluation_errors import (
    EvaluationErrorRecord,
    EvaluationErrorStoreError,
    append_error_record,
    load_error_records,
    render_error_report,
    summarize_errors,
)
from scripts.evaluation_registry import EvaluationRegistryError

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
ERROR_SCHEMA = ROOT / "specs/007-evaluation/contracts/error-record.schema.json"


def _record(error_id: str = "err-001") -> EvaluationErrorRecord:
    return EvaluationErrorRecord(
        error_id=error_id,
        run_id=uuid4(),
        case_id="case-india-youth-2025",
        expected_behavior="answer",
        observed_outcome="Request failed with OPENAI_API_KEY=sk-test-secret-value.",
        failure_layer="generation",
        trace_id=uuid4(),
        severity="high",
        frequency=2,
        root_cause_hypothesis="Provider request returned a safe error.",
        supporting_trace_evidence=("Authorization: Bearer test-secret-token-value",),
        proposed_intervention="Add a sanitized fixture regression.",
        predicted_metric_impact="Reduce generation failures in the affected case family.",
        regression_test="scripts/tests/test_evaluation_errors.py::test_redacts_secret_values",
    )


def test_error_record_redacts_secret_values_and_conforms_to_schema() -> None:
    record = _record()
    schema = json.loads(ERROR_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        record.model_dump(mode="json")
    )

    serialized = record.model_dump_json()
    assert "sk-test-secret-value" not in serialized
    assert "test-secret-token-value" not in serialized
    assert "<redacted>" in serialized


def test_error_manifest_appends_records_and_preserves_prior_errors(tmp_path) -> None:
    manifest_path = tmp_path / "evaluation-error-manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": "1.0", "errors": []}),
        encoding="utf-8",
    )

    append_error_record(_record(), manifest_path=manifest_path)
    append_error_record(_record("err-002"), manifest_path=manifest_path)

    records = load_error_records(manifest_path)
    assert [record.error_id for record in records] == ["err-001", "err-002"]
    assert len(json.loads(manifest_path.read_text(encoding="utf-8"))["errors"]) == 2


@pytest.mark.parametrize(
    "contents",
    [
        "not-json",
        json.dumps({"schema_version": "2.0", "errors": []}),
        json.dumps({"schema_version": "1.0", "errors": {}}),
        json.dumps({"schema_version": "1.0", "errors": [{"bad": "record"}]}),
    ],
)
def test_error_manifest_rejects_invalid_prior_state(tmp_path, contents: str) -> None:
    manifest_path = tmp_path / "evaluation-error-manifest.json"
    manifest_path.write_text(contents, encoding="utf-8")

    with pytest.raises((EvaluationErrorStoreError, EvaluationRegistryError)):
        append_error_record(_record(), manifest_path=manifest_path)


def test_error_summary_and_report_aggregate_without_raw_trace_payloads() -> None:
    record = _record()
    summary = summarize_errors((record, record.model_copy(update={"error_id": "err-002"})))
    report = render_error_report((record,))

    assert summary["error_record_count"] == 2
    assert summary["occurrence_count"] == 4
    assert summary["by_failure_layer"] == {"generation": 4}
    assert "OPENAI_API_KEY" not in report
    assert "test-secret-value" not in report
    assert "test-secret-token-value" not in report
    assert "regression_errors.py" not in report


def test_error_report_cli_writes_empty_report_without_live_calls(tmp_path, capsys) -> None:
    report_path = tmp_path / "error-report.md"

    assert main(["--manifest", str(tmp_path / "missing.json"), "--output", str(report_path)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert result["error_record_count"] == 0
    assert "No reviewed error records" in report_path.read_text(encoding="utf-8")


def test_error_manifest_rejects_duplicate_error_ids(tmp_path) -> None:
    manifest_path = tmp_path / "evaluation-error-manifest.json"
    record = _record()
    append_error_record(record, manifest_path=manifest_path)

    with pytest.raises(EvaluationErrorStoreError, match="manifest is invalid"):
        append_error_record(record, manifest_path=manifest_path)
