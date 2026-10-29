from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import (
    Field,
    field_validator,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

from policylens.retrieval.models import StrictModel
from policylens.settings import PROJECT_ROOT
from scripts.evaluation_registry import EvaluationRegistryError, append_manifest_record

DEFAULT_FIXTURE_PATH = PROJECT_ROOT / "data/evaluation/security-attack-fixtures.json"
DEFAULT_THREAT_MODEL = PROJECT_ROOT / "docs/security/threat-model.md"
DEFAULT_RESULT_SCHEMA = (
    PROJECT_ROOT
    / "specs/008-security-and-responsible-ai/contracts/security-test-result.schema.json"
)
DEFAULT_RESULT_MANIFEST = PROJECT_ROOT / "data/manifests/security-test-manifest.json"

BOUNDARY_IDS = (
    "browser-frontend",
    "frontend-api",
    "api-openai",
    "api-mlx",
    "mcp-host-server",
    "mcp-server-data",
    "ingestion-source",
    "evaluation-judge",
    "logs-traces",
)
FIXTURE_IDS = tuple(f"SEC-008-{index:03d}" for index in range(1, 17))
_BOUNDARY_SET = frozenset(BOUNDARY_IDS)
_FIXTURE_SET = frozenset(FIXTURE_IDS)
_FIELD_LABELS = {
    "assets_and_data_class": "Assets/data class",
    "principals_and_identity": "Principals/identity",
    "authorization": "Authorization",
    "validation": "Validation",
    "logging_and_redaction": "Logging/redaction",
    "failure_behavior": "Failure behavior",
    "abuse_cases": "Abuse cases",
    "test_references": "Tests",
    "residual_risk": "Residual risk",
}
_BOUNDARY_HEADER = re.compile(r"(?m)^## ([a-z][a-z0-9-]*): (.+)$")
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[:=]\s*"
        r"[\"']?[A-Za-z0-9~+/=-]{24,}"
    ),
    re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_SOURCE_MARKERS = re.compile(
    r"(?i)\b(?:world bank|international labour organization|ilo dataset|"
    r"data/canonical/|source_id\s*=|sha256:|page\s+[0-9]{1,4})\b"
)
_TEXT_SUFFIXES = frozenset(
    {".css", ".html", ".js", ".json", ".md", ".py", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml"}
)
_IGNORED_PARTS = frozenset(
    {".git", ".venv", "__pycache__", "node_modules", "indexes", "raw", "canonical", "processed"}
)
_APPROVED_FAKE_SECRET_FIXTURES = frozenset(
    {
        "apps/backend/tests/unit/test_agent_state.py",
        "apps/backend/tests/unit/test_logging.py",
        "apps/backend/tests/unit/test_mcp_client.py",
        "apps/backend/tests/unit/test_settings.py",
        "scripts/tests/test_evaluation_errors.py",
        "scripts/tests/test_evaluation_registry.py",
        "scripts/tests/test_evaluation_review.py",
        "services/mcp-policy-data/tests/test_logging.py",
    }
)
_APPROVED_SECRET_PLACEHOLDERS = ("mlx-local-no-auth-token",)


class SecurityAuditError(ValueError):
    """Security audit inputs are invalid or unsafe to record."""


def _has_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


class TrustBoundary(StrictModel):
    boundary_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    assets_and_data_class: str
    principals_and_identity: str
    authorization: str
    validation: str
    logging_and_redaction: str
    failure_behavior: str
    abuse_cases: str
    test_references: str
    residual_risk: str

    @field_validator("boundary_id")
    @classmethod
    def validate_boundary_id(cls, value: str) -> str:
        if value not in _BOUNDARY_SET:
            raise ValueError("unknown boundary ID")
        return value


class AttackFixture(StrictModel):
    fixture_id: str = Field(min_length=1, max_length=100)
    boundary_id: str = Field(min_length=1, max_length=100)
    attack_category: str = Field(min_length=1, max_length=100)
    payload: str = Field(min_length=1, max_length=1000)
    expected_invariant: str = Field(min_length=1, max_length=1000)
    test_reference: str = Field(min_length=1, max_length=500)
    status: Literal["planned", "tested", "unavailable"]

    @field_validator("fixture_id")
    @classmethod
    def validate_fixture_id(cls, value: str) -> str:
        if value not in _FIXTURE_SET:
            raise ValueError("unknown fixture ID")
        return value

    @field_validator("boundary_id")
    @classmethod
    def validate_fixture_boundary(cls, value: str) -> str:
        if value not in _BOUNDARY_SET:
            raise ValueError("unknown boundary ID")
        return value

    @field_validator("payload")
    @classmethod
    def validate_synthetic_payload(cls, value: str) -> str:
        if not value.startswith("SYNTHETIC:"):
            raise ValueError("fixture payload must be explicitly synthetic")
        if _has_secret(value):
            raise ValueError("fixture payload contains a secret-shaped value")
        if _SOURCE_MARKERS.search(value):
            raise ValueError("fixture payload contains a source-text marker")
        return value

    @field_validator("test_reference")
    @classmethod
    def validate_test_reference(cls, value: str) -> str:
        test_path = value.split("::", maxsplit=1)[0]
        if Path(test_path).is_absolute() or ".." in Path(test_path).parts:
            raise ValueError("test reference must be a workspace-relative path")
        return value


class AttackFixtureSet(StrictModel):
    schema_version: Literal["1.0"]
    fixtures: tuple[AttackFixture, ...] = Field(min_length=1, max_length=100)


class ResidualRisk(StrictModel):
    risk_id: str = Field(min_length=1, max_length=100)
    boundary_id: str = Field(min_length=1, max_length=100)
    condition: str = Field(min_length=1, max_length=1000)
    likelihood_impact: str = Field(min_length=1, max_length=1000)
    existing_mitigation: str = Field(min_length=1, max_length=1000)
    untested_assumption: str = Field(min_length=1, max_length=1000)
    owner_next_trigger: str = Field(min_length=1, max_length=500)
    local_only: bool

    @field_validator("boundary_id")
    @classmethod
    def validate_risk_boundary(cls, value: str) -> str:
        if value not in _BOUNDARY_SET:
            raise ValueError("unknown boundary ID")
        return value


class SecurityTestResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    fixture_id: str = Field(min_length=1, max_length=100)
    boundary_id: str = Field(min_length=1, max_length=100)
    result: Literal["pass", "fail", "blocked", "not_tested"]
    expected_invariant: str = Field(min_length=1, max_length=1000)
    observed_summary: str = Field(max_length=1000)
    test_reference: str = Field(min_length=1, max_length=500)
    artifact_reference: str | None = Field(default=None, max_length=500)
    environment: dict[str, str | None]
    live_requests_made: bool

    @field_validator("fixture_id")
    @classmethod
    def validate_result_fixture(cls, value: str) -> str:
        if value not in _FIXTURE_SET:
            raise ValueError("unknown fixture ID")
        return value

    @field_validator("boundary_id")
    @classmethod
    def validate_result_boundary(cls, value: str) -> str:
        if value not in _BOUNDARY_SET:
            raise ValueError("unknown boundary ID")
        return value

    @model_validator(mode="after")
    def reject_secret_values(self) -> SecurityTestResult:
        required_environment = {
            "execution_mode",
            "python_version",
            "dependency_lock_sha256",
        }
        if not required_environment.issubset(self.environment):
            raise ValueError("security result environment is missing execution or lock identity")
        if set(self.environment) - required_environment - {"code_revision"}:
            raise ValueError("security result environment contains an unknown field")
        lock_hash = self.environment["dependency_lock_sha256"]
        if not isinstance(lock_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", lock_hash):
            raise ValueError("security result requires a dependency lock digest")
        if self.environment["execution_mode"] == "offline" and self.live_requests_made:
            raise ValueError("offline result cannot report a live request")
        serialized = json.dumps(self.model_dump(mode="json"), ensure_ascii=True)
        if _has_secret(serialized):
            raise ValueError("security result contains a secret-shaped value")
        return self


def load_attack_fixtures(
    path: Path = DEFAULT_FIXTURE_PATH,
) -> tuple[AttackFixture, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SecurityAuditError("Security attack fixture file is invalid") from error
    try:
        fixture_set = AttackFixtureSet.model_validate(payload)
    except PydanticValidationError as error:
        messages = " ".join(item["msg"] for item in error.errors(include_input=False))
        if "unknown fixture ID" in messages:
            raise SecurityAuditError("Security fixture contains an unknown fixture ID") from error
        if "unknown boundary ID" in messages:
            raise SecurityAuditError("Security fixture contains an unknown boundary ID") from error
        if "synthetic" in messages:
            raise SecurityAuditError("Security fixture payload must be synthetic") from error
        if "secret-shaped" in messages or "source-text" in messages:
            raise SecurityAuditError(
                "Security fixture contains restricted text or secret-shaped data"
            ) from error
        raise SecurityAuditError("Security attack fixture record is invalid") from error

    fixture_ids = [fixture.fixture_id for fixture in fixture_set.fixtures]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise SecurityAuditError("Security attack fixture file contains a duplicate fixture ID")
    if set(fixture_ids) != _FIXTURE_SET:
        raise SecurityAuditError("Security attack fixture set is missing required fixture IDs")
    return fixture_set.fixtures


def load_boundary_inventory(path: Path = DEFAULT_THREAT_MODEL) -> tuple[TrustBoundary, ...]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SecurityAuditError("Threat model is unavailable") from error
    headers = tuple(_BOUNDARY_HEADER.finditer(content))
    inventory: list[TrustBoundary] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        section = content[header.end() : end]
        values: dict[str, str] = {
            "boundary_id": header.group(1),
            "title": header.group(2).strip(),
        }
        for field_name, label in _FIELD_LABELS.items():
            match = re.search(rf"(?m)^- \*\*{re.escape(label)}\*\*:\s*(.*)$", section)
            values[field_name] = match.group(1).strip() if match else ""
        try:
            inventory.append(TrustBoundary.model_validate(values))
        except ValueError as error:
            raise SecurityAuditError("Threat model contains an unknown boundary ID") from error
    return tuple(inventory)


def boundary_issues(
    inventory: tuple[TrustBoundary, ...], *, project_root: Path = PROJECT_ROOT
) -> tuple[str, ...]:
    issues: list[str] = []
    found_ids = [boundary.boundary_id for boundary in inventory]
    if len(found_ids) != len(set(found_ids)):
        issues.append("Boundary IDs must be unique.")
    for boundary_id in BOUNDARY_IDS:
        if boundary_id not in found_ids:
            issues.append(f"Missing boundary: {boundary_id}.")
    for boundary in inventory:
        for field_name in _FIELD_LABELS:
            if not getattr(boundary, field_name).strip():
                issues.append(f"{boundary.boundary_id} is missing {_FIELD_LABELS[field_name]}.")
        if boundary.test_references and "not_tested" not in boundary.test_references.casefold():
            references = re.findall(r"`([^`]+)`", boundary.test_references)
            if not references:
                issues.append(f"{boundary.boundary_id} has no test reference or limitation.")
            for reference in references:
                test_path = reference.split("::", maxsplit=1)[0]
                if not (project_root / test_path).is_file():
                    issues.append(f"{boundary.boundary_id} references a missing test: {test_path}.")
    return tuple(issues)


def _fixture_issues(fixtures: tuple[AttackFixture, ...], project_root: Path) -> tuple[str, ...]:
    issues = []
    for fixture in fixtures:
        reference_parts = fixture.test_reference.split("::", maxsplit=1)
        test_path = reference_parts[0]
        source_path = project_root / test_path
        if not source_path.is_file():
            issues.append(f"{fixture.fixture_id} references a missing test: {test_path}.")
        elif source_path.suffix == ".py":
            test_name = reference_parts[1].split("::")[-1] if len(reference_parts) == 2 else ""
            try:
                module = ast.parse(source_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                issues.append(f"{fixture.fixture_id} references an unreadable test: {test_path}.")
            else:
                defined_tests = {
                    node.name
                    for node in ast.walk(module)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if not test_name or test_name not in defined_tests:
                    issues.append(
                        f"{fixture.fixture_id} references a missing test node: "
                        f"{fixture.test_reference}."
                    )
        if fixture.status == "unavailable" and "not_testable" not in fixture.expected_invariant:
            issues.append(f"{fixture.fixture_id} is unavailable without a not_testable reason.")
    return tuple(issues)


def _iter_scan_files(paths: Iterable[Path]) -> Iterable[tuple[Path, Path]]:
    for root in paths:
        if root.is_file():
            yield root, root
            continue
        if not root.is_dir():
            continue
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file() or candidate.suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            if any(part in _IGNORED_PARTS for part in candidate.parts):
                continue
            if candidate.stat().st_size > 2_000_000:
                continue
            yield root, candidate


def scan_secret_canaries(
    paths: Iterable[Path], *, project_root: Path | None = None
) -> tuple[str, ...]:
    findings: set[str] = set()
    for root, candidate in _iter_scan_files(paths):
        try:
            relative_path = (
                candidate.relative_to(project_root) if project_root else candidate.relative_to(root)
            )
        except ValueError:
            relative_path = Path(candidate.name)
        if relative_path.as_posix() in _APPROVED_FAKE_SECRET_FIXTURES:
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for placeholder in _APPROVED_SECRET_PLACEHOLDERS:
            content = content.replace(placeholder, "<approved-local-placeholder>")
        if any(pattern.search(content) for pattern in _SECRET_PATTERNS):
            findings.add(relative_path.as_posix())
    return tuple(sorted(findings))


def _scan_roots(project_root: Path) -> tuple[Path, ...]:
    relative_roots = (
        "apps/backend/src",
        "apps/backend/tests",
        "apps/frontend/src",
        "apps/frontend/tests",
        "apps/frontend/dist",
        "services/mcp-policy-data/src",
        "services/mcp-policy-data/tests",
        "scripts",
        "docs",
        "specs/008-security-and-responsible-ai",
        "data/evaluation",
    )
    return tuple(project_root / relative for relative in relative_roots)


def run_audit(
    *, project_root: Path = PROJECT_ROOT, include_secret_scan: bool = True
) -> dict[str, Any]:
    inventory = load_boundary_inventory(project_root / "docs/security/threat-model.md")
    fixtures = load_attack_fixtures(project_root / "data/evaluation/security-attack-fixtures.json")
    issues = list(boundary_issues(inventory, project_root=project_root))
    issues.extend(_fixture_issues(fixtures, project_root))
    secret_findings = (
        scan_secret_canaries(_scan_roots(project_root), project_root=project_root)
        if include_secret_scan
        else ()
    )
    issues.extend(f"Secret-shaped value detected in {path}." for path in secret_findings)
    return {
        "status": "completed" if not issues else "failed",
        "boundary_count": len(inventory),
        "fixture_count": len(fixtures),
        "fixture_mappings": sum(fixture.status != "unavailable" for fixture in fixtures),
        "secret_findings": list(secret_findings),
        "issues": issues,
        "live_requests_made": False,
    }


def append_security_test_result(
    result: SecurityTestResult,
    *,
    manifest_path: Path = DEFAULT_RESULT_MANIFEST,
    schema_path: Path = DEFAULT_RESULT_SCHEMA,
) -> None:
    try:
        fixture_by_id = {fixture.fixture_id: fixture for fixture in load_attack_fixtures()}
        fixture = fixture_by_id.get(result.fixture_id)
        if fixture is None or fixture.boundary_id != result.boundary_id:
            raise SecurityAuditError("Security result does not match its fixture boundary")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result.model_dump(mode="json"))
        append_manifest_record(
            result.model_dump(mode="json"),
            manifest_path=manifest_path,
            collection="results",
            record_validator=SecurityTestResult.model_validate,
        )
    except SecurityAuditError:
        raise
    except (
        OSError,
        json.JSONDecodeError,
        JSONSchemaValidationError,
        ValueError,
        EvaluationRegistryError,
    ) as error:
        raise SecurityAuditError("Security test result could not be safely recorded") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline PolicyLens security audits.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--boundaries", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--scan-secrets", action="store_true")
    parser.add_argument("--record-result", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_RESULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.record_result is not None:
            record = SecurityTestResult.model_validate(
                json.loads(arguments.record_result.read_text(encoding="utf-8"))
            )
            append_security_test_result(record, manifest_path=arguments.manifest)
            report: dict[str, Any] = {
                "status": "recorded",
                "fixture_id": record.fixture_id,
                "live_requests_made": record.live_requests_made,
            }
        else:
            report = run_audit(
                project_root=arguments.project_root,
                include_secret_scan=arguments.scan_secrets or arguments.verify,
            )
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0 if report["status"] in {"completed", "recorded"} else 1
    except (OSError, json.JSONDecodeError, SecurityAuditError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
