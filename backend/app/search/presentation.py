from __future__ import annotations

from typing import Any, Iterable

from app.bibliography.catalog import get_work_bibliography
from app.search.lexical import LexicalSearchResult, QueryAnalysis

RETRIEVAL_ID = "deterministic_lexical_v1"


def _structure_provenance(result: LexicalSearchResult) -> tuple[str, str]:
    if result.content_kind == "main_legacy_inferred":
        return "legacy_pipe_inferred", "INFERRED"
    if result.section_path:
        return "openiti_explicit", "SOURCE_EXPLICIT"
    return "none", "NONE"


def _bibliographic_provenance(result: LexicalSearchResult) -> dict[str, Any]:
    bibliography = get_work_bibliography(result.work_uri)
    if bibliography is not None:
        return bibliography.to_dict()

    if result.work_title:
        return {
            "verification_status": "SOURCE_METADATA",
            "scope": "ingested_openiti_work_metadata",
            "source_name": "OpenITI work metadata",
            "source_url": None,
            "source_record_id": result.work_uri,
            "verified_on": None,
            "notes": (
                "The display title comes from ingested OpenITI work metadata after "
                "placeholder filtering. No independent catalogue verification is "
                "registered for this work URI."
            ),
        }

    return {
        "verification_status": "UNVERIFIED",
        "scope": "none",
        "source_name": None,
        "source_url": None,
        "source_record_id": None,
        "verified_on": None,
        "notes": "No reliable display title is registered for this work URI.",
    }


def build_search_payload(
    analysis: QueryAnalysis,
    results: Iterable[LexicalSearchResult],
    *,
    preview_chars: int | None = None,
) -> dict[str, Any]:
    items = list(results)
    payload: dict[str, Any] = {
        "query": analysis.original,
        "normalized_query": analysis.normalized,
        "terms": list(analysis.terms),
        "count": len(items),
        "retrieval": RETRIEVAL_ID,
        "generated_answer": None,
        "results": [],
    }

    for rank, result in enumerate(items, start=1):
        bibliography = get_work_bibliography(result.work_uri)
        structure_provenance, structure_status = _structure_provenance(result)
        work_display = (
            bibliography.title_ar
            if bibliography is not None
            else result.work_title
        )
        original = result.text_original
        if preview_chars is not None:
            original = original[:preview_chars]

        payload["results"].append(
            {
                "rank": rank,
                "score": round(result.score, 3),
                "coverage": round(result.coverage, 3),
                "matched_terms": result.matched_terms,
                "total_terms": result.total_terms,
                "phrase_hits": result.phrase_hits,
                "term_hits": result.term_hits,
                "section_hits": result.section_hits,
                "citation": {
                    "author": result.author_name,
                    "author_uri": result.author_uri,
                    "work": work_display,
                    "work_uri": result.work_uri,
                    "work_title_source_metadata": result.work_title,
                    "work_title_ar": bibliography.title_ar if bibliography else None,
                    "work_title_latin": bibliography.title_latin if bibliography else None,
                    "bibliographic_provenance": _bibliographic_provenance(result),
                    "version_uri": result.version_uri,
                    "volume": result.volume,
                    "page": result.page,
                    "page_side": result.page_side,
                    "section_path": list(result.section_path),
                    "section_title": result.section_title,
                    "structure_provenance": structure_provenance,
                    "structure_status": structure_status,
                    "content_kind": result.content_kind,
                    "chunk_id": result.chunk_id,
                    "text_hash": result.text_hash,
                    "source_start": result.source_start,
                    "source_end": result.source_end,
                    "source_text_sha256": result.source_text_sha256,
                    "source_metadata_sha256": result.source_metadata_sha256,
                    "quality_status": result.quality_status,
                    "quality_issues": list(result.quality_issues),
                    "provider": result.provider,
                    "source_url": result.source_url,
                    "release": result.release,
                    "rights": {
                        "license": result.license,
                        "copyright_status": result.copyright_status,
                        "commercial_use_allowed": result.commercial_use_allowed,
                        "attribution_required": result.attribution_required,
                    },
                },
                "passage_original": original,
                "passage_normalized": result.text_normalized,
            }
        )

    return payload
