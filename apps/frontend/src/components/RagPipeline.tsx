import { useState } from "react";

interface Stage {
  id: string;
  step: string;
  title: string;
  tech: string;
  kind: "offline" | "query" | "rank" | "verify" | "out";
  detail: string;
  settings: string[];
}

const OFFLINE: Stage[] = [
  {
    id: "parse",
    step: "A1",
    title: "Parse sources",
    tech: "4 World Bank PDFs · 2 indicator datasets",
    kind: "offline",
    detail:
      "Report PDFs become canonical documents (pages, blocks, section paths) and indicator CSVs become canonical rows with country, year and indicator keys. Only approved, licensed sources are ingested; a quality report flags parsing problems.",
    settings: [
      "data/canonical/*",
      "ingestion/reports.py",
      "ingestion/structured.py",
    ],
  },
  {
    id: "chunk",
    step: "A2",
    title: "Chunk",
    tech: "fixed 500/75 · structure-aware 250/450",
    kind: "offline",
    detail:
      "Reports are split into passages with token overlap, preserving page range, block offsets and section path so every citation can point back to the exact place. Structured rows become one passage per observation. Chunking strategies are compared in the evaluation.",
    settings: ["tokenizer BAAI/bge-small-en-v1.5", "retrieval/chunking.py"],
  },
  {
    id: "embed",
    step: "A3",
    title: "Embed",
    tech: "FastEmbed bge-small · or OpenAI",
    kind: "offline",
    detail:
      "Passages are embedded locally by default; OpenAI embeddings are opt-in with per-run consent and use a separate versioned index. The embedding identity is stored in the manifest and validated at load time (INDEX_EMBEDDING_MISMATCH).",
    settings: ["EMBEDDING_PROVIDER=local|openai", "retrieval/embeddings.py"],
  },
  {
    id: "index",
    step: "A4",
    title: "Index + hash",
    tech: "BM25S · Chroma · SHA-256 catalog",
    kind: "offline",
    detail:
      "A keyword BM25S index and a dense Chroma collection are written under a versioned active-index manifest. Each passage gets a SHA-256 text hash and is published to the MCP passage catalog, which the runtime later uses to verify what the model sees.",
    settings: ["data/indexes/active-index.json", "mcp-passage-catalog.json"],
  },
];

