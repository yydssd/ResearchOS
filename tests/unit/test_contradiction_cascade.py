"""The cascade classifies why two claims are not the same claim (P5 spec §5)."""

from __future__ import annotations

import pytest

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim
from research_os.research.contradiction import assess_pair


def _claim(
    subject="restormer",
    dataset="sidd",
    metric="psnr",
    direction="UP",
    conditions="",
    bucket="psnr=39.18",
    text="x",
    tiers: dict[str, str] | None = None,
) -> Claim:
    key = "|".join([subject, "image restoration", dataset, metric, direction, conditions, bucket])
    flags = [f"condition_tier={kind}:{tier}" for kind, tier in sorted((tiers or {}).items())]
    return Claim(text=text, status=ClaimStatus.SUPPORTED, identity_key=key, conditions=flags)


def _relationship(a: Claim, b: Claim):
    result = assess_pair(a, b)
    return result.relationship if result else None


def test_missing_dataset_is_skipped_not_judged():
    assert assess_pair(_claim(dataset=""), _claim(dataset="")) is None


def test_missing_metric_is_skipped_not_judged():
    assert assess_pair(_claim(metric=""), _claim(metric="")) is None


def test_different_datasets_with_opposite_directions_are_a_scope_difference():
    """The plan's own example: same component, different benchmark, different
    conclusion. It must never become TRUE_CONTRADICTION."""
    a = _claim(dataset="rain100h", direction="UP", conditions="backbone=transformer")
    b = _claim(dataset="sidd", direction="LEVEL", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.SCOPE_DIFFERENCE


def test_different_datasets_with_same_direction_are_complementary():
    a = _claim(dataset="rain100h", direction="UP", conditions="backbone=transformer")
    b = _claim(dataset="sidd", direction="UP", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.COMPLEMENTARY


def test_different_conditions_are_a_scope_difference():
    a = _claim(direction="UP", conditions="backbone=transformer")
    b = _claim(direction="LEVEL", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.SCOPE_DIFFERENCE


def test_metric_without_overlap_is_experimental_incompatibility():
    a = _claim(metric="psnr", conditions="backbone=cnn")
    b = _claim(metric="lpips", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.EXPERIMENTAL_INCOMPATIBILITY


def test_different_conditions_with_the_same_direction_are_complementary():
    """Row 3 has two arms: opposite directions give SCOPE_DIFFERENCE (covered),
    same direction gives COMPLEMENTARY (not covered). Without this the
    same-direction arm could return anything."""
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "sentence"})
    b = _claim(
        direction="UP", conditions="backbone=cnn", tiers={"backbone": "sentence"},
        bucket="psnr=38.5",
    )

    assert _relationship(a, b) == ContradictionType.COMPLEMENTARY


def test_missing_conditions_means_insufficient_evidence_not_a_contradiction():
    """Empty conditions on both sides only prove the extractor found nothing."""
    a = _claim(direction="UP", conditions="")
    b = _claim(direction="LEVEL", conditions="")

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.INSUFFICIENT_EVIDENCE
    assert result.confidence_label == ConfidenceLabel.LOW


def test_same_explicit_scope_and_opposite_direction_is_a_true_contradiction():
    # HD-014: TRUE_CONTRADICTION needs provenance that proves a shared setup.
    # "Explicit conditions" alone is not enough - both sides must be `sentence`.
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "sentence"})
    b = _claim(direction="LEVEL", conditions="backbone=transformer", tiers={"backbone": "sentence"})

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.TRUE_CONTRADICTION
    assert result.confidence_label == ConfidenceLabel.DISPUTED


def test_reported_value_is_not_a_direction_so_it_cannot_contradict():
    a = _claim(direction="UP", conditions="backbone=cnn")
    b = _claim(direction="", conditions="backbone=cnn")

    assert assess_pair(a, b).relationship == ContradictionType.INSUFFICIENT_EVIDENCE


def test_same_direction_different_values_is_experimental_incompatibility():
    a = _claim(direction="UP", conditions="backbone=cnn", bucket="psnr=39.18")
    b = _claim(direction="UP", conditions="backbone=cnn", bucket="psnr=38.50")

    assert _relationship(a, b) == ContradictionType.EXPERIMENTAL_INCOMPATIBILITY


def test_same_direction_without_values_is_insufficient_evidence():
    a = _claim(direction="UP", conditions="backbone=cnn", bucket="")
    b = _claim(direction="UP", conditions="backbone=cnn", bucket="psnr=39.18")

    assert _relationship(a, b) == ContradictionType.INSUFFICIENT_EVIDENCE


def test_equal_but_inherited_conditions_do_not_prove_a_contradiction():
    """D13: "the section said so once" is an assumption, not evidence. Two claims
    whose setup was inherited from the first mention may well disagree, but the
    judgement cannot assert that their scopes are the same."""
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "section-first-mention"})
    b = _claim(direction="LEVEL", conditions="backbone=transformer", tiers={"backbone": "section-first-mention"})

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.INSUFFICIENT_EVIDENCE
    assert result.confidence_label == ConfidenceLabel.LOW
    assert "backbone" in result.explanation and "not confirmed" in result.explanation


