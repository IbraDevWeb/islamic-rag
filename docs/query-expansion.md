# Controlled terminology query expansion

## Why this layer exists

The frozen Bidāyat holdout exposed one shared semantic/hybrid failure:

```text
query: المضاربة
target: كتاب القراض
```

A depth-50 diagnostic then showed that no relevant `كتاب القراض` candidate appeared in the lexical, semantic, or hybrid candidate pools. That means a cross-encoder reranker cannot fix this specific failure: there is nothing relevant for it to rerank.

The next experiment therefore targets **candidate generation**, not reranking.

## Curated retrieval aliases

`app.search.query_expansion` contains a tiny, explicit, versioned alias registry. V1 starts with:

```text
القراض <-> المضاربة
```

This registry is retrieval engineering metadata only. It:

- never changes `text_original` or stored source text;
- is not a scholarly source;
- must not be presented as a legal ruling or universal technical equivalence;
- is deterministic and reviewable;
- is versioned through `curated_fiqh_aliases_v1`.

Every future addition should be justified and reviewed instead of being generated dynamically by an LLM.

## Expanded retrievers

Three experimental retrievers are exposed through the evaluation CLI:

```text
lexical-expanded
semantic-expanded
hybrid-expanded
```

For a mapped query, the original normalized query and its curated variant are searched separately. Results from variants of the same retriever are merged with rank fusion. The expanded hybrid then applies the already frozen 12.5% lexical / 87.5% semantic RRF profile to the expanded lexical and semantic rankings.

No document embeddings are rebuilt.

## Development-only evaluation

The focused development dataset is:

```text
backend/evals/retrieval_terminology_expansion_dev_v1.json
```

It deliberately includes the diagnosed `المضاربة -> كتاب القراض` failure. Because the engine change was designed after seeing that failure, this dataset is **not an independent holdout** and its scores must never be used as a generalization claim.

Run:

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_terminology_expansion_dev_v1.json `
  --retriever semantic-expanded `
  --summary-only

docker compose exec api python -m app.cli.evaluate_retrieval `
  --dataset evals/retrieval_terminology_expansion_dev_v1.json `
  --retriever hybrid-expanded `
  --summary-only
```

If the alias case is recovered, the next unbiased test must use a **new** holdout or, preferably, a multi-work benchmark after more books are ingested. Do not retroactively call the original 26-case holdout unbiased for this expanded engine.

## Reranker gate

Only introduce a cross-encoder reranker after candidate recall is adequate. A reranker is appropriate when relevant passages exist in the candidate pool but are ranked too low. It is not the right tool when terminology mismatch prevents relevant candidates from entering the pool at all.
