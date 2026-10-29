# ADR-0001: Foundation Conventions

**Status**: Accepted for Feature 001  
**Date**: 2026-10-24  
**Owners**: PolicyLens maintainers

## Context

The repository starts as an uninitialized workspace. The product specification requires three separately runnable services, reproducible dependencies, a standalone stdio MCP server, a provider-neutral architecture, and honest separation between foundation scaffolding and later product features.

## Decision

- Use one uv workspace for the backend and MCP Python members, with one root `uv.lock`; keep the frontend npm lock at `apps/frontend/package-lock.json`.
- Keep the three deployable service boundaries and canonical package identities.
- Use stdio for the local MCP service; the backend owns HTTP liveness/readiness and performs a bounded protocol identity check.
- Use OpenAI as the initial generation configuration. Keep MLX as an additive, explicitly selected path for later Apple-silicon validation; never fall back automatically.
- Keep local and OpenAI embedding providers independently selectable through `EMBEDDING_PROVIDER`; preserve the master specification's local default.
- Feature 001 supplies typed configuration and service skeletons only. It does not make model calls, embed data, retrieve evidence, or expose production MCP capabilities.

## Alternatives Considered

- Separate lockfiles for each Python service: rejected for this small workspace because uv workspaces provide one reproducible shared resolution while preserving separate service packages.
- MCP HTTP listener solely for health: rejected because stdio is the default and backend protocol discovery can provide readiness without another network surface.
- Replace local embeddings with OpenAI embeddings: rejected; the user requested both providers, and the master specification retains local as the default.
- Automatic OpenAI fallback when MLX is unavailable: rejected because it could send local/private input externally without explicit approval.

## Consequences

The Python workspace has one coordinated lock update. Service processes remain independent. The first API-based generation path requires user-supplied OpenAI settings; local MLX execution and embedding implementations remain future work. Provider selection does not imply parity or fallback.

## Verification

Feature 001 configuration tests cover selector validity, independent embedding selection, missing credentials, and no fallback. Provider runtime and parity evidence belong to Features 003 and 006.