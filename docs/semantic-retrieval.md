# Semantic retrieval V1 and hybrid comparison

## Purpose

The semantic layer is a **derived retrieval index**, not a source of evidence. PostgreSQL remains the source of truth for immutable chunks, source hashes, locations and editorial status. Qdrant stores vectors plus enough provenance identifiers to locate the underlying chunk.

This phase deliberately does not add LLM answer synthesis. Its purpose is to test whether dense semantic retrieval improves the demanding retrieval baseline, especially morphology/paraphrase failures that pure lexical matching cannot reliably solve.

## Dense model

Default model:

```text
intfloat/multilingual-e5-large
```

Configuration:

```text
EMBEDDING_MODEL=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024
QDRANT_DENSE_COLLECTION=islamic_rag_dense_e5_v1
```

The model is run locally through FastEmbed/ONNX. Retrieval input follows the E5 asymmetric retrieval convention:

```text
query: <normalized query>
passage: <normalized section path>\n<normalized passage>
```

`text_original` is never embedded in-place or overwritten. Normalized embedding input remains a derived representation.

## Why this model is only a baseline

The model is multilingual and stable in FastEmbed, which makes it practical for local Arabic/French experimentation. It has a 1024-dimensional dense representation and a finite context window. It is not declared the final model for Islamic RAG.

Future candidates such as BGE-M3 or other multilingual long-context retrievers must beat this baseline on the same versioned benchmark and corpus fingerprint before replacing it.

## Reproducible indexing

Migration `004_semantic_index_manifest.sql` adds `semantic_index_manifests` in PostgreSQL.

A manifest records:

- Qdrant collection name;
- embedding model and vector dimension;
- embedding schema version;
- exact semantic chunk-set SHA-256 fingerprint;
- indexed point count;
- state: `BUILDING`, `READY`, or `FAILED`;
- last indexing error, if any.

Every Qdrant point uses a deterministic UUID derived from the immutable `chunk_id`. Its payload includes the original `chunk_id`, work/version URI, quality status, sequence, volume/page, section path, text hash and source-text SHA-256.

Before semantic/hybrid benchmarking, the evaluator checks that:

1. the manifest is `READY`;
2. model/dimension/schema match current configuration;
3. the PostgreSQL chunk fingerprint still matches the manifest;
4. PostgreSQL chunk count matches the manifest;
5. Qdrant point count matches the manifest.

A stale vector index is therefore rejected rather than silently evaluated.

## Model cache

Docker Compose mounts a persistent `model_cache` volume at `/root/.cache`. The first semantic build downloads the embedding model; subsequent API-container rebuilds reuse the cache as long as that Docker volume is preserved.

Do not use `docker compose down -v` when you want to preserve PostgreSQL, Qdrant, and the model cache.

## Build the dense index

After pulling dependency/config changes, rebuild the API image and apply migrations:

```powershell
docker compose up -d --build api
docker compose exec api python -m app.cli.migrate
```

First build:

```powershell
docker compose exec api python -m app.cli.index_semantic
```

If the dedicated derived collection already exists and you intentionally want to regenerate all vectors:

```powershell
docker compose exec api python -m app.cli.index_semantic --recreate
```

The command refuses to destroy an existing collection unless `--recreate` is explicit.

## Compare retrieval modes

Lexical baseline:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever lexical --summary-only
```

Dense semantic baseline:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever semantic --summary-only
```

Equal-weight reciprocal-rank fusion baseline:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever hybrid --summary-only
```

Failure inspection works for every backend:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever hybrid --failures-only
```

## Hybrid V1

Hybrid V1 does not add raw lexical scores to cosine similarity because those scales are unrelated. It retrieves independent candidate rankings and combines them with equal-weight Reciprocal Rank Fusion (RRF).

Identifier:

```text
hybrid_rrf_lexical_v2_e5_large_v1
```

The initial fusion weights are intentionally **not tuned against the 51-case benchmark**. The benchmark is for measuring the baseline, not for repeatedly optimizing coefficients until the test set is overfit.

## Acceptance discipline

Do not promote semantic or hybrid retrieval as the default `/search` backend merely because it sounds more advanced. Compare at least:

- strict pass-rate;
- Hit@1 and Hit@3;
- MRR;
- Precision@k;
- morphology/paraphrase slices;
- latency;
- failure cases.

The current public API remains deterministic lexical retrieval until a candidate demonstrates a useful, reproducible gain without unacceptable regressions.
