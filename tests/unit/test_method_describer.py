"""The sync face of an async provider (design §7.1).

The two things that matter: a call from inside a running event loop must raise a
typed error instead of nesting `asyncio.run` (which corrupts the loop or hangs),
and the response is parsed into the draft model so a bad aspect does not kill the
whole run - it becomes a rejected point with an event, one layer up.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from research_os.domain.models import DocumentChunk
from research_os.llm.base import LLMInEventLoopError, MethodDescriptionResponse, Message
from research_os.llm.describer import SYSTEM_PROMPT, AsyncProviderDescriber, build_prompt


def _chunk(text: str, *, section: str = "Method", index: int = 0) -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{index}", source_version_id="sv_1", section=section,
        chunk_index=index, text=text,
    )


class FakeProvider:
    """Async provider that records the messages it was given."""

    def __init__(self, response: BaseModel | None = None) -> None:
        self.calls = 0
        self.messages: list[Message] = []
        self._response = response or MethodDescriptionResponse(points=[])

    async def generate(self, messages, response_model=None):
        self.calls += 1
        self.messages = list(messages)
        return self._response


def test_describe_runs_the_async_provider_synchronously():
    provider = FakeProvider()
    describer = AsyncProviderDescriber(provider)

    attempt = describer.describe([_chunk("We propose LangProp.")])

    assert provider.calls == 1
    assert attempt.response is not None
    assert attempt.response.points == []
    assert attempt.error is None


def test_a_running_event_loop_is_refused_instead_of_nested():
    provider = FakeProvider()
    describer = AsyncProviderDescriber(provider)

    async def call_inside_loop():
        describer.describe([_chunk("We propose LangProp.")])

    with pytest.raises(LLMInEventLoopError):
        asyncio.run(call_inside_loop())
    assert provider.calls == 0


def test_the_prompt_carries_chunk_ids_and_their_text():
    """The model must answer with a `chunk_id` we can resolve; a prompt without
    ids produces quotes that cannot be located (design §7.4)."""
    chunks = [_chunk("We propose LangProp.", index=0), _chunk("It stores code.", index=1)]
    prompt = build_prompt(chunks)

    assert "chunk_0" in prompt
    assert "chunk_1" in prompt
    assert "We propose LangProp." in prompt
    # The enum lives in the system message; without it the model invents aspects
    # and every answer is rejected one layer up.
    assert "aspect" in SYSTEM_PROMPT


def test_the_prompt_is_bounded_even_on_a_long_paper():
    """A 40-page paper must not become a 200k-token request: the prompt keeps a
    fixed character budget and says so when it truncates."""
    chunks = [_chunk("x" * 5000, index=i) for i in range(30)]
    prompt = build_prompt(chunks)

    assert len(prompt) < 12000
    assert "truncated" in prompt.lower()


def test_a_provider_error_becomes_an_attempt_not_an_exception():
    """The supervisor must be able to log a typed event and carry on; an
    exception escaping here would kill the run at the first flaky response."""

    class BoomProvider:
        async def generate(self, messages, response_model=None):
            raise RuntimeError("upstream 500")

    attempt = AsyncProviderDescriber(BoomProvider()).describe([_chunk("We propose X.")])

    assert attempt.response is None
    assert attempt.error is not None
    assert "500" in attempt.error


def test_building_the_describer_inside_a_loop_is_refused_too():
    """Construction happens during wiring, which is exactly where an async caller
    would do it; failing there names the defect before the first paper loads."""

    async def build_inside_loop():
        return AsyncProviderDescriber(FakeProvider())

    with pytest.raises(LLMInEventLoopError):
        asyncio.run(build_inside_loop())

