from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import asyncpg

from app.core.config import settings
from app.db.migrations import apply_migrations
from app.ingestion.openiti import build_openiti_document, document_summary
from app.ingestion.repository import SourceDescriptor, persist_openiti_document


QUALITY_STATUSES = ("UNREVIEWED", "ACCEPTED", "REVIEW_REQUIRED", "REJECTED")


def _optional_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    if normalized == "unknown":
        return None
    raise argparse.ArgumentTypeError("expected yes, no, or unknown")


def _read(path: str | None) -> str | None:
    if path is None:
        return None
    return Path(path).read_text(encoding="utf-8-sig")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse and ingest one OpenITI text without embeddings or LLMs."
    )
    parser.add_argument("--text", required=True, help="OpenITI mARkdown text file")
    parser.add_argument("--version-yml", required=True, help="OpenITI YML-1 version file")
    parser.add_argument("--book-yml", help="OpenITI YML-2 book file")
    parser.add_argument("--author-yml", help="OpenITI YML-3 author file")
    parser.add_argument("--source-url", help="Canonical URL for this text version")
    parser.add_argument("--provider", default="OpenITI")
    parser.add_argument("--release")
    parser.add_argument("--license")
    parser.add_argument("--copyright-status")
    parser.add_argument(
        "--commercial-use-allowed",
        type=_optional_bool,
        default=None,
        metavar="yes|no|unknown",
    )
    parser.add_argument(
        "--attribution-required",
        type=_optional_bool,
        default=None,
        metavar="yes|no|unknown",
    )
    parser.add_argument(
        "--quality-status", choices=QUALITY_STATUSES, default="UNREVIEWED"
    )
    parser.add_argument("--max-chars", type=int, default=1800)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only; do not write to PostgreSQL",
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    text_raw = _read(args.text)
    version_yml_raw = _read(args.version_yml)
    assert text_raw is not None and version_yml_raw is not None

    document = build_openiti_document(
        text_raw,
        version_yml_raw,
        _read(args.book_yml),
        _read(args.author_yml),
        max_chars=args.max_chars,
    )

    summary = document_summary(document)
    summary["quality_status"] = args.quality_status

    if args.dry_run:
        summary["mode"] = "dry-run"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if not args.source_url:
        raise SystemExit("--source-url is required unless --dry-run is used")

    source = SourceDescriptor(
        provider=args.provider,
        source_url=args.source_url,
        release=args.release,
        license=args.license,
        copyright_status=args.copyright_status,
        commercial_use_allowed=args.commercial_use_allowed,
        attribution_required=args.attribution_required,
    )

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        await apply_migrations(conn)
        persisted = await persist_openiti_document(
            conn,
            document,
            source,
            quality_status=args.quality_status,
        )
    finally:
        await conn.close()

    summary.update(persisted)
    summary["mode"] = "persisted"
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
