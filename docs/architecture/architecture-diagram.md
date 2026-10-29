# PolicyLens Architecture Diagram

```mermaid
flowchart LR
    subgraph Offline[Offline ingestion]
        Sources[Approved sources<br/>2 indicator snapshots + 4 PDFs<br/>licence + SHA-256 pinned]
        Parse[Parse + quality checks]
        Chunk[Chunking<br/>fixed / structure-aware]
        Index[BM25S + Chroma dense index<br/>active-index manifest]
        Catalog[Hash-pinned MCP passage catalog]
        Sources --> Parse --> Chunk --> Index
        Parse --> Catalog
    end

    Browser[Browser<br/>React + Vite workbench]
    API[FastAPI guardrails<br/>schema, consent, workspace, SSE stream]
    Hot[(Hot memory<br/>SQLite, last 5 turns)]
    Warm[(Warm memory<br/>Chroma, opt-in)]
    Agent[Bounded agent runtime<br/>state machine, budgets, retries]
    Retrieval[Hybrid retrieval<br/>permission filter + optional re-rank]
    Gateway[Model gateway<br/>no automatic fallback]
    OpenAI[OpenAI / Foundry<br/>per-run consent]
    MLX[Local MLX<br/>loopback only]
    Tool[Host tool executor<br/>validated, budgeted]
    MCP[MCP stdio server<br/>query_statistics + passage resource<br/>schema hashes pinned]
    Validation[Output + citation validation<br/>exact excerpts, numbers, calculations]
    Eval[Evaluation harness<br/>67 cases, dev/test, metrics, judge, review]
    EvalAPI[Read-only evaluation summary API]
    Logs[Allow-listed logs and traces<br/>no prompts or secrets]

    Browser -->|typed HTTP| API
    API <--> Hot
    API <-.->|opt-in| Warm
    API --> Agent
    Index --> Retrieval
    Agent --> Retrieval
    Retrieval -->|untrusted evidence| Agent
    Agent -->|verify each passage| MCP
    Catalog --> MCP
    Agent --> Gateway
    Gateway -->|consent| OpenAI
    Gateway -->|configured route| MLX
    Gateway -->|tool request| Tool
    Tool --> MCP
    MCP -->|untrusted result| Tool
    Tool --> Agent
    Agent --> Validation
    Validation -->|claims + citations| API
    API -->|progress events + answer| Browser
    Eval -->|manifests| EvalAPI -->|aggregates only| Browser
    Eval -. runs .-> Agent
    API -. safe events .-> Logs
    Agent -. safe events .-> Logs
```

The diagram shows the offline pipeline and the per-request flow. Retrieval is a host step, not a model-selected tool; the model can only request the allow-listed statistics tool. Agent state and citation lookup are request-scoped; persistence is the job of hot and warm memory. Retrieved passages and MCP output are untrusted data. OpenAI processing needs explicit per-run approval, MLX is loopback-only, and no provider fallback occurs.
