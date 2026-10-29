from __future__ import annotations

import csv
from uuid import uuid4

from scripts.blind_review import SHEET_COLUMNS, main, stratified_sample
from scripts.evaluation_review import load_review_records


def test_stratified_sample_covers_every_category_first() -> None:
    cases = [{"case_id": f"{c}-{i}", "category": c} for c in "abc" for i in range(5)]
    sample = stratified_sample(cases, 3, seed=0)
    assert {case["category"] for case in sample} == {"a", "b", "c"}


def test_import_appends_scored_rows_only(tmp_path) -> None:
    sheet = tmp_path / "sheet.csv"
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        base = {"question": "q", "answer": "a", "citations": ""}
        writer.writerow(
            {
                **base,
                "case_id": "factual-india-youth-2025",
                "groundedness": 5,
                "answer_relevance": 4,
                "citation_correctness": 5,
                "citation_completeness": 3,
                "expected_behavior_correct": "y",
                "safety_compliant": "yes",
                "notes": "blind human review",
            }
        )
        writer.writerow({**base, "case_id": "skipped-case"})
    manifest = tmp_path / "reviews.json"
    run_id = str(uuid4())
    main(
        [
            "import",
            "--input",
            str(sheet),
            "--run-id",
            run_id,
            "--reviewer-id",
            "reviewer-human",
            "--manifest",
            str(manifest),
        ]
    )
    records = load_review_records(manifest)
    assert [r.case_id for r in records] == ["factual-india-youth-2025"]
    assert records[0].citation_completeness == 3
