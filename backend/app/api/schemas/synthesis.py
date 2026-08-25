from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.search import Citation


class SynthesisSource(BaseModel):
    source_id: str
    rank: int
    passage_original: str
    citation: Citation


class SynthesisPackageResponse(BaseModel):
    contract_version: str
    status: str
    package_id: str
    package_sha256: str
    evidence_bundle_id: str
    evidence_bundle_sha256: str
    question: str
    normalized_question: str
    allowed_citation_ids: list[str]
    instructions: list[str]
    output_schema: dict[str, Any]
    generated_answer: None = None
    sources: list[SynthesisSource]
    model_context: str


class DraftClaim(BaseModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)


class SynthesisDraft(BaseModel):
    status: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE"]
    answer: str
    claims: list[DraftClaim] = Field(default_factory=list)


class SynthesisValidationRequest(BaseModel):
    package: SynthesisPackageResponse
    draft: SynthesisDraft


class SynthesisValidationResponse(BaseModel):
    valid: bool
    package_id: str | None = None
    package_integrity_valid: bool
    status: str
    allowed_citation_ids: list[str]
    inline_citation_ids: list[str]
    uncited_claim_indexes: list[int]
    unknown_citation_ids: list[str]
    errors: list[str]
    semantic_entailment_checked: bool
    note: str
