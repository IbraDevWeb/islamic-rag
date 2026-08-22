-- Make structural headings first-class lexical retrieval evidence.
--
-- `section_path` remains the authoritative structured JSON representation.
-- `section_text_normalized` is a denormalized search projection used only for
-- retrieval. Existing rows are backfilled conservatively from their stored
-- section path; future ingestions populate the normalized value in Python.

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS section_text_normalized TEXT NOT NULL DEFAULT '';

UPDATE chunks c
SET section_text_normalized = COALESCE(
    (
        SELECT string_agg(value, ' ' ORDER BY ordinality)
        FROM jsonb_array_elements_text(c.section_path)
             WITH ORDINALITY AS section(value, ordinality)
    ),
    ''
)
WHERE c.section_text_normalized = ''
  AND jsonb_array_length(c.section_path) > 0;

CREATE INDEX IF NOT EXISTS idx_chunks_section_text_normalized_trgm
    ON chunks USING GIN (section_text_normalized gin_trgm_ops);
