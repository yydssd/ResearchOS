"""A run must produce assessments, log the counts, and never mutate claims."""

from __future__ import annotations

import pytest

from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import (
    SqlClaimRepository,
    SqlContradictionRepository,
    SqlEventRepository,
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
    for field in ("assessments", "total_before_cap", "evaluated", "coverage",
                  "skipped_missing_dataset", "skipped_missing_metric",
                  "skipped_self_prefilter", "skipped_same_value", "skipped_cap",
                  "by_type", "replaced"):
        assert field in payload, field
