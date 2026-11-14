"""Database initialization tests (P0 acceptance)."""

from __future__ import annotations

from sqlalchemy import inspect, text

from research_os.storage.database import session_scope


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
