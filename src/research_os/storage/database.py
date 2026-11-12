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
