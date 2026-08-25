from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Mapping

import httpx

from app.synthesis.ollama_provider import (
    SynthesisProviderError,
    SynthesisProviderInvalidResponse,
    SynthesisProviderUnavailable,
)

FAITHFULNESS_VERIFIER_ID = "ollama_claim_faithfulness_v1"

FAITHFULNESS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_index": {"type": "integer", "minimum": 1},
                    "verdict": {
                        "type": "string",
                        "enum": ["SUPPORTED", "NOT_SUPPORTED", "UNCLEAR"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["claim_index", "verdict", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["checks"],
    "additionalProperties": False,
}


def _system_prompt() -> str:
    schema = json.dumps(FAITHFULNESS_JSON_SCHEMA, ensure_ascii=False, sort_keys=True)
    return (
        "You are a citation-faithfulness verifier, not a religious authority.\n"
        "Judge only whether each CLAIM is supported by the CITED SOURCE PASSAGES supplied for that claim.\n"
        "Do not use outside knowledge, memory, unstated fiqh principles, or other sources.\n"
        "SUPPORTED means the cited passages directly support the claim.\n"
        "NOT_SUPPORTED means the cited passages contradict it or do not support the asserted proposition.\n"
        "UNCLEAR means support requires material inference, missing context, or the passages are ambiguous.\n"
        "When in doubt choose UNCLEAR.\n"
        "Return only JSON matching this schema and no markdown.\n"
        f"JSON_SCHEMA\n{schema}"
    )


def _verification_context(package: Mapping[str, Any], draft: Mapping[str, Any]) -> str:
    source_map = {
        str(source["source_id"]): source
        for source in package.get("sources", [])
    }
    parts = [f"QUESTION\n{str(package.get('question', '')).strip()}"]
    for index, claim in enumerate(draft.get("claims") or [], start=1):
        citation_ids = [str(value) for value in claim.get("citation_ids") or []]
        blocks: list[str] = []
        for source_id in citation_ids:
            source = source_map.get(source_id)
            if source is None:
                raise ValueError(f"Unknown citation id in faithfulness input: {source_id}")
            citation = source.get("citation") or {}
            section = " > ".join(citation.get("section_path") or [])
            blocks.append(
                "\n".join(
                    [
                        f"[{source_id}]",
                        f"section: {section or 'unavailable'}",
                        f"volume: {citation.get('volume')}",
                        f"page: {citation.get('page')}",
                        "passage_original:",
                        str(source.get("passage_original", "")),
                    ]
                )
            )
        parts.append(
            "\n".join(
                [
                    f"CLAIM {index}",
                    str(claim.get("text", "")).strip(),
                    "CITED SOURCE PASSAGES",
                    "\n\n".join(blocks),
                ]
            )
        )
    return "\n\n".join(parts)


def build_faithfulness_request(
    package: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    model: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    claims = list(draft.get("claims") or [])
    if str(draft.get("status")) != "ANSWERED" or not claims:
        raise ValueError("Faithfulness verification requires an ANSWERED draft with claims")
    if not model.strip():
        raise ValueError("Faithfulness verifier model must not be empty")

    return {
        "model": model.strip(),
        "stream": False,
        "think": False,
        "format": FAITHFULNESS_JSON_SCHEMA,
        "options": {"temperature": float(temperature)},
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _verification_context(package, draft)},
        ],
    }


async def verify_claims_ollama(
    package: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    base_url: str,
    model: str,
    timeout_seconds: float,
    generator_model: str | None = None,
    temperature: float = 0.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    request_payload = build_faithfulness_request(
        package,
        draft,
        model=model,
        temperature=temperature,
    )
    url = base_url.rstrip("/") + "/api/chat"
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)

    started = perf_counter()
    try:
        try:
            response = await client.post(url, json=request_payload)
            response.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise SynthesisProviderUnavailable(
                f"Cannot reach Ollama faithfulness verifier at {base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise SynthesisProviderError(
                f"Ollama faithfulness verifier returned HTTP {exc.response.status_code}: {detail}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SynthesisProviderInvalidResponse(
                "Faithfulness verifier returned a non-JSON HTTP response"
            ) from exc

        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise SynthesisProviderInvalidResponse(
                "Faithfulness verifier response is missing message.content"
            )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SynthesisProviderInvalidResponse(
                "Faithfulness verifier message.content is not valid JSON"
            ) from exc
        raw_checks = parsed.get("checks") if isinstance(parsed, dict) else None
        if not isinstance(raw_checks, list):
            raise SynthesisProviderInvalidResponse(
                "Faithfulness verifier response is missing checks"
            )
    finally:
        elapsed_ms = (perf_counter() - started) * 1000.0
        if owns_client:
            await client.aclose()

    claims = list(draft.get("claims") or [])
    expected_indexes = list(range(1, len(claims) + 1))
    seen_indexes: list[int] = []
    checks_by_index: dict[int, dict[str, Any]] = {}
    for raw in raw_checks:
        if not isinstance(raw, dict):
            raise SynthesisProviderInvalidResponse("Faithfulness check must be an object")
        index = int(raw.get("claim_index", 0))
        verdict = str(raw.get("verdict", ""))
        reason = str(raw.get("reason", "")).strip()
        if verdict not in {"SUPPORTED", "NOT_SUPPORTED", "UNCLEAR"}:
            raise SynthesisProviderInvalidResponse(
                f"Invalid faithfulness verdict for claim {index}: {verdict}"
            )
        if not reason:
            raise SynthesisProviderInvalidResponse(
                f"Faithfulness verifier gave no reason for claim {index}"
            )
        if index in checks_by_index:
            raise SynthesisProviderInvalidResponse(
                f"Duplicate faithfulness check for claim {index}"
            )
        seen_indexes.append(index)
        checks_by_index[index] = {
            "claim_index": index,
            "claim_text": str(claims[index - 1].get("text", "")).strip()
            if 1 <= index <= len(claims)
            else "",
            "citation_ids": [
                str(value) for value in claims[index - 1].get("citation_ids") or []
            ] if 1 <= index <= len(claims) else [],
            "verdict": verdict,
            "reason": reason,
        }

    if sorted(seen_indexes) != expected_indexes:
        raise SynthesisProviderInvalidResponse(
            "Faithfulness verifier did not return exactly one check for every claim"
        )

    checks = [checks_by_index[index] for index in expected_indexes]
    verdicts = {check["verdict"] for check in checks}
    if "NOT_SUPPORTED" in verdicts:
        overall = "NOT_SUPPORTED"
    elif "UNCLEAR" in verdicts:
        overall = "UNCLEAR"
    else:
        overall = "SUPPORTED"

    independent = bool(
        generator_model
        and generator_model.strip()
        and generator_model.strip() != model.strip()
    )
    return {
        "checked": True,
        "verifier_id": FAITHFULNESS_VERIFIER_ID,
        "model": model.strip(),
        "elapsed_ms": round(elapsed_ms, 3),
        "done_reason": payload.get("done_reason"),
        "overall_verdict": overall,
        "all_claims_supported": overall == "SUPPORTED",
        "independent_verifier_model": independent,
        "checks": checks,
        "note": (
            "Experimental semantic support check using only cited passages. "
            + (
                "The verifier model differs from the generator model, but this is still not a scholarly review."
                if independent
                else "The verifier currently uses the same model family/configuration as generation, so this is not an independent production-grade gate."
            )
        ),
    }


def not_applicable_faithfulness(*, reason: str) -> dict[str, Any]:
    return {
        "checked": False,
        "verifier_id": None,
        "model": None,
        "elapsed_ms": None,
        "done_reason": None,
        "overall_verdict": "NOT_APPLICABLE",
        "all_claims_supported": None,
        "independent_verifier_model": False,
        "checks": [],
        "note": reason,
    }
