# Weighted hybrid retrieval tuning

## Goal

The project already has three measured retrieval baselines on the same 51-case Bidāyat al-Mujtahid benchmark:

- deterministic lexical retrieval;
- dense multilingual E5 retrieval;
- equal-weight reciprocal rank fusion (RRF).

The next question is not whether hybrid retrieval can find the relevant section, but how much influence each branch should receive. The equal-weight baseline can preserve strict coverage while still letting lexical ranking degrade strong semantic top-1 results on morphology-heavy queries.

This tuner therefore searches a small, explicit weight grid before any production default is changed.

## Important property: no document re-embedding

`python -m app.cli.tune_hybrid` does **not** rebuild the 1,538 document vectors.

For each benchmark query it:

1. validates that the Qdrant semantic index is READY and fresh against PostgreSQL;
2. runs lexical retrieval once;
3. embeds the query and runs semantic retrieval once;
4. keeps both candidate rankings in memory;
5. applies every requested weighted-RRF configuration to those same rankings;
6. evaluates every fused ranking against the exact same benchmark labels.

Changing RRF weights therefore changes only rank fusion. It does not mutate PostgreSQL, Qdrant, source text, chunks, or embeddings.

## Default sweep

The default configurations are:

```text
lexical 0.50 / semantic 0.50
lexical 0.40 / semantic 0.60
lexical 0.30 / semantic 0.70
lexical 0.20 / semantic 0.80
lexical 0.10 / semantic 0.90
```

For a concise terminal result:

```powershell
docker compose exec api python -m app.cli.tune_hybrid --compact
```

Omit `--compact` to include complete per-type and per-difficulty metrics for every candidate.

Custom lexical weights can be supplied as a comma-separated list; semantic weight is `1 - lexical`:

```powershell
docker compose exec api python -m app.cli.tune_hybrid `
  --compact `
  --lexical-weights "0.50,0.45,0.40,0.35,0.30,0.25,0.20,0.15,0.10"
```

The default candidate pool is 25 results from each source retriever per query. It can be changed explicitly with `--pool-size`, but pool-size tuning should be treated as a separate experiment from weight tuning.

## Selection rule

The tool reports every candidate and also selects one `best_candidate` using this fixed priority:

1. highest strict `pass_rate`;
2. highest `Hit@1`;
3. highest MRR;
4. highest Precision@k;
5. if every measured quality metric still ties, prefer the candidate with less semantic weight so lexical evidence retains more influence.

This ordering is deliberate. A candidate is not allowed to improve top-1 ranking by losing a benchmark case that the current hybrid can satisfy.

The selected configuration is an **evaluation recommendation**, not an automatic production change. The public retrieval default must only be changed after inspecting the report and confirming that the result is not an artefact of the current small single-work benchmark.

## What to inspect

Do not look only at the global winner. Compare:

- `pass_rate` and `failed_case_ids`;
- `hit_rate_at_1`;
- MRR;
- Precision@k;
- `by_query_type`, especially `morphology`, `clitic`, and `topic_discrimination`;
- `by_difficulty`, especially `hard`.

A future larger multi-work benchmark may select a different weight ratio. For that reason weights remain explicit parameters rather than being baked into the embedding model or source data.

## Reproducibility

Each report includes:

- benchmark SHA-256;
- corpus fingerprint;
- lexical retrieval implementation id;
- semantic retrieval implementation id;
- pool size;
- tested weight configurations;
- the fixed selection rule.

This makes a weight decision traceable to the exact corpus and benchmark on which it was made.
