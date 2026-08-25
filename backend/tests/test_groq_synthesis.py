from __future__ import annotations

import json

import httpx
import pytest

from app.synthesis.groq_provider import generate_groq_draft, verify_claims_groq
from app.synthesis.ollama_provider import SynthesisProviderUnavailable


def _package() -> dict:
    return {
        "package_id": "sp1_test",
        "question": "في أي كتاب يناقش ابن رشد القراض؟",
        "model_context": (
            "QUESTION\nفي أي كتاب يناقش ابن رشد القراض؟\n\n"
            "EVIDENCE SOURCES\n[S1]\nsection: كتاب القراض\n"
            "volume: 2\npage: 178\npassage_original:\nنص أصلي في القراض"
        ),
        "instructions": [
            "Use only the evidence sources provided in this package.",
            "Every factual or legal claim in an ANSWERED draft must cite one or more allowed source ids.",
        ],
        "sources": [
            {
                "source_id": "S1",
                "rank": 1,
                "passage_original": "نص أصلي في القراض",
                "citation": {
                    "section_path": ["كتاب القراض"],
                    "volume": 2,
                    "page": 178,
                },
            }
        ],
    }


def _draft() -> dict:
    return {
        "status": "ANSWERED",
        "answer": "يناقش ابن رشد القراض في كتاب القراض [S1].",
        "claims": [
            {
                "text": "يناقش ابن رشد القراض في كتاب القراض.",
                "citation_ids": ["S1"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_groq_qwen_generation_uses_json_object_and_no_reasoning():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        seen.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(_draft(), ensure_ascii=False),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 35},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        draft, metadata = await generate_groq_draft(
            _package(),
            base_url="https://api.groq.test/openai/v1",
            api_key="test-key",
            model="qwen/qwen3.6-27b",
            timeout_seconds=10,
            client=client,
        )

    assert draft["status"] == "ANSWERED"
    assert seen["response_format"] == {"type": "json_object"}
    assert seen["reasoning_effort"] == "none"
    assert metadata["provider"] == "groq_free_tier_v1"
    assert metadata["model"] == "qwen/qwen3.6-27b"
    assert metadata["prompt_eval_count"] == 120
    assert metadata["eval_count"] == 35


@pytest.mark.asyncio
async def test_groq_gpt_oss_verifier_uses_strict_json_schema_and_is_independent():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "checks": [
                                        {
                                            "claim_index": 1,
                                            "verdict": "SUPPORTED",
                                            "reason": "The cited passage directly identifies كتاب القراض.",
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 20},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_claims_groq(
            _package(),
            _draft(),
            base_url="https://api.groq.test/openai/v1",
            api_key="test-key",
            model="openai/gpt-oss-120b",
            timeout_seconds=10,
            generator_model="qwen/qwen3.6-27b",
            client=client,
        )

    response_format = seen["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert seen["reasoning_effort"] == "low"
    assert result["overall_verdict"] == "SUPPORTED"
    assert result["all_claims_supported"] is True
    assert result["independent_verifier_model"] is True
    assert result["model"] == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_groq_rate_limit_has_no_paid_fallback():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "3"}, json={"error": "limit"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SynthesisProviderUnavailable, match="No paid or automatic fallback"):
            await generate_groq_draft(
                _package(),
                base_url="https://api.groq.test/openai/v1",
                api_key="test-key",
                model="qwen/qwen3.6-27b",
                timeout_seconds=10,
                client=client,
            )
