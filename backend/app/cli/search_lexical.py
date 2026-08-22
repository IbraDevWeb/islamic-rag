from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from app.core.config import settings
from app.search.lexical import search_lexical
from app.search.presentation import build_search_payload


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

    payload = build_search_payload(
        analysis,
        results,
        preview_chars=args.preview_chars,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
