from __future__ import annotations

import json
from builtins import __import__ as original_import
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from pydantic import ValidationError as PydanticValidationError

from scripts.evaluation_errors import redact_error_text
from scripts.security_audit import (
    BOUNDARY_IDS,
    SecurityTestResult,
    append_security_test_result,
    boundary_issues,
    load_attack_fixtures,
    load_boundary_inventory,
    run_audit,
    scan_secret_canaries,
)

ROOT = Path(__file__).resolve().parents[2]
RESULT_SCHEMA = (
    ROOT / "specs/008-security-and-responsible-ai/contracts/security-test-result.schema.json"
)


def _valid_result() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "fixture_id": "SEC-008-005",
        "boundary_id": "api-openai",
        "result": "pass",
        "expected_invariant": "No external request occurs without explicit opt-in.",
        "observed_summary": "Fake provider was not called.",
        "test_reference": "scripts/tests/test_security_audit.py::test_result_schema",
        "artifact_reference": None,
        "environment": {
            "execution_mode": "offline",
            "python_version": "3.12.14",
            "dependency_lock_sha256": "a" * 64,
            "code_revision": None,
        },
        "live_requests_made": False,
    }


def test_security_test_result_schema_is_valid_and_accepts_valid_record() -> None:
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(_valid_result())


@pytest.mark.parametrize(
    "update",
    [
        {"schema_version": "2.0"},
        {"result": "unknown"},
        {"fixture_id": ""},
        {"live_requests_made": True},
        {"unreviewed_field": "not allowed"},
        {
            "environment": {
                "execution_mode": "offline",
                "python_version": "3.12.14",
                "dependency_lock_sha256": "a" * 64,
                "code_revision": None,
                "unreviewed_field": "not allowed",
            }
        },
    ],
)
def test_security_test_result_schema_rejects_invalid_records(
    update: dict[str, object],
) -> None:
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    with pytest.raises(ValidationError):
        validator.validate(_valid_result() | update)


def test_boundary_inventory_contains_all_required_fields() -> None:
    inventory = load_boundary_inventory(ROOT / "docs/security/threat-model.md")

    assert {boundary.boundary_id for boundary in inventory} == set(BOUNDARY_IDS)
    assert boundary_issues(inventory) == ()


def test_fixture_loader_rejects_unknown_duplicate_and_non_synthetic_fixtures(
    tmp_path: Path,
) -> None:
    fixture_path = ROOT / "data/evaluation/security-attack-fixtures.json"
    fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixtures = load_attack_fixtures(fixture_path)
    assert len(fixtures) == 16
    consequential_case = next(
        fixture for fixture in fixtures if fixture.fixture_id == "SEC-008-011"
    )
    assert consequential_case.status == "unavailable"
    assert "not_testable" in consequential_case.expected_invariant

    unknown = json.loads(json.dumps(fixture_payload))
    unknown["fixtures"][0]["fixture_id"] = "SEC-008-999"
    unknown_path = tmp_path / "unknown.json"
    unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fixture"):
        load_attack_fixtures(unknown_path)

    unknown_boundary = json.loads(json.dumps(fixture_payload))
    unknown_boundary["fixtures"][0]["boundary_id"] = "unknown-boundary"
    unknown_boundary_path = tmp_path / "unknown-boundary.json"
    unknown_boundary_path.write_text(json.dumps(unknown_boundary), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown boundary"):
        load_attack_fixtures(unknown_boundary_path)

    duplicate = json.loads(json.dumps(fixture_payload))
    duplicate["fixtures"][1]["fixture_id"] = duplicate["fixtures"][0]["fixture_id"]
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate fixture"):
        load_attack_fixtures(duplicate_path)

    source_text = json.loads(json.dumps(fixture_payload))
    source_text["fixtures"][0]["payload"] = "A source quotation without a synthetic marker."
    source_path = tmp_path / "source-text.json"
    source_path.write_text(json.dumps(source_text), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic"):
        load_attack_fixtures(source_path)

    source_marker = json.loads(json.dumps(fixture_payload))
    source_marker["fixtures"][0]["payload"] = "SYNTHETIC: World Bank source quotation."
    source_marker_path = tmp_path / "source-marker.json"
    source_marker_path.write_text(json.dumps(source_marker), encoding="utf-8")
    with pytest.raises(ValueError, match="restricted text"):
        load_attack_fixtures(source_marker_path)

    secret_payload = json.loads(json.dumps(fixture_payload))
    secret_payload["fixtures"][0]["payload"] = "SYNTHETIC: api_key=" + "A" * 32
    secret_path = tmp_path / "secret.json"
    secret_path.write_text(json.dumps(secret_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="restricted text"):
        load_attack_fixtures(secret_path)


def test_security_audit_is_offline_and_never_imports_provider_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported_clients: list[str] = []

    def guarded_import(name: str, *args: Any, **kwargs: Any):
        if name.split(".")[0] in {"openai", "mlx", "mcp"}:
            imported_clients.append(name)
            raise AssertionError(f"provider client import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    report = run_audit(project_root=ROOT, include_secret_scan=False)

    assert report["status"] == "completed"
    assert report["live_requests_made"] is False
    assert imported_clients == []


def test_feature_scope_is_local_assessment_only() -> None:
    spec = (ROOT / "specs/008-security-and-responsible-ai/spec.md").read_text(encoding="utf-8")

    assert "Local assessment only" in spec
    assert "do not add public exposure or production authentication" in spec


def test_security_result_manifest_appends_validated_records(tmp_path: Path) -> None:
    manifest_path = tmp_path / "security-test-manifest.json"
    result = SecurityTestResult.model_validate(_valid_result())

    append_security_test_result(result, manifest_path=manifest_path)
    append_security_test_result(
        result.model_copy(update={"observed_summary": "Repeated deterministic test."}),
        manifest_path=manifest_path,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert len(manifest["results"]) == 2

    with pytest.raises(ValueError, match="does not match its fixture boundary"):
        append_security_test_result(
            result.model_copy(update={"boundary_id": "browser-frontend"}),
            manifest_path=manifest_path,
        )


def test_security_result_model_rejects_invalid_and_secret_summaries() -> None:
    with pytest.raises(PydanticValidationError):
        SecurityTestResult.model_validate(_valid_result() | {"unexpected": "value"})
    with pytest.raises(PydanticValidationError):
        SecurityTestResult.model_validate(
            _valid_result() | {"observed_summary": "Bearer " + "A" * 32}
        )
    with pytest.raises(PydanticValidationError, match="offline result"):
        SecurityTestResult.model_validate(_valid_result() | {"live_requests_made": True})


def test_secret_scan_reports_only_file_locations(tmp_path: Path) -> None:
    canary = "sk-" + "A" * 32
    private_file = tmp_path / "trace.txt"
    private_file.write_text(f"provider key: {canary}", encoding="utf-8")

    findings = scan_secret_canaries((tmp_path,))

    assert findings == ("trace.txt",)
    assert canary not in " ".join(findings)


def test_redaction_removes_fake_provider_token_password_and_personal_identifier() -> None:
    api_key = "sk-" + "A" * 32
    bearer = "Bearer " + "B" * 32
    password = "password=" + "C" * 28
    email = "reviewer" + "@example.test"
    value = f"API_KEY={api_key}; Authorization: {bearer}; {password}; {email}"

    redacted = redact_error_text(value)

    assert api_key not in redacted
    assert bearer not in redacted
    assert password not in redacted
    assert email not in redacted
