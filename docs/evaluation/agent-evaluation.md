# Feature 004 Agent Evaluation

Status: `blocked`
Case set: `feature004-agent-tool-engineering-v1` (6 author-curated engineering cases)
Latest historical run ID: `dcced7aa-31c9-44a6-8b79-785a7398d197`
Current blocker: `FEATURE_004_COMPARISON_NOT_IMPLEMENTED`

The Feature 004 command is a readiness-only stub and does not execute agent or baseline runs. The production statistics MCP adapter is implemented in Feature 005; adapter availability is not the current blocker. Use Feature 007's evaluation suite for an explicitly authorized generation comparison.

The Feature 007 registry contains a historical `agent-v2`/`non-agent-v1` comparison; it does not measure the current `agent-v3` prompt or its host guards. Case definitions have since been human-reviewed, but the run has no human-reviewed answers. A blocked or unrun comparison is not a success result.
