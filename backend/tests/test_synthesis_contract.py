from __future__ import annotations

from copy import deepcopy

from app.synthesis.contract import build_synthesis_package, validate_synthesis_draft


def _bundle() -> dict:
    return {
        "bundle_version": "evidence_bundle_v1",
        "bundle_id": "eb1_example",
        "bundle_sha256": "a" * 64,
        "query": "المضاربة",
        "normalized_query": "المضاربة",
        "source_ids": ["S1", "S2"],
        "generation_contract": {
            "status": "EVIDENCE_ONLY",
            "generated_answer": None,
            "allowed_citation_ids": ["S1", "S2"],
            "rules": [],
        },
        "sources": [
            {
                "source_id": "S1",
                "rank": 1,
                "score": 0.02,
                "source_score": 0.9,
                "variant_ranks": [None, 1],
                "citation": {
                    "work_uri": "0595IbnRushdHafid.BidayatMujtahid",
                    "version_uri": "0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
                    "volume": 2,
                    "page": 178,
                    "section_path": ["كتاب القراض"],
                    "chunk_id": "1" * 64,
                    "text_hash": "2" * 64,
                    "source_text_sha256": "3" * 64,
                    "source_metadata_sha256": "4" * 64,
                },
                "passage_original": "نص في القراض",
            },
            {
                "source_id": "S2",
                "rank": 2,
                "score": 0.01,
                "source_score": 0.8,
                "variant_ranks": [1, None],
                "citation": {
                    "work_uri": "0595IbnRushdHafid.BidayatMujtahid",
                    "version_uri": "0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
                    "volume": 2,
                    "page": 179,
                    "section_path": ["كتاب القراض", "الباب الأول"],
                    "chunk_id": "5" * 64,
                    "text_hash": "6" * 64,
                    "source_text_sha256": "3" * 64,
                    "source_metadata_sha256": "4" * 64,
                },
                "passage_original": "نص آخر",
            },
        ],
    }


def test_synthesis_package_is_deterministic_and_contains_only_allowed_sources():
    first = build_synthesis_package(_bundle())
    second = build_synthesis_package(_bundle())

    assert first["package_id"] == second["package_id"]
    assert first["package_sha256"] == second["package_sha256"]
    assert first["allowed_citation_ids"] == ["S1", "S2"]
    assert first["generated_answer"] is None
    assert "[S1]" in first["model_context"]
    assert "كتاب القراض" in first["model_context"]


def test_synthesis_package_hash_changes_if_evidence_text_changes():
    original = build_synthesis_package(_bundle())
    changed_bundle = _bundle()
    changed_bundle["sources"][0]["passage_original"] = "نص مختلف"
    changed = build_synthesis_package(changed_bundle)

    assert original["package_sha256"] != changed["package_sha256"]


def test_validation_accepts_structurally_cited_answer():
    package = build_synthesis_package(_bundle())
    result = validate_synthesis_draft(
        package,
        {
            "status": "ANSWERED",
            "answer": "تتعلق المسألة بالقراض [S1].",
            "claims": [
                {
                    "text": "تتعلق المسألة بالقراض.",
                    "citation_ids": ["S1"],
                }
            ],
        },
    )

    assert result["valid"] is True
    assert result["package_integrity_valid"] is True
    assert result["semantic_entailment_checked"] is False


def test_validation_rejects_unknown_and_uncited_claims():
    package = build_synthesis_package(_bundle())
    result = validate_synthesis_draft(
        package,
        {
            "status": "ANSWERED",
            "answer": "Réponse [S99].",
            "claims": [
                {"text": "Première affirmation", "citation_ids": []},
                {"text": "Deuxième affirmation", "citation_ids": ["S99"]},
            ],
        },
    )

    assert result["valid"] is False
    assert result["uncited_claim_indexes"] == [1]
    assert result["unknown_citation_ids"] == ["S99"]


def test_validation_rejects_tampered_package():
    package = build_synthesis_package(_bundle())
    tampered = deepcopy(package)
    tampered["sources"][0]["passage_original"] = "texte modifié après création"

    result = validate_synthesis_draft(
        tampered,
        {
            "status": "INSUFFICIENT_EVIDENCE",
            "answer": "Les preuves sont insuffisantes.",
            "claims": [],
        },
    )

    assert result["valid"] is False
    assert result["package_integrity_valid"] is False
