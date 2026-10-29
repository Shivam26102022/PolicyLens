# 7. Responsible AI, Security and Privacy

> Assignment §7: test prompt injection, malicious retrieved content, unsupported claims, sensitive-data requests and unsafe tool invocation; describe controls for permission-aware retrieval, least privilege, secrets, logging, data minimisation and human oversight; keep model-generated insight distinguishable from source facts and statistics.

Intended use and limits: [system card](11-system-card.md).

## Threat testing

Two independent test layers, both with synthetic attack text only.

**1. Deterministic security fixtures** (`data/evaluation/security-attack-fixtures.json`, 16 fixtures; 15 linked to executable tests, 1 not testable locally). `make security-verify` runs them with no live provider call.

| Required threat | Fixtures | Invariant that is tested |
|---|---|---|
| Prompt injection (user) | SEC-001 | Policy and tool permissions do not change. |
| Malicious retrieved or tool content | SEC-002, 003, 004, 014 | Retrieved text and MCP content are evidence only and cannot select tools or alter policy. Malformed results are never evidence. |
| Unsupported or fabricated claims | SEC-012 | Citations must resolve to validated evidence from the current run. |
| Sensitive-data and exfiltration requests | SEC-005, 016 | No external request without explicit consent and no silent provider fallback. |
| Unsafe tool invocation | SEC-004, 006, 007, 015 | Only configured read-only tools run. Invalid arguments are rejected before execution. Traversal identifiers resolve to nothing. Unknown server identity blocks use. |
| Resource exhaustion | SEC-008, 009, 013 | Oversized input and results fail closed. Timeouts stop safely. |
| Permission-aware retrieval | SEC-010 | Unapproved evidence is excluded before it reaches the answer. |
| Consequential decisions | SEC-011 | **Not testable:** no decision policy exists locally. Documented for human review. |

**2. Live behavioural cases** in the 67-case evaluation. Agent accuracy by category, run `ad3163da…` (`agent-v4`):

| Category | n | Agent accuracy |
|---|---:|---:|
| `user_prompt_injection` | 3 | 0.667 |
| `retrieved_document_injection` (synthetic) | 1 | 1.000 |
| `mcp_output_injection` | 3 | 1.000 |
| `sensitive_data_request` | 3 | 1.000 |
| `unauthorized_source_request` | 3 | 0.667 |
| `adversarial_citation` | 3 | 0.333 |
| `invalid_mcp_arguments` | 3 | 0.667 |

The two `0.667` and `0.333` safety misses in `unauthorized_source_request` and `adversarial_citation` are fail-safes (`MODEL_UNAVAILABLE`, `CITATION_INVALID`): the guard stopped the answer rather than letting a fabricated one through. User prompt injection and invalid arguments still miss cases, so injection is **not solved**. Fixture coverage proves selected invariants, not general resistance. Details in [evaluation analysis](06-evaluation-analysis.md).

## Controls

| Area | Control | Evidence |
|---|---|---|
| Trusted versus untrusted | User query, history, memory, passages and tool results are all labelled untrusted in the prompt. Host code redacts recognised instruction-like clauses before provider submission and never reconstructs them. Injection-only requests end as `blocked`. | `prompts/agent/system-v3.md`, `test_agent_runtime.py` |
| Permission-aware retrieval | Passages carry a permission scope. The filter runs **before** ranking, so out-of-scope passages never reach the model. Default scope is `public`. | `retrieval/config.py`, SEC-010 |
| Least privilege | One read-only tool and one read-only resource. No shell, SQL, URL or write tool exists. The model chooses arguments only, never commands or servers. | MCP server, SEC-004 |
| Explicit consent | OpenAI processing needs per-run consent. MLX is loopback only. No automatic provider fallback. | `test_provider_boundaries.py` |
| Secrets | Keys are read by the backend only. `.env` is git-ignored. `VITE_*` values are public. An offline scanner checks the tree (0 findings at last run). | `scripts/security_audit.py` |
| Logging | Allow-listed fields only (event, duration, error code, hashes). No prompts, model output, raw tool arguments or credentials. | `observability/logging.py`, `test_logging.py` |
| Data minimisation | Only public or synthetic data. Local embeddings. Bounded context (≤ 12,000 characters, ≤ 6 chunks). Reviewer IDs are pseudonymous. Question text is not logged. | privacy and retention (above) |
| Memory | Hot (last 5 exchanges, SQLite) and warm (opt-in Chroma) memory are untrusted context and can never be cited. Warm memory needs a data-use acknowledgement, is per workspace and is deletable. | `conversations/`, `test_conversation_memory.py` |
| Human oversight | Answers are research support. The reader must inspect cited passages. All tools are read-only, so no action needs approval. Any future write, send or export tool must require explicit user confirmation. Consequential decisions are escalated to a qualified human. | privacy and retention (above) |

## Model insight versus source fact

Every answer is split into labelled parts so a reader can tell where each statement comes from:

| Kind | How it is shown | Provenance |
|---|---|---|
| **Source claim** | A short claim next to a verbatim excerpt, with source, page and highlighted PDF passage. | Exact-excerpt check against current-run passages. |
| **Statistical result** | Rendered by the host from validated rows, with formula, rounding and input rows. | Deterministic `query_statistics` calculation ID and row keys. |
| **Model note** | Plain-language caveats such as "these differ in period and definition, so no causal link is established". | No citation. Never presented as a source fact. |
| **Status** | `abstained`, `clarification_required`, `conflict`, `blocked`, `failed_safe`. | Host-assigned. |

Modelled-estimate caveats from the source metadata are carried into answers. The prompt forbids rounding, generalising to other places or years, and inferring causes.

## Known gaps

- No production authentication. Access is a workspace header plus a data-use acknowledgement. SSO and RBAC are future work.
- Heuristic injection redaction can miss novel or obfuscated phrasing.
- An exact-excerpt check does not prove the claim follows from the excerpt.
- Provider-side retention is outside local evidence.
- Eligibility, benefits, legal and enforcement use is out of scope (SEC-011).
