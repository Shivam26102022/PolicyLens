export type ImplementationStatus =
  "implemented" | "configured" | "planned" | "unavailable";

export interface ArchitectureLayer {
  id: string;
  title: string;
  shortLabel: string;
  description: string;
  inputs: string[];
  outputs: string[];
  trustBoundary: string;
  implementationStatus: ImplementationStatus;
  references: string[];
}

export interface AgentStateInfo {
  id: string;
  label: string;
  kind: "active" | "terminal" | "failure";
  summary: string;
}

export const agentStates: AgentStateInfo[] = [
  {
    id: "received",
    label: "RECEIVED",
    kind: "active",
    summary:
      "Request accepted; session context and any opt-in warm memory are loaded and recorded as safe events.",
  },
  {
    id: "validated",
    label: "VALIDATED",
    kind: "active",
    summary:
      "Schema, provider selection, consent, and permissions are checked before any retrieval happens.",
  },
  {
    id: "retrieving",
    label: "RETRIEVING",
    kind: "active",
    summary:
      "Hybrid search applies permission filters, optionally reorders up to 20 candidates with the local cross-encoder, and produces run-scoped evidence. Each selected passage is then re-read through the MCP resource and verified (ids, text, SHA-256 hashes, licence, untrusted flag) before the model sees it; a mismatch fails safe with MCP_PASSAGE_MISMATCH. A reranker failure keeps the hybrid order and is reported in the answer trail.",
  },
  {
    id: "assessing",
    label: "ASSESSING",
    kind: "active",
    summary:
      "An out-of-scope guard (for example image-generation requests) blocks before any model call. Otherwise the model reasons over untrusted evidence plus hot and warm context and decides: answer, call a tool, ask, abstain, or flag a conflict. No evidence and no statistics tool means abstain.",
  },
  {
    id: "tool_execution",
    label: "TOOL_EXECUTION",
    kind: "active",
    summary:
      "The host validates arguments, enforces call budgets and timeouts, calls the MCP server, and feeds validated results back to ASSESSING. Transient errors get a bounded retry.",
  },
  {
    id: "output_validation",
    label: "OUTPUT_VALIDATION",
    kind: "active",
    summary:
      "The typed draft is checked against the output schema before any claim is trusted.",
  },
  {
    id: "citation_validation",
    label: "CITATION_VALIDATION",
    kind: "active",
    summary:
      "Each claim is written in the model's own words and must cite exact excerpts contained in current-run passages, or deterministic calculation ids. The run-scoped validator rejects anything else, and a number guard rejects any figure that is not in the cited passage or a calculation. The first failure triggers one repair turn with the failure reason; a second failure ends as CITATION_INVALID (fail safe).",
  },
  {
    id: "answered",
    label: "ANSWERED",
    kind: "terminal",
    summary: "Validated answer with claim-linked citations and calculations.",
  },
  {
    id: "clarification_required",
    label: "CLARIFICATION",
    kind: "terminal",
    summary: "The question is ambiguous; the agent asks instead of guessing.",
  },
  {
    id: "abstained",
    label: "ABSTAINED",
    kind: "terminal",
    summary: "Evidence does not support an answer, so none is given.",
  },
  {
    id: "conflict",
    label: "CONFLICT",
    kind: "terminal",
    summary:
      "Sources genuinely disagree; both sides are cited and reported honestly.",
  },
  {
    id: "blocked",
    label: "BLOCKED",
    kind: "terminal",
    summary:
      "Out-of-scope request (OUT_OF_SCOPE) or policy block (POLICY_BLOCKED); the model is not called for image requests.",
  },
  {
    id: "failed_safe",
    label: "FAILED_SAFE",
    kind: "failure",
    summary:
      "Any state can fail safely with a stable error code; no provider fallback occurs.",
  },
];

