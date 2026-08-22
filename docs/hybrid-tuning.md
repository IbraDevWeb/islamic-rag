# Weighted hybrid retrieval tuning

## Goal

The project already has three measured retrieval baselines on the same 51-case Bidāyat al-Mujtahid benchmark:

- deterministic lexical retrieval;
- dense multilingual E5 retrieval;
- reciprocal rank fusion (RRF).

The goal of tuning is to decide how much influence each branch should receive without adding incomparable raw lexical and cosine scores.

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

The coarse default configurations are:

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

Custom lexical weights can be supplied as a comma-separated list; semantic weight is `1 - lexical`.

## Selection rule

The tool selects one `best_candidate` using this fixed priority:

1. highest strict `pass_rate`;
2. highest `Hit@1`;
3. highest MRR;
4. highest Precision@k;
5. if all measured quality metrics still tie, prefer the candidate with less semantic weight so deterministic lexical evidence retains more influence.

A candidate is not allowed to improve top-1 ranking by losing a benchmark case that another candidate satisfies.

## Measured tuning decision — Hybrid Retrieval V1

On the frozen 51-case `bidayat-retrieval-baseline-v2` dataset, a fine sweep tested lexical weights:

```text
0.000, 0.025, 0.050, 0.075, 0.100, 0.125, 0.150, 0.175, 0.200
```

The selected development-tuned profile is:

```text
lexical  = 0.125
semantic = 0.875
```

Measured metrics on the tuning dataset:

```text
strict pass rate : 1.000000
Hit@k            : 1.000000
Hit@1            : 0.980392
Hit@3            : 1.000000
MRR              : 0.990196
Precision@k      : 0.894118
failed cases     : none
```

The ratio `0.075 / 0.925` reached the same strict pass-rate, Hit@1, MRR and Precision@k. The fixed tie-break rule therefore selected `0.125 / 0.875` because it retains more lexical influence without degrading the measured quality metrics.

The frozen code identifier is:

```text
hybrid_rrf_l0125_s0875_lexical_v2_e5_large_v1
```

`search_hybrid()` now uses this ratio by default, while explicit weight overrides remain available for experiments.

## Critical evaluation caveat

These numbers are **tuning-set measurements**, not an unbiased estimate of generalization. The 51 cases were used to choose the weights, so reporting the same 51-case score as a final test score would be optimistic.

Before calling this profile corpus-wide or production-optimal, the project should evaluate it on one or both of:

- a new holdout set that was not used during weight selection;
- a larger multi-work benchmark after more books are ingested.

The public `/search` endpoint should therefore not be switched solely because this single-work tuning set is perfect on strict pass-rate.

## Reproducibility

Each tuning report includes benchmark SHA-256, corpus fingerprint, lexical/semantic retrieval IDs, candidate pool size, tested weights and the fixed selection rule. This keeps every weight decision tied to the exact corpus and benchmark used to make it.
