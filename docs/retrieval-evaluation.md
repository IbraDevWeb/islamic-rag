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

The lexical candidate query emits one parameterized `ILIKE` predicate per normalized query term. This preserves user values as bound parameters while allowing PostgreSQL to use trigram index scans/bitmap combinations rather than forcing the application to interpolate user text into SQL.

Candidates matching more distinct query terms are considered before the candidate cap; the existing deterministic Python ranker then applies coverage, exact-phrase, occurrence and section-context scoring.

This is an acceleration and regression-control layer. It is **not** called BM25 and it is **not** the final hybrid retrieval design.

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
