from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_postgres_connection
from app.api.schemas.evidence import EvidenceResponse
from app.search.evidence import search_evidence
from app.search.evidence_presentation import build_evidence_payload

router = APIRouter(tags=["retrieval"])


@router.get(
    "/evidence",
    response_model=EvidenceResponse,
    summary="Retrieve source evidence with semantic expansion",
    description=(
        "Experimental evidence retrieval. Candidate chunk ids are discovered with "
        "multilingual semantic search plus curated terminology expansion, then every "
        "returned passage and citation field is re-read from PostgreSQL before being "
        "exposed. This endpoint does not generate a legal answer."
    ),
    response_description=(
        "Ranked source passages hydrated from PostgreSQL with citation provenance."
    ),
)
async def evidence(
    q: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Arabic or multilingual semantic query.",
        examples=["المضاربة"],
    ),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of evidence passages."),
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
) -> EvidenceResponse:
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

    return EvidenceResponse.model_validate(
        build_evidence_payload(analysis, query_variants, results)
    )
