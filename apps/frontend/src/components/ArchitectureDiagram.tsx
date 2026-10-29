import { Pause, Play, Radio } from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import type { ArchitectureLayer } from "../data/architecture";

type Zone =
  "BROWSER" | "BACKEND" | "LOCAL STORE" | "MCP PROCESS" | "MODEL" | "OFFLINE";

interface NodeSpec {
  id: string;
  col: number;
  row: "A" | "B" | "C";
  zone: Zone;
  tech: string;
}

interface EdgeSpec {
  id: string;
  from: string;
  to: string;
  kind: "main" | "aux" | "memory" | "mcp";
  label: string;
  reverseLabel?: string;
  dxFrom?: number;
  dxTo?: number;
  arc?: boolean;
  hidden?: boolean;
}

const NODE_W = 190;
const NODE_H = 86;
const COL_X = [30, 275, 520, 765];
const ROW_Y = { A: 62, B: 238, C: 414 };
const EVAL_Y = 596;

const ZONE_COLOR: Record<Zone, string> = {
  BROWSER: "#60a5fa",
  BACKEND: "#5eead4",
  "LOCAL STORE": "#c084fc",
  "MCP PROCESS": "#f472b6",
  MODEL: "#fbbf24",
  OFFLINE: "#fb923c",
};

const NODES: NodeSpec[] = [
  {
    id: "web-interface",
    col: 0,
    row: "A",
    zone: "BROWSER",
    tech: "React · Vite · SSE trail",
  },
  {
    id: "api-guardrails",
    col: 1,
    row: "A",
    zone: "BACKEND",
    tech: "FastAPI · consent · session",
  },
  {
    id: "hot-memory",
    col: 2,
    row: "A",
    zone: "LOCAL STORE",
    tech: "SQLite · last 5 turns",
  },
  {
    id: "warm-memory",
    col: 3,
    row: "A",
    zone: "LOCAL STORE",
    tech: "Chroma · top-5 recall",
  },
  {
    id: "ingestion-indexing",
    col: 0,
    row: "B",
    zone: "OFFLINE",
    tech: "parse · chunk · embed · hash",
  },
  {
    id: "evidence-validation",
    col: 1,
    row: "B",
    zone: "BACKEND",
    tech: "citations · number guard",
  },
  {
    id: "agent-runtime",
    col: 2,
    row: "B",
    zone: "BACKEND",
    tech: "state machine · repair turns",
  },
  {
    id: "model-gateway",
    col: 3,
    row: "B",
    zone: "MODEL",
    tech: "OpenAI Agents SDK · MLX",
  },
  {
    id: "run-memory",
    col: 0,
    row: "C",
    zone: "BACKEND",
    tech: "ledger · budgets · events",
  },
  {
    id: "retrieval-index",
    col: 1,
    row: "C",
    zone: "LOCAL STORE",
    tech: "BM25S · dense · rerank",
  },
  {
    id: "runtime-tools",
    col: 2,
    row: "C",
    zone: "BACKEND",
    tech: "validated · budgeted calls",
  },
  {
    id: "mcp-server",
    col: 3,
    row: "C",
    zone: "MCP PROCESS",
    tech: "stdio · tool · resource",
  },
];

