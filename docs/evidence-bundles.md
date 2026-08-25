# Evidence bundles

## Goal

`/evidence-bundle` turns already hydrated evidence passages into a deterministic, citation-addressable package for a future synthesis layer.

It does not generate an answer.

Current path:

```text
query
  -> curated terminology expansion
  -> multilingual E5 retrieval
  -> PostgreSQL hydration
  -> evidence bundle
  -> [future] constrained synthesis
```

## Source ids

Every returned passage receives a bundle-local id:

```text
S1
S2
S3
...
```

A future generator will be allowed to cite only these ids. The ids are not scholarly identifiers; they are local handles pointing to full provenance already stored in each citation object.

## Deterministic identity

The bundle exposes:

```text
bundle_version
bundle_id
bundle_sha256
```

The SHA-256 is computed from stable material only: normalized query, query variants, retrieval id, source order, chunk ids, text hashes, source hashes and version URIs. Floating-point retrieval scores are deliberately excluded from identity.

Therefore, the same query with the same ordered immutable evidence set yields the same bundle id.

## Generation contract

The response contains a `generation_contract` but still has no generated answer. Its rules establish the boundary for a later LLM layer:

- only source ids present in the bundle may be cited;
- factual/legal claims require cited support;
- the LLM is never a source;
- bibliographic metadata may not be invented;
- insufficient evidence must be reported explicitly;
- normalized retrieval text is not evidence: `passage_original` plus citation provenance are authoritative.

## Endpoint

Example:

```powershell
$r = Invoke-RestMethod "http://localhost:8000/evidence-bundle?q=المضاربة&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5"
$r | ConvertTo-Json -Depth 20
```

If Windows PowerShell displays Arabic as mojibake (`Ø...`, `Ù...`), this is a local response-decoding/display issue rather than a reason to alter stored corpus text. A robust diagnostic is to save the HTTP bytes and decode the file explicitly as UTF-8:

```powershell
curl.exe -s "http://localhost:8000/evidence-bundle?q=%D8%A7%D9%84%D9%85%D8%B6%D8%A7%D8%B1%D8%A8%D8%A9&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5" -o evidence-bundle.json
Get-Content .\evidence-bundle.json -Raw -Encoding UTF8
```

The endpoint is experimental and does not replace the deterministic lexical `/search` route.
