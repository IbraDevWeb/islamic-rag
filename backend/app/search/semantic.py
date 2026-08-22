from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

import asyncpg
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.ingestion.openiti import normalize_arabic
from app.search.lexical import QueryAnalysis, analyze_query

SEMANTIC_RETRIEVAL_ID = "semantic_multilingual_e5_large_v1"
EMBEDDING_SCHEMA_VERSION = 1
_POINT_NAMESPACE = uuid.UUID("df7db06b-c9f7-4ecf-ae4c-759ea9e51b6b")


@dataclass(frozen=True)
class SemanticSearchResult:
    score: float
    chunk_id: str
    section_path: tuple[str, ...]
    section_title: str | None
    volume: int | None
    page: int | None
    page_side: str | None
    work_uri: str
    version_uri: str
    quality_status: str
    text_hash: str | None = None
    source_text_sha256: str | None = None


@dataclass(frozen=True)
class SemanticIndexManifest:
    collection_name: str
    embedding_model: str
    embedding_dimension: int
    embedding_schema_version: int
    corpus_fingerprint: str
    point_count: int
    status: str
    last_error: str | None


def qdrant_point_id(chunk_id: str) -> str:
    """Map an immutable chunk SHA identity to a stable Qdrant UUID."""

    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


def build_embedding_passage(
    text_normalized: str,
    section_path: Sequence[str],
) -> str:
    """Build derived embedding text without altering evidentiary source text."""

    section = normalize_arabic(" / ".join(section_path)) if section_path else ""
    body = text_normalized.strip()
    if section:
        return f"passage: {section}\n{body}"
    return f"passage: {body}"


def build_embedding_query(query: str) -> str:
    normalized = normalize_arabic(query).strip()
    return f"query: {normalized}"


