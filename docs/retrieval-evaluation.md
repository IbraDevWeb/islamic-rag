# Retrieval evaluation and lexical scale guardrails

## Why this exists

A RAG system should not add embeddings or answer synthesis before its retrieval quality can be measured. This project therefore keeps a deterministic retrieval benchmark alongside the code.

The first dataset is intentionally small. It is a smoke/regression suite for the first ingested work, not a scholarly gold standard and not evidence that retrieval quality generalizes to the future corpus.

## Benchmark

Dataset:

```text
backend/evals/retrieval_bidayat_v1.json
```

Each case contains:

- a query;
- an optional exact OpenITI work URI filter;
- one or more section-path fragments that a relevant result must contain;
- `k`, the maximum rank inspected;
- optional volume/page constraints;
- notes where useful.

A result is considered relevant only when every declared section fragment is present in the returned section hierarchy and every optional location constraint is satisfied.

## Metrics

The evaluator reports:

- `Hit@k`: whether at least one relevant result appears within the requested top-k;
- hit rate across all cases;
- reciprocal rank for every case;
- mean reciprocal rank (MRR);
- mean rank of the first relevant result among successful cases;
- per-case top section paths/pages for debugging regressions.

No LLM judges relevance. Labels are explicit and version-controlled.

## Run locally

After the corpus is running and migrations are applied:

```powershell
docker compose exec api python -m app.cli.migrate

docker compose exec api python -m app.cli.evaluate_retrieval
```

To make a regression check fail when any smoke case misses:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --fail-under-hit-rate 1.0
```

This corpus-dependent evaluation is deliberately not part of the lightweight GitHub Actions unit-test job, because CI does not currently provision and ingest the pinned OpenITI corpus.

## Lexical scaling

Migration `002_lexical_trigram_index.sql` enables PostgreSQL `pg_trgm` and creates a GIN trigram index on `chunks.text_normalized`.

Migration `003_section_search_index.sql` makes structural context searchable through a separate `section_text_normalized` projection and a second GIN trigram index. `section_path` remains the structured provenance field; the search projection is only an acceleration/retrieval aid.

Future ingestion computes `section_text_normalized` in Python with the same Arabic normalization used for query/search text. Existing rows are conservatively backfilled from their stored section path when migration `003` is applied.

## Deterministic lexical v2

`deterministic_lexical_v2` addresses an important failure mode observed in the smoke benchmark: a relevant chapter can be identified by its heading even when an individual body chunk does not repeat every query term.

Candidate retrieval therefore searches both:

- `chunks.text_normalized` — normalized source passage text;
- `chunks.section_text_normalized` — normalized structural heading context.

A term present in either location counts toward retrieval coverage. Body occurrences, exact body phrases, section-term matches, section coverage, and exact section phrases remain separately weighted. This is still deterministic lexical evidence; it is not semantic inference.

The candidate SQL emits parameterized `ILIKE` predicates for both indexed projections. User text remains bound parameters rather than interpolated SQL.

This layer is **not** called BM25 and it is **not** the final hybrid retrieval design.

## Regression discipline

A retrieval change should be judged against the versioned benchmark rather than by visual inspection alone. When a benchmark case fails:

1. inspect the returned paths/pages;
2. determine whether the failure is caused by candidate generation, ranking, normalization, chunking, or an incorrect benchmark label;
3. change one layer deliberately;
4. add or update a unit/regression test that captures the failure mode;
5. rerun the full benchmark and compare metrics before accepting the change.

A smoke-suite score of 100% is necessary for this tiny dataset before moving on, but it is not evidence that the system is production-ready or that retrieval generalizes to other books.

## Before semantic retrieval

The benchmark should grow with the corpus and include at least:

- exact terminology queries;
- paraphrases and morphology variants;
- queries whose relevant evidence is not in the first lexical match;
- cross-work queries once multiple books are ingested;
- deliberately unanswerable queries;
- hard negatives with similar vocabulary but wrong legal topic;
- independently reviewed labels for higher-stakes evaluation.

Only after this baseline is measurable should Qdrant embeddings and hybrid lexical/vector reranking be compared against it.
