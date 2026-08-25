# Citation faithfulness V1

## Goal

Structural citation validation proves only that a generated draft uses allowed ids such as `S1` and that each structured claim has at least one citation. It does **not** prove that the cited passage actually supports the claim.

Citation Faithfulness V1 adds an optional semantic support check after generation.

```text
question
  -> semantic evidence retrieval
  -> PostgreSQL hydration
  -> evidence bundle S1..Sn
  -> synthesis package
  -> local Ollama draft
  -> structural citation validation
  -> optional claim-to-cited-passage faithfulness verification
```

## Opt-in behavior

`POST /generate-synthesis` now accepts:

```json
{
  "question": "...",
  "limit": 5,
  "work_uri": "...",
  "include_rejected": false,
  "verify_claims": true
}
```

The verifier sees each structured claim and **only the passages cited for that claim**. It must return one of:

- `SUPPORTED`: the cited passages directly support the proposition;
- `NOT_SUPPORTED`: the cited passages do not support it or contradict it;
- `UNCLEAR`: support requires material inference, missing context, or is ambiguous.

The prompt explicitly forbids outside knowledge. When uncertain, the verifier is instructed to choose `UNCLEAR`.

## Abstention

If generation returns `INSUFFICIENT_EVIDENCE`, there are no positive legal/factual claims to verify. The faithfulness stage is therefore marked `NOT_APPLICABLE` and no second model call is made.

## Development limitation

The default verifier model is currently the same local `qwen3:8b` model used for generation. This is useful as a development gate, but it is **not an independent production-grade verifier** and must not be described as scholarly review.

The response exposes:

```text
independent_verifier_model: false
releasable_answer: null
```

A later evaluation should compare an independent verifier model or dedicated multilingual NLI/entailment component on a labelled claim-to-source benchmark.

## Promotion rule

Even when every claim receives `SUPPORTED`, this V1 only returns:

```text
FAITHFULNESS_SUPPORTED_EXPERIMENTAL
```

It does not populate `releasable_answer`. Production promotion requires an independently evaluated verifier, explicit thresholds, multilingual tests, and a corpus broader than the current single-work development environment.
