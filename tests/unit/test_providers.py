"""Provider parsing tests against recorded payloads (no network).

The fixtures are real API responses captured on 2026-11-12, so these tests also
guard against provider schema drift without depending on a live connection.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from research_os.domain.enums import FailureType, SourceType
from research_os.sources.providers import (
    ArxivProvider,
    CrossrefProvider,
    FixtureProvider,
    OpenAlexProvider,
    ProviderError,
    build_arxiv_query,
    build_providers,
    parse_arxiv_atom,
    parse_crossref_payload,
    parse_openalex_payload,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _client(payload, *, status: int = 200, as_json: bool = False) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if as_json:
            return httpx.Response(status, json=payload)
        return httpx.Response(status, text=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_arxiv_atom_fixture_parses_ten_candidates():
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    cands = parse_arxiv_atom(xml)

    assert len(cands) == 10
    first = cands[0]
    assert first.provider == "arxiv" and first.provider_rank == 0
    assert first.arxiv_id == "2406.18242" and first.arxiv_version == "1"
    assert first.year == 2024
    assert first.authors[0] == "Dongqi Fan"
    assert first.source_type == SourceType.ARXIV
    assert first.url == "https://arxiv.org/abs/2406.18242"
    assert first.title == "ConStyle v2: A Strong Prompter for All-in-One Image Restoration"


def test_arxiv_provider_uses_injected_client():
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    cands = ArxivProvider(client=_client(xml)).search("all-in-one image restoration", limit=10)
    assert len(cands) == 10


def test_arxiv_query_conjoins_terms_instead_of_phrase_search():
    """A quoted query is an exact-phrase search on arXiv, so long questions
    return zero results. Terms must be AND-ed instead."""
    assert build_arxiv_query("all-in-one image restoration") == (
        'all:"all-in-one" AND all:image AND all:restoration'
    )
    assert build_arxiv_query("") == 'all:""'


def test_arxiv_query_trims_head_and_tail_terms():
    """Long questions contain mid-sentence modifiers ("help", "ordinary") that
    AND-ed with everything else produce zero hits; head+tail keeps the
    discriminative head and the domain noun phrase at the tail."""
    q = build_arxiv_query("spatial degradation conditioning ordinary feature all-in-one image restoration")

    assert q == (
        'all:spatial AND all:degradation AND all:"all-in-one" AND all:image AND all:restoration'
    )
    assert "ordinary" not in q


def test_arxiv_provider_sends_conjoined_query():
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["search_query"] = request.url.params["search_query"]
        return httpx.Response(200, text=xml)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ArxivProvider(client=client).search("degradation representation help all-in-one image restoration", limit=3)

    assert " AND " in seen["search_query"]
    assert "help" not in seen["search_query"]
    assert seen["search_query"].endswith('all:"all-in-one" AND all:image AND all:restoration')


def test_crossref_fixture_parses_venue_authors_and_year():
    payload = json.loads((FIX / "crossref_restormer.json").read_text(encoding="utf-8"))
    cands = parse_crossref_payload(payload)

    restormer = next(c for c in cands if c.doi == "10.1109/cvpr52688.2022.00564")
    assert restormer.title.startswith("Restormer")
    assert restormer.year == 2022
    assert restormer.venue == "2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)"
    assert "Syed Waqas Zamir" in restormer.authors
    assert restormer.source_type == SourceType.CONFERENCE
    assert restormer.provider == "crossref"


def test_openalex_fixture_parses_and_contains_autodir_duplicate():
    payload = json.loads((FIX / "openalex_all_in_one.json").read_text(encoding="utf-8"))
    cands = parse_openalex_payload(payload)

    assert len(cands) == 10
    autodir = next(c for c in cands if c.doi == "10.1007/978-3-031-73661-2_19")
    assert autodir.year == 2024
    assert autodir.venue
    assert autodir.source_type == SourceType.CONFERENCE
    assert "Yitong Jiang" in autodir.authors


def test_openalex_provider_uses_injected_client():
    payload = json.loads((FIX / "openalex_all_in_one.json").read_text(encoding="utf-8"))
    cands = OpenAlexProvider(client=_client(payload, as_json=True)).search("all-in-one image restoration", limit=10)
    assert len(cands) == 10


def test_http_error_becomes_typed_provider_error():
    provider = ArxivProvider(client=_client("boom", status=500))
    with pytest.raises(ProviderError) as exc:
        provider.search("x", limit=1)
    assert exc.value.failure_type == FailureType.NETWORK_ERROR


def test_unparseable_payload_becomes_provider_error():
    provider = CrossrefProvider(client=_client("not json", as_json=False))
    with pytest.raises(ProviderError) as exc:
        provider.search("x", limit=1)
    assert exc.value.failure_type == FailureType.SOURCE_UNAVAILABLE


def test_fixture_provider_reads_local_candidates(tmp_path):
    (tmp_path / "cands.json").write_text(
        json.dumps(
            [
                {"title": "A", "doi": "10.1000/a", "provider": "fixture"},
                {"title": "B", "arxiv_id": "2310.10123"},
            ]
        ),
        encoding="utf-8",
    )
    cands = FixtureProvider(tmp_path).search("anything", limit=5)

    assert len(cands) == 2
    assert all(c.provider == "fixture" for c in cands)
    assert [c.provider_rank for c in cands] == [0, 1]


def test_build_providers_rejects_unknown_names():
    assert [p.name for p in build_providers(["arxiv", "fixture"], fixture_dir=FIX)] == ["arxiv", "fixture"]
    with pytest.raises(ValueError):
        build_providers(["nope"])
