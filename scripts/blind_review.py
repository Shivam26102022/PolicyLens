"""Blind second-reviewer workflow.

`export` asks the live agent for answers to a stratified case sample and writes a
review sheet that omits expected behaviour, AI scores, and other reviewers' ratings.
`import` validates the filled CSV and appends review records for a human reviewer id.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from policylens.settings import PROJECT_ROOT
from scripts.evaluation_review import (
    DEFAULT_REVIEW_MANIFEST,
    RATING_FIELDS,
    EvaluationReviewRecord,
    append_review_record,
)

CASES_PATH = PROJECT_ROOT / "data/evaluation/feature007-cases.json"
RUBRIC_VERSION = "feature007-review-v1"
SHEET_COLUMNS = (
    "case_id",
    "question",
    "answer",
    "citations",
    *RATING_FIELDS,
    "expected_behavior_correct",
    "safety_compliant",
    "notes",
)
BOOLEAN_TRUE = {"y", "yes", "true", "1"}
BOOLEAN_FALSE = {"n", "no", "false", "0"}


def stratified_sample(cases: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    """Take cases round-robin across categories so every category is represented."""
    rng = random.Random(seed)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        by_category[case["category"]].append(case)
    for items in by_category.values():
        rng.shuffle(items)
    picked: list[dict[str, Any]] = []
    categories = sorted(by_category)
    while len(picked) < size and any(by_category.values()):
        for category in categories:
            if by_category[category] and len(picked) < size:
                picked.append(by_category[category].pop())
    rng.shuffle(picked)
    return picked


def render_answer(body: dict[str, Any]) -> tuple[str, str]:
    status = body.get("status", "unknown")
    text = body.get("answer") or body.get("clarification_question") or body.get("abstention_reason")
    citations: list[str] = []
    for claim in body.get("claims") or []:
        for citation in claim.get("citations") or []:
            pages = citation.get("page_start")
            where = f" p.{pages}" if pages else ""
            citations.append(
                f"[{claim.get('claim_id')}] {citation.get('source_id')}{where}: "
                f"{(citation.get('excerpt') or '')[:300]}"
            )
    return f"({status}) {text or 'no answer text'}", "\n".join(citations)


def export_sheet(args: argparse.Namespace) -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    sample = stratified_sample(cases, args.size, args.seed)
    workspace = str(uuid.uuid4())
    rows = []
    with httpx.Client(timeout=180) as client:
        for case in sample:
            response = client.post(
                f"{args.base_url}/api/agent/answer",
                headers={"X-Workspace-ID": workspace},
                json={
                    "schema_version": "1.0",
                    "query": case["question"],
                    "mode": case.get("mode", "hybrid"),
                    "allow_external_provider": True,
                },
            )
            answer, citations = render_answer(response.json())
            rows.append(
                {
                    "case_id": case["case_id"],
                    "question": case["question"],
                    "answer": answer,
                    "citations": citations,
                }
            )
    out = Path(args.output)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} blind rows to {out}. Fill the score columns (1-5; y/n) and import.")


def parse_bool(value: str, field: str, case_id: str) -> bool:
    lowered = value.strip().lower()
    if lowered in BOOLEAN_TRUE:
        return True
    if lowered in BOOLEAN_FALSE:
        return False
    raise ValueError(f"{case_id}: {field} must be y or n")


def import_sheet(args: argparse.Namespace) -> None:
    run_id = uuid.UUID(args.run_id)
    records = []
    with Path(args.input).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not any((row.get(field) or "").strip() for field in RATING_FIELDS):
                continue
            case_id = row["case_id"]
            records.append(
                EvaluationReviewRecord(
                    review_id=f"{run_id}:{case_id}:{args.reviewer_id}",
                    run_id=run_id,
                    case_id=case_id,
                    reviewer_id=args.reviewer_id,
                    rubric_version=RUBRIC_VERSION,
                    reviewed_at=datetime.now(UTC),
                    groundedness=int(row["groundedness"]),
                    answer_relevance=int(row["answer_relevance"]),
                    citation_correctness=int(row["citation_correctness"]),
                    citation_completeness=int(row["citation_completeness"]),
                    expected_behavior_correct=parse_bool(
                        row["expected_behavior_correct"], "expected_behavior_correct", case_id
                    ),
                    safety_compliant=parse_bool(
                        row["safety_compliant"], "safety_compliant", case_id
                    ),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    if not records:
        raise SystemExit("No scored rows found.")
    for record in records:
        append_review_record(record, manifest_path=Path(args.manifest))
    print(f"Appended {len(records)} reviews for {args.reviewer_id}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", default="blind-review-sheet.csv")
    export.add_argument("--size", type=int, default=20)
    export.add_argument("--seed", type=int, default=0)
    export.add_argument("--base-url", default="https://policy-lens-ochre.vercel.app")
    export.set_defaults(func=export_sheet)
    imp = sub.add_parser("import")
    imp.add_argument("--input", required=True)
    imp.add_argument("--run-id", required=True)
    imp.add_argument("--reviewer-id", required=True)
    imp.add_argument("--manifest", default=str(DEFAULT_REVIEW_MANIFEST))
    imp.set_defaults(func=import_sheet)
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
