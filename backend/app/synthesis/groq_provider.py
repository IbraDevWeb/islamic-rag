from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Mapping

import httpx

from app.synthesis.faithfulness import (
    FAITHFULNESS_JSON_SCHEMA,
    FAITHFULNESS_VERIFIER_ID,
    _verification_context,
)
from app.synthesis.ollama_provider import (
    DRAFT_JSON_SCHEMA,
    SynthesisProviderError,
    SynthesisProviderInvalidResponse,
    SynthesisProviderUnavailable,
)

GROQ_PROVIDER_ID = "groq_free_tier_v1"
GROQ_FAITHFULNESS_VERIFIER_ID = "groq_gpt_oss_claim_faithfulness_v1"


def _draft_system_prompt(package: Mapping[str, Any]) -> str:
    rules = "\n".join(f"- {rule}" for rule in package.get("instructions", []))
    schema = json.dumps(DRAFT_JSON_SCHEMA, ensure_ascii=False, sort_keys=True)
    return (
        "You are a source-constrained synthesis engine.\n"
        "You are not a religious authority and you are never a source.\n"
        "Use only the evidence supplied in the user message.\n"
        "Follow every rule below exactly.\n\n"
        f"RULES\n{rules}\n\n"
        "Return only one valid JSON object matching this schema. "
        "Do not add markdown fences or commentary outside JSON.\n"
        f"JSON_SCHEMA\n{schema}"
    )


def _faithfulness_system_prompt() -> str:
    schema = json.dumps(FAITHFULNESS_JSON_SCHEMA, ensure_ascii=False, sort_keys=True)
    return (
        "You are a citation-faithfulness verifier, not a religious authority.\n"
        "Judge only whether each CLAIM is supported by the CITED SOURCE PASSAGES supplied for that claim.\n"
        "Do not use outside knowledge, memory, unstated fiqh principles, or other sources.\n"
        "SUPPORTED means the cited passages directly support the claim.\n"
        "NOT_SUPPORTED means the cited passages contradict it or do not support the asserted proposition.\n"
        "UNCLEAR means support requires material inference, missing context, or the passages are ambiguous.\n"
        "When in doubt choose UNCLEAR.\n"
        "Return only JSON matching the supplied schema and no markdown."
    )


def _chat_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _headers(api_key: str) -> dict[str, str]:
    if not api_key.strip():
        raise ValueError("GROQ_API_KEY is required when SYNTHESIS_PROVIDER=groq")
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }


