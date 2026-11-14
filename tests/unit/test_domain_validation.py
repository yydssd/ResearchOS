"""Domain model validation tests (P0 acceptance)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, EvidenceRelation, SourceType
from research_os.domain.models import (
    Claim,
    ClaimEvidenceRelation,
    Evidence,
    ResearchBudget,
    ResearchQuestion,
    ResearchRun,
    SourceVersion,
)


def test_question_requires_non_blank():
    with pytest.raises(ValidationError):
        ResearchQuestion(question="   ")
    q = ResearchQuestion(question="Does spatial conditioning help restoration?")
    assert q.id.startswith("q_")


def test_evidence_requires_text_and_source():
    with pytest.raises(ValidationError):
        Evidence(source_version_id="sv_1", text="   ")
    with pytest.raises(ValidationError):
        Evidence(text="missing source version id")
    ev = Evidence(source_version_id="sv_1", text="A result sentence.")
    assert ev.id.startswith("e_")
    assert ev.evidence_type.value == "text"


def test_claim_requires_status_and_text():
    with pytest.raises(ValidationError):
        Claim(text="no status")
    claim = Claim(text="A improves Rain100H PSNR", status=ClaimStatus.SUPPORTED)
    assert claim.confidence_label == ConfidenceLabel.LOW
    assert claim.id.startswith("c_")


def test_relation_requires_both_ids():
    rel = ClaimEvidenceRelation(
        claim_id="c_1", evidence_id="e_1", relation=EvidenceRelation.SUPPORTS, rationale="direct"
    )
    assert rel.relation == EvidenceRelation.SUPPORTS


def test_run_has_default_budget_and_state():
    run = ResearchRun(question_id="q_1")
    assert run.status.value == "CREATED"
    assert run.budget.max_llm_calls == 80
    assert run.budget.max_cost_usd == 5.0


def test_source_version_defaults():
    sv = SourceVersion(work_id="w_1", source_type=SourceType.PDF, title="Paper")
    assert sv.verified is False
    assert sv.local_path is None


def test_budget_exceeded_logic():
    b = ResearchBudget(max_llm_calls=1)
    assert not b.exceeded()
    b.llm_calls = 1
    assert b.exceeded()
    c = ResearchBudget(max_cost_usd=0.1)
    c.cost_usd = 0.11
    assert c.exceeded()
