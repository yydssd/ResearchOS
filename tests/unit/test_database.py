"""Database initialization tests (P0 acceptance)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from research_os.storage import tables  # noqa: F401  (registers models on Base)
from research_os.storage.database import Base, init_db, session_scope


def test_tables_created(db):
    with session_scope() as session:
        inspector = inspect(session.bind)
        names = set(inspector.get_table_names())
        expected = {
            "questions",
            "works",
            "source_versions",
            "evidence",
            "claims",
            "claim_evidence_relations",
            "contradiction_assessments",
            "runs",
            "tasks",
            "events",
        }
        assert expected <= names, f"missing tables: {expected - names}"


def test_memory_db_is_persistent_within_session(db):
    """A row written in one transaction is visible in the next."""
    with session_scope() as session:
        session.execute(text("INSERT INTO runs (id, question_id, status, current_phase, warnings, budget) "
                             "VALUES ('run_x', 'q_1', 'CREATED', 'created', '[]', '{}')"))
    with session_scope() as session:
        row = session.execute(text("SELECT id FROM runs WHERE id = 'run_x'")).scalar_one_or_none()
        assert row == "run_x"


@pytest.fixture()
def file_database():
    """`init_db(url=...)` replaces the global engine and session factory for the
    rest of the process. Without restoring them, a later test that does not take
    the `db` fixture would silently talk to this test's deleted temp file."""
    yield
    init_db(url="sqlite:///:memory:")


def _old_database_without_unit(url: str) -> None:
    """A pre-S1 database: today's schema minus the unit column.

    Derived from the model instead of hand-written DDL, so "old database" stays
    equal to "current schema minus unit" forever. A hand-written table drifts the
    moment the model gains a column, and the test would keep passing against a
    table that no real database ever had.
    """
    engine = create_engine(url)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE quantitative_evidence DROP COLUMN unit")
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, delta) "
            "VALUES ('e#0','e',0,'dB',0.44)"
        )
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, delta) "
            "VALUES ('e#1','e',1,'percent',0.5)"
        )
    engine.dispose()


def test_unit_backfill_moves_the_old_unit_and_clears_protocol(tmp_path: Path, file_database):
    """`protocol` used to hold the unit. The backfill must move it, not copy it:
    leaving "dB" in protocol would make the field lie about being a protocol."""
    url = f"sqlite:///{tmp_path / 'old.db'}"
    _old_database_without_unit(url)

    init_db(url=url)

    with session_scope() as session:
        rows = session.execute(
            text("SELECT id, unit, protocol FROM quantitative_evidence ORDER BY id")
        ).all()
    assert rows == [("e#0", "dB", None), ("e#1", "percent", None)]


def test_second_init_db_does_not_destroy_the_backfilled_unit(tmp_path: Path, file_database):
    """The backfill runs on every init_db(), so it must be idempotent by data:
    an unguarded `unit = protocol` would set unit to NULL on the second pass,
    because the first pass already cleared protocol. This test is the reason the
    statements carry WHERE clauses instead of running unconditionally."""
    url = f"sqlite:///{tmp_path / 'twice.db'}"
    _old_database_without_unit(url)

    init_db(url=url)
    with session_scope() as session:
        session.execute(
            text("UPDATE quantitative_evidence SET protocol = 'zero-shot' WHERE id = 'e#0'")
        )

    init_db(url=url)  # second start-up, as every CLI run and every test fixture does

    with session_scope() as session:
        row = session.execute(
            text("SELECT unit, protocol FROM quantitative_evidence WHERE id = 'e#0'")
        ).one()
    assert row == ("dB", "zero-shot")


def test_backfill_normalises_vocabulary_and_never_drops_a_unit(tmp_path: Path, file_database):
    """Legacy rows are not constrained by the extractor: a hand-edited database may
    say 'DB', 'dB ', or carry an empty-string unit. The guards normalise the first
    two and treat the third as "no value" - with `unit IS NULL` the empty string
    would count as filled, the protocol would be cleared, and the unit would be
    gone with no copy left anywhere. A real protocol ('zero-shot') must survive."""
    url = f"sqlite:///{tmp_path / 'variants.db'}"
    _old_database_without_unit(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE quantitative_evidence ADD COLUMN unit VARCHAR(32)"
        )
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, unit) VALUES "
            "('v#0','e',0,'DB',NULL),"
            "('v#1','e',1,'dB ',NULL),"
            "('v#2','e',2,'dB',''),"
            "('v#3','e',3,'percent','dB'),"
            "('v#4','e',4,'zero-shot',NULL)"
        )
    engine.dispose()

    init_db(url=url)

    with session_scope() as session:
        rows = session.execute(
            text("SELECT id, unit, protocol FROM quantitative_evidence "
                 "WHERE id LIKE 'v#%' ORDER BY id")
        ).all()
    assert rows == [
        ("v#0", "dB", None),      # 'DB' normalised
        ("v#1", "dB", None),      # trailing space normalised
        ("v#2", "dB", None),      # empty-string unit counts as "no value"
        ("v#3", "dB", None),      # an existing unit wins, the old copy is cleared
        ("v#4", None, "zero-shot"),  # a real protocol is not a unit and is untouched
    ]
