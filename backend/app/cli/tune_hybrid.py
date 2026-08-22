from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from app.core.config import settings
from app.evaluation.hybrid_tuning import (
    FusionWeights,
    run_hybrid_weight_sweep,
)
from app.evaluation.retrieval import load_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark weighted lexical/semantic RRF combinations on one fixed "
            "retrieval dataset without rebuilding document embeddings."
        )
    )
    parser.add_argument(
        "--dataset",
        default="evals/retrieval_bidayat_baseline_v2.json",
        help="Path to the retrieval benchmark JSON file.",
    )
    parser.add_argument(
        "--lexical-weights",
        default="0.50,0.40,0.30,0.20,0.10",
        help=(
            "Comma-separated lexical weights. Semantic weight is computed as 1-w. "
            "Default: 0.50,0.40,0.30,0.20,0.10."
        ),
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=25,
        help="Number of candidates fetched once from each source retriever per query.",
    )
    parser.add_argument(
        "--skip-label-validation",
        action="store_true",
        help="Skip corpus validation of benchmark target sections.",
    )
    return parser


def _parse_weights(value: str) -> tuple[FusionWeights, ...]:
    items: list[FusionWeights] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            lexical = float(raw)
        except ValueError as exc:
            raise SystemExit(f"Invalid lexical weight: {raw}") from exc
        if not 0 <= lexical <= 1:
            raise SystemExit("Every lexical weight must be between 0.0 and 1.0")
        items.append(FusionWeights(lexical=lexical, semantic=1.0 - lexical))
    if not items:
        raise SystemExit("--lexical-weights must contain at least one value")
    return tuple(items)


async def _run(args: argparse.Namespace) -> int:
    benchmark = load_benchmark(args.dataset)
    weights = _parse_weights(args.lexical_weights)

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        report = await run_hybrid_weight_sweep(
            conn,
            benchmark,
            weights=weights,
            pool_size=args.pool_size,
            validate_labels=not args.skip_label_validation,
        )
    finally:
        await conn.close()

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
