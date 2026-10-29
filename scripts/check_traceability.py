import json
import re
import sys
from pathlib import Path

GLOBAL_ID_PATTERN = re.compile(r"^[A-Z]+-\d{3}$")
FEATURE_REQUIREMENT_PATTERN = re.compile(
    r"^- \*\*((?:FR|OBS|TEST|DOC|TRACE|SEC|REPRO)-001-\d{2})\*\*:", re.MULTILINE
)
ACCEPTANCE_PATTERN = re.compile(r"\*\*(AC-001-\d{2})\*\*")
SUCCESS_PATTERN = re.compile(r"^- \*\*(SC-001-\d{2})\*\*:", re.MULTILINE)
TASK_REFERENCE_PATTERN = re.compile(r"\b(?:FR|OBS|TEST|DOC|TRACE|SEC|REPRO|AC|SC)-001-\d{2}\b")
DEMO_IDS = {f"DEMO-{number:02d}" for number in range(1, 11)}


def table_rows_in_section(markdown: str, section_title: str) -> list[list[str]]:
    heading = f"## {section_title}"
    lines = markdown.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []

    rows: list[list[str]] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if cells[0].lower() in {"id", "requirement id", "acceptance id", "success criterion"}:
            continue
        rows.append(cells)
    return rows


def compare_table(
    label: str,
    expected_ids: set[str],
    rows: list[list[str]],
    expected_columns: int,
) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    actual_ids: set[str] = set()
    duplicates: set[str] = set()

    for row in rows:
        row_id = row[0] if row else "<empty>"
        if len(row) != expected_columns:
            errors.append(
                f"{label}: row {row_id} has {len(row)} columns; expected {expected_columns}"
            )
        if any(not cell for cell in row):
            errors.append(f"{label}: row {row_id} has an empty mapping/evidence cell")
        if row_id in actual_ids:
            duplicates.add(row_id)
        actual_ids.add(row_id)

    for row_id in sorted(expected_ids - actual_ids):
        errors.append(f"{label}: missing row for {row_id}")
    for row_id in sorted(actual_ids - expected_ids):
        errors.append(f"{label}: orphan row for {row_id}")
    for row_id in sorted(duplicates):
        errors.append(f"{label}: duplicate row for {row_id}")

    return errors, actual_ids


def validate_documents(
    inventory: dict[str, object],
    spec: str,
    tasks: str,
    traceability: str,
) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    requirements = inventory.get("requirements")
    if not isinstance(requirements, list):
        return ["Inventory: requirements must be a list"], {}

    global_ids: list[str] = []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("id"), str):
            errors.append("Inventory: every requirement must contain a string id")
            continue
        global_ids.append(requirement["id"])
        if not requirement.get("acceptance_criteria") or not requirement.get("expected_evidence"):
            errors.append(
                f"Inventory: {requirement['id']} is missing acceptance criteria or evidence"
            )

    if len(global_ids) != len(set(global_ids)):
        errors.append("Inventory: duplicate global requirement IDs")
    invalid_global_ids = sorted(
        set(global_ids) - {item for item in global_ids if GLOBAL_ID_PATTERN.fullmatch(item)}
    )
    errors.extend(f"Inventory: invalid global requirement ID {item}" for item in invalid_global_ids)

    feature_ids = set(FEATURE_REQUIREMENT_PATTERN.findall(spec))
    acceptance_ids = set(ACCEPTANCE_PATTERN.findall(spec))
    success_ids = set(SUCCESS_PATTERN.findall(spec))
    task_references = set(TASK_REFERENCE_PATTERN.findall(tasks))
    known_task_ids = feature_ids | acceptance_ids | success_ids

    checks = [
        (
            "Global requirements",
            set(global_ids),
            table_rows_in_section(traceability, "Global Requirement Matrix"),
            5,
        ),
        (
            "Feature 001 requirements",
            feature_ids,
            table_rows_in_section(traceability, "Feature 001 Requirement Mapping"),
            3,
        ),
        (
            "Acceptance criteria",
            acceptance_ids,
            table_rows_in_section(traceability, "Feature 001 Acceptance Scenario Mapping"),
            3,
        ),
        (
            "Success criteria",
            success_ids,
            table_rows_in_section(traceability, "Definition of Done Mapping"),
            3,
        ),
        (
            "Demo scenarios",
            DEMO_IDS,
            table_rows_in_section(traceability, "Ten Required Demonstration Scenarios"),
            7,
        ),
    ]

    for label, expected, rows, columns in checks:
        table_errors, _ = compare_table(label, expected, rows, columns)
        errors.extend(table_errors)

    unknown_task_ids = sorted(task_references - known_task_ids)
    errors.extend(
        f"Tasks: unknown requirement or acceptance ID {item}" for item in unknown_task_ids
    )

    counts = {
        "global_requirements": len(global_ids),
        "feature_requirements": len(feature_ids),
        "acceptance_criteria": len(acceptance_ids),
        "success_criteria": len(success_ids),
        "demo_scenarios": len(DEMO_IDS),
    }
    return errors, counts


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    inventory_path = root / "docs/traceability/requirements-inventory.json"
    spec_path = root / "specs/001-foundation/spec.md"
    tasks_path = root / "specs/001-foundation/tasks.md"
    traceability_path = root / "docs/traceability/traceability.md"

    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        errors, counts = validate_documents(
            inventory,
            spec_path.read_text(encoding="utf-8"),
            tasks_path.read_text(encoding="utf-8"),
            traceability_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as read_error:
        print(
            f"Traceability check could not read its inputs: {type(read_error).__name__}",
            file=sys.stderr,
        )
        return 2

    if errors:
        for finding in errors:
            print(f"ERROR: {finding}", file=sys.stderr)
        return 1

    summary = ", ".join(f"{key}={value}" for key, value in counts.items())
    print(f"Traceability check passed: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
