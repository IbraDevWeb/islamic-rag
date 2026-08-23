# Multilingual reranking

## Goal

The retriever can now generate candidates reliably enough to justify a second ranking stage.

The reranker does **not** search the whole corpus. It receives only the top candidates already found by `semantic-expanded`, reads the query and each candidate passage together, then changes their order.

Current pipeline:

```text
query
  -> curated terminology expansion
  -> multilingual E5 semantic retrieval
  -> top 20 candidates
  -> PostgreSQL hydration of original text
  -> multilingual cross-encoder reranker
  -> top k passages
```

The public `/search` endpoint is still unchanged.

## Why candidate retrieval comes first

A reranker cannot recover a passage that is absent from its candidate pool. The frozen holdout exposed exactly that failure for `المضاربة -> كتاب القراض`: lexical, semantic, and hybrid retrieval all missed the target even at depth 50.

Curated query expansion fixed that candidate-recall problem. Only after candidate generation was repaired does reranking become meaningful.

## Model

Reranking V1 uses a quantized ONNX conversion of:

```text
Alibaba-NLP/gte-multilingual-reranker-base
```

Runtime source:

```text
onnx-community/gte-multilingual-reranker-base
onnx/model_quantized.onnx
```

Project retrieval id:

```text
semantic_expanded_curated_fiqh_aliases_v1_gte_multilingual_reranker_base_int8_v1
```

The base model is multilingual and Apache-2.0 licensed. The quantized ONNX file is roughly 341 MB, which keeps local CPU deployment much lighter than a multi-gigabyte PyTorch reranker.

FastEmbed 0.8.0 already supports custom ONNX cross-encoders, so this stage does not add PyTorch or Transformers to the backend image.

## Source-of-truth rule

Qdrant and the semantic-expanded layer are used only to identify candidate chunk ids.

Before reranking, every candidate is hydrated again from PostgreSQL. The reranker receives:

- the exact `text_original` stored for the chunk;
- its section hierarchy;
- its immutable chunk/text hashes and source metadata needed downstream.

If a candidate id returned by the derived retrieval layer cannot be hydrated from PostgreSQL, reranking fails loudly instead of silently trusting derived payload text.

The transient reranker input prepends section context to the original passage, but the stored source text itself is never modified.

## Terminology expansion during reranking

Candidate generation already uses `curated_fiqh_aliases_v1`. Reranking evaluates each candidate against the original normalized query and every explicit curated query variant, then retains the strongest cross-encoder score for that candidate.

For example:

```text
المضاربة
  -> المضاربة
  -> القراض
```

This remains a retrieval-engineering mechanism. The alias registry is not a religious source and must not be presented as proof of legal equivalence.

## Runtime defaults

```text
candidate pool = 20
batch size     = 4
CPU threads    = 4
cache          = /root/.cache/fastembed
```

The existing Docker `model_cache` volume is mounted at `/root/.cache`, so the reranker model persists across normal API container rebuilds. Do not use `docker compose down -v` if that cache should be preserved.

## First local load

Run:

```powershell
docker compose exec api python -m app.cli.warm_reranker
```

The first run downloads the quantized model and tokenizer into the persistent model cache, loads the ONNX cross-encoder, and scores two tiny smoke pairs. It does not modify PostgreSQL, Qdrant, chunks, or document embeddings.

A successful result contains:

```json
{
  "status": "READY",
  "reranker_id": "gte_multilingual_reranker_base_int8_v1"
}
```

The two smoke scores only prove that inference works. They are not quality metrics.

## Evaluation

The reranker is available to the existing evaluation CLI as:

```text
--retriever reranked
```

A quick development check can use the terminology-expansion development set:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_terminology_expansion_dev_v1.json `
  --retriever reranked `
  --summary-only
```

Then compare the established 51-case development baseline:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_bidayat_baseline_v2.json `
  --retriever semantic-expanded `
  --summary-only

docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_bidayat_baseline_v2.json `
  --retriever reranked `
  --summary-only
```

Do **not** tune reranker decisions directly against the frozen holdout V1. The holdout has already served its role as an independent evaluation of pre-reranker retrieval. A fresh independent set is required before a later production-promotion claim.

## Promotion criteria

Reranking should only become part of the preferred retrieval pipeline if it demonstrates a meaningful gain in top-rank quality without unacceptable latency or stability cost.

At minimum compare:

- strict pass rate;
- Hit@1;
- Hit@3;
- MRR;
- Precision@k;
- failures by query type;
- median and p95 latency.

A reranker that only adds latency while preserving the same ranking should remain experimental.
