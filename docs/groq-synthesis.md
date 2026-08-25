# Groq synthesis mode — zero-cost development path

Status: **experimental / opt-in**.

This mode exists so generation and claim verification do not need to run large LLMs on the developer workstation. PostgreSQL, Qdrant, E5 retrieval, evidence hydration, bundle construction and citation integrity remain unchanged.

## Architecture

```text
question
  -> local E5/Qdrant retrieval
  -> authoritative PostgreSQL hydration
  -> evidence bundle S1..Sn
  -> synthesis package
  -> Groq: qwen/qwen3.6-27b (draft generation)
  -> structural citation validator
  -> Groq: openai/gpt-oss-120b (claim-to-citation verifier, when requested)
  -> experimental verdict
```

Only the prepared question/evidence package is sent to the remote LLM provider. The complete database is not uploaded.

## Zero-cost rule

The application has **no paid fallback path**. If Groq returns HTTP 429 because the account's free-tier rate limit is exhausted, the request fails explicitly. The application does not retry through another paid API and does not switch billing plans.

Groq account limits are external to this repository and can change. Check the provider's current Free Plan limits before large evaluation runs.

## Models

Generator:

```text
qwen/qwen3.6-27b
```

The generator uses Groq JSON Object Mode plus the project's Pydantic and synthesis-contract validators. It is not assumed to obey the schema merely because it returned JSON.

Verifier:

```text
openai/gpt-oss-120b
```

The verifier uses Groq Strict Structured Outputs with the project faithfulness JSON schema. It receives only each claim and the passages that claim cites. It must return `SUPPORTED`, `NOT_SUPPORTED`, or `UNCLEAR`.

The generator and verifier are deliberately different models. This is more independent than Qwen verifying its own Qwen output, but it is still an automated model-based check, not scholarly review.

## Configuration

Put secrets only in the untracked local `.env` file:

```text
SYNTHESIS_PROVIDER=groq
GROQ_API_KEY=<your key>
SYNTHESIS_GROQ_URL=https://api.groq.com/openai/v1
SYNTHESIS_GROQ_MODEL=qwen/qwen3.6-27b
SYNTHESIS_GROQ_VERIFIER_MODEL=openai/gpt-oss-120b
SYNTHESIS_TIMEOUT_SECONDS=180
SYNTHESIS_TEMPERATURE=0
```

Never commit a real `GROQ_API_KEY`.

After changing `.env`, recreate the API container so Docker reloads environment variables:

```powershell
docker compose up -d --force-recreate api
```

## Test

```powershell
$body = @{
    question = "في أي كتاب يناقش ابن رشد القراض؟"
    limit = 5
    work_uri = "0595IbnRushdHafid.BidayatMujtahid"
    include_rejected = $false
    verify_claims = $true
} | ConvertTo-Json

$r = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/generate-synthesis" `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))

$r.status
$r.provider
$r.draft.answer
$r.faithfulness_validation
```

A successful experimental answer can reach `FAITHFULNESS_SUPPORTED_EXPERIMENTAL`, but `releasable_answer` remains `null`. The project still requires a proper generation benchmark and stronger release policy before generated legal/religious answers can be treated as publishable.

## Ollama

Ollama remains supported as an optional local/offline mode:

```text
SYNTHESIS_PROVIDER=ollama
```

It is no longer required for normal development when Groq mode is configured.
