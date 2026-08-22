-- Track Qdrant semantic indexes as derived, reproducible projections of PostgreSQL corpus data.
-- PostgreSQL remains the source of truth. A semantic index is valid only when its manifest
-- is READY and its corpus fingerprint matches the indexed chunk set.

CREATE TABLE IF NOT EXISTS semantic_index_manifests (
    collection_name TEXT PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0),
    embedding_schema_version INTEGER NOT NULL CHECK (embedding_schema_version > 0),
    corpus_fingerprint TEXT NOT NULL,
    point_count BIGINT NOT NULL CHECK (point_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('BUILDING', 'READY', 'FAILED')),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_semantic_index_manifests_status
    ON semantic_index_manifests(status);
