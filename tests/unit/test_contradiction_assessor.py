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


def test_one_bad_pair_does_not_stop_the_others(monkeypatch):
    """A single malformed pair must cost one judgement, not the whole run.

    The counter is the only evidence that a pair was dropped for an error rather
    than for a missing scope, so it has to be distinct from the skip counters.
    """
    import research_os.research.contradiction as module

    real = module.assess_pair
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("boom")
        return real(a, b)

    monkeypatch.setattr(module, "assess_pair", flaky)

    assessments, stats = module.HeuristicContradictionAssessor().assess(
        [_claim("UP"), _claim("LEVEL"), _claim("UP"), _claim("LEVEL")]
    )

    assert stats.failed_pairs == 1
    # Four claims in one scope group make six pairs: four with opposite
    # directions and two with the same value. Whichever pair the stub hits, the
    # remaining five are still judged, so the batch loses one judgement instead
    # of the whole run - and the loss is not folded into a skip counter.
    assert stats.evaluated == 6
    assert len(assessments) + stats.skipped_same_value + stats.failed_pairs == stats.evaluated
    assert stats.skipped_missing_dataset == 0
    assert stats.skipped_missing_metric == 0
    assert stats.skipped_self_prefilter == 0
    assert stats.skipped_cap == 0
    assert set(stats.emitted_by_type) == {"TRUE_CONTRADICTION"}
    # Without logging the event is the only channel, so the error type and one
    # concrete pair have to survive the catch.
    assert stats.failed_by_error == {"ValueError": 1}
    assert stats.first_failure is not None
    assert stats.first_failure.startswith("ValueError: boom")
    assert stats.judged == 5


def test_same_value_pairs_are_counted_not_swallowed():
    """A same-direction same-value pair reaching the cascade means P4 should have
    merged it. The count is the tripwire; the supervisor turns it into an event."""
    def claim():
        return Claim(
            text="x",
            status=ClaimStatus.SUPPORTED,
            identity_key="m|image restoration|sidd|psnr|UP|backbone=cnn|psnr=39.18",
            conditions=["conditions_from=sentence"],
        )

    assessments, stats = HeuristicContradictionAssessor().assess([claim(), claim()])

    assert assessments == []
    assert stats.skipped_same_value == 1
