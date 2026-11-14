"""Live provider smoke tests (opt-in).

Skipped by default so the suite stays deterministic and offline; run with
RESEARCHOS_NETWORK_TESTS=1 to confirm the recorded fixtures still match the
real endpoints.
"""

from __future__ import annotations

import os

import pytest

from research_os.orchestration.supervisor import Supervisor
from research_os.sources.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider
from research_os.storage.database import session_scope

pytestmark = pytest.mark.skipif(
    os.environ.get("RESEARCHOS_NETWORK_TESTS") != "1",
    reason="set RESEARCHOS_NETWORK_TESTS=1 to hit live APIs",
)

QUESTION = (
    "Does spatial degradation conditioning provide value beyond ordinary feature "
    "conditioning in all-in-one image restoration?"
)


def test_live_providers_are_parseable():
    assert len(ArxivProvider().search("all-in-one image restoration", limit=3)) == 3
    assert len(OpenAlexProvider().search("all-in-one image restoration", limit=3)) >= 1
    assert len(CrossrefProvider().search("Restormer efficient transformer", limit=3)) >= 1


def test_live_discovery_meets_phase2_acceptance(db):
    with session_scope() as session:
        supervisor = Supervisor(
            session,
            providers=[ArxivProvider(), CrossrefProvider(), OpenAlexProvider()],
        )
        run = supervisor.create_run(QUESTION)
        result = supervisor.run_source_discovery(run.id, limit=10)

        assert result["candidates"] >= 10
        assert result["works"] >= 5
        assert result["verified"] >= 1
        print(
            f"live discovery: {result['candidates']} candidates -> {result['works']} works "
            f"({result['verified']} verified / {result['unverified']} unverified), "
            f"errors={result['errors']}"
        )