def test_heading_level_conditions_are_evidence():
    """A heading that names the setup governs the whole section, so it is
    confirmed rather than assumed."""
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "heading"})
    b = _claim(direction="LEVEL", conditions="backbone=transformer", tiers={"backbone": "heading"})

    assert _relationship(a, b) == ContradictionType.TRUE_CONTRADICTION


def test_inherited_conditions_can_still_disprove_a_shared_setup():
    """The asymmetry is the point: inherited conditions that differ are real
    evidence that the two claims came from different experiments."""
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "section-first-mention"})
    b = _claim(direction="LEVEL", conditions="backbone=cnn", tiers={"backbone": "section-first-mention"})

    assert _relationship(a, b) == ContradictionType.SCOPE_DIFFERENCE


@pytest.mark.parametrize(
    "a_dir,b_dir",
    [("UP", "LEVEL"), ("UP", "DOWN"), ("DOWN", "LEVEL")],
)
def test_every_opposite_pair_combination(a_dir, b_dir):
    # HD-014: every opposite pair is only a contradiction when both setups are
    # stated in the sentences; without the tier the cascade must answer LOW.
    a = _claim(direction=a_dir, conditions="backbone=cnn", bucket="psnr=39.18", tiers={"backbone": "sentence"})
    b = _claim(direction=b_dir, conditions="backbone=cnn", bucket="psnr=39.18", tiers={"backbone": "sentence"})

    assert _relationship(a, b) == ContradictionType.TRUE_CONTRADICTION


def test_explanation_names_the_dimension_and_the_values():
    a = _claim(dataset="rain100h", direction="UP", conditions="backbone=transformer")
    b = _claim(dataset="sidd", direction="LEVEL", conditions="backbone=cnn")

    result = assess_pair(a, b)

    assert "dataset differs" in result.explanation
    assert "rain100h" in result.explanation and "sidd" in result.explanation


def test_missing_provenance_cannot_prove_a_contradiction():
    """D13 is a whitelist, not a blacklist. A claim with no conditions_from tag
    says nothing about where its setup came from, so equal conditions cannot be
    promoted to "same experiment" - that is silence used as evidence (HD-014)."""
    a = _claim(direction="UP", conditions="backbone=cnn")
    b = _claim(direction="LEVEL", conditions="backbone=cnn")

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.INSUFFICIENT_EVIDENCE
    assert result.confidence_label == ConfidenceLabel.LOW
    assert "not confirmed" in result.explanation


def test_unknown_provenance_tier_cannot_prove_a_contradiction():
    """Legacy rows and future tier names are untrusted for the same reason: only
    `sentence` and `heading` were ever defined as evidence of a shared setup."""
    a = _claim(direction="UP", conditions="backbone=cnn", tiers={"backbone": "legacy-unknown"})
    b = _claim(direction="LEVEL", conditions="backbone=cnn", tiers={"backbone": "legacy-unknown"})

    assert _relationship(a, b) == ContradictionType.INSUFFICIENT_EVIDENCE


def test_sentence_level_conditions_are_evidence():
    """The strongest tier: both sentences state their own setup. This is the
    tier the fixtures must exercise before claiming TRUE_CONTRADICTION is tested."""
    a = _claim(direction="UP", conditions="backbone=cnn", tiers={"backbone": "sentence"})
    b = _claim(direction="LEVEL", conditions="backbone=cnn", tiers={"backbone": "sentence"})

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.TRUE_CONTRADICTION
    assert result.confidence_label == ConfidenceLabel.DISPUTED


def test_one_unconfirmed_kind_blocks_a_true_contradiction():
    """HD-014, per kind: a shared setup needs *every* shared kind confirmed. The
    inherited backbone makes "same setup" unproven even though the protocol was
    stated in both sentences."""
    a = _claim(direction="UP", conditions="backbone=transformer;protocol=5-shot",
               tiers={"backbone": "section-first-mention", "protocol": "sentence"})
    b = _claim(direction="DOWN", conditions="backbone=transformer;protocol=5-shot",
               tiers={"backbone": "sentence", "protocol": "sentence"})

    result = assess_pair(a, b)

    assert result.relationship is ContradictionType.INSUFFICIENT_EVIDENCE
    assert "backbone" in result.explanation
    assert "protocol" not in result.explanation  # 只点名未确认的 kind，正是「按 kind」的锁


def test_every_shared_kind_confirmed_still_reaches_a_true_contradiction():
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "sentence"})
    b = _claim(direction="DOWN", conditions="backbone=transformer", tiers={"backbone": "heading"})

    result = assess_pair(a, b)

    assert result.relationship is ContradictionType.TRUE_CONTRADICTION
