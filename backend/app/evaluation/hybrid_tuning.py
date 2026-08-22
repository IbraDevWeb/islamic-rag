from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from time import perf_counter
from typing import Iterable, Sequence

import asyncpg

from app.evaluation.retrieval import (
    RetrievalBenchmark,
    RetrievalCaseResult,
    RetrievalEvaluationSummary,
    corpus_fingerprint,
    evaluate_results,
    summarize_evaluation,
    validate_benchmark_against_corpus,
)
from app.search.hybrid import reciprocal_rank_fusion
from app.search.lexical import RETRIEVAL_ID as LEXICAL_RETRIEVAL_ID, search_lexical
from app.search.semantic import (
    SEMANTIC_RETRIEVAL_ID,
    search_semantic,
    validate_semantic_index_fresh,
)


@dataclass(frozen=True)
class FusionWeights:
    lexical: float
    semantic: float

    @property
    def label(self) -> str:
        return f"lexical_{self.lexical:.2f}_semantic_{self.semantic:.2f}"


@dataclass(frozen=True)
class FusionCandidateSummary:
    label: str
    lexical_weight: float
    semantic_weight: float
    pass_rate: float
    hit_rate: float
    hit_rate_at_1: float
    hit_rate_at_3: float
    mean_reciprocal_rank: float
    mean_precision_at_k: float
    mean_first_relevant_rank: float | None
    failed_case_ids: tuple[str, ...]
    by_query_type: dict[str, dict[str, float | int | None]]
    by_difficulty: dict[str, dict[str, float | int | None]]


