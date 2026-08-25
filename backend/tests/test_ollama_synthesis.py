from __future__ import annotations

import json

import httpx
import pytest

from app.synthesis.ollama_provider import (
    DRAFT_JSON_SCHEMA,
    SynthesisProviderInvalidResponse,
    build_ollama_request,
    generate_ollama_draft,
)


def _package() -> dict:
    return {
        "package_id": "sp1_test",
        "model_context": (
            "QUESTION\nما حكم المضاربة؟\n\n"
            "EVIDENCE SOURCES\n[S1]\nsection: كتاب القراض\npassage_original:\nنص أصلي"
        ),
        "instructions": [
            "Use only the evidence sources provided in this package.",
            "Every factual or legal claim in an ANSWERED draft must cite one or more allowed source ids.",
        ],
    }


def test_ollama_request_is_schema_constrained_and_disables_thinking():
    payload = build_ollama_request(_package(), model="qwen3:8b")

    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["format"] == DRAFT_JSON_SCHEMA
    assert payload["options"]["temperature"] == 0.0
    assert "[S1]" in payload["messages"][1]["content"]
    assert "Return only JSON" in payload["messages"][0]["content"]


@pytest.mark.asyncio
async def test_generate_ollama_draft_parses_structured_json():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "status": "ANSWERED",
                            "answer": "المسألة مذكورة في باب القراض [S1].",
                            "claims": [
                                {
                                    "text": "المسألة مذكورة في باب القراض.",
                                    "citation_ids": ["S1"],
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
                "done_reason": "stop",
                "prompt_eval_count": 100,
                "eval_count": 20,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        draft, metadata = await generate_ollama_draft(
            _package(),
            base_url="http://ollama.test",
            model="qwen3:8b",
            timeout_seconds=10,
            client=client,
        )

    assert draft["status"] == "ANSWERED"
    assert draft["claims"][0]["citation_ids"] == ["S1"]
    assert metadata["provider"] == "ollama_local_v1"
    assert metadata["model"] == "qwen3:8b"
    assert metadata["done_reason"] == "stop"
    assert seen["format"] == DRAFT_JSON_SCHEMA


@pytest.mark.asyncio
async def test_generate_ollama_draft_rejects_non_json_model_content():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "not json"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SynthesisProviderInvalidResponse):
            await generate_ollama_draft(
                _package(),
                base_url="http://ollama.test",
                model="qwen3:8b",
                timeout_seconds=10,
                client=client,
            )
