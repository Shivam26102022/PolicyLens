# PolicyLens Feature Specifications

Features 001-003 are implemented locally; Features 004-010 remain draft specifications whose plans, task lists, checklists, and implementation must be generated and reviewed when scheduled.

| Feature | Specification | Dependency / gate |
|---|---|---|
| 001 Foundation and reproducibility | [spec.md](001-foundation/spec.md) | Implemented locally; see plan, tasks, analysis, and evidence. |
| 002 Data acquisition, corpus ingestion, and EDA | [spec.md](002-corpus-ingestion/spec.md) | Implemented locally; see tasks, data sheet, manifests, and EDA report. |
| 003 Chunking, indexing, retrieval, citations, and baseline | [spec.md](003-retrieval-and-citations/spec.md) | Implemented locally; see tasks, contracts, active-index manifest, baseline API, and measured retrieval evaluation. |
| 004 Bounded agent runtime | [spec.md](004-agent-runtime/spec.md) | Implemented locally with mocked tool/provider paths; Foundry is configured, but live agent-value comparison is blocked on the Feature 005 production adapter. |
| 005 Standalone MCP service and trust controls | [spec.md](005-mcp-server/spec.md) | Depends on approved challenge data and host/server contracts. |
| 006 OpenAI and local MLX model routing | [spec.md](006-model-routing/spec.md) | OpenAI-first route; MLX runtime evidence requires Apple silicon (Q-MLX-01). |
| 007 Evaluation and error analysis | [spec.md](007-evaluation/spec.md) | Depends on frozen corpus/evaluation cases and both model paths where available. |
| 008 Security and responsible AI | [spec.md](008-security-and-responsible-ai/spec.md) | Cross-cuts all service and data features. |
| 009 Minimal PolicyLens UI | [spec.md](009-minimal-ui/spec.md) | Depends on versioned backend contracts and service health states. |
| 010 Convergence and submission package | [spec.md](010-convergence/spec.md) | Depends on implementation/evaluation evidence from prior features. |

Do not infer implementation status from a draft specification. No data, benchmark, result, or acceptance outcome is asserted until verified.