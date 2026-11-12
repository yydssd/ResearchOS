"""Chunk persistence: provenance must survive the process (plan §15)."""

from __future__ import annotations

from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.loader import load_markdown
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlChunkRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_chunks_roundtrip_with_provenance(db):
    chunks = chunk_pages(load_markdown(FIXTURES / "sample_paper.md"), source_version_id="sv_1")

    with session_scope() as s:
        SqlChunkRepository(s).create_many(chunks)

    with session_scope() as s:
        repo = SqlChunkRepository(s)
        got = repo.list_by_source("sv_1")
        assert len(got) == len(chunks)
        assert [c.chunk_index for c in got] == [c.chunk_index for c in chunks]
        first = repo.get(chunks[0].id)
        assert first is not None
        assert first.text == chunks[0].text
        assert first.content_hash == chunks[0].content_hash
        assert first.section == chunks[0].section


def test_chunk_lookup_by_id_is_possible_for_every_evidence_reference(db):
    chunks = chunk_pages(load_markdown(FIXTURES / "sample_paper.md"), source_version_id="sv_2")
    with session_scope() as s:
        SqlChunkRepository(s).create_many(chunks)

    with session_scope() as s:
        repo = SqlChunkRepository(s)
        for chunk in chunks:
            assert repo.get(chunk.id) is not None
