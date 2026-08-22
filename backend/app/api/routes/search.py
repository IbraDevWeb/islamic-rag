from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_postgres_connection
from app.api.schemas.search import SearchResponse
from app.search.lexical import search_lexical
from app.search.presentation import build_search_payload

router = APIRouter(tags=["retrieval"])


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search the ingested source corpus",
    description=(
        "Deterministic lexical retrieval over normalized source text. "
        "This endpoint returns source passages and provenance only; it does not "
        "generate a legal answer or treat an LLM as a source. REJECTED text "
        "versions are excluded unless include_rejected=true is explicitly set."
    ),
    response_description="Ranked source passages with bibliographic and textual provenance.",
)
async def search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Arabic or Latin-script lexical query.",
        examples=["الصلاة في السفر"],
    ),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results."),
    work_uri: str | None = Query(
        None,
        max_length=255,
        description="Optional exact OpenITI work URI filter.",
        examples=["0595IbnRushdHafid.BidayatMujtahid"],
    ),
    include_rejected: bool = Query(
        False,
        description="Include source versions explicitly marked REJECTED.",
    ),
    conn: asyncpg.Connection = Depends(get_postgres_connection),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query must contain non-whitespace characters",
        )

    try:
        analysis, results = await search_lexical(
            conn,
            query,
            limit=limit,
            work_uri=work_uri,
            include_rejected=include_rejected,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except asyncpg.PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search storage is temporarily unavailable",
        ) from exc

    return SearchResponse.model_validate(build_search_payload(analysis, results))
