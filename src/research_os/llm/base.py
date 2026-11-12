"""LLM provider interface — replaceable providers, provider-independent research logic."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class LLMProvider(Protocol):
    """Minimal provider contract (plan §11).

    Structured output is requested by passing a response_model; providers must
    validate the result, enforce timeouts, propagate errors, and track usage.
    """

    async def generate(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
    ) -> Any: ...


class UnavailableProvider:
    """Fallback used when no provider is configured.

    Week 1 runs deterministic heuristics and never calls an LLM; this guard
    keeps the contract explicit instead of silently guessing.
    """

    async def generate(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
    ) -> Any:
        raise NotImplementedError("No LLM provider configured; research uses deterministic heuristics.")
