# Retrieval holdout protocol

## Why a holdout is required now

The 51-case Bidāyat baseline was used to tune hybrid RRF weights. The selected `0.125 lexical / 0.875 semantic` profile therefore has a measured tuning-set score, not an unbiased generalization score.

Running more tuning on the same 51 labels would increasingly overfit the retrieval stack to one work and one benchmark.

Before introducing a reranker as the next ranking layer, the project now freezes an independent evaluation set that is not used to choose hybrid weights.

## Frozen holdout V1

The holdout is versioned at:

```text
backend/evals/retrieval_bidayat_holdout_v1.json
```

It contains 26 cases across top-level sections that were absent from the 51-case tuning dataset when the holdout was authored. The candidate sections were first enumerated directly from PostgreSQL using `app.cli.propose_holdout_sections`; only then were queries written and committed.

The holdout mixes direct terminology, clitics, structural queries, morphology, paraphrases, and topic-discrimination cases. It is a retrieval-engineering benchmark, not a scholarly legal gold standard.

A regression test asserts that holdout top-level sections remain disjoint from the tuning dataset.

## Candidate discovery without invented labels

The discovery command remains available for future holdouts:

```powershell
docker compose exec api python -m app.cli.propose_holdout_sections
```

It reads the actual PostgreSQL section hierarchy and excludes top-level `كتاب` sections already used by the tuning dataset. Its output is only a corpus-backed candidate list, not a benchmark.

## Frozen evaluation rule

Do **not** retune Hybrid Retrieval V1 weights after seeing this holdout's results. The fixed profile under test is:

```text
lexical  = 0.125
semantic = 0.875
retrieval id = hybrid_rrf_l0125_s0875_lexical_v2_e5_large_v1
```

Run the three retrievers on the exact same frozen holdout:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_bidayat_holdout_v1.json `
  --retriever lexical `
  --summary-only

docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_bidayat_holdout_v1.json `
  --retriever semantic `
  --summary-only

docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_bidayat_holdout_v1.json `
  --retriever hybrid `
  --summary-only
```

Normal evaluation must keep runtime label validation enabled. If one of the expected sections is missing from the current corpus, evaluation should stop rather than silently count a bad label as a retrieval failure.

## Holdout authoring rules

1. Never alter a frozen holdout in response to model performance unless the label itself is demonstrably wrong; such corrections require a new documented dataset version.
2. Do not change Hybrid Retrieval V1 weights after seeing holdout results.
3. Prefer topics not used by the tuning set.
4. Validate every expected section against the stored corpus.
5. Record benchmark SHA-256 and corpus fingerprint with every result.
6. Evaluate lexical, semantic and frozen hybrid before introducing a reranker.
7. Do not tune a future reranker directly on this final holdout. Use a separate development set, cross-validation, or a larger multi-work benchmark.

## Promotion rule

The holdout can support a decision that Hybrid Retrieval V1 generalizes better than its component retrievers on unseen topics from the same work. It cannot establish corpus-wide optimality because the corpus still contains only one evaluated work.

A later production promotion should also include a multi-work benchmark after more independently sourced books are ingested.
