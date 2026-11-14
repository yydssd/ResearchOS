"""Offline end-to-end source discovery (plan §14 acceptance).

Recorded provider payloads are replayed through `httpx.MockTransport`, so the
whole P2 pipeline runs with no network: candidates -> canonical works ->
verified versions -> events, and no evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from research_os.domain.enums import EventType
from research_os.orchestration.supervisor import Supervisor
from research_os.sources.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlEventRepository,
    SqlEvidenceRepository,
    SqlSourceCandidateRepository,
    SqlSourceVersionRepository,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _recorded_providers() -> list:
    """Replay the recorded API responses for any request host."""
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    crossref = json.loads((FIX / "crossref_restormer.json").read_text(encoding="utf-8"))
    openalex = json.loads((FIX / "openalex_all_in_one.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "arxiv" in host:
            return httpx.Response(200, text=xml)
        if "crossref" in host:
            return httpx.Response(200, json=crossref)
        return httpx.Response(200, json=openalex)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return [ArxivProvider(client=client), CrossrefProvider(client=client), OpenAlexProvider(client=client)]


def test_discovery_merges_versions_and_keeps_snippets_out_of_evidence(db):
    with session_scope() as session:
        supervisor = Supervisor(session, providers=_recorded_providers())
        run = supervisor.create_run(
            "Does spatial degradation conditioning provide value beyond feature conditioning "
            "in all-in-one image restoration?"
        )
        result = supervisor.run_source_discovery(run.id, limit=10, max_queries=1)

        assert result["candidates"] >= 10
        assert result["works"] >= 5
        assert result["verified"] >= 1

        # AutoDIR exists as an arXiv preprint and an ECCV paper -> one work, two versions
        autodir = [r for r in result["resolutions"] if "autodir" in r.work.canonical_title.lower()]
        assert len(autodir) == 1
        assert len(autodir[0].versions) == 2
        assert {v.source_tier.value for v in autodir[0].versions} == {"PREPRINT", "OFFICIAL_PUBLICATION"}

        # Candidates are persisted with provider metadata and resolution pointers
        candidates = SqlSourceCandidateRepository(session).list_by_run(run.id)
        assert len(candidates) == result["candidates"]
        assert all(c.resolved_work_id for c in candidates)
        assert {c.provider for c in candidates} == {"arxiv", "crossref", "openalex"}

        # Verified and unverified versions are distinguishable
        versions = SqlSourceVersionRepository(session).list_by_run(run.id)
        assert any(v.verified for v in versions)
        assert all(v.verification_notes for v in versions)

        # Discovery never manufactures evidence (plan §14)
        assert SqlEvidenceRepository(session).list_all() == []

        # Supervisor owns budget accounting and emits structured events
        assert supervisor.get_run(run.id).budget.search_calls == 3
        assert supervisor.get_run(run.id).budget.sources_discovered == result["candidates"]
        event_types = {e.event_type for e in SqlEventRepository(session).list_by_run(run.id)}
        assert EventType.SOURCE_DISCOVERED in event_types
        assert EventType.SOURCE_VERIFIED in event_types


def test_provider_failure_is_persisted_not_swallowed(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with session_scope() as session:
        supervisor = Supervisor(session, providers=[ArxivProvider(client=client)])
        run = supervisor.create_run("all-in-one image restoration")
        result = supervisor.run_source_discovery(run.id, limit=5, max_queries=1)

        assert result["candidates"] == 0
        assert result["errors"]
        events = SqlEventRepository(session).list_by_run(run.id)
        failures = [e for e in events if e.event_type == EventType.FAILURE]
        assert failures and failures[0].failure_type is not None
        # No candidates means the run cannot proceed to synthesis
        assert supervisor.get_run(run.id).status.value == "FAILED"
