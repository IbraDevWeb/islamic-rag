# OpenITI ingestion — phase 2

This phase is deliberately deterministic: no LLM and no embeddings.

## What is implemented

1. Parse the OpenITI version URI (`Author.Work.Version`).
2. Parse YML-1 (version), YML-2 (book), and YML-3 (author) metadata.
3. Keep the source text immutable by storing SHA-256 hashes and rejecting a silent overwrite when the same version URI has different text.
4. Split the OpenITI header at `#META#Header#End#`.
5. Treat `PageV##P###` / `FolioV##P###` markers as page-end markers. A page number is never fabricated when no marker exists.
6. Track `### |`, `### ||`, ... section headings and paratext kinds (`EDITOR`, `PARATEXT`, `APPENDIX`).
7. Build deterministic, non-overlapping chunks that do not cross an explicit page boundary or section context.
8. Store the exact source slice in `text_original` and a separate Arabic-normalized value in `text_normalized`.
9. Store authors, works, text versions, provenance, licensing fields, quality state, and chunks in PostgreSQL.
10. Keep licensing booleans nullable so unknown rights are not guessed.

## Database migration

```powershell
docker compose exec api python -m app.cli.migrate
```

## First candidate corpus item

The first pinned candidate is Ibn Rushd al-Hafid's `BidayatMujtahid` OpenITI version:

```text
0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1
```

The OpenITI YML-1 record marks this version `PRIMARY_VERSION, CLEANED_VERSION`. This does **not** automatically make it `ACCEPTED` in Islamic RAG; the local quality state remains `UNREVIEWED` until editorial review.

Download the exact pinned OpenITI revision:

```powershell
.\scripts\download_bidayat_mujtahid.ps1
```

The files are written under `data/openiti/bidayat-mujtahid/`. The `data/` directory is ignored by Git.

## Parse-only validation

Run this before writing anything to PostgreSQL:

```powershell
docker compose exec api python -m app.cli.ingest_openiti `
  --text /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1 `
  --version-yml /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1.yml `
  --book-yml /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.BidayatMujtahid.yml `
  --author-yml /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.yml `
  --dry-run
```

## Persist to PostgreSQL

Licensing fields are intentionally left unknown in this first ingestion until they are verified separately.

```powershell
docker compose exec api python -m app.cli.ingest_openiti `
  --text /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1 `
  --version-yml /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1.yml `
  --book-yml /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.BidayatMujtahid.yml `
  --author-yml /data/openiti/bidayat-mujtahid/0595IbnRushdHafid.yml `
  --source-url "https://github.com/OpenITI/0600AH/blob/ea4bdc6517a49d07106f223aa0869aa7c21b9589/data/0595IbnRushdHafid/0595IbnRushdHafid.BidayatMujtahid/0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1" `
  --release "OpenITI/0600AH@ea4bdc6517a49d07106f223aa0869aa7c21b9589" `
  --quality-status UNREVIEWED
```

## Tests

```powershell
docker compose exec api pytest -q
```

The parser tests verify URI parsing, page-end semantics, exact chunk/source slices, hashes, Arabic normalization, metadata consistency, and rejection of obvious OpenITI template placeholders.

## Not implemented yet

- embeddings
- Qdrant indexing
- lexical/BM25 retrieval
- LLM synthesis
- automatic madhhab assignment
- automatic legal-strength labels (`mashhur`, `rajih`, `mu'tamad`)
- automatic licensing conclusions

These are intentionally deferred until ingestion and provenance are validated on real texts.
