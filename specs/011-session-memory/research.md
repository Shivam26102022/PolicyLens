# Research: Session Chat and Memory

## Decisions

### Persist conversation transcripts in SQLite

- **Decision**: Use Python's standard-library `sqlite3` for workspace-scoped sessions, ordered turns, answer JSON, memory preferences, and the required data-use acknowledgement.
- **Rationale**: The API is local and single-operator, currently has no database service or ORM, and the feature needs durable transactional transcript state. SQLite adds no service or dependency and supports foreign-key deletion of session turns.
- **Alternatives considered**: Browser-only state cannot provide backend-owned hot context or durable server-side sessions. Adding a database service or ORM would violate the minimal-service goal without measurable value.

### Use a dedicated, stable Chroma persistence path for conversation memory

- **Decision**: Store bounded conversation-pair documents in a versioned `policylens_chat_memory_v1` collection under a stable memory-specific directory beneath the configured Chroma root. Keep it separate from per-build corpus databases.
- **Rationale**: The repository already uses `chromadb.PersistentClient`, explicit embeddings, and a provider-neutral embedding interface. Its corpus index builder creates a new persistence path for each version/build (`apps/backend/src/policylens/retrieval/indexing.py`), so placing memory in the active corpus path would couple memory lifetime to index replacement. Chroma's current system constraints also state that local persistence is thread-safe but not process-safe for concurrent writers sharing one path. A stable, separate path avoids index-version coupling and concurrent writer corruption without adding a service. The installed Chroma version is **1.5.9**; collection `query`, `get`, and `delete` accept metadata filters, allowing workspace-scoped retrieval and deletion. The package range is `chromadb>=1.0,<2`, so compatibility tests must remain against the selected installed version rather than assuming later API behavior.
- **Alternatives considered**: Mixing memory records into a versioned corpus collection would blur evidence identity and couple retention to corpus rebuilds. Sharing a single persistence path with corpus indexing risks unsafe concurrent writers. A separate service or vector database is unnecessary.

- **Compatibility behavior**: Store the collection's embedding provider, model identifier, and dimension. If the configured identity changes, fail memory retrieval/writes closed until the user explicitly clears memory. The clear operation removes the incompatible collection only when it can prove that no other workspace records would be affected; a replacement collection is created on the next consented memory-enabled write. No silent mixing or automatic re-embedding.

### Reuse the configured embedding identity and gate external embedding calls

- **Decision**: Use the configured retrieval embedding provider and its existing `embed_query` behavior for conversation-memory writes and searches; apply the current request's external-processing consent before invoking an external embedding route.
- **Rationale**: Using the same configured embedding identity keeps the memory collection's vectors and queries compatible and avoids adding a model or dependency. The existing settings distinguish local FastEmbed from OpenAI embedding routes.
- **Alternatives considered**: A second embedding model would require separate configuration, evaluation, and lifecycle. Silently using OpenAI embeddings on a local-generation turn would violate the project's privacy boundary.

### Keep session and memory context application-managed and untrusted

- **Decision**: The backend loads the last five completed session pairs and up to five same-workspace memories, then passes them as separate untrusted context fields to the existing agent runtime. It persists user/assistant turns and does not rely on provider-managed conversation IDs.
- **Rationale**: The current runtime already serializes prior conversation as untrusted context, while the citation validator accepts evidence only from the current retrieval run. Keeping memory separate preserves this trust boundary and works consistently for local and OpenAI model routes.
- **Alternatives considered**: Provider-managed Responses API state would couple persistence and follow-ups to one provider and conflict with the current explicit-context design. Sending the full warm transcript would violate bounded-input requirements.

### Evaluate memory retrieval without claiming improved answer quality

- **Decision**: Add a versioned synthetic fixture and deterministic retrieval harness that reports precision@5 and recall@5 against a no-memory baseline; retain its configuration, results, limitations, and negative outcomes in the feature evaluation record.
- **Rationale**: This compares the new retrieval behavior with a simple baseline without using private data, live providers, or frozen policy-evaluation cases. It validates memory selection only and does not claim that memory improves factual answer quality.
- **Alternatives considered**: A live-provider quality benchmark is not necessary to verify the contract and would introduce cost, privacy, and reproducibility burdens.

## Repository Evidence

- `apps/backend/src/policylens/retrieval/search.py` opens the persistent local Chroma index with `PersistentClient` and `embedding_function=None`.
- `apps/backend/src/policylens/retrieval/embeddings.py` exposes provider-neutral `embed_query`; local FastEmbed and OpenAI implementations have distinct descriptors.
- `apps/backend/src/policylens/retrieval/config.py` selects the embedding provider and shares the Chroma persistence path with application settings.
- `apps/backend/src/policylens/agent_runtime/runtime.py` serializes conversation as `untrusted_conversation_context`; citation validation uses only the current retrieval run's evidence.
- `apps/backend/src/policylens/api/agent.py` is the current per-request provider-consent and runtime boundary.
- `apps/backend/pyproject.toml` permits `chromadb>=1.0,<2`; local inspection verified Chroma 1.5.9's query/get/delete signatures support metadata filters.
- The pinned Chroma public system-constraints documentation states that `PersistentClient` is thread-safe but not process-safe for concurrent writers sharing one path; the migration guide documents that empty `{}` filters are rejected and older negation operators may match records missing a field. Sources: [System constraints](https://cookbook.chromadb.dev/core/system_constraints/), [metadata filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering), [delete data](https://docs.trychroma.com/docs/collections/delete-data), and [migration guide](https://docs.trychroma.com/docs/overview/migration).
- Local signature inspection of Chroma 1.5.9 verified that `Collection.query`, `get`, and `delete` accept metadata `where` filters. All workspace reads/deletes will supply a non-empty exact-match workspace filter; the implementation will never issue an empty or unscoped delete.
- The versioned memory evaluation uses synthetic fixture records separate from runtime prompts, reports precision@5/recall@5 against an empty/no-memory baseline, and does not make model-quality claims.
