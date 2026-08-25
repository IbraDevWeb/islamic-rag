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


class SynthesisGenerateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    work_uri: str | None = Field(default=None, max_length=255)
    include_rejected: bool = False


class SynthesisGenerationMetadata(BaseModel):
    provider: str
    model: str
    elapsed_ms: float
    done_reason: str | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None


class SynthesisGenerationResponse(BaseModel):
    status: Literal[
        "STRUCTURALLY_VALID_PENDING_ENTAILMENT",
        "REJECTED_STRUCTURAL_VALIDATION",
    ]
    package_id: str
    evidence_bundle_id: str
    provider: SynthesisGenerationMetadata
    draft: SynthesisDraft
    structural_validation: SynthesisValidationResponse
    semantic_entailment_checked: bool = False
    releasable_answer: None = None
    note: str
