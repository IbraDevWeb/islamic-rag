CREATE TABLE IF NOT EXISTS sources (
    id BIGSERIAL PRIMARY KEY,
    source_key CHAR(64) NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    source_url TEXT NOT NULL,
    release TEXT,
    license TEXT,
    copyright_status TEXT,
    commercial_use_allowed BOOLEAN,
    attribution_required BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS authors (
    id BIGSERIAL PRIMARY KEY,
    openiti_uri TEXT NOT NULL UNIQUE,
    name_display TEXT,
    death_year_ah INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_sha256 CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS works (
    id BIGSERIAL PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES authors(id) ON DELETE RESTRICT,
    openiti_uri TEXT NOT NULL UNIQUE,
    title_display TEXT,
    genres TEXT,
    madhhab TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_sha256 CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS text_versions (
    id BIGSERIAL PRIMARY KEY,
    work_id BIGINT NOT NULL REFERENCES works(id) ON DELETE RESTRICT,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    openiti_uri TEXT NOT NULL UNIQUE,
    version_id TEXT NOT NULL,
    language_code TEXT,
    quality_status TEXT NOT NULL DEFAULT 'UNREVIEWED'
        CHECK (quality_status IN ('UNREVIEWED', 'ACCEPTED', 'REVIEW_REQUIRED', 'REJECTED')),
    quality_issues TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    text_header TEXT NOT NULL,
    source_text_sha256 CHAR(64) NOT NULL,
    source_metadata_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id CHAR(64) NOT NULL UNIQUE,
    version_id BIGINT NOT NULL REFERENCES text_versions(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    text_original TEXT NOT NULL,
    text_normalized TEXT NOT NULL,
    text_hash CHAR(64) NOT NULL,
    volume INTEGER,
    page INTEGER,
    page_side CHAR(1) CHECK (page_side IS NULL OR page_side IN ('A', 'B')),
    section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    section_title TEXT,
    content_kind TEXT NOT NULL DEFAULT 'main',
    source_start INTEGER NOT NULL,
    source_end INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(version_id, sequence_no),
    CHECK (source_start >= 0),
    CHECK (source_end > source_start)
);

CREATE INDEX IF NOT EXISTS idx_works_author_id ON works(author_id);
CREATE INDEX IF NOT EXISTS idx_text_versions_work_id ON text_versions(work_id);
CREATE INDEX IF NOT EXISTS idx_text_versions_quality_status ON text_versions(quality_status);
CREATE INDEX IF NOT EXISTS idx_chunks_version_id ON chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_chunks_location ON chunks(version_id, volume, page);