def _raise_for_groq_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        suffix = f" Retry after {retry_after}s." if retry_after else ""
        raise SynthesisProviderUnavailable(
            "Groq free-tier rate limit reached. No paid or automatic fallback is configured."
            + suffix
        )
    if response.status_code in {401, 403}:
        raise SynthesisProviderUnavailable(
            "Groq authentication failed. Check GROQ_API_KEY in the local .env file."
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise SynthesisProviderError(
            f"Groq returned HTTP {exc.response.status_code}: {detail}"
        ) from exc


def _extract_message_content(payload: Mapping[str, Any], *, label: str) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SynthesisProviderInvalidResponse(f"{label} response is missing choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise SynthesisProviderInvalidResponse(
            f"{label} response is missing choices[0].message.content"
        )
    return content


def _usage_metadata(payload: Mapping[str, Any]) -> tuple[str | None, int | None, int | None]:
    choices = payload.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else {}
    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return (
        str(finish_reason) if finish_reason is not None else None,
        int(usage["prompt_tokens"]) if usage.get("prompt_tokens") is not None else None,
        int(usage["completion_tokens"]) if usage.get("completion_tokens") is not None else None,
    )


async def generate_groq_draft(
    package: Mapping[str, Any],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
    temperature: float = 0.0,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate an untrusted structured draft through Groq's free-tier API path.

    Qwen currently uses JSON Object Mode here because Groq's strict JSON Schema mode
    is limited to supported models. Pydantic + the synthesis validator remain the
    authoritative contract checks after generation.
    """

    if not model.strip():
        raise ValueError("Groq synthesis model must not be empty")

    request_payload = {
        "model": model.strip(),
        "stream": False,
        "temperature": float(temperature),
        "reasoning_effort": "none",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _draft_system_prompt(package)},
            {
                "role": "user",
                "content": (
                    str(package["model_context"])
                    + "\n\nReturn the source-constrained synthesis as JSON now."
                ),
            },
        ],
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)

    started = perf_counter()
    payload: dict[str, Any]
    try:
        try:
            response = await client.post(
                _chat_url(base_url),
                headers=_headers(api_key),
                json=request_payload,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise SynthesisProviderUnavailable(
                f"Cannot reach Groq synthesis provider at {base_url}"
            ) from exc
        _raise_for_groq_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SynthesisProviderInvalidResponse(
                "Groq returned a non-JSON HTTP response"
            ) from exc

        content = _extract_message_content(payload, label="Groq synthesis")
        try:
            draft = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SynthesisProviderInvalidResponse(
                "Groq synthesis content is not valid JSON"
            ) from exc
        if not isinstance(draft, dict):
            raise SynthesisProviderInvalidResponse(
                "Groq synthesis output must be a JSON object"
            )
    finally:
        elapsed_ms = (perf_counter() - started) * 1000.0
        if owns_client:
            await client.aclose()

    done_reason, prompt_tokens, completion_tokens = _usage_metadata(payload)
    metadata = {
        "provider": GROQ_PROVIDER_ID,
        "model": model.strip(),
        "elapsed_ms": round(elapsed_ms, 3),
        "done_reason": done_reason,
        "prompt_eval_count": prompt_tokens,
        "eval_count": completion_tokens,
    }
    return draft, metadata


def _normalize_faithfulness_checks(
    *,
    raw_checks: list[Any],
    draft: Mapping[str, Any],
    model: str,
    elapsed_ms: float,
    done_reason: str | None,
    generator_model: str | None,
) -> dict[str, Any]:
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
        if not 1 <= index <= len(claims):
            raise SynthesisProviderInvalidResponse(
                f"Faithfulness verifier returned unknown claim index {index}"
            )
        seen_indexes.append(index)
        checks_by_index[index] = {
            "claim_index": index,
            "claim_text": str(claims[index - 1].get("text", "")).strip(),
            "citation_ids": [
                str(value) for value in claims[index - 1].get("citation_ids") or []
            ],
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
        "verifier_id": GROQ_FAITHFULNESS_VERIFIER_ID,
        "model": model.strip(),
        "elapsed_ms": round(elapsed_ms, 3),
        "done_reason": done_reason,
        "overall_verdict": overall,
        "all_claims_supported": overall == "SUPPORTED",
        "independent_verifier_model": independent,
        "checks": checks,
        "note": (
            "Experimental claim-to-citation support check using only cited passages. "
            + (
                "The verifier model differs from the generator model, but this is still not a scholarly review."
                if independent
                else "The verifier model is not independent from generation."
            )
        ),
    }


async def verify_claims_groq(
    package: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
    generator_model: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Verify cited-claim support with Groq GPT-OSS strict Structured Outputs."""

    claims = list(draft.get("claims") or [])
    if str(draft.get("status")) != "ANSWERED" or not claims:
        raise ValueError("Faithfulness verification requires an ANSWERED draft with claims")
    if not model.strip():
        raise ValueError("Groq faithfulness verifier model must not be empty")

    request_payload = {
        "model": model.strip(),
        "stream": False,
        "temperature": 0.0,
        "reasoning_effort": "low",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "citation_faithfulness",
                "strict": True,
                "schema": FAITHFULNESS_JSON_SCHEMA,
            },
        },
        "messages": [
            {"role": "system", "content": _faithfulness_system_prompt()},
            {"role": "user", "content": _verification_context(package, draft)},
        ],
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)

    started = perf_counter()
    payload: dict[str, Any]
    try:
        try:
            response = await client.post(
                _chat_url(base_url),
                headers=_headers(api_key),
                json=request_payload,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise SynthesisProviderUnavailable(
                f"Cannot reach Groq faithfulness provider at {base_url}"
            ) from exc
        _raise_for_groq_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SynthesisProviderInvalidResponse(
                "Groq faithfulness verifier returned a non-JSON HTTP response"
            ) from exc

        content = _extract_message_content(payload, label="Groq faithfulness")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SynthesisProviderInvalidResponse(
                "Groq faithfulness content is not valid JSON"
            ) from exc
        raw_checks = parsed.get("checks") if isinstance(parsed, dict) else None
        if not isinstance(raw_checks, list):
            raise SynthesisProviderInvalidResponse(
                "Groq faithfulness response is missing checks"
            )
    finally:
        elapsed_ms = (perf_counter() - started) * 1000.0
        if owns_client:
            await client.aclose()

    done_reason, _prompt_tokens, _completion_tokens = _usage_metadata(payload)
    return _normalize_faithfulness_checks(
        raw_checks=raw_checks,
        draft=draft,
        model=model,
        elapsed_ms=elapsed_ms,
        done_reason=done_reason,
        generator_model=generator_model,
    )