@dataclass(frozen=True)
class HybridTuningReport:
    dataset_id: str
    benchmark_sha256: str
    corpus_fingerprint: str
    lexical_retrieval_id: str
    semantic_retrieval_id: str
    cases: int
    pool_size: int
    retrieval_elapsed_seconds: float
    selection_rule: str
    best_candidate: FusionCandidateSummary
    candidates: tuple[FusionCandidateSummary, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["best_candidate"] = asdict(self.best_candidate)
        payload["candidates"] = [asdict(candidate) for candidate in self.candidates]
        return payload


def default_weight_grid() -> tuple[FusionWeights, ...]:
    return (
        FusionWeights(0.50, 0.50),
        FusionWeights(0.40, 0.60),
        FusionWeights(0.30, 0.70),
        FusionWeights(0.20, 0.80),
        FusionWeights(0.10, 0.90),
    )


def validate_weight_grid(weights: Iterable[FusionWeights]) -> tuple[FusionWeights, ...]:
    items = tuple(weights)
    if not items:
        raise ValueError("At least one fusion weight configuration is required")

    seen: set[tuple[float, float]] = set()
    for item in items:
        if not math.isfinite(item.lexical) or not math.isfinite(item.semantic):
            raise ValueError("Fusion weights must be finite")
        if item.lexical < 0 or item.semantic < 0:
            raise ValueError("Fusion weights must be non-negative")
        total = item.lexical + item.semantic
        if total <= 0:
            raise ValueError("At least one fusion weight must be positive")
        key = (round(item.lexical / total, 8), round(item.semantic / total, 8))
        if key in seen:
            raise ValueError("Duplicate normalized fusion weight configuration")
        seen.add(key)
    return items


def _candidate_from_summary(
    weights: FusionWeights,
    summary: RetrievalEvaluationSummary,
) -> FusionCandidateSummary:
    return FusionCandidateSummary(
        label=weights.label,
        lexical_weight=weights.lexical,
        semantic_weight=weights.semantic,
        pass_rate=summary.pass_rate,
        hit_rate=summary.hit_rate,
        hit_rate_at_1=summary.hit_rate_at_1,
        hit_rate_at_3=summary.hit_rate_at_3,
        mean_reciprocal_rank=summary.mean_reciprocal_rank,
        mean_precision_at_k=summary.mean_precision_at_k,
        mean_first_relevant_rank=summary.mean_first_relevant_rank,
        failed_case_ids=tuple(
            result.case_id for result in summary.results if not result.passed
        ),
        by_query_type=summary.by_query_type,
        by_difficulty=summary.by_difficulty,
    )


def select_best_candidate(
    candidates: Sequence[FusionCandidateSummary],
) -> FusionCandidateSummary:
    if not candidates:
        raise ValueError("No fusion candidates to select from")

    # Primary goal: preserve strict benchmark coverage. Then maximize top-1 quality,
    # MRR and precision. If all measured metrics tie, prefer the candidate that
    # relies less on the semantic branch so lexical evidence retains more influence.
    return max(
        candidates,
        key=lambda item: (
            item.pass_rate,
            item.hit_rate_at_1,
            item.mean_reciprocal_rank,
            item.mean_precision_at_k,
            -item.semantic_weight,
        ),
    )


async def run_hybrid_weight_sweep(
    conn: asyncpg.Connection,
    benchmark: RetrievalBenchmark,
    *,
    weights: Iterable[FusionWeights] | None = None,
    pool_size: int = 25,
    validate_labels: bool = True,
) -> HybridTuningReport:
    if pool_size < 1 or pool_size > 100:
        raise ValueError("pool_size must be between 1 and 100")
    largest_k = max(case.k for case in benchmark.cases)
    if pool_size < largest_k:
        raise ValueError(
            f"pool_size must be at least the benchmark maximum k ({largest_k})"
        )
    weight_grid = validate_weight_grid(weights or default_weight_grid())

    if validate_labels:
        await validate_benchmark_against_corpus(conn, benchmark)
    await validate_semantic_index_fresh(conn)
    fingerprint = await corpus_fingerprint(conn, benchmark)

    started = perf_counter()
    source_rankings: list[tuple[Sequence, Sequence]] = []
    for case in benchmark.cases:
        _, lexical_results = await search_lexical(
            conn,
            case.query,
            limit=pool_size,
            work_uri=case.work_uri,
        )
        _, semantic_results = await search_semantic(
            conn,
            case.query,
            limit=pool_size,
            work_uri=case.work_uri,
        )
        source_rankings.append((tuple(lexical_results), tuple(semantic_results)))
    retrieval_elapsed = perf_counter() - started

    candidate_summaries: list[FusionCandidateSummary] = []
    for config in weight_grid:
        case_results: list[RetrievalCaseResult] = []
        for case, (lexical_results, semantic_results) in zip(
            benchmark.cases,
            source_rankings,
            strict=True,
        ):
            fused = reciprocal_rank_fusion(
                lexical_results,
                list(semantic_results),
                limit=case.k,
                lexical_weight=config.lexical,
                semantic_weight=config.semantic,
            )
            case_results.append(evaluate_results(case, fused))

        summary = summarize_evaluation(
            benchmark,
            case_results,
            corpus_fingerprint=fingerprint,
        )
        summary = replace(
            summary,
            retrieval_id=f"hybrid_weighted_rrf_{config.label}",
        )
        candidate_summaries.append(_candidate_from_summary(config, summary))

    best = select_best_candidate(candidate_summaries)
    return HybridTuningReport(
        dataset_id=benchmark.dataset_id,
        benchmark_sha256=benchmark.benchmark_sha256,
        corpus_fingerprint=fingerprint,
        lexical_retrieval_id=LEXICAL_RETRIEVAL_ID,
        semantic_retrieval_id=SEMANTIC_RETRIEVAL_ID,
        cases=len(benchmark.cases),
        pool_size=pool_size,
        retrieval_elapsed_seconds=round(retrieval_elapsed, 3),
        selection_rule=(
            "maximize pass_rate, then Hit@1, then MRR, then Precision@k; "
            "if still tied, prefer less semantic weight"
        ),
        best_candidate=best,
        candidates=tuple(candidate_summaries),
    )
