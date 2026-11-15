"""Scoring a filled annotation sheet (agreement is only meaningful if the
computation is identical every time)."""

from __future__ import annotations

import pytest

from scripts.score_l3_annotation import kappa, score

JUDGEMENT = {
    "verdicts": [
        {"id": "p01", "verdict": "partial", "reason": ""},
        {"id": "p02", "verdict": "supported", "reason": ""},
        {"id": "p03", "verdict": "partial", "reason": ""},
    ]
}


def _sheet(*verdicts: str) -> dict:
    ids = ["p01", "p02", "p03"]
    return {
        "items": [
            {"id": f"a{i:02d}", "source_id": sid, "verdict": v}
            for i, (sid, v) in enumerate(zip(ids, verdicts), 1)
        ]
    }


def test_perfect_agreement_is_one_and_kappa_one():
    report = score(_sheet("partial", "supported", "partial"), JUDGEMENT)

    assert report["agreement"] == 1.0
    assert report["kappa_binary"] == 1.0


def test_one_disagreement_is_reported_per_stratum():
    report = score(_sheet("supported", "supported", "partial"), JUDGEMENT)

    assert report["agreement"] == pytest.approx(0.667)
    # One of the two model-partial rows disagreed; the supported row agreed.
    assert report["by_stratum"]["partial"][0] == 1
    assert report["by_stratum"]["supported"][0] == 1


def test_an_unfilled_verdict_is_an_error_not_a_disagreement():
    with pytest.raises(ValueError, match="a02"):
        score(_sheet("partial", "", "partial"), JUDGEMENT)


def test_an_unknown_source_id_is_an_error():
    sheet = _sheet("partial", "supported", "partial")
    sheet["items"][1]["source_id"] = "p99"

    with pytest.raises(ValueError, match="p99"):
        score(sheet, JUDGEMENT)


def test_kappa_is_zero_when_the_two_sides_agree_by_chance_only():
    """Two supported, two not, disagreeing on both: po == pe == 0.5."""
    pairs = [
        ("supported", "supported"),
        ("supported", "not"),
        ("not", "supported"),
        ("not", "not"),
    ]

    assert kappa(pairs) == 0.0
