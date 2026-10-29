import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

const modelOptions = {
  schema_version: "1.0",
  default_provider: "mlx",
  options: [
    {
      provider: "mlx",
      model_id: "test-local-model",
      execution_scope: "loopback",
      configured: true,
      selected_by_default: true,
      consent_required: false,
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
    cases: [
      {
        case_id: "factual-india-youth-2025",
        category: "factual",
        question: "What was India's youth unemployment estimate in 2025?",
        expected_behavior: "answer",
        difficulty: "easy",
        split: "dev",
        review_status: "approved",
        reference_claims: ["The stored estimate is approximately 16.0%."],
        required_tools: [],
        forbidden_behaviors: ["Present the estimate as a survey result."],
        expected_sources: ["wb-youth-unemployment-1524-2015-2025"],
      },
    ],
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
        estimated_cost_usd_total: null,
        estimated_cost_basis: "unavailable",
        estimated_cost_pricing_as_of: null,
        estimated_cost_usage_gap_count: null,
        estimated_cost_model_ids: [],
        validated_tool_result_output_count: null,
      },
      condition_breakdowns: [],
      limitations: ["No case metrics were measured."],
    },
  ],
  reviewed_case_count: 0,
  error_record_count: 0,
};

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
});

describe("evaluation results", () => {
  it("renders only the newest recorded run", async () => {
    window.history.replaceState({}, "", "/evaluations");
    const olderRun = {
      ...summary.runs[0],
      run_id: "older-evaluation-run",
      started_at: "2026-10-20T16:24:26.659139Z",
      limitations: ["Older evaluation run should not be shown."],
    };
    const summaryWithHistory = {
      ...summary,
      runs: [summary.runs[0], olderRun],
    };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/model/options")) {
        return Promise.resolve({ ok: true, json: async () => modelOptions });
      }
      if (url.endsWith("/evaluation/summary")) {
        return Promise.resolve({
          ok: true,
          json: async () => summaryWithHistory,
        });
      }
      throw new Error("Unexpected browser request");
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Evaluations" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Agent and baseline run" }),
    ).toBeTruthy();
    expect(await screen.findByText("Blocked")).toBeTruthy();
    expect(
      screen.queryByText("Older evaluation run should not be shown."),
    ).toBeNull();
    expect(screen.getByText("36 approved / 36 cases")).toBeTruthy();
    expect(screen.getAllByText("Not measured").length).toBeGreaterThan(0);
    expect(screen.getByText("No case metrics were measured.")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /run evaluation/i }),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows an honest empty state when there are no runs", async () => {
    window.history.replaceState({}, "", "/evaluations");
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url.endsWith("/model/options")
            ? modelOptions
            : { ...summary, status: "empty", runs: [] },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByText("No evaluation runs are recorded."),
    ).toBeTruthy();
  });

  it("shows each case query and its expected-answer oracle", async () => {
    window.history.replaceState({}, "", "/evaluations");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url.endsWith("/model/options") ? modelOptions : summary,
        }),
      ),
    );

    render(<App />);

    expect(
      await screen.findByText(
        "What was India's youth unemployment estimate in 2025?",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Oracle: Answer with citations/)).toBeTruthy();
    expect(
      screen.getByText("The stored estimate is approximately 16.0%."),
    ).toBeTruthy();
  });

  it("labels AI-judged scores with the judge model and scoring coverage", async () => {
    window.history.replaceState({}, "", "/evaluations");
    const judgedSummary = {
      ...summary,
      runs: [
        {
          ...summary.runs[0],
          ai_judge: {
            enabled: true,
            rubric_version: "feature007-ai-judge-v2",
            model_ids: ["judge-model"],
            same_model_as_generator: true,
            attempted_count: 2,
            scored_count: 1,
            failed_count: 1,
            skipped_count: 1,
            ineligible_output_count: 1,
          },
          metrics: {
            ...summary.runs[0].metrics,
            expected_behavior_accuracy: 0.5,
            expected_behavior_scored_count: 2,
            failed_output_count: 1,
            failure_exclusion_applied: true,
            groundedness_mean: 4,
            groundedness_scored_count: 1,
            groundedness_score_distribution: [0, 0, 0, 1, 0],
            retrieval_recall_at_k_mean: 0.566,
            retrieval_recall_at_k_scored_count: 25,
            retrieval_anchor_hits: 17,
            retrieval_anchor_count: 30,
            answer_relevance_mean: 3,
            answer_relevance_scored_count: 1,
          },
          condition_breakdowns: [
            {
              condition_id: "openai:agent",
              result_count: 2,
              failed_output_count: 1,
              metrics: {
                expected_behavior_accuracy: 0.5,
                expected_behavior_scored_count: 2,
                retrieval_recall_at_k_mean: null,
                retrieval_recall_at_k_scored_count: null,
                retrieval_anchor_hits: null,
                retrieval_anchor_count: null,
                citation_correctness_mean: 1,
                citation_correctness_scored_count: 1,
                citation_completeness_mean: 0.5,
                citation_completeness_scored_count: 1,
                citation_anchor_matches: 1,
                citation_anchor_count: 2,
                groundedness_mean: 4,
                groundedness_scored_count: 1,
                groundedness_score_distribution: [0, 0, 0, 1, 0],
                answer_relevance_mean: 3,
                answer_relevance_scored_count: 1,
                validated_tool_result_output_count: 1,
                latency_sample_count: 1,
              },
              category_breakdowns: [
                {
                  category: "calculation",
                  result_count: 1,
                  failed_output_count: 0,
                  metrics: {
                    expected_behavior_accuracy: 1,
                    expected_behavior_scored_count: 1,
                    retrieval_recall_at_k_mean: null,
                    retrieval_recall_at_k_scored_count: 0,
                    retrieval_anchor_hits: null,
                    retrieval_anchor_count: null,
                    citation_correctness_mean: 1,
                    citation_correctness_scored_count: 1,
                    citation_completeness_mean: 1,
                    citation_completeness_scored_count: 1,
                    citation_anchor_matches: 2,
                    citation_anchor_count: 2,
                    groundedness_mean: 5,
                    groundedness_scored_count: 1,
                    groundedness_score_distribution: [0, 0, 0, 0, 1],
                    answer_relevance_mean: 4,
                    answer_relevance_scored_count: 1,
                    validated_tool_result_output_count: 1,
                    latency_sample_count: 1,
                  },
                },
              ],
            },
          ],
          limitations: [
            "Groundedness and answer relevance are AI-judged; not human-validated.",
          ],
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url.endsWith("/model/options") ? modelOptions : judgedSummary,
        }),
      ),
    );

    render(<App />);

    const judgeMeta = await screen.findByText(/AI judge · judge-model/);
    expect(judgeMeta.textContent).toContain(
      "1/2 scored · 1 failed · 1 skipped · 1 failed-generation output excluded",
    );
    expect(judgeMeta.textContent).toContain(
      "Judge model ID matches generation for all scored cases.",
    );
    expect(judgeMeta.textContent).toContain("Scores are not human-validated.");
    expect(screen.getByText(/Groundedness · AI judge · n=1/)).toBeTruthy();
    expect(screen.getByText("4.0 / 5")).toBeTruthy();
    expect(screen.getByText("How scores are measured")).toBeTruthy();
    expect(screen.getByText(/Groundedness · AI judge · n=1/)).toBeTruthy();
    expect(screen.getAllByText(/1\/5 · 0 outputs/).length).toBe(2);
    expect(screen.getByText("56.6%")).toBeTruthy();
    expect(
      screen.getByText("Expected evidence anchors found (pooled): 17 / 30"),
    ).toBeTruthy();
    fireEvent.click(screen.getByText(/Scores by condition/));
    fireEvent.click(screen.getByText("openai:agent", { selector: "code" }));
    fireEvent.click(screen.getByText(/Category breakdown/));
    expect(screen.getByText("calculation")).toBeTruthy();
    expect(
      screen.getByText(
        "1 failed output counted as incorrect for expected behavior and excluded from answer-quality scores.",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Expected behavior · n=2/)).toBeTruthy();
    expect(screen.getByText("50.0%")).toBeTruthy();
  });

  it("does not imply an anchor denominator for historical recall", async () => {
    window.history.replaceState({}, "", "/evaluations");
    const historicalSummary = {
      ...summary,
      runs: [
        {
          ...summary.runs[0],
          metrics: {
            ...summary.runs[0].metrics,
            retrieval_recall_at_k_mean: 0.566,
            retrieval_recall_at_k_scored_count: 25,
          },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url.endsWith("/model/options") ? modelOptions : historicalSummary,
        }),
      ),
    );

    render(<App />);

    expect(
      await screen.findByText(/Stored recall has no anchor-level denominator/),
    ).toBeTruthy();
  });

  it("does not render an empty groundedness distribution as measured", async () => {
    window.history.replaceState({}, "", "/evaluations");
    const emptyDistributionSummary = {
      ...summary,
      runs: [
        {
          ...summary.runs[0],
          metrics: {
            ...summary.runs[0].metrics,
            groundedness_scored_count: 0,
            groundedness_score_distribution: [0, 0, 0, 0, 0] as const,
          },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url.endsWith("/model/options")
              ? modelOptions
              : emptyDistributionSummary,
        }),
      ),
    );

    render(<App />);

    expect(
      await screen.findByText(/Groundedness · AI judge · n=0/),
    ).toBeTruthy();
    expect(screen.queryByText("Groundedness scores · 0 outputs")).toBeNull();
  });

  it("explains metric calculations and labels partial token cost estimates", async () => {
    window.history.replaceState({}, "", "/evaluations");
    const costSummary = {
      ...summary,
      runs: [
        {
          ...summary.runs[0],
          metrics: {
            ...summary.runs[0].metrics,
            estimated_cost_usd_total: 0.0232642,
            estimated_cost_basis: "partial_token_estimate",
            estimated_cost_pricing_as_of: "2026-10-28",
            estimated_cost_usage_gap_count: 5,
            estimated_cost_model_ids: ["gpt-6-luna"],
          },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url.endsWith("/model/options") ? modelOptions : costSummary,
        }),
      ),
    );

    render(<App />);

    expect(await screen.findByText("$0.0232642")).toBeTruthy();
    expect(
      screen.getByText("Estimated cost · partial token estimate"),
    ).toBeTruthy();
    expect(screen.getAllByText("How it's measured").length).toBe(9);

    const costLabel = screen.getByText(
      "Estimated cost · partial token estimate",
    );
    const costCard = costLabel.closest(".evaluation-metric");
    const costDetails = costCard?.querySelector<HTMLElement>("summary");
    if (!costDetails) throw new Error("Cost metric disclosure is missing");
    fireEvent.click(costDetails);

    expect(
      await screen.findByText(/5 result rows had no usable token usage/),
    ).toBeTruthy();
    expect(
      screen.getByText(/OpenAI Standard short-context rates/),
    ).toBeTruthy();
  });
});
