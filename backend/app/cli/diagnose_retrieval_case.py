from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Sequence

import asyncpg

from app.core.config import settings
from app.evaluation.retrieval import RetrievalBenchmarkCase, load_benchmark
from app.ingestion.openiti import normalize_arabic
from app.search.hybrid import HYBRID_RETRIEVAL_ID, reciprocal_rank_fusion
from app.search.lexical import RETRIEVAL_ID as LEXICAL_RETRIEVAL_ID, search_lexical
from app.search.semantic import (
    SEMANTIC_RETRIEVAL_ID,
    search_semantic,
    validate_semantic_index_fresh,
)


def _result_is_relevant(case: RetrievalBenchmarkCase, result: Any) -> bool:
    normalized_path = normalize_arabic(" / ".join(result.section_path))
    for expected in case.expected_section_contains:
        if normalize_arabic(expected) not in normalized_path:
            return False

    if case.expected_volume is not None and result.volume != case.expected_volume:
        return False
    if case.expected_page_min is not None:
        if result.page is None or result.page < case.expected_page_min:
            return False
    if case.expected_page_max is not None:
        if result.page is None or result.page > case.expected_page_max:
            return False
    return True


def _first_relevant_rank(case: RetrievalBenchmarkCase, results: Sequence[Any]) -> int | None:
    return next(
        (
            rank
            for rank, result in enumerate(results, start=1)
            if _result_is_relevant(case, result)
        ),
        None,
    )


def _result_payload(case: RetrievalBenchmarkCase, result: Any, rank: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rank": rank,
        "relevant": _result_is_relevant(case, result),
        "score": round(float(result.score), 8),
        "chunk_id": result.chunk_id,
        "page": result.page,
        "section_path": list(result.section_path),
    }
    if hasattr(result, "lexical_rank"):
        payload["lexical_rank"] = result.lexical_rank
    if hasattr(result, "semantic_rank"):
        payload["semantic_rank"] = result.semantic_rank
    return payload


def _branch_payload(
    case: RetrievalBenchmarkCase,
    results: Sequence[Any],
    *,
    show: int,
) -> dict[str, Any]:
    first_rank = _first_relevant_rank(case, results)
    return {
        "first_relevant_rank": first_rank,
        "hit_within_original_k": first_rank is not None and first_rank <= case.k,
        "hit_within_depth": first_rank is not None,
        "reranker_candidate_status": (
            "already_in_original_top_k"
            if first_rank is not None and first_rank <= case.k
            else "recoverable_from_deeper_pool"
            if first_rank is not None
            else "missing_from_candidate_pool"
        ),
        "results": [
            _result_payload(case, result, rank)
            for rank, result in enumerate(results[:show], start=1)
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect one frozen benchmark case at greater retrieval depth before "
            "deciding whether a reranker can help."
        )
    )
    parser.add_argument(
        "--dataset",
        default="evals/retrieval_bidayat_holdout_v1.json",
        help="Path to a retrieval benchmark JSON file.",
    )
    parser.add_argument(
        "--case-id",
        required=True,
        help="Exact benchmark case id to inspect.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=50,
        help="Candidate depth to fetch from lexical and semantic retrieval (1-100).",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=10,
        help="Number of ranked results to print per branch (1-depth).",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if not 1 <= args.depth <= 100:
        raise SystemExit("--depth must be between 1 and 100")
    if not 1 <= args.show <= args.depth:
        raise SystemExit("--show must be between 1 and --depth")

    benchmark = load_benchmark(args.dataset)
    case = next((item for item in benchmark.cases if item.case_id == args.case_id), None)
    if case is None:
        available = ", ".join(item.case_id for item in benchmark.cases)
        raise SystemExit(f"Unknown case id: {args.case_id}. Available: {available}")

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        await validate_semantic_index_fresh(conn)
        _, lexical_results = await search_lexical(
            conn,
            case.query,
            limit=args.depth,
            work_uri=case.work_uri,
        )
        _, semantic_results = await search_semantic(
            conn,
            case.query,
            limit=args.depth,
            work_uri=case.work_uri,
        )
    finally:
        await conn.close()

    hybrid_results = reciprocal_rank_fusion(
        lexical_results,
        semantic_results,
        limit=args.depth,
    )

    payload = {
        "dataset_id": benchmark.dataset_id,
        "benchmark_sha256": benchmark.benchmark_sha256,
        "case_id": case.case_id,
        "query": case.query,
        "expected_section_contains": list(case.expected_section_contains),
        "original_k": case.k,
        "required_rank": case.required_rank,
        "diagnostic_depth": args.depth,
        "retrieval_ids": {
            "lexical": LEXICAL_RETRIEVAL_ID,
            "semantic": SEMANTIC_RETRIEVAL_ID,
            "hybrid": HYBRID_RETRIEVAL_ID,
        },
        "branches": {
            "lexical": _branch_payload(case, lexical_results, show=args.show),
            "semantic": _branch_payload(case, semantic_results, show=args.show),
            "hybrid": _branch_payload(case, hybrid_results, show=args.show),
        },
        "interpretation": (
            "A reranker can only rescue this case if a relevant candidate exists in "
            "the deeper pool. If every branch reports missing_from_candidate_pool, "
            "improve candidate generation or terminology coverage before reranking."
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
