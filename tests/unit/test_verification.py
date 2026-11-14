"""Source tier and verification rules (plan §8, §14)."""

from __future__ import annotations

from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import SourceVersion
from research_os.sources.verification import assign_tier, verify_version


def test_assign_tier_distinguishes_published_preprint_repository_web():
    assert assign_tier(SourceType.CONFERENCE, venue="CVPR", doi="10.1109/x") == SourceTier.OFFICIAL_PUBLICATION
    assert assign_tier(SourceType.ARXIV, arxiv_id="2310.10123") == SourceTier.PREPRINT
    assert assign_tier(SourceType.REPOSITORY, url="https://github.com/x/y") == SourceTier.REPOSITORY
    assert assign_tier(SourceType.WEB, url="https://blog.example/post") == SourceTier.WEB
    assert assign_tier(SourceType.WEB) == SourceTier.WEB


def test_verify_requires_identifier_title_and_authors():
    ok = SourceVersion(work_id="w", source_type=SourceType.ARXIV, title="T", authors=["A B"], arxiv_id="2310.10123")
    assert verify_version(ok, ambiguous=False)[0] is True


def test_verify_reports_each_missing_prerequisite():
    anonymous = SourceVersion(work_id="w", source_type=SourceType.WEB, title="Some blog post")
    verified, notes = verify_version(anonymous, ambiguous=False)
    assert verified is False
    assert "no resolvable identifier" in notes
    assert "no authors" in notes

    no_author = SourceVersion(work_id="w", source_type=SourceType.ARXIV, title="T", arxiv_id="2310.10123")
    verified, notes = verify_version(no_author, ambiguous=False)
    assert verified is False and "no authors" in notes

    ambiguous = SourceVersion(work_id="w", source_type=SourceType.ARXIV, title="T", authors=["A B"], arxiv_id="2310.1")
    verified, notes = verify_version(ambiguous, ambiguous=True)
    assert verified is False
    assert any("identity ambiguous" in n for n in notes)


def test_preprint_note_is_informational_not_a_failure():
    sv = SourceVersion(
        work_id="w",
        source_type=SourceType.ARXIV,
        title="T",
        authors=["A B"],
        arxiv_id="2310.10123",
        source_tier=SourceTier.PREPRINT,
    )
    verified, notes = verify_version(sv, ambiguous=False)
    assert verified is True
    assert "preprint: not peer-reviewed" in notes
