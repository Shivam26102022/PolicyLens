from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scripts.evaluation_case_set import EvaluationCaseSet
from scripts.evaluation_registry import (
    EvaluationRegistryError,
    _source_tree_fingerprint,
    append_run_record,
    build_run_record,
    fingerprint,
    redact_configuration,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT / "data/evaluation/feature007-cases.json"
RUN_SCHEMA = ROOT / "specs/007-evaluation/contracts/evaluation-run.schema.json"


def _record(project_root: Path):
    case_set = EvaluationCaseSet.load(CASE_PATH)
    return build_run_record(
        case_set=case_set,
        case_set_path=CASE_PATH,
        project_root=project_root,
        status="blocked",
        configuration={
            "provider": "mlx",
            "model": "candidate-model",
            "api_key": "must-not-be-stored",
            "nested": {"password": "also-secret"},
        },
        notes=("Candidate set has no human approvals.",),
    )


def test_fingerprint_is_key_order_independent_and_configuration_redacts_secrets() -> None:
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})

    redacted = redact_configuration(
        {"api_key": "not-stored", "nested": {"password": "not-stored"}, "mode": "hybrid"}
    )

    assert redacted == {
        "api_key": "<redacted>",
        "nested": {"password": "<redacted>"},
        "mode": "hybrid",
    }
    assert "not-stored" not in json.dumps(redacted)


def test_run_record_conforms_to_contract_and_preserves_fingerprints(tmp_path: Path) -> None:
    record = _record(tmp_path)
    schema = json.loads(RUN_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        record.model_dump(mode="json")
    )

    assert record.case_set_sha256 == sha256_file(CASE_PATH)
    assert record.configuration["api_key"] == "<redacted>"
    assert record.configuration["nested"]["password"] == "<redacted>"
    assert record.code_revision is None
    assert record.source_tree_sha256 is None
    assert any("Git revision unavailable" in note for note in record.notes)


def test_source_tree_fingerprint_is_deterministic_and_tracks_relevant_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scripts" / "example.py"
    source.parent.mkdir()
    source.write_text("answer = 1\n", encoding="utf-8")
    (tmp_path / "scripts" / ".ignored.py").write_text("answer = 2\n", encoding="utf-8")

    original = _source_tree_fingerprint(tmp_path)

    assert original is not None
    assert _source_tree_fingerprint(tmp_path) == original
    source.write_text("answer = 3\n", encoding="utf-8")
    assert _source_tree_fingerprint(tmp_path) != original


def test_run_record_stores_source_tree_fingerprint_when_available(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "example.py"
    source.parent.mkdir()
    source.write_text("answer = 1\n", encoding="utf-8")

    record = _record(tmp_path)

    assert record.source_tree_sha256 == _source_tree_fingerprint(tmp_path)


def test_manifest_append_preserves_existing_runs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "evaluation-run-manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": "1.0", "runs": [{"run_id": "prior"}]}),
        encoding="utf-8",
    )

    append_run_record(_record(tmp_path), manifest_path=manifest_path)
    append_run_record(_record(tmp_path), manifest_path=manifest_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [run["run_id"] for run in manifest["runs"][:1]] == ["prior"]
    assert len(manifest["runs"]) == 3
    assert list(manifest_path.parent.glob(".evaluation-run-manifest.json.*.tmp")) == []


@pytest.mark.parametrize(
    "contents",
    [
        "not-json",
        json.dumps({"schema_version": "2.0", "runs": []}),
        json.dumps({"schema_version": "1.0", "runs": {}}),
    ],
)
def test_manifest_rejects_invalid_prior_state(tmp_path: Path, contents: str) -> None:
    manifest_path = tmp_path / "evaluation-run-manifest.json"
    manifest_path.write_text(contents, encoding="utf-8")

    with pytest.raises(EvaluationRegistryError):
        append_run_record(_record(tmp_path), manifest_path=manifest_path)
