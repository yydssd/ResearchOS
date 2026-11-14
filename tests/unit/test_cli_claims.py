"""`claims RUN_ID` must be scoped to one run (plan §28: traceability).

Regression guard: the command used to call `list_all()`, so it printed claims
from every run ever persisted. That makes the listing useless as a trace surface
and lets one run's conclusions leak into another run's audit.
"""

from __future__ import annotations

from pathlib import Path

from research_os.cli import main
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlClaimRepository

QUESTION = "Does spatial degradation conditioning provide value in all-in-one image restoration?"

PAPER_A = (
    "# Result A\n\n"
    "On the Rain100H benchmark our method improves the baseline PSNR by 0.42 dB.\n"
)
PAPER_B = (
    "# Result B\n\n"
    "On the SIDD dataset the method achieves 39.18 dB PSNR compared with 39.01 dB.\n"
)


def _slice(tmp_path: Path, filename: str, text: str) -> str:
    """Run the vertical slice on one small local paper and return its run id."""
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8")
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION)
        supervisor.run_vertical_slice(
            run_id=run.id, sources=[(str(path), filename, "markdown")], reports_dir=tmp_path
        )
        return run.id


def test_claims_command_lists_only_the_requested_run(db, tmp_path, capsys):
    run_a = _slice(tmp_path, "paper_a.md", PAPER_A)
    run_b = _slice(tmp_path, "paper_b.md", PAPER_B)

    with session_scope() as session:
        repo = SqlClaimRepository(session)
        claims_a = {c.id for c in repo.list_by_run(run_a)}
        claims_b = {c.id for c in repo.list_by_run(run_b)}
    assert claims_a and claims_b and claims_a.isdisjoint(claims_b), "runs must own disjoint claims"

    assert main(["claims", run_a]) == 0
    out_a = capsys.readouterr().out
    for claim_id in claims_a:
        assert claim_id in out_a
    for claim_id in claims_b:
        assert claim_id not in out_a, "claim from another run leaked into the listing"

    assert main(["claims", run_b]) == 0
    out_b = capsys.readouterr().out
    for claim_id in claims_b:
        assert claim_id in out_b


def test_claims_command_reports_empty_run_instead_of_listing_everything(db, tmp_path, capsys):
    _slice(tmp_path, "paper_a.md", PAPER_A)

    with session_scope() as session:
        supervisor = Supervisor(session)
        empty_run = supervisor.create_run(question_text=QUESTION).id

    assert main(["claims", empty_run]) == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == "", "an empty run must not print other runs' claims"
    assert "no claims" in captured.err
