import EvaluationInsights from "../components/EvaluationInsights";
import { useEffect, useState } from "react";
import { CircleAlert, FileChartColumnIncreasing } from "lucide-react";

import {
  getEvaluationSummary,
  type EvaluationCaseView,
  type EvaluationConditionBreakdown,
  type EvaluationScoreMetrics,
  type EvaluationRunSummary,
  type EvaluationSummaryResponse,
} from "../api/client";

function formatMetric(
  value: number | null,
  kind: "ratio" | "score" | "milliseconds" | "currency" = "ratio",
): string {
  if (value === null || !Number.isFinite(value)) return "Not measured";
  if (kind === "ratio") return `${(value * 100).toFixed(1)}%`;
  if (kind === "score") return `${value.toFixed(1)} / 5`;
  if (kind === "milliseconds")
    return `${Math.round(value).toLocaleString()} ms`;
  const [whole, fraction = ""] = value.toFixed(7).split(".");
  const significantFraction = fraction.replace(/0+$/, "");
  return `$${whole}.${significantFraction.padEnd(4, "0")}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function formatStatus(status: EvaluationRunSummary["status"]): string {
  if (status === "partial") return "Completed with gaps";
  return status
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const METRIC_EXPLANATIONS = {
  expectedBehavior:
    "Share of attempted outputs whose observed behavior (answer, clarify, abstain, surface a conflict, or block) matched the case oracle. Failed generations count as incorrect. This measures behavior, not factual accuracy.",
  retrievalRecall:
    "For each query and retrieval configuration, this is the fraction of expected evidence anchors found in the top six passages. The run value averages query/configuration rows, so a run comparing several chunkers and modes is not one deployed system's score. Multiple passage variants of an anchor count once.",
  citationCorrectness:
    "A measured output scores 1 when each passage citation has valid source and hash metadata and calculation claims reference host-validated tool results. This checks provenance structure, not whether evidence semantically supports the claim.",
  citationCompleteness:
    "For outputs with expected anchors, this is the fraction covered by a passage citation matching the expected source and row/page-marker, or by validated calculation evidence containing the expected structured row key. Fractions are averaged per output. It measures provenance coverage, not semantic support; outputs without expected anchors are not scored.",
  groundedness:
    "The AI judge rates whether substantive claims are supported by cited evidence and, for rubric versions that support it, validated deterministic calculation results. Scores range from 1 to 5 and are not human-validated; the run's rubric version is shown in judge details.",
  answerRelevance:
    "The AI judge rates how directly an output addresses the question and expected intent on a 1-to-5 scale. Relevance is not factual correctness, and these scores are not human-validated.",
  latency:
    "p50 is the median and p95 is the 95th percentile of recorded per-case latency for the headline condition (the agent when the run compares agent and baseline). Retrieval-only latency is in the condition breakdown. This is not an end-to-end latency guarantee.",
  externalRequests:
    "This is the run manifest's yes/no live-request flag, not a request count. It does not identify every destination or report the cost of those requests.",
} as const;

function costMetricLabel(
  basis: EvaluationRunSummary["metrics"]["estimated_cost_basis"],
): string {
  if (basis === "provider_reported") return "Provider-reported cost";
  if (basis === "token_estimate") return "Estimated cost · token estimate";
  if (basis === "partial_token_estimate")
    return "Estimated cost · partial token estimate";
  return "Estimated cost";
}

function costMetricDescription(
  metrics: EvaluationRunSummary["metrics"],
): string {
  if (metrics.estimated_cost_basis === "provider_reported") {
    return "This total comes from the cost recorded in the run manifest; the UI did not calculate a price from tokens.";
  }
  if (
    metrics.estimated_cost_basis === "token_estimate" ||
    metrics.estimated_cost_basis === "partial_token_estimate"
  ) {
    const models =
      metrics.estimated_cost_model_ids.join(", ") || "the recorded model";
    const pricingDate =
      metrics.estimated_cost_pricing_as_of ?? "an unspecified pricing date";
    const gaps = metrics.estimated_cost_usage_gap_count ?? 0;
    const coverage =
      metrics.estimated_cost_basis === "partial_token_estimate"
        ? ` ${gaps} result ${gaps === 1 ? "row had" : "rows had"} no usable token usage or a known model rate, so the estimate covers only priced recorded usage.`
        : " Token usage was available for all priced results.";
    return `Token estimate for ${models} using OpenAI Standard short-context rates as of ${pricingDate}: $0.10 per million input tokens and $0.50 per million output tokens. Input is treated as uncached because cached-token counts are not recorded.${coverage} This is not an invoice total.`;
  }
  const gaps = metrics.estimated_cost_usage_gap_count;
  const gapNote =
    gaps === null
      ? ""
      : ` ${gaps} result ${gaps === 1 ? "row could not" : "rows could not"} be priced because token usage was missing or the model rate was unsupported.`;
  return `No provider-reported total or token usage with a supported model price was available.${gapNote} Unknown model IDs are not assigned another model's rates, so no estimate is shown.`;
}

