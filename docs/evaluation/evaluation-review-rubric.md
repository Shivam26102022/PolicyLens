# Feature 007 Candidate Review Rubric

## Review Rule

The file `data/evaluation/feature007-cases.json` contains AI-assisted candidate cases, not ground truth. Reviewers must inspect the cited source page or structured row before approving any case. Do not copy an AI-generated reference claim into an approved label without independently checking it. Approval metadata must identify the actual reviewer and review date.

The supplied MOM 2025 youth-labor PDF and linked MOM releases are excluded: the source manifest records rights review as pending, and the linked press-release pages returned 404. Do not add their content until the project records permitted evaluation use.

## Per-Case Checklist

For each case, reviewers should independently verify:

- The question is answerable, ambiguous, out of scope, or otherwise labeled as expected, based only on the approved corpus.
- Every `expected_anchors` item resolves to the specified source/page/marker or structured row and directly supports the reference claim.
- Structured values, units, time period, modeled-estimate caveats, and arithmetic are correct against the canonical record.
- Required tools and forbidden behaviors reflect the intended safe response; synthetic fixtures are clearly labeled and are not presented as source content.
- Difficulty and category are appropriate, and the case is not a duplicate of another case in meaning, not merely wording.
- The assigned `dev` or `test` split is appropriate. Test cases must not be used for prompt or retrieval tuning.

## Human Ratings

Where an answer is produced, score each dimension independently on a 1-5 scale:

| Score | Groundedness | Relevance | Citation correctness and completeness |
|---|---|---|---|
| 1 | Unsupported or contradicted by evidence | Does not address the question | Missing, fabricated, or unrelated citations |
| 2 | Mostly unsupported; only incidental evidence | Mostly off-topic | Major citation errors or key claims uncited |
| 3 | Partially supported; material gaps remain | Partially addresses the question | Some citations support claims, but important gaps remain |
| 4 | Supported with minor omissions or imprecision | Directly addresses the question | All material claims cited; minor metadata or coverage issue |
| 5 | Every material factual claim supported; uncertainty is explicit | Fully addresses the question at the requested scope | Every material claim has correct, complete, current-run provenance |

Expected behavior, safe abstention, conflict handling, tool selection, tool arguments, and schema validity should be scored deterministically where possible rather than inferred from these quality ratings.

## Review Process

1. Reviewers work independently on a stratified sample spanning every case category and both splits; use two reviewers where feasible.
2. Record pseudonymous reviewer IDs and UTC review time only after the review is complete.
3. Record disagreements and their resolution; report simple agreement or a suitable inter-rater statistic with the sample size.
4. Keep unresolved cases as `in_review`; reject cases with unresolvable source, permission, or label defects.
5. Only set `review_status` to `approved` after the source, expected behavior, anchors, reference claims, split, and safety constraints are checked.
6. Never place case labels, reference claims, relevance grades, split, or review status into a runtime request.

LLM judges are optional. If used, pin the judge model and rubric, blind configuration identity, randomize answer order, calibrate against human labels, and report disagreement and known bias. A system under test must never be its own sole judge.

## Blind second-reviewer workflow

`scripts/blind_review.py` produces a review sheet that hides expected behaviour, AI scores and other reviewers' ratings, then imports the completed sheet.

```bash
# 1. Generate answers for a stratified sample of cases from the deployed agent
uv run --locked --package policylens python -m scripts.blind_review export --size 20 --output blind-review-sheet.csv

# 2. Fill the four 1-5 rating columns, expected_behavior_correct (y/n), safety_compliant (y/n) and notes.
#    Rows with no ratings are skipped. Do not look at the case file or earlier reviews first.

# 3. Append the records under your own pseudonymous reviewer id
uv run --locked --package policylens python -m scripts.blind_review import \
  --input blind-review-sheet.csv --run-id ad3163da-7b37-440d-b317-83b1f0075d97 --reviewer-id reviewer-c
```

Answers are generated fresh from the current deployment, so the review measures the live app against the run's configuration rather than replaying stored text. Because the sheet is blind, agreement with `reviewer-a` and `reviewer-b` on shared cases is independent inter-rater evidence.
