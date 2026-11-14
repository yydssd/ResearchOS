"""Pure helpers the supervisor uses to turn assessor output into failure events.

These live here rather than next to the vertical-slice tests because they need no
session and no run: the thing under test is a definition, and a definition is
cheaper to pin down without a database in the way.
"""

from __future__ import annotations

from research_os.domain.enums import ConfidenceLabel, ContradictionType, EvidenceRelation
from research_os.domain.models import ClaimEvidenceRelation, ContradictionAssessment
from research_os.orchestration.supervisor import _unlocatable_claims


def _assessment(a: str, b: str) -> ContradictionAssessment:
    return ContradictionAssessment(
        claim_a_id=a,
        claim_b_id=b,
        relationship=ContradictionType.SCOPE_DIFFERENCE,
        explanation="x",
        confidence_label=ConfidenceLabel.LOW,
    )


def _relation(claim_id: str, relation: EvidenceRelation) -> ClaimEvidenceRelation:
    return ClaimEvidenceRelation(
        claim_id=claim_id, evidence_id=f"e_{claim_id}", relation=relation
    )


def test_unlocatable_claims_only_counts_claims_without_supports():
    """Definition must match the memo: no SUPPORTS relation means the claim renders
    as 'no locatable evidence'."""
    assessments = [_assessment("c1", "c2"), _assessment("c3", "c4")]

    relations = [
        _relation("c1", EvidenceRelation.SUPPORTS),
        _relation("c2", EvidenceRelation.BACKGROUND),
        # Only SUPPORTS makes a claim locatable: a qualifying or contradicting
        # source says something about the claim without locating it, so treating
        # either as evidence of location would hide the gap the memo reports.
        _relation("c3", EvidenceRelation.QUALIFIES),
        _relation("c4", EvidenceRelation.CONTRADICTS),
    ]

    assert _unlocatable_claims(assessments, relations) == ["c2", "c3", "c4"]


def test_unlocatable_claims_accepts_a_bare_enum_string():
    """Upstream rows can hand us the string rather than the enum member. Identity
    would call it unsupported and invent a location gap; equality does not."""
    from types import SimpleNamespace

    relations = [SimpleNamespace(claim_id="c1", relation="SUPPORTS")]

    assert _unlocatable_claims([_assessment("c1", "c2")], relations) == ["c2"]
