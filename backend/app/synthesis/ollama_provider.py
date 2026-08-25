from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Mapping

import httpx

OLLAMA_PROVIDER_ID = "ollama_local_v1"

DRAFT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ANSWERED", "INSUFFICIENT_EVIDENCE"],
        },
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citation_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["text", "citation_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "answer", "claims"],
    "additionalProperties": False,
}


class SynthesisProviderError(RuntimeError):
    pass


class SynthesisProviderUnavailable(SynthesisProviderError):
    pass


class SynthesisProviderInvalidResponse(SynthesisProviderError):
    pass


def _system_prompt(package: Mapping[str, Any]) -> str:
    rules = "\n".join(f"- {rule}" for rule in package.get("instructions", []))
    schema = json.dumps(DRAFT_JSON_SCHEMA, ensure_ascii=False, sort_keys=True)
    return (
        "You are a source-constrained synthesis engine.\n"
        "You are not a religious authority and you are never a source.\n"
        "Follow every rule below exactly.\n\n"
        f"RULES\n{rules}\n\n"
        "Return only JSON matching the supplied schema. "
        "Do not add markdown fences or commentary outside JSON.\n"
        f"JSON_SCHEMA\n{schema}"
    )


def build_ollama_request(
    package: Mapping[str, Any],
    *,
    model: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    if not model.strip():
        raise ValueError("Ollama synthesis model must not be empty")

    return {
        "model": model.strip(),
        "stream": False,
        "think": False,
        "format": DRAFT_JSON_SCHEMA,
        "options": {"temperature": float(temperature)},
        "messages": [
            {"role": "system", "content": _system_prompt(package)},
            {
                "role": "user",
                "content": (
                    str(package["model_context"])
                    + "\n\nReturn the source-constrained synthesis as JSON now."
                ),
            },
        ],
    }


async def generate_ollama_draft(
    package: Mapping[str, Any],
    *,
    base_url: str,
    model: str,
    timeout_seconds: float,
    temperature: float = 0.0,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate one structured draft through a local Ollama-compatible endpoint.

    The function deliberately returns an untrusted draft. Callers must run the
    synthesis contract validator before treating even its citation mechanics as valid.
    Semantic claim-to-source entailment is a later, separate gate.
    """

    request_payload = build_ollama_request(
        package,
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
                f"Cannot reach Ollama synthesis provider at {base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise SynthesisProviderError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SynthesisProviderInvalidResponse(
                "Ollama returned a non-JSON HTTP response"
            ) from exc

        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise SynthesisProviderInvalidResponse(
                "Ollama response is missing message.content"
            )

        try:
            draft = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SynthesisProviderInvalidResponse(
                "Ollama message.content is not valid structured JSON"
            ) from exc
        if not isinstance(draft, dict):
            raise SynthesisProviderInvalidResponse(
                "Ollama structured output must be a JSON object"
            )
    finally:
        elapsed_ms = (perf_counter() - started) * 1000.0
        if owns_client:
            await client.aclose()

    metadata = {
        "provider": OLLAMA_PROVIDER_ID,
        "model": model.strip(),
        "elapsed_ms": round(elapsed_ms, 3),
        "done_reason": payload.get("done_reason"),
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
    }
    return draft, metadata
