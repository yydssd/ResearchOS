"""The real half of the fixture set is the only evidence in the P5 report that
did not come from the rules themselves. Without this test, replacing every
`a_text`/`b_text` with lorem ipsum would leave the whole suite green.

The HTML cache is gitignored and re-fetchable, so this is an opt-in check: it
skips on a fresh clone and runs wherever the hold-out corpus is present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".holdout_cache"
FIXTURE = ROOT / "tests" / "fixtures" / "contradiction" / "pairs.json"


@pytest.mark.skipif(not CACHE.is_dir(), reason="hold-out HTML cache is gitignored; re-fetch to enable")
def test_every_real_fixture_sentence_is_verbatim_in_its_declared_paper():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real = [entry for entry in payload["pairs"] if entry["source"] == "real"]
    assert len(real) >= 12, "the real subset must not quietly shrink"

    html = {
        path.stem: path.read_text(encoding="utf-8", errors="ignore")
        for path in CACHE.glob("*.html")
    }
    checked = 0
    for entry in real:
        for side in ("a", "b"):
            text = entry[f"{side}_text"]
            declared = entry.get("from") if side == "a" else entry.get("b_from", entry.get("from"))
            assert declared in html, f"{entry['id']}.{side}: missing paper {declared}"
            assert text in html[declared], (
                f"{entry['id']}.{side}: text not verbatim in {declared}"
            )
            checked += 1
    assert checked == 2 * len(real)
