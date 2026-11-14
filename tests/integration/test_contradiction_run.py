"""A run must produce assessments, log the counts, and never mutate claims."""

from __future__ import annotations

import pytest

from research_os.domain.enums import EventType, FailureType
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import (
    SqlClaimRepository,
    SqlContradictionRepository,
    SqlEventRepository,
    SqlRunRepository,
)

PAPER_BODY = (
    "# Image denoising\n\n"
    "On SIDD, Restormer improves PSNR by 0.42 dB with a Transformer backbone.\n\n"
    "On SIDD, Restormer shows no improvement in PSNR with a Transformer backbone.\n"
)


@pytest.fixture()
def session(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'run.db'}")
    s = session_factory()()
    yield s
    s.close()


def _slice(supervisor: Supervisor, paper, tmp_path) -> dict:
    """Create a run for the paper, then run the vertical slice over it."""
    run = supervisor.create_run(question_text="Does it work?")
    return supervisor.run_vertical_slice(
        run_id=run.id,
        sources=[(str(paper), "paper", "markdown")],
        reports_dir=tmp_path,
    )


class _NoopAssessor:
    """An assessor that finds nothing. Comparing a run that uses it against a run
    that uses the real one isolates P5's effect: any difference in a claim's
    status or confidence would mean the assessor wrote to P4's output."""

    def assess(self, claims):
        from research_os.research.contradiction import PairingStats

        return [], PairingStats()


