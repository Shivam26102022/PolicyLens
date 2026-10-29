# 10. Reproducibility and Setup

> Assignment §10: a reviewer can set up, run, test and re-evaluate the system from the repository. Versions are pinned and every evaluation run records its inputs.

## Prerequisites

Python 3.12, `uv` 0.13.0, Node 24.21.0 (see `.node-version`). No GPU is needed. MLX local generation requires Apple silicon and cannot run on Linux.

## Setup

```bash
cp .env.example .env     # add OPENAI_* values only for live answers
make setup               # uv sync --locked --all-packages --all-groups + npm ci
```

`.env` is git-ignored. Without provider credentials everything except live generation runs.

## Rebuild data and indexes

`data/raw`, `data/canonical`, `data/processed` and `data/indexes` are git-ignored, so rebuild them after cloning.

```bash
make data-fetch && make data-verify   # download and checksum sources
make data-parse                       # parse PDFs and statistics
make data-eda                         # writes docs/data/eda/
make retrieval-index && make retrieval-verify
```

Embeddings are local (`BAAI/bge-small-en-v1.5`, revision pinned), so no key is needed.

## Run

| Command | Result |
|---|---|
| `make dev-api` | API at `http://127.0.0.1:8009` (docs at `/docs`) |
| `make dev-frontend` | UI at `http://127.0.0.1:3009` |
| `make dev-mcp` / `make mcp-health` | MCP server, and a protocol identity check |

## Test and verify

| Command | Covers |
|---|---|
| `make check` | format, lint, types, tests, coverage and traceability |
| `make test`, `make lint`, `make typecheck`, `make coverage` | individual gates |
| `make security-verify` | deterministic security suites (16 fixtures) |
| `make retrieval-eval`, `make agent-eval` | offline retrieval and agent harnesses |
| `make evaluation-verify` | stored evaluation artifacts and hashes |
| `make traceability` | requirement-to-test and doc links |

CI (`.github/workflows/ci.yml`) runs the locked sync, format, lint, type check, tests, coverage, traceability and `make mcp-health`, plus frontend checks.

## Re-run the evaluation

```bash
# live (needs provider authorization and credentials)
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --run-retrieval --run-generation --provider openai --allow-openai-live \
  --allow-mcp-tools --ai-judge --split all --seed 0

# offline re-render of the stored run, with no model call
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --render-run-id ad3163da-7b37-440d-b317-83b1f0075d97
```

## What is pinned and recorded

| Item | Where |
|---|---|
| Python and Node dependencies | `uv.lock`, `package-lock.json`, `uv sync --locked` |
| Tool versions | `uv==0.13.0`, Node 24.21.0 |
| Prompts | `prompts/*`, version recorded per run |
| Embedding and reranker models | revision hashes in retrieval manifests |
| Data | source checksums, `data/manifests/` |
| Case set | content hash plus dev/test split |
| Evaluation runs | `data/manifests/evaluation-run-manifest.json` (append-only; 6 runs, two partial; latest full run `ad3163da` on `agent-v4`) |
| Seed | `--seed`, default 0 |

## Known reproducibility limits

- Generation is not deterministic, because the deployment rejects `temperature=0`. Expect run-to-run variance and compare by interval.
- Provider model versions can change behind a deployment name.
- Live runs need credentials and consent. An offline re-render reproduces the report, not the answers.
- The MLX path is untested on this Linux host.

## Deployment (optional)

`Dockerfile` builds one image (frontend build plus backend, secrets supplied at run time). `vercel.json` serves the static frontend plus the API as one function. Serverless limits are listed in the root [README](../README.md).
