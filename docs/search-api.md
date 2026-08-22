# Search API v1 — deterministic source retrieval

## Purpose

`GET /search` exposes the first retrieval layer of Islamic RAG. It retrieves and ranks source passages; it does **not** generate a fatwa, legal conclusion, or synthetic answer.

The API contract is designed so every returned passage can be traced back to:

- the author and OpenITI work/version identifiers;
- volume/page markers present in the source text;
- section hierarchy, with an explicit structure provenance/status;
- the immutable source URL/release;
- the deterministic chunk id and SHA-256 text hash;
- the editorial quality status of the text version;
- a separately sourced bibliographic identity when one has been manually verified.

## Endpoint

```http
GET /search?q=الصلاة%20في%20السفر&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5
```

Parameters:

- `q` — required query, 1–500 characters;
- `limit` — 1–50, default 10;
- `work_uri` — optional exact OpenITI work URI filter;
- `include_rejected` — default `false`; rejected text versions stay excluded unless explicitly requested.

Swagger/OpenAPI documentation is available at `/docs`.

## Provenance rules

### Text provenance

`source_url` and `release` identify the ingested text source. `chunk_id` and `text_hash` identify the exact returned chunk. The API returns `passage_original` separately from the normalized search representation.

### Structure provenance

A section path can be:

- `SOURCE_EXPLICIT` / `openiti_explicit` — explicit OpenITI structural markup;
- `INFERRED` / `legacy_pipe_inferred` — conservatively inferred from legacy-looking `# |` headings because that source version contained no explicit `### |` hierarchy;
- `NONE` — no structural claim.

Inferred hierarchy must never be presented as if it were explicit source markup.

### Bibliographic provenance

Bibliographic identity is kept separate from OpenITI source metadata. For `0595IbnRushdHafid.BidayatMujtahid`, the project-curated title is verified against the BnF Catalogue général record `cb32268155q`:

- Arabic title: `بداية المجتهد ونهاية المقتصد`
- Latin display: `Bidāyat al-mujtahid wa-nihāyat al-muqtaṣid`
- BnF record: `https://catalogue.bnf.fr/ark:/12148/cb32268155q`
- verification scope: `work_identity_and_title_only`

This bibliographic record verifies the **work identity/title only**. It does not assert that the BnF physical edition and the OpenITI digital version share the same pagination, editor, or edition.

If no curated record exists, the API returns `verification_status: UNVERIFIED` rather than inventing bibliographic data.

## Retrieval v1

Current retrieval identifier: `deterministic_lexical_v1`.

The ranker uses normalized query terms, term coverage, exact-phrase hits, occurrence counts, and a small section-context bonus. It is deterministic and contains no LLM step.

The response deliberately includes:

```json
"generated_answer": null
```

This makes the current boundary explicit: retrieval is implemented; answer synthesis is not.

## Next retrieval milestones

Before LLM synthesis, the intended progression is:

1. build a larger evaluated corpus;
2. add scalable lexical retrieval and regression/evaluation datasets;
3. index immutable chunks in Qdrant with embeddings and the same provenance identifiers;
4. implement hybrid lexical + vector retrieval/reranking;
5. only then add source-constrained synthesis whose claims point back to retrieved evidence.
