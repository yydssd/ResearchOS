"""Claim synthesis end to end (plan §16, P4 spec §9/§11).

The memo has to make the scope visible: a reader must be able to see that
"0.42 dB on Rain100H" and "39.18 dB on SIDD" were compared, not merged, and how
well each claim is grounded.
"""

from __future__ import annotations

from pathlib import Path

from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, inspect_claim
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlClaimRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
QUESTION = "Does spatial degradation conditioning provide value in all-in-one image restoration?"


def _run_fixture_slice(tmp_path) -> str:
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION, domain="image restoration")
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "sample_paper.md"), "sample_paper", "markdown")],
            reports_dir=tmp_path,
        )
        return run.id


def test_memo_shows_scope_conditions_and_grounding(db, tmp_path):
    run_id = _run_fixture_slice(tmp_path)

    with session_scope() as session:
        memo = build_memo_from_run(session, run_id)

    assert "Scope:" in memo
    assert "Conditions:" in memo
    assert "Grounding:" in memo


def test_memo_lists_claims_that_were_kept_apart(db, tmp_path):
    run_id = _run_fixture_slice(tmp_path)

    with session_scope() as session:
        memo = build_memo_from_run(session, run_id)

    assert "# Claims Kept Separate" in memo
    section = memo.split("# Claims Kept Separate", 1)[1].split("\n# ", 1)[0]
    assert "Rain100H" in section and "SIDD" in section


def test_claims_carry_an_identity_key(db, tmp_path):
    run_id = _run_fixture_slice(tmp_path)

    with session_scope() as session:
        claims = SqlClaimRepository(session).list_by_run(run_id)

    assert claims
    assert all(claim.identity_key for claim in claims)
    supported = [c for c in claims if c.status.value == "SUPPORTED"]
    assert len({c.identity_key for c in supported}) == len(supported)


def test_fixture_status_split_is_four_supported_two_unsupported(db, tmp_path):
    """P4 spec §11.8: only speculation is unsupported; the 0.11 dB sentence is
    supported evidence whose number is now structured by the delta channel."""
    run_id = _run_fixture_slice(tmp_path)

    with session_scope() as session:
        claims = SqlClaimRepository(session).list_by_run(run_id)

    statuses = [claim.status.value for claim in claims]
    assert statuses.count("SUPPORTED") == 4
    assert statuses.count("UNSUPPORTED") == 2


def test_inspect_claim_exposes_identity_and_grounding(db, tmp_path):
    run_id = _run_fixture_slice(tmp_path)

    with session_scope() as session:
        claim = SqlClaimRepository(session).list_by_run(run_id)[0]
        info = inspect_claim(session, run_id, claim.id)

    assert info is not None
    assert info["identity_key"] == claim.identity_key
    assert "grounding" in info


def test_inspect_claim_reports_unit_not_protocol(db, tmp_path):
    """`inspect_claim` is a public surface (CLI `inspect-claim`). It used to emit
    a key named "protocol" whose value was a unit ("dB"), so a reader of that
    payload would conclude the row carried an evaluation protocol."""
    run_id = _run_fixture_slice(tmp_path)

    facts = []
    with session_scope() as session:
        for claim in SqlClaimRepository(session).list_by_run(run_id):
            info = inspect_claim(session, run_id, claim.id)
            for entry in info["chain"]:
                facts.extend(entry["quantitative"])

    assert facts, "the fixture must produce at least one quantitative fact"
    assert any(fact["unit"] == "dB" for fact in facts)
    assert all("protocol" not in fact for fact in facts)
