"""Source verification and tier assignment (plan §8, §14).

`SourceTier` is discovery metadata, not truth: the plan is explicit that a
source's authority depends on the claim being evaluated. Tiers are therefore
used only to pick a canonical version and to describe a version, never to
promote or demote a claim.
"""

from __future__ import annotations

from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import SourceVersion


def assign_tier(
    source_type: SourceType,
    venue: str | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None,
    url: str | None = None,
) -> SourceTier:
    """Classify how authoritative a version looks, for canonical selection only.

    A DOI *with* a venue is treated as an official publication; a DOI alone is
    not, because bare DOIs also minted for datasets and preprints would
    otherwise be over-graded.
    """
    if doi and venue:
        return SourceTier.OFFICIAL_PUBLICATION
    if arxiv_id:
        return SourceTier.PREPRINT
    if source_type == SourceType.REPOSITORY:
        return SourceTier.REPOSITORY
    if source_type == SourceType.WEB:
        return SourceTier.WEB
    return SourceTier.UNKNOWN


def verify_version(sv: SourceVersion, ambiguous: bool = False) -> tuple[bool, list[str]]:
    """Decide whether a version is verifiable, and record why not.

    Verification means "we can point at an identifiable work", not "the content
    is correct". Requirements: a resolvable identifier, a title, and authors.
    """
    failures: list[str] = []
    if not sv.doi and not sv.arxiv_id:
        failures.append("no resolvable identifier")
    if not sv.title.strip():
        failures.append("no title")
    if not sv.authors:
        failures.append("no authors")
    if ambiguous:
        failures.append("identity ambiguous (title match with conflicting authors)")

    notes = list(failures)
    # Informational notes: these describe the version but do not block verification.
    if sv.source_tier == SourceTier.PREPRINT:
        notes.append("preprint: not peer-reviewed")
    return (not failures, notes)
