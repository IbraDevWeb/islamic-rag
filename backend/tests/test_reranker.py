from types import SimpleNamespace

import pytest

from app.search.reranker import (
    HydratedRerankerCandidate,
    build_reranker_document,
    search_semantic_expanded_reranked,
    select_best_variant_scores,
)


def _hydrated(chunk_id: str, text: str, page: int) -> HydratedRerankerCandidate:
    return HydratedRerankerCandidate(
        chunk_id=chunk_id,
        sequence_no=page,
        text_original=text,
        text_hash=f"hash-{chunk_id}",
        volume=1,
        page=page,
        page_side=None,
        section_path=("كتاب القراض",),
        section_title="كتاب القراض",
        version_uri="version",
        quality_status="UNREVIEWED",
        source_text_sha256="source-sha",
        work_uri="work",
    )


def test_build_reranker_document_preserves_original_text() -> None:
    candidate = _hydrated("a", "نص أصلي مضبوط", 10)

    document = build_reranker_document(candidate)

    assert document.startswith("كتاب القراض\n")
    assert document.endswith("نص أصلي مضبوط")


def test_select_best_variant_scores_uses_strongest_variant() -> None:
    selected = select_best_variant_scores(
        candidate_count=2,
        query_variants=("المضاربة", "القراض"),
        scores=(0.10, 0.91, 0.80, 0.20),
    )

    assert selected == [(0.91, "القراض"), (0.80, "المضاربة")]


def test_select_best_variant_scores_prefers_original_variant_on_score_tie() -> None:
    selected = select_best_variant_scores(
        candidate_count=1,
        query_variants=("المضاربة", "القراض"),
        scores=(0.8, 0.8),
    )

    assert selected == [(0.8, "المضاربة")]


def test_select_best_variant_scores_rejects_wrong_score_count() -> None:
    with pytest.raises(ValueError, match="Expected 4"):
        select_best_variant_scores(
            candidate_count=2,
            query_variants=("q", "alias"),
            scores=(0.1, 0.2, 0.3),
        )


@pytest.mark.asyncio
async def test_reranked_search_reorders_candidates_without_using_qdrant_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = SimpleNamespace(
        score=0.95,
        chunk_id="first",
        section_path=("كتاب الشركة",),
        section_title="كتاب الشركة",
        volume=1,
        page=1,
        page_side=None,
        work_uri="work",
        version_uri="version",
        quality_status="UNREVIEWED",
    )
    second = SimpleNamespace(
        score=0.90,
        chunk_id="second",
        section_path=("كتاب القراض",),
        section_title="كتاب القراض",
        volume=1,
        page=2,
        page_side=None,
        work_uri="work",
        version_uri="version",
        quality_status="UNREVIEWED",
    )

    async def fake_search(*args, **kwargs):
        analysis = SimpleNamespace(original="المضاربة")
        return analysis, [first, second]

    async def fake_hydrate(*args, **kwargs):
        return {
            "first": _hydrated("first", "postgres text one", 1),
            "second": _hydrated("second", "postgres text two", 2),
        }

    def fake_score(pairs):
        # Candidate-major order, two query variants per candidate.
        assert any("postgres text one" in document for _, document in pairs)
        assert any("postgres text two" in document for _, document in pairs)
        return [0.10, 0.20, 0.70, 0.95]

    monkeypatch.setattr(
        "app.search.reranker.search_semantic_expanded",
        fake_search,
    )
    monkeypatch.setattr(
        "app.search.reranker.hydrate_reranker_candidates",
        fake_hydrate,
    )
    monkeypatch.setattr(
        "app.search.reranker._score_query_document_pairs",
        fake_score,
    )

    _, results = await search_semantic_expanded_reranked(
        object(),
        "المضاربة",
        limit=2,
        candidate_pool=2,
    )

    assert [result.chunk_id for result in results] == ["second", "first"]
    assert results[0].text_original == "postgres text two"
    assert results[0].candidate_rank == 2
    assert results[0].best_query_variant == "القراض"
