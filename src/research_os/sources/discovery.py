"""Provider-agnostic discovery loop (plan §14).

This module owns *only* the loop over queries and providers. Budget accounting
and event logging stay in the supervisor, so there is a single place that can
stop a run (plan §26).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from research_os.domain.models import SourceCandidate
from research_os.sources.normalize import normalize_title
from research_os.sources.providers import ProviderError, SearchProvider

# Called before each provider call; returning False stops discovery (budget).
BeforeSearch = Callable[[str, str], bool]
OnError = Callable[[str, ProviderError], None]


@dataclass
class DiscoveryOutcome:
    queries: list[str]
    candidates: list[SourceCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stopped_by_budget: bool = False


def dedupe_candidates(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    """Drop exact repeats produced by running several queries through a provider.

    Without this, the same record found by query 1 and query 2 would inflate the
    "sources discovered" budget counter (plan §26) and make coverage metrics
    meaningless. First occurrence wins, so provider rank stays truthful.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[SourceCandidate] = []
    for candidate in candidates:
        if candidate.doi:
            key = ("doi", candidate.doi)
        elif candidate.arxiv_id:
            key = ("arxiv", candidate.arxiv_id)
        else:
            key = ("title", f"{normalize_title(candidate.title)}|{candidate.year or ''}")
        dedupe_key = (candidate.provider, f"{key[0]}:{key[1]}")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(candidate)
    return unique


def collect_candidates(
    providers: list[SearchProvider],
    queries: list[str],
    limit: int,
    *,
    before_search: BeforeSearch | None = None,
    on_error: OnError | None = None,
) -> DiscoveryOutcome:
    """Run every provider for every query, tolerating per-provider failures.

    A single failing provider must not sink the run: its error is reported and
    the remaining providers still contribute candidates (plan §25).
    """
    outcome = DiscoveryOutcome(queries=list(queries))

    for query in queries:
        for provider in providers:
            if before_search is not None and not before_search(provider.name, query):
                outcome.stopped_by_budget = True
                return outcome
            try:
                outcome.candidates.extend(provider.search(query, limit))
            except ProviderError as exc:
                outcome.errors.append(f"{provider.name}: {exc}")
                if on_error is not None:
                    on_error(provider.name, exc)
    return outcome
