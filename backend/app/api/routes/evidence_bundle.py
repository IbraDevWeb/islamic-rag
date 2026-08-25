from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_postgres_connection
from app.api.schemas.evidence_bundle import EvidenceBundleResponse
from app.search.evidence import search_evidence
from app.search.evidence_bundle import build_evidence_bundle_payload

router = APIRouter(tags=["retrieval"])


@router.get(
    "/evidence-bundle",
    response_model=EvidenceBundleResponse,
    summary="Build a deterministic citation-addressable evidence bundle",
    description=(
        "Retrieves semantic evidence with curated terminology expansion, rehydrates "
        "all source text and citation metadata from PostgreSQL, and assigns stable "
        "bundle-local source ids such as S1 and S2. No legal answer is generated."
    ),
)
async def evidence_bundle(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(5, ge=1, le=20),
    work_uri: str | None = Query(None, max_length=255),
    include_rejected: bool = Query(False),
    conn: asyncpg.Connection = Depends(get_postgres_connection),
) -> EvidenceBundleResponse:
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence query must contain non-whitespace characters",
        )

    try:
        analysis, query_variants, results = await search_evidence(
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
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic evidence index is unavailable, stale, or inconsistent",
        ) from exc
    except asyncpg.PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evidence storage is temporarily unavailable",
        ) from exc

    return EvidenceBundleResponse.model_validate(
        build_evidence_bundle_payload(analysis, query_variants, results)
    )
