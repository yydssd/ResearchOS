"""The one place that speaks HTTP to a model (ADR-010: recorded transport)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from research_os.llm.base import Message, MethodDescriptionResponse
from research_os.llm.openai_compat import OpenAICompatibleProvider

MESSAGES = [Message(role="system", content="s"), Message(role="user", content="u")]


def _provider(handler) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        base_url="https://example.invalid/v1", api_key="k", model="m", client=client
    )


def test_a_json_answer_is_parsed_into_the_response_model():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer k"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"points": [
                    {"aspect": "goal", "statement": "s", "quote": "q", "chunk_id": "c"}
                ]})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    response = asyncio.run(_provider(handler).generate(MESSAGES))

    assert isinstance(response, MethodDescriptionResponse)
    assert response.points[0].chunk_id == "c"


def test_usage_becomes_a_cost_estimate():
    """`last_cost_usd` stays None when no price table applies; a made-up number
    would make the budget ceiling depend on a guess."""
    provider = _provider(
        lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "{\"points\": []}"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
        })
    )
    provider.price_per_million = (0.0, 0.0)

    asyncio.run(provider.generate(MESSAGES))

    assert provider.last_cost_usd == 0.0
    assert OpenAICompatibleProvider(base_url="x", api_key="k", model="m").last_cost_usd is None


def test_a_non_200_is_an_error_not_an_empty_answer():
    provider = _provider(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(RuntimeError, match="500"):
        asyncio.run(provider.generate(MESSAGES))


def test_content_that_is_not_json_is_an_error():
    provider = _provider(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json at all"}}]}
        )
    )

    with pytest.raises(RuntimeError, match="json"):
        asyncio.run(provider.generate(MESSAGES))


def test_a_timeout_is_an_error_with_the_timeout_in_the_message():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _provider(handler)

    with pytest.raises(RuntimeError, match="timeout|timed out"):
        asyncio.run(provider.generate(MESSAGES))