function Metric({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="evaluation-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <details className="evaluation-metric-details">
        <summary aria-label={`How ${label} is measured`}>
          How it's measured
        </summary>
        <p>{description}</p>
      </details>
    </div>
  );
}

function formatMetricWithCount(
  value: number | null,
  count: number | null,
  kind: "ratio" | "score" = "ratio",
): string {
  const sample = count === null ? "n unavailable" : `n=${count}`;
  return `${formatMetric(value, kind)} · ${sample}`;
}

function ScoreMetrics({ metrics }: { metrics: EvaluationScoreMetrics }) {
  return (
    <div className="evaluation-metrics evaluation-condition-metrics">
      <Metric
        label="Expected behavior"
        value={formatMetricWithCount(
          metrics.expected_behavior_accuracy,
          metrics.expected_behavior_scored_count,
        )}
        description={METRIC_EXPLANATIONS.expectedBehavior}
      />
      <Metric
        label="Retrieval recall@k"
        value={formatMetricWithCount(
          metrics.retrieval_recall_at_k_mean,
          metrics.retrieval_recall_at_k_scored_count,
        )}
        description={METRIC_EXPLANATIONS.retrievalRecall}
      />
      <Metric
        label="Citation correctness"
        value={formatMetricWithCount(
          metrics.citation_correctness_mean,
          metrics.citation_correctness_scored_count,
        )}
        description={METRIC_EXPLANATIONS.citationCorrectness}
      />
      <Metric
        label="Citation completeness"
        value={formatMetricWithCount(
          metrics.citation_completeness_mean,
          metrics.citation_completeness_scored_count,
        )}
        description={METRIC_EXPLANATIONS.citationCompleteness}
      />
      <Metric
        label="Groundedness · AI judge"
        value={formatMetricWithCount(
          metrics.groundedness_mean,
          metrics.groundedness_scored_count,
          "score",
        )}
        description={METRIC_EXPLANATIONS.groundedness}
      />
      <Metric
        label="Answer relevance · AI judge"
        value={formatMetricWithCount(
          metrics.answer_relevance_mean,
          metrics.answer_relevance_scored_count,
          "score",
        )}
        description={METRIC_EXPLANATIONS.answerRelevance}
      />
    </div>
  );
}

