# Repository Assessment

**As of:** 2026-10-24  
**Authoritative source inspected:** `POLICYLENS_MASTER_SPEC.md` (1,795 lines)

## Observed Facts

### Initial workspace state

- Before Spec Kit initialization, the workspace contained only `POLICYLENS_MASTER_SPEC.md`; recursive file enumeration found no hidden configuration, source code, tests, dependency manifests, data, or generated indexes.
- `git status --short --branch` reported that this directory was not a Git repository. No commit, branch, baseline, or remote was present.
- No `.specify/` or `.github/` directory existed initially. `specify` was not on `PATH`, and `uv tool list` reported no installed tools.
- The attached master specification was read in full. No separate challenge brief or challenge dataset was present in the workspace.

### Available runtimes and tools

| Tool | Observed version/state |
|---|---|
| Host | Linux, x86_64 |
| System Python | Python 3.12.3 |
| uv-managed Python | Python 3.12.14 and Python 3.14.7 available; additional versions are downloadable |
| Node.js | v24.21.0 |
| npm | 11.19.0 |
| uv | 0.13.0 |
| Git | 2.43.0 |
| GNU Make | 4.3 |
| System `python3 -m pip` | Unavailable: `/usr/bin/python3` has no `pip` module; use `uv` for project package management |

The `specify` CLI was installed outside the repository from the official `v1.2.3` tag at commit `5ea8b1cf0a38699340a38e00d02770308997d8c0`. `specify version` reported CLI 1.2.3, running under its uv-managed Python 3.14.7 environment. This tool installation is not an application dependency or a repository lockfile.

The host is not Apple silicon. It can support planning and Linux-compatible service work, but it cannot produce runtime evidence for MLX/MLX-LM; that evidence requires an Apple-silicon host.

### Spec Kit initialization performed

- A disposable project was initialized first to inspect the pinned release's actual generated templates, Copilot skill names, and workflow. It was outside the repository.
- The current workspace was then initialized in place with the verified command below. The only pre-existing file was the supplied master specification, and no generated managed path conflicted with it.
- `specify integration status` returned `OK`: Copilot is the default integration, with no missing or modified managed files.
- The source specification remains present at 1,795 lines. After the user authorized Feature 001 implementation, the three service foundations, locked dependencies, tests, CI workflow, documentation, and traceability checker were added. No source data, RAG pipeline, production MCP capability, agent runtime, or live model call was added.

## Repository Classification

At the start of this run this was a **new, uninitialized workspace**, not an existing Git repository and not an existing Spec Kit repository. It is now initialized with Spec Kit v1.2.3 and Copilot skills, and Feature 001 is implemented locally, but it is still not a Git repository. No commit or branch was created.

The generated Copilot skills use hyphenated invocation names such as `/speckit-constitution`, `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze`, and `/speckit-implement`. Clarify and Analyze are optional gates in the stock workflow, but this project elevates both to required gates. The generated workflow manifest does not automatically insert those optional gates; the operator must invoke them explicitly.

## Recommendations and Resolved Assumptions

- Provider clarification (2026-10-24): select OpenAI for initial generation; keep `mlx` as an additive, fail-closed option until Apple-silicon validation. Keep `EMBEDDING_PROVIDER=local|openai` independent of generation; preserve local embeddings as the default and select OpenAI embeddings explicitly through the environment. No automatic fallback or silent provider replacement.
- Use the canonical Python package name `policylens`, rather than the illustrative `policy_assistant` path in the repository blueprint.
- Keep the frontend's npm lockfile inside `apps/frontend/`; keep the Python workspace lock at the repository root. This gives each package manager one unambiguous lockfile owner.
- Preserve stdio as the default MCP transport. Since stdio has no HTTP health endpoint, expose backend liveness/readiness over HTTP and check MCP readiness by a bounded protocol initialization/capability handshake. Do not add an auxiliary HTTP listener just for health.
- Treat local development and assessment use as Feature 001's deployment target. Do not add production hosting, public network exposure, or production authentication in this feature.
- Preserve the provided `POLICYLENS_MASTER_SPEC.md` path and contents during this run. The specification itself recommends `MASTER_SPEC_PROMPT.md`; reconcile that filename before later repository documentation depends on a single canonical path.