const EDGES: EdgeSpec[] = [
  {
    id: "e1",
    from: "web-interface",
    to: "api-guardrails",
    kind: "main",
    label: "POST",
    reverseLabel: "SSE",
  },
  {
    id: "e2",
    from: "api-guardrails",
    to: "hot-memory",
    kind: "memory",
    label: "load",
    reverseLabel: "save",
  },
  {
    id: "e3",
    from: "api-guardrails",
    to: "warm-memory",
    kind: "memory",
    label: "top-5 recall · write-back",
    arc: true,
  },
  {
    id: "e4",
    from: "api-guardrails",
    to: "agent-runtime",
    kind: "main",
    label: "query + memory ctx",
  },
  {
    id: "e5",
    from: "agent-runtime",
    to: "retrieval-index",
    kind: "main",
    label: "search",
    reverseLabel: "evidence",
    dxFrom: -50,
    dxTo: 30,
  },
  {
    id: "e15",
    from: "ingestion-indexing",
    to: "retrieval-index",
    kind: "main",
    label: "indexes",
  },
  {
    id: "e8",
    from: "agent-runtime",
    to: "model-gateway",
    kind: "aux",
    label: "prompt",
    reverseLabel: "draft",
  },
  {
    id: "e9",
    from: "agent-runtime",
    to: "runtime-tools",
    kind: "aux",
    label: "call",
    reverseLabel: "result",
    dxFrom: -10,
    dxTo: -10,
  },
  {
    id: "e10",
    from: "runtime-tools",
    to: "mcp-server",
    kind: "mcp",
    label: "args",
    reverseLabel: "output",
  },
  {
    id: "e14",
    from: "agent-runtime",
    to: "mcp-server",
    kind: "mcp",
    label: "verify",
    reverseLabel: "passage",
    dxFrom: 62,
    dxTo: -45,
  },
  {
    id: "e11",
    from: "agent-runtime",
    to: "run-memory",
    kind: "aux",
    label: "events",
    hidden: true,
    dxFrom: -75,
    dxTo: 30,
  },
  {
    id: "e12",
    from: "agent-runtime",
    to: "evidence-validation",
    kind: "main",
    label: "typed draft",
  },
  {
    id: "e13",
    from: "evidence-validation",
    to: "api-guardrails",
    kind: "main",
    label: "cited answer",
  },
];

const MAIN_PATH_IDS = ["e1", "e4", "e5", "e12", "e13"];

const TRACE = [
  "web-interface",
  "api-guardrails",
  "hot-memory",
  "warm-memory",
  "agent-runtime",
  "ingestion-indexing",
  "retrieval-index",
  "mcp-server",
  "model-gateway",
  "runtime-tools",
  "mcp-server",
  "run-memory",
  "evidence-validation",
  "api-guardrails",
  "evaluation-observability",
];

function nodeBox(spec: NodeSpec) {
  return { x: COL_X[spec.col], y: ROW_Y[spec.row], w: NODE_W, h: NODE_H };
}

function find(id: string) {
  return NODES.find((n) => n.id === id);
}

function reversed(edge: EdgeSpec): EdgeSpec {
  return {
    ...edge,
    from: edge.to,
    to: edge.from,
    label: edge.reverseLabel ?? "",
    dxFrom: edge.dxTo,
    dxTo: edge.dxFrom,
  };
}

function edgePath(edge: EdgeSpec, lane = 0): string {
  const from = find(edge.from);
  const to = find(edge.to);
  if (!from || !to) return "";
  const a = nodeBox(from);
  const b = nodeBox(to);
  if (edge.arc) {
    const x1 = a.x + a.w / 2;
    const x2 = b.x + b.w / 2;
    return `M ${x1} ${a.y} L ${x1} 30 L ${x2} 30 L ${x2} ${b.y}`;
  }
  if (from.row === to.row) {
    const y = a.y + a.h / 2 + lane;
    return a.x < b.x
      ? `M ${a.x + a.w} ${y} L ${b.x} ${y}`
      : `M ${a.x} ${y} L ${b.x + b.w} ${y}`;
  }
  const down = b.y > a.y;
  const x1 = a.x + a.w / 2 + (edge.dxFrom ?? 0) + lane;
  const x2 = b.x + b.w / 2 + (edge.dxTo ?? 0) + lane;
  const y1 = down ? a.y + a.h : a.y;
  const y2 = down ? b.y : b.y + b.h;
  const k = Math.abs(y2 - y1) * 0.5;
  const s = down ? 1 : -1;
  return `M ${x1} ${y1} C ${x1} ${y1 + s * k}, ${x2} ${y2 - s * k}, ${x2} ${y2}`;
}

