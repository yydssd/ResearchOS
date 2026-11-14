"""A fixture key must not encode a direction the rule would not produce.

The keys are hand-written so the cascade can be tested without re-running
extraction. That freedom is necessary - scope fields come from chunk context that
a bare sentence does not carry - but it also lets the direction segment drift away
from the rule. Three keys had drifted: p15 read `unchanged` as no-gain while the
rule missed the word, and p20/p21 labelled a pure value report as LEVEL, which
made p21 pass `TRUE_CONTRADICTION` on a pair the spec says must never be one.

Only the direction segment is checkable here: it depends on the text alone. The
scope segments legitimately encode context the sentence does not contain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.research.claims import _direction

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contradiction" / "pairs.json"
PAIRS = json.loads(FIXTURE.read_text(encoding="utf-8"))["pairs"]
CASES = [(entry["id"], side) for entry in PAIRS for side in ("a", "b")]


def _entry(pair_id: str) -> dict:
    return next(entry for entry in PAIRS if entry["id"] == pair_id)


@pytest.mark.parametrize(("pair_id", "side"), CASES, ids=[f"{i}.{s}" for i, s in CASES])
def test_key_direction_matches_the_rule(pair_id: str, side: str):
    entry = _entry(pair_id)
    declared = entry[f"{side}_key"].split("|")[4]
    produced = _direction(entry[f"{side}_text"]) or ""

    assert declared == produced, (
        f"{pair_id}.{side}: key says {declared or 'None'}, rule says {produced or 'None'} "
        f"for {entry[f'{side}_text']!r}"
    )
