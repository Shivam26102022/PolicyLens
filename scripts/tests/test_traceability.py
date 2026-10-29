import json
from pathlib import Path

from scripts.check_traceability import compare_table, main, validate_documents


def test_complete_requirement_mapping_passes() -> None:
    errors, actual = compare_table(
        "Acceptance criteria",
        {"AC-001-01"},
        [["AC-001-01", "Run a focused test", "T002"]],
        3,
    )

    assert errors == []
    assert actual == {"AC-001-01"}


def test_missing_and_orphan_requirement_rows_fail() -> None:
    errors, _ = compare_table(
        "Feature requirements",
        {"FR-001-01", "FR-001-02"},
        [["FR-001-01", "T001", "A package test"], ["FR-001-03", "T002", "A health test"]],
        3,
    )

    assert "Feature requirements: missing row for FR-001-02" in errors
    assert "Feature requirements: orphan row for FR-001-03" in errors


def test_acceptance_mapping_without_evidence_fails() -> None:
    errors, _ = compare_table(
        "Acceptance criteria",
        {"AC-001-01"},
        [["AC-001-01", "", "T002"]],
        3,
    )

    assert "Acceptance criteria: row AC-001-01 has an empty mapping/evidence cell" in errors


def test_repository_traceability_maps_all_current_requirements() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    inventory = json.loads(
        (repository_root / "docs/traceability/requirements-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    errors, counts = validate_documents(
        inventory,
        (repository_root / "specs/001-foundation/spec.md").read_text(encoding="utf-8"),
        (repository_root / "specs/001-foundation/tasks.md").read_text(encoding="utf-8"),
        (repository_root / "docs/traceability/traceability.md").read_text(encoding="utf-8"),
    )

    assert errors == []
    assert counts == {
        "global_requirements": 67,
        "feature_requirements": 14,
        "acceptance_criteria": 11,
        "success_criteria": 5,
        "demo_scenarios": 10,
    }


def test_traceability_command_passes_for_the_repository() -> None:
    assert main() == 0
