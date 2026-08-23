from types import SimpleNamespace

from app.search.expanded import fuse_query_variant_rankings


def _result(chunk_id: str, score: float, page: int):
    return SimpleNamespace(
        score=score,
        chunk_id=chunk_id,
        section_path=("كتاب القراض",),
        section_title="كتاب القراض",
        volume=1,
        page=page,
        page_side=None,
        work_uri="work",
        version_uri="version",
        quality_status="UNREVIEWED",
    )


def test_variant_fusion_rewards_candidate_seen_in_multiple_variants() -> None:
    first = [_result("shared", 0.8, 1), _result("a", 0.7, 2)]
    second = [_result("b", 0.9, 3), _result("shared", 0.85, 1)]

    fused = fuse_query_variant_rankings([first, second], limit=3)

    assert fused[0].chunk_id == "shared"
    assert fused[0].variant_ranks == (1, 2)


def test_variant_fusion_uses_source_score_to_break_single_variant_rank_tie() -> None:
    original = [_result("original-only", 0.80, 1)]
    alias = [_result("alias-target", 0.95, 2)]

    fused = fuse_query_variant_rankings([original, alias], limit=2)

    assert [item.chunk_id for item in fused] == ["alias-target", "original-only"]


def test_variant_fusion_respects_limit() -> None:
    fused = fuse_query_variant_rankings(
        [[_result("a", 0.9, 1), _result("b", 0.8, 2)]],
        limit=1,
    )

    assert len(fused) == 1
    assert fused[0].chunk_id == "a"
