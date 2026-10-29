# Feature 007 Evaluation Report

Run ID: `7437acdc-972b-433b-b8ff-4f9f4dc31630`
Status: `completed`
Started at: `2026-10-29T03:01:00.442486+00:00`
Case set: `feature007-candidate-ground-truth-v1` (`6060567cfc83d6f5cd90b1e486189f6b02067805316c7b372a70dcb3db84f460`)
Git revision: `f4e5520c7c38cbc7ab5fb4c3555115ae99f41b2f`
Source tree SHA-256: `f6721c364de04c26ec79f0931d0a457d197a2cc0527c844feeb20edf66dca9a7`
Prompt versions: not recorded
Model IDs: not recorded
Live requests made: `false`

## Conditions

| Condition | Results | Outputs scored | Failed excluded | Expected behavior accuracy | Recall@k | MRR | nDCG@k | Groundedness (AI, 1-5) | Relevance (AI, 1-5) | Mean latency ms | P95 latency ms | Tokens in/out | Est. cost USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| retrieval:fixed-500-75-v4:bm25 | 40 | 0 | 0 | not measured | 0.629 | 0.633 | 0.611 | not measured | not measured | 0.200 | 0.256 | not measured | not measured |
| retrieval:fixed-500-75-v4:dense | 40 | 0 | 0 | not measured | 0.662 | 0.608 | 0.619 | not measured | not measured | 5.121 | 7.355 | not measured | not measured |
| retrieval:fixed-500-75-v4:hybrid | 40 | 0 | 0 | not measured | 0.688 | 0.637 | 0.647 | not measured | not measured | 5.514 | 7.753 | not measured | not measured |
| retrieval:fixed-500-75-v4:hybrid+cross_encoder | 40 | 0 | 0 | not measured | 0.750 | 0.692 | 0.701 | not measured | not measured | 202.639 | 461.405 | not measured | not measured |
| retrieval:structure-aware-250-v4:bm25 | 40 | 0 | 0 | not measured | 0.675 | 0.631 | 0.631 | not measured | not measured | 0.204 | 0.255 | not measured | not measured |
| retrieval:structure-aware-250-v4:dense | 40 | 0 | 0 | not measured | 0.637 | 0.600 | 0.608 | not measured | not measured | 7.331 | 12.339 | not measured | not measured |
| retrieval:structure-aware-250-v4:hybrid | 40 | 0 | 0 | not measured | 0.713 | 0.647 | 0.661 | not measured | not measured | 7.808 | 12.549 | not measured | not measured |
| retrieval:structure-aware-250-v4:hybrid+cross_encoder | 40 | 0 | 0 | not measured | 0.750 | 0.693 | 0.702 | not measured | not measured | 103.050 | 239.264 | not measured | not measured |
| retrieval:structure-aware-450-v4:bm25 | 40 | 0 | 0 | not measured | 0.633 | 0.634 | 0.615 | not measured | not measured | 0.206 | 0.283 | not measured | not measured |
| retrieval:structure-aware-450-v4:dense | 40 | 0 | 0 | not measured | 0.662 | 0.610 | 0.620 | not measured | not measured | 5.302 | 7.584 | not measured | not measured |
| retrieval:structure-aware-450-v4:hybrid | 40 | 0 | 0 | not measured | 0.713 | 0.640 | 0.655 | not measured | not measured | 5.646 | 7.982 | not measured | not measured |
| retrieval:structure-aware-450-v4:hybrid+cross_encoder | 40 | 0 | 0 | not measured | 0.750 | 0.694 | 0.703 | not measured | not measured | 159.279 | 357.802 | not measured | not measured |

Failed generation outputs count as incorrect for expected-behavior accuracy and are excluded from AI answer-quality scores; retrieval and operational metrics remain measured.

## AI quality judging

- AI quality judging was not enabled for this run.

## Confidence and sample limits

