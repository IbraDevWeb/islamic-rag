from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

import asyncpg
from fastembed.common.model_description import ModelSource
from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.core.config import settings
from app.search.expanded import ExpandedSearchResult, search_semantic_expanded
from app.search.lexical import QueryAnalysis
from app.search.query_expansion import expand_query_variants

RERANKER_ID = "gte_multilingual_reranker_base_int8_v1"
RERANKED_RETRIEVAL_ID = (
    "semantic_expanded_curated_fiqh_aliases_v1_" + RERANKER_ID
)

# FastEmbed 0.8.0 does not ship this multilingual reranker in its built-in registry,
# but it supports custom ONNX cross-encoders. The source below is an ONNX conversion
# of Alibaba-NLP/gte-multilingual-reranker-base. We deliberately use the quantized
# model so local CPU inference stays materially lighter than a multi-gigabyte
# PyTorch deployment.
_RERANKER_SOURCE_REPO = "onnx-community/gte-multilingual-reranker-base"
_RERANKER_MODEL_FILE = "onnx/model_quantized.onnx"
_RERANKER_REGISTRY_NAME = "islamic-rag/gte-multilingual-reranker-base-int8-v1"


@dataclass(frozen=True)
class HydratedRerankerCandidate:
    chunk_id: str
    sequence_no: int
    text_original: str
    text_hash: str
    volume: int | None
    page: int | None
    page_side: str | None
    section_path: tuple[str, ...]
    section_title: str | None
    version_uri: str
    quality_status: str
    source_text_sha256: str
    work_uri: str


@dataclass(frozen=True)
class RerankedSearchResult:
    score: float
    candidate_score: float
    candidate_rank: int
    best_query_variant: str
    chunk_id: str
    sequence_no: int
    text_original: str
    text_hash: str
    volume: int | None
    page: int | None
    page_side: str | None
    section_path: tuple[str, ...]
    section_title: str | None
    version_uri: str
    quality_status: str
    source_text_sha256: str
    work_uri: str


