from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from app.core.config import settings
from app.evaluation.retrieval import RetrievalBenchmark, load_benchmark


def used_top_level_sections(benchmark: RetrievalBenchmark) -> set[str]:
    """Return top-level كتاب labels already used by a tuning benchmark."""

    used: set[str] = set()
    for case in benchmark.cases:
        for fragment in case.expected_section_contains:
            value = fragment.strip()
            if value.startswith("كتاب "):
                used.add(value)
                break
    return used


def filter_unused_sections(
    rows: list[dict],
    *,
    used_sections: set[str],
    min_chunks: int,
) -> list[dict]:
    return [
        row
        for row in rows
        if row["top_section"] not in used_sections and int(row["chunks"]) >= min_chunks
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "List corpus-backed top-level sections not already used by the tuning "
            "benchmark, so a genuinely new holdout set can be authored without "
            "inventing section labels."
        )
    )
    parser.add_argument(
        "--dataset",
        default="evals/retrieval_bidayat_baseline_v2.json",
        help="Benchmark whose labelled top-level sections should be excluded.",
    )
    parser.add_argument(
        "--work-uri",
        default="0595IbnRushdHafid.BidayatMujtahid",
        help="Exact OpenITI work URI to inspect.",
    )
    parser.add_argument(
        "--min-chunks",
        type=int,
        default=2,
        help="Only show sections containing at least this many chunks.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.min_chunks < 1:
        raise SystemExit("--min-chunks must be positive")

    benchmark = load_benchmark(args.dataset)
    used_sections = used_top_level_sections(benchmark)

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        records = await conn.fetch(
            """
            SELECT
                c.section_path ->> 0 AS top_section,
                COUNT(*)::int AS chunks,
                MIN(c.page)::int AS first_page,
                MAX(c.page)::int AS last_page
            FROM chunks c
            JOIN text_versions tv ON tv.id = c.version_id
            JOIN works w ON w.id = tv.work_id
            WHERE w.openiti_uri = $1
              AND jsonb_array_length(c.section_path) > 0
              AND c.section_path ->> 0 IS NOT NULL
            GROUP BY c.section_path ->> 0
            ORDER BY MIN(c.sequence_no), c.section_path ->> 0
            """,
            args.work_uri,
        )
    finally:
        await conn.close()

    rows = [dict(record) for record in records]
    candidates = filter_unused_sections(
        rows,
        used_sections=used_sections,
        min_chunks=args.min_chunks,
    )

    payload = {
        "work_uri": args.work_uri,
        "source_dataset": benchmark.dataset_id,
        "benchmark_sha256": benchmark.benchmark_sha256,
        "used_top_level_sections": len(used_sections),
        "corpus_top_level_sections": len(rows),
        "holdout_candidate_sections": len(candidates),
        "candidates": candidates,
        "note": (
            "These are corpus-backed candidates only. They are not relevance labels. "
            "Choose new queries manually, freeze the holdout, then evaluate the already "
            "selected hybrid profile without retuning weights on that holdout."
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
