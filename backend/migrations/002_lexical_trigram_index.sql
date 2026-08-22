-- Accelerate deterministic lexical candidate retrieval without changing ranking semantics.
-- pg_trgm is bundled with PostgreSQL and supports GIN/GiST indexes for LIKE/ILIKE.
-- This is an acceleration layer only; it is not presented as BM25 or semantic search.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_chunks_text_normalized_trgm
    ON chunks USING GIN (text_normalized gin_trgm_ops);
