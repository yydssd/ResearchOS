"""Discovery loop behaviour: budget stop, fault tolerance, dedupe (plan §25/§26)."""

from __future__ import annotations

from research_os.domain.enums import FailureType, SourceType
from research_os.domain.models import SourceCandidate
from research_os.sources.discovery import collect_candidates, dedupe_candidates
from research_os.sources.providers import ProviderError


class _Ok:
    def __init__(self, name: str, candidates: list[SourceCandidate]) -> None:
        self.name = name
        self._candidates = candidates

    def search(self, query: str, limit: int) -> list[SourceCandidate]:
        return list(self._candidates)


class _Broken:
    name = "broken"

    def search(self, query: str, limit: int) -> list[SourceCandidate]:
        raise ProviderError(FailureType.NETWORK_ERROR, "boom")


def test_collect_candidates_survives_a_failing_provider():
    ok = _Ok("ok", [SourceCandidate(provider="ok", title="T1")])
    errors: list[str] = []

    outcome = collect_candidates([_Broken(), ok], ["q"], 5, on_error=lambda name, exc: errors.append(name))

    assert [c.title for c in outcome.candidates] == ["T1"]
    assert outcome.errors and "broken" in outcome.errors[0]
    assert errors == ["broken"]


def test_collect_candidates_stops_when_budget_hook_refuses():
    ok = _Ok("ok", [SourceCandidate(provider="ok", title="T1")])
    calls: list[str] = []

    def budget(provider: str, query: str) -> bool:
        calls.append(provider)
        return len(calls) < 2

    outcome = collect_candidates([ok, ok], ["q1", "q2"], 5, before_search=budget)

    assert outcome.stopped_by_budget is True
    assert len(outcome.candidates) == 1


def test_dedupe_candidates_keeps_first_occurrence_and_order():
    arxiv_a = SourceCandidate(provider="arxiv", title="AutoDIR", arxiv_id="2310.10123", source_type=SourceType.ARXIV)
    arxiv_dup = SourceCandidate(provider="arxiv", title="AutoDIR (v5)", arxiv_id="2310.10123", source_type=SourceType.ARXIV)
    doi_a = SourceCandidate(provider="openalex", title="AutoDIR", doi="10.1007/x")
    nameless_a = SourceCandidate(provider="web", title="Some Post", year=2025)
    nameless_dup = SourceCandidate(provider="web", title="Some  post!", year=2025)

    deduped = dedupe_candidates([arxiv_a, arxiv_dup, doi_a, nameless_a, nameless_dup])

    assert deduped == [arxiv_a, doi_a, nameless_a]
