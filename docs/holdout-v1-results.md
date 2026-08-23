# Bidāyat holdout V1 results

## Frozen evaluation context

Dataset: `bidayat-retrieval-holdout-v1`

Benchmark SHA-256:

```text
f1f5d272445f205fa2d38fcb1eeb2dd1ef6789fc8e9f250da4a3b89d0b2c6ff6
```

Corpus fingerprint:

```text
509f32fddd6eaa0c0cf1b5e11ea6d959c4dc84f3f927f8c780efc8ad252fe143
```

The holdout contains 26 cases and was frozen before these results were observed. These results must not be used to retune Hybrid Retrieval V1 weights.

## Results

| Retriever | Strict pass rate | Hit@k | Hit@1 | Hit@3 | MRR | Precision@k | Median latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `deterministic_lexical_v2` | 88.46% | 92.31% | 84.62% | 92.31% | 0.8846 | 0.8308 | 64.714 ms |
| `semantic_multilingual_e5_large_v1` | 96.15% | 96.15% | 96.15% | 96.15% | 0.9615 | 0.9462 | 65.050 ms |
| `hybrid_rrf_l0125_s0875_lexical_v2_e5_large_v1` | 96.15% | 96.15% | 96.15% | 96.15% | 0.9615 | 0.9385 | 140.386 ms |

### Failed cases

Lexical:

- `holdout-ghusl-direct`
- `holdout-marriage-paraphrase`
- `holdout-qirad-mudaraba`

Semantic:

- `holdout-qirad-mudaraba`

Frozen Hybrid V1:

- `holdout-qirad-mudaraba`

## Interpretation

The independent holdout confirms a substantial generalization gain from dense retrieval over the lexical baseline on unseen top-level sections from the same work. Semantic retrieval improves strict pass rate from 88.46% to 96.15%, and Hit@1 from 84.62% to 96.15%.

However, the frozen 12.5/87.5 hybrid does **not** outperform semantic retrieval on this holdout. It ties semantic retrieval on strict pass rate, Hit@k, Hit@1, Hit@3 and MRR, has slightly lower Precision@k, and roughly doubles median local query latency. Therefore the holdout does not justify claiming that Hybrid V1 is superior to semantic retrieval in general.

The shared failure is `holdout-qirad-mudaraba`: query `المضاربة` targeting `كتاب القراض`. This is a terminology/paraphrase case.

## Depth-50 diagnosis

The case was inspected at retrieval depth 50 after the frozen holdout evaluation. All three branches reported:

```text
first_relevant_rank = null
hit_within_depth = false
reranker_candidate_status = missing_from_candidate_pool
```

So `كتاب القراض` was absent from the top 50 lexical candidates, top 50 semantic candidates, and the resulting hybrid candidate pool.

This rules out a reranker as the immediate fix for this failure. A cross-encoder cannot promote a relevant passage that candidate generation never retrieves.

The next development experiment is therefore controlled terminology query expansion, starting with the explicit retrieval-only alias pair:

```text
القراض <-> المضاربة
```

That change is documented in `docs/query-expansion.md` and is evaluated only on a development dataset that openly includes the diagnosed failure.

## Holdout contamination boundary

The original 26-case scores above remain the independent measurement of the pre-expansion lexical/semantic/hybrid engines.

Once the `المضاربة -> القراض` failure informed the design of a new expanded retriever, this holdout is no longer unbiased for that new engine version. Do not rerun the expanded engine on these 26 cases and present the result as fresh generalization evidence. Use a new holdout or a later multi-work benchmark for that purpose.
