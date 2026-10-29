# Feature 004 Agent Runtime Quickstart

## Prerequisites

- Python 3.12+ and the locked workspace dependencies.
- Feature 002 canonical data and a verified Feature 003 active index.
- `MODEL_PROVIDER=openai`, `OPENAI_API_KEY`, and one model configuration. For the standard OpenAI endpoint set `OPENAI_MODEL`; for OpenAI-compatible Foundry set both `OPENAI_DEPLOYMENT_MODEL` and `OPENAI_BASE_URL`.
- The API key and Foundry endpoint belong only in the backend `.env`; never put them in frontend variables or source control.
- Feature 005 provides the production stdio MCP server, including the read-only statistics tool and passage resource. Unit tests still use a typed fake adapter; live evaluation requires explicit provider authorization.

## Build and Verify Retrieval

```bash
uv sync --locked --all-packages --all-groups
make data-parse
make retrieval-index
make retrieval-verify
uv run --locked --package policylens pytest apps/backend/tests -q
```

## Run the API

```bash
make dev-api
```

`POST /agent/answer` accepts the Feature 003 query, retrieval mode, top-k, and restrictive filters. Corpus-derived claims may be concise summaries; if a model-provided citation excerpt is not an exact match, the host replaces it with a bounded exact excerpt from that same current-run passage before validating the citation's passage and source provenance. Citation validation does not prove semantic entailment, so inspect the linked evidence when reviewing a claim. Calculation claim text is rendered by the host from validated tool rows. The response includes a terminal status, citations, calculations, model/prompt identity, trace ID, and safe event summaries. It never returns hidden reasoning, prompts, raw tool arguments/results, or full evidence in the event list. Citation failures include a safe validation reason in the per-answer event trail without retaining the rejected model draft.

Example request:

```bash
curl -sS http://127.0.0.1:8009/agent/answer \
  -H 'Content-Type: application/json' \
  -d '{"schema_version":"1.0","query":"What was the youth unemployment rate in India in 2025?","mode":"hybrid","top_k":5,"filters":{"country_iso3":["IND"],"years":[2025]}}'
```

Expected safe outcomes include `answered`, `clarification_required`, `abstained`, `conflict`, `blocked`, and `failed_safe`. A tool/model timeout or invalid citation produces a stable error and a trace ID; it does not trigger provider fallback.

## Foundry Configuration

```dotenv
MODEL_PROVIDER=openai
OPENAI_API_KEY=<secret>
OPENAI_BASE_URL=<OpenAI-compatible-Foundry-base-URL>
OPENAI_DEPLOYMENT_MODEL=gpt-6-luna
```

When `OPENAI_DEPLOYMENT_MODEL` is set, `OPENAI_BASE_URL` is required and the deployment ID is used as the model. Standard OpenAI uses `OPENAI_MODEL` and the default OpenAI endpoint. The configured Foundry endpoint selects the Chat Completions-compatible Agents SDK path. SDK retries and tracing are disabled; the host enforces the total run timeout and call budgets.

## Tests and Evaluation

```bash
uv run --locked --package policylens pytest apps/backend/tests -q
uv run --locked --package policylens python -m scripts.evaluate_agent
```

The automated suite injects fake model outputs and a typed fake `query_statistics` adapter; it does not make live OpenAI/Foundry calls. The evaluation set is a small author-curated tool-required engineering set, not Feature 007's reviewed benchmark. `scripts.evaluate_agent --live` is a readiness-only stub: it never sends requests and reports `FEATURE_004_COMPARISON_NOT_IMPLEMENTED` when configuration is otherwise present. Use Feature 007's evaluation suite for an actual comparison, with explicit provider opt-in.

## Citation Regression Verification (2026-10-27)

- Corpus claim text may be concise paraphrase. The host replaces a nonmatching model excerpt hint with exact text from the same retrieved passage; passage identity and source provenance remain validated. The validator does not independently prove semantic entailment, so reviewers should inspect the linked evidence.
- Citation failures record an allow-listed validation reason in the safe event trail. The rejected model draft and raw exception text are not persisted.
- The latest excerpt-canonicalization change passed 42 focused backend runtime/model/provider/contract tests, plus Python lint, format, and type checks. The Research page's earlier UI change passed 29 focused UI tests, lint, typecheck, production build, and Prettier checks. Repository traceability passed.
- No live provider endpoint was called. Existing historical traces do not contain the rejected draft, so they cannot identify the exact validation branch retroactively.

## Current Calculation Presentation

- Calculation-only claims are rendered by the host from validated result rows as readable operation/value summaries instead of raw JSON. The full row set, formula, rounding, and provenance remain available in the calculation details.
- Focused runtime tests cover the readable summary. This is a presentation regression fix, not a new model-quality measurement; the current `agent-v2` prompt still needs a controlled evaluation.
