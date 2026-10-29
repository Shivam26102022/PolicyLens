import type {
  EvaluationConditionBreakdown,
  EvaluationRunSummary,
} from "../api/client";

const MODE_LABELS: Record<string, string> = {
  bm25: "BM25",
  dense: "Dense",
  hybrid: "Hybrid",
  "hybrid+cross_encoder": "Hybrid + reranker",
};
const MODE_ORDER = ["bm25", "dense", "hybrid", "hybrid+cross_encoder"];

function pct(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "n/a"
    : `${(value * 100).toFixed(1)}%`;
}

function shortDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value.slice(0, 10)
    : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function parseRetrieval(condition: EvaluationConditionBreakdown) {
  const [, chunker, ...mode] = condition.condition_id.split(":");
  return { chunker, mode: mode.join(":") };
}

function retrievalConditions(run: EvaluationRunSummary) {
  return run.condition_breakdowns.filter((item) =>
    item.condition_id.startsWith("retrieval:"),
  );
}

function recallByMode(run: EvaluationRunSummary): Map<string, number> {
  const acc = new Map<string, { sum: number; n: number }>();
  for (const condition of retrievalConditions(run)) {
    const recall = condition.metrics.retrieval_recall_at_k_mean;
    if (recall === null) continue;
    const { mode } = parseRetrieval(condition);
    const entry = acc.get(mode) ?? { sum: 0, n: 0 };
    entry.sum += recall;
    entry.n += 1;
    acc.set(mode, entry);
  }
  return new Map(
    Array.from(acc.entries()).map(([mode, { sum, n }]) => [mode, sum / n]),
  );
}

function Bar({
  value,
  tone,
  label,
}: {
  value: number | null;
  tone: "agent" | "baseline" | "before" | "after" | "rerank";
  label: string;
}) {
  const width = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="insight-bar-row">
      <span className="insight-bar-label">{label}</span>
      <div
        className="insight-bar-track"
        role="img"
        aria-label={`${label}: ${pct(value)}`}
      >
        <div
          className={`insight-bar-fill insight-bar-${tone}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="insight-bar-value">{pct(value)}</span>
    </div>
  );
}

function Kpi({
  value,
  label,
  hint,
}: {
  value: string;
  label: string;
  hint: string;
}) {
  return (
    <div className="insight-kpi">
      <strong>{value}</strong>
      <span>{label}</span>
      <small>{hint}</small>
    </div>
  );
}

export default function EvaluationInsights({
  runs,
}: {
  runs: EvaluationRunSummary[];
}) {
  const agentRun = runs.find(
    (run) =>
      run.metrics.headline_condition_id !== null &&
      !run.condition_breakdowns.every((c) =>
        c.condition_id.startsWith("retrieval:"),
      ),
  );
  const retrievalRuns = runs.filter((run) => retrievalConditions(run).length);
  const latestRetrieval = retrievalRuns[0];
  const earlierRetrieval = retrievalRuns.find(
    (run) =>
      latestRetrieval &&
      run.run_id !== latestRetrieval.run_id &&
      run.started_at < latestRetrieval.started_at,
  );

  const agent = agentRun?.condition_breakdowns.find(
    (c) => c.condition_id === agentRun.metrics.headline_condition_id,
  );
  const baseline = agentRun?.condition_breakdowns.find(
    (c) => c.condition_id === agentRun.metrics.baseline_condition_id,
  );

  const baselineByCategory = new Map(
    (baseline?.category_breakdowns ?? []).map((item) => [
      item.category,
      item.metrics.expected_behavior_accuracy,
    ]),
  );
  const categories = [...(agent?.category_breakdowns ?? [])]
    .filter((item) => item.metrics.expected_behavior_accuracy !== null)
    .sort(
      (left, right) =>
        (left.metrics.expected_behavior_accuracy ?? 0) -
          (right.metrics.expected_behavior_accuracy ?? 0) ||
        right.result_count - left.result_count,
    );
  const failing = categories.filter(
    (item) => (item.metrics.expected_behavior_accuracy ?? 1) < 1,
  );
  const perfect = categories.length - failing.length;

  const latestModes = latestRetrieval ? recallByMode(latestRetrieval) : null;
  const earlierModes = earlierRetrieval ? recallByMode(earlierRetrieval) : null;
  const orderedModes = MODE_ORDER.filter(
    (mode) => latestModes?.has(mode) || earlierModes?.has(mode),
  );

  const rerankByChunker = new Map<
    string,
    { base?: number | null; rerank?: number | null }
  >();
  for (const condition of latestRetrieval
    ? retrievalConditions(latestRetrieval)
    : []) {
    const { chunker, mode } = parseRetrieval(condition);
    if (mode !== "hybrid" && mode !== "hybrid+cross_encoder") continue;
    const entry = rerankByChunker.get(chunker) ?? {};
    if (mode === "hybrid")
      entry.base = condition.metrics.retrieval_recall_at_k_mean;
    else entry.rerank = condition.metrics.retrieval_recall_at_k_mean;
    rerankByChunker.set(chunker, entry);
  }
  const rerankRows = Array.from(rerankByChunker.entries()).filter(
    ([, v]) => v.base != null && v.rerank != null,
  );

  const hybrid = latestModes?.get("hybrid");
  const reranked = latestModes?.get("hybrid+cross_encoder");
  const lift =
    hybrid !== undefined && reranked !== undefined ? reranked - hybrid : null;
  const accuracy = agent?.metrics.expected_behavior_accuracy ?? null;
  const baselineAccuracy = baseline?.metrics.expected_behavior_accuracy ?? null;

  if (!agentRun && !latestRetrieval) return null;

  return (
    <section className="evaluation-insights" aria-labelledby="insights-title">
      <div className="coverage-heading">
        <div>
          <p className="eyebrow">AT A GLANCE</p>
          <h2 id="insights-title">What the evaluation shows</h2>
        </div>
        <span className="coverage-summary">
          Charts read the recorded runs below
        </span>
      </div>

      <div className="insight-kpis">
        {accuracy !== null && (
          <Kpi
            value={pct(accuracy)}
            label="Agent expected behavior"
            hint={`n=${agent?.metrics.expected_behavior_scored_count ?? "?"} cases`}
          />
        )}
        {baselineAccuracy !== null && (
          <Kpi
            value={pct(baselineAccuracy)}
            label="Non-agent baseline"
            hint="same cases, no tools"
          />
        )}
        {reranked !== undefined && (
          <Kpi
            value={pct(reranked)}
            label="Best retrieval recall@6"
            hint="hybrid + reranker, local"
          />
        )}
        {agentRun?.metrics.latency_p50_ms != null && (
          <Kpi
            value={`${(agentRun.metrics.latency_p50_ms / 1000).toFixed(1)}s`}
            label="Latency p50"
            hint={`p95 ${((agentRun.metrics.latency_p95_ms ?? 0) / 1000).toFixed(1)}s`}
          />
        )}
      </div>

      {baseline && (
        <p className="insight-callout">
          <strong>What does the {pct(baselineAccuracy)} baseline mean?</strong>{" "}
          The baseline is the same model answering each question in a single
          call with no tools (no calculator, no data lookup, no abstain guard).{" "}
          {baseline.failed_output_count} of {baseline.result_count} baseline
          calls failed outright and count as wrong, so the baseline is a weak
          floor rather than a fair &quot;best non-agent&quot; score. The gap to
          the agent partly reflects those failures and the different prompts,
          not only the value of tools.
        </p>
      )}

      <div className="insight-grid">
        {latestModes && (
          <article className="insight-card">
            <h3>Retrieval recall@6 by mode, older run vs newest run</h3>
            <p className="insight-note">
              Share of expected evidence anchors found in the top 6 passages,
              averaged over chunkers.
              {earlierRetrieval
                ? ` Orange = run ${earlierRetrieval.run_id.slice(0, 8)} (${shortDate(earlierRetrieval.started_at)}, before the per-source-cap fix). Green = run ${latestRetrieval.run_id.slice(0, 8)} (${shortDate(latestRetrieval.started_at)}, after the fix; the reranker row exists only in this run).`
                : ""}
            </p>
            {orderedModes.map((mode) => (
              <div key={mode} className="insight-group">
                <span className="insight-group-title">
                  {MODE_LABELS[mode] ?? mode}
                </span>
                {earlierModes?.has(mode) && (
                  <Bar
                    value={earlierModes.get(mode) ?? null}
                    tone="before"
                    label={`Run ${shortDate(earlierRetrieval?.started_at ?? "")}`}
                  />
                )}
                {latestModes.has(mode) && (
                  <Bar
                    value={latestModes.get(mode) ?? null}
                    tone={mode.includes("cross") ? "rerank" : "after"}
                    label={`Run ${shortDate(latestRetrieval.started_at)}`}
                  />
                )}
              </div>
            ))}
          </article>
        )}

        {rerankRows.length > 0 && (
          <article className="insight-card">
            <h3>With vs without the reranker</h3>
            <p className="insight-note">
              Same retrieval run, per chunking strategy. The reranker is local
              only; production runs without it.
              {lift !== null &&
                ` Average lift: ${lift >= 0 ? "+" : ""}${(lift * 100).toFixed(1)} points.`}
            </p>
            {rerankRows.map(([chunker, value]) => (
              <div key={chunker} className="insight-group">
                <span className="insight-group-title">{chunker}</span>
                <Bar value={value.base ?? null} tone="after" label="Hybrid" />
                <Bar
                  value={value.rerank ?? null}
                  tone="rerank"
                  label="+ Reranker"
                />
              </div>
            ))}
          </article>
        )}
      </div>

      {categories.length > 0 && (
        <article className="insight-card insight-card-wide">
          <h3>Edge cases: agent vs baseline by category</h3>
          <p className="insight-note">
            Expected-behavior accuracy per case category, weakest first.{" "}
            {perfect} of {categories.length} categories are at 100%; the rest
            need attention. Small categories (n=1 to 2) are descriptive only.
          </p>
          <div className="insight-category-list">
            {categories.map((item) => (
              <div key={item.category} className="insight-category">
                <span className="insight-group-title">
                  {item.category.replaceAll("_", " ")}
                  <small> n={item.result_count}</small>
                </span>
                <Bar
                  value={item.metrics.expected_behavior_accuracy}
                  tone="agent"
                  label="Agent"
                />
                {baselineByCategory.has(item.category) && (
                  <Bar
                    value={baselineByCategory.get(item.category) ?? null}
                    tone="baseline"
                    label="Baseline"
                  />
                )}
              </div>
            ))}
          </div>
        </article>
      )}

      <article className="insight-card insight-card-wide">
        <h3>How to read these charts</h3>
        <dl className="insight-glossary">
          <dt>Expected behavior</dt>
          <dd>
            Whether the response type (answer, abstain, ask to clarify, flag a
            conflict, block) matched what the test case required. It does not
            check that the answer text is factually right.
          </dd>
          <dt>Recall@6</dt>
          <dd>
            For each question, the share of the known evidence locations
            (&quot;anchors&quot;: a table row or a PDF page) that appear in the
            top 6 retrieved passages.
          </dd>
          <dt>Hybrid / Dense / BM25</dt>
          <dd>
            BM25 matches keywords, dense matches meaning using embeddings,
            hybrid combines both.
          </dd>
          <dt>Reranker</dt>
          <dd>
            A cross-encoder that re-scores the top candidates against the
            question. Slower, so it is on locally and off on Vercel.
          </dd>
          <dt>Categories (edge cases)</dt>
          <dd>
            Groups of test cases such as unanswerable questions, prompt
            injection, conflicting sources or bad tool arguments. Categories
            with only 1 to 3 cases are descriptive, not statistically firm.
          </dd>
        </dl>
      </article>

      <article className="insight-card insight-card-wide">
        <h3>Key takeaways</h3>
        <ul className="insight-takeaways">
          {accuracy !== null && baselineAccuracy !== null && (
            <li>
              The agent beats the no-tool baseline by{" "}
              <strong>
                {((accuracy - baselineAccuracy) * 100).toFixed(1)} points
              </strong>{" "}
              on expected behavior ({pct(accuracy)} vs {pct(baselineAccuracy)}).
            </li>
          )}
          {failing.length > 0 && (
            <li>
              Weakest categories:{" "}
              {failing
                .slice(0, 4)
                .map((item) => item.category.replaceAll("_", " "))
                .join(", ")}
              . These are the edge cases to improve next.
            </li>
          )}
          {lift !== null && (
            <li>
              The cross-encoder reranker adds{" "}
              <strong>{(lift * 100).toFixed(1)} points</strong> of recall@6 over
              hybrid, mostly on narrative PDF pages; table rows are already at
              ceiling.
            </li>
          )}
          {earlierModes?.has("hybrid") && latestModes?.has("hybrid") && (
            <li>
              Fixing the per-source passage cap raised hybrid recall@6 from{" "}
              {pct(earlierModes.get("hybrid"))} to{" "}
              {pct(latestModes.get("hybrid"))} without changing the data.
            </li>
          )}
          <li>
            Agent accuracy, evidence completeness and judge scores come from the
            earlier generation run; they have not been regenerated since the
            retrieval fix.
          </li>
        </ul>
      </article>
    </section>
  );
}
