from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from app.core.config import settings
from app.evaluation.retrieval import load_benchmark, run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate deterministic retrieval against a manually labelled benchmark."
        )
    )
    parser.add_argument(
        "--dataset",
        default="evals/retrieval_bidayat_v1.json",
        help="Path to a retrieval benchmark JSON file.",
    )
    parser.add_argument(
        "--fail-under-hit-rate",
        type=float,
        default=None,
        help="Exit non-zero if hit-rate is below this threshold (0.0-1.0).",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.fail_under_hit_rate is not None and not 0 <= args.fail_under_hit_rate <= 1:
        raise SystemExit("--fail-under-hit-rate must be between 0.0 and 1.0")

    benchmark = load_benchmark(args.dataset)
    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        summary = await run_benchmark(conn, benchmark)
    finally:
        await conn.close()

    payload = summary.to_dict()
    payload["description"] = benchmark.description
    payload["label_provenance"] = benchmark.label_provenance
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if (
        args.fail_under_hit_rate is not None
        and summary.hit_rate < args.fail_under_hit_rate
    ):
        return 2
    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
