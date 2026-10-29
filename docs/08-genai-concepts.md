# 8. GenAI Concepts and Technology

> Assignment §8: practical understanding and trade-offs across LLM fundamentals, embeddings and retrieval, prompt and context engineering, evaluation, agentic systems, MCP and production concerns. Each section states the concept, **what PolicyLens does**, and the trade-off. Where the project does *not* do something, it says so.

## LLM fundamentals

| Concept | In PolicyLens | Trade-off |
|---|---|---|
| Tokenisation | Chunk sizes are counted in tokens using the embedding model's tokenizer, so a chunk never exceeds the embedder's input limit (≤ 500 tokens). | Token counts differ between the embedder and the generation model, so token-based cost is an estimate. |
| Context window | Context is capped at 6 chunks and 12,000 characters; excerpts at 500 characters. | A tight context lowers cost and distraction but can drop the one passage that matters (a retrieval miss). |
| Sampling controls | Temperature is left at the provider default because the deployment rejects `temperature=0`. Output is capped at 1,200 tokens and reasoning effort is `none`. | Runs are not bit-reproducible, so results are compared by interval, not single values. |
| Structured generation | Typed Pydantic outputs with a fixed status enum and bounded fields, validated after generation. | Schemas stop malformed output but not wrong content, so semantic checks are still needed. |
| Model selection | One small, low-cost model (`gpt-6-luna`) because the task is extraction and citation. | Cheaper and faster, but untested against larger models. No model-to-model comparison was run. |
| Failure modes | Hallucination, over-reading an excerpt, instruction following from untrusted text, refusal by provider filters. | Mitigations are in [7. Responsible AI](07-responsible-ai.md). Over-reading is the main open risk. |

## Embeddings and retrieval

| Concept | In PolicyLens | Trade-off |
|---|---|---|
| Similarity | Cosine over normalised BGE-small vectors (384 dimensions). | Small model, fast and local, but weaker than larger embedders on subtle semantics. |
| Chunking | Fixed 500/75 against structure-aware 250 and 450, which keep headings and table rows together. | Structure helps readability and citation precision. No retrieval gain was shown at n=40. |
| Metadata filters | Permission scope, source, country and year filter before ranking. | Filtering first guarantees the model never sees excluded text, at the cost of ignoring potentially relevant material. |
| Hybrid retrieval | BM25 plus dense, fused with reciprocal rank fusion (k=60). | Robust to both exact terms and paraphrase. About 35× the latency of BM25 alone for no measured gain here. |
| Re-ranking | Optional local cross-encoder over ≤ 20 candidates. | Better ordering in some settings; +212 ms. Mixed on 7 cases. |
| Retrieval versus generation errors | Retrieval is scored by Recall@k and generation separately by behaviour and judged groundedness. A wrong answer with a correct passage retrieved is a generation error; a missing passage is a retrieval error. | Separate metrics are needed. Per-case attribution of failures is not yet done. |

## Prompt and context engineering

| Concept | In PolicyLens | Trade-off |
|---|---|---|
| Instruction hierarchy | Host policy and code > system prompt > user request. Query, history, memory, passages and tool results are explicitly untrusted data. | A prompt cannot enforce hierarchy alone, so the host redacts, validates and blocks. |
| Few-shot examples | Not used. The prompt relies on explicit rules. | Fewer tokens and less overfitting to examples, but possibly lower format consistency. |
| Context assembly | Verified passages, run-scoped IDs and optional untrusted memory. Duplicate or over-cap sources are trimmed. | Per-source caps reduce dominance but may drop corroboration. |
| Grounding | Each claim must restate only what its excerpt says and carry an exact excerpt. | Verbatim excerpts are checkable but cannot prove entailment. |
| Prompt versioning | `agent-v1` to `v3` and `non-agent-v1` are files, and each run records the version. | Changes of prompt and case set at the same time confound comparisons. |
| Caching | Passage embeddings are cached by model identity and text hash. Identical tool calls are cached per run. No LLM response cache is used. | Response caching would cut cost but risks stale or cross-user answers. |

## Evaluation

| Concept | In PolicyLens | Trade-off |
|---|---|---|
| Offline versus online | Offline only: a frozen 67-case set and a 40-case retrieval set. No online evaluation or user feedback loop yet. | Offline is reproducible but may not match real queries. Feedback capture is proposed in [Section 2](12-section2-innovation.md). |
| Deterministic versus model judges | Behaviour, tool choice, schema validity and citation exactness are deterministic. Groundedness and relevance use an AI judge. | Deterministic checks are cheap and unbiased but shallow. Judges capture meaning but add bias. |
| Judge bias | The judge is the generator model. That is known self-preference risk, so scores are labelled AI-only. | Fix: a different judge model, randomised order, calibration against human labels. |
| Test-set leakage | `dev`/`test` split, test run once, no labels in runtime requests, and unanswerable cases to detect memorised answers. | `agent-v4` scores 0.853 on dev and 0.879 on test, so no dev-over-test tuning gap is visible in the latest run. |
| Human review | Rubric and process documented. All 67 cases approved; 19 deployed answers reviewed (2 reviewers, 38 records). | A blind, independent second reviewer is the next step ([6. Evaluation](06-evaluation-analysis.md)). |

## Agentic systems

Covered in [5. Agentic workflow](05-agentic-workflow.md). **Workflow versus agent:** retrieval and validation are a fixed workflow, and the model chooses only whether and how to call one statistics tool. **State:** an explicit finite state machine. **Memory:** hot and warm, both untrusted. **Idempotency:** identical calls are served from a run cache. **Retries:** one, for transient errors only. **Stopping:** turn, tool, time and token bounds. **Human approval:** unnecessary today because every tool is read-only, and required for any future consequential tool.

## Model Context Protocol

Covered in [9. MCP integration](09-mcp-integration.md): host, client and server roles; tools, resources and prompts; capability discovery; stdio transport and request-scoped lifecycle; and the MCP versus direct-call comparison with measured overhead.

## Production considerations

| Concern | Now | For production |
|---|---|---|
| Observability | Allow-listed structured events with trace IDs, per-answer activity trail, no content | Central log store, dashboards, alerting |
| Latency | Mean 4.8 s, P95 10.9 s for the agent; MCP stdio adds about 0.5 s per call | Persistent MCP client, caching, streaming (SSE is present) |
| Token and cost | About $0.0004 per case; tokens recorded per run | Per-workspace budgets, small-model routing |
| Model routing | Per-run provider selection among configured models; **no automatic fallback** | Routing policy that never crosses trust levels silently |
| Rate limits | Request, call and token bounds in the host; no provider rate-limit handling beyond error mapping | Backoff, queuing, quotas |
| Fallbacks | Safe failure, not substitute models | Documented exit path to a local model |
| Versioning | Pinned lockfile, prompt, index, MCP schema hash and protocol version | Release process and compatibility matrix |
| Reproducibility | Run manifests with revisions and hashes ([4. Experiments](04-genai-experiments.md)) | Experiment tracking dashboard |
