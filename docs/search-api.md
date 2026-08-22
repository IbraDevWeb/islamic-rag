# Search API v2 — deterministic source retrieval

## Purpose

`GET /search` exposes the deterministic retrieval layer of Islamic RAG. It retrieves and ranks source passages; it does **not** generate a fatwa, legal conclusion, or synthetic answer.

The API contract is designed so every returned passage can be traced back to:

- the author and OpenITI work/version identifiers;
- volume/page markers present in the source text;
- section hierarchy, with an explicit structure provenance/status;
- exact source offsets for the chunk;
- the immutable source URL/release;
- the deterministic chunk id and SHA-256 hashes for both the chunk and complete source text;
- the editorial quality status and source quality issues;
- rights/licensing fields without guessing unknown values;
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

### Text and integrity provenance

`source_url` and `release` identify the ingested text source. `source_start` and `source_end` point to the exact slice of the immutable OpenITI body used for the chunk.

Integrity fields are deliberately redundant:

- `chunk_id` — deterministic identity of the chunk;
- `text_hash` — SHA-256 of the exact original chunk text;
- `source_text_sha256` — SHA-256 of the complete downloaded source text;
- `source_metadata_sha256` — SHA-256 of the exact downloaded version metadata file.

The API returns `passage_original` separately from `passage_normalized`. Search normalization must never replace the evidentiary source text.

### Quality provenance

`quality_status` is the project's editorial status (`UNREVIEWED`, `ACCEPTED`, `REVIEW_REQUIRED`, or `REJECTED`). `quality_issues` carries issues/labels declared by the source metadata, such as `PRIMARY_VERSION` or `CLEANED_VERSION`.

These are separate concepts: a source label such as `CLEANED_VERSION` does not automatically make the project status `ACCEPTED`.

### Rights provenance

The response exposes `license`, `copyright_status`, `commercial_use_allowed`, and `attribution_required`. Unknown values stay `null`; the system must not infer permissions merely because a text is publicly accessible.

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

## Retrieval v2

Current retrieval identifier: `deterministic_lexical_v2`.

The ranker remains fully deterministic and contains no LLM step. It now retrieves lexical evidence from two indexed projections:

- normalized source passage text;
- normalized section-heading context.

A query term found in either location contributes to coverage. Body occurrences, exact body phrases, section-term matches, section coverage, and exact section phrases are weighted separately. This allows a chapter heading to provide useful lexical evidence without pretending the engine understands semantic equivalence.

The response deliberately includes:

```json
"generated_answer": null
```

This makes the current boundary explicit: retrieval is implemented; answer synthesis is not.

## Next retrieval milestones

Before LLM synthesis, the intended progression is:

1. grow the versioned retrieval benchmark and independently review labels;
2. compare stronger lexical ranking approaches against `deterministic_lexical_v2`;
3. index immutable chunks in Qdrant with embeddings and the same provenance identifiers;
4. implement hybrid lexical + vector retrieval/reranking;
5. only then add source-constrained synthesis whose claims point back to retrieved evidence.
