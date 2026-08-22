# Retrieval evaluation and lexical scale guardrails

## Why this exists

A RAG system should not add embeddings or answer synthesis before retrieval quality can be measured. The project therefore keeps versioned retrieval benchmarks alongside the code and treats regressions as engineering defects rather than subjective impressions.

No LLM judges relevance in these baselines. Labels are explicit, version-controlled and tied to the stored corpus structure.

## Two benchmark levels

### Smoke suite

`backend/evals/retrieval_bidayat_v1.json`

This small suite contains the first six manually checked queries. It is useful for fast regression checks and backward compatibility, but it is deliberately too small to represent overall retrieval quality.

### Demanding baseline

`backend/evals/retrieval_bidayat_baseline_v2.json`

This is the default evaluator dataset. It contains more than forty cases and intentionally mixes:

- direct Arabic terminology;
- nested structural targets (`كتاب` / `باب` / `فصل`);
- attached Arabic proclitics such as `و`, `ب`, and `ل`;
- singular/plural morphology changes that the current lexical engine may not solve;
- word-order changes;
- short/broad queries;
- related legal topics that share vocabulary and therefore test discrimination.

The harder cases are not added so the lexical engine can claim 100%. They are added to expose where semantic retrieval, better morphology or reranking can create measurable gains later.

## Grounded labels

Every positive case declares `expected_section_contains`: fragments that must all be present in a result's stored section hierarchy.

At runtime, the evaluator first validates every benchmark label against the current PostgreSQL corpus. If an expected section path does not exist, evaluation stops with an error rather than counting an invented or mistyped label as a retrieval miss.

This validation proves only that the labelled target exists in the corpus. It does not replace scholarly review of whether a user query should be mapped to that target.

## Per-case strictness

Each case has:

- `k`: how many results are inspected;
- `max_first_relevant_rank`: the highest acceptable rank for the first relevant result;
- `query_type`: evaluation slice such as `direct`, `structural`, `clitic`, `morphology`, `paraphrase`, or `topic_discrimination`;
- `difficulty`: `easy`, `medium`, or `hard`;
- optional volume/page constraints.

A case can therefore have a Hit@5 while still failing its strict requirement. Example: a direct chapter-name query may require rank 1, whereas a deliberately difficult singular/plural variation can be allowed anywhere in the top 5.

## Metrics

The evaluator reports both retrieval coverage and ranking quality:

- `Hit@k` and aggregate hit rate;
- `Hit@1`;
- `Hit@3`;
- strict pass rate based on each case's `max_first_relevant_rank`;
- reciprocal rank and mean reciprocal rank (MRR);
- first relevant rank;
- number of relevant results in the top-k;
- `Precision@k` under the benchmark's section-based relevance rule;
- median and p95 query latency as informational local measurements;
- the same quality metrics sliced by `query_type` and by `difficulty`.

Latency is reported for comparison, but it should not be treated as a stable cross-machine benchmark without a controlled environment.

## Reproducibility fingerprints

Every run emits:

- `benchmark_sha256`: SHA-256 of the exact benchmark JSON file;
- `corpus_fingerprint`: SHA-256 over the relevant ingested version identities, source-text hashes, metadata hashes, quality status, provider and release;
- `retrieval_id`: the retrieval implementation identifier, currently `deterministic_lexical_v2`.

This prevents a future result such as “MRR improved” from being detached from the exact dataset, corpus version and retrieval implementation used to produce it.

## Run locally

After the corpus is running and migrations are applied:

```powershell
docker compose exec api python -m app.cli.migrate

docker compose exec api python -m app.cli.evaluate_retrieval
```

The demanding v2 baseline is now the default dataset.

To run only the original smoke suite:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_bidayat_v1.json
```

## Regression gates

Do not assume the demanding baseline should start at 100%. First record the measured lexical-v2 baseline, inspect its failures, and then freeze realistic gates.

Supported gates are:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval `
  --fail-under-hit-rate 0.90 `
  --fail-under-pass-rate 0.80 `
  --fail-under-hit-at-1 0.70 `
  --fail-under-mrr 0.80
```

The numbers above are examples only, not project thresholds. Actual thresholds should be chosen after measuring the demanding baseline and then changed only through an explicit evaluation decision.

`--skip-label-validation` exists only for benchmark authoring/debugging. Normal project evaluation should keep label validation enabled.

## Lexical scaling

Migration `002_lexical_trigram_index.sql` enables PostgreSQL `pg_trgm` and creates a GIN trigram index on `chunks.text_normalized`.

Migration `003_section_search_index.sql` adds an indexed normalized representation of the stored section hierarchy, so candidate retrieval can use both source-body text and structural context.

The candidate query keeps all user values as bound parameters. This is an acceleration and regression-control layer. It is not called BM25 and it is not semantic retrieval.

## What the baseline still does not measure

This section-based baseline does not yet provide complete document-level qrels, graded relevance, answer faithfulness, citation entailment, cross-book retrieval, multilingual retrieval, or unanswerable-question behavior. Those require larger corpora and independently reviewed labels.

Before source-constrained LLM synthesis, the target progression is:

1. freeze the lexical-v2 demanding baseline;
2. ingest more independently sourced works;
3. expand the benchmark across books and madhhabs;
4. add Qdrant embeddings using the same immutable chunk identifiers;
5. compare vector retrieval against the frozen lexical baseline;
6. implement hybrid fusion and reranking only when metrics demonstrate a gain;
7. create separate answer/citation-faithfulness evaluations before enabling synthesis.
