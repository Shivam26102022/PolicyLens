# 9. MCP Integration

> Assignment §9: integrate at least one MCP server, expose tools or resources, validate inputs and outputs, handle timeouts and errors, keep trusted and untrusted content separate, and justify MCP against a direct call. Demo scenarios 8–10 are covered here.

## Roles

| Role | Component | Notes |
|---|---|---|
| Host | FastAPI backend (agent runtime) | Owns policy, validation, limits and the model call. |
| Client | Backend MCP adapter (`mcp==2.3.0`) | One request-scoped stdio session. |
| Server | `services/mcp-policy-data` (v0.1.0, protocol 2026-07-28) | Read-only, local, no network access. |

## Capabilities exposed

| Kind | Name | Purpose |
|---|---|---|
| Tool | `query_statistics` | Deterministic lookup and aggregation over the World Bank unemployment indicators. |
| Resource template | `policy://sources/{source_id}/passages/{passage_id}` | Read one approved source passage (`read_source_passage`). |
| Prompt | `cited_policy_brief` | Discoverable template. The agent does not invoke it. |

`query_statistics` contract (schema version `1.0`):

| Field | Rule |
|---|---|
| Indicators | `SL.UEM.1524.ZS`, `SL.UEM.TOTL.ZS` only |
| Geographies | 1–4 ISO3 codes |
| Years | 2015–2025 |
| Aggregation | `none`, `mean`, `sum`, `median` |
| Grouping | `geography` or `year` |
| Row limit | ≤ 44 |
| Errors | Stable `STATISTICS_*` codes (invalid arguments, no data, and so on) |

The model proposes arguments only. It never selects a server, command or URL.

## Validation, timeouts and errors

- **Discovery:** at start-up the host lists capabilities and checks server identity, protocol version, tool-schema hashes and a resource allow-list. A mismatch means the server is unknown and use is blocked (SEC-015).
- **Input:** arguments are validated against the schema before the call. Invalid arguments never reach the server (SEC-006).
- **Output:** the result is schema-validated and size-capped. Malformed or oversized results are discarded and never become evidence (SEC-013, 014).
- **Timeouts:** 15 s per call, 90 s per request. Cancellation stops the session (SEC-009 area).
- **Retry:** one retry for `MCP_UNAVAILABLE`, `MCP_TIMEOUT` and `INTERNAL_ERROR` only. Invalid arguments are not retried.
- **Failure behaviour:** a persistent failure gives a safe terminal state with a user-visible reason, never an invented number.

## Trusted and untrusted separation

Tool results and resource text are **untrusted data**. They are labelled as such in the prompt, instruction-like clauses are redacted, and they cannot change tools, permissions or the evidence allow-list (SEC-003, 004). Only calculations with a validated row key can be cited.

## Least privilege

One read-only tool and one resource template, no write, shell, SQL, filesystem or network capability, and no secrets in the server's environment. The server holds no state between requests.

## MCP versus a direct call

The ADR-005-01 measurement compared both paths on the same inputs (`scripts/evaluate_mcp_direct.py`).

| Aspect | MCP (stdio) | Direct in-process |
|---|---|---|
| Result parity | Exact | Exact |
| Overhead per call | about 533–559 ms | about 10–12 ms |
| Isolation | Separate process with schema and identity pinning | Same trust domain |
| Reuse by other hosts | Yes | No |
| Discovery and versioning | Protocol-level | Code-level |

**Decision:** production uses MCP, because process isolation, schema pinning and reuse outweigh about half a second, and a direct call is kept only as an evaluation baseline. For a single-host product with no reuse requirement, the direct call would be the simpler choice. Cold-start cost could be reduced with a persistent client, which is not implemented.

## Demo scenarios 8–10

| # | Scenario | How to show it | Evidence |
|---|---|---|---|
| 8 | Discover and invoke a tool | `make mcp-health`, then a statistics question in the UI. The activity trail shows discovery and the call. | `test_mcp_protocol.py`, `services/mcp-policy-data/tests/` |
| 9 | Invalid arguments and timeout | Ask for an unsupported country or use the fault-injection harness. | Cases `invalid-mcp-arguments-*`, `mcp-timeout-*`, SEC-006, 009 |
| 10 | Injection in tool output | Fault-injection wrapper returns instruction text. | `mcp_output_injection` (3 cases, 1.000), SEC-003 |

Measured weakness: `invalid_mcp_arguments` scored 0.333 (baseline 0.667), and `invalid-mcp-arguments-unsupported-country` failed with `MCP_UNAVAILABLE`. See [6. Evaluation](06-evaluation-analysis.md). Fault injection is a synthetic wrapper around the real adapter, so it tests the host's handling, not a real server failure.
