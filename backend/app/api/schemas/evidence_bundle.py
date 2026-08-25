from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas.search import Citation


class EvidenceBundleSource(BaseModel):
    source_id: str
    rank: int
    score: float
    source_score: float
    variant_ranks: list[int | None]
    citation: Citation
    passage_original: str


class GenerationContract(BaseModel):
    status: str
    generated_answer: None = None
    allowed_citation_ids: list[str]
    rules: list[str]


class EvidenceBundleResponse(BaseModel):
    bundle_version: str
    bundle_id: str
    bundle_sha256: str
    query: str
    normalized_query: str
    terms: list[str]
    query_variants: list[str]
    retrieval: str
    evidence_count: int
    source_ids: list[str]
    generation_contract: GenerationContract
    sources: list[EvidenceBundleSource]
