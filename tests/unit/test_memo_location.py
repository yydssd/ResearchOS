"""Where a claim's number came from must be readable, and its absence must look
absent. Printing `chars None-None` reads like a location and sends a reader
looking for something that was never recorded.
"""

from __future__ import annotations

from research_os.domain.enums import ClaimStatus
from research_os.domain.models import Claim, Evidence
from research_os.reporting.memo import RunGraph, _claim_location

CLAIM_ID = "c_1"


def _graph(*evidence: Evidence) -> RunGraph:
    claim = Claim(id=CLAIM_ID, text="t", status=ClaimStatus.SUPPORTED)
    return RunGraph(
        run_id="run_1",
        question_text="q",
        sources=[],
        evidence=list(evidence),
        claims=[claim],
        supports={CLAIM_ID: list(evidence)},
    )


def test_offsets_are_shown_when_known():
    ev = Evidence(
        source_version_id="sv_a", text="Restormer improves PSNR.", section="4.1", char_start=74, char_end=150
    )

    assert _claim_location(_graph(ev), CLAIM_ID) == "sv_a · 4.1 · chars 74-150"


def test_a_missing_offset_is_not_rendered_as_a_number():
    ev = Evidence(source_version_id="sv_a", text="Restormer improves PSNR.", section="4.1")

    location = _claim_location(_graph(ev), CLAIM_ID)

    assert location == "sv_a · 4.1"
    assert "None" not in location


def test_a_claim_without_evidence_says_so():
    assert _claim_location(_graph(), CLAIM_ID) == "no locatable evidence"
