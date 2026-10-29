from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import EmbeddingProvider, create_embedding_provider
from policylens.retrieval.evaluation import (
    EvaluationCaseError,
    evaluate_retrieval,
    load_retrieval_cases,
)
from policylens.retrieval.indexing import (
    IndexBuildError,
    _append_manifest_entry,
    load_current_sources,
)
from policylens.retrieval.reranking import create_reranker
from policylens.settings import PROJECT_ROOT


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_report(
    path: Path, set_id: str, lineage: str, result: dict[str, Any], embedder: EmbeddingProvider
) -> None:
    descriptor = embedder.descriptor
    reranker = result.get("reranker", {})
    k = result.get("top_k", 5)
    lines = [
        "# Retrieval and Chunking Evaluation",
        "",
        f"Case set: `{set_id}`",
        f"Case lineage: {lineage}",
        (
            f"Embedding provider/model: `{descriptor.provider}` / `{descriptor.model_id}` "
            f"({descriptor.dimension} dimensions)"
        ),
        f"Embedding revision/hash: `{descriptor.model_revision}` / `{descriptor.model_sha256}`",
        "License/pooling/tokenizer: "
        f"`{descriptor.licence}` / `{descriptor.pooling}` / "
        f"`{descriptor.tokenizer}`",
        "",
        (
            "The case set is author-curated engineering evidence tied to "
            "current canonical page/row anchors. It is not independently "
            "human-reviewed or representative of the later Feature 007 "
            "benchmark. Feature 003 includes a bounded extractive non-agent "
            "baseline whose answered claims exactly match current-run excerpts. "
            "This retrieval evaluation does not measure answer selection quality "
            "or source accuracy."
        ),
        "",
        (
            "Dense evaluation uses exact in-memory cosine similarity over "
            "the same normalized vectors; production dense retrieval uses "
            "persistent Chroma."
        ),
        "",
        (
            "The `hybrid+cross_encoder` row, when present, applies the configured "
            "local cross-encoder to up to 20 permission-filtered hybrid candidates "
            "before the final evidence cap. Its score only changes ordering; the "
            "original hybrid ranks and scores remain available."
        ),
        "",
        (
            f"| Chunker | Passages | Mode | Recall@{k} | nDCG@{k} | MRR | Empty rate | "
            "Citation completeness | Mean latency (ms) |"
        ),
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for configuration in result["configurations"]:
        chunker = configuration["chunker"]
        chunker_name = f"{chunker['strategy']}:{chunker['version']}"
        for mode, metrics in configuration["modes"].items():
            lines.append(
                (
                    "| {chunker} | {passages} | {mode} | {recall:.3f} | {ndcg:.3f} | "
                    "{mrr:.3f} | {empty:.3f} | {citation:.3f} | {latency:.2f} |"
                ).format(
                    chunker=chunker_name,
                    passages=configuration["passage_count"],
                    mode=mode,
                    recall=metrics["recall_at_k"],
                    ndcg=metrics["ndcg_at_k"],
                    mrr=metrics["mrr"],
                    empty=metrics["empty_result_rate"],
                    citation=metrics["citation_completeness"],
                    latency=metrics["mean_latency_ms"],
                )
            )
    if reranker.get("enabled"):
        reranking_counts = [
            configuration.get("reranking", {}) for configuration in result["configurations"]
        ]
        counts = {
            key: sum(item.get(key, 0) for item in reranking_counts)
            for key in (
                "attempted_case_count",
                "completed_case_count",
                "failed_case_count",
                "not_run_case_count",
            )
        }
        lines.extend(
            (
                "",
                (
                    f"Reranker: `{reranker['model_id']}`; local inference; "
                    f"candidate cap `{reranker['candidate_count']}`."
                ),
                (
                    "Reranking outcomes across chunk configurations: "
                    f"{counts['completed_case_count']} completed, "
                    f"{counts['failed_case_count']} failed, "
                    f"{counts['not_run_case_count']} not run "
                    f"({counts['attempted_case_count']} attempts)."
                ),
            )
        )
    lines.extend(
        (
            "",
            "## Limitations",
            "",
            "- The engineering relevance set is small and author-curated; no quality threshold or "
            "superiority claim is inferred from it.",
            "- `citation_completeness` measures retrieval source/hash/location metadata.",
            "- Answer selection quality and source accuracy are `not_measured`; "
            "the baseline is extractive, but these cases are not an answer-quality "
            "or source-validity benchmark.",
            "- Latency is measured locally in this run and is not a service-level objective.",
            "- The cross-encoder model is run locally. Case counts report completed, "
            "failed, and not-run reranking attempts; a failed reranker retains hybrid order.",
            "- The first cross-encoder query includes lazy model initialization; warm-cache "
            "latency will differ.",
            "- OpenAI embeddings and baseline generation require explicit configuration; "
            "automated tests make no live calls.",
            "",
            "## Non-Agent Baseline",
            "",
            "`POST /retrieval/answer` makes one structured, tool-free OpenAI Responses call "
            "only when `MODEL_PROVIDER=openai` is explicitly configured. The request disables "
            "provider storage and retries, and bounds evidence input, output tokens, and timeout.",
            "",
            "No evidence abstains before generation is initialized. Every returned claim is "
            "verbatim text exactly equal to a server-derived citation excerpt validated against "
            "the current retrieval run. Provider-backed responses report the provider, model ID, "
            "and prompt version. Baseline tests mock the SDK; this report contains no live "
            "generation result.",
            "",
            "Reproduce with `make retrieval-eval` after `make retrieval-index` "
            "and `make retrieval-verify`.",
            "",
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def run_evaluation(
    project_root: Path = PROJECT_ROOT,
    cases_path: Path | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    settings = RetrievalSettings()
    resolved_cases = cases_path or root / "data/evaluation/retrieval-cases.json"
    cases = load_retrieval_cases(resolved_cases)
    sources = load_current_sources(root)
    embedder = create_embedding_provider(settings)
    reranker = create_reranker(settings)
    started_at = _utcnow()
    start_clock = time.perf_counter()
    result = evaluate_retrieval(root, settings, embedder, cases, reranker=reranker)
    finished_at = _utcnow()
    source_inputs = [
        {
            "source_id": source.source_id,
            "raw_sha256": source.source_content_sha256,
            "canonical_sha256": source.canonical_sha256,
        }
        for source in sorted(sources, key=lambda item: item.source_id)
    ]
    configuration = {
        "chunkers": [item["chunker"] for item in result["configurations"]],
        "modes": ["bm25", "dense", "hybrid"]
        + (["hybrid+cross_encoder"] if result["reranker"]["enabled"] else []),
        "retrieval": {
            "top_k": settings.final_context_chunks,
            "max_candidates": settings.max_candidates,
            "per_source_cap": settings.per_source_cap,
            "rrf_k": settings.rrf_k,
            "bm25_k1": settings.bm25_k1,
            "bm25_b": settings.bm25_b,
            "reranker": result["reranker"],
        },
        "embedding": embedder.descriptor.model_dump(mode="json"),
        "evaluation_schema": "1.1",
    }
    case_set_sha256 = hashlib.sha256(resolved_cases.read_bytes()).hexdigest()
    corpus_sha256 = _fingerprint(source_inputs)
    configuration_sha256 = _fingerprint(configuration)
    manifest_record = {
        "schema_version": "1.0",
        "evaluation_id": str(uuid4()),
        "status": "completed",
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": time.perf_counter() - start_clock,
        "case_set_id": cases.set_id,
        "case_set_sha256": case_set_sha256,
        "corpus_sha256": corpus_sha256,
        "configuration_sha256": configuration_sha256,
        "evaluation_fingerprint": _fingerprint(
            {
                "case_set_sha256": case_set_sha256,
                "corpus_sha256": corpus_sha256,
                "configuration_sha256": configuration_sha256,
            }
        ),
        "source_inputs": source_inputs,
        "configuration": configuration,
        "ephemeral_index_versions": [item["index_version"] for item in result["configurations"]],
        "embedding": embedder.descriptor.model_dump(mode="json"),
        "python_version": platform.python_version(),
        "tool_versions": {
            "bm25s": importlib.metadata.version("bm25s"),
            "fastembed": importlib.metadata.version("fastembed"),
            "tiktoken": importlib.metadata.version("tiktoken"),
        },
        "groundedness": "not_measured",
        "results": result["configurations"],
    }
    _append_manifest_entry(
        root / settings.evaluation_manifest_path,
        "runs",
        manifest_record,
    )
    _write_report(
        root / "docs/evaluation/retrieval-evaluation.md",
        cases.set_id,
        cases.lineage,
        result,
        embedder,
    )
    return manifest_record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare local PolicyLens retrieval modes and chunkers"
    )
    parser.add_argument("--cases", type=Path, help="Optional frozen retrieval case file")
    args = parser.parse_args(argv)
    try:
        record = run_evaluation(cases_path=args.cases)
    except (EvaluationCaseError, IndexBuildError) as error:
        print(json.dumps({"status": "failed", "message": str(error)}))
        return 1
    print(
        json.dumps(
            {
                "status": record["status"],
                "evaluation_id": record["evaluation_id"],
                "case_set_id": record["case_set_id"],
                "configurations": len(record["results"]),
                "manifest": "data/manifests/retrieval-evaluation-manifest.json",
                "report": "docs/evaluation/retrieval-evaluation.md",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