export const architectureLayers: ArchitectureLayer[] = [
  {
    id: "web-interface",
    title: "Web interface",
    shortLabel: "Browser",
    description:
      "The React workbench collects questions, shows the live agent trail, answers, and evidence, and manages conversation sessions. It never calls models, MCP, or data stores directly.",
    inputs: [
      "Research question",
      "Configured model choice and consent",
      "Optional filters and workspace/session identity",
    ],
    outputs: ["Typed backend request", "Answer, citations, and agent trail"],
    trustBoundary: "Browser to frontend and frontend to backend",
    implementationStatus: "implemented",
    references: [
      "apps/frontend/src/pages/ResearchPage.tsx",
      "apps/frontend/src/components/AgentTrail.tsx",
    ],
  },
  {
    id: "api-guardrails",
    title: "API and request guardrails",
    shortLabel: "Backend API",
    description:
      "FastAPI validates request shape, checks provider and embedding consent, resolves the workspace and session, saves the new turn, loads hot memory and (if enabled) recalls warm memory, then hands the query and that context to the agent runtime. It streams lifecycle events to the browser over SSE, persists the completed turn, writes warm memory back, and maps safe errors. Provider credentials stay server-side.",
    inputs: [
      "Versioned HTTP requests",
      "Server configuration",
      "Workspace and session IDs",
    ],
    outputs: [
      "Validated request plus memory context",
      "SSE lifecycle events and final answer",
      "Safe error",
    ],
    trustBoundary: "Frontend to backend API",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/api/agent.py",
      "apps/backend/src/policylens/settings.py",
    ],
  },
  {
    id: "hot-memory",
    title: "Hot memory (session context)",
    shortLabel: "Hot memory",
    description:
      "Hot memory is the short-term working context: the most recent completed turns of the current session, read from the SQLite conversation store. Up to 5 turns and 12,000 characters are replayed to the model as prior messages, with each assistant reply truncated to 4,000 characters.",
    inputs: ["Workspace ID", "Session ID", "Completed turns in SQLite"],
    outputs: [
      "Bounded prior user/assistant messages",
      "session_context_loaded event",
    ],
    trustBoundary: "Workspace-scoped local SQLite store to agent context",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/api/agent.py",
      "apps/backend/src/policylens/conversations/store.py",
    ],
  },
  {
    id: "warm-memory",
    title: "Warm memory (long-term recall)",
    shortLabel: "Warm memory",
    description:
      "Warm memory is opt-in long-term recall, read and written by the API (not by the agent). After a data-use acknowledgement, each completed turn that is not blocked or failed is embedded and stored in a ChromaDB collection scoped by workspace; later questions retrieve the top 5 semantically similar past exchanges, even from other sessions. It can be cleared per session or per workspace.",
    inputs: [
      "Data-use acknowledgement and long-memory flag",
      "Question embedding",
      "Completed turn text (max 4,000 characters)",
    ],
    outputs: [
      "Up to 5 recalled memories",
      "memory_retrieval_completed / memory_write_completed events",
    ],
    trustBoundary:
      "Workspace-scoped local vector store; embedding model identity is validated",
    implementationStatus: "configured",
    references: [
      "apps/backend/src/policylens/conversations/memory.py",
      "apps/backend/src/policylens/api/sessions.py",
    ],
  },
  {
    id: "ingestion-indexing",
    title: "Ingestion and index build (offline RAG pipeline)",
    shortLabel: "Ingestion pipeline",
    description:
      "An offline pipeline prepares the corpus before any request: four World Bank report PDFs are parsed into canonical documents and two World Bank indicator datasets into canonical structured rows. Reports are chunked (fixed 500/75 tokens or structure-aware 250/450 tokens with page and section provenance), embedded with local FastEmbed bge-small or OpenAI, and written to a BM25S keyword index and a Chroma dense index under a versioned active-index manifest. Every passage gets a SHA-256 hash and is published to the MCP passage catalog, which the runtime later uses to verify what the model sees. Embedding identity is validated at load time.",
    inputs: [
      "Approved source PDFs and indicator CSVs with licences",
      "Chunker and embedding configuration",
    ],
    outputs: [
      "BM25S and Chroma indexes plus active-index manifest",
      "Hash-pinned MCP passage catalog",
      "Ingestion quality report",
    ],
    trustBoundary:
      "Source documents are untrusted data; embedded instructions never become application policy",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/ingestion/reports.py",
      "apps/backend/src/policylens/retrieval/chunking.py",
      "apps/backend/src/policylens/retrieval/indexing.py",
    ],
  },
  {
    id: "retrieval-index",
    title: "Retrieval and active index",
    shortLabel: "Evidence retrieval",
    description:
      "Retrieval is a host-side step the agent runtime runs before the model call; it is not a model-selected tool. The backend searches the active index built offline using keyword (BM25), semantic (dense), or hybrid retrieval, with metadata filters (country, year, indicator, source). BM25S and dense Chroma lists are fused with reciprocal rank fusion (k=60), permission-filtered, then the local cross-encoder optionally reranks up to 20 candidates. The host then keeps at most 3 passages per source, drops overlapping passages, and caps context at 6; original channel ranks, scores, provenance, and citation identity are preserved. A safe diagnostic is recorded if local reranking fails. Passages remain untrusted data.",
    inputs: ["Question", "Retrieval mode", "Validated filters"],
    outputs: ["Run-scoped evidence and reranker diagnostics", "Index version"],
    trustBoundary: "Backend to local index and approved source data",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/retrieval/search.py",
      "apps/backend/src/policylens/retrieval/reranking.py",
      "docs/architecture/architecture.md",
    ],
  },
  {
    id: "agent-runtime",
    title: "Agentic runtime and state machine",
    shortLabel: "Agent runtime",
    description:
      "A bounded agent loop (prompt agent-v4, max 6 turns). For a follow-up, the model first rewrites the message into a standalone question (failing open to the original). It then retrieves evidence, verifies passages over MCP, applies the scope guard, assesses, optionally calls tools and re-assesses, then validates its typed draft and citations. If the model returns prose instead of the typed schema, one format-repair turn is allowed. Transitions are enforced by a state machine with tool-call, retry, event, and time budgets; every path ends in a safe terminal state.",
    inputs: [
      "Question",
      "Untrusted retrieved evidence",
      "Hot and warm memory context",
      "Configured model gateway",
    ],
    outputs: ["Typed answer draft", "Safe lifecycle events", "Terminal status"],
    trustBoundary: "Untrusted instructions and data to application policy",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/agent_runtime/runtime.py",
      "apps/backend/src/policylens/agent_runtime/state.py",
      "prompts/agent/system-v4.md",
    ],
  },
  {
    id: "run-memory",
    title: "Run ledger and request state",
    shortLabel: "Request-scoped state",
    description:
      "AgentRunLedger and the bounded retrieval registry hold request-scoped state: allowed transitions, tool counters, retries, safe events, and current-run citation lookup. This state is discarded after the request; persistence is the job of hot and warm memory.",
    inputs: [
      "Current run ID",
      "Bounded state transitions",
      "Current retrieval run",
    ],
    outputs: ["Safe event ledger", "Current-run citation lookup"],
    trustBoundary: "Ephemeral process memory for one request",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/agent_runtime/state.py",
      "apps/backend/src/policylens/retrieval/citations.py",
    ],
  },
  {
    id: "model-gateway",
    title: "Model gateway and provider routes",
    shortLabel: "Model gateway",
    description:
      "A provider-neutral gateway runs the model for one run through the OpenAI Agents SDK runner (OpenAI) or a host action envelope (loopback MLX). OpenAI requires explicit consent; provider failure never triggers automatic fallback.",
    inputs: [
      "Validated provider selection",
      "Per-run consent",
      "Bounded model context",
    ],
    outputs: [
      "Typed draft or tool request",
      "Provider/model metadata",
      "Usage and latency when available",
    ],
    trustBoundary: "Backend to external OpenAI or local loopback MLX",
    implementationStatus: "configured",
    references: [
      "apps/backend/src/policylens/agent_runtime/gateway.py",
      "apps/backend/src/policylens/agent_runtime/mlx_provider.py",
    ],
  },
  {
    id: "runtime-tools",
    title: "Host tool executor",
    shortLabel: "Tool executor",
    description:
      "The model can only request the allow-listed statistics tool. The host validates arguments (geographies, ranges, grouping), enforces total (8), per-tool (4), retry (1), and timeout budgets, and converts results into validated calculation records.",
    inputs: [
      "Model tool request",
      "Approved source permissions",
      "Ledger budgets",
    ],
    outputs: [
      "Calculation record",
      "Safe tool_started / tool_completed events",
    ],
    trustBoundary: "Model request to host-validated action",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/agent_runtime/tools.py",
      "apps/backend/src/policylens/agent_runtime/state.py",
    ],
  },
  {
    id: "mcp-server",
    title: "MCP policy-data server",
    shortLabel: "MCP server",
    description:
      "A read-only Model Context Protocol server over stdio, used twice per run: the host reads every retrieved passage through the resource template to verify it before the model call, and the model reaches statistics only via query_statistics. The client pins server name, version, protocol, tool and resource allow-lists, and SHA-256 hashes of the tool schemas before use. It exposes one tool, query_statistics, one resource template, policy://sources/{source_id}/passages/{passage_id}, and one prompt template, cited_policy_brief (discoverable; not yet invoked by the agent). Everything it returns is untrusted data. For evaluation only, a fault-injection wrapper can make the tool time out, become unavailable, return malformed output, fail once, or return an injected instruction, to test that the host fails safe.",
    inputs: ["Validated query_statistics arguments", "Passage resource URI"],
    outputs: [
      "Deterministic aggregation with source rows",
      "Bounded verbatim passage",
    ],
    trustBoundary: "Agent host to MCP subprocess and approved local data",
    implementationStatus: "implemented",
    references: [
      "services/mcp-policy-data/src/policylens_mcp/server.py",
      "apps/backend/src/policylens/mcp/client.py",
    ],
  },
  {
    id: "evidence-validation",
    title: "Evidence validation and answer assembly",
    shortLabel: "Citation checks",
    description:
      "The host verifies that each claim's exact excerpts exist in current-run passages or tool calculations, and that every material number in a claim appears in the cited passage or a deterministic calculation (a groundedness guard). A failure triggers one repair turn, then fails safe. The host then assembles bounded citations and calculations, and abstains or reports conflicts when evidence does not support an answer. Completed turns are then persisted and, if enabled, written to warm memory.",
    inputs: [
      "Typed model draft",
      "Current-run passages",
      "Deterministic calculation records",
    ],
    outputs: [
      "Claim-linked citations",
      "Validated calculations",
      "Honest terminal response",
    ],
    trustBoundary: "Model output to user-visible factual claims",
    implementationStatus: "implemented",
    references: [
      "apps/backend/src/policylens/retrieval/citations.py",
      "apps/backend/src/policylens/agent_runtime/runtime.py",
    ],
  },
  {
    id: "evaluation-observability",
    title: "Evaluation, privacy, and observability",
    shortLabel: "Evaluation and traces",
    description:
      "A 67-case evaluation set (20 categories, development and test splits) is run live against the agent and a no-tools baseline, plus retrieval-only configurations. Reported: expected-behaviour accuracy with a paired McNemar and bootstrap comparison, retrieval recall@k, citation correctness and completeness, AI-judged groundedness and relevance (uncalibrated), latency, tokens and cost. Headline metrics use the agent condition only. Runs are append-only manifests; the workbench shows aggregates only; null means not measured.",
    inputs: [
      "Recorded run manifests",
      "Pseudonymous review metadata",
      "Allow-listed telemetry",
    ],
    outputs: ["Aggregate evaluation summaries", "Safe status and limitations"],
    trustBoundary: "Evaluation artifacts and traces to browser summaries",
    implementationStatus: "implemented",
    references: [
      "docs/evaluation/evaluation-report.md",
      "docs/security/privacy-retention.md",
      "apps/backend/src/policylens/observability/logging.py",
    ],
  },
];
