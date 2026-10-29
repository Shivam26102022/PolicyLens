#!/usr/bin/env python3
"""Evaluate deterministic synthetic memory ranking; this does not call Chroma."""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "apps/backend/tests/fixtures/conversation_memory_eval_v1.json"
TOP_K = 5
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def _rank(query: str, memories: list[dict[str, str]]) -> list[str]:
    query_tokens = _tokens(query)
    document_tokens = [_tokens(memory["text"]) for memory in memories]
    document_frequency: Counter[str] = Counter(
        token for tokens in document_tokens for token in set(tokens)
    )
    average_length = (
        sum(len(tokens) for tokens in document_tokens) / len(document_tokens)
        if document_tokens
        else 0
    )
    scores: list[tuple[float, str]] = []
    for memory, tokens in zip(memories, document_tokens, strict=True):
        counts = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = counts[token]
            if frequency == 0:
                continue
            inverse_document_frequency = math.log(
                1
                + (len(memories) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            length_normalizer = (
                1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length) if average_length else 0.0
            )
            score += inverse_document_frequency * (
                frequency * (1.5 + 1) / (frequency + length_normalizer)
            )
        scores.append((score, memory["id"]))
    return [
        memory_id
        for _score, memory_id in sorted(scores, key=lambda item: (-item[0], item[1]))[:TOP_K]
    ]


def _metrics(ranked_ids: list[str], relevant_ids: set[str]) -> dict[str, float]:
    relevant_found = sum(memory_id in relevant_ids for memory_id in ranked_ids)
    return {
        "precision_at_5": relevant_found / TOP_K,
        "recall_at_5": relevant_found / len(relevant_ids) if relevant_ids else 0.0,
    }


def evaluate(fixture: dict[str, Any]) -> dict[str, Any]:
    category_results: list[dict[str, Any]] = []
    retrieval_durations_ms: list[float] = []
    for category in fixture["categories"]:
        relevant_ids = set(category["relevant_memory_ids"])
        start = perf_counter()
        ranked_ids = _rank(category["query"], category["memories"])
        retrieval_durations_ms.append((perf_counter() - start) * 1000)
        category_results.append(
            {
                "category": category["name"],
                "candidate_count": len(category["memories"]),
                "relevant_count": len(relevant_ids),
                "ranked_memory_ids": ranked_ids,
                "memory": _metrics(ranked_ids, relevant_ids),
                "no_memory_baseline": _metrics([], relevant_ids),
            }
        )

    category_count = len(category_results)
    memory_p5 = (
        sum(result["memory"]["precision_at_5"] for result in category_results) / category_count
    )
    memory_r5 = sum(result["memory"]["recall_at_5"] for result in category_results) / category_count
    baseline_p5 = (
        sum(result["no_memory_baseline"]["precision_at_5"] for result in category_results)
        / category_count
    )
    baseline_r5 = (
        sum(result["no_memory_baseline"]["recall_at_5"] for result in category_results)
        / category_count
    )
    return {
        "schema_version": fixture["schema_version"],
        "evaluation_id": fixture["evaluation_id"],
        "seed": fixture["seed"],
        "retriever": fixture["retriever"],
        "top_k": TOP_K,
        "category_count": category_count,
        "macro_average": {
            "memory": {
                "precision_at_5": round(memory_p5, 4),
                "recall_at_5": round(memory_r5, 4),
            },
            "no_memory_baseline": {
                "precision_at_5": round(baseline_p5, 4),
                "recall_at_5": round(baseline_r5, 4),
            },
        },
        "retrieval_latency_ms": {
            "mean": round(sum(retrieval_durations_ms) / category_count, 4),
            "max": round(max(retrieval_durations_ms), 4),
            "note": "In-process fixture-ranking time; not Chroma or embedding latency.",
        },
        "estimated_provider_cost_usd": 0.0,
        "categories": category_results,
        "limitations": [
            "The lexical fixture ranker does not exercise Chroma or production embeddings.",
            "The no-memory baseline has no retrieved candidates and therefore scores zero.",
            "Retrieval metrics do not measure answer factuality or citation correctness.",
        ],
    }


def main() -> int:
    try:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        report = evaluate(fixture)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Conversation-memory evaluation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
