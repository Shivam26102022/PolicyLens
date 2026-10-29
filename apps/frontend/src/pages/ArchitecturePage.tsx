import { ArrowDownRight, ArrowUpRight, LockKeyhole } from "lucide-react";
import { useState } from "react";

import AgentStateMachine from "../components/AgentStateMachine";
import ArchitectureDiagram from "../components/ArchitectureDiagram";
import PlatformCoverage from "../components/PlatformCoverage";
import RagPipeline from "../components/RagPipeline";
import {
  architectureLayers,
  type ImplementationStatus,
} from "../data/architecture";

function StatusBadge({ status }: { status: ImplementationStatus }) {
  const labels: Record<ImplementationStatus, string> = {
    implemented: "Implemented",
    configured: "Configured",
    planned: "Planned",
    unavailable: "Unavailable",
  };
  return (
    <span className={`architecture-status status-${status}`}>
      {labels[status]}
    </span>
  );
}

export default function ArchitecturePage() {
  const [selectedId, setSelectedId] = useState(architectureLayers[0]?.id ?? "");
  const selectedLayer = architectureLayers.find(
    (layer) => layer.id === selectedId,
  );

  return (
    <div className="architecture-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">SYSTEM GUIDE / TRUST BOUNDARIES</p>
          <h1>Architecture</h1>
          <p className="page-description">
            Follow an agentic RAG request end to end: the offline ingestion and
            index build, hot and warm memory, hybrid retrieval with reranking,
            MCP passage verification, the bounded agent loop, MCP tool calls,
            and citation and number checks. Select a layer to inspect its role.
          </p>
        </div>
      </section>

      <ArchitectureDiagram
        layers={architectureLayers}
        onSelect={setSelectedId}
        selectedId={selectedId}
      />

      <RagPipeline />

      <AgentStateMachine />

      <PlatformCoverage />

      <div className="architecture-explorer">
        <nav
          aria-label="Architecture layers"
          className="architecture-layer-list"
        >
          {architectureLayers.map((layer, index) => (
            <button
              aria-pressed={selectedId === layer.id}
              className={`architecture-layer-button${selectedId === layer.id ? " is-selected" : ""}`}
              key={layer.id}
              onClick={() => setSelectedId(layer.id)}
              type="button"
            >
              <span className="layer-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="layer-button-copy">
                <span className="layer-button-title">{layer.title}</span>
                <StatusBadge status={layer.implementationStatus} />
              </span>
              {selectedId === layer.id ? (
                <ArrowUpRight aria-hidden="true" size={16} />
              ) : (
                <ArrowDownRight aria-hidden="true" size={16} />
              )}
            </button>
          ))}
        </nav>

        {selectedLayer && (
          <article aria-live="polite" className="architecture-detail">
            <div className="architecture-detail-heading">
              <span className="architecture-detail-index">
                LAYER{" "}
                {String(
                  architectureLayers.findIndex(
                    (layer) => layer.id === selectedLayer.id,
                  ) + 1,
                ).padStart(2, "0")}
              </span>
              <span className="architecture-short-label">
                {selectedLayer.shortLabel}
              </span>
              <StatusBadge status={selectedLayer.implementationStatus} />
            </div>
            <h2>{selectedLayer.title}</h2>
            <p className="architecture-description">
              {selectedLayer.description}
            </p>

            <div className="architecture-io">
              <section>
                <h3>Inputs</h3>
                <ul>
                  {selectedLayer.inputs.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
              <section>
                <h3>Outputs</h3>
                <ul>
                  {selectedLayer.outputs.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            </div>

            <div className="trust-boundary-note">
              <LockKeyhole aria-hidden="true" size={16} />
              <div>
                <h3>Trust boundary</h3>
                <p>{selectedLayer.trustBoundary}</p>
              </div>
            </div>

            <div className="architecture-references">
              <h3>Project references</h3>
              <ul>
                {selectedLayer.references.map((reference) => (
                  <li key={reference}>
                    <code>{reference}</code>
                  </li>
                ))}
              </ul>
            </div>
          </article>
        )}
      </div>

      <p className="architecture-footnote">
        Layer status describes this local assessment implementation. Provider
        availability depends on backend configuration; no claim of model parity
        or general prompt-injection prevention is made.
      </p>
    </div>
  );
}
