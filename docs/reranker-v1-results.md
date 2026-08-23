# Reranker V1 evaluation result

## Decision

**Status: NOT PROMOTED.**

The first multilingual cross-encoder reranker is technically functional, but the measured development result does not justify placing it in the preferred retrieval path.

The model remains available behind the `reranked` evaluation backend for future experiments.

## Runtime smoke test

Local warm-up succeeded with:

```text
reranker id  = gte_multilingual_reranker_base_int8_v1
source repo  = onnx-community/gte-multilingual-reranker-base
model file   = onnx/model_quantized.onnx
candidate pool = 20
batch size     = 4
threads        = 4
```

The first local download reconstructed roughly 358 MB of cached model files and returned valid cross-encoder scores. This proves only that inference works; it is not a quality benchmark.

## Terminology development set

On `retrieval-terminology-expansion-dev-v1` the reranked pipeline passed all 3/3 cases at rank 1. Median latency was about 10.1 seconds per query on the measured local CPU run.

This dataset was deliberately created after diagnosing the `المضاربة -> كتاب القراض` failure, so it cannot be used as an independent generalization claim.

## 51-case development baseline

Comparison on `bidayat-retrieval-baseline-v2`:

| Metric | semantic-expanded | reranked |
| --- | ---: | ---: |
| Strict pass rate | 98.04% | 98.04% |
| Hit@k | 100% | 100% |
| Hit@1 | 98.04% | 94.12% |
| Hit@3 | 100% | 100% |
| MRR | 0.9902 | 0.9706 |
| Precision@k | 0.8902 | 0.8863 |
| Median latency | 62.159 ms | 5281.236 ms |
| p95 latency | 101.437 ms | 5791.033 ms |

The reranker fixed the strict clitic miss seen in semantic-expanded, but degraded top-rank quality in morphology, paraphrase, and topic-discrimination slices. Its remaining strict failure was `interdiction`.

The overall result is therefore worse for the intended use: the same strict pass count, lower Hit@1, lower MRR, slightly lower Precision@k, and roughly two orders of magnitude more local latency.

## Consequence

The preferred experimental evidence path remains:

```text
curated terminology expansion
  -> multilingual E5 semantic retrieval
  -> PostgreSQL hydration
  -> cited evidence passages
```

The reranker is not deleted. Keeping it versioned is useful for later comparisons against a larger multi-work corpus, a different cross-encoder, smaller candidate pools, or hardware acceleration. It must not be presented as the current best retriever.

The public `/search` route remains the deterministic lexical route until an explicit production promotion decision is made.
