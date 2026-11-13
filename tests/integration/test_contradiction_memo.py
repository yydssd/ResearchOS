"""The memo must show the relation, the reason, and where each claim came from."""

from __future__ import annotations

import pytest

from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, inspect_claim
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import SqlClaimRepository

PAPER_BODY = (
    "# Image denoising\n\n"
    "On SIDD, Restormer improves PSNR by 0.42 dB with a Transformer backbone.\n\n"
    "On SIDD, Restormer shows no improvement in PSNR with a Transformer backbone.\n"
)


@pytest.fixture()
def session(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'memo.db'}")
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


def test_memo_lists_the_assessment_with_its_reason(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    run_id = _slice(Supervisor(session), paper, tmp_path)["run_id"]

    memo = build_memo_from_run(session, run_id)

    assert "# Contradictions and Open Questions" in memo
    assert "Assessed" in memo and "coverage" in memo.lower()
    assert "same scope, opposite direction" in memo or "SCOPE_DIFFERENCE" in memo
    assert "chars" in memo  # evidence location travels with the claim text


def test_inspect_claim_exposes_partners_and_provenance(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    run_id = _slice(Supervisor(session), paper, tmp_path)["run_id"]
    claim = SqlClaimRepository(session).list_by_run(run_id)[0]

    detail = inspect_claim(session, run_id, claim.id)

    assert "contradictions" in detail
    assert detail["contradictions"], "the paired claim should appear as a partner"
    assert "relationship" in detail["contradictions"][0]
