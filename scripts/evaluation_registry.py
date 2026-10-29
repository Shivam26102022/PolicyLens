from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import yaml
from pydantic import Field

from policylens.retrieval.models import StrictModel
from policylens.settings import PROJECT_ROOT
from scripts.evaluation_case_set import EvaluationCaseSet

RunStatus = Literal["completed", "partial", "blocked", "failed"]
DEFAULT_RUN_MANIFEST = PROJECT_ROOT / "data/manifests/evaluation-run-manifest.json"
_SECRET_KEY_PARTS = ("api_key", "secret", "password", "token", "authorization", "base_url")


class EvaluationRegistryError(ValueError):
    """The evaluation manifest could not be safely updated."""


class EvaluationRunRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID = Field(default_factory=uuid4)
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    case_set_id: str = Field(min_length=1, max_length=100)
    case_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    index_versions: tuple[str, ...] = Field(default=(), max_length=10)
    prompt_versions: tuple[str, ...] = Field(default=(), max_length=10)
    model_ids: tuple[str, ...] = Field(default=(), max_length=10)
    code_revision: str | None = Field(default=None, max_length=100)
    source_tree_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    uv_lock_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration: dict[str, Any]
    tool_versions: dict[str, str]
    seed: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    results: tuple[dict[str, Any], ...] = Field(default=(), max_length=1000)
    artifact_paths: tuple[str, ...] = Field(default=(), max_length=50)
    notes: tuple[str, ...] = Field(default=(), max_length=50)
    live_requests_made: bool = False


