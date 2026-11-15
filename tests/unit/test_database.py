"""Database initialization tests (P0 acceptance)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from research_os.storage.database import init_db, session_scope


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


def _old_database_without_unit(url: str) -> None:
    """A pre-S1 database: `quantitative_evidence` has protocol but no unit."""
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE quantitative_evidence ("
            " id VARCHAR(80) PRIMARY KEY, evidence_id VARCHAR(64), seq INTEGER,"
            " dataset VARCHAR(255), metric VARCHAR(64), method TEXT, value FLOAT,"
            " comparator TEXT, comparator_value FLOAT, protocol VARCHAR(64), delta FLOAT)"
        )
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, delta) "
            "VALUES ('e#0','e',0,'dB',0.44)"
        )
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, delta) "
            "VALUES ('e#1','e',1,'percent',0.5)"
        )


def test_unit_backfill_moves_the_old_unit_and_clears_protocol(tmp_path: Path):
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


def test_second_init_db_does_not_destroy_the_backfilled_unit(tmp_path: Path):
    """The backfill runs on every init_db(), so it must be idempotent by data:
    an unguarded `unit = protocol` would set unit to NULL on the second pass,
    because the first pass already cleared protocol. This test is the reason
    both statements carry WHERE clauses instead of running unconditionally."""
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
