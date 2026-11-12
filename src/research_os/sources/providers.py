"""Search provider adapters (plan §14).

Providers do exactly three things: query one endpoint, map its payload onto
`SourceCandidate`, and surface failures as typed errors. They deliberately do
NOT deduplicate across providers, verify identity, or judge quality - that is
`resolver`/`verification` territory, and keeping it out here is what makes each
provider replaceable and independently testable.

Parsing is split into pure functions (`parse_*`) so recorded payloads can be
replayed offline without any HTTP at all.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Protocol

import httpx

from research_os.domain.enums import FailureType, SourceType
from research_os.domain.models import SourceCandidate
from research_os.sources.normalize import normalize_doi, parse_arxiv

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
DEFAULT_TIMEOUT = 20.0
USER_AGENT = "ResearchOS/0.1 (research-os@local)"


class ProviderError(Exception):
    """Typed provider failure — never swallowed (plan §25)."""

    def __init__(self, failure_type: FailureType, message: str) -> None:
        super().__init__(message)
        self.failure_type = failure_type


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[SourceCandidate]: ...


def _collapse(text: str | None) -> str:
    """Titles and abstracts from APIs arrive with hard-wrapped newlines."""
    return " ".join((text or "").split())


# ---------------------------------------------------------------------------
# arXiv (Atom XML)
# ---------------------------------------------------------------------------


def parse_arxiv_atom(xml_text: str) -> list[SourceCandidate]:
    """Map an arXiv Atom feed onto candidates, preserving provider rank."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderError(FailureType.SOURCE_UNAVAILABLE, f"arxiv payload is not valid XML: {exc}") from exc

    candidates: list[SourceCandidate] = []
    for rank, entry in enumerate(root.findall(f"{ATOM}entry")):
        raw_id = entry.findtext(f"{ATOM}id", default="", namespaces=None)
        parsed = parse_arxiv(raw_id)
        if parsed is None:
            continue
        arxiv_id, version = parsed
        published = entry.findtext(f"{ATOM}published", default="") or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [
            _collapse(a.findtext(f"{ATOM}name", default=""))
            for a in entry.findall(f"{ATOM}author")
        ]
        candidates.append(
            SourceCandidate(
                provider="arxiv",
                provider_rank=rank,
                title=_collapse(entry.findtext(f"{ATOM}title", default="")),
                authors=[a for a in authors if a],
                year=year,
                venue=_collapse(entry.findtext(f"{ARXIV_NS}journal_ref", default="")) or None,
                doi=normalize_doi(entry.findtext(f"{ARXIV_NS}doi", default="")),
                arxiv_id=arxiv_id,
                arxiv_version=version,
                # Version-free abs URL: the version is kept in arxiv_version.
                url=f"https://arxiv.org/abs/{arxiv_id}",
                abstract=_collapse(entry.findtext(f"{ATOM}summary", default="")) or None,
                source_type=SourceType.ARXIV,
                raw={"id": raw_id},
            )
        )
    return candidates


# arXiv ANDs every term, so a long question (which contains mid-sentence
# modifiers like "help" or "ordinary feature") collapses to zero results.
# English research questions put the discriminative modifiers first and the
# domain noun phrase last, so keeping the head and tail terms preserves both
# while dropping the words that only exist in the question, not in titles.
ARXIV_HEAD_TERMS = 2
ARXIV_TAIL_TERMS = 3


def _select_arxiv_terms(tokens: list[str]) -> list[str]:
    limit = ARXIV_HEAD_TERMS + ARXIV_TAIL_TERMS
    if len(tokens) <= limit:
        return tokens
    return tokens[:ARXIV_HEAD_TERMS] + tokens[-ARXIV_TAIL_TERMS:]


def build_arxiv_query(query: str) -> str:
    """Turn a keyword query into an arXiv ``search_query`` expression.

    A quoted string on arXiv is an *exact phrase* search, so wrapping a whole
    question in quotes silently returns nothing. Terms are AND-ed instead, and
    the term list is trimmed head+tail (see constants above) so that AND-ing
    does not zero out the result set. Hyphenated terms stay quoted because
    arXiv's parser treats "-" as an operator.
    """
    tokens = [token for token in query.split() if token]
    if not tokens:
        return 'all:""'
    selected = _select_arxiv_terms(tokens)
    parts = [f'all:"{token}"' if "-" in token else f"all:{token}" for token in selected]
    return " AND ".join(parts)


