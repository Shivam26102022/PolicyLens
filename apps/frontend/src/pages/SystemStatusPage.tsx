import { useEffect, useState } from "react";
import { Activity, CircleAlert, Cpu, Database, Network } from "lucide-react";

import { getReadiness, type ServiceHealth } from "../api/client";
import { useWorkbench } from "../state/WorkbenchContext";

type ComponentStatus = ServiceHealth["components"][string];

const statusLabels: Record<ComponentStatus, string> = {
  ready: "Ready",
  degraded: "Degraded",
  not_configured: "Not configured",
  unavailable: "Unavailable",
};

const componentDetails: Record<
  string,
  { label: string; icon: typeof Activity; description: string }
> = {
  api: {
    label: "Backend API",
    icon: Activity,
    description: "Accepts typed requests and validates run boundaries.",
  },
  generation: {
    label: "Generation",
    icon: Cpu,
    description: "Uses the selected backend-configured model when available.",
  },
  embedding: {
    label: "Embeddings",
    icon: Database,
    description: "Identifies the configured embedding component.",
  },
  retrieval: {
    label: "Retrieval index",
    icon: Database,
    description: "Searches the active local evidence index.",
  },
  mcp: {
    label: "MCP tools",
    icon: Network,
    description: "Connects to the configured read-only policy-data service.",
  },
};

export default function SystemStatusPage() {
  const { modelOptionsError } = useWorkbench();
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    getReadiness(controller.signal)
      .then(setHealth)
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Backend readiness is unavailable.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const components = health?.components ?? {};
  const statuses: Array<[string, ComponentStatus]> = Object.entries(
    components,
  ).filter(
    (entry): entry is [string, ComponentStatus] => entry[1] in statusLabels,
  );

  return (
    <div className="system-status-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">OPERATIONS / LOCAL COMPONENTS</p>
          <h1>System status</h1>
          <p className="page-description">
            Safe readiness summaries for configured backend components.
          </p>
        </div>
      </section>

      {loading && (
        <p className="evaluation-state" role="status">
          Checking backend readiness…
        </p>
      )}
      {(error || modelOptionsError) && (
        <p className="inline-alert evaluation-state" role="alert">
          <CircleAlert aria-hidden="true" size={16} />
          {error ?? modelOptionsError}
        </p>
      )}
      {health && (
        <div className="service-summary" role="status">
          <span
            className={`run-badge run-badge-${health.status === "ready" ? "completed" : health.status === "degraded" ? "degraded" : "failed"}`}
          >
            {health.status
              .replaceAll("_", " ")
              .replace(/\b\w/g, (letter) => letter.toUpperCase())}
          </span>
          <span>PolicyLens API · {health.version}</span>
        </div>
      )}
      {health?.status === "degraded" && (
        <p className="status-degraded-note" role="note">
          Some components need attention. Components marked Ready remain
          available.
        </p>
      )}
      {!loading && statuses.length > 0 && (
        <section
          aria-label="Component readiness"
          className="component-status-list"
        >
          {statuses.map(([key, status]) => {
            const detail = componentDetails[key] ?? {
              label: key
                .replaceAll("_", " ")
                .replace(/\b\w/g, (letter) => letter.toUpperCase()),
              icon: Activity,
              description: "Configured service component.",
            };
            const Icon = detail.icon;
            return (
              <article className="component-status-row" key={key}>
                <Icon
                  aria-hidden="true"
                  className="component-status-icon"
                  size={19}
                />
                <div className="component-status-copy">
                  <h2>{detail.label}</h2>
                  <p>{detail.description}</p>
                </div>
                <span className={`component-status-value component-${status}`}>
                  {statusLabels[status]}
                </span>
              </article>
            );
          })}
        </section>
      )}
      <p className="status-footnote">
        Status is a momentary readiness check. It does not disclose service
        paths, credentials, or provider-side health.
      </p>
    </div>
  );
}
