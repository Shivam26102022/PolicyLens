import { expect, test } from "@playwright/test";

const options = {
  schema_version: "1.0",
  default_provider: "mlx",
  options: [
    {
      provider: "mlx",
      model_id: "local-test-model",
      execution_scope: "loopback",
      configured: true,
      selected_by_default: true,
      consent_required: false,
      reasoning_efforts: ["none"],
    },
  ],
};

const summary = {
  schema_version: "1.5",
  status: "available",
  case_set: {
    case_count: 36,
    approved_case_count: 36,
    category_count: 20,
    category_counts: { factual: 12, adversarial: 4 },
    split_counts: { dev: 18, test: 18 },
  },
  runs: [
    {
      run_id: "585449c7-53e0-4704-b6f0-a6a7e7871678",
      status: "blocked",
      started_at: "2026-10-26T16:24:26.659139Z",
      finished_at: "2026-10-26T16:24:26.707240Z",
      split: "test",
      case_count: 0,
      live_requests_made: false,
      ai_judge: {
        enabled: false,
        rubric_version: null,
        model_ids: [],
        same_model_as_generator: null,
        attempted_count: 0,
        scored_count: 0,
        failed_count: 0,
        skipped_count: 0,
        ineligible_output_count: 0,
      },
      metrics: {
        expected_behavior_accuracy: null,
        expected_behavior_scored_count: 0,
        failed_output_count: 0,
        failure_exclusion_applied: false,
        retrieval_recall_at_k_mean: null,
        retrieval_recall_at_k_scored_count: null,
        retrieval_anchor_hits: null,
        retrieval_anchor_count: null,
        citation_correctness_mean: null,
        citation_correctness_scored_count: null,
        citation_completeness_mean: null,
        citation_completeness_scored_count: null,
        citation_anchor_matches: null,
        citation_anchor_count: null,
        groundedness_mean: null,
        groundedness_scored_count: null,
        groundedness_score_distribution: null,
        answer_relevance_mean: null,
        answer_relevance_scored_count: null,
        latency_p50_ms: null,
        latency_p95_ms: null,
        latency_sample_count: null,
        validated_tool_result_output_count: null,
        estimated_cost_usd_total: null,
        estimated_cost_basis: "unavailable",
        estimated_cost_pricing_as_of: null,
        estimated_cost_usage_gap_count: null,
        estimated_cost_model_ids: [],
      },
      condition_breakdowns: [],
      limitations: ["No case metrics were measured."],
    },
  ],
  reviewed_case_count: 0,
  error_record_count: 0,
};

test("evaluation view is read-only and distinguishes missing metrics from zero", async ({
  page,
}) => {
  let evaluationRequests = 0;
  const olderRun = {
    ...summary.runs[0],
    run_id: "older-evaluation-run",
    started_at: "2026-10-20T16:24:26.659139Z",
    limitations: ["Older evaluation run should not be shown."],
  };
  await page.route("**/model/options", (route) =>
    route.fulfill({ json: options }),
  );
  await page.route("**/evaluation/summary", (route) => {
    evaluationRequests += 1;
    return route.fulfill({
      json: { ...summary, runs: [summary.runs[0], olderRun] },
    });
  });

  await page.goto("/evaluations");
  await expect(
    page.getByRole("heading", { name: "Latest evaluation run" }),
  ).toBeVisible();
  await expect(page.getByText("36 approved / 36 cases")).toBeVisible();
  await expect(page.getByText("Blocked")).toBeVisible();
  await expect(
    page.getByText("Older evaluation run should not be shown."),
  ).toHaveCount(0);
  await expect(page.getByText("Not measured").first()).toBeVisible();
  await page.getByText("Limitations · 1").click();
  await expect(page.getByText("No case metrics were measured.")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /run evaluation/i }),
  ).toHaveCount(0);
  expect(evaluationRequests).toBeGreaterThan(0);
});

test("empty evaluation summaries show an honest browser empty state", async ({
  page,
}) => {
  let evaluationRequests = 0;
  await page.route("**/model/options", (route) =>
    route.fulfill({ json: options }),
  );
  await page.route("**/evaluation/summary", (route) => {
    evaluationRequests += 1;
    return route.fulfill({
      json: {
        ...summary,
        status: "empty",
        runs: [],
      },
    });
  });

  await page.goto("/evaluations");
  await expect(
    page.getByText("No evaluation runs are recorded."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /run evaluation/i }),
  ).toHaveCount(0);
  expect(evaluationRequests).toBeGreaterThan(0);
});
