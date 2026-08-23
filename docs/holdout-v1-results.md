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

The shared failure is `holdout-qirad-mudaraba`: query `المضاربة` targeting `كتاب القراض`. This is a terminology/paraphrase case. Before adding a cross-encoder reranker, candidate recall must be diagnosed at deeper retrieval depths. A reranker cannot recover a relevant passage that is absent from its candidate pool.

## Next diagnostic

After pulling the diagnostic CLI, inspect the shared failure at depth 50:

```powershell
docker compose exec api python -m app.cli.diagnose_retrieval_case `
  --dataset evals/retrieval_bidayat_holdout_v1.json `
  --case-id holdout-qirad-mudaraba `
  --depth 50 `
  --show 10
```

Interpretation:

- `already_in_original_top_k`: reranking is unnecessary for candidate recall on that branch;
- `recoverable_from_deeper_pool`: a reranker may be able to promote the relevant candidate;
- `missing_from_candidate_pool`: improve candidate generation, terminology coverage, or the dense representation before adding a reranker.

The holdout remains frozen regardless of the diagnostic outcome.
