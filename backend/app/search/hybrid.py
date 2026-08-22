from __future__ import annotations

import math
from dataclasses import dataclass

import asyncpg

from app.search.lexical import QueryAnalysis, search_lexical
from app.search.semantic import SemanticSearchResult, search_semantic

HYBRID_RETRIEVAL_ID = "hybrid_rrf_lexical_v2_e5_large_v1"
RRF_K = 60


@dataclass(frozen=True)
class HybridSearchResult:
    score: float
    chunk_id: str
    section_path: tuple[str, ...]
    section_title: str | None
    volume: int | None
    page: int | None
    page_side: str | None
    work_uri: str
    version_uri: str
    quality_status: str
    lexical_rank: int | None
    semantic_rank: int | None


def _normalized_weights(
    lexical_weight: float,
    semantic_weight: float,
) -> tuple[float, float]:
    weights = (lexical_weight, semantic_weight)
    if any(not math.isfinite(weight) for weight in weights):
        raise ValueError("RRF weights must be finite")
    if any(weight < 0 for weight in weights):
        raise ValueError("RRF weights must be non-negative")
    total = lexical_weight + semantic_weight
    if total <= 0:
        raise ValueError("At least one RRF weight must be positive")
    return lexical_weight / total, semantic_weight / total


def reciprocal_rank_fusion(
    lexical_results,
    semantic_results: list[SemanticSearchResult],
    *,
    limit: int,
    rrf_k: int = RRF_K,
    lexical_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> list[HybridSearchResult]:
    """Fuse lexical and dense rankings with weighted reciprocal rank fusion.

    Raw lexical and cosine scores are deliberately never added because they live in
    incomparable score spaces. Only ranks are fused. Equal weights preserve the
    original baseline behavior; tuning can change relative influence without
    rebuilding any embedding vectors.
    """

    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    lexical_weight, semantic_weight = _normalized_weights(
        lexical_weight,
        semantic_weight,
    )

    merged: dict[str, dict] = {}

    def ensure_from_lexical(result):
        entry = merged.setdefault(
            result.chunk_id,
            {
                "chunk_id": result.chunk_id,
                "section_path": result.section_path,
                "section_title": result.section_title,
                "volume": result.volume,
                "page": result.page,
                "page_side": result.page_side,
                "work_uri": result.work_uri,
                "version_uri": result.version_uri,
                "quality_status": result.quality_status,
                "score": 0.0,
                "lexical_rank": None,
                "semantic_rank": None,
            },
        )
        return entry

    def ensure_from_semantic(result: SemanticSearchResult):
        entry = merged.setdefault(
            result.chunk_id,
            {
                "chunk_id": result.chunk_id,
                "section_path": result.section_path,
                "section_title": result.section_title,
                "volume": result.volume,
                "page": result.page,
                "page_side": result.page_side,
                "work_uri": result.work_uri,
                "version_uri": result.version_uri,
                "quality_status": result.quality_status,
                "score": 0.0,
                "lexical_rank": None,
                "semantic_rank": None,
            },
        )
        return entry

    for rank, result in enumerate(lexical_results, start=1):
        entry = ensure_from_lexical(result)
        entry["lexical_rank"] = rank
        entry["score"] += lexical_weight / (rrf_k + rank)

    for rank, result in enumerate(semantic_results, start=1):
        entry = ensure_from_semantic(result)
        entry["semantic_rank"] = rank
        entry["score"] += semantic_weight / (rrf_k + rank)

    fused = [
        HybridSearchResult(
            score=entry["score"],
            chunk_id=entry["chunk_id"],
            section_path=entry["section_path"],
            section_title=entry["section_title"],
            volume=entry["volume"],
            page=entry["page"],
            page_side=entry["page_side"],
            work_uri=entry["work_uri"],
            version_uri=entry["version_uri"],
            quality_status=entry["quality_status"],
            lexical_rank=entry["lexical_rank"],
            semantic_rank=entry["semantic_rank"],
        )
        for entry in merged.values()
    ]
    fused.sort(
        key=lambda result: (
            -result.score,
            result.lexical_rank if result.lexical_rank is not None else 10**9,
            result.semantic_rank if result.semantic_rank is not None else 10**9,
            result.chunk_id,
        )
    )
    return fused[:limit]


async def search_hybrid(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    work_uri: str | None = None,
    include_rejected: bool = False,
    pool_size: int | None = None,
    lexical_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> tuple[QueryAnalysis, list[HybridSearchResult]]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    pool = pool_size or max(20, limit * 5)
    pool = min(max(pool, limit), 100)

    lexical_analysis, lexical_results = await search_lexical(
        conn,
        query,
        limit=pool,
        work_uri=work_uri,
        include_rejected=include_rejected,
    )
    _, semantic_results = await search_semantic(
        conn,
        query,
        limit=pool,
        work_uri=work_uri,
        include_rejected=include_rejected,
    )
    return lexical_analysis, reciprocal_rank_fusion(
        lexical_results,
        semantic_results,
        limit=limit,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
    )
