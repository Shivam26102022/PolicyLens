import { Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { agentStates } from "../data/architecture";

const ACTIVE = [
  "received",
  "validated",
  "retrieving",
  "assessing",
  "tool_execution",
  "output_validation",
  "citation_validation",
];
const TERMINAL = [
  "clarification_required",
  "abstained",
  "blocked",
  "conflict",
  "answered",
  "failed_safe",
];

const AW = 112;
const AH = 48;
const AY = 78;
const TW = 140;
const TH = 48;
const TY = 250;

const activeX = (i: number) => 24 + i * 140;
const termX = (i: number) => 30 + i * 155;

interface Scenario {
  id: string;
  label: string;
  steps: string[];
  toolCalls: number;
}

const BASE = ["received", "validated", "retrieving", "assessing"];
const SCENARIOS: Scenario[] = [
  {
    id: "tool",
    label: "Answer with tool",
    steps: [
      ...BASE,
      "tool_execution",
      "assessing",
      "output_validation",
      "citation_validation",
      "answered",
    ],
    toolCalls: 1,
  },
  {
    id: "mismatch",
    label: "Passage mismatch",
    steps: ["received", "validated", "retrieving", "failed_safe"],
    toolCalls: 0,
  },
  {
    id: "abstain",
    label: "Abstain",
    steps: [...BASE, "abstained"],
    toolCalls: 0,
  },
  {
    id: "clarify",
    label: "Clarify",
    steps: [...BASE, "clarification_required"],
    toolCalls: 0,
  },
  {
    id: "blocked",
    label: "Blocked",
    steps: [...BASE, "blocked"],
    toolCalls: 0,
  },
  {
    id: "conflict",
    label: "Citation conflict",
    steps: [...BASE, "output_validation", "citation_validation", "conflict"],
    toolCalls: 0,
  },
];

function pos(id: string) {
  const ai = ACTIVE.indexOf(id);
  if (ai >= 0) return { x: activeX(ai), y: AY, w: AW, h: AH };
  const ti = TERMINAL.indexOf(id);
  return { x: termX(ti), y: TY, w: TW, h: TH };
}

function link(from: string, to: string, dxFrom = 0, dxTo = 0): string {
  const a = pos(from);
  const b = pos(to);
  if (a.y === b.y) {
    return `M ${a.x + a.w} ${a.y + a.h / 2} L ${b.x} ${b.y + b.h / 2}`;
  }
  const x1 = a.x + a.w / 2 + dxFrom;
  const x2 = b.x + b.w / 2 + dxTo;
  const y1 = a.y + a.h;
  const y2 = b.y;
  const k = (y2 - y1) * 0.5;
  return `M ${x1} ${y1} C ${x1} ${y1 + k}, ${x2} ${y2 - k}, ${x2} ${y2}`;
}

const arcAbove = () => {
  const x1 = activeX(3) + AW / 2;
  const x2 = activeX(5) + AW / 2;
  return `M ${x1} ${AY} C ${x1} ${AY - 56}, ${x2} ${AY - 56}, ${x2} ${AY}`;
};
const arcBelow = () => {
  const x1 = activeX(4) + 30;
  const x2 = activeX(3) + AW - 30;
  const y = AY + AH;
  return `M ${x1} ${y} C ${x1} ${y + 26}, ${x2} ${y + 26}, ${x2} ${y}`;
};

export default function AgentStateMachine() {
  const [scenarioId, setScenarioId] = useState("tool");
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [inspectId, setInspectId] = useState("assessing");

  const scenario = SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0];

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setStep((current) => {
        const next = current + 1;
        if (next >= scenario.steps.length - 1) setPlaying(false);
        return Math.min(next, scenario.steps.length - 1);
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [playing, scenario]);

  useEffect(() => {
    if (step >= 0) setInspectId(scenario.steps[step]);
  }, [step, scenario]);

  const current = step >= 0 ? scenario.steps[step] : null;
  const visited = new Set(scenario.steps.slice(0, step + 1));
  const toolCallsUsed =
    step < 0
      ? 0
      : scenario.steps.slice(0, step + 1).filter((s) => s === "tool_execution")
          .length;
  const inspected = agentStates.find((s) => s.id === inspectId);

  const run = (id: string) => {
    setScenarioId(id);
    setStep(0);
    setPlaying(true);
  };

  const stateClass = (id: string, kind: string) =>
    `asm-state asm-${kind}${current === id ? " is-current" : ""}${visited.has(id) ? " is-visited" : ""}${inspectId === id ? " is-inspected" : ""}`;

  return (
    <section aria-label="Agent state machine" className="arch-diagram asm">
      <div className="arch-diagram-toolbar">
        <div>
          <span className="arch-diagram-title">
            AGENT LOOP / BOUNDED STATE MACHINE
          </span>
          <span className="arch-diagram-sub">
            Retrieved passages are verified over MCP, then the agent iterates
            assess ⇄ tool until it can answer; every claim excerpt is validated.
            Pick a scenario to simulate a run.
          </span>
        </div>
        <div className="arch-diagram-actions">
          {SCENARIOS.map((s) => (
            <button
              aria-pressed={scenarioId === s.id && step >= 0}
              className="arch-tool-button"
              key={s.id}
              onClick={() => run(s.id)}
              type="button"
            >
              <Play aria-hidden="true" size={12} />
              {s.label}
            </button>
          ))}
          <button
            className="arch-tool-button"
            onClick={() => {
              setPlaying(false);
              setStep(-1);
            }}
            type="button"
          >
            <RotateCcw aria-hidden="true" size={12} />
            Reset
          </button>
        </div>
      </div>

      <svg
        aria-label="Agent run state transitions"
        className="arch-svg"
        role="group"
        viewBox="0 0 1000 356"
      >
        <defs>
          <marker
            id="asm-arrow"
            markerHeight="8"
            markerWidth="8"
            orient="auto"
            refX="7"
            refY="4"
          >
            <path d="M0,0 L8,4 L0,8 Z" fill="#7aa2b5" />
          </marker>
        </defs>

        <text className="arch-zone-caption" x="24" y="24">
          ACTIVE STATES
        </text>
        <text className="arch-zone-caption" x="30" y="324">
          TERMINAL STATES · EVERY RUN ENDS IN EXACTLY ONE
        </text>

        <g className="asm-edges">
          {ACTIVE.slice(0, -1).map((id, i) =>
            id === "assessing" ? null : id === "tool_execution" ? null : (
              <path
                d={link(id, ACTIVE[i + 1])}
                key={id}
                markerEnd="url(#asm-arrow)"
              />
            ),
          )}
          <path
            d={link("assessing", "tool_execution")}
            markerEnd="url(#asm-arrow)"
          />
          <path
            className="asm-loop"
            d={arcBelow()}
            markerEnd="url(#asm-arrow)"
          />
          <path d={arcAbove()} markerEnd="url(#asm-arrow)" />
          <text className="asm-label" x={activeX(3) + 150} y={AY - 52}>
            draft ready
          </text>
          <text className="asm-label" x={activeX(3) + 112} y={AY + AH + 40}>
            tool result · loop (≤ 8 calls, 1 retry)
          </text>
          <path
            d={link("assessing", "clarification_required")}
            markerEnd="url(#asm-arrow)"
          />
          <path
            d={link("assessing", "abstained")}
            markerEnd="url(#asm-arrow)"
          />
          <path d={link("assessing", "blocked")} markerEnd="url(#asm-arrow)" />
          <path d={link("assessing", "conflict")} markerEnd="url(#asm-arrow)" />
          <path
            d={link("citation_validation", "answered", -20, 0)}
            markerEnd="url(#asm-arrow)"
          />
          <path
            d={link("citation_validation", "conflict", 20, 20)}
            markerEnd="url(#asm-arrow)"
          />
        </g>

        {[...ACTIVE, ...TERMINAL].map((id) => {
          const info = agentStates.find((s) => s.id === id);
          if (!info) return null;
          const p = pos(id);
          return (
            <g
              aria-label={`${info.label} state`}
              className={stateClass(id, info.kind)}
              key={id}
              onClick={() => setInspectId(id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setInspectId(id);
                }
              }}
              role="button"
              tabIndex={0}
              transform={`translate(${p.x} ${p.y})`}
            >
              <rect height={p.h} rx="7" width={p.w} />
              <text
                fontSize={info.label.length > 16 ? 8.5 : undefined}
                textAnchor="middle"
                x={p.w / 2}
                y={p.h / 2 + 4}
              >
                {info.label}
              </text>
            </g>
          );
        })}

        <text className="asm-label" x="30" y="344">
          FAILED_SAFE is reachable from every state on timeout, invalid output,
          provider or MCP failure — never a silent fallback.
        </text>
      </svg>

      <div className="asm-readout">
        <div className="asm-inspector" aria-live="polite">
          <span className="asm-inspector-title">{inspected?.label ?? ""}</span>
          <p>{inspected?.summary}</p>
        </div>
        <div className="asm-counters">
          <span>
            STEP <b>{Math.max(step + 1, 0)}</b>/{scenario.steps.length}
          </span>
          <span>
            TOOL CALLS <b>{toolCallsUsed}</b>/8
          </span>
          <span>
            STATE <b>{current ? current.toUpperCase() : "IDLE"}</b>
          </span>
        </div>
      </div>
    </section>
  );
}
