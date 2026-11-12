"""Shared pytest fixtures: in-memory SQLite database per test."""

from __future__ import annotations

import pytest

from research_os.storage.database import init_db


@pytest.fixture()
def db():
    """Fresh in-memory database for each test."""
    init_db(url="sqlite:///:memory:")
    yield
