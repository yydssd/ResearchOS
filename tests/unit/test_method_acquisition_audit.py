"""Synthetic fixtures pin the arithmetic; real labels are checked for contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.method_acquisition_audit import (
    cause_for,
    covered_for,
    load_labels,
    summarise,
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

# `L3` is observed from the profile's points, not hardcoded: the previous audit
# returned False for L3 by construction, which is why the layer could never be
# seen to start working.
SIDES = {
    "a1": {"L1": True,  "L1_ambiguous": False, "L2": False, "L3": False, "L4": False,
           "proxy": 2, "empty": False},
    "a2": {"L1": False, "L1_ambiguous": False, "L2": False, "L3": False, "L4": True,
           "proxy": 0, "empty": False},
    "b1": {"L1": True,  "L1_ambiguous": False, "L2": True,  "L3": False, "L4": False,
           "proxy": 1, "empty": False},
    "b2": {"L1": False, "L1_ambiguous": True,  "L2": False, "L3": False, "L4": False,
           "proxy": 3, "empty": False},
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
    assert report["gaps"]["d1|L1|命名歧义"] == 1
    assert report["gaps"]["d1|L3|无结构化字段"] == 1
    assert report["gaps"]["d1|L4|词表未覆盖"] == 1
    assert sum(report["gaps"].values()) == 4


def test_every_cell_is_traceable_to_an_arxiv_id():
    report = summarise(LABELS, SIDES, domain_size=2)
    assert len(report["cells"]) == 16
    assert {c["arxiv_id"] for c in report["cells"]} == {"a1", "a2", "b1", "b2"}
    assert all({"layer", "label", "covered"} <= set(c) for c in report["cells"])
    # a1/L1, a2/L4, b1/L1, b1/L2. b2 names two methods, so its L1 is present in
    # the labels but not covered by the system - the case the ambiguity cause
    # exists for.
    assert sum(1 for c in report["cells"] if c["covered"]) == 4
    assert sum(1 for c in report["cells"] if c["label"] == "ambiguous") == 1


def test_layer_mapping():
    assert covered_for("L1", SIDES["a1"]) is True
    assert covered_for("L1", SIDES["a2"]) is False
    assert covered_for("L2", SIDES["b1"]) is True
    assert covered_for("L4", SIDES["a2"]) is True
    # L3 must read the observation, not a constant: a profile with a point turns
    # the cell green even though S2 has no describer.
    assert covered_for("L3", SIDES["a1"]) is False
    assert covered_for("L3", {**SIDES["a1"], "L3": True}) is True
    assert cause_for("L3", SIDES["a1"]) == "无结构化字段"
    # Both other causes must be reachable, or cause_for could collapse to a
    # constant and every test above would still pass.
    empty_side = {**SIDES["a1"], "empty": True}
    assert cause_for("L4", empty_side) == "无来源定位"
    assert cause_for("L2", SIDES["a2"]) == "词表未覆盖"
    # "无结构化字段" means the layer has no field yet (S2's L3), not that the
    # patterns missed: L1 and L4 do have fields, so their cause is the vocabulary.
    assert cause_for("L1", SIDES["a2"]) == "词表未覆盖"
    assert cause_for("L4", SIDES["a1"]) == "词表未覆盖"
    # A paper that named two methods gets the ambiguity cause, not "no field".
    assert cause_for("L1", SIDES["b2"]) == "命名歧义"


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


HTML = """<html><body><h2>Method</h2><p>LangProp stores each policy as code and
scores it by execution feedback.</p></body></html>"""


def _mini_cache(tmp_path):
    (tmp_path / "x.html").write_text(HTML, encoding="utf-8")
    return tmp_path


def test_l3_cause_says_whether_a_describer_was_configured():
    """0/20 for L3 has two very different meanings: "nothing can fill this layer"
    and "nobody asked". After S3 the field exists, so the audit must say which."""
    side = {**SIDES["a1"], "L3_cause": "LLM 未启用"}

    assert cause_for("L3", side) == "LLM 未启用"
    # No hint at all keeps the S2 behaviour for the synthetic fixtures above.
    assert cause_for("L3", SIDES["a1"]) == "无结构化字段"


def test_system_side_reports_an_l3_cause_without_a_describer(tmp_path):
    from scripts.method_acquisition_audit import system_side

    side = system_side("x", _mini_cache(tmp_path))

    assert side["L3"] is False
    assert side["L3_cause"] == "LLM 未启用"


def test_a_describer_with_a_locatable_point_makes_l3_covered(tmp_path):
    """The replay path must be able to move L3; a flag that can only relabel the
    cause would turn "not measured" into "measured as zero"."""
    from scripts.method_acquisition_audit import system_side

    class StubDescriber:
        def describe(self, chunks):
            from research_os.llm.base import DescriptionAttempt, MethodDescriptionResponse, MethodPointDraft

            chunk = chunks[0]
            return DescriptionAttempt(
                response=MethodDescriptionResponse(
                    points=[
                        MethodPointDraft(
                            aspect="mechanism",
                            statement="Stores each policy as code.",
                            quote="LangProp stores each policy as code and scores it by execution feedback.",
                            chunk_id=chunk.id,
                            section=chunk.section,
                        )
                    ]
                )
            )

    side = system_side("x", _mini_cache(tmp_path), StubDescriber())

    assert side["L3"] is True
    assert side["L3_cause"] is None



def test_an_empty_model_answer_has_its_own_cause(tmp_path):
    """Asked and answered with nothing is not "not enabled": the describer ran.
    Labelling it as disabled would hide a real model failure behind a config
    story (S4's D15 was the same mistake in the other direction)."""
    from scripts.method_acquisition_audit import system_side
    from research_os.llm.base import DescriptionAttempt, MethodDescriptionResponse

    class EmptyDescriber:
        def describe(self, chunks):
            return DescriptionAttempt(response=MethodDescriptionResponse(points=[]))

    side = system_side("x", _mini_cache(tmp_path), EmptyDescriber())

    assert side["L3"] is False
    assert side["L3_cause"] == "LLM 空答复"
