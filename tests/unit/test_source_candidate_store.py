"""Persistence for discovery candidates and source tiers (plan §14 / §8)."""

from __future__ import annotations

import sqlite3

from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import ResearchWork, SourceCandidate, SourceVersion
from research_os.storage.database import init_db, session_scope
from research_os.storage.repositories import (
    SqlSourceCandidateRepository,
    SqlSourceVersionRepository,
    SqlWorkRepository,
)


def test_source_candidate_roundtrip(db):
    cand = SourceCandidate(
        provider="openalex",
        provider_rank=0,
        title="AutoDIR: Automatic All-in-One Image Restoration",
        doi="10.1007/978-3-031-73661-2_19",
        year=2024,
        venue="ECCV",
        source_type=SourceType.CONFERENCE,
        abstract="snippet used for triage only",
        raw={"id": "https://openalex.org/W1"},
    )
    with session_scope() as s:
        SqlSourceCandidateRepository(s).create_many([cand], run_id="run_x")
    with session_scope() as s:
        got = SqlSourceCandidateRepository(s).list_by_run("run_x")
        assert len(got) == 1
        assert got[0].doi == "10.1007/978-3-031-73661-2_19"
        # The abstract is discovery metadata; it must remain on the candidate,
        # never be promoted into the evidence table.
        assert got[0].abstract == "snippet used for triage only"
        assert got[0].raw == {"id": "https://openalex.org/W1"}


def test_source_candidate_resolution_is_recorded(db):
    cand = SourceCandidate(provider="arxiv", title="AutoDIR")
    with session_scope() as s:
        SqlSourceCandidateRepository(s).create_many([cand], run_id="run_x")
        SqlSourceCandidateRepository(s).attach_resolution(cand.id, work_id="w_1", source_version_id="sv_1")
    with session_scope() as s:
        got = SqlSourceCandidateRepository(s).list_all()[0]
        assert got.resolved_work_id == "w_1"
        assert got.resolved_source_version_id == "sv_1"


def test_source_version_carries_tier(db):
    with session_scope() as s:
        work = SqlWorkRepository(s).create(ResearchWork(canonical_title="T"))
        sv = SourceVersion(
            work_id=work.id,
            source_type=SourceType.CONFERENCE,
            title="T",
            source_tier=SourceTier.OFFICIAL_PUBLICATION,
        )
        SqlSourceVersionRepository(s).create(sv)
    with session_scope() as s:
        got = SqlSourceVersionRepository(s).get(sv.id)
        assert got is not None and got.source_tier == SourceTier.OFFICIAL_PUBLICATION


def test_sqlite_migration_adds_source_tier_column(tmp_path):
    """Pre-existing databases (created before P2) must gain the new column:
    SQLAlchemy's create_all never ALTERs an existing table."""
    db_file = tmp_path / "legacy.db"
    con = sqlite3.connect(db_file)
    con.execute("CREATE TABLE source_versions (id VARCHAR(64) PRIMARY KEY)")
    con.commit()
    con.close()

    init_db(url=f"sqlite:///{db_file.as_posix()}")

    con = sqlite3.connect(db_file)
    columns = {row[1] for row in con.execute("PRAGMA table_info(source_versions)")}
    con.close()
    assert "source_tier" in columns
