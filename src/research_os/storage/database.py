"""SQLAlchemy setup and SQLite initialization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from research_os.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
        )
    return _engine


def init_db(url: str | None = None) -> None:
    """Create all tables. Passing an explicit url (e.g. ':memory:' or a temp
    file) is supported for tests; the global engine is replaced for the test
    session only when url is given."""
    global _engine, _SessionLocal
    target = url or settings.database_url
    kwargs: dict = {}
    if target.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if target in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # keep a single in-memory connection
    engine = create_engine(target, **kwargs)
    if url is not None:
        _engine = engine
        _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    from research_os.storage import tables  # noqa: F401  (registers models on Base)

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations(engine)


# Columns added after the first release. `create_all` only creates missing
# tables, it never ALTERs an existing one, so pre-P2 databases would otherwise
# be missing these columns. Keep this list tiny; introduce Alembic only when a
# migration needs to rewrite data (plan §35: no infrastructure without a
# measurable need).
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "source_versions": {"source_tier": "VARCHAR(32)"},
    "quantitative_evidence": {"delta": "FLOAT"},
    "claims": {"identity_key": "VARCHAR(256)"},
}

# Indexes added after the first release, for the same reason as the columns:
# create_all never touches an existing table, so pre-P5 databases would accept
# the same claim pair twice.
_ADDED_INDEXES: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_pair "
    "ON contradiction_assessments (claim_a_id, claim_b_id)",
)


def _apply_sqlite_migrations(engine) -> None:
    """Idempotently add post-release columns on SQLite databases."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            if not rows:
                continue  # table does not exist yet; create_all just made it
            existing = {row[1] for row in rows}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

        # Runs after create_all, so the table exists on both fresh and old databases.
        for statement in _ADDED_INDEXES:
            conn.exec_driver_sql(statement)


def session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
