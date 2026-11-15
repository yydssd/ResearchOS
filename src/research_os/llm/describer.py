"""Sync face for the L3 describer (design §7.1).

`LLMProvider.generate` is async; the vertical slice is sync. One adapter, one
rule: never nest an event loop. Everything else here is prompt construction,
which is deterministic on purpose - a prompt that changes between runs makes the
recorded fixtures (Task 3) unusable.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from research_os.domain.models import DocumentChunk
from research_os.llm.base import (
    DescriptionAttempt,
    LLMInEventLoopError,
    MethodDescriptionResponse,
    Message,
)

# Chunk text is the only evidence the model is allowed to quote, so the prompt
# budget is in characters of chunk text, not tokens: a token estimate would need
# a tokenizer that differs per provider.
_MAX_CHUNK_CHARS = 9000
_MAX_CHUNKS = 12
_ASPECTS = ("goal", "mechanism", "why_it_works", "io")

SYSTEM_PROMPT = """You extract what a paper says about its own method.

Answer with JSON only: {"points": [{"aspect": ..., "statement": ..., "quote": ...,
"chunk_id": ..., "section": ...}]}.

Rules, all mandatory:
- `quote` must be copied verbatim from the chunk named by `chunk_id`, at least 4
  words, and must appear exactly once in that chunk.
- `statement` must be a paraphrase of that quote in at most 200 characters, and
  it must reuse at least two content words from it.
- `aspect` is one of: goal, mechanism, why_it_works, io.
- Never write a method name, a dataset, a metric or a number here.
- If the chunks do not describe the method, answer {"points": []}.
"""


def _payload(chunks: list[DocumentChunk]) -> tuple[str, bool]:
    """(text, truncated) - method sections first, then everything else."""
    ordered = sorted(
        chunks,
        key=lambda chunk: (0 if "method" in (chunk.section or "").lower() else 1, chunk.chunk_index),
    )
    parts: list[str] = []
    used = 0
    truncated = False
    kept = 0
    for chunk in ordered:
        if kept >= _MAX_CHUNKS or used + len(chunk.text) > _MAX_CHUNK_CHARS:
            truncated = True
            break
        parts.append(f"[{chunk.id}] section={chunk.section or '-'}\n{chunk.text}")
        used += len(chunk.text)
        kept += 1
    if kept < len(ordered):
        truncated = True
    return "\n\n".join(parts), truncated


def build_prompt(chunks: list[DocumentChunk]) -> str:
    """The user message: every chunk line starts with its id.

    Ids are in the prompt because the response must name one; a quote without a
    resolvable id cannot be located and will be dropped as unlocatable.
    """
    body, truncated = _payload(chunks)
    notice = "\n\n[truncated: only the first chunks are shown]" if truncated else ""
    return f"{body}{notice}"


def _refuse_inside_loop() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise LLMInEventLoopError(
        "MethodDescriber.describe() was called from inside a running event loop; "
        "await the provider directly or run this pipeline in a worker thread."
    )


class MethodDescriber(Protocol):
    def describe(self, chunks: list[DocumentChunk]) -> DescriptionAttempt: ...


class AsyncProviderDescriber:
    """Adapts an async `LLMProvider` to the synchronous describer contract."""

    def __init__(self, provider, *, model: str | None = None) -> None:
        self._provider = provider
        self._model = model
        # Fail at construction too: a describer built inside a loop is a wiring
        # defect, and finding it at run start beats finding it mid-paper.
        _refuse_inside_loop()

    def describe(self, chunks: list[DocumentChunk]) -> DescriptionAttempt:
        _refuse_inside_loop()
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=build_prompt(chunks)),
        ]
        try:
            response = asyncio.run(
                self._provider.generate(messages, response_model=MethodDescriptionResponse)
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as an event, never swallowed
            return DescriptionAttempt(response=None, error=f"{type(exc).__name__}: {exc}")
        if not isinstance(response, MethodDescriptionResponse):
            # A provider that ignores `response_model` must not smuggle a dict in.
            try:
                response = MethodDescriptionResponse.model_validate(response)
            except Exception as exc:  # noqa: BLE001
                return DescriptionAttempt(response=None, error=f"schema: {exc}")
        cost = getattr(self._provider, "last_cost_usd", None)
        return DescriptionAttempt(response=response, cost_usd=cost)

