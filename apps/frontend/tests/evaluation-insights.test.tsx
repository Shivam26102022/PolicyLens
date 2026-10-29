import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { EvaluationRunSummary } from "../src/api/client";
import EvaluationInsights from "../src/components/EvaluationInsights";

const metrics = (recall: number | null, accuracy: number | null) =>
  ({
    retrieval_recall_at_k_mean: recall,
    expected_behavior_accuracy: accuracy,
    expected_behavior_scored_count: 10,
  }) as never;

const run = (
  id: string,
  startedAt: string,
  conditions: [string, number | null, number | null][],
  extra: Record<string, unknown> = {},
) =>
  ({
    run_id: id,
    started_at: startedAt,
    metrics: {
      headline_condition_id: null,
      baseline_condition_id: null,
      latency_p50_ms: null,
      ...extra,
    },
    condition_breakdowns: conditions.map(
      ([condition_id, recall, accuracy]) => ({
        condition_id,
        result_count: 10,
        failed_output_count: 0,
        metrics: metrics(recall, accuracy),
        category_breakdowns:
          accuracy === null
            ? []
            : [
                {
                  category: "edge_case",
                  result_count: 3,
                  failed_output_count: 0,
                  metrics: metrics(null, accuracy),
                },
              ],
      }),
    ),
  }) as unknown as EvaluationRunSummary;

afterEach(cleanup);

describe("EvaluationInsights", () => {
  it("shows reranker lift and before/after recall", () => {
    render(
      <EvaluationInsights
        runs={[
          run("aaaaaaaa-new", "2026-10-29T00:00:00Z", [
            ["retrieval:c1:hybrid", 0.7, null],
            ["retrieval:c1:hybrid+cross_encoder", 0.75, null],
          ]),
          run(
            "bbbbbbbb-old",
            "2026-10-20T00:00:00Z",
            [
              ["openai:agent", null, 0.9],
              ["openai:non_agent", null, 0.4],
              ["retrieval:c1:hybrid", 0.56, null],
            ],
            {
              headline_condition_id: "openai:agent",
              baseline_condition_id: "openai:non_agent",
            },
          ),
        ]}
      />,
    );
    expect(screen.getByText("With vs without the reranker")).toBeTruthy();
    expect(screen.getAllByText(/5\.0\s+points/).length).toBeGreaterThan(0);
    expect(screen.getByText(/from 56\.0% to 70\.0%/)).toBeTruthy();
    expect(screen.getByText(/beats the no-tool baseline by/)).toBeTruthy();
  });

  it("renders nothing without usable runs", () => {
    const { container } = render(<EvaluationInsights runs={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
