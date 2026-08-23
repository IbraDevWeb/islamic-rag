from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Awaitable, Callable, Protocol, Sequence

import asyncpg

from app.evaluation.retrieval import (
    RetrievalBenchmark,
    RetrievalEvaluationSummary,
    corpus_fingerprint,
    evaluate_results,
    summarize_evaluation,
    validate_benchmark_against_corpus,
)
from app.search.expanded import (
    HYBRID_EXPANDED_RETRIEVAL_ID,
    LEXICAL_EXPANDED_RETRIEVAL_ID,
    SEMANTIC_EXPANDED_RETRIEVAL_ID,
    search_hybrid_expanded,
    search_lexical_expanded,
    search_semantic_expanded,
)
from app.search.hybrid import HYBRID_RETRIEVAL_ID, search_hybrid
from app.search.lexical import RETRIEVAL_ID as LEXICAL_RETRIEVAL_ID, search_lexical
from app.search.semantic import (
    SEMANTIC_RETRIEVAL_ID,
    search_semantic,
    validate_semantic_index_fresh,
)


class RetrievalHit(Protocol):
    section_path: tuple[str, ...]
    volume: int | None
    page: int | None


SearchFunction = Callable[..., Awaitable[tuple[object, Sequence[RetrievalHit]]]]


RETRIEVERS: dict[str, tuple[str, SearchFunction]] = {
    "lexical": (LEXICAL_RETRIEVAL_ID, search_lexical),
    "semantic": (SEMANTIC_RETRIEVAL_ID, search_semantic),
    "hybrid": (HYBRID_RETRIEVAL_ID, search_hybrid),
    "lexical-expanded": (LEXICAL_EXPANDED_RETRIEVAL_ID, search_lexical_expanded),
    "semantic-expanded": (SEMANTIC_EXPANDED_RETRIEVAL_ID, search_semantic_expanded),
    "hybrid-expanded": (HYBRID_EXPANDED_RETRIEVAL_ID, search_hybrid_expanded),
}
SEMANTIC_INDEX_RETRIEVERS = {
    "semantic",
    "hybrid",
    "semantic-expanded",
    "hybrid-expanded",
}


async def run_benchmark_for_retriever(
    conn: asyncpg.Connection,
    benchmark: RetrievalBenchmark,
    *,
    retriever: str,
    validate_labels: bool = True,
) -> RetrievalEvaluationSummary:
    if retriever not in RETRIEVERS:
        raise ValueError(f"Unknown retriever: {retriever}")

    retrieval_id, search_fn = RETRIEVERS[retriever]
    if validate_labels:
        await validate_benchmark_against_corpus(conn, benchmark)
    if retriever in SEMANTIC_INDEX_RETRIEVERS:
        await validate_semantic_index_fresh(conn)

    fingerprint = await corpus_fingerprint(conn, benchmark)
    case_results = []
    for case in benchmark.cases:
        started = perf_counter()
        _, search_results = await search_fn(
            conn,
            case.query,
            limit=case.k,
            work_uri=case.work_uri,
        )
        latency_ms = (perf_counter() - started) * 1000.0
        case_results.append(
            evaluate_results(case, search_results, latency_ms=latency_ms)
        )

    summary = summarize_evaluation(
        benchmark,
        case_results,
        corpus_fingerprint=fingerprint,
    )
    return replace(summary, retrieval_id=retrieval_id)
