# PolicyLens Architecture

## Current Application

PolicyLens has three separately runnable services:

| Service | Package | Current responsibility |
|---|---|---|
| Frontend | `policylens-web` | React/TypeScript/Vite research, evaluation, architecture, model-settings, and system-status views. |
| Backend | `policylens` / `policylens-api` | Typed requests, retrieval, bounded agent runtime, citations, provider selection, persistent sessions/memory, evaluation summaries, safe health/logging. |
| MCP | `policylens-mcp` | Standalone Python stdio server with the read-only `query_statistics` tool, policy-passage resource template and the `cited_policy_brief` prompt template (discoverable, not yet invoked by the agent); identity, permissions, limits, and results are validated. |

The frontend does not hold provider credentials and has no direct access to MCP, Chroma, source files, evaluation manifests, or model APIs. Verified canonical artifacts, the local Chroma/BM25S index, retrieval/citation routes, and conversation memory are owned by the backend. The MCP process has no HTTP listener in the local default configuration.

## Provider Boundaries

`MODEL_PROVIDER` controls the server default independently from `EMBEDDING_PROVIDER`. The workbench reports configured model identifiers through a safe backend endpoint and sends a per-run provider selection. OpenAI requires explicit consent for each request that can transmit question/evidence externally. MLX remains loopback-only. Both local and OpenAI embeddings remain separately configurable. No provider fallback is automatic.

Feature 003 performs local FastEmbed embeddings by default; explicitly selecting OpenAI embeddings sends passage/query text to OpenAI and uses a separate versioned index. The non-agent baseline and bounded agent use the configured OpenAI deployment/model or configured loopback MLX route. The baseline uses no tools; the agent exposes only the typed statistics adapter and returns source-linked claims or host-rendered calculation summaries. Feature 009 selects among backend-configured models per run without exposing keys, and its evaluation view reads an allow-listed summary of Feature 007 manifests.

Hybrid retrieval optionally applies a local FastEmbed cross-encoder (`jinaai/jina-reranker-v1-tiny-en`) to at most 20 already permission-filtered candidates before the final evidence cap. Reranking only changes candidate order: original BM25/dense ranks, hybrid score, passage identity, and citation provenance remain available. Model failures keep the original hybrid order and emit a safe diagnostic. Query rewriting, HyDE, MMR, and graph retrieval remain deferred pending separate evaluation.

## Trust Boundaries

1. Browser to frontend: browser-visible configuration is non-secret; persistent chats are fetched from the backend using the workspace scope.
2. Frontend to backend: typed/versioned HTTP contracts; question, provider, consent, and filters are validated by the backend.
3. Backend to OpenAI: a per-run consent flag is required before external generation; credentials stay backend-side and fallback is disabled.
4. Backend to MLX: configured local model is restricted to a loopback HTTP endpoint.
5. Backend MCP client to MCP process: fixed configured stdio command, bounded handshake, server-name/capability checks, and no model-selected command.
6. MCP process to policy data: read-only source/statistics access with permission, identity, size, argument, and result validation.
7. Ingestion/retrieval to source documents: source content remains untrusted; embedded instructions are never application policy.
8. Evaluation to judge: versioned run and human-review manifests are summarized by an allow-listed read-only backend route; no browser-side manifest reads or automatic evaluation runs occur.
9. Application to logs: structured allow-listed fields; credentials, queries, evidence bodies, and hidden reasoning are omitted.

## Agent State and Memory

`AgentRunLedger` holds finite state transitions, retry/tool budgets, trace identity, and safe lifecycle events for one request. `RetrievalRunRegistry` holds bounded, expiring evidence identity for current-run citation validation. Conversation sessions and turns are persisted server-side in SQLite; follow-up context is limited to the five latest completed exchanges. Optional workspace-scoped long-term memory uses Chroma and requires data-use acknowledgement. Both hot and long-term memories are untrusted context, never evidence, and can be cleared or deleted through the session APIs.

## Evaluation Visibility

The browser consumes aggregate data from `GET /evaluation/summary`; the backend validates local case/run/review/error artifacts and returns status, category/split coverage, selected aggregate metrics, and limitations. Null metrics remain “not measured.” Raw case prompts, per-case results, local artifact paths, and provider credentials are not returned. The view is read-only and cannot start evaluation or generation.

## Remaining Deployment Work

The local implementation includes corpus acquisition/parsing, retrieval, current-run citation checks, a bounded agent, read-only MCP tool/resource access, model routing, evaluation artifacts, security/privacy checks, and the research workbench with persistent sessions and optional memory. Production SSO/RBAC, public deployment, human answer review, and a live quality evaluation of current `agent-v3` remain outstanding. Retrieval readiness reflects active index/provider identity; it does not imply every generation model is configured or ready.