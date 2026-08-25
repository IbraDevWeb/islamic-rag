from __future__ import annotations

from app.search.evidence import EvidenceSearchResult
from app.search.evidence_bundle import build_evidence_bundle_payload
from app.search.lexical import analyze_query


def _evidence(chunk: str, text_hash: str, page: int) -> EvidenceSearchResult:
    return EvidenceSearchResult(
        score=0.03,
        source_score=0.9,
        variant_ranks=(None, 1),
        chunk_id=chunk,
        sequence_no=page,
        text_original="نص أصلي",
        text_normalized="نص اصلي",
        text_hash=text_hash,
        source_start=100,
        source_end=200,
        volume=2,
        page=page,
        page_side=None,
        section_path=("كتاب القراض",),
        section_title="كتاب القراض",
        content_kind="main_legacy_inferred",
        version_uri="0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
        quality_status="UNREVIEWED",
        quality_issues=(),
        source_text_sha256="c" * 64,
        source_metadata_sha256="d" * 64,
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        work_title=None,
        author_uri="0595IbnRushdHafid",
        author_name="Ibn Rušd al-Ḥafīd",
        provider="OpenITI",
        source_url="https://github.com/OpenITI/0600AH",
        release="test",
        license=None,
        copyright_status=None,
        commercial_use_allowed=None,
        attribution_required=None,
    )


def test_bundle_assigns_citation_ids_and_is_deterministic():
    analysis = analyze_query("المضاربة")
    results = [
        _evidence("a" * 64, "1" * 64, 179),
        _evidence("b" * 64, "2" * 64, 180),
    ]

    first = build_evidence_bundle_payload(
        analysis,
        ("المضاربة", "القراض"),
        results,
    )
    second = build_evidence_bundle_payload(
        analysis,
        ("المضاربة", "القراض"),
        results,
    )

    assert first["bundle_id"] == second["bundle_id"]
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first["source_ids"] == ["S1", "S2"]
    assert first["sources"][0]["source_id"] == "S1"
    assert first["sources"][1]["source_id"] == "S2"
    assert first["generation_contract"]["generated_answer"] is None
    assert first["generation_contract"]["allowed_citation_ids"] == ["S1", "S2"]


def test_bundle_identity_changes_when_source_order_changes():
    analysis = analyze_query("المضاربة")
    first = _evidence("a" * 64, "1" * 64, 179)
    second = _evidence("b" * 64, "2" * 64, 180)

    bundle_a = build_evidence_bundle_payload(
        analysis,
        ("المضاربة", "القراض"),
        [first, second],
    )
    bundle_b = build_evidence_bundle_payload(
        analysis,
        ("المضاربة", "القراض"),
        [second, first],
    )

    assert bundle_a["bundle_sha256"] != bundle_b["bundle_sha256"]