function labelPos(edge: EdgeSpec, lane = 0): { x: number; y: number } {
  const from = find(edge.from);
  const to = find(edge.to);
  if (!from || !to) return { x: 0, y: 0 };
  const a = nodeBox(from);
  const b = nodeBox(to);
  if (edge.arc) {
    return { x: (a.x + b.x + a.w) / 2 + 40, y: 24 };
  }
  if (from.row === to.row) {
    const mid = a.x < b.x ? (a.x + a.w + b.x) / 2 : (b.x + b.w + a.x) / 2;
    return { x: mid, y: a.y + a.h / 2 + lane + (lane > 0 ? 14 : -7) };
  }
  const x1 = a.x + a.w / 2 + (edge.dxFrom ?? 0);
  const x2 = b.x + b.w / 2 + (edge.dxTo ?? 0);
  const down = b.y > a.y;
  const yMid = down ? (a.y + a.h + b.y) / 2 : (b.y + b.h + a.y) / 2;
  const dir = lane === 0 ? 0 : lane > 0 ? 1 : -1;
  return { x: (x1 + x2) / 2 + dir * 28, y: yMid + 3 };
}

const STATUS_COLOR: Record<ArchitectureLayer["implementationStatus"], string> =
  {
    implemented: "#34d399",
    configured: "#fbbf24",
    planned: "#7dd3fc",
    unavailable: "#f87171",
  };

interface Props {
  layers: ArchitectureLayer[];
  selectedId: string;
  onSelect: (id: string) => void;
}

