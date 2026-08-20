from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from app.core.config import settings
from app.search.lexical import search_lexical


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search ingested Arabic chunks with deterministic lexical ranking."
    )
    parser.add_argument("query", help="Arabic lexical query")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--candidate-limit", type=int)
    parser.add_argument("--work-uri", help="Restrict search to one OpenITI work URI")
    parser.add_argument(
        "--include-rejected",
        action="store_true",
        help="Include text versions whose quality status is REJECTED",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=700,
        help="Maximum number of original source characters printed per result",
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    if args.preview_chars < 100 or args.preview_chars > 5000:
        raise SystemExit("--preview-chars must be between 100 and 5000")

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        analysis, results = await search_lexical(
            conn,
            args.query,
            limit=args.limit,
            candidate_limit=args.candidate_limit,
            work_uri=args.work_uri,
            include_rejected=args.include_rejected,
        )
    finally:
        await conn.close()

    payload = {
        "query": analysis.original,
        "normalized_query": analysis.normalized,
        "terms": list(analysis.terms),
        "count": len(results),
        "retrieval": "deterministic_lexical_v1",
        "results": [],
    }

    for rank, result in enumerate(results, start=1):
        payload["results"].append(
            {
                "rank": rank,
                "score": round(result.score, 3),
                "coverage": round(result.coverage, 3),
                "matched_terms": result.matched_terms,
                "total_terms": result.total_terms,
                "phrase_hits": result.phrase_hits,
                "term_hits": result.term_hits,
                "section_hits": result.section_hits,
                "citation": {
                    "author": result.author_name,
                    "author_uri": result.author_uri,
                    "work": result.work_title,
                    "work_uri": result.work_uri,
                    "version_uri": result.version_uri,
                    "volume": result.volume,
                    "page": result.page,
                    "page_side": result.page_side,
                    "section_path": list(result.section_path),
                    "section_title": result.section_title,
                    "chunk_id": result.chunk_id,
                    "text_hash": result.text_hash,
                    "quality_status": result.quality_status,
                    "provider": result.provider,
                    "source_url": result.source_url,
                    "release": result.release,
                },
                "passage_original": result.text_original[: args.preview_chars],
            }
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