const ONLINE: Stage[] = [
  {
    id: "query",
    step: "B1",
    title: "Query + filters",
    tech: "mode · country · year · indicator · source",
    kind: "query",
    detail:
      "The validated question arrives with an optional retrieval mode (bm25, dense or hybrid, default hybrid) and metadata filters. Filters are strictly validated (for example ISO3 codes) and applied to both channels. For a follow-up, the model first rewrites the message into a standalone question. Hot and warm memory are passed to the model separately and never act as evidence.",
    settings: ["top_k ≤ 20 (final ≤ 6)", "RetrievalFilters"],
  },
  {
    id: "bm25",
    step: "B2a",
    title: "BM25S keyword",
    tech: "top 20 · exact terms, numbers, names",
    kind: "rank",
    detail:
      "Lexical search is strong for exact indicator names, country names and figures. Runs over the whole corpus, then candidates are filtered by metadata.",
    settings: ["max_candidates=20"],
  },
  {
    id: "dense",
    step: "B2b",
    title: "Dense (Chroma)",
    tech: "top 20 · semantic similarity",
    kind: "rank",
    detail:
      "The query is embedded and matched against passage vectors with a native metadata where-filter. This finds paraphrases and concepts that share no words with the question.",
    settings: ["cosine / Chroma", "embedding identity validated"],
  },
  {
    id: "rrf",
    step: "B3",
    title: "Hybrid fusion (RRF)",
    tech: "reciprocal rank fusion · k=60",
    kind: "rank",
    detail:
      "Reciprocal Rank Fusion combines the two ranked lists using ranks only, so BM25 and cosine scores need no calibration. Original channel ranks and scores are preserved on every passage for transparency.",
    settings: ["score = Σ 1/(k + rank)", "rrf_k=60"],
  },
  {
    id: "rerank",
    step: "B4",
    title: "Cross-encoder rerank",
    tech: "jina-reranker-v1-tiny-en · top 20",
    kind: "rank",
    detail:
      "A local cross-encoder reads the query and each of up to 20 permission-filtered candidates together and re-scores them, which fixes near-misses the first-stage rankers make. It only reorders: passage identity, original ranks and citation provenance are untouched. If the model fails or returns invalid scores, the hybrid order is kept and a safe diagnostic is reported in the answer trail. The hosted Vercel demo runs with the reranker off (RERANKER_ENABLED=false) to avoid a cold-start model download, so it serves the hybrid order; local runs enable it by default.",
    settings: [
      "reranker_enabled=true",
      "reranker_candidate_count=20",
      "batch 16",
      "event: reranking_completed",
    ],
  },
  {
    id: "select",
    step: "B5",
    title: "Select + diversify",
    tech: "per-source cap 3 · overlap drop · top 6",
    kind: "rank",
    detail:
      "Walking the reranked list, the host skips passages from a source that already contributed 3, skips passages that overlap an already chosen one (same hash or at least half the span on the same page block), and stops at the final context size. Each kept passage gets a stable rank and a citation identity.",
    settings: ["per_source_cap=3", "final_context_chunks=6"],
  },
  {
    id: "register",
    step: "B6",
    title: "Run registry",
    tech: "bounded · expiring · run-scoped",
    kind: "verify",
    detail:
      "The selected passages are registered as a retrieval run with an id and index version. Later, a claim can only cite a passage that is in this run, which is what makes citations unforgeable by the model.",
    settings: ["RetrievalRunRegistry", "CitationValidator"],
  },
  {
    id: "mcp",
    step: "B7",
    title: "MCP verify",
    tech: "resource read · SHA-256 compare",
    kind: "verify",
    detail:
      "Every selected passage is re-read through the MCP resource policy://sources/{source_id}/passages/{passage_id} and compared field by field (ids, text, hash, licence, untrusted flag). Any mismatch fails safe with MCP_PASSAGE_MISMATCH before the model sees anything.",
    settings: ["event: mcp_resource_completed", "no evidence → abstain"],
  },
  {
    id: "agent",
    step: "B8",
    title: "To the agent",
    tech: "untrusted evidence + hot/warm memory",
    kind: "out",
    detail:
      "The model receives the question, bounded conversation context, recalled memories and the verified evidence, all labelled untrusted. It then answers, calls the statistics tool through MCP, asks, abstains or flags a conflict. Output is then citation- and number-checked.",
    settings: ["prompt agent-v4", "max 6 turns · 8 tool calls"],
  },
];

function StageRow({
  stages,
  selected,
  onSelect,
}: {
  stages: Stage[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <ol className="rag-row">
      {stages.map((stage) => (
        <li key={stage.id}>
          <button
            aria-pressed={selected === stage.id}
            className={`rag-stage rag-${stage.kind}${selected === stage.id ? " is-selected" : ""}`}
            onClick={() => onSelect(stage.id)}
            type="button"
          >
            <span className="rag-step">{stage.step}</span>
            <span className="rag-title">{stage.title}</span>
            <span className="rag-tech">{stage.tech}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export default function RagPipeline() {
  const [selectedId, setSelectedId] = useState("rerank");
  const selected = [...OFFLINE, ...ONLINE].find((s) => s.id === selectedId);

  return (
    <section aria-label="RAG pipeline" className="arch-diagram rag-pipeline">
      <div className="arch-diagram-toolbar">
        <div>
          <span className="arch-diagram-title">
            RAG PIPELINE / INDEX BUILD → HYBRID RETRIEVAL → RERANK → VERIFY
          </span>
          <span className="arch-diagram-sub">
            The retrieval half of the system in detail. Select a stage to see
            what it does and how it is configured.
          </span>
        </div>
      </div>
      <p className="rag-lane-label">A · OFFLINE INDEX BUILD</p>
      <StageRow
        onSelect={setSelectedId}
        selected={selectedId}
        stages={OFFLINE}
      />
      <p className="rag-lane-label">
        B · PER REQUEST (HOST-SIDE, BEFORE THE MODEL)
      </p>
      <StageRow
        onSelect={setSelectedId}
        selected={selectedId}
        stages={ONLINE}
      />
      {selected && (
        <article aria-live="polite" className="rag-detail">
          <h3>
            {selected.step} · {selected.title}
          </h3>
          <p>{selected.detail}</p>
          <ul>
            {selected.settings.map((item) => (
              <li key={item}>
                <code>{item}</code>
              </li>
            ))}
          </ul>
        </article>
      )}
    </section>
  );
}
