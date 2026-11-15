"""OpenAI-compatible chat completions (one client, many vendors).

Deliberately small: JSON mode, one attempt, errors raised. Retries belong to the
caller's budget, and a silent retry would spend calls the supervisor never counted
(design §7.3).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from research_os.llm.base import MethodDescriptionResponse, Message

DEFAULT_TIMEOUT = 60.0


class OpenAICompatibleProvider:
    """`generate()` posts to `{base_url}/chat/completions` in JSON mode."""

    # (input $/1M, output $/1M). None means "no price table": `last_cost_usd`
    # then stays None and the supervisor leaves the cost counter alone.
    price_per_million: tuple[float, float] | None = None

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model
        self._client = client
        self._timeout = timeout
        self.last_cost_usd: float | None = None

    async def generate(self, messages: list[Message], response_model: type | None = None) -> Any:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            # JSON mode is what makes the draft model parseable at all; without it
            # half the answers arrive wrapped in prose and the schema defence
            # rejects the paper for a formatting reason.
            "response_format": {"type": "json_object"},
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._key}"},
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"timeout talking to the model: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()
        if response.status_code != 200:
            raise RuntimeError(f"model returned {response.status_code}: {response.text[:200]}")
        content = response.json()["choices"][0]["message"]["content"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"model answer was not json: {content[:200]}") from exc
        self.last_cost_usd = self._cost(response.json().get("usage") or {})
        return MethodDescriptionResponse.model_validate(data)

    def _cost(self, usage: dict) -> float | None:
        if self.price_per_million is None:
            return None
        prompt, completion = self.price_per_million
        # Both defaults are 0: a missing usage field means "unknown", and charging
        # a full million tokens for it would inflate the supervisor's ceiling.
        return round(
            usage.get("prompt_tokens", 0) / 1e6 * prompt
            + usage.get("completion_tokens", 0) / 1e6 * completion,
            6,
        )
