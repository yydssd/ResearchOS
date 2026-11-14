"""Work clustering and version merging (plan §7.2, §14).

The central risk this file guards against is over-merging: two different papers
must never collapse into one work just because their titles look alike.
"""

from __future__ import annotations

from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import SourceCandidate
from research_os.sources.resolver import resolve_candidates

AUTODIR_TITLE = "AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion"
AUTODIR_AUTHORS = ["Yitong Jiang", "Zhaoyang Zhang", "Tianfan Xue", "Jinwei Gu"]

AUTODIR_ARXIV = SourceCandidate(
    provider="arxiv",
    provider_rank=8,
    title=AUTODIR_TITLE,
    authors=AUTODIR_AUTHORS,
    year=2023,
    arxiv_id="2310.10123",
    arxiv_version="5",
    source_type=SourceType.ARXIV,
)
AUTODIR_ECCV = SourceCandidate(
    provider="openalex",
    provider_rank=2,
    title=AUTODIR_TITLE,
    authors=AUTODIR_AUTHORS,
    year=2024,
    doi="10.1007/978-3-031-73661-2_19",
    venue="Lecture notes in computer science",
    source_type=SourceType.CONFERENCE,
)


def test_arxiv_and_published_versions_merge_into_one_work():
    resolutions = resolve_candidates([AUTODIR_ARXIV, AUTODIR_ECCV])

    assert len(resolutions) == 1
    resolution = resolutions[0]
    assert len(resolution.versions) == 2
    assert resolution.canonical_version.source_tier == SourceTier.OFFICIAL_PUBLICATION
    assert all(v.work_id == resolution.work.id for v in resolution.versions)


def test_arxiv_version_bump_collapses_to_latest_version():
    v1 = AUTODIR_ARXIV.model_copy(deep=True)
    v1.arxiv_version = "1"

    resolutions = resolve_candidates([v1, AUTODIR_ARXIV])

    assert len(resolutions) == 1
    assert len(resolutions[0].versions) == 1
    assert resolutions[0].versions[0].version == "5"


def test_same_doi_from_two_providers_merges_metadata():
    sparse = AUTODIR_ECCV.model_copy(deep=True)
    sparse.venue = None
    sparse.provider = "crossref"

    resolutions = resolve_candidates([sparse, AUTODIR_ECCV])

    assert len(resolutions[0].versions) == 1
    assert resolutions[0].versions[0].venue == "Lecture notes in computer science"


def test_title_match_with_conflicting_authors_does_not_merge():
    impostor = AUTODIR_ECCV.model_copy(deep=True)
    impostor.doi = None
    impostor.venue = None
    impostor.provider = "crossref"
    impostor.authors = ["Someone Else", "Another Person"]

    resolutions = resolve_candidates([AUTODIR_ARXIV, impostor])

    assert len(resolutions) == 2
    assert any(r.ambiguous for r in resolutions)
    assert any("SOURCE_IDENTITY_AMBIGUOUS" in note for r in resolutions for note in r.notes)


def test_candidate_without_identifier_or_authors_is_unverified():
    anonymous = SourceCandidate(provider="fixture", title="Some blog post", url="https://x", source_type=SourceType.WEB)

    versions = resolve_candidates([anonymous])[0].versions

    assert versions[0].verified is False
    assert "no resolvable identifier" in versions[0].verification_notes


def test_merge_notes_record_the_providers_used():
    resolutions = resolve_candidates([AUTODIR_ARXIV, AUTODIR_ECCV])
    assert any("arxiv" in note and "openalex" in note for note in resolutions[0].notes)
