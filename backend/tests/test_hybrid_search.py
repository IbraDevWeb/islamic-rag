from types import SimpleNamespace

from app.search.hybrid import reciprocal_rank_fusion
from app.search.semantic import SemanticSearchResult


def _lexical(chunk_id: str, page: int):
    return SimpleNamespace(
        chunk_id=chunk_id,
        section_path=("كتاب الصلاة",),
        section_title="كتاب الصلاة",
        volume=1,
        page=page,
        page_side=None,
        work_uri="work",
        version_uri="version",
        quality_status="UNREVIEWED",
    )


def _semantic(chunk_id: str, page: int) -> SemanticSearchResult:
    return SemanticSearchResult(
        score=0.9,
        chunk_id=chunk_id,
        section_path=("كتاب الصلاة",),
        section_title="كتاب الصلاة",
        volume=1,
        page=page,
        page_side=None,
        work_uri="work",
        version_uri="version",
        quality_status="UNREVIEWED",
    )


def test_rrf_rewards_agreement_between_retrievers() -> None:
    lexical = [_lexical("shared", 1), _lexical("lexical-only", 2)]
    semantic = [_semantic("semantic-only", 3), _semantic("shared", 1)]

    fused = reciprocal_rank_fusion(lexical, semantic, limit=3)

    assert fused[0].chunk_id == "shared"
    assert fused[0].lexical_rank == 1
    assert fused[0].semantic_rank == 2


def test_rrf_keeps_semantic_only_candidates() -> None:
    fused = reciprocal_rank_fusion(
        [_lexical("lexical-only", 2)],
        [_semantic("semantic-only", 3)],
        limit=2,
    )

    assert {result.chunk_id for result in fused} == {"lexical-only", "semantic-only"}
