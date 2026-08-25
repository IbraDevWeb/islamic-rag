# Controlled synthesis contract

## Status

The project now prepares a provider-neutral synthesis package but **does not call an LLM yet**.

This is deliberate. Retrieval, source hydration, citation ids, and validation rules are fixed before any generative model is allowed into the pipeline.

Current flow:

```text
question
  -> semantic-expanded retrieval
  -> PostgreSQL evidence hydration
  -> evidence bundle S1..Sn
  -> synthesis package
  -> [future LLM provider]
  -> structural citation validation
  -> [future semantic citation-faithfulness validation]
```

## GET /synthesis-package

This endpoint starts from the same PostgreSQL-hydrated evidence path as `/evidence-bundle` and produces a deterministic package containing:

- the original question;
- the evidence bundle id and SHA-256;
- an ordered allow-list of citation ids such as `S1`, `S2`, ...;
- exact source passages and their full citation metadata;
- explicit model instructions;
- an output schema;
- a rendered provider-neutral `model_context`;
- a package SHA-256 covering the prompt-relevant evidence and contract.

The endpoint returns:

```text
status = PREPARED_NO_MODEL_CALL
generated_answer = null
```

No OpenAI, Ollama, Anthropic, local model, or other provider is invoked at this stage.

## Package integrity

The package hash covers the contract version, evidence-bundle identity, question, allowed citation ids, instructions, output schema, source order, exact `passage_original` values, and citation metadata.

This protects the hand-off boundary: if prompt-relevant evidence is altered after package construction, `POST /validate-synthesis` rejects the package integrity check.

## Future model output contract

The first draft schema is intentionally simple:

```json
{
  "status": "ANSWERED",
  "answer": "... [S1] ...",
  "claims": [
    {
      "text": "...",
      "citation_ids": ["S1"]
    }
  ]
}
```

or:

```json
{
  "status": "INSUFFICIENT_EVIDENCE",
  "answer": "The supplied evidence is insufficient to answer safely.",
  "claims": []
}
```

## POST /validate-synthesis

The validator currently checks mechanical safety constraints only:

- package integrity;
- allowed citation ids;
- unknown inline `[Sx]` citations;
- unknown structured citation ids;
- uncited structured claims in an `ANSWERED` draft;
- non-empty answer and valid status.

It deliberately returns:

```text
semantic_entailment_checked = false
```

This is important: a syntactically valid citation does **not** prove that the cited passage supports the claim. Citation-faithfulness / entailment evaluation is the next validation layer before production answer generation.

## Local test

Prepare a package:

```powershell
curl.exe -s "http://localhost:8000/synthesis-package?q=%D8%A7%D9%84%D9%85%D8%B6%D8%A7%D8%B1%D8%A8%D8%A9&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5" -o synthesis-package.json
Get-Content .\synthesis-package.json -Raw -Encoding UTF8
```

Important fields include:

```text
contract_version
package_id
package_sha256
evidence_bundle_id
allowed_citation_ids
instructions
sources
model_context
generated_answer = null
```

## Why no LLM call yet

The project should not choose a generative provider merely to produce an early demo. Before adding one, the interface around it must make the following invariants testable:

1. only hydrated source evidence enters the model context;
2. only bundle-local citation ids may be emitted;
3. no uncited claim is accepted structurally;
4. altered evidence packages fail integrity validation;
5. insufficient evidence is an explicit valid outcome;
6. semantic citation faithfulness is evaluated separately.

Once this boundary is stable, a local or remote LLM can be plugged in behind the same contract without changing the evidence model.
