interface Capability {
  group: string;
  items: { name: string; text: string }[];
}

const CAPABILITIES: Capability[] = [
  {
    group: "Model Context Protocol",
    items: [
      {
        name: "Tool: query_statistics",
        text: "Deterministic aggregation (none, mean, sum, median), optionally grouped by geography or year, over the two World Bank unemployment indicators, with source rows returned for every number.",
      },
      {
        name: "Resource: policy://sources/{id}/passages/{id}",
        text: "Bounded verbatim passage with SHA-256 hashes, licence and an untrusted flag, read by the host to verify retrieval.",
      },
      {
        name: "Prompt: cited_policy_brief",
        text: "Discoverable brief template that enforces citations, uncertainty and abstention. Advertised, not yet invoked by the agent.",
      },
      {
        name: "Pinned client",
        text: "Server name, version, protocol, allow-lists and tool-schema hashes are checked before use; the command is fixed, never model-chosen.",
      },
    ],
  },
  {
    group: "Agent safety and reliability",
    items: [
      {
        name: "Bounded loop",
        text: "6 turns, 8 tool calls (4 per tool), 1 transient retry and a request timeout; every path ends in a typed terminal state.",
      },
      {
        name: "Repair turns",
        text: "One format-repair turn if the model replies in prose, one citation or number repair turn, then fail safe.",
      },
      {
        name: "Untrusted by default",
        text: "Evidence, tool output, conversation and memory are labelled untrusted data; instructions inside them are never followed.",
      },
      {
        name: "Scope and provider guards",
        text: "Out-of-scope requests (image generation) block before any model call; a provider content filter maps to a blocked status.",
      },
      {
        name: "Fault injection",
        text: "Evaluation can force MCP timeout, unavailable, malformed output, flaky-once or an injected instruction to prove the agent fails safe.",
      },
    ],
  },
  {
    group: "Memory and sessions",
    items: [
      {
        name: "Hot memory",
        text: "Last 5 completed turns (12,000 characters) from SQLite, per workspace and session.",
      },
      {
        name: "Warm memory",
        text: "Opt-in Chroma recall of the top 5 similar past exchanges, with embedding identity validation and clear-by-session or workspace.",
      },
      {
        name: "Privacy controls",
        text: "Data-use acknowledgement before any turn is stored, workspace scoping, and delete APIs for sessions and memories.",
      },
    ],
  },
  {
    group: "Models and providers",
    items: [
      {
        name: "OpenAI and local MLX",
        text: "Backend-configured routes chosen per run; OpenAI needs explicit consent each run and there is never an automatic fallback.",
      },
      {
        name: "Reasoning effort",
        text: "Selectable per run where the model route supports it, with output-token budgets scaled to the effort.",
      },
      {
        name: "Usage and cost",
        text: "Token usage and latency are recorded per run and rolled into the evaluation cost estimate.",
      },
    ],
  },
  {
    group: "Evaluation and observability",
    items: [
      {
        name: "67-case evaluation",
        text: "20 categories, development and test splits, run live for the agent, a no-tools baseline and retrieval-only configurations.",
      },
      {
        name: "Statistics",
        text: "Paired McNemar test and bootstrap interval, recall@k, citation correctness and completeness, AI-judged groundedness and relevance.",
      },
      {
        name: "Traceability",
        text: "Every run has a trace id and a stream of allow-listed lifecycle events; logs omit queries, evidence bodies and credentials.",
      },
    ],
  },
  {
    group: "Deployment",
    items: [
      {
        name: "Single Vercel app",
        text: "The React build is served statically and the FastAPI backend with the MCP service runs as one Python function behind /api.",
      },
      {
        name: "Docker and local",
        text: "Docker image and local dev servers use the same backend, index and MCP code paths.",
      },
    ],
  },
];

export default function PlatformCoverage() {
  return (
    <section aria-label="Platform coverage" className="arch-diagram platform">
      <div className="arch-diagram-toolbar">
        <div>
          <span className="arch-diagram-title">
            PLATFORM / WHAT ELSE IS BUILT
          </span>
          <span className="arch-diagram-sub">
            Capabilities that sit around the request flow above.
          </span>
        </div>
      </div>
      <div className="platform-grid">
        {CAPABILITIES.map((group) => (
          <article className="platform-card" key={group.group}>
            <h3>{group.group}</h3>
            <dl>
              {group.items.map((item) => (
                <div key={item.name}>
                  <dt>{item.name}</dt>
                  <dd>{item.text}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
