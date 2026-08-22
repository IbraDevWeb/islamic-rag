from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import asyncpg

from app.ingestion.openiti import OpenITIDocument, metadata_json, normalize_arabic


@dataclass(frozen=True)
class SourceDescriptor:
    provider: str
    source_url: str
    release: str | None = None
    license: str | None = None
    copyright_status: str | None = None
    commercial_use_allowed: bool | None = None
    attribution_required: bool | None = None

    @property
    def source_key(self) -> str:
        identity = json.dumps(
            {
                "provider": self.provider,
                "source_url": self.source_url,
                "release": self.release,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def persist_openiti_document(
    conn: asyncpg.Connection,
    document: OpenITIDocument,
    source: SourceDescriptor,
    *,
    quality_status: str = "UNREVIEWED",
) -> dict[str, int | str]:
    existing_hash = await conn.fetchval(
        "SELECT source_text_sha256 FROM text_versions WHERE openiti_uri = $1",
        document.uri.version_uri,
    )
    if existing_hash is not None and existing_hash != document.text_sha256:
        raise ValueError(
            "Immutable source violation: this OpenITI version URI is already stored "
            "with a different text SHA-256. Ingest it as a distinct pinned source/version "
            "instead of overwriting the original text."
        )

    async with conn.transaction():
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (
                source_key, provider, source_url, release, license,
                copyright_status, commercial_use_allowed, attribution_required
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (source_key) DO UPDATE SET
                provider = EXCLUDED.provider,
                source_url = EXCLUDED.source_url,
                release = EXCLUDED.release,
                license = COALESCE(EXCLUDED.license, sources.license),
                copyright_status = COALESCE(
                    EXCLUDED.copyright_status, sources.copyright_status
                ),
                commercial_use_allowed = COALESCE(
                    EXCLUDED.commercial_use_allowed, sources.commercial_use_allowed
                ),
                attribution_required = COALESCE(
                    EXCLUDED.attribution_required, sources.attribution_required
                ),
                updated_at = NOW()
            RETURNING id
            """,
            source.source_key,
            source.provider,
            source.source_url,
            source.release,
            source.license,
            source.copyright_status,
            source.commercial_use_allowed,
            source.attribution_required,
        )

        author_id = await conn.fetchval(
            """
            INSERT INTO authors (
                openiti_uri, name_display, death_year_ah, metadata, metadata_sha256
            ) VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (openiti_uri) DO UPDATE SET
                name_display = COALESCE(EXCLUDED.name_display, authors.name_display),
                death_year_ah = COALESCE(EXCLUDED.death_year_ah, authors.death_year_ah),
                metadata = CASE
                    WHEN EXCLUDED.metadata = '{}'::jsonb THEN authors.metadata
                    ELSE EXCLUDED.metadata
                END,
                metadata_sha256 = COALESCE(
                    EXCLUDED.metadata_sha256, authors.metadata_sha256
                ),
                updated_at = NOW()
            RETURNING id
            """,
            document.uri.author_uri,
            document.author_name_display,
            document.author_death_year_ah,
            metadata_json(document.author_metadata),
            document.author_metadata_sha256,
        )

        work_id = await conn.fetchval(
            """
            INSERT INTO works (
                author_id, openiti_uri, title_display, genres, metadata, metadata_sha256
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            ON CONFLICT (openiti_uri) DO UPDATE SET
                author_id = EXCLUDED.author_id,
                title_display = COALESCE(EXCLUDED.title_display, works.title_display),
                genres = COALESCE(EXCLUDED.genres, works.genres),
                metadata = CASE
                    WHEN EXCLUDED.metadata = '{}'::jsonb THEN works.metadata
                    ELSE EXCLUDED.metadata
                END,
                metadata_sha256 = COALESCE(
                    EXCLUDED.metadata_sha256, works.metadata_sha256
                ),
                updated_at = NOW()
            RETURNING id
            """,
            author_id,
            document.uri.work_uri,
            document.work_title_display,
            document.work_genres,
            metadata_json(document.book_metadata),
            document.book_metadata_sha256,
        )

        version_id = await conn.fetchval(
            """
            INSERT INTO text_versions (
                work_id, source_id, openiti_uri, version_id, language_code,
                quality_status, quality_issues, metadata, text_header,
                source_text_sha256, source_metadata_sha256
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7::text[], $8::jsonb, $9, $10, $11
            )
            ON CONFLICT (openiti_uri) DO UPDATE SET
                work_id = EXCLUDED.work_id,
                source_id = EXCLUDED.source_id,
                version_id = EXCLUDED.version_id,
                language_code = EXCLUDED.language_code,
                quality_status = CASE
                    WHEN EXCLUDED.quality_status = 'UNREVIEWED'
                        THEN text_versions.quality_status
                    ELSE EXCLUDED.quality_status
                END,
                quality_issues = EXCLUDED.quality_issues,
                metadata = EXCLUDED.metadata,
                text_header = EXCLUDED.text_header,
                source_text_sha256 = EXCLUDED.source_text_sha256,
                source_metadata_sha256 = EXCLUDED.source_metadata_sha256,
                updated_at = NOW()
            RETURNING id
            """,
            work_id,
            source_id,
            document.uri.version_uri,
            document.uri.version_id,
            document.uri.language_code,
            quality_status,
            list(document.quality_issues),
            metadata_json(document.version_metadata),
            document.header,
            document.text_sha256,
            document.version_metadata_sha256,
        )

        await conn.execute("DELETE FROM chunks WHERE version_id = $1", version_id)
        await conn.executemany(
            """
            INSERT INTO chunks (
                chunk_id, version_id, sequence_no, text_original, text_normalized,
                text_hash, volume, page, page_side, section_path, section_title,
                section_text_normalized, content_kind, source_start, source_end
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14, $15
            )
            """,
            [
                (
                    chunk.chunk_id,
                    version_id,
                    chunk.sequence_no,
                    chunk.text_original,
                    chunk.text_normalized,
                    chunk.text_hash,
                    chunk.volume,
                    chunk.page,
                    chunk.page_side,
                    json.dumps(list(chunk.section_path), ensure_ascii=False),
                    chunk.section_title,
                    normalize_arabic(" ".join(chunk.section_path)),
                    chunk.content_kind,
                    chunk.source_start,
                    chunk.source_end,
                )
                for chunk in document.chunks
            ],
        )

    return {
        "source_id": source_id,
        "author_id": author_id,
        "work_id": work_id,
        "version_id": version_id,
        "chunks": len(document.chunks),
        "version_uri": document.uri.version_uri,
    }