class ArxivProvider:
    name = "arxiv"
    _BASE_URL = "https://export.arxiv.org/api/query"

    def __init__(self, client: httpx.Client | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._client = client
        self._timeout = timeout

    def search(self, query: str, limit: int) -> list[SourceCandidate]:
        params = {
            "search_query": build_arxiv_query(query),
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
        }
        text = _get_text(self._client, self._timeout, self._BASE_URL, params, provider=self.name)
        return parse_arxiv_atom(text)[:limit]


# ---------------------------------------------------------------------------
# Crossref (JSON)
# ---------------------------------------------------------------------------


def _crossref_year(item: dict) -> int | None:
    """issued first, then print/online dates; each is [[2022, 6, 1], ...]."""
    for key in ("issued", "published-print", "published-online", "published"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def parse_crossref_payload(payload: dict) -> list[SourceCandidate]:
    """Map a Crossref `/works` response onto candidates."""
    items = ((payload or {}).get("message") or {}).get("items") or []
    candidates: list[SourceCandidate] = []
    for rank, item in enumerate(items):
        title = (item.get("title") or [""])[0]
        authors: list[str] = []
        for author in item.get("author") or []:
            given = (author.get("given") or "").strip()
            family = (author.get("family") or "").strip()
            name = " ".join(p for p in (given, family) if p)
            if name:
                authors.append(name)
        venue = (item.get("container-title") or [None])[0]
        is_proceedings = (item.get("type") or "") in ("proceedings-article", "proceedings")
        candidates.append(
            SourceCandidate(
                provider="crossref",
                provider_rank=rank,
                title=_collapse(title),
                authors=authors,
                year=_crossref_year(item),
                venue=_collapse(venue) or None,
                doi=normalize_doi(item.get("DOI")),
                url=item.get("URL"),
                abstract=_collapse(item.get("abstract")) or None,
                source_type=SourceType.CONFERENCE if is_proceedings else SourceType.WEB,
                raw={"type": item.get("type"), "DOI": item.get("DOI")},
            )
        )
    return candidates


class CrossrefProvider:
    name = "crossref"
    _BASE_URL = "https://api.crossref.org/works"
    _SELECT = "DOI,title,author,issued,published-print,published-online,container-title,type,URL,abstract"

    def __init__(self, client: httpx.Client | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._client = client
        self._timeout = timeout

    def search(self, query: str, limit: int) -> list[SourceCandidate]:
        params = {"query.bibliographic": query, "rows": limit, "select": self._SELECT}
        payload = _get_json(self._client, self._timeout, self._BASE_URL, params, provider=self.name)
        return parse_crossref_payload(payload)[:limit]


# ---------------------------------------------------------------------------
# OpenAlex (JSON)
# ---------------------------------------------------------------------------


def parse_openalex_payload(payload: dict) -> list[SourceCandidate]:
    """Map an OpenAlex `/works` response onto candidates."""
    works = (payload or {}).get("results") or []
    candidates: list[SourceCandidate] = []
    for rank, work in enumerate(works):
        authors = [
            _collapse((a.get("author") or {}).get("display_name"))
            for a in work.get("authorships") or []
        ]
        location = (work.get("primary_location") or {}).get("source") or {}
        is_conference = (work.get("type") or "") in ("conference-paper", "proceedings-article")
        doi = normalize_doi(work.get("doi"))
        candidates.append(
            SourceCandidate(
                provider="openalex",
                provider_rank=rank,
                title=_collapse(work.get("display_name")),
                authors=[a for a in authors if a],
                year=work.get("publication_year"),
                venue=_collapse(location.get("display_name")) or None,
                doi=doi,
                url=f"https://doi.org/{doi}" if doi else work.get("id"),
                source_type=SourceType.CONFERENCE if is_conference else SourceType.WEB,
                raw={"type": work.get("type"), "id": work.get("id")},
            )
        )
    return candidates


class OpenAlexProvider:
    name = "openalex"
    _BASE_URL = "https://api.openalex.org/works"
    _SELECT = "id,doi,display_name,publication_year,authorships,primary_location,type"

    def __init__(self, client: httpx.Client | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._client = client
        self._timeout = timeout

    def search(self, query: str, limit: int) -> list[SourceCandidate]:
        params = {"search": query, "per-page": limit, "select": self._SELECT}
        payload = _get_json(self._client, self._timeout, self._BASE_URL, params, provider=self.name)
        return parse_openalex_payload(payload)[:limit]


# ---------------------------------------------------------------------------
# Fixture provider (offline demos and integration tests)
# ---------------------------------------------------------------------------


class FixtureProvider:
    """Replays candidate JSON files from a directory, in filename order.

    Used to keep end-to-end runs reproducible and network-free; never used to
    claim live coverage.
    """

    name = "fixture"

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)

    def search(self, query: str, limit: int) -> list[SourceCandidate]:
        records: list[dict] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ProviderError(FailureType.SOURCE_UNAVAILABLE, f"bad fixture {path}: {exc}") from exc
            if isinstance(loaded, dict):
                loaded = loaded.get("candidates", [])
            records.extend(loaded)

        candidates: list[SourceCandidate] = []
        for rank, record in enumerate(records[:limit]):
            data = dict(record)
            data["provider"] = self.name
            data["provider_rank"] = rank
            data["source_type"] = SourceType(data.get("source_type", SourceType.WEB))
            candidates.append(SourceCandidate(**data))
        return candidates


# ---------------------------------------------------------------------------
# Transport helpers + registry
# ---------------------------------------------------------------------------


def _request(
    client: httpx.Client | None,
    timeout: float,
    url: str,
    params: dict,
    provider: str,
) -> httpx.Response:
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        response = http.get(url, params=params)
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:  # network, timeout, 4xx/5xx
        raise ProviderError(FailureType.NETWORK_ERROR, f"{provider} request failed: {exc}") from exc
    finally:
        if owns_client:
            http.close()


def _get_text(client, timeout, url, params, provider) -> str:
    return _request(client, timeout, url, params, provider).text


def _get_json(client, timeout, url, params, provider) -> dict:
    response = _request(client, timeout, url, params, provider)
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProviderError(FailureType.SOURCE_UNAVAILABLE, f"{provider} returned non-JSON payload: {exc}") from exc


def build_providers(
    names: list[str],
    *,
    client: httpx.Client | None = None,
    fixture_dir: str | Path | None = None,
) -> list[SearchProvider]:
    """Instantiate providers by name; unknown names are a configuration error."""
    providers: list[SearchProvider] = []
    for name in names:
        key = name.strip().lower()
        if key == "arxiv":
            providers.append(ArxivProvider(client=client))
        elif key == "crossref":
            providers.append(CrossrefProvider(client=client))
        elif key == "openalex":
            providers.append(OpenAlexProvider(client=client))
        elif key == "fixture":
            if fixture_dir is None:
                raise ValueError("provider 'fixture' requires fixture_dir")
            providers.append(FixtureProvider(fixture_dir))
        else:
            raise ValueError(f"unknown search provider: {name}")
    return providers
