from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas.search import Citation


class EvidenceResult(BaseModel):
    rank: int
    score: float
    source_score: float
    variant_ranks: list[int | None]
    citation: Citation
    passage_original: str
    passage_normalized: str


class EvidenceResponse(BaseModel):
    query: str
    normalized_query: str
    terms: list[str]
    query_variants: list[str]
    count: int
    retrieval: str
    generated_answer: None = None
    results: list[EvidenceResult]