export default function ArchitectureDiagram({
  layers,
  selectedId,
  onSelect,
}: Props) {
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [packets, setPackets] = useState(true);

  const reducedMotion = useMemo(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );

  const traceStep = useRef(0);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      const next = Math.min(traceStep.current + 1, TRACE.length - 1);
      traceStep.current = next;
      onSelect(TRACE[next]);
      if (next === TRACE.length - 1) setPlaying(false);
    }, 1400);
    return () => window.clearInterval(timer);
  }, [playing, onSelect]);

  const activeId = hoverId ?? selectedId;
  const layerById = (id: string) => layers.find((l) => l.id === id);
  const indexOf = (id: string) =>
    String(layers.findIndex((l) => l.id === id) + 1).padStart(2, "0");

  const connected = new Set<string>([activeId]);
  EDGES.forEach((e) => {
    if (e.from === activeId) connected.add(e.to);
    if (e.to === activeId) connected.add(e.from);
  });

  const mainPath = MAIN_PATH_IDS.map((id) => {
    const e = EDGES.find((x) => x.id === id);
    return e ? edgePath(e) : "";
  }).join(" ");

  const onKey = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  };

  const evalLayer = layerById("evaluation-observability");

  return (
    <figure className="arch-diagram">
      <div className="arch-diagram-toolbar">
        <div>
          <span className="arch-diagram-title">
            SYSTEM MAP / AGENTIC REQUEST LIFECYCLE
          </span>
          <span className="arch-diagram-sub">
            Click or focus a node to inspect it. Retrieval and passage
            verification are host steps before the model call; tool calls go
            agent → executor → MCP server and back. The request ledger is owned
            by the agent runtime.
          </span>
        </div>
        <div className="arch-diagram-actions">
          <button
            className="arch-tool-button"
            onClick={() => {
              if (!playing) {
                traceStep.current = 0;
                onSelect(TRACE[0]);
              }
              setPlaying((p) => !p);
            }}
            type="button"
          >
            {playing ? (
              <Pause aria-hidden="true" size={13} />
            ) : (
              <Play aria-hidden="true" size={13} />
            )}
            {playing ? "Pause trace" : "Trace a request"}
          </button>
          <button
            aria-pressed={packets}
            className="arch-tool-button"
            onClick={() => setPackets((p) => !p)}
            type="button"
          >
            <Radio aria-hidden="true" size={13} />
            Data packets {packets ? "on" : "off"}
          </button>
        </div>
      </div>

      <svg
        aria-label="PolicyLens system architecture diagram"
        className="arch-svg"
        role="group"
        viewBox="0 0 1000 680"
      >
        <defs>
          <pattern
            height="24"
            id="arch-grid"
            patternUnits="userSpaceOnUse"
            width="24"
          >
            <path
              d="M 24 0 L 0 0 0 24"
              fill="none"
              stroke="#1f3a46"
              strokeWidth="0.5"
            />
          </pattern>
          <linearGradient id="arch-node" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#14303b" />
            <stop offset="1" stopColor="#0d2029" />
          </linearGradient>
          <linearGradient id="arch-node-active" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#17505a" />
            <stop offset="1" stopColor="#0f3540" />
          </linearGradient>
          {(
            [
              ["main", "#5eead4"],
              ["aux", "#7aa2b5"],
              ["memory", "#c084fc"],
              ["mcp", "#f472b6"],
            ] as const
          ).map(([kind, color]) => (
            <marker
              id={`arch-arrow-${kind}`}
              key={kind}
              markerHeight="8"
              markerWidth="8"
              orient="auto"
              refX="7"
              refY="4"
            >
              <path d="M0,0 L8,4 L0,8 Z" fill={color} />
            </marker>
          ))}
          <filter height="160%" id="arch-glow" width="160%" x="-30%" y="-30%">
            <feGaussianBlur result="b" stdDeviation="5" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <path d={mainPath} id="arch-main-path" />
        </defs>

        <rect fill="url(#arch-grid)" height="680" rx="10" width="1000" />

        <g className="arch-region arch-region-client">
          <rect height="132" rx="10" width="210" x="20" y="52" />
          <text x="30" y="46">
            UNTRUSTED CLIENT
          </text>
        </g>
        <g className="arch-region arch-region-ext">
          <rect height="288" rx="10" width="210" x="755" y="228" />
          <text x="765" y="222">
            MODEL + MCP TRUST BOUNDARY
          </text>
        </g>
        <g className="arch-region arch-region-off">
          <rect height="108" rx="10" width="210" x="20" y="228" />
          <text x="30" y="222">
            OFFLINE BUILD
          </text>
        </g>
        <g className="arch-region arch-region-mem">
          <rect height="108" rx="10" width="455" x="510" y="52" />
          <text x="520" y="46">
            MEMORY · HOT (SESSION) → WARM (LONG-TERM)
          </text>
        </g>

        {EDGES.filter((edge) => !edge.hidden)
          .flatMap((edge) =>
            edge.reverseLabel
              ? [
                  { edge, lane: -9, key: edge.id },
                  { edge: reversed(edge), lane: 9, key: `${edge.id}r` },
                ]
              : [{ edge, lane: 0, key: edge.id }],
          )
          .map(({ edge, lane, key }) => {
            const live = edge.from === activeId || edge.to === activeId;
            const pos = labelPos(edge, lane);
            return (
              <g
                className={`arch-edge arch-edge-${edge.kind}${live ? " is-live" : ""}${live ? "" : " is-dim"}`}
                key={key}
              >
                <path
                  d={edgePath(edge, lane)}
                  markerEnd={`url(#arch-arrow-${edge.kind})`}
                />
                <text textAnchor="middle" x={pos.x} y={pos.y}>
                  {edge.label}
                </text>
              </g>
            );
          })}

        {NODES.map((spec) => {
          const layer = layerById(spec.id);
          if (!layer) return null;
          const box = nodeBox(spec);
          const selected = selectedId === spec.id;
          const dim = !connected.has(spec.id);
          return (
            <g
              aria-label={`${layer.shortLabel} diagram node`}
              aria-pressed={selected}
              className={`arch-node${selected ? " is-selected" : ""}${dim ? " is-dim" : ""}`}
              key={spec.id}
              onBlur={() => setHoverId(null)}
              onClick={() => onSelect(spec.id)}
              onFocus={() => setHoverId(spec.id)}
              onKeyDown={(e) => onKey(e, spec.id)}
              onMouseEnter={() => setHoverId(spec.id)}
              onMouseLeave={() => setHoverId(null)}
              role="button"
              tabIndex={0}
              transform={`translate(${box.x} ${box.y})`}
            >
              <rect
                className="arch-node-body"
                fill={selected ? "url(#arch-node-active)" : "url(#arch-node)"}
                filter={selected ? "url(#arch-glow)" : undefined}
                height={box.h}
                rx="8"
                width={box.w}
              />
              <rect
                fill={ZONE_COLOR[spec.zone]}
                height="3"
                opacity="0.8"
                rx="1.5"
                width={box.w - 24}
                x="12"
                y="0"
              />
              <text className="arch-node-index" x="14" y="24">
                {indexOf(spec.id)} · {spec.zone}
              </text>
              <circle
                cx={box.w - 16}
                cy="20"
                fill={STATUS_COLOR[layer.implementationStatus]}
                r="4"
              />
              <text className="arch-node-title" x="14" y="50">
                {layer.shortLabel}
              </text>
              <text className="arch-node-tech" x="14" y="72">
                {spec.tech}
              </text>
            </g>
          );
        })}

        {[0, 1, 2, 3].map((col) => (
          <line
            className="arch-observe"
            key={col}
            x1={COL_X[col] + NODE_W / 2}
            x2={COL_X[col] + NODE_W / 2}
            y1={ROW_Y.C + NODE_H}
            y2={EVAL_Y}
          />
        ))}

        {evalLayer && (
          <g
            aria-label={`${evalLayer.shortLabel} diagram node`}
            aria-pressed={selectedId === evalLayer.id}
            className={`arch-node${selectedId === evalLayer.id ? " is-selected" : ""}${activeId !== evalLayer.id ? " is-dim" : ""}`}
            onBlur={() => setHoverId(null)}
            onClick={() => onSelect(evalLayer.id)}
            onFocus={() => setHoverId(evalLayer.id)}
            onKeyDown={(e) => onKey(e, evalLayer.id)}
            onMouseEnter={() => setHoverId(evalLayer.id)}
            onMouseLeave={() => setHoverId(null)}
            role="button"
            tabIndex={0}
            transform={`translate(30 ${EVAL_Y})`}
          >
            <rect
              className="arch-node-body"
              fill={
                selectedId === evalLayer.id
                  ? "url(#arch-node-active)"
                  : "url(#arch-node)"
              }
              height="62"
              rx="8"
              width="925"
            />
            <text className="arch-node-index" x="14" y="24">
              {indexOf(evalLayer.id)} · CROSS-CUTTING
            </text>
            <circle
              cx="909"
              cy="20"
              fill={STATUS_COLOR[evalLayer.implementationStatus]}
              r="4"
            />
            <text className="arch-node-title" x="14" y="47">
              {evalLayer.shortLabel}
            </text>
            <text className="arch-node-tech" x="250" y="47">
              versioned manifests · safe lifecycle events · aggregate-only
              browser metrics
            </text>
          </g>
        )}

        {packets && !reducedMotion && (
          <g aria-hidden="true" className="arch-packets">
            {[0, 1.6, 3.2].map((delay) => (
              <circle fill="#5eead4" filter="url(#arch-glow)" key={delay} r="4">
                <animateMotion
                  begin={`${delay}s`}
                  dur="10s"
                  repeatCount="indefinite"
                >
                  <mpath href="#arch-main-path" />
                </animateMotion>
              </circle>
            ))}
          </g>
        )}
      </svg>

      <figcaption className="arch-legend">
        <span>
          <i className="line line-main" /> Primary request path
        </span>
        <span>
          <i className="line line-memory" /> Hot / warm memory
        </span>
        <span>
          <i className="line line-aux" /> Model and tool calls
        </span>
        <span>
          <i className="line line-mcp" /> MCP stdio
        </span>
        <span>
          <i className="dot dot-implemented" /> Implemented
        </span>
        <span>
          <i className="dot dot-configured" /> Configured
        </span>
      </figcaption>
    </figure>
  );
}
