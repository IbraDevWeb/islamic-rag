from __future__ import annotations

import json

import httpx
import pytest

from app.synthesis.faithfulness import (
    FAITHFULNESS_JSON_SCHEMA,
    build_faithfulness_request,
    not_applicable_faithfulness,
    verify_claims_ollama,
)


def _package() -> dict:
    return {
        "question": "ما حكم المسألة؟",
        "sources": [
            {
                "source_id": "S1",
                "rank": 1,
                "passage_original": "النص يثبت الحكم المذكور.",
                "citation": {
                    "section_path": ["كتاب المثال"],
                    "volume": 1,
                    "page": 10,
                },
            }
        ],
    }


def _draft() -> dict:
    return {
        "status": "ANSWERED",
        "answer": "الحكم ثابت [S1].",
        "claims": [
            {
                "text": "الحكم ثابت.",
                "citation_ids": ["S1"],
            }
        ],
    }


def test_faithfulness_request_is_source_constrained():
    payload = build_faithfulness_request(_package(), _draft(), model="qwen3:8b")

    assert payload["model"] == "qwen3:8b"
    assert payload["think"] is False
    assert payload["format"] == FAITHFULNESS_JSON_SCHEMA
    assert payload["options"]["temperature"] == 0.0
    assert "الحكم ثابت" in payload["messages"][1]["content"]
    assert "[S1]" in payload["messages"][1]["content"]
    assert "Do not use outside knowledge" in payload["messages"][0]["content"]


@pytest.mark.asyncio
async def test_faithfulness_verifier_accepts_supported_claim():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "checks": [
                                {
                                    "claim_index": 1,
                                    "verdict": "SUPPORTED",
                                    "reason": "The cited passage directly states the proposition.",
                                }
                            ]
                        }
                    ),
                },
                "done_reason": "stop",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_claims_ollama(
            _package(),
            _draft(),
            base_url="http://ollama.test",
            model="qwen3:8b",
            timeout_seconds=10,
            generator_model="qwen3:8b",
            client=client,
        )

    assert result["checked"] is True
    assert result["overall_verdict"] == "SUPPORTED"
    assert result["all_claims_supported"] is True
    assert result["independent_verifier_model"] is False
    assert result["checks"][0]["citation_ids"] == ["S1"]


@pytest.mark.asyncio
async def test_faithfulness_verifier_propagates_unclear():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "checks": [
                                {
                                    "claim_index": 1,
                                    "verdict": "UNCLEAR",
                                    "reason": "The passage is related but does not directly establish the claim.",
                                }
                            ]
                        }
                    ),
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_claims_ollama(
            _package(),
            _draft(),
            base_url="http://ollama.test",
            model="qwen3:8b",
            timeout_seconds=10,
            generator_model="other-model",
            client=client,
        )

    assert result["overall_verdict"] == "UNCLEAR"
    assert result["all_claims_supported"] is False
    assert result["independent_verifier_model"] is True


def test_abstention_faithfulness_is_not_applicable():
    result = not_applicable_faithfulness(reason="abstained")

    assert result["checked"] is False
    assert result["overall_verdict"] == "NOT_APPLICABLE"
    assert result["all_claims_supported"] is None
