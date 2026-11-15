"""Replay recorded L3 answers from disk (design §7.6).

Two facts drive the fixture format:

- Chunk ids are generated per run (`new_id("chunk")`), so a recorded `chunk_id`
  can never be resolved on the next run. The recording therefore stores the point's
  position in the prompt, and the reply maps that position onto the ids the current
  prompt carries - the same chunk, by the same order, with a real id.
- The file name hashes the prompt with those ids removed, for the same reason: a
  key made of a per-run id would miss every time and report zero coverage as if the
  model had answered nothing.

A missing recording answers `points: []`. That is the honest reading: the model
was not asked, so it described nothing. The audit turns an all-empty replay into
"LLM 未启用" (Task 7) instead of reporting a coverage number it did not measure.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel

from research_os.llm.base import MethodDescriptionResponse, MethodPointDraft, Message

# `build_prompt` starts every chunk block with `[chunk_xxx] ` at the beginning of
# a line. The `chunk_` prefix is load-bearing: body text can start a line with a
# citation ("[13] Hadsell et al. ..."), and reading that as an id would shift every
# `prompt_index` by one and silently map points onto the wrong chunk.
_ID_LINE = re.compile(r"^\[(chunk_[^\]]*)\] ", re.MULTILINE)


class RecordedPoint(BaseModel):
    """One point as recorded. `prompt_index` replaces `chunk_id` (see module doc)."""

    aspect: str = ""
    statement: str = ""
    quote: str = ""
    prompt_index: int = 0
    section: str | None = None


def prompt_key(prompt: str) -> str:
    """Stable file name for one recording: the prompt without its per-run ids."""
    body = _ID_LINE.sub("", prompt)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def prompt_ids(prompt: str) -> list[str]:
    """Chunk ids in prompt order. Recording and replay must agree on this."""
    return _ID_LINE.findall(prompt)


class RecordedProvider:
    """Reads `{prompt_key}.json` from a fixture directory; never touches the network."""

    def __init__(self, fixture_dir: str | Path) -> None:
        self._dir = Path(fixture_dir)
        self.last_cost_usd: float | None = None

    async def generate(self, messages: list[Message], response_model=None):
        prompt = messages[-1].content if messages else ""
        path = self._dir / f"{prompt_key(prompt)}.json"
        if not path.exists():
            return MethodDescriptionResponse(points=[])
        payload = json.loads(path.read_text(encoding="utf-8"))
        ids = prompt_ids(prompt)
        points = []
        for raw in payload.get("points", []):
            recorded = RecordedPoint(**raw)
            index = recorded.prompt_index
            points.append(
                MethodPointDraft(
                    aspect=recorded.aspect,
                    statement=recorded.statement,
                    quote=recorded.quote,
                    # Out of range leaves the id empty, and the schema defence one
                    # layer up rejects it - a wrong id would be worse than none.
                    chunk_id=ids[index] if 0 <= index < len(ids) else "",
                    section=recorded.section,
                )
            )
        return MethodDescriptionResponse(points=points)

