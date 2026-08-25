# Local source-constrained synthesis

## Status

Generated synthesis is **experimental and disabled by default**.

The preferred source path remains evidence-first:

```text
question
  -> curated terminology expansion
  -> multilingual E5 retrieval
  -> PostgreSQL hydration
  -> evidence bundle S1..Sn
  -> synthesis package
  -> optional local LLM draft
  -> structural citation validation
  -> future semantic citation-faithfulness validation
```

A generated draft is never a source. Passing structural validation is not enough to make a draft releasable.

## First provider

The first optional provider is local Ollama. It is intentionally outside Docker so the backend can use an Ollama installation already running on the Windows host.

Default settings:

```text
SYNTHESIS_PROVIDER=disabled
SYNTHESIS_OLLAMA_URL=http://host.docker.internal:11434
SYNTHESIS_MODEL=qwen3:8b
SYNTHESIS_TIMEOUT_SECONDS=180
SYNTHESIS_TEMPERATURE=0
```

The route refuses to call a model while `SYNTHESIS_PROVIDER=disabled`.

## Why Qwen3 8B is only a development default

`qwen3:8b` is a practical multilingual local development candidate, not an endorsed religious model and not a source. The model choice is configuration, so later experiments can compare other local or remote providers without changing evidence retrieval or citation contracts.

## Structured output

The Ollama adapter calls `/api/chat` with:

- `stream=false`;
- `think=false`;
- temperature `0` by default;
- a JSON Schema in `format`;
- the synthesis package rules as the system message;
- the exact package `model_context` as user evidence.

The model must return:

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

or an `INSUFFICIENT_EVIDENCE` draft.

## Post-generation gates

The backend immediately validates:

- synthesis-package integrity;
- allowed source ids;
- absence of unknown citation ids such as `S99`;
- at least one structured claim for `ANSWERED`;
- at least one allowed citation for every structured `ANSWERED` claim.

A passing draft receives status:

```text
STRUCTURALLY_VALID_PENDING_ENTAILMENT
```

This still means **not releasable**. The response contains:

```text
semantic_entailment_checked = false
releasable_answer = null
```

The next required quality gate is semantic claim-to-source entailment: verifying that each cited passage actually supports the associated claim.

## Local setup

Install/start Ollama on the Windows host, then download the development model:

```powershell
ollama pull qwen3:8b
```

In the project's real `.env`, change only:

```text
SYNTHESIS_PROVIDER=ollama
```

The other defaults may remain unless the local setup differs. Restart the API container so settings are reloaded:

```powershell
docker compose restart api
```

## Generate a candidate draft

```powershell
$body = @{
  question = "ما حكم المضاربة؟"
  limit = 5
  work_uri = "0595IbnRushdHafid.BidayatMujtahid"
  include_rejected = $false
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/generate-synthesis" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

A technically successful response is still only a candidate draft. Do not present it as a final religious answer while `semantic_entailment_checked` is false.

## Failure behavior

The endpoint fails closed:

- provider disabled -> HTTP 503;
- Ollama unreachable -> HTTP 503;
- provider returns invalid structured output -> HTTP 502;
- evidence index/storage unavailable -> HTTP 503;
- structurally invalid citations -> response status `REJECTED_STRUCTURAL_VALIDATION` and `releasable_answer=null`.

No generation path changes the immutable corpus, Qdrant index, or PostgreSQL source text.