## Clarifications and Blockers

| ID | Item | Effect |
|---|---|---|
| Q-DATA-01 | No challenge brief, approved policy theme, source files, licences, or usage rights were available. | Blocks Feature 002 source selection and acquisition; no data was selected or downloaded. |
| Q-DEPLOY-01 | No production deployment target was specified. | Does not block a local-only foundation; must be answered before adding deployment/auth/network assumptions. |
| Q-MLX-01 | No Apple-silicon host is available in this workspace. | Blocks MLX runtime and parity evidence here; does not block a platform-neutral interface specification. |
| Q-MASTER-PATH-01 | Supplied filename differs from the filename suggested inside the master spec. | The supplied file is preserved; decide whether to rename/copy it before final README and clean-checkout instructions are written. |

No unresolved question materially blocks Feature 001's local foundation acceptance criteria. These are recorded rather than guessed; Q-DATA-01 and Q-MLX-01 are explicit gates for later features.

## Proposed Repository Tree

The tree below combines current Feature 001 files with planned later-feature paths. Data, evaluation, prompt, and later-feature artifacts are not present unless explicitly noted. `POLICYLENS_MASTER_SPEC.md` is the supplied source and is preserved unchanged.

```text
.
├── POLICYLENS_MASTER_SPEC.md
├── .github/
│   ├── skills/                         # Spec Kit Copilot skills (generated)
│   └── workflows/ci.yml
├── .specify/
│   ├── memory/constitution.md
│   ├── feature.json                     # Active Spec Kit feature pointer
│   ├── scripts/bash/                   # Spec Kit scripts (generated)
│   ├── templates/                      # Spec Kit templates (generated)
│   └── workflows/                      # Spec Kit workflow (generated)
├── apps/
│   ├── frontend/
│   │   ├── src/
│   │   ├── tests/
│   │   ├── e2e/                        # Later frontend feature
│   │   ├── package.json
│   │   └── package-lock.json
│   └── backend/
│       ├── src/policylens/
│       ├── tests/
│       └── pyproject.toml
├── services/
│   └── mcp-policy-data/
│       ├── src/policylens_mcp/
│       ├── tests/
│       └── pyproject.toml
├── data/
│   ├── raw/.gitkeep
│   ├── canonical/.gitkeep
│   ├── chunks/.gitkeep
│   ├── processed/.gitkeep
│   ├── indexes/.gitkeep
│   └── manifests/sources.yaml
├── docs/
│   ├── adr/
│   ├── architecture.md
│   ├── data-sheet.md
│   ├── evaluation-report.md
│   ├── model-system-card.md
│   ├── repository-assessment.md
│   ├── requirements-inventory.json
│   ├── internal/spec-kit-bootstrap.md
│   ├── threat-model.md
│   ├── traceability.md
│   └── limitations.md
├── evals/{datasets,rubrics,runners}/
├── experiments/{registry.yaml,results/}
├── prompts/{system,answer,conflict,abstention,citation-repair}/
├── scripts/
├── specs/
│   ├── README.md
│   ├── 001-foundation/{spec.md,plan.md,tasks.md,analysis.md}
│   ├── 002-corpus-ingestion/spec.md
│   ├── 003-retrieval-and-citations/spec.md
│   ├── 004-agent-runtime/spec.md
│   ├── 005-mcp-server/spec.md
│   ├── 006-model-routing/spec.md
│   ├── 007-evaluation/spec.md
│   ├── 008-security-and-responsible-ai/spec.md
│   ├── 009-minimal-ui/spec.md
│   └── 010-convergence/spec.md
├── .env.example
├── .gitignore
├── Makefile
├── pyproject.toml                       # uv workspace root
└── uv.lock
```

The frontend package is named `policylens-web`; the backend Python package is `policylens`; the standalone MCP package is `policylens_mcp` and its service identity is `policylens-mcp`. No service should import another service's private source tree; shared contracts should be published or generated through a small, versioned contract boundary rather than a fourth deployable service.