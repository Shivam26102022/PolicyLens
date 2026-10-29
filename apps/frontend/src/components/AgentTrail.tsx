import {
  ChevronDown,
  Circle,
  Check,
  CircleAlert,
  LoaderCircle,
  Network,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";

import type {
  AgentProgressEvent,
  ModelRunMetadata,
  ModelRoute,
  ModelUsage,
} from "../api/client";

interface AgentTrailProps {
  events: AgentProgressEvent[];
  isRunning: boolean;
  hasRun: boolean;
  embedded?: boolean;
  modelMetadata?: ModelRunMetadata | null;
}

function aggregateEventUsage(events: AgentProgressEvent[]): ModelUsage | null {
  const usages = events
    .filter((event) => event.event_type === "model_completed")
    .map((event) => event.model_usage)
    .filter(
      (usage): usage is ModelUsage => usage !== null && usage !== undefined,
    );
  if (usages.length === 0) return null;

  const sum = (field: keyof ModelUsage): number | null => {
    const values = usages.map((usage) => usage[field]);
    if (values.length === 0) return null;
    let total = 0;
    for (const value of values) {
      if (typeof value !== "number") return null;
      total += value;
    }
    return total;
  };

  return {
    requests: sum("requests"),
    prompt_tokens: sum("prompt_tokens"),
    completion_tokens: sum("completion_tokens"),
    total_tokens: sum("total_tokens"),
    cached_input_tokens: sum("cached_input_tokens"),
    reasoning_tokens: sum("reasoning_tokens"),
  };
}

function tokenLabel(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "Not reported"
    : new Intl.NumberFormat().format(value);
}

function routeLabel(route: ModelRoute | null): string {
  if (route === "openai_responses") return "OpenAI Responses API";
  if (route === "openai_chat_completions") return "OpenAI Chat Completions";
  if (route === "mlx_chat_completions") return "Local MLX Chat Completions";
  return "Route not recorded";
}

function stepLabel(event: AgentProgressEvent): string {
  if (event.event_type === "mcp_resource_started")
    return "Loading retrieved passages from Policy Data MCP";
  if (event.event_type === "mcp_resource_completed") {
    return event.status === "failed"
      ? "Policy Data MCP passage lookup failed"
      : "Passages verified by Policy Data MCP";
  }
  if (event.event_type === "reranking_completed") {
    return event.status === "failed"
      ? "Cross-encoder reranking unavailable; hybrid order retained"
      : "Cross-encoder reranked candidates";
  }
  if (event.event_type === "tool_started") return "Statistics query started";
  if (event.event_type === "tool_completed") {
    return event.status === "failed"
      ? "Statistics query failed"
      : event.status === "skipped"
        ? "Statistics query skipped"
        : "Statistics query completed";
  }
  if (event.status === "failed" && event.event_type === "model_completed")
    return "Model processing failed";
  if (event.status === "failed" && event.event_type === "citations_validated")
    return "Citation validation failed";

  const states: Record<string, string> = {
    received: "Request received",
    validated: "Request validated",
    retrieving: "Searching policy evidence",
    assessing: "Assessing evidence",
    tool_execution: "Calling the policy data server",
    output_validation: "Checking answer format",
    citation_validation: "Checking citations",
    answered: "Answer ready",
    clarification_required: "Clarification needed",
    abstained: "Insufficient evidence",
    conflict: "Evidence conflict found",
    blocked: "Request blocked safely",
    failed_safe: "Run stopped safely",
  };
  const labels: Record<string, string> = {
    session_context_loaded: "Loaded this chat's recent context",
    memory_retrieval_completed: "Checked long-term memory",
    session_turn_persisted: "Saved this chat turn",
    memory_write_completed: "Updated long-term memory",
    retrieval_completed: "Evidence search completed",
    reranking_completed: "Cross-encoder reranking completed",
    model_started: "Model started",
    model_completed: "Model finished",
    output_validated: "Answer format validated",
    citations_validated: "Citations validated",
    terminal: "Run finished",
  };
  return event.event_type === "state_transition"
    ? (states[event.state] ?? "Processing request")
    : (labels[event.event_type] ?? "Processing request");
}

type DisplayStatus = AgentProgressEvent["status"] | "finished" | "ended";

function displayStatus(
  event: AgentProgressEvent,
  events: AgentProgressEvent[],
  isRunning: boolean,
): DisplayStatus {
  if (event.status !== "started") return event.status;

  const completionType =
    event.event_type === "tool_started"
      ? "tool_completed"
      : event.event_type === "mcp_resource_started"
        ? "mcp_resource_completed"
        : event.event_type === "model_started"
          ? "model_completed"
          : null;
  const hasCompletion =
    completionType !== null &&
    events.some(
      (candidate) =>
        candidate.event_type === completionType &&
        candidate.sequence > event.sequence &&
        (event.event_type !== "tool_started" ||
          candidate.tool_name === event.tool_name),
    );

  if (hasCompletion) return "finished";
  return isRunning ? "started" : "ended";
}

function stepCategory(event: AgentProgressEvent): string {
  if (event.event_type.startsWith("tool_")) return "MCP SERVER";
  if (event.event_type.startsWith("mcp_resource_")) return "MCP SERVER";
  if (event.event_type.startsWith("memory_")) return "CHAT MEMORY";
  if (
    event.event_type === "reranking_completed" ||
    event.event_type === "retrieval_completed" ||
    event.state === "retrieving"
  )
    return "EVIDENCE RETRIEVAL";
  if (event.event_type.startsWith("model_")) return "MODEL";
  return "AGENT";
}

function stepStatus(status: DisplayStatus): string {
  const labels: Record<DisplayStatus, string> = {
    started: "In progress",
    finished: "Finished",
    ended: "Run ended",
    succeeded: "Complete",
    failed: "Failed",
    skipped: "Skipped",
  };
  return labels[status];
}

function itemSummary(event: AgentProgressEvent): string | null {
  if (event.item_count === null || event.item_count === undefined) return null;
  if (event.event_type === "mcp_resource_completed") {
    const label = event.item_count === 1 ? "passage" : "passages";
    return `${event.item_count} ${label} verified`;
  }
  if (event.event_type === "memory_retrieval_completed")
    return `${event.item_count} memories considered`;
  if (event.event_type === "memory_write_completed")
    return `${event.item_count} memories saved`;
  if (event.event_type === "retrieval_completed")
    return `${event.item_count} evidence items`;
  if (event.event_type === "reranking_completed")
    return `${event.item_count} candidates scored`;
  return `${event.item_count} items`;
}

function summaryStepLabel(event: AgentProgressEvent): string | null {
  if (event.status === "skipped") return null;
  switch (event.event_type) {
    case "retrieval_completed":
      return event.status === "failed"
        ? "Evidence search failed"
        : "Evidence search completed";
    case "reranking_completed":
      return event.status === "failed"
        ? "Cross-encoder reranking unavailable"
        : "Cross-encoder reranking completed";
    case "tool_completed":
    case "model_completed":
      return stepLabel(event);
    case "mcp_resource_completed":
      return event.status === "failed"
        ? "MCP passage lookup failed"
        : "MCP passages verified";
    case "output_validated":
      return event.status === "failed"
        ? "Answer format check failed"
        : "Answer format checked";
    case "citations_validated":
      return event.status === "failed"
        ? "Citation check failed"
        : "Citations checked";
    case "memory_retrieval_completed":
      return event.status === "failed"
        ? "Long-term memory unavailable"
        : "Long-term memory checked";
    case "memory_write_completed":
      return event.status === "failed"
        ? "Long-term memory update failed"
        : "Long-term memory updated";
    default:
      return null;
  }
}

function processingSummary(
  events: AgentProgressEvent[],
  hasRun: boolean,
): string {
  const stages = [
    ...new Set(
      events
        .map(summaryStepLabel)
        .filter((label): label is string => label !== null),
    ),
  ].slice(0, 4);
  if (stages.length > 0) return stages.join(" · ");
  return hasRun
    ? "No processing events were recorded."
    : "No saved activity is available for this message.";
}

function mcpStatus(
  events: AgentProgressEvent[],
  isRunning: boolean,
  hasRun: boolean,
): string {
  const calls = events.filter(
    (event) =>
      event.event_type.startsWith("tool_") ||
      event.event_type.startsWith("mcp_resource_"),
  );
  const latest = calls[calls.length - 1];
  if (!latest) {
    if (isRunning) return "Not called yet";
    return hasRun ? "Not needed this run" : "Called when needed";
  }
  if (latest.status === "started")
    return isRunning ? "In progress" : "Run ended";
  if (latest.status === "failed") return "Failed";
  if (latest.status === "skipped") return "Skipped";
  return "Completed";
}

function stepErrorExplanation(event: AgentProgressEvent): string | null {
  if (
    event.tool_name !== "query_statistics" ||
    event.error_code !== "TOOL_INVALID_ARGUMENTS"
  ) {
    return null;
  }
  return (
    "The statistics tool requires a supported indicator, 1 to 4 unique uppercase " +
    "ISO3 geographies, years from 2015 to 2025 with start year no later than end " +
    "year, valid aggregation/grouping, and a row limit from 1 to 44. Add a " +
    "geography if the question has none. Raw arguments are hidden, so this event " +
    "does not identify the exact invalid field."
  );
}

export default function AgentTrail({
  events,
  isRunning,
  hasRun,
  embedded = false,
  modelMetadata = null,
}: AgentTrailProps) {
  const hasFailure = events.some((event) => event.status === "failed");
  const integrationStatus = mcpStatus(events, isRunning, hasRun);
  const trailStatus = isRunning
    ? "In progress"
    : hasFailure
      ? "Needs attention"
      : hasRun
        ? "Complete"
        : "Ready";
  const modelEvents = events.filter((event) =>
    event.event_type.startsWith("model_"),
  );
  const lastModelEvent = modelEvents[modelEvents.length - 1];
  const modelRoute =
    modelMetadata?.capabilities.route ?? lastModelEvent?.model_route ?? null;
  const reasoningEffort =
    modelMetadata?.reasoning_effort ?? lastModelEvent?.reasoning_effort ?? null;
  const metadataHasUsage = Object.entries(modelMetadata?.usage ?? {}).some(
    ([field, value]) => field !== "requests" && typeof value === "number",
  );
  const modelUsage =
    metadataHasUsage && modelMetadata
      ? modelMetadata.usage
      : aggregateEventUsage(events);
  const reasoningSummary =
    modelMetadata?.reasoning_summary ||
    [
      ...new Set(
        events
          .map((event) => event.reasoning_summary)
          .filter((summary): summary is string => Boolean(summary?.trim())),
      ),
    ].join("\n\n");
  const hasModelActivity = modelMetadata !== null || modelEvents.length > 0;
  const missingSummaryMessage =
    modelRoute === "openai_chat_completions"
      ? "This Chat Completions route does not provide the Responses API reasoning summary. Enable Responses API only if the configured deployment supports it."
      : reasoningEffort === "none"
        ? "Reasoning effort was set to none, so no reasoning summary was requested."
        : "The provider did not return a reasoning summary for this run.";
  const eventContent =
    events.length > 0 ? (
      <ol
        aria-live="polite"
        aria-label="Agent processing steps"
        className="agent-trail-list"
        aria-relevant="additions text"
      >
        {events.map((event) => {
          const status = displayStatus(event, events, isRunning);
          const Icon =
            status === "failed"
              ? CircleAlert
              : status === "started"
                ? LoaderCircle
                : status === "ended"
                  ? Circle
                  : Check;
          const itemCount = itemSummary(event);
          const errorExplanation = stepErrorExplanation(event);
          return (
            <li
              className={`agent-trail-step step-${status}`}
              key={`${event.sequence}-${event.event_type}`}
            >
              <span className="agent-step-icon">
                <Icon
                  aria-hidden="true"
                  className={status === "started" ? "spin" : undefined}
                  size={15}
                />
              </span>
              <div className="agent-step-content">
                <span className="trail-kicker">{stepCategory(event)}</span>
                <strong>{stepLabel(event)}</strong>
                <div className="agent-step-meta">
                  <span>{stepStatus(status)}</span>
                  {event.duration_ms !== null && (
                    <span>{Math.round(event.duration_ms)} ms</span>
                  )}
                  {event.retry_count > 0 && (
                    <span>
                      {event.retry_count}{" "}
                      {event.retry_count === 1 ? "retry" : "retries"}
                    </span>
                  )}
                  {itemCount && <span>{itemCount}</span>}
                  {event.reranker_model && (
                    <span>Model: {event.reranker_model}</span>
                  )}
                </div>
                {event.error_code && (
                  <>
                    <code className="agent-step-error">{event.error_code}</code>
                    {errorExplanation && (
                      <p className="agent-step-error-explanation">
                        {errorExplanation}
                      </p>
                    )}
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    ) : (
      <div className="agent-trail-empty">
        <ShieldCheck aria-hidden="true" size={18} />
        <p>
          {embedded
            ? hasRun
              ? "No processing events were recorded for this answer."
              : "No saved processing activity is available for this message."
            : isRunning
              ? "Preparing the run. Steps will appear here."
              : hasRun
                ? "No extra tool calls were needed for the latest answer."
                : "Ask a question to see how evidence and approved tools are used."}
        </p>
      </div>
    );

  if (embedded) {
    return (
      <details className="answer-agent-trail" open>
        <summary className="answer-agent-trail-summary">
          <span className="answer-agent-trail-copy">
            <strong>How this answer was prepared</strong>
            <span>{processingSummary(events, hasRun)}</span>
          </span>
          <span className={`trail-status${hasFailure ? " has-failure" : ""}`}>
            {trailStatus}
          </span>
          <span aria-hidden="true" className="answer-agent-trail-toggle">
            <ChevronDown size={15} />
          </span>
        </summary>
        <div className="answer-agent-trail-content">
          <p className="agent-trail-intro">
            Operational processing steps, provider-reported token counts, and
            the provider-generated reasoning summary. Private reasoning text and
            raw tool inputs are not shown.
          </p>
          {hasModelActivity && (
            <section
              aria-label="Model usage and reasoning"
              className="model-run-details"
            >
              <h3>Model usage and reasoning</h3>
              <div className="model-run-facts">
                <div>
                  <span>API route</span>
                  <strong>{routeLabel(modelRoute)}</strong>
                </div>
                <div>
                  <span>Reasoning effort</span>
                  <strong>
                    {reasoningEffort
                      ? reasoningEffort[0].toUpperCase() +
                        reasoningEffort.slice(1)
                      : "Not reported"}
                  </strong>
                </div>
              </div>
              {modelUsage ? (
                <>
                  <dl className="model-token-usage">
                    <div>
                      <dt>Requests</dt>
                      <dd>{tokenLabel(modelUsage.requests)}</dd>
                    </div>
                    <div>
                      <dt>Input tokens</dt>
                      <dd>{tokenLabel(modelUsage.prompt_tokens)}</dd>
                    </div>
                    <div>
                      <dt>Output tokens</dt>
                      <dd>{tokenLabel(modelUsage.completion_tokens)}</dd>
                    </div>
                    <div>
                      <dt>Reasoning tokens</dt>
                      <dd>{tokenLabel(modelUsage.reasoning_tokens)}</dd>
                    </div>
                    <div>
                      <dt>Cached input</dt>
                      <dd>{tokenLabel(modelUsage.cached_input_tokens)}</dd>
                    </div>
                    <div>
                      <dt>Total tokens</dt>
                      <dd>{tokenLabel(modelUsage.total_tokens)}</dd>
                    </div>
                  </dl>
                  <p className="model-usage-note">
                    Provider-reported usage. Reasoning tokens are part of output
                    tokens; cached input is part of input tokens.
                  </p>
                </>
              ) : (
                <p className="model-usage-note">
                  The provider did not report token usage for this run.
                </p>
              )}
              <div className="model-reasoning-summary">
                <h4>SDK reasoning summary</h4>
                {reasoningSummary ? (
                  <p>{reasoningSummary}</p>
                ) : (
                  <p>{missingSummaryMessage}</p>
                )}
              </div>
            </section>
          )}
          {eventContent}
        </div>
      </details>
    );
  }

  return (
    <section aria-labelledby="agent-trail-title" className="agent-trail-panel">
      <header className="agent-trail-heading">
        <div>
          <p className="eyebrow">SAFE RUN VISIBILITY</p>
          <h2 id="agent-trail-title">Agent trail</h2>
        </div>
        <span
          className={`trail-status${isRunning ? " is-running" : ""}${hasFailure ? " has-failure" : ""}`}
          role="status"
        >
          {isRunning && (
            <LoaderCircle aria-hidden="true" className="spin" size={13} />
          )}
          {trailStatus}
        </span>
      </header>
      <p className="agent-trail-intro">
        Follow retrieval, approved MCP calls, model activity, and validation.
        Private reasoning and raw tool inputs stay hidden.
      </p>

      <article className="mcp-integration-card">
        <div className="mcp-integration-icon">
          <Network aria-hidden="true" size={17} />
        </div>
        <div className="mcp-integration-copy">
          <span className="trail-kicker">MCP INTEGRATION</span>
          <strong>PolicyLens Policy Data Server</strong>
          <span>
            Read-only passage resources and statistics · called when needed
          </span>
        </div>
        <span
          className={`mcp-run-status${integrationStatus === "Failed" ? " has-failure" : ""}`}
        >
          {integrationStatus}
        </span>
        <Link className="mcp-status-link" to="/status">
          Check service status
        </Link>
      </article>

      {eventContent}
    </section>
  );
}
