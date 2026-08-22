# Retrieval holdout protocol

## Why a holdout is required now

The 51-case Bidāyat baseline was used to tune hybrid RRF weights. The selected `0.125 lexical / 0.875 semantic` profile therefore has a measured tuning-set score, not an unbiased generalization score.

Running more tuning on the same 51 labels would increasingly overfit the retrieval stack to one work and one benchmark.

Before introducing a reranker as the next ranking layer, the project should freeze an independent evaluation set that is not used to choose hybrid weights.

## Candidate discovery without invented labels

Run:

```powershell
docker compose exec api python -m app.cli.propose_holdout_sections
```

The command reads the actual PostgreSQL section hierarchy and excludes top-level `كتاب` sections already used by the tuning dataset. It prints only corpus-backed candidate sections, including chunk counts and page range.

The output is **not** a benchmark and does not automatically decide relevance. It exists so holdout labels are authored from sections that demonstrably exist in the stored corpus.

## Holdout authoring rules

1. Do not change the frozen Hybrid Retrieval V1 weights after seeing holdout results.
2. Prefer sections/topics not used by the 51-case tuning set.
3. Mix direct terminology, morphology, paraphrase, clitics and topic-discrimination queries.
4. Validate every expected section against the corpus at runtime using the existing benchmark validator.
5. Version the holdout JSON and record its SHA-256.
6. Evaluate lexical, semantic and frozen hybrid exactly once before any reranker tuning decision.
7. If a future reranker is tuned, use a separate development set or cross-validation rather than selecting it directly on the final holdout.

## Promotion rule

The current hybrid profile is a development-tuned retrieval profile. It should not become the public `/search` default solely because it reached perfect strict pass-rate on the data used to select its weights.

A promotion decision should use independent holdout results and, ideally, a later multi-work benchmark after additional books are ingested.