def test_vertical_slice_records_assessments_without_touching_claims(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")

    supervisor = Supervisor(session)
    result = _slice(supervisor, paper, tmp_path)
    run_id = result["run_id"]

    assessments = SqlContradictionRepository(session).list_by_run(run_id)

    assert assessments, "expected at least one assessment for two same-scope claims"
    assert all(a.explanation for a in assessments)


def test_assessment_does_not_change_claim_outcomes(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")

    quiet = _slice(Supervisor(session, contradiction_assessor=_NoopAssessor()), paper, tmp_path)
    loud = _slice(Supervisor(session), paper, tmp_path)

    def outcomes(run_id):
        return {
            (c.identity_key, c.status.value, c.confidence_label.value)
            for c in SqlClaimRepository(session).list_by_run(run_id)
        }

    assert outcomes(quiet["run_id"]) == outcomes(loud["run_id"])


def test_assessment_records_an_event_with_skip_accounting(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")

    result = _slice(Supervisor(session), paper, tmp_path)
    events = [e for e in SqlEventRepository(session).list_by_run(result["run_id"])
              if e.event_type.value == "CONTRADICTION_ASSESSED"]

    assert len(events) == 1
    payload = events[0].payload
    # Values, not key names: filling every field with 0 would have passed.
    assert payload["assessments"] == sum(payload["by_type"].values())
    assert payload["evaluated"] == payload["total_before_cap"] - payload["skipped_cap"]
    assert 0.0 <= payload["coverage"] <= 1.0
    assert payload["assessments"] >= 1, "the fixture pair is a true contradiction"
    assert payload["judged"] + payload["failed_pairs"] == payload["evaluated"]


class _CrossRunAssessor:
    """Assessor that always returns one pair whose B side belongs to another run.

    Driving the real repository rather than faking `replace_for_run` matters: the
    test fails if the repository stops raising `CrossRunPairError`, because a bare
    ValueError would escape `run_vertical_slice` and the run would never complete.
    """

    def assess(self, claims):
        from research_os.domain.enums import ConfidenceLabel, ContradictionType
        from research_os.domain.models import ContradictionAssessment
        from research_os.research.contradiction import PairingStats

        return (
            [
                ContradictionAssessment(
                    claim_a_id=claims[0].id,
                    claim_b_id="c_from_another_run",
                    relationship=ContradictionType.SCOPE_DIFFERENCE,
                    explanation="planted cross-run pair",
                    confidence_label=ConfidenceLabel.MEDIUM,
                )
            ],
            PairingStats(total_before_cap=1, evaluated=1),
        )


def test_cross_run_rejection_is_logged_and_the_run_survives(session, tmp_path):
    """Plan section 25: a rejected pair must leave a failure event, not kill the run."""
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    supervisor = Supervisor(session, contradiction_assessor=_CrossRunAssessor())

    result = _slice(supervisor, paper, tmp_path)

    events = SqlEventRepository(session).list_by_run(result["run_id"])
    failures = [
        e for e in events
        if e.event_type is EventType.FAILURE and e.failure_type is FailureType.CROSS_RUN_PAIR
    ]
    assert len(failures) == 1
    assert failures[0].payload["claim_b_id"] == "c_from_another_run"
    assert failures[0].payload["dropped"] == 1

    assessed = [e for e in events if e.event_type is EventType.CONTRADICTION_ASSESSED]
    assert assessed[0].payload["assessments"] == 0
    assert assessed[0].payload["dropped"] == 1

    assert result["status"] == "COMPLETED"
    assert SqlContradictionRepository(session).list_all() == []


def test_a_non_cross_run_value_error_is_not_relabelled(session, tmp_path, monkeypatch):
    """Narrowing the catch is the whole point of CrossRunPairError: pydantic's
    ValidationError subclasses ValueError, so a wide catch would relabel a schema
    error as a cross-run rejection and discard the batch in silence."""
    from research_os.storage.repositories import SqlContradictionRepository

    def explode(self, run_id, items):
        raise ValueError("ValidationError: something else entirely")

    monkeypatch.setattr(SqlContradictionRepository, "replace_for_run", explode)

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")

    with pytest.raises(ValueError, match="something else entirely"):
        _slice(Supervisor(session), paper, tmp_path)


def test_failed_pairs_are_reported_in_an_event(session, tmp_path, monkeypatch):
    import research_os.research.contradiction as module

    def always_boom(a, b):
        raise RuntimeError("boom")

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    monkeypatch.setattr(module, "assess_pair", always_boom)

    result = _slice(Supervisor(session), paper, tmp_path)

    failures = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.FAILURE
        and event.failure_type is FailureType.CONTRADICTION_UNRESOLVED
    ]
    assert failures, "expected a CONTRADICTION_UNRESOLVED failure event"
    assert failures[0].payload["failed_pairs"] == 1
    # The event is the only observation channel, so it must carry what raised.
    assert failures[0].payload["evaluated"] == 1
    assert failures[0].payload["by_error"] == {"RuntimeError": 1}
    assert failures[0].payload["first_failure"].startswith("RuntimeError: boom")

    run = SqlRunRepository(session).get(result["run_id"])
    assert any("CONTRADICTION_UNRESOLVED" in w for w in run.warnings)

    assessed = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.CONTRADICTION_ASSESSED
    ]
    assert assessed[0].payload["failed_pairs"] == 1
    assert assessed[0].payload["judged"] == 0

    # The memo is rendered from that payload: claiming 100% coverage while every
    # pair went unjudged is worse than saying nothing. "Skipped" is the bucket a
    # raised pair must stay out of, so both halves are asserted.
    assert "Assessed 0 of 1 candidate pairs" in result["memo"]
    assert "Not judged: 1" in result["memo"]
    assert "Skipped: 1 failed to judge" not in result["memo"]


def test_identical_value_pairs_are_reported_as_a_p4_defect(session, tmp_path):
    """The counter says how many; the event is what makes it actionable without
    reading the payload of every run."""
    from research_os.research.contradiction import PairingStats

    class _SameValueOnly:
        def assess(self, claims):
            return [], PairingStats(total_before_cap=1, evaluated=1, skipped_same_value=1)

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    result = _slice(Supervisor(session, contradiction_assessor=_SameValueOnly()), paper, tmp_path)

    failures = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.FAILURE
        and event.failure_type is FailureType.CONTRADICTION_UNRESOLVED
    ]
    assert any(event.payload.get("skipped_same_value") == 1 for event in failures)
    assert any(
        "share an identical value" in warning
        for warning in SqlRunRepository(session).get(result["run_id"]).warnings
    )


def test_assessed_claims_without_evidence_are_reported(session, tmp_path, monkeypatch):
    """The memo prints 'no locatable evidence'; §6 also wants an event, so the gap
    is visible in the run's failure record and not only in prose."""
    import research_os.orchestration.supervisor as module

    monkeypatch.setattr(module, "_unlocatable_claims", lambda assessments, relations: ["c_fake"])

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    result = _slice(Supervisor(session), paper, tmp_path)

    failures = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.FAILURE
        and event.failure_type is FailureType.CITATION_LOCATION_MISSING
    ]
    assert any(event.payload.get("claim_ids") == ["c_fake"] for event in failures)
    assert any(
        "no locatable evidence" in warning
        for warning in SqlRunRepository(session).get(result["run_id"]).warnings
    )
