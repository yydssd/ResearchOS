"""A verdict without a locatable source is not traceable, whatever its type.

COMPLEMENTARY used to be folded into a count plus five explanations: no claim
ids, no evidence locations. That breaks the same audit chain the other four
types honour, so these tests pin the uniform rendering.
"""

from __future__ import annotations

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim, ContradictionAssessment, Evidence
from research_os.reporting.memo import RunGraph, _render_contradictions


def _graph(*assessments: ContradictionAssessment, stats: dict | None = None) -> RunGraph:
    claims = [Claim(id=f"c{i}", text="t", status=ClaimStatus.SUPPORTED) for i in (1, 2, 3)]
    evidence = [
        Evidence(source_version_id="sv_a", text="x", section="4.1", char_start=0, char_end=80),
    ]
    return RunGraph(
        run_id="run_1",
        question_text="q",
        sources=[],
        evidence=evidence,
        claims=claims,
        supports={"c1": evidence, "c2": evidence},
        assessments=list(assessments),
        assessment_stats=stats or {},
    )


def _complementary() -> ContradictionAssessment:
    return ContradictionAssessment(
        claim_a_id="c1",
        claim_b_id="c2",
        relationship=ContradictionType.COMPLEMENTARY,
        explanation="dataset differs: sidd vs urban100",
        confidence_label=ConfidenceLabel.MEDIUM,
    )


def test_complementary_entries_show_both_claim_ids_and_locations():
    lines = _render_contradictions(_graph(_complementary()))
    start = lines.index("## Complementary findings (1)")
    end = lines.index("## Insufficient evidence (0)")
    section = "\n".join(lines[start:end])

    assert "`c1`" in section and "`c2`" in section
    assert "chars 0-80" in section
    assert "dataset differs: sidd vs urban100" in section


def test_all_skipped_pairs_do_not_claim_there_was_nothing_to_compare():
    """'Assessed 10 of 10' followed by 'No comparable claim pair' contradicts
    itself. When pairs were evaluated but all skipped, say so."""
    stats = {
        "evaluated": 10, "total_before_cap": 10, "coverage": 1.0,
        "skipped_same_value": 10, "assessments": 0,
    }
    lines = _render_contradictions(_graph(stats=stats))

    assert "No comparable claim pair in this run." not in lines
    assert any(
        "evaluated pairs were skipped" in line and "produced no judgement" in line
        for line in lines
    )


def test_an_unassessed_run_says_so_instead_of_looking_like_no_contradictions():
    lines = _render_contradictions(_graph(stats=None))

    assert any("No contradiction assessment" in line for line in lines)
