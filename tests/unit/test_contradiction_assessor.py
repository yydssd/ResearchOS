"""The assessor turns pairs into assessments and, just as importantly, into counts.

A report that only says "0 contradictions" cannot be told apart from a report that
compared nothing, so every pair that does not produce an assessment has to land in
exactly one bucket (P5 spec §5).
"""

from __future__ import annotations

from research_os.domain.enums import ClaimStatus
from research_os.domain.models import Claim
from research_os.research.contradiction import HeuristicContradictionAssessor


def _claim(direction: str = "UP", bucket: str = "psnr=39.18", dataset: str = "sidd") -> Claim:
    key = "|".join(["restormer", "image restoration", dataset, "psnr", direction, "backbone=cnn", bucket])
    # HD-014: a sentence-stated setup is the confirmed tier. Without this flag
    # the cascade refuses to emit TRUE_CONTRADICTION, so the counter test below
    # would be measuring INSUFFICIENT_EVIDENCE instead.
    return Claim(
        text="x", status=ClaimStatus.SUPPORTED, identity_key=key,
        conditions=["conditions_from=sentence"],
    )


def test_emitted_types_are_counted():
    a = _claim(direction="UP")
    b = _claim(direction="LEVEL")

    assessments, stats = HeuristicContradictionAssessor().assess([a, b])

    assert len(assessments) == 1
    assert stats.evaluated == 1
    assert stats.emitted_by_type == {"TRUE_CONTRADICTION": 1}


def test_same_value_pairs_are_counted_as_a_p4_defect():
    """Identical scope and identical value should have merged in P4, so a pair
    reaching this point means the merge gate let something through. Counting it
    keeps the defect visible instead of silently dropping the pair."""
    assessments, stats = HeuristicContradictionAssessor().assess([_claim(), _claim()])

    assert assessments == []
    assert stats.skipped_same_value == 1


def test_pairs_missing_a_dataset_are_counted_separately():
    a = _claim(dataset="", bucket="")
    b = _claim(bucket="")

    assessments, stats = HeuristicContradictionAssessor().assess([a, b])

    assert assessments == []
    assert stats.skipped_missing_dataset == 1
    assert stats.skipped_same_value == 0
