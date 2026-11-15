"""LLM provider interface — replaceable providers, provider-independent research logic."""

from __future__ import annotations

from dataclasses import dataclass
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


class LLMInEventLoopError(RuntimeError):
    """Raised when a sync describer is called from inside a running event loop.

    `asyncio.run` cannot be nested: it would either raise a confusing
    "loop already running" from deep inside the provider, or - worse - the caller
    would wrap it in its own loop and get a hang that looks like a slow model.
    A typed error at the boundary is the only version of this that can be logged.
    """


class MethodPointDraft(BaseModel):
    """One point as the model claims it, before any check.

    Deliberately loose: `aspect` is a plain string and the lengths are unchecked,
    so a malformed answer is *rejected with a reason* one layer up instead of
    raising inside the provider and losing the whole paper (design §7.4).
    """

    aspect: str = ""
    statement: str = ""
    quote: str = ""
    chunk_id: str = ""
    section: str | None = None


class MethodDescriptionResponse(BaseModel):
    """What a describer returns: points only, never a name or a setup.

    L1/L2/L4 are deterministic (S2); letting the model write a name here would
    put an unverified string into the field that attributes every quantitative
    row (ADR-034).
    """

    points: list[MethodPointDraft] = []


@dataclass(frozen=True)
class DescriptionAttempt:
    """One call's outcome, including the two facts the budget needs.

    `response is None` plus `error` means "the call happened and failed";
    `skipped` is not represented here - the supervisor decides that before
    calling, because only it owns the budget (design §7.3).
    """

    response: MethodDescriptionResponse | None
    cost_usd: float | None = None
    error: str | None = None


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
