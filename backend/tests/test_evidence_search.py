from __future__ import annotations

import pytest

from app.search.evidence import hydrate_evidence_candidates
from app.search.expanded import ExpandedSearchResult


class FakeConnection:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    async def fetch(self, *_args, **_kwargs):
        return self.rows


def _candidate(chunk_id: str = "a" * 64) -> ExpandedSearchResult:
    return ExpandedSearchResult(
        score=0.031,
        source_score=0.91,
        chunk_id=chunk_id,
        section_path=("كتاب القراض",),
        section_title="كتاب القراض",
        volume=2,
        page=178,
        page_side=None,
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        version_uri="0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
        quality_status="UNREVIEWED",
        variant_ranks=(None, 1),
    )


def _row(chunk_id: str = "a" * 64) -> dict:
    return {
        "chunk_id": chunk_id,
        "sequence_no": 900,
        "text_original": "نص أصلي",
        "text_normalized": "نص اصلي",
        "text_hash": "b" * 64,
        "source_start": 100,
        "source_end": 200,
        "volume": 2,
        "page": 178,
        "page_side": None,
        "section_path": ["كتاب القراض"],
        "section_title": "كتاب القراض",
        "content_kind": "main_legacy_inferred",
        "version_uri": "0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
        "quality_status": "UNREVIEWED",
        "quality_issues": [],
        "source_text_sha256": "c" * 64,
        "source_metadata_sha256": "d" * 64,
        "work_uri": "0595IbnRushdHafid.BidayatMujtahid",
        "work_title": None,
        "author_uri": "0595IbnRushdHafid",
        "author_name": "Ibn Rušd al-Ḥafīd",
        "provider": "OpenITI",
        "source_url": "https://github.com/OpenITI/0600AH",
        "release": "test",
        "license": None,
        "copyright_status": None,
        "commercial_use_allowed": None,
        "attribution_required": None,
    }


@pytest.mark.asyncio
async def test_evidence_hydration_uses_postgres_text_and_preserves_rank_metadata():
    result = await hydrate_evidence_candidates(
        FakeConnection([_row()]),
        [_candidate()],
    )

    assert len(result) == 1
    evidence = result[0]
    assert evidence.text_original == "نص أصلي"
    assert evidence.text_normalized == "نص اصلي"
    assert evidence.score == 0.031
    assert evidence.source_score == 0.91
    assert evidence.variant_ranks == (None, 1)
    assert evidence.section_path == ("كتاب القراض",)
    assert evidence.source_text_sha256 == "c" * 64


@pytest.mark.asyncio
async def test_evidence_hydration_fails_if_derived_candidate_is_missing_in_postgres():
    with pytest.raises(RuntimeError, match="Evidence hydration failed"):
        await hydrate_evidence_candidates(
            FakeConnection([]),
            [_candidate()],
        )
