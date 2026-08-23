# Evidence retrieval

## Purpose

`/evidence` is the first API layer designed for downstream answer generation without letting a derived search index become a source of truth.

It is still **retrieval only**. It does not generate a fatwa, legal conclusion, or natural-language answer.

## Pipeline

```text
query
  -> curated terminology expansion
  -> multilingual E5 semantic retrieval in Qdrant
  -> ranked chunk ids
  -> exact PostgreSQL hydration
  -> original passages + citations + hashes
```

The preferred experimental retrieval id is:

```text
semantic_multilingual_e5_large_v1_curated_fiqh_aliases_v1_pg_hydrated_v1
```

## Why hydrate from PostgreSQL

Qdrant is a derived vector index. Its payload can help locate a chunk, but it is not the authoritative copy of the source.

For every candidate returned by semantic retrieval, `/evidence` re-reads the chunk from PostgreSQL and returns the stored:

- `text_original`;
- normalized search projection;
- chunk and text hashes;
- source byte/character offsets;
- volume, page and section hierarchy;
- OpenITI work/version identifiers;
- quality status and issues;
- author/work display metadata;
- provider/source URL;
- rights metadata when known.

If Qdrant returns a chunk id that PostgreSQL cannot hydrate, the evidence request fails instead of silently trusting the derived payload.

## Endpoint

Example:

```powershell
Invoke-RestMethod "http://localhost:8000/evidence?q=المضاربة&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5"
```

The response includes:

```text
query
normalized_query
terms
query_variants
retrieval
results[]
  rank
  score
  source_score
  variant_ranks
  citation
  passage_original
  passage_normalized
generated_answer = null
```

`query_variants` exposes exactly which retrieval-only terminology variants were considered. This is auditable and must not be confused with scholarly equivalence claims.

## Current status

This endpoint is experimental. It uses `semantic-expanded` because the current 51-case development baseline showed materially better top-rank quality and latency than the first cross-encoder reranker.

The deterministic public `/search` endpoint is intentionally unchanged.

The next layer after evidence retrieval can consume only the hydrated evidence objects, not raw Qdrant payloads. Any future answer generator should be constrained to these passages and should be able to abstain when evidence is insufficient.
