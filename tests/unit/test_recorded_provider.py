"""Replay recorded L3 answers (design §7.6, ADR-010's pattern).

The point is reproducibility, not convenience: the same fixtures must give the
same audit numbers on a machine with no key and no network. Chunk ids are random
per run, so both the file name and the point's chunk are expressed in terms the
prompt can reproduce: its text and its order.
"""

from __future__ import annotations

import asyncio
import json

from research_os.llm.base import MethodDescriptionResponse
from research_os.llm.recorded import RecordedProvider, prompt_key


def _messages(text: str):
    from research_os.llm.base import Message

    return [Message(role="system", content="s"), Message(role="user", content=text)]


def _write(dir_path, prompt: str, points: list[dict]):
    (dir_path / f"{prompt_key(prompt)}.json").write_text(
        json.dumps({"points": points}), encoding="utf-8"
    )


def test_a_recorded_answer_is_replayed_for_its_chunk_id(tmp_path):
    prompt = "[chunk_0] section=Abstract\nAll-in-one ..."
    _write(
        tmp_path,
        prompt,
        [
            {
                "aspect": "goal",
                "statement": "Restore all degradations with one model.",
                "quote": "All-in-one image restoration aims to handle multiple degradations",
                "prompt_index": 0,
                "section": "Abstract",
            }
        ],
    )
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages(prompt)))

    assert isinstance(response, MethodDescriptionResponse)
    assert response.points[0].chunk_id == "chunk_0"


def test_a_missing_recording_is_an_empty_answer_not_a_crash(tmp_path):
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages("[chunk_9] section=Method\nnope")))

    assert response.points == []


def test_a_bracketed_line_inside_a_chunk_is_not_mistaken_for_an_id(tmp_path):
    """A citation at the start of a line must not shift the index: shifting it maps
    a point onto the wrong chunk, and the validator then rejects a good point as
    unlocatable - a silent coverage loss with no error anywhere."""
    prompt = (
        "[chunk_aaa] section=Method\n[13] Hadsell et al. describe a baseline.\n\n"
        "[chunk_bbb] section=Method\nWe store the policy as code."
    )
    _write(tmp_path, prompt, [{"aspect": "io", "statement": "Policy as code.",
                               "quote": "We store the policy as code", "prompt_index": 1}])
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages(prompt)))

    assert [point.chunk_id for point in response.points] == ["chunk_bbb"]


def test_the_recording_survives_a_new_run_with_new_chunk_ids(tmp_path):
    """Ids are minted per run, so the key must not contain them; otherwise the
    fixture misses on the second run and the audit reports a fake zero."""
    recorded = "[chunk_aaa] section=Method\nWe store the policy as code."
    replayed = "[chunk_bbb] section=Method\nWe store the policy as code."
    _write(tmp_path, recorded, [{"aspect": "io", "statement": "Policy as code.",
                                 "quote": "We store the policy as code", "prompt_index": 0}])
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages(replayed)))

    assert [point.chunk_id for point in response.points] == ["chunk_bbb"]

