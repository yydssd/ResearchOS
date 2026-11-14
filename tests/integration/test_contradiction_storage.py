"""Assessment storage must be unique per pair, run-scoped, and idempotent."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim, ContradictionAssessment
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import (
    CrossRunPairError,
    SqlClaimRepository,
    SqlContradictionRepository,
)


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
    """Rerunning must reproduce the same rows, not just the same count.

    Counting alone passes even if the second run writes a different relationship
    or explanation, which is exactly the kind of drift a rerun is supposed to
    prove absent.
    """
    _seed(session, "run_1", ("c1", "c2"))
    repo = SqlContradictionRepository(session)
    items = [_assessment("c1", "c2")]

    repo.replace_for_run("run_1", items)
    session.commit()
    first = [
        (a.claim_a_id, a.claim_b_id, a.relationship.value, a.explanation, a.confidence_label.value)
        for a in repo.list_by_run("run_1")
    ]

    deleted = repo.replace_for_run("run_1", items)
    session.commit()
    second = [
        (a.claim_a_id, a.claim_b_id, a.relationship.value, a.explanation, a.confidence_label.value)
        for a in repo.list_by_run("run_1")
    ]

    assert deleted == 1
    assert len(second) == 1
    assert second == first


def test_replace_rejects_a_pair_from_another_run(session):
    _seed(session, "run_1", ("c1",))
    _seed(session, "run_2", ("c2",))

    with pytest.raises(CrossRunPairError, match="cross_run_pair"):
        SqlContradictionRepository(session).replace_for_run("run_1", [_assessment("c1", "c2")])


def test_list_by_run_hides_a_row_with_a_foreign_b_side(session):
    """ADR-019 applies to both endpoints. `replace_for_run` rejects mixed-run
    writes, but `create()` is public and legacy rows can predate P5; the read
    path still has to keep another run's claim_b out of this run's trace."""
    from sqlalchemy import text

    _seed(session, "run_1", ("c1", "c2"))
    _seed(session, "run_2", ("c3",))
    session.execute(
        text(
            "INSERT INTO contradiction_assessments "
            "(id, claim_a_id, claim_b_id, relationship, explanation, confidence_label) "
            "VALUES ('mixed', 'c1', 'c3', 'SCOPE_DIFFERENCE', 'x', 'MEDIUM')"
        )
    )
    session.commit()

    assert SqlContradictionRepository(session).list_by_run("run_1") == []


def test_replace_cleans_rows_anchored_in_another_run(session):
    """A mixed-run row whose claim_a belongs elsewhere still references one of
    this run's claims, so replace_for_run must delete it - otherwise it survives
    every rerun and the audit chain stays dirty."""
    from sqlalchemy import text

    _seed(session, "run_1", ("c1", "c2"))
    _seed(session, "run_2", ("c3",))
    session.execute(
        text(
            "INSERT INTO contradiction_assessments "
            "(id, claim_a_id, claim_b_id, relationship, explanation, confidence_label) "
            "VALUES ('mixed', 'c3', 'c1', 'SCOPE_DIFFERENCE', 'x', 'MEDIUM')"
        )
    )
    session.commit()

    repo = SqlContradictionRepository(session)
    deleted = repo.replace_for_run("run_1", [])
    session.commit()

    assert deleted == 1
    assert repo.list_all() == []


def test_migration_dedupes_a_legacy_database_before_creating_the_index(tmp_path):
    """The index exists precisely because pre-P5 databases could store the same
    pair twice. Creating it over such a database must converge, not crash the
    whole application at init_db() - that is the case the migration is for."""
    from sqlalchemy import create_engine, text

    from research_os.storage.database import init_db

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    init_db(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX IF EXISTS uq_contradiction_pair")
        for row_id in ("legacy_a", "legacy_b"):
            conn.execute(
                text(
                    "INSERT INTO contradiction_assessments "
                    "(id, claim_a_id, claim_b_id, relationship, explanation, confidence_label) "
                    "VALUES (:id, 'c1', 'c2', 'SCOPE_DIFFERENCE', 'x', 'MEDIUM')"
                ),
                {"id": row_id},
            )
    init_db(url)  # must not raise

    with engine.begin() as conn:
        remaining = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM contradiction_assessments WHERE claim_a_id='c1' AND claim_b_id='c2'"
        ).scalar()
        indexes = [r[1] for r in conn.exec_driver_sql(
            "PRAGMA index_list('contradiction_assessments')"
        ).fetchall()]
    assert remaining == 1
    assert "uq_contradiction_pair" in indexes
