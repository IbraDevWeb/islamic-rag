import pytest

from app.evaluation.hybrid_tuning import (
    FusionCandidateSummary,
    FusionWeights,
    default_weight_grid,
    select_best_candidate,
    validate_weight_grid,
)


def _candidate(
    *,
    lexical: float,
    semantic: float,
    pass_rate: float,
    hit_at_1: float,
    mrr: float,
    precision: float,
) -> FusionCandidateSummary:
    return FusionCandidateSummary(
        label=f"l{lexical}-s{semantic}",
        lexical_weight=lexical,
        semantic_weight=semantic,
        pass_rate=pass_rate,
        hit_rate=1.0,
        hit_rate_at_1=hit_at_1,
        hit_rate_at_3=1.0,
        mean_reciprocal_rank=mrr,
        mean_precision_at_k=precision,
        mean_first_relevant_rank=1.0,
        failed_case_ids=(),
        by_query_type={},
        by_difficulty={},
    )


def test_default_weight_grid_matches_planned_semantic_sweep() -> None:
    grid = default_weight_grid()

    assert [(item.lexical, item.semantic) for item in grid] == [
        (0.50, 0.50),
        (0.40, 0.60),
        (0.30, 0.70),
        (0.20, 0.80),
        (0.10, 0.90),
    ]


def test_selection_prioritizes_strict_pass_rate_before_hit_at_1() -> None:
    perfect_coverage = _candidate(
        lexical=0.4,
        semantic=0.6,
        pass_rate=1.0,
        hit_at_1=0.94,
        mrr=0.96,
        precision=0.87,
    )
    better_top1_but_misses_case = _candidate(
        lexical=0.1,
        semantic=0.9,
        pass_rate=0.98,
        hit_at_1=0.98,
        mrr=0.99,
        precision=0.90,
    )

    assert select_best_candidate([better_top1_but_misses_case, perfect_coverage]) == (
        perfect_coverage
    )


def test_selection_uses_hit_at_1_then_mrr_after_equal_pass_rate() -> None:
    first = _candidate(
        lexical=0.4,
        semantic=0.6,
        pass_rate=1.0,
        hit_at_1=0.96,
        mrr=0.97,
        precision=0.88,
    )
    second = _candidate(
        lexical=0.2,
        semantic=0.8,
        pass_rate=1.0,
        hit_at_1=0.98,
        mrr=0.96,
        precision=0.86,
    )

    assert select_best_candidate([first, second]) == second


def test_selection_prefers_more_lexical_in_complete_metric_tie() -> None:
    more_lexical = _candidate(
        lexical=0.4,
        semantic=0.6,
        pass_rate=1.0,
        hit_at_1=0.98,
        mrr=0.99,
        precision=0.9,
    )
    more_semantic = _candidate(
        lexical=0.2,
        semantic=0.8,
        pass_rate=1.0,
        hit_at_1=0.98,
        mrr=0.99,
        precision=0.9,
    )

    assert select_best_candidate([more_semantic, more_lexical]) == more_lexical


def test_weight_grid_rejects_duplicate_normalized_ratios() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_weight_grid(
            [
                FusionWeights(1.0, 1.0),
                FusionWeights(0.5, 0.5),
            ]
        )
