from types import SimpleNamespace

import pytest

from app.search.hybrid import (
    HYBRID_DEFAULT_LEXICAL_WEIGHT,
    HYBRID_DEFAULT_SEMANTIC_WEIGHT,
    HYBRID_RETRIEVAL_ID,
    reciprocal_rank_fusion,
)
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


def test_hybrid_v1_profile_is_frozen() -> None:
    assert HYBRID_DEFAULT_LEXICAL_WEIGHT == 0.125
    assert HYBRID_DEFAULT_SEMANTIC_WEIGHT == 0.875
    assert HYBRID_DEFAULT_LEXICAL_WEIGHT + HYBRID_DEFAULT_SEMANTIC_WEIGHT == 1.0
    assert HYBRID_RETRIEVAL_ID == "hybrid_rrf_l0125_s0875_lexical_v2_e5_large_v1"


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


def test_semantic_weight_can_override_lexical_tie_break() -> None:
    lexical = [_lexical("lexical-first", 1), _lexical("semantic-first", 2)]
    semantic = [_semantic("semantic-first", 2), _semantic("lexical-first", 1)]

    equal = reciprocal_rank_fusion(lexical, semantic, limit=2)
    semantic_heavy = reciprocal_rank_fusion(
        lexical,
        semantic,
        limit=2,
        lexical_weight=0.2,
        semantic_weight=0.8,
    )

    assert equal[0].chunk_id == "lexical-first"
    assert semantic_heavy[0].chunk_id == "semantic-first"


def test_rrf_normalizes_equivalent_weight_ratios() -> None:
    lexical = [_lexical("a", 1), _lexical("b", 2)]
    semantic = [_semantic("b", 2), _semantic("a", 1)]

    first = reciprocal_rank_fusion(
        lexical,
        semantic,
        limit=2,
        lexical_weight=1,
        semantic_weight=3,
    )
    second = reciprocal_rank_fusion(
        lexical,
        semantic,
        limit=2,
        lexical_weight=0.25,
        semantic_weight=0.75,
    )

    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert [item.score for item in first] == pytest.approx([item.score for item in second])


def test_rrf_rejects_invalid_weights() -> None:
    lexical = [_lexical("a", 1)]
    semantic = [_semantic("a", 1)]

    with pytest.raises(ValueError, match="non-negative"):
        reciprocal_rank_fusion(
            lexical,
            semantic,
            limit=1,
            lexical_weight=-0.1,
            semantic_weight=1.1,
        )

    with pytest.raises(ValueError, match="At least one"):
        reciprocal_rank_fusion(
            lexical,
            semantic,
            limit=1,
            lexical_weight=0,
            semantic_weight=0,
        )