function GroundednessDistribution({
  distribution,
}: {
  distribution: EvaluationScoreMetrics["groundedness_score_distribution"];
}) {
  if (distribution === null) return null;
  const total = distribution.reduce((sum, count) => sum + count, 0);
  if (total === 0) return null;
  return (
    <div
      className="groundedness-distribution"
      role="group"
      aria-label="Groundedness score distribution"
    >
      <strong>Groundedness scores · {total} outputs</strong>
      <ul>
        {distribution.map((count, index) => {
          const score = index + 1;
          const width = total === 0 ? 0 : (count / total) * 100;
          return (
            <li key={score}>
              <span>
                {score}/5 · {count} outputs
              </span>
              <span className="groundedness-bar" aria-hidden="true">
                <span style={{ width: `${width}%` }} />
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ConditionBreakdowns({
  conditions,
}: {
  conditions: EvaluationConditionBreakdown[];
}) {
  if (conditions.length === 0) return null;
  return (
    <details className="evaluation-condition-breakdowns">
      <summary>Scores by condition · {conditions.length}</summary>
      <div className="evaluation-condition-list">
        {conditions.map((condition) => (
          <details
            className="evaluation-condition"
            key={condition.condition_id}
          >
            <summary>
              <span>{condition.condition_id}</span>
              <span>
                {condition.result_count} results ·{" "}
                {condition.failed_output_count} failed
              </span>
            </summary>
            <ScoreMetrics metrics={condition.metrics} />
            <GroundednessDistribution
              distribution={condition.metrics.groundedness_score_distribution}
            />
            {condition.metrics.retrieval_anchor_hits !== null &&
              condition.metrics.retrieval_anchor_count !== null && (
                <p className="evaluation-anchor-coverage">
                  Retrieval anchors found, all retrieval configurations pooled:{" "}
                  {condition.metrics.retrieval_anchor_hits} /{" "}
                  {condition.metrics.retrieval_anchor_count}
                </p>
              )}
            {condition.metrics.retrieval_recall_at_k_mean !== null &&
              condition.metrics.retrieval_anchor_count === null && (
                <p className="evaluation-anchor-coverage">
                  Stored recall has no anchor-level denominator; it was not
                  recalculated.
                </p>
              )}
            {condition.metrics.citation_anchor_matches !== null &&
              condition.metrics.citation_anchor_count !== null && (
                <p className="evaluation-anchor-coverage">
                  Expected citation anchors covered (agent outputs, pooled):{" "}
                  {condition.metrics.citation_anchor_matches} /{" "}
                  {condition.metrics.citation_anchor_count}
                </p>
              )}
            {condition.metrics.validated_tool_result_output_count !== null && (
              <p className="evaluation-anchor-coverage">
                Outputs with validated tool results:{" "}
                {condition.metrics.validated_tool_result_output_count}
              </p>
            )}
            {condition.category_breakdowns.length > 0 && (
              <details className="evaluation-category-breakdowns">
                <summary>
                  Category breakdown · {condition.category_breakdowns.length}
                </summary>
                <div
                  className="evaluation-table-scroll"
                  role="region"
                  tabIndex={0}
                  aria-label={`${condition.condition_id} category scores`}
                >
                  <table className="evaluation-score-table">
                    <thead>
                      <tr>
                        <th scope="col">Category</th>
                        <th scope="col">Outputs</th>
                        <th scope="col">Expected behavior</th>
                        <th scope="col">Expected anchor recall@6</th>
                        <th scope="col">Evidence completeness</th>
                        <th scope="col">Groundedness</th>
                        <th scope="col">Relevance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {condition.category_breakdowns.map((category) => (
                        <tr key={category.category}>
                          <th scope="row">
                            {category.category.replaceAll("_", " ")}
                          </th>
                          <td>
                            {category.result_count} ·{" "}
                            {category.failed_output_count} failed
                          </td>
                          <td>
                            {formatMetricWithCount(
                              category.metrics.expected_behavior_accuracy,
                              category.metrics.expected_behavior_scored_count,
                            )}
                          </td>
                          <td>
                            {formatMetricWithCount(
                              category.metrics.retrieval_recall_at_k_mean,
                              category.metrics
                                .retrieval_recall_at_k_scored_count,
                            )}
                          </td>
                          <td>
                            {formatMetricWithCount(
                              category.metrics.citation_completeness_mean,
                              category.metrics
                                .citation_completeness_scored_count,
                            )}
                          </td>
                          <td>
                            {formatMetricWithCount(
                              category.metrics.groundedness_mean,
                              category.metrics.groundedness_scored_count,
                              "score",
                            )}
                          </td>
                          <td>
                            {formatMetricWithCount(
                              category.metrics.answer_relevance_mean,
                              category.metrics.answer_relevance_scored_count,
                              "score",
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </details>
        ))}
      </div>
    </details>
  );
}

const ORACLE_LABELS: Record<string, string> = {
  answer: "Answer with citations",
  clarify: "Ask a clarifying question",
  abstain: "Abstain (no supporting evidence)",
  conflict: "Surface the conflict",
  block: "Refuse / block",
};

function CaseCard({ item }: { item: EvaluationCaseView }) {
  return (
    <li className="eval-case">
      <p className="eval-case-query">{item.question}</p>
      <div className="eval-case-tags">
        <span className={`oracle-tag oracle-${item.expected_behavior}`}>
          Oracle:{" "}
          {ORACLE_LABELS[item.expected_behavior] ?? item.expected_behavior}
        </span>
        <span>{item.difficulty}</span>
        <span>{item.split}</span>
        <span>{item.review_status}</span>
      </div>
      {item.reference_claims.length > 0 && (
        <div className="eval-case-block">
          <strong>Expected answer</strong>
          <ul>
            {item.reference_claims.map((claim) => (
              <li key={claim}>{claim}</li>
            ))}
          </ul>
        </div>
      )}
      {item.forbidden_behaviors.length > 0 && (
        <div className="eval-case-block">
          <strong>Must not</strong>
          <ul>
            {item.forbidden_behaviors.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
        </div>
      )}
      {(item.required_tools.length > 0 || item.expected_sources.length > 0) && (
        <p className="eval-case-meta">
          {item.required_tools.length > 0 &&
            `Tools: ${item.required_tools.join(", ")}`}
          {item.required_tools.length > 0 &&
            item.expected_sources.length > 0 &&
            " · "}
          {item.expected_sources.length > 0 &&
            `Sources: ${item.expected_sources.join(", ")}`}
        </p>
      )}
    </li>
  );
}

const RETRIEVAL_MODE_LABELS: Record<string, string> = {
  bm25: "BM25 (keyword)",
  dense: "Dense (BGE-small)",
  hybrid: "Hybrid (BM25 + dense)",
  "hybrid+cross_encoder": "Hybrid + cross-encoder reranker",
};

function isRetrievalOnlyRun(run: EvaluationRunSummary): boolean {
  return (
    run.condition_breakdowns.length > 0 &&
    run.condition_breakdowns.every((item) =>
      item.condition_id.startsWith("retrieval:"),
    )
  );
}

function RetrievalRunPanel({ run }: { run: EvaluationRunSummary }) {
  const byMode = new Map<string, { sum: number; count: number }>();
  for (const condition of run.condition_breakdowns) {
    const mode = condition.condition_id.split(":").slice(2).join(":");
    const recall = condition.metrics.retrieval_recall_at_k_mean;
    if (recall === null) continue;
    const entry = byMode.get(mode) ?? { sum: 0, count: 0 };
    entry.sum += recall;
    entry.count += 1;
    byMode.set(mode, entry);
  }
  const rows = Array.from(byMode.entries()).map(([mode, entry]) => ({
    mode,
    recall: entry.sum / entry.count,
    configs: entry.count,
  }));
  if (rows.length === 0) return null;
  return (
    <section
      className="evaluation-retrieval-run"
      aria-labelledby="retrieval-run-title"
    >
      <div className="coverage-heading">
        <div>
          <p className="eyebrow">RETRIEVAL RE-RUN</p>
          <h2 id="retrieval-run-title">
            Retrieval modes after the per-source-cap fix
          </h2>
        </div>
        <span className="coverage-summary">{formatDate(run.started_at)}</span>
      </div>
      <p className="evaluation-anchor-coverage">
        Run {run.run_id}. Retrieval only, no generation or judge calls. Expected
        anchor recall@6 averaged over the chunking configurations. The reranker
        row is local-only; the Vercel deployment runs without it.
      </p>
      <div
        className="evaluation-table-scroll"
        role="region"
        tabIndex={0}
        aria-label="Retrieval recall by mode"
      >
        <table className="evaluation-score-table">
          <thead>
            <tr>
              <th scope="col">Mode</th>
              <th scope="col">Expected anchor recall@6</th>
              <th scope="col">Chunking configs</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.mode}>
                <th scope="row">
                  {RETRIEVAL_MODE_LABELS[row.mode] ?? row.mode}
                </th>
                <td>{formatMetric(row.recall)}</td>
                <td>{row.configs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RunCard({ run }: { run: EvaluationRunSummary }) {
  const scoredOutputCount = run.metrics.expected_behavior_scored_count;
  const failedOutputCount = run.metrics.failed_output_count;
  const conditionIds = run.condition_breakdowns.map(
    (item) => item.condition_id,
  );
  const offlineGuardrailRun = conditionIds.some((condition) =>
    condition.startsWith("offline:"),
  );
  const retrievalConditionCount = conditionIds.filter((condition) =>
    condition.startsWith("retrieval:"),
  ).length;
  return (
    <article className="evaluation-run">
      <div className="evaluation-run-heading">
        <div>
          <span className={`run-badge run-badge-${run.status}`}>
            {formatStatus(run.status)}
          </span>
          <span className="run-date">{formatDate(run.started_at)}</span>
        </div>
        <span className="run-case-count">
          {run.case_count} measured · {run.split} split
        </span>
      </div>
      {conditionIds.length > 0 && (
        <p className="evaluation-score-coverage">
          Condition:{" "}
          {conditionIds.map((condition) => (
            <code key={condition}>{condition}</code>
          ))}
        </p>
      )}
      {offlineGuardrailRun && (
        <p className="evaluation-score-coverage">
          Offline host checks with stubbed model output; not live LLM quality
          evidence.
        </p>
      )}
      {run.metrics.failed_output_count > 0 && (
        <p className="evaluation-score-coverage">
          {failedOutputCount}{" "}
          {failedOutputCount === 1 ? "failed output" : "failed outputs"} counted
          as incorrect for expected behavior and excluded from answer-quality
          scores.
        </p>
      )}
      {run.metrics.headline_condition_id && (
        <p className="evaluation-score-coverage">
          Headline answer-quality metrics use the{" "}
          <code>{run.metrics.headline_condition_id}</code> condition only;
          latency covers the same rows. Retrieval metrics use the retrieval
          configurations only. Baseline and paired comparison are shown below.
        </p>
      )}
      <div className="evaluation-metrics">
        <Metric
          label={`Expected behavior · n=${scoredOutputCount}`}
          value={formatMetric(run.metrics.expected_behavior_accuracy)}
          description={METRIC_EXPLANATIONS.expectedBehavior}
        />
        <Metric
          label={`Expected anchor recall@6 · ${retrievalConditionCount} ${retrievalConditionCount === 1 ? "config" : "configs"} · ${run.metrics.retrieval_recall_at_k_scored_count === null ? "n unavailable" : `n=${run.metrics.retrieval_recall_at_k_scored_count}`}`}
          value={formatMetric(run.metrics.retrieval_recall_at_k_mean)}
          description={METRIC_EXPLANATIONS.retrievalRecall}
        />
        <Metric
          label={`Citation correctness · ${run.metrics.citation_correctness_scored_count === null ? "n unavailable" : `n=${run.metrics.citation_correctness_scored_count}`}`}
          value={formatMetric(run.metrics.citation_correctness_mean)}
          description={METRIC_EXPLANATIONS.citationCorrectness}
        />
        <Metric
          label={`Evidence completeness · ${run.metrics.citation_completeness_scored_count === null ? "n unavailable" : `n=${run.metrics.citation_completeness_scored_count}`}`}
          value={formatMetric(run.metrics.citation_completeness_mean)}
          description={METRIC_EXPLANATIONS.citationCompleteness}
        />
        <Metric
          label={`Groundedness · AI judge · ${run.metrics.groundedness_scored_count === null ? "n unavailable" : `n=${run.metrics.groundedness_scored_count}`}`}
          value={formatMetric(run.metrics.groundedness_mean, "score")}
          description={METRIC_EXPLANATIONS.groundedness}
        />
        <Metric
          label={`Answer relevance · AI judge · ${run.metrics.answer_relevance_scored_count === null ? "n unavailable" : `n=${run.metrics.answer_relevance_scored_count}`}`}
          value={formatMetric(run.metrics.answer_relevance_mean, "score")}
          description={METRIC_EXPLANATIONS.answerRelevance}
        />
        <Metric
          label={`Latency p50 / p95 · ${run.metrics.latency_sample_count === null ? "n unavailable" : `n=${run.metrics.latency_sample_count}`}`}
          value={`${formatMetric(run.metrics.latency_p50_ms, "milliseconds")} / ${formatMetric(run.metrics.latency_p95_ms, "milliseconds")}`}
          description={METRIC_EXPLANATIONS.latency}
        />
        <Metric
          label={costMetricLabel(run.metrics.estimated_cost_basis)}
          value={formatMetric(run.metrics.estimated_cost_usd_total, "currency")}
          description={costMetricDescription(run.metrics)}
        />
        <Metric
          label="External requests"
          value={run.live_requests_made ? "Made" : "None"}
          description={METRIC_EXPLANATIONS.externalRequests}
        />
      </div>
      {run.metrics.baseline_expected_behavior_accuracy !== null &&
        run.metrics.baseline_condition_id && (
          <p className="evaluation-anchor-coverage">
            Baseline <code>{run.metrics.baseline_condition_id}</code> expected
            behavior:{" "}
            {formatMetric(run.metrics.baseline_expected_behavior_accuracy)} (n=
            {run.metrics.baseline_expected_behavior_scored_count ?? 0}).
            {run.metrics.paired_accuracy_difference !== null &&
              run.metrics.paired_case_count !== null && (
                <>
                  {" "}
                  Paired difference over {run.metrics.paired_case_count} shared
                  cases (failed outputs count as incorrect):{" "}
                  {run.metrics.paired_accuracy_difference >= 0 ? "+" : ""}
                  {(run.metrics.paired_accuracy_difference * 100).toFixed(
                    1,
                  )}{" "}
                  pts
                  {run.metrics.paired_accuracy_difference_lower_95 !== null &&
                    run.metrics.paired_accuracy_difference_upper_95 !== null &&
                    ` (95% bootstrap ${(run.metrics.paired_accuracy_difference_lower_95 * 100).toFixed(1)} to ${(run.metrics.paired_accuracy_difference_upper_95 * 100).toFixed(1)})`}
                  {run.metrics.paired_mcnemar_p !== null &&
                    `, exact McNemar p ${run.metrics.paired_mcnemar_p < 0.0001 ? "< 0.0001" : `= ${run.metrics.paired_mcnemar_p.toFixed(4)}`}`}
                  .
                </>
              )}
          </p>
        )}
      {run.metrics.retrieval_anchor_hits !== null &&
        run.metrics.retrieval_anchor_count !== null && (
          <p className="evaluation-anchor-coverage">
            Expected evidence anchors found (pooled):{" "}
            {run.metrics.retrieval_anchor_hits} /{" "}
            {run.metrics.retrieval_anchor_count}
          </p>
        )}
      {run.metrics.retrieval_recall_at_k_mean !== null &&
        run.metrics.retrieval_anchor_count === null && (
          <p className="evaluation-anchor-coverage">
            Stored recall has no anchor-level denominator; it was not
            recalculated.
          </p>
        )}
      {run.metrics.citation_anchor_matches !== null &&
        run.metrics.citation_anchor_count !== null && (
          <p className="evaluation-anchor-coverage">
            Expected citation anchors covered (agent outputs, pooled):{" "}
            {run.metrics.citation_anchor_matches} /{" "}
            {run.metrics.citation_anchor_count}
          </p>
        )}
      {run.ai_judge.enabled && (
        <details className="evaluation-judge-meta">
          <summary>
            AI judge ·{" "}
            {run.ai_judge.model_ids.join(", ") || "model unavailable"} ·{" "}
            {run.ai_judge.scored_count}/{run.ai_judge.attempted_count} scored
            {run.ai_judge.failed_count > 0 &&
              ` · ${run.ai_judge.failed_count} failed`}
            {run.ai_judge.skipped_count > 0 &&
              ` · ${run.ai_judge.skipped_count} skipped`}
            {run.ai_judge.ineligible_output_count > 0 &&
              ` · ${run.ai_judge.ineligible_output_count} failed-generation output${run.ai_judge.ineligible_output_count === 1 ? "" : "s"} excluded`}
            {run.ai_judge.rubric_version && ` · ${run.ai_judge.rubric_version}`}
            .
            {run.ai_judge.same_model_as_generator === true &&
              " Judge model ID matches generation for all scored cases."}
            {run.ai_judge.same_model_as_generator === false &&
              " At least one judge model ID differs from generation."}
            Scores are not human-validated.
          </summary>
          <p>
            Attempted counts completed or failed judge calls. Scored counts
            eligible outputs with a returned score; skipped outputs were not
            sent to the judge, and failed-generation outputs are ineligible.
            Judge scores are diagnostic signals, not independent human review.
          </p>
        </details>
      )}
      <GroundednessDistribution
        distribution={run.metrics.groundedness_score_distribution}
      />
      <ConditionBreakdowns conditions={run.condition_breakdowns} />
      {run.limitations.length > 0 && (
        <details className="evaluation-limitations">
          <summary>Limitations · {run.limitations.length}</summary>
          <ul>
            {run.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

export default function EvaluationsPage() {
  const [summary, setSummary] = useState<EvaluationSummaryResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    getEvaluationSummary(controller.signal)
      .then(setSummary)
      .catch(() => {
        if (!controller.signal.aborted) {
          setError("Evaluation summaries are unavailable right now.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const categoryCounts = Object.entries(
    summary?.case_set.category_counts ?? {},
  ).sort(([, left], [, right]) => right - left);

  return (
    <div className="evaluations-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">QUALITY / MEASURED RUNS</p>
          <h1>Evaluations</h1>
          <p className="page-description">
            Review recorded coverage, metrics, and limitations. This view never
            starts a run.
          </p>
        </div>
        <FileChartColumnIncreasing
          className="page-watermark-icon"
          aria-hidden="true"
          size={34}
        />
      </section>

      {loading && (
        <p className="evaluation-state" role="status">
          Loading evaluation summaries…
        </p>
      )}
      {error && (
        <p className="inline-alert evaluation-state" role="alert">
          <CircleAlert aria-hidden="true" size={16} />
          {error}
        </p>
      )}
      {summary && (
        <>
          <EvaluationInsights runs={summary.runs} />
          <details className="evaluation-score-guide">
            <summary>How scores are measured</summary>
            <ul>
              <li>
                Expected behavior checks whether the response type matched the
                case oracle; it does not measure factual accuracy. When a run
                compares an agent with a non-agent baseline, the headline
                numbers are the agent only; the baseline and a paired comparison
                are shown separately.
              </li>
              <li>
                Synthetic conflict and retrieved-document injection fixtures are
                materialized by the evaluation harness; historical runs predate
                that change and the one-case strata remain descriptive. MLX
                tool-call failure is not executable on this Linux host. Human
                approval of case definitions is separate from human review of
                generated answers.
              </li>
              <li>
                Retrieval recall@k is the per-query fraction of expected
                evidence anchors found in the top k, averaged across retrieval
                results. A chunk split into several passages still counts as one
                anchor. The displayed anchor totals are pooled across results
                and may not equal the average percentage; n counts result rows,
                not unique cases, when multiple conditions are evaluated.
              </li>
              <li>
                Historical results without anchor totals retain their recorded
                recall and are not recalculated; their anchor-level denominator
                is unavailable.
              </li>
              <li>
                Citation correctness checks citation metadata structure.
                Citation completeness measures how many expected evidence
                anchors were covered; neither proves semantic support by itself.
              </li>
              <li>
                Groundedness and relevance are uncalibrated AI-judge scores from
                1 to 5, not human review. Current rubric v2 can use validated
                deterministic tool results for calculation claims; historical v1
                runs used cited excerpts only.
              </li>
              <li>
                Each metric shows its own scored sample count. Failed
                generations are excluded from answer-quality scores and shown
                separately.
              </li>
            </ul>
          </details>
          <section
            className="evaluation-coverage"
            aria-labelledby="coverage-title"
          >
            <div className="coverage-heading">
              <div>
                <p className="eyebrow">CASE SET</p>
                <h2 id="coverage-title">Coverage</h2>
              </div>
              <span className="coverage-summary">
                {summary.case_set.approved_case_count} approved /{" "}
                {summary.case_set.case_count} cases
              </span>
            </div>
            <div className="coverage-facts">
              <div>
                <strong>{summary.case_set.category_count}</strong>
                <span>categories</span>
              </div>
              <div>
                <strong>{summary.case_set.split_counts.dev}</strong>
                <span>development</span>
              </div>
              <div>
                <strong>{summary.case_set.split_counts.test}</strong>
                <span>test</span>
              </div>
              <div>
                <strong>{summary.reviewed_case_count}</strong>
                <span>scored review cases</span>
              </div>
              <div>
                <strong>{summary.error_record_count}</strong>
                <span>error records</span>
              </div>
            </div>
            {categoryCounts.length > 0 && (
              <details className="category-breakdown">
                <summary>Cases by category · {categoryCounts.length}</summary>
                <ul>
                  {categoryCounts.map(([category, count]) => (
                    <li key={category}>
                      <details className="category-cases">
                        <summary>
                          <span>{category.replaceAll("_", " ")}</span>
                          <strong>{count}</strong>
                        </summary>
                        <ul className="eval-case-list">
                          {(summary.case_set.cases ?? [])
                            .filter((item) => item.category === category)
                            .map((item) => (
                              <CaseCard key={item.case_id} item={item} />
                            ))}
                        </ul>
                      </details>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          <section className="evaluation-runs" aria-labelledby="runs-title">
            <div className="coverage-heading">
              <div>
                <p className="eyebrow">LATEST RUN WITH ANSWERS</p>
                <h2 id="runs-title">Agent and baseline run</h2>
              </div>
              {summary.runs.length > 0 && (
                <span className="coverage-summary">
                  Newer retrieval-only re-runs are listed below
                </span>
              )}
            </div>
            {summary.runs.length === 0 ? (
              <div className="empty-state">
                <FileChartColumnIncreasing aria-hidden="true" size={22} />
                <h3>No evaluation runs are recorded.</h3>
                <p>
                  When a run is recorded, its measured metrics and limitations
                  will appear here.
                </p>
              </div>
            ) : (
              <div className="evaluation-run-list">
                <RunCard
                  run={
                    summary.runs.find((run) => !isRetrievalOnlyRun(run)) ??
                    summary.runs[0]
                  }
                />
              </div>
            )}
          </section>
          {(() => {
            const retrievalRun = summary.runs.find(isRetrievalOnlyRun);
            return retrievalRun ? (
              <RetrievalRunPanel run={retrievalRun} />
            ) : null;
          })()}
          <p className="evaluation-footnote">
            Metrics describe recorded runs only. “Not measured” is different
            from zero; read each run’s limitations before comparing results.
          </p>
        </>
      )}
    </div>
  );
}
