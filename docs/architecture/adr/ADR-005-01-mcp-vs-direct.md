# ADR-005-01: MCP Versus Direct Statistics Calls

**Status**: Accepted for Feature 005  
**Date**: 2026-10-26  
**Owners**: PolicyLens maintainers

## Context

Feature 005 requires a standalone MCP statistics service and a backend host that validates identity, protocol, capabilities, schemas, errors, and untrusted resources. The evaluation must compare that boundary with a thin direct-call adapter on identical deterministic requests. The comparison is evidence about result parity and local operational cost, not a claim that MCP improves calculation quality.

## Decision

- Keep the production path on the request-scoped stdio MCP adapter. MCP is required by the feature contract, and the host verifies the exact server identity, protocol version, tool/resource allow-list, and schema fingerprints before use.
- Keep the direct call only as a local evaluation baseline. Both paths use the same validated statistics computation and Feature 004 result translation.
- Preserve the measured process-startup and protocol overhead in the report; do not hide it or present the single-machine measurement as an SLO.
- Do not add a public HTTP transport, persistent server process, provider fallback, or new deployable service in this feature.

## Alternatives Considered

- Use a direct adapter in production: rejected because it would bypass the required independent MCP trust boundary, protocol discovery, and capability/schema checks.
- Keep a long-lived shared MCP client process: deferred. It may reduce process startup overhead, but would add lifecycle, concurrency, and recovery behavior that has not been measured as necessary for the current local target.
- Claim MCP improves result quality: rejected. The same deterministic computation produced exact parity; the observed difference is operational overhead, not quality.

## Comparison

| Criterion | MCP stdio | Thin direct call |
|---|---|---|
| Interoperability | Uses the pinned protocol and typed discovery boundary; identity, capabilities, and schemas are checked before use. | Shares the Python models but has no protocol-level discovery or cross-process contract. |
| Operational overhead and latency | Separate process/session startup is measurable; this run showed roughly 533–559 ms paired median overhead. | In-process execution measured roughly 9.6–12.0 ms median for the same requests. |
| Debugging | Adds process startup, protocol envelopes, and a second log stream; host/server events use safe trace IDs and hashes. | Easier single-process stepping and fewer moving parts. |
| Trust boundary | Host pins identity and schemas; tool/resource capabilities are read-only and output remains untrusted. | Trust is in-process and depends on import boundaries and Python call-site discipline. |
| Versioning | MCP SDK, server version, protocol version, and schema fingerprints are explicit and fail closed on drift. | Python package/API versioning is simpler but couples caller and implementation release cadence. |

## Consequences

The request-scoped MCP process is materially slower than an in-process direct call in this local measurement. Its cost is visible and attributable to subprocess/session startup and protocol handling. The direct baseline provides a useful regression oracle, while the MCP adapter remains the production path required by the assignment. No live Foundry or external data-provider request was made.

## Verification

Command: `uv run --locked --package policylens python scripts/evaluate_mcp_direct.py --repeats 3`

Environment: Linux, Python 3.12.14, `mcp==2.3.0`, server `0.1.0`, protocol `2026-07-28`; local canonical datasets and a local stdio process. Each case used three repeated paired requests.

| Fixture | Contract parity | Result parity | Direct median (ms) | MCP stdio median (ms) | Paired overhead median (ms) |
|---|---:|---:|---:|---:|---:|
| Youth mean, India, 2020–2022 | Pass | Pass | 9.994 | 569.430 | 559.328 |
| Total median, Indonesia, 2015–2025 | Pass | Pass | 11.961 | 544.093 | 533.115 |
| Youth observations, India, 2020–2022 | Pass | Pass | 10.077 | 545.802 | 536.044 |

The harness reported `parity_passed=true` for all three fixtures. These are local measurements from one workspace with three repetitions per request. They are not live-production, cross-machine, cost, throughput, or quality evidence and do not establish a latency SLO.