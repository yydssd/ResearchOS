"""Synthetic fixtures pin the arithmetic; real labels are checked for contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.method_acquisition_audit import (
    load_labels,
    summarise,
    covered_for,
    cause_for,
    PLACEHOLDER_METHOD,
)

DOMAINS = ("d0", "d1")
LAYERS = ("L1", "L2", "L3", "L4")


def _cell(label, quote=None):
    evidence = [] if quote is None else [
        {"section": "Method", "page_label": None, "chunk_index": 0, "quote": quote}
    ]
    return {"label": label, "evidence": evidence}


def _row(arxiv_id, domain, spec):
    return {
        "arxiv_id": arxiv_id,
        "domain": domain,
        "layers": {layer: _cell(spec[layer][0], spec[layer][1]) for layer in LAYERS},
    }


# present/absent/ambiguous are arranged so every branch below has one hit.
LABELS = [
    _row("a1", "d0", {"L1": ("present", "we introduce A"),
                      "L2": ("absent", None),
                      "L3": ("present", "A routes skills"),
                      "L4": ("absent", None)}),
    _row("a2", "d0", {"L1": ("absent", None),
                      "L2": ("absent", None),
                      "L3": ("ambiguous", None),
                      "L4": ("present", "lr = 3e-4")}),
    _row("b1", "d1", {"L1": ("present", "B is a planner"),
                      "L2": ("present", "B uses a CNN"),
                      "L3": ("present", "B stores memory"),
                      "L4": ("present", "batch 32")}),
    _row("b2", "d1", {"L1": ("present", "B2 extends B"),
                      "L2": ("absent", None),
                      "L3": ("absent", None),
                      "L4": ("absent", None)}),
]

SIDES = {
    "a1": {"structured": True,  "proxy": 2, "L2": False, "L4": False, "empty": False},
    "a2": {"structured": False, "proxy": 0, "L2": False, "L4": True,  "empty": False},
    "b1": {"structured": False, "proxy": 1, "L2": True,  "L4": False, "empty": False},
    "b2": {"structured": True,  "proxy": 3, "L2": False, "L4": False, "empty": False},
}


def test_availability_and_coverage_values():
    report = summarise(LABELS, SIDES, domain_size=2)

    assert report["A"]["d0|L1"] == (1, 2)
    assert report["A"]["d0|L2"] == (0, 2)
    assert report["A"]["d1|L1"] == (2, 2)

    assert report["C"]["d0|L1"] == (1, 1)
    assert report["C"]["d0|L2"] == "N/A"
    assert report["C"]["d0|L3"] == (0, 1)
    assert report["C"]["d0|L4"] == (1, 1)
    assert report["C"]["d1|L1"] == (1, 2)
    assert report["C"]["d1|L2"] == (1, 1)
    assert report["C"]["d1|L4"] == (0, 1)


def test_covered_over_20_and_proxy_and_ambiguous():
    report = summarise(LABELS, SIDES, domain_size=2)

    assert report["covered_over_20"]["d0|L1"] == (1, 2)
    assert report["proxy"] == {"d0": 2, "d1": 4, "total": 6}
    assert report["ambiguous"] == {"total": 1, "d0|L3": 1}


def test_gap_causes_are_classified():
    report = summarise(LABELS, SIDES, domain_size=2)
    assert report["gaps"]["d0|L3|无结构化字段"] == 1
    assert report["gaps"]["d1|L1|无结构化字段"] == 1
    assert report["gaps"]["d1|L3|无结构化字段"] == 1
    assert report["gaps"]["d1|L4|无结构化字段"] == 1
    assert sum(report["gaps"].values()) == 4


def test_every_cell_is_traceable_to_an_arxiv_id():
    report = summarise(LABELS, SIDES, domain_size=2)
    assert len(report["cells"]) == 16
    assert {c["arxiv_id"] for c in report["cells"]} == {"a1", "a2", "b1", "b2"}
    assert all({"layer", "label", "covered"} <= set(c) for c in report["cells"])
    assert sum(1 for c in report["cells"] if c["covered"]) == 4
    assert sum(1 for c in report["cells"] if c["label"] == "ambiguous") == 1


def test_layer_mapping():
    assert covered_for("L1", SIDES["a1"]) is True
    assert covered_for("L1", SIDES["a2"]) is False
    assert covered_for("L2", SIDES["b1"]) is True
    assert covered_for("L3", SIDES["a1"]) is False
    assert covered_for("L4", SIDES["a2"]) is True
    assert cause_for("L3", SIDES["a1"]) == "无结构化字段"
    # Both other causes must be reachable, or cause_for could collapse to a
    # constant and every test above would still pass.
    empty_side = {"structured": False, "proxy": 0, "L2": False, "L4": False, "empty": True}
    assert cause_for("L4", empty_side) == "无来源定位"
    assert cause_for("L2", SIDES["a2"]) == "词表未覆盖"


def test_real_labels_pass_the_contract():
    """The frozen fixture must be loadable, not just the synthetic one."""
    path = Path(__file__).resolve().parents[2] / "tests/fixtures/method_acquisition/labels.json"
    rows = load_labels(path)
    assert len(rows) == 40
    assert len({r["arxiv_id"] for r in rows}) == 40


def test_load_labels_rejects_a_present_cell_without_evidence(tmp_path):
    bad = {"labels": [
        _row("x", "image_restoration", {layer: ("present", None) for layer in LAYERS})
    ]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="present without evidence"):
        load_labels(path)
