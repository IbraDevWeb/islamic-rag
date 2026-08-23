from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence

import asyncpg

from app.search.hybrid import (
    HYBRID_DEFAULT_LEXICAL_WEIGHT,
    HYBRID_DEFAULT_SEMANTIC_WEIGHT,
    HybridSearchResult,
    reciprocal_rank_fusion,
)
from app.search.lexical import QueryAnalysis, analyze_query, search_lexical
from app.search.query_expansion import QUERY_EXPANSION_ID, expand_query_variants
from app.search.semantic import search_semantic

LEXICAL_EXPANDED_RETRIEVAL_ID = f"deterministic_lexical_v2_{QUERY_EXPANSION_ID}"
SEMANTIC_EXPANDED_RETRIEVAL_ID = f"semantic_multilingual_e5_large_v1_{QUERY_EXPANSION_ID}"
HYBRID_EXPANDED_RETRIEVAL_ID = (
    "hybrid_rrf_l0125_s0875_lexical_v2_e5_large_v1_" + QUERY_EXPANSION_ID
)
VARIANT_RRF_K = 60


@dataclass(frozen=True)
class ExpandedSearchResult:
    score: float
    source_score: float
    chunk_id: str
    section_path: tuple[str, ...]
    section_title: str | None
    volume: int | None
    page: int | None
    page_side: str | None
    work_uri: str
    version_uri: str
    quality_status: str
    variant_ranks: tuple[int | None, ...]


SearchCallable = Callable[..., Awaitable[tuple[object, Sequence[Any]]]]


def fuse_query_variant_rankings(
    rankings: Sequence[Sequence[Any]],
    *,
    limit: int,
    rrf_k: int = VARIANT_RRF_K,
) -> list[ExpandedSearchResult]:
    """Fuse rankings produced by deterministic query variants of one retriever.

    Rank fusion is used for the primary score. Raw scores are only used as a
    deterministic tie-break inside the same retriever family, where their scale is
    comparable. Source documents and stored text remain unchanged.
    """

    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if not rankings:
        return []

    variant_count = len(rankings)
    merged: dict[str, dict[str, Any]] = {}
    for variant_index, results in enumerate(rankings):
        for rank, result in enumerate(results, start=1):
            entry = merged.setdefault(
                result.chunk_id,
                {
                    "result": result,
                    "score": 0.0,
                    "source_score": float(result.score),
                    "variant_ranks": [None] * variant_count,
                },
            )
            entry["score"] += 1.0 / (rrf_k + rank)
            entry["source_score"] = max(entry["source_score"], float(result.score))
            entry["variant_ranks"][variant_index] = rank

    fused = [
        ExpandedSearchResult(
            score=float(entry["score"]),
            source_score=float(entry["source_score"]),
            chunk_id=entry["result"].chunk_id,
            section_path=tuple(entry["result"].section_path),
            section_title=entry["result"].section_title,
            volume=entry["result"].volume,
            page=entry["result"].page,
            page_side=entry["result"].page_side,
            work_uri=entry["result"].work_uri,
            version_uri=entry["result"].version_uri,
            quality_status=entry["result"].quality_status,
            variant_ranks=tuple(entry["variant_ranks"]),
        )
        for entry in merged.values()
    ]
    fused.sort(
        key=lambda item: (
            -item.score,
            -item.source_score,
            min((rank for rank in item.variant_ranks if rank is not None), default=10**9),
            item.chunk_id,
        )
    )
    return fused[:limit]


async def _search_expanded(
    conn: asyncpg.Connection,
    query: str,
    *,
    search_fn: SearchCallable,
    limit: int,
    work_uri: str | None,
    include_rejected: bool,
    pool_size: int | None = None,
) -> tuple[QueryAnalysis, list[ExpandedSearchResult]]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    analysis = analyze_query(query)
    variants = expand_query_variants(query)
    pool = pool_size or max(20, limit * 5)
    pool = min(max(pool, limit), 100)

    rankings: list[Sequence[Any]] = []
    for variant in variants:
        _, results = await search_fn(
            conn,
            variant,
            limit=pool,
            work_uri=work_uri,
            include_rejected=include_rejected,
        )
        rankings.append(tuple(results))

    return analysis, fuse_query_variant_rankings(rankings, limit=limit)


async def search_lexical_expanded(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    work_uri: str | None = None,
    include_rejected: bool = False,
    pool_size: int | None = None,
) -> tuple[QueryAnalysis, list[ExpandedSearchResult]]:
    return await _search_expanded(
        conn,
        query,
        search_fn=search_lexical,
        limit=limit,
        work_uri=work_uri,
        include_rejected=include_rejected,
        pool_size=pool_size,
    )


async def search_semantic_expanded(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    work_uri: str | None = None,
    include_rejected: bool = False,
    pool_size: int | None = None,
) -> tuple[QueryAnalysis, list[ExpandedSearchResult]]:
    return await _search_expanded(
        conn,
        query,
        search_fn=search_semantic,
        limit=limit,
        work_uri=work_uri,
        include_rejected=include_rejected,
        pool_size=pool_size,
    )


async def search_hybrid_expanded(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    work_uri: str | None = None,
    include_rejected: bool = False,
    pool_size: int | None = None,
) -> tuple[QueryAnalysis, list[HybridSearchResult]]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    pool = pool_size or max(20, limit * 5)
    pool = min(max(pool, limit), 100)
    lexical_analysis, lexical_results = await search_lexical_expanded(
        conn,
        query,
        limit=pool,
        work_uri=work_uri,
        include_rejected=include_rejected,
        pool_size=pool,
    )
    _, semantic_results = await search_semantic_expanded(
        conn,
        query,
        limit=pool,
        work_uri=work_uri,
        include_rejected=include_rejected,
        pool_size=pool,
    )
    fused = reciprocal_rank_fusion(
        lexical_results,
        semantic_results,
        limit=limit,
        lexical_weight=HYBRID_DEFAULT_LEXICAL_WEIGHT,
        semantic_weight=HYBRID_DEFAULT_SEMANTIC_WEIGHT,
    )
    return lexical_analysis, fused