def _decode_section_path(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
    else:
        decoded = value
    if isinstance(decoded, list):
        return tuple(str(item) for item in decoded if item)
    return (str(decoded),)


def build_reranker_document(candidate: HydratedRerankerCandidate) -> str:
    """Build reranker input from authoritative PostgreSQL evidence.

    The original source text is never modified. Section context is prepended only to
    the transient model input so the cross-encoder can use both chapter structure and
    passage content when judging relevance.
    """

    section = " / ".join(candidate.section_path).strip()
    if section:
        return f"{section}\n{candidate.text_original}"
    return candidate.text_original


async def hydrate_reranker_candidates(
    conn: asyncpg.Connection,
    chunk_ids: Sequence[str],
    *,
    include_rejected: bool = False,
) -> dict[str, HydratedRerankerCandidate]:
    """Hydrate derived retrieval hits from PostgreSQL, the source of truth."""

    ordered_ids = tuple(dict.fromkeys(str(chunk_id) for chunk_id in chunk_ids if chunk_id))
    if not ordered_ids:
        return {}

    rows = await conn.fetch(
        """
        SELECT
            c.chunk_id::text AS chunk_id,
            c.sequence_no,
            c.text_original,
            c.text_hash,
            c.volume,
            c.page,
            c.page_side,
            c.section_path,
            c.section_title,
            tv.openiti_uri AS version_uri,
            tv.quality_status,
            tv.source_text_sha256,
            w.openiti_uri AS work_uri
        FROM chunks c
        JOIN text_versions tv ON tv.id = c.version_id
        JOIN works w ON w.id = tv.work_id
        WHERE c.chunk_id::text = ANY($1::text[])
          AND ($2::boolean OR tv.quality_status <> 'REJECTED')
        """,
        list(ordered_ids),
        include_rejected,
    )

    hydrated: dict[str, HydratedRerankerCandidate] = {}
    for row in rows:
        chunk_id = str(row["chunk_id"])
        hydrated[chunk_id] = HydratedRerankerCandidate(
            chunk_id=chunk_id,
            sequence_no=int(row["sequence_no"]),
            text_original=str(row["text_original"]),
            text_hash=str(row["text_hash"]),
            volume=(int(row["volume"]) if row["volume"] is not None else None),
            page=(int(row["page"]) if row["page"] is not None else None),
            page_side=(str(row["page_side"]) if row["page_side"] is not None else None),
            section_path=_decode_section_path(row["section_path"]),
            section_title=(
                str(row["section_title"]) if row["section_title"] is not None else None
            ),
            version_uri=str(row["version_uri"]),
            quality_status=str(row["quality_status"]),
            source_text_sha256=str(row["source_text_sha256"]),
            work_uri=str(row["work_uri"]),
        )

    missing = [chunk_id for chunk_id in ordered_ids if chunk_id not in hydrated]
    if missing:
        preview = ", ".join(missing[:3])
        raise RuntimeError(
            "Reranker candidate hydration failed for PostgreSQL chunk ids: " + preview
        )
    return hydrated


def _register_reranker_model() -> None:
    registered = {
        str(model["model"]).lower()
        for model in TextCrossEncoder.list_supported_models()
        if model.get("model")
    }
    if _RERANKER_REGISTRY_NAME.lower() in registered:
        return

    TextCrossEncoder.add_custom_model(
        model=_RERANKER_REGISTRY_NAME,
        sources=ModelSource(hf=_RERANKER_SOURCE_REPO),
        model_file=_RERANKER_MODEL_FILE,
        description=(
            "Quantized ONNX multilingual cross-encoder derived from "
            "Alibaba-NLP/gte-multilingual-reranker-base."
        ),
        license="apache-2.0",
        size_in_gb=0.341,
    )


@lru_cache(maxsize=1)
def get_reranker_model() -> TextCrossEncoder:
    _register_reranker_model()
    return TextCrossEncoder(
        model_name=_RERANKER_REGISTRY_NAME,
        cache_dir=settings.reranker_cache_dir,
        threads=settings.reranker_threads,
    )


def _score_query_document_pairs(pairs: Sequence[tuple[str, str]]) -> list[float]:
    if not pairs:
        return []
    model = get_reranker_model()
    return [
        float(score)
        for score in model.rerank_pairs(
            list(pairs),
            batch_size=settings.reranker_batch_size,
        )
    ]


def select_best_variant_scores(
    *,
    candidate_count: int,
    query_variants: Sequence[str],
    scores: Sequence[float],
) -> list[tuple[float, str]]:
    """Choose each candidate's strongest score across curated query variants."""

    if candidate_count < 0:
        raise ValueError("candidate_count must be non-negative")
    if not query_variants:
        raise ValueError("query_variants must not be empty")
    expected = candidate_count * len(query_variants)
    if len(scores) != expected:
        raise ValueError(f"Expected {expected} reranker scores, got {len(scores)}")

    selected: list[tuple[float, str]] = []
    width = len(query_variants)
    for candidate_index in range(candidate_count):
        start = candidate_index * width
        candidate_scores = scores[start : start + width]
        best_index = max(
            range(width),
            key=lambda index: (float(candidate_scores[index]), -index),
        )
        selected.append(
            (float(candidate_scores[best_index]), str(query_variants[best_index]))
        )
    return selected


def _build_scoring_pairs(
    query_variants: Sequence[str],
    hydrated_candidates: Sequence[HydratedRerankerCandidate],
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for candidate in hydrated_candidates:
        document = build_reranker_document(candidate)
        pairs.extend((variant, document) for variant in query_variants)
    return pairs


async def search_semantic_expanded_reranked(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    work_uri: str | None = None,
    include_rejected: bool = False,
    candidate_pool: int | None = None,
) -> tuple[QueryAnalysis, list[RerankedSearchResult]]:
    """Retrieve with semantic+terminology expansion, then cross-encode top candidates.

    Candidate generation is deliberately separated from reranking:
    1. semantic-expanded finds a broad candidate pool;
    2. PostgreSQL hydrates exact source text and provenance;
    3. the multilingual cross-encoder only changes candidate order;
    4. no generated answer or source mutation occurs here.
    """

    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    pool = candidate_pool or settings.reranker_candidate_pool
    if pool < limit or pool > 100:
        raise ValueError("candidate_pool must be between limit and 100")

    analysis, candidates = await search_semantic_expanded(
        conn,
        query,
        limit=pool,
        work_uri=work_uri,
        include_rejected=include_rejected,
        pool_size=pool,
    )
    if not candidates:
        return analysis, []

    hydrated_by_id = await hydrate_reranker_candidates(
        conn,
        [candidate.chunk_id for candidate in candidates],
        include_rejected=include_rejected,
    )
    hydrated_in_rank_order = [hydrated_by_id[candidate.chunk_id] for candidate in candidates]

    query_variants = expand_query_variants(query)
    pairs = _build_scoring_pairs(query_variants, hydrated_in_rank_order)
    scores = await asyncio.to_thread(_score_query_document_pairs, pairs)
    best_scores = select_best_variant_scores(
        candidate_count=len(candidates),
        query_variants=query_variants,
        scores=scores,
    )

    reranked: list[RerankedSearchResult] = []
    for candidate_rank, (candidate, hydrated, best) in enumerate(
        zip(candidates, hydrated_in_rank_order, best_scores, strict=True),
        start=1,
    ):
        score, best_variant = best
        reranked.append(
            RerankedSearchResult(
                score=score,
                candidate_score=float(candidate.score),
                candidate_rank=candidate_rank,
                best_query_variant=best_variant,
                chunk_id=hydrated.chunk_id,
                sequence_no=hydrated.sequence_no,
                text_original=hydrated.text_original,
                text_hash=hydrated.text_hash,
                volume=hydrated.volume,
                page=hydrated.page,
                page_side=hydrated.page_side,
                section_path=hydrated.section_path,
                section_title=hydrated.section_title,
                version_uri=hydrated.version_uri,
                quality_status=hydrated.quality_status,
                source_text_sha256=hydrated.source_text_sha256,
                work_uri=hydrated.work_uri,
            )
        )

    reranked.sort(
        key=lambda result: (
            -result.score,
            result.candidate_rank,
            result.chunk_id,
        )
    )
    return analysis, reranked[:limit]
