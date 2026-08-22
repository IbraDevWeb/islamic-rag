from __future__ import annotations

from pydantic import BaseModel, Field


class BibliographicProvenance(BaseModel):
    verification_status: str
    scope: str
    source_name: str | None = None
    source_url: str | None = None
    source_record_id: str | None = None
    verified_on: str | None = None
    notes: str | None = None
    work_uri: str | None = None
    title_ar: str | None = None
    title_latin: str | None = None


class Citation(BaseModel):
    author: str | None = None
    author_uri: str
    work: str | None = None
    work_uri: str
    work_title_source_metadata: str | None = None
    work_title_ar: str | None = None
    work_title_latin: str | None = None
    bibliographic_provenance: BibliographicProvenance
    version_uri: str
    volume: int | None = None
    page: int | None = None
    page_side: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_title: str | None = None
    structure_provenance: str
    structure_status: str
    content_kind: str
    chunk_id: str
    text_hash: str
    quality_status: str
    provider: str
    source_url: str
    release: str | None = None


class SearchResult(BaseModel):
    rank: int
    score: float
    coverage: float
    matched_terms: int
    total_terms: int
    phrase_hits: int
    term_hits: int
    section_hits: int
    citation: Citation
    passage_original: str
    passage_normalized: str


class SearchResponse(BaseModel):
    query: str
    normalized_query: str
    terms: list[str]
    count: int
    retrieval: str
    generated_answer: None = None
    results: list[SearchResult]
