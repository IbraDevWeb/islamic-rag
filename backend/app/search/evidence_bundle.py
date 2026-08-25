from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Sequence

from app.search.evidence import EVIDENCE_RETRIEVAL_ID, EvidenceSearchResult
from app.search.evidence_presentation import build_evidence_payload
from app.search.lexical import QueryAnalysis

EVIDENCE_BUNDLE_VERSION = "evidence_bundle_v1"


def _bundle_integrity_material(
    *,
    normalized_query: str,
    query_variants: Sequence[str],
    sources: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Return the stable material used to identify an evidence bundle.

    Scores are deliberately excluded: the bundle identity follows the query,
    retrieval contract, source order, and immutable source hashes rather than
    floating-point implementation details.
    """

    return {
        "bundle_version": EVIDENCE_BUNDLE_VERSION,
        "normalized_query": normalized_query,
        "query_variants": list(query_variants),
        "retrieval": EVIDENCE_RETRIEVAL_ID,
        "sources": [
            {
                "source_id": source["source_id"],
                "rank": source["rank"],
                "chunk_id": source["citation"]["chunk_id"],
                "text_hash": source["citation"]["text_hash"],
                "source_text_sha256": source["citation"]["source_text_sha256"],
                "source_metadata_sha256": source["citation"]["source_metadata_sha256"],
                "version_uri": source["citation"]["version_uri"],
            }
            for source in sources
        ],
    }


def build_evidence_bundle_payload(
    analysis: QueryAnalysis,
    query_variants: Sequence[str],
    results: Iterable[EvidenceSearchResult],
) -> dict[str, Any]:
    """Build a deterministic, citation-addressable evidence bundle.

    This is intentionally not an answer generator. It turns already hydrated
    PostgreSQL evidence into a stable contract that a future synthesis layer may
    consume. Every source gets an immutable local citation id (S1, S2, ...), while
    the underlying chunk/text/source hashes remain available for verification.
    """

    evidence_payload = build_evidence_payload(analysis, query_variants, results)
    sources: list[dict[str, Any]] = []
    for item in evidence_payload["results"]:
        source_id = f"S{item['rank']}"
        sources.append(
            {
                "source_id": source_id,
                "rank": item["rank"],
                "score": item["score"],
                "source_score": item["source_score"],
                "variant_ranks": item["variant_ranks"],
                "citation": item["citation"],
                "passage_original": item["passage_original"],
            }
        )

    material = _bundle_integrity_material(
        normalized_query=analysis.normalized,
        query_variants=query_variants,
        sources=sources,
    )
    canonical = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    bundle_sha256 = hashlib.sha256(canonical).hexdigest()
    allowed_source_ids = [source["source_id"] for source in sources]

    return {
        "bundle_version": EVIDENCE_BUNDLE_VERSION,
        "bundle_id": f"eb1_{bundle_sha256[:20]}",
        "bundle_sha256": bundle_sha256,
        "query": analysis.original,
        "normalized_query": analysis.normalized,
        "terms": list(analysis.terms),
        "query_variants": list(query_variants),
        "retrieval": EVIDENCE_RETRIEVAL_ID,
        "evidence_count": len(sources),
        "source_ids": allowed_source_ids,
        "generation_contract": {
            "status": "EVIDENCE_ONLY",
            "generated_answer": None,
            "allowed_citation_ids": allowed_source_ids,
            "rules": [
                "A future synthesis layer may cite only source_ids present in this bundle.",
                "Every factual or legal claim must be supported by one or more cited source_ids.",
                "The LLM is never a source and may not invent bibliographic metadata.",
                "If the bundle does not contain sufficient evidence, synthesis must say so explicitly.",
                "Normalized retrieval text is not evidence; passage_original and citation provenance are authoritative.",
            ],
        },
        "sources": sources,
    }