def semantic_chunk_fingerprint(rows: Sequence[Any]) -> str:
    """Fingerprint exact chunk identities represented by a semantic index."""

    digest = hashlib.sha256()
    for row in rows:
        record = {
            "chunk_id": str(row["chunk_id"]),
            "text_hash": str(row["text_hash"]),
            "work_uri": str(row["work_uri"]),
            "version_uri": str(row["version_uri"]),
            "quality_status": str(row["quality_status"]),
            "sequence_no": int(row["sequence_no"]),
        }
        digest.update(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(
        model_name=settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
    )


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


async def fetch_semantic_index_rows(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT
            c.chunk_id,
            c.sequence_no,
            c.text_normalized,
            c.text_hash,
            c.volume,
            c.page,
            c.page_side,
            c.section_path,
            c.section_title,
            tv.openiti_uri AS version_uri,
            tv.quality_status,
            tv.source_text_sha256,
            w.openiti_uri AS work_uri
        FROM chunks c
        JOIN text_versions tv ON tv.id = c.version_id
        JOIN works w ON w.id = tv.work_id
        WHERE tv.quality_status <> 'REJECTED'
        ORDER BY w.openiti_uri, tv.openiti_uri, c.sequence_no, c.chunk_id
        """
    )


def _decode_section_path(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
    else:
        decoded = value
    if isinstance(decoded, list):
        return tuple(str(item) for item in decoded if item)
    return (str(decoded),)


async def upsert_manifest(
    conn: asyncpg.Connection,
    *,
    collection_name: str,
    corpus_fingerprint: str,
    point_count: int,
    status: str,
    last_error: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO semantic_index_manifests (
            collection_name,
            embedding_model,
            embedding_dimension,
            embedding_schema_version,
            corpus_fingerprint,
            point_count,
            status,
            last_error
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (collection_name) DO UPDATE SET
            embedding_model = EXCLUDED.embedding_model,
            embedding_dimension = EXCLUDED.embedding_dimension,
            embedding_schema_version = EXCLUDED.embedding_schema_version,
            corpus_fingerprint = EXCLUDED.corpus_fingerprint,
            point_count = EXCLUDED.point_count,
            status = EXCLUDED.status,
            last_error = EXCLUDED.last_error,
            updated_at = NOW()
        """,
        collection_name,
        settings.embedding_model,
        settings.embedding_dimension,
        EMBEDDING_SCHEMA_VERSION,
        corpus_fingerprint,
        point_count,
        status,
        last_error,
    )


async def get_manifest(conn: asyncpg.Connection) -> SemanticIndexManifest | None:
    row = await conn.fetchrow(
        """
        SELECT
            collection_name,
            embedding_model,
            embedding_dimension,
            embedding_schema_version,
            corpus_fingerprint,
            point_count,
            status,
            last_error
        FROM semantic_index_manifests
        WHERE collection_name = $1
        """,
        settings.qdrant_dense_collection,
    )
    if row is None:
        return None
    return SemanticIndexManifest(
        collection_name=row["collection_name"],
        embedding_model=row["embedding_model"],
        embedding_dimension=row["embedding_dimension"],
        embedding_schema_version=row["embedding_schema_version"],
        corpus_fingerprint=row["corpus_fingerprint"],
        point_count=row["point_count"],
        status=row["status"],
        last_error=row["last_error"],
    )


async def assert_semantic_index_ready(conn: asyncpg.Connection) -> SemanticIndexManifest:
    manifest = await get_manifest(conn)
    if manifest is None:
        raise RuntimeError(
            "Semantic index is not built. Run python -m app.cli.index_semantic first."
        )
    if manifest.status != "READY":
        raise RuntimeError(
            f"Semantic index manifest status is {manifest.status}; rebuild it before use."
        )
    if manifest.embedding_model != settings.embedding_model:
        raise RuntimeError(
            "Semantic index embedding model differs from current configuration; rebuild it."
        )
    if manifest.embedding_dimension != settings.embedding_dimension:
        raise RuntimeError(
            "Semantic index embedding dimension differs from current configuration; rebuild it."
        )
    if manifest.embedding_schema_version != EMBEDDING_SCHEMA_VERSION:
        raise RuntimeError(
            "Semantic index schema version differs from current code; rebuild it."
        )
    return manifest


async def validate_semantic_index_fresh(conn: asyncpg.Connection) -> SemanticIndexManifest:
    """Verify manifest, exact chunk fingerprint, and Qdrant point count once per run."""

    manifest = await assert_semantic_index_ready(conn)
    rows = await fetch_semantic_index_rows(conn)
    current_fingerprint = semantic_chunk_fingerprint(rows)
    if current_fingerprint != manifest.corpus_fingerprint:
        raise RuntimeError(
            "Semantic index is stale: PostgreSQL chunk fingerprint changed. Rebuild it."
        )
    if len(rows) != manifest.point_count:
        raise RuntimeError(
            "Semantic index manifest point count differs from PostgreSQL. Rebuild it."
        )

    def qdrant_count() -> int:
        return int(
            get_qdrant_client().count(
                collection_name=settings.qdrant_dense_collection,
                exact=True,
            ).count
        )

    actual_count = await asyncio.to_thread(qdrant_count)
    if actual_count != manifest.point_count:
        raise RuntimeError(
            "Semantic index Qdrant point count differs from its manifest. Rebuild it."
        )
    return manifest


def _semantic_filter(
    *,
    work_uri: str | None,
    include_rejected: bool,
) -> models.Filter | None:
    must: list[models.FieldCondition] = []
    must_not: list[models.FieldCondition] = []
    if work_uri is not None:
        must.append(
            models.FieldCondition(
                key="work_uri",
                match=models.MatchValue(value=work_uri),
            )
        )
    if not include_rejected:
        must_not.append(
            models.FieldCondition(
                key="quality_status",
                match=models.MatchValue(value="REJECTED"),
            )
        )
    if not must and not must_not:
        return None
    return models.Filter(must=must or None, must_not=must_not or None)


def _query_qdrant(
    query: str,
    *,
    limit: int,
    work_uri: str | None,
    include_rejected: bool,
) -> list[SemanticSearchResult]:
    client = get_qdrant_client()
    model = get_embedding_model()
    query_vector = next(model.embed([build_embedding_query(query)])).tolist()
    response = client.query_points(
        collection_name=settings.qdrant_dense_collection,
        query=query_vector,
        query_filter=_semantic_filter(
            work_uri=work_uri,
            include_rejected=include_rejected,
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    results: list[SemanticSearchResult] = []
    for point in response.points:
        payload = point.payload or {}
        results.append(
            SemanticSearchResult(
                score=float(point.score),
                chunk_id=str(payload.get("chunk_id", "")),
                section_path=_decode_section_path(payload.get("section_path")),
                section_title=(
                    str(payload["section_title"])
                    if payload.get("section_title") is not None
                    else None
                ),
                volume=(int(payload["volume"]) if payload.get("volume") is not None else None),
                page=(int(payload["page"]) if payload.get("page") is not None else None),
                page_side=(
                    str(payload["page_side"])
                    if payload.get("page_side") is not None
                    else None
                ),
                work_uri=str(payload.get("work_uri", "")),
                version_uri=str(payload.get("version_uri", "")),
                quality_status=str(payload.get("quality_status", "")),
                text_hash=(
                    str(payload["text_hash"])
                    if payload.get("text_hash") is not None
                    else None
                ),
                source_text_sha256=(
                    str(payload["source_text_sha256"])
                    if payload.get("source_text_sha256") is not None
                    else None
                ),
            )
        )
    return results


async def search_semantic(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    work_uri: str | None = None,
    include_rejected: bool = False,
) -> tuple[QueryAnalysis, list[SemanticSearchResult]]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    analysis = analyze_query(query)
    await assert_semantic_index_ready(conn)
    results = await asyncio.to_thread(
        _query_qdrant,
        query,
        limit=limit,
        work_uri=work_uri,
        include_rejected=include_rejected,
    )
    return analysis, results
