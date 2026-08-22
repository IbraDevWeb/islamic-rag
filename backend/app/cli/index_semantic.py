from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter

import asyncpg
from qdrant_client import models

from app.core.config import settings
from app.search.semantic import (
    EMBEDDING_SCHEMA_VERSION,
    build_embedding_passage,
    fetch_semantic_index_rows,
    get_embedding_model,
    get_qdrant_client,
    qdrant_point_id,
    semantic_chunk_fingerprint,
    upsert_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the derived dense Qdrant index from immutable PostgreSQL chunks."
        )
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the dedicated dense collection if it already exists.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Embedding/upsert batch size. Defaults to EMBEDDING_BATCH_SIZE.",
    )
    return parser


def _payload(row) -> dict:
    section_path = row["section_path"]
    if isinstance(section_path, str):
        section_path = json.loads(section_path)
    return {
        "chunk_id": row["chunk_id"],
        "work_uri": row["work_uri"],
        "version_uri": row["version_uri"],
        "quality_status": row["quality_status"],
        "sequence_no": row["sequence_no"],
        "volume": row["volume"],
        "page": row["page"],
        "page_side": row["page_side"],
        "section_path": section_path or [],
        "section_title": row["section_title"],
        "text_hash": row["text_hash"],
        "source_text_sha256": row["source_text_sha256"],
        "embedding_model": settings.embedding_model,
        "embedding_schema_version": EMBEDDING_SCHEMA_VERSION,
    }


def _build_qdrant_index(rows, *, recreate: bool, batch_size: int) -> int:
    client = get_qdrant_client()
    collection = settings.qdrant_dense_collection

    exists = client.collection_exists(collection_name=collection)
    if exists and not recreate:
        raise RuntimeError(
            f"Qdrant collection {collection!r} already exists. "
            "Use --recreate only when intentionally rebuilding this derived index."
        )
    if exists:
        client.delete_collection(collection_name=collection)

    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=settings.embedding_dimension,
            distance=models.Distance.COSINE,
        ),
    )

    for field in ("work_uri", "version_uri", "quality_status"):
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )

    model = get_embedding_model()
    indexed = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        texts = []
        for row in batch:
            section_path = row["section_path"]
            if isinstance(section_path, str):
                section_path = json.loads(section_path)
            texts.append(
                build_embedding_passage(
                    row["text_normalized"],
                    tuple(section_path or ()),
                )
            )
        vectors = list(model.embed(texts, batch_size=batch_size))
        points = [
            models.PointStruct(
                id=qdrant_point_id(row["chunk_id"]),
                vector=vector.tolist(),
                payload=_payload(row),
            )
            for row, vector in zip(batch, vectors, strict=True)
        ]
        client.upsert(
            collection_name=collection,
            points=points,
            wait=True,
        )
        indexed += len(points)
        print(f"Indexed {indexed}/{len(rows)} chunks", flush=True)

    qdrant_count = client.count(
        collection_name=collection,
        exact=True,
    ).count
    if qdrant_count != len(rows):
        raise RuntimeError(
            f"Qdrant count mismatch: expected {len(rows)}, got {qdrant_count}"
        )
    return qdrant_count


async def _run(args: argparse.Namespace) -> int:
    batch_size = args.batch_size or settings.embedding_batch_size
    if batch_size < 1 or batch_size > 256:
        raise SystemExit("--batch-size must be between 1 and 256")

    conn = await asyncpg.connect(settings.postgres_dsn)
    rows = await fetch_semantic_index_rows(conn)
    if not rows:
        await conn.close()
        raise SystemExit("No non-rejected chunks are available to index")

    fingerprint = semantic_chunk_fingerprint(rows)
    await upsert_manifest(
        conn,
        collection_name=settings.qdrant_dense_collection,
        corpus_fingerprint=fingerprint,
        point_count=0,
        status="BUILDING",
    )

    started = perf_counter()
    try:
        point_count = await asyncio.to_thread(
            _build_qdrant_index,
            rows,
            recreate=args.recreate,
            batch_size=batch_size,
        )
    except Exception as exc:
        await upsert_manifest(
            conn,
            collection_name=settings.qdrant_dense_collection,
            corpus_fingerprint=fingerprint,
            point_count=0,
            status="FAILED",
            last_error=f"{type(exc).__name__}: {exc}",
        )
        await conn.close()
        raise

    await upsert_manifest(
        conn,
        collection_name=settings.qdrant_dense_collection,
        corpus_fingerprint=fingerprint,
        point_count=point_count,
        status="READY",
    )
    await conn.close()

    elapsed = perf_counter() - started
    print(
        json.dumps(
            {
                "status": "READY",
                "collection": settings.qdrant_dense_collection,
                "embedding_model": settings.embedding_model,
                "embedding_dimension": settings.embedding_dimension,
                "embedding_schema_version": EMBEDDING_SCHEMA_VERSION,
                "points": point_count,
                "corpus_fingerprint": fingerprint,
                "elapsed_seconds": round(elapsed, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
