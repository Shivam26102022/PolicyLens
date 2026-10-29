# 4. GenAI Modelling and Experimentation

> Assignment §4: at least one LLM with justified model, embedding, prompt and generation settings; a controlled comparison of at least two configurations (quality, latency, cost); structured, programmatically validated outputs; reproducible experiment records.

## Models and settings

| Component | Choice | Justification |
|---|---|---|
| Generation LLM | `gpt-6-luna`, an OpenAI-compatible Azure/Foundry deployment, called through the `openai-agents` SDK | The task is extraction, citation and tool sequencing, not open reasoning. A small, cheap model at $0.10 (input) and $0.50 (output) per million tokens keeps per-answer cost near $0.0004. |
| Reasoning effort | `none` | Lower latency and cost. The host validates every claim, so extra reasoning is not relied on for correctness. |
| Output cap | 1,200 tokens (`MAX_AGENT_OUTPUT_TOKENS`) | Answers are short claims plus excerpts. |
| Temperature | Provider default | The deployment rejects `temperature=0`. Runs are not bit-for-bit deterministic; see the caveat below. |
| Embedding | `BAAI/bge-small-en-v1.5`, local (revision `aa8f8b06…`) | Corpus text stays on the machine. OpenAI embeddings are opt-in and need a separate index. |
| Local alternative | MLX over loopback | Implemented and tested, but it cannot run on this Linux host, so it has no live result. |
| Prompt | `prompts/agent/system-v3.md` (`agent-v3`); baseline `prompts/answer/non-agent-v1.md` | Versioned files. Prompts treat all retrieved text, memory and tool output as untrusted, forbid claims beyond the excerpt, and define abstain, clarify, conflict and block statuses. |

Prompt history: `agent-v1` → `agent-v2` → `agent-v3` → `agent-v4`. **v4 (current app and evaluation harness template)** adds conversation guidance: the model decides how to treat greetings, acknowledgements, confirmations and "are you sure", and must write courteous, explanatory abstentions. A separate model call (`prompts/agent/query-rewrite-v1.md`) turns a follow-up into a standalone retrieval question; it only runs when the chat has prior messages, so the 67 single-turn evaluation cases do not exercise it. The v4 run `ad3163da` re-measured all 67 cases (agent 0.866 against 0.881 for v3 run `18454f3c`; the difference is within noise). v3 differs from v2 in three ways: host-redacted instruction text is declared "not evidence"; `conflict` is narrowed to directly incompatible claims about the same population, period and measure, with differing definitions reported as "not directly comparable"; and injection handling now relies on host redaction (the markers are ignored) rather than the model spotting example phrases.

## Controlled comparison: agent against non-agent baseline

Same model (`gpt-6-luna`), same 67 cases, same corpus and index, same run (`ad3163da…`, seed 0). Only the workflow differs. Source: [evaluation report](06-evaluation-analysis.md).

| Configuration | Expected-behaviour accuracy | AI groundedness (1–5) | AI relevance (1–5) | Mean latency | P95 latency | Tokens in / out | Est. cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| A. Non-agent baseline (`non-agent-v1`): retrieve, then one structured call, no tools | 0.433 | not measured | not measured | 4.2 s | 7.9 s | 98,901 / 16,144 | $0.0180 |
| B. Bounded agent (`agent-v4`): retrieve, optional MCP tool, host validation | 0.866 | 3.54 | 4.58 | 4.8 s | 10.9 s | 252,978 / 10,044 | $0.0303 |

**Trade-off.** The agent is about 1.1× slower on average (1.4× at P95), uses 2.6× the input tokens and costs about 1.7× more per 67-case run, in return for +0.433 absolute accuracy (95% bootstrap CI [+0.299, +0.567]; 31 discordant pairs favour the agent against 2 favouring the baseline; exact McNemar p<0.0001). Most of the gap comes from categories the baseline cannot handle at all (unauthorised source, sensitive data, MCP-output injection, out-of-scope, structured synthesis), where it scored 0.000. That is a missing capability, not a close contest.

**Caveats that limit the claim**

- The two arms differ in prompt, tools **and** host guards, so the gain is not attributable to "agency" alone.
- 13 of 67 baseline generations failed and count as incorrect. A more forgiving baseline harness would narrow the gap.
- Groundedness and relevance are scored by an AI judge that is the same model as the generator. They are not human-validated and are biased towards the generator's style.
- Expected-behaviour accuracy measures the type of response (answer, abstain, block), not semantic correctness.
- v3 (`18454f3c`: agent 0.881, baseline 0.418) and v4 (`ad3163da`: 0.866, 0.433) ran on the same case set and are one seed each, so the 0.015 difference is not evidence that either prompt is better. Per case, v4 fixed three outcomes (multi-step period change, Singapore tripartite synthesis, out-of-range years) and regressed four (country-comparison citation, ministry-memo block, fake-page citation, synthetic conflict reported as clarification). Several regressions end in fail-safes (`MODEL_UNAVAILABLE`, `CITATION_INVALID`) rather than wrong answers; one of them (`MODEL_UNAVAILABLE`) is a provider error.

## Retrieval configurations

Nine retrieval configurations are compared on 40 cases in [3. RAG pipeline](03-rag-pipeline.md). No configuration is shown to be better.

## Structured outputs and programmatic validation

| Boundary | Validation |
|---|---|
| Model output | Pydantic schema with bounded fields: claim text ≤ 2,000 characters, excerpt ≤ 500, a fixed status enum. Invalid output ends as `failed_safe`. |
| Citations | Every excerpt must match current-run evidence exactly. Duplicates and unknown passage IDs are rejected. |
| Numbers | Calculation claims reference a deterministic calculation ID. The host replaces model wording with a summary built from validated rows. |
| MCP request and result | Strict request schema and result schema with pinned schema hashes ([MCP](09-mcp-integration.md)). |
| API | Typed, versioned request models. The backend is authoritative over consent, workspace and filters. |

## Reproducing an experiment

Every run is appended to `data/manifests/evaluation-run-manifest.json` with its run ID, case-set ID and SHA-256, git revision, source-tree SHA-256, `uv.lock` SHA-256, corpus SHA-256, index versions, embedding descriptor (model, revision, hash, dimension), chunker settings, prompt versions, model IDs, AI-judge rubric and model, tool versions and seed (0). Bootstrap uses 2,000 resamples with the recorded seed.

```bash
uv run --locked --package policylens python -m scripts.evaluate_suite \
  --split all --run-retrieval --run-generation --provider openai \
  --allow-openai-live --allow-mcp-tools --ai-judge --seed 0
uv run --locked --package policylens python -m scripts.evaluate_suite --render-run-id <run-id>
```

Live calls need explicit opt-in flags and credentials ([reproducibility](10-reproducibility.md)). `--render-run-id` re-renders a stored run offline without calling any provider. Because the deployment rejects `temperature=0`, a re-run will vary slightly; compare against the recorded confidence intervals, not single numbers.
