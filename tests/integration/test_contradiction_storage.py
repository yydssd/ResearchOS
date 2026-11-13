"""Assessment storage must be unique per pair, run-scoped, and idempotent."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim, ContradictionAssessment
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import SqlClaimRepository, SqlContradictionRepository


@pytest.fixture()
def session(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'p5.db'}")
    s = session_factory()()
    yield s
    s.close()


def _assessment(a: str, b: str) -> ContradictionAssessment:
    return ContradictionAssessment(
        claim_a_id=a,
        claim_b_id=b,
        relationship=ContradictionType.SCOPE_DIFFERENCE,
        explanation="dataset differs: rain100h vs sidd",
        confidence_label=ConfidenceLabel.MEDIUM,
    )


def _seed(session, run_id: str, ids: tuple[str, str]) -> None:
    repo = SqlClaimRepository(session)
    for claim_id in ids:
        repo.create(
            Claim(id=claim_id, text="t", status=ClaimStatus.SUPPORTED, identity_key="m|t|sidd|psnr|UP||"),
            run_id=run_id,
        )
    session.commit()


def test_unique_index_exists_on_the_pair(session):
    """A primary key on a truncated pair id is not a constraint on the pair.

    The row id is `con_<a[:10]>_<b[:10]>`, so two distinct pairs sharing their
    first ten characters collide by accident while a genuine duplicate is caught
    for the wrong reason. The uniqueness we rely on has to be declared on the
    columns themselves.
    """
    from sqlalchemy import text

    rows = session.execute(text("PRAGMA index_list('contradiction_assessments')")).all()
    unique = [row for row in rows if row[1] == "uq_contradiction_pair" and row[2]]
    assert unique, f"expected uq_contradiction_pair among {[r[1] for r in rows]}"


def test_duplicate_pair_is_rejected_by_the_database(session):
    _seed(session, "run_1", ("c1", "c2"))
    repo = SqlContradictionRepository(session)
    repo.create(_assessment("c1", "c2"))
    session.commit()

    with pytest.raises(IntegrityError):
        repo.create(_assessment("c1", "c2"))
        session.commit()
    session.rollback()


def test_list_by_run_hides_other_runs(session):
    _seed(session, "run_1", ("c1", "c2"))
    _seed(session, "run_2", ("c3", "c4"))
    repo = SqlContradictionRepository(session)
    repo.create(_assessment("c1", "c2"))
    repo.create(_assessment("c3", "c4"))
    session.commit()

    mine = repo.list_by_run("run_1")

    assert [(x.claim_a_id, x.claim_b_id) for x in mine] == [("c1", "c2")]


def test_replace_for_run_is_idempotent(session):
    _seed(session, "run_1", ("c1", "c2"))
    repo = SqlContradictionRepository(session)
    repo.replace_for_run("run_1", [_assessment("c1", "c2")])
    session.commit()

    deleted = repo.replace_for_run("run_1", [_assessment("c1", "c2")])
    session.commit()

    assert deleted == 1
    assert len(repo.list_by_run("run_1")) == 1


def test_replace_rejects_a_pair_from_another_run(session):
    _seed(session, "run_1", ("c1",))
    _seed(session, "run_2", ("c2",))

    with pytest.raises(ValueError, match="cross_run_pair"):
        SqlContradictionRepository(session).replace_for_run("run_1", [_assessment("c1", "c2")])
