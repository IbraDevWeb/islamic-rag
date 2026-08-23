from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

import asyncpg

from app.search.expanded import ExpandedSearchResult, search_semantic_expanded
from app.search.lexical import QueryAnalysis
from app.search.query_expansion import expand_query_variants

EVIDENCE_RETRIEVAL_ID = (
    "semantic_multilingual_e5_large_v1_curated_fiqh_aliases_v1_pg_hydrated_v1"
)


@dataclass(frozen=True)
class EvidenceSearchResult:
    score: float
    source_score: float
    variant_ranks: tuple[int | None, ...]
    chunk_id: str
    sequence_no: int
    text_original: str
    text_normalized: str
    text_hash: str
    source_start: int
    source_end: int
    volume: int | None
    page: int | None
    page_side: str | None
    section_path: tuple[str, ...]
    section_title: str | None
    content_kind: str
    version_uri: str
    quality_status: str
    quality_issues: tuple[str, ...]
    source_text_sha256: str
    source_metadata_sha256: str
    work_uri: str
    work_title: str | None
    author_uri: str
    author_name: str | None
    provider: str
    source_url: str
    release: str | None
    license: str | None
    copyright_status: str | None
    commercial_use_allowed: bool | None
    attribution_required: bool | None


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


async def hydrate_evidence_candidates(
    conn: asyncpg.Connection,
    candidates: Sequence[ExpandedSearchResult],
    *,
    include_rejected: bool = False,
) -> list[EvidenceSearchResult]:
    """Hydrate semantic candidate ids from PostgreSQL, the evidentiary source of truth."""

    if not candidates:
        return []

    chunk_ids = tuple(dict.fromkeys(candidate.chunk_id for candidate in candidates))
    rows = await conn.fetch(
        """
        SELECT
            c.chunk_id::text AS chunk_id,
            c.sequence_no,
            c.text_original,
            c.text_normalized,
            c.text_hash,
            c.source_start,
            c.source_end,
            c.volume,
            c.page,
            c.page_side,
            c.section_path,
            c.section_title,
            c.content_kind,
            tv.openiti_uri AS version_uri,
            tv.quality_status,
            tv.quality_issues,
            tv.source_text_sha256,
            tv.source_metadata_sha256,
            w.openiti_uri AS work_uri,
            w.title_display AS work_title,
            a.openiti_uri AS author_uri,
            a.name_display AS author_name,
            s.provider,
            s.source_url,
            s.release,
            s.license,
            s.copyright_status,
            s.commercial_use_allowed,
            s.attribution_required
        FROM chunks c
        JOIN text_versions tv ON tv.id = c.version_id
        JOIN works w ON w.id = tv.work_id
        JOIN authors a ON a.id = w.author_id
        JOIN sources s ON s.id = tv.source_id
        WHERE c.chunk_id::text = ANY($1::text[])
          AND ($2::boolean OR tv.quality_status <> 'REJECTED')
        """,
        list(chunk_ids),
        include_rejected,
    )

    rows_by_id = {str(row["chunk_id"]): row for row in rows}
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in rows_by_id]
    if missing:
        preview = ", ".join(missing[:3])
        raise RuntimeError(
            "Evidence hydration failed for PostgreSQL chunk ids: " + preview
        )

    hydrated: list[EvidenceSearchResult] = []
    for candidate in candidates:
        row = rows_by_id[candidate.chunk_id]
        hydrated.append(
            EvidenceSearchResult(
                score=float(candidate.score),
                source_score=float(candidate.source_score),
                variant_ranks=tuple(candidate.variant_ranks),
                chunk_id=str(row["chunk_id"]),
                sequence_no=int(row["sequence_no"]),
                text_original=str(row["text_original"]),
                text_normalized=str(row["text_normalized"]),
                text_hash=str(row["text_hash"]),
                source_start=int(row["source_start"]),
                source_end=int(row["source_end"]),
                volume=(int(row["volume"]) if row["volume"] is not None else None),
                page=(int(row["page"]) if row["page"] is not None else None),
                page_side=(str(row["page_side"]) if row["page_side"] is not None else None),
                section_path=_decode_section_path(row["section_path"]),
                section_title=(
                    str(row["section_title"])
                    if row["section_title"] is not None
                    else None
                ),
                content_kind=str(row["content_kind"]),
                version_uri=str(row["version_uri"]),
                quality_status=str(row["quality_status"]),
                quality_issues=tuple(row["quality_issues"] or ()),
                source_text_sha256=str(row["source_text_sha256"]),
                source_metadata_sha256=str(row["source_metadata_sha256"]),
                work_uri=str(row["work_uri"]),
                work_title=(str(row["work_title"]) if row["work_title"] is not None else None),
                author_uri=str(row["author_uri"]),
                author_name=(str(row["author_name"]) if row["author_name"] is not None else None),
                provider=str(row["provider"]),
                source_url=str(row["source_url"]),
                release=(str(row["release"]) if row["release"] is not None else None),
                license=(str(row["license"]) if row["license"] is not None else None),
                copyright_status=(
                    str(row["copyright_status"])
                    if row["copyright_status"] is not None
                    else None
                ),
                commercial_use_allowed=row["commercial_use_allowed"],
                attribution_required=row["attribution_required"],
            )
        )
    return hydrated


async def search_evidence(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 5,
    work_uri: str | None = None,
    include_rejected: bool = False,
) -> tuple[QueryAnalysis, tuple[str, ...], list[EvidenceSearchResult]]:
    """Retrieve source evidence with semantic expansion, then hydrate from PostgreSQL.

    Qdrant contributes candidate identities and ranking only. All text, hashes,
    bibliographic fields and rights metadata returned downstream are read again from
    PostgreSQL before they are exposed as evidence.
    """

    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50")

    analysis, candidates = await search_semantic_expanded(
        conn,
        query,
        limit=limit,
        work_uri=work_uri,
        include_rejected=include_rejected,
    )
    query_variants = expand_query_variants(query)
    hydrated = await hydrate_evidence_candidates(
        conn,
        candidates,
        include_rejected=include_rejected,
    )
    return analysis, query_variants, hydrated