def fingerprint(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(secret_part in normalized for secret_part in _SECRET_KEY_PARTS)


def redact_configuration(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if _is_secret_key(str(key)) else redact_configuration(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [redact_configuration(item) for item in value]
    return value


def _corpus_fingerprint(project_root: Path) -> str | None:
    manifest_path = project_root / "data/manifests/sources.yaml"
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    source_records = manifest.get("sources") if isinstance(manifest, dict) else None
    if not isinstance(source_records, list):
        return None
    inputs = sorted(
        (
            {key: record.get(key) for key in ("source_id", "sha256", "canonical_sha256")}
            for record in source_records
            if isinstance(record, dict)
            and record.get("license_review_status") == "verified"
            and isinstance(record.get("source_id"), str)
        ),
        key=lambda item: str(item.get("source_id")),
    )
    return fingerprint(inputs)


def _code_revision(project_root: Path) -> str | None:
    configured = os.environ.get("POLICYLENS_CODE_REVISION", "").strip()
    if configured:
        return configured[:100]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()[:100] or None


def _source_tree_fingerprint(project_root: Path) -> str | None:
    source_roots = (
        "apps/backend/src",
        "apps/backend/tests",
        "apps/frontend/src",
        "apps/frontend/tests",
        "services/mcp-policy-data/src",
        "services/mcp-policy-data/tests",
        "scripts",
        "prompts",
        "specs/007-evaluation/contracts",
    )
    source_suffixes = {".json", ".js", ".jsx", ".md", ".py", ".ts", ".tsx"}
    input_files = {
        "Makefile",
        "pyproject.toml",
        "uv.lock",
        "apps/frontend/package.json",
        "apps/frontend/package-lock.json",
    }
    paths: set[Path] = set()
    try:
        for relative_root in source_roots:
            root = project_root / relative_root
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                relative_path = path.relative_to(project_root)
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and path.suffix.casefold() in source_suffixes
                    and not any(part.startswith(".") for part in relative_path.parts)
                ):
                    paths.add(path)
        paths.update(
            project_root / relative
            for relative in input_files
            if (project_root / relative).is_file()
        )

        if not paths:
            return None

        digest = hashlib.sha256()
        for path in sorted(paths, key=lambda item: item.relative_to(project_root).as_posix()):
            digest.update(path.relative_to(project_root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
    except OSError:
        return None
    return digest.hexdigest()


def _tool_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for distribution in ("policylens", "pydantic", "jsonschema", "openai", "openai-agents"):
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            continue
    return versions


def build_run_record(
    *,
    case_set: EvaluationCaseSet,
    case_set_path: Path,
    configuration: dict[str, Any],
    project_root: Path = PROJECT_ROOT,
    status: RunStatus = "blocked",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    index_versions: tuple[str, ...] = (),
    prompt_versions: tuple[str, ...] = (),
    model_ids: tuple[str, ...] = (),
    seed: int | None = None,
    metrics: dict[str, Any] | None = None,
    results: tuple[dict[str, Any], ...] = (),
    artifact_paths: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    live_requests_made: bool = False,
) -> EvaluationRunRecord:
    case_hash = sha256_file(case_set_path)
    if case_hash is None:
        raise EvaluationRegistryError("Evaluation case set cannot be fingerprinted")
    safe_configuration = redact_configuration(configuration)
    if not isinstance(safe_configuration, dict):
        raise EvaluationRegistryError("Evaluation configuration must be an object")
    lock_hash = sha256_file(project_root / "uv.lock")
    code_revision = _code_revision(project_root)
    source_tree_hash = _source_tree_fingerprint(project_root)
    run_notes = list(notes)
    if code_revision is None:
        run_notes.append(
            "Git revision unavailable; source_tree_sha256 identifies the evaluated source snapshot."
        )
    if source_tree_hash is None:
        run_notes.append("Source tree fingerprint unavailable.")
    if lock_hash is None:
        run_notes.append("uv.lock was unavailable when this run record was created.")

    return EvaluationRunRecord(
        status=status,
        started_at=started_at or datetime.now(UTC),
        finished_at=finished_at or datetime.now(UTC),
        case_set_id=case_set.set_id,
        case_set_sha256=case_hash,
        corpus_sha256=_corpus_fingerprint(project_root),
        index_versions=index_versions,
        prompt_versions=prompt_versions,
        model_ids=model_ids,
        code_revision=code_revision,
        source_tree_sha256=source_tree_hash,
        uv_lock_sha256=lock_hash,
        configuration_sha256=fingerprint(safe_configuration),
        configuration=safe_configuration,
        tool_versions=_tool_versions(),
        seed=seed,
        metrics=metrics or {},
        results=results,
        artifact_paths=artifact_paths,
        notes=tuple(run_notes),
        live_requests_made=live_requests_made,
    )


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def append_run_record(
    record: EvaluationRunRecord,
    *,
    manifest_path: Path = DEFAULT_RUN_MANIFEST,
) -> None:
    append_manifest_record(
        record.model_dump(mode="json"),
        manifest_path=manifest_path,
        collection="runs",
    )


def append_manifest_record(
    record: dict[str, Any],
    *,
    manifest_path: Path,
    collection: str,
    record_validator: Callable[[object], object] | None = None,
) -> None:
    if not collection or collection == "schema_version":
        raise EvaluationRegistryError("Manifest collection name is invalid")
    lock_path = manifest_path.with_suffix(manifest_path.suffix + ".lock")
    with _exclusive_lock(lock_path):
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise EvaluationRegistryError("Evaluation run manifest is invalid JSON") from error
            if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
                raise EvaluationRegistryError("Evaluation run manifest schema version is invalid")
            records = manifest.get(collection)
            if not isinstance(records, list):
                raise EvaluationRegistryError(f"Evaluation manifest {collection} must be an array")
            for existing_record in records:
                if not isinstance(existing_record, dict):
                    raise EvaluationRegistryError(
                        f"Evaluation manifest {collection} contains a non-object record"
                    )
                if record_validator is not None:
                    try:
                        record_validator(existing_record)
                    except Exception as error:
                        raise EvaluationRegistryError(
                            f"Evaluation manifest {collection} contains an invalid record"
                        ) from error
        else:
            manifest = {"schema_version": "1.0", collection: []}
            records = manifest[collection]
        id_field = {"runs": "run_id", "errors": "error_id", "reviews": "review_id"}.get(collection)
        if id_field is not None and any(
            isinstance(existing, dict) and existing.get(id_field) == record.get(id_field)
            for existing in records
        ):
            raise EvaluationRegistryError(
                f"Evaluation manifest {collection} contains duplicate IDs"
            )
        records.append(record)
        _atomic_write_json(manifest_path, manifest)
