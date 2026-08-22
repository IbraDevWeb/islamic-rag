from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes.search as search_route
from app.api.deps import get_postgres_connection
from app.main import app
from app.search.lexical import LexicalSearchResult, QueryAnalysis


async def _fake_connection():
    yield object()


async def _fake_search(*args, **kwargs):
    analysis = QueryAnalysis(
        original="الصلاة في السفر",
        normalized="الصلاة في السفر",
        terms=("الصلاة", "السفر"),
    )
    result = LexicalSearchResult(
        score=155.0,
        matched_terms=2,
        total_terms=2,
        phrase_hits=1,
        term_hits=10,
        section_hits=2,
        chunk_id="a" * 64,
        sequence_no=215,
        text_original="# نص أصلي",
        text_normalized="نص اصلي",
        text_hash="b" * 64,
        volume=1,
        page=121,
        page_side=None,
        section_path=(
            "كتاب الصلاة",
            "الباب الرابع في صلاة السفر",
            "الفصل الأول في القصر",
        ),
        section_title="الفصل الأول في القصر",
        content_kind="main_legacy_inferred",
        version_uri="0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
        quality_status="UNREVIEWED",
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        work_title=None,
        author_uri="0595IbnRushdHafid",
        author_name="Ibn Rušd al-Ḥafīd",
        provider="OpenITI",
        source_url="https://example.test/openiti/pinned-version",
        release="OpenITI/0600AH@test",
    )
    return analysis, [result]


def test_search_endpoint_returns_traceable_source_not_generated_answer(monkeypatch) -> None:
    app.dependency_overrides[get_postgres_connection] = _fake_connection
    monkeypatch.setattr(search_route, "search_lexical", _fake_search)

    try:
        client = TestClient(app)
        response = client.get(
            "/search",
            params={
                "q": "الصلاة في السفر",
                "work_uri": "0595IbnRushdHafid.BidayatMujtahid",
                "limit": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval"] == "deterministic_lexical_v1"
    assert payload["generated_answer"] is None
    assert payload["count"] == 1

    result = payload["results"][0]
    citation = result["citation"]
    assert citation["work"] == "بداية المجتهد ونهاية المقتصد"
    assert citation["work_title_source_metadata"] is None
    assert citation["bibliographic_provenance"]["verification_status"] == (
        "VERIFIED_EXTERNAL_CATALOG"
    )
    assert citation["bibliographic_provenance"]["source_name"] == (
        "BnF Catalogue général"
    )
    assert citation["structure_status"] == "INFERRED"
    assert citation["structure_provenance"] == "legacy_pipe_inferred"
    assert citation["volume"] == 1
    assert citation["page"] == 121
    assert citation["chunk_id"] == "a" * 64
    assert citation["text_hash"] == "b" * 64
    assert result["passage_original"] == "# نص أصلي"


def test_search_endpoint_rejects_blank_query_without_searching(monkeypatch) -> None:
    app.dependency_overrides[get_postgres_connection] = _fake_connection

    async def should_not_run(*args, **kwargs):
        raise AssertionError("search_lexical must not run for a blank query")

    monkeypatch.setattr(search_route, "search_lexical", should_not_run)
    try:
        client = TestClient(app)
        response = client.get("/search", params={"q": "   "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Search query must contain non-whitespace characters"
    )


def test_search_endpoint_caps_limit_at_fifty() -> None:
    app.dependency_overrides[get_postgres_connection] = _fake_connection
    try:
        client = TestClient(app)
        response = client.get("/search", params={"q": "الصلاة", "limit": 51})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
