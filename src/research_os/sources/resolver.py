"""Work clustering, version merging, and canonical work identity (plan §7.2, §14).

One logical paper may exist as arXiv v1/v2, conference proceedings, a project
page and a repository; treating those as five independent papers destroys
provenance later. This module resolves candidates into works deterministically
(no LLM), and it refuses to merge when identity evidence conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from research_os.domain.enums import SourceTier
from research_os.domain.models import ResearchWork, SourceCandidate, SourceVersion
from research_os.sources.normalize import (
    author_overlap,
    normalize_title,
    title_similarity,
)
from research_os.sources.verification import assign_tier, verify_version

# Tuned to be conservative: a false merge corrupts provenance, a false split
# only costs one extra work. Do not lower these without fixture evidence.
TITLE_SIMILARITY_THRESHOLD = 0.92
AUTHOR_OVERLAP_THRESHOLD = 0.5
YEAR_TOLERANCE = 1

_TIER_RANK: dict[SourceTier, int] = {
    SourceTier.OFFICIAL_PUBLICATION: 4,
    SourceTier.PREPRINT: 3,
    SourceTier.REPOSITORY: 2,
    SourceTier.WEB: 1,
    SourceTier.UNKNOWN: 0,
}


@dataclass
class WorkResolution:
    """One canonical work plus its versions, and how candidates mapped onto them."""

    work: ResearchWork
    versions: list[SourceVersion]
    canonical_version: SourceVersion
    ambiguous: bool = False
    notes: list[str] = field(default_factory=list)
    candidate_to_version: dict[str, str] = field(default_factory=dict)


@dataclass
class _Cluster:
    members: list[SourceCandidate] = field(default_factory=list)


def resolve_candidates(candidates: list[SourceCandidate]) -> list[WorkResolution]:
    """Group candidates into works, merge duplicate versions, assign tiers."""
    clusters: list[_Cluster] = []
    ambiguous_ids: set[str] = set()

    for candidate in candidates:
        matched = _match_by_identifier(candidate, clusters)
        if matched is None:
            matched = _match_by_metadata(candidate, clusters)
        if matched is not None:
            matched.members.append(candidate)
            continue

        # No cluster accepted this candidate. If it merely *looks* like an
        # existing work but the authors disagree, record the ambiguity instead
        # of silently merging or silently ignoring it.
        if _title_conflicts(candidate, clusters):
            ambiguous_ids.add(candidate.id)
        clusters.append(_Cluster(members=[candidate]))

    resolutions: list[WorkResolution] = []
    for cluster in clusters:
        ambiguous = any(m.id in ambiguous_ids for m in cluster.members)
        resolutions.append(_build_resolution(cluster, ambiguous=ambiguous))
    return resolutions


def _candidate_tier(candidate: SourceCandidate) -> SourceTier:
    return assign_tier(
        candidate.source_type,
        venue=candidate.venue,
        doi=candidate.doi,
        arxiv_id=candidate.arxiv_id,
        url=candidate.url,
    )


def _years_compatible(a: SourceCandidate, b: SourceCandidate) -> bool:
    if a.year is None or b.year is None:
        return True
    return abs(a.year - b.year) <= YEAR_TOLERANCE


def _match_by_identifier(candidate: SourceCandidate, clusters: list[_Cluster]) -> _Cluster | None:
    """Same DOI or same arXiv base id is identity — no fuzzy comparison needed."""
    for cluster in clusters:
        for member in cluster.members:
            if candidate.doi and member.doi and candidate.doi == member.doi:
                return cluster
            if candidate.arxiv_id and member.arxiv_id and candidate.arxiv_id == member.arxiv_id:
                return cluster
    return None


def _match_by_metadata(candidate: SourceCandidate, clusters: list[_Cluster]) -> _Cluster | None:
    for cluster in clusters:
        for member in cluster.members:
            if title_similarity(candidate.title, member.title) < TITLE_SIMILARITY_THRESHOLD:
                continue
            if not _years_compatible(candidate, member):
                continue
            # Missing author metadata is not evidence of a different work, so it
            # is not treated as a conflict here.
            if not candidate.authors or not member.authors:
                return cluster
            if author_overlap(candidate.authors, member.authors) >= AUTHOR_OVERLAP_THRESHOLD:
                return cluster
    return None


def _title_conflicts(candidate: SourceCandidate, clusters: list[_Cluster]) -> bool:
    """True when the title matches a known work but the authors clearly do not."""
    if not candidate.authors:
        return False
    for cluster in clusters:
        for member in cluster.members:
            if not member.authors:
                continue
            if title_similarity(candidate.title, member.title) < TITLE_SIMILARITY_THRESHOLD:
                continue
            if not _years_compatible(candidate, member):
                continue
            if author_overlap(candidate.authors, member.authors) < AUTHOR_OVERLAP_THRESHOLD:
                return True
    return False


def _version_key(candidate: SourceCandidate) -> str:
    """Identity of a *version* inside a work (not of the work itself)."""
    if candidate.doi:
        return f"doi:{candidate.doi}"
    if candidate.arxiv_id:
        return f"arxiv:{candidate.arxiv_id}"
    return f"title:{normalize_title(candidate.title)}|{candidate.year or ''}"


def _first_non_empty(group: list[SourceCandidate], attribute: str):
    for candidate in group:
        value = getattr(candidate, attribute)
        if value:
            return value
    return None


def _max_arxiv_version(group: list[SourceCandidate]) -> str | None:
    versions = [c.arxiv_version for c in group if c.arxiv_version and c.arxiv_version.isdigit()]
    return max(versions, key=int) if versions else None


def _build_version(group: list[SourceCandidate], ambiguous: bool) -> SourceVersion:
    # The most authoritative, most complete candidate supplies the descriptive
    # fields; the others only fill gaps.
    primary = max(
        group,
        key=lambda c: (_TIER_RANK[_candidate_tier(c)], len(c.authors), c.year or 0),
    )
    authors = max((c.authors for c in group), key=len, default=[])
    title = max((c.title for c in group if c.title), key=len, default="")

    version = SourceVersion(
        work_id="",  # assigned once the work exists
        source_type=primary.source_type,
        title=title,
        url=_first_non_empty(group, "url"),
        authors=authors,
        year=_first_non_empty(group, "year"),
        venue=_first_non_empty(group, "venue"),
        doi=_first_non_empty(group, "doi"),
        arxiv_id=_first_non_empty(group, "arxiv_id"),
        version=_max_arxiv_version(group),
    )
    version.source_tier = assign_tier(
        version.source_type,
        venue=version.venue,
        doi=version.doi,
        arxiv_id=version.arxiv_id,
        url=version.url,
    )
    version.verified, version.verification_notes = verify_version(version, ambiguous=ambiguous)

    if len(group) > 1:
        providers = sorted({c.provider for c in group})
        version.verification_notes.append(
            f"merged {len(group)} candidates into one version (providers: {', '.join(providers)})"
        )
    else:
        # Provenance of every version is auditable even when it was not merged.
        version.verification_notes.append(f"discovered via {group[0].provider}")
    return version


def _build_resolution(cluster: _Cluster, ambiguous: bool) -> WorkResolution:
    groups: dict[str, list[SourceCandidate]] = {}
    # Lowest provider rank first, so the highest-ranked result leads each group.
    for candidate in sorted(cluster.members, key=lambda c: (c.provider_rank, c.provider)):
        groups.setdefault(_version_key(candidate), []).append(candidate)

    candidate_to_version: dict[str, str] = {}
    versions: list[SourceVersion] = []
    for group in groups.values():
        version = _build_version(group, ambiguous=ambiguous)
        versions.append(version)
        for candidate in group:
            candidate_to_version[candidate.id] = version.id

    canonical = max(
        versions,
        key=lambda v: (
            _TIER_RANK[v.source_tier or SourceTier.UNKNOWN],
            v.year or 0,
            int(v.version) if (v.version or "").isdigit() else 0,
        ),
    )
    work = ResearchWork(canonical_title=canonical.title, authors=canonical.authors)
    for version in versions:
        version.work_id = work.id

    notes: list[str] = []
    providers = sorted({c.provider for c in cluster.members})
    notes.append(f"candidates from: {', '.join(providers)}")
    if len(cluster.members) > 1:
        notes.append(f"merged {len(cluster.members)} candidates into {len(versions)} version(s)")
    if ambiguous:
        notes.append(
            "SOURCE_IDENTITY_AMBIGUOUS: title matches another work but author lists disagree; "
            "kept separate deliberately"
        )

    return WorkResolution(
        work=work,
        versions=versions,
        canonical_version=canonical,
        ambiguous=ambiguous,
        notes=notes,
        candidate_to_version=candidate_to_version,
    )