- `retrieval:fixed-500-75-v4:bm25` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.483, 0.767]; mrr [0.479, 0.775]; ndcg_at_k [0.469, 0.745]
- `retrieval:fixed-500-75-v4:dense` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.525, 0.800]; mrr [0.469, 0.750]; ndcg_at_k [0.481, 0.760]
- `retrieval:fixed-500-75-v4:hybrid` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.537, 0.825]; mrr [0.500, 0.775]; ndcg_at_k [0.509, 0.781]
- `retrieval:fixed-500-75-v4:hybrid+cross_encoder` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.613, 0.875]; mrr [0.552, 0.819]; ndcg_at_k [0.568, 0.825]
- `retrieval:structure-aware-250-v4:bm25` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.537, 0.812]; mrr [0.487, 0.773]; ndcg_at_k [0.489, 0.768]
- `retrieval:structure-aware-250-v4:dense` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.500, 0.775]; mrr [0.456, 0.744]; ndcg_at_k [0.466, 0.752]
- `retrieval:structure-aware-250-v4:hybrid` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.562, 0.838]; mrr [0.504, 0.785]; ndcg_at_k [0.518, 0.796]
- `retrieval:structure-aware-250-v4:hybrid+cross_encoder` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.613, 0.875]; mrr [0.554, 0.822]; ndcg_at_k [0.565, 0.832]
- `retrieval:structure-aware-450-v4:bm25` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.483, 0.775]; mrr [0.480, 0.775]; ndcg_at_k [0.469, 0.753]
- `retrieval:structure-aware-450-v4:dense` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.525, 0.800]; mrr [0.471, 0.752]; ndcg_at_k [0.482, 0.761]
- `retrieval:structure-aware-450-v4:hybrid` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.575, 0.850]; mrr [0.508, 0.775]; ndcg_at_k [0.520, 0.787]
- `retrieval:structure-aware-450-v4:hybrid+cross_encoder` 95% bootstrap (n=40, retrieval metrics, minimum 20 cases): recall_at_k [0.613, 0.875]; mrr [0.556, 0.821]; ndcg_at_k [0.569, 0.826]
- `retrieval:fixed-500-75-v4:bm25`: latency mean 95% bootstrap interval [0.183, 0.221] ms (n=40, resamples=2000, seed=0).
- `retrieval:fixed-500-75-v4:dense`: latency mean 95% bootstrap interval [4.778, 5.490] ms (n=40, resamples=2000, seed=0).
- `retrieval:fixed-500-75-v4:hybrid`: latency mean 95% bootstrap interval [5.141, 5.920] ms (n=40, resamples=2000, seed=0).
- `retrieval:fixed-500-75-v4:hybrid+cross_encoder`: latency mean 95% bootstrap interval [144.607, 260.483] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-250-v4:bm25`: latency mean 95% bootstrap interval [0.184, 0.233] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-250-v4:dense`: latency mean 95% bootstrap interval [6.585, 8.194] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-250-v4:hybrid`: latency mean 95% bootstrap interval [7.067, 8.671] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-250-v4:hybrid+cross_encoder`: latency mean 95% bootstrap interval [75.395, 131.347] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-450-v4:bm25`: latency mean 95% bootstrap interval [0.186, 0.232] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-450-v4:dense`: latency mean 95% bootstrap interval [4.886, 5.785] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-450-v4:hybrid`: latency mean 95% bootstrap interval [5.290, 6.034] ms (n=40, resamples=2000, seed=0).
- `retrieval:structure-aware-450-v4:hybrid+cross_encoder`: latency mean 95% bootstrap interval [112.938, 204.643] ms (n=40, resamples=2000, seed=0).

## Generation behavior by category

- No generation results were measured.

## Generation behavior by split

- No generation results were measured.

## Evaluation-set review

Approved case definitions: 67 / 67
Case-definition reviewers recorded: 1

## Answer review for this run

Review records: 0
Reviewed answer cases: 0 / 67
Reviewers: 0
AI-assisted review records: 0
Cases with multiple reviewers: 0
Reviewer pairs: 0
Pairwise exact agreement: not measured
Mean scores (1-5): groundedness=not measured, answer_relevance=not measured, citation_correctness=not measured, citation_completeness=not measured
Expected-behavior rating accuracy: not measured
Safety-compliance rating rate: not measured

## Error analysis

Error records: 0
Observed error occurrences: 0
By failure layer: `{}`
By severity: `{}`

## Limitations

- Groundedness and answer relevance are not measured unless an AI judge completes successfully.
- Bootstrap intervals are omitted for fewer than 30 observations.
- Cost and local resource metrics are null when unavailable.
- nDCG uses binary relevance for cases without graded relevance labels.
- This run measures retrieval only; generation/provider comparison was skipped.
- Generation/provider comparison was not measured in this run.
- No answer-level reviews are linked to this run.
- Cost was not measured or estimated for this run.
- nDCG is not measured because no graded relevance labels were available.
- Candidate or unreviewed labels are never used as release ground truth.
