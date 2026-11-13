"""Conditions describe the experimental setup a claim's number came from."""

from __future__ import annotations

from research_os.research.conditions import extract_conditions


def test_backbone_is_extracted():
    assert extract_conditions("We train a Transformer-based model.") == ("backbone=transformer",)
    assert extract_conditions("A CNN backbone is used for comparison.") == ("backbone=cnn",)


def test_degradation_level_is_extracted():
    assert extract_conditions("At noise level 25 the gain is largest.") == ("degradation=25",)
    assert extract_conditions("Images suffer from heavy rain.") == ("degradation=heavy",)


def test_baseline_is_extracted():
    assert extract_conditions("Compared with MPRNet, the gain is 0.4 dB.") == ("baseline=mprnet",)


def test_training_protocol_is_extracted():
    assert extract_conditions("All models are trained from scratch.") == ("training=from-scratch",)


def test_multiple_kinds_are_sorted_and_deduplicated():
    text = "The Transformer model trained from scratch is compared with MPRNet."
    assert extract_conditions(text) == (
        "backbone=transformer",
        "baseline=mprnet",
        "training=from-scratch",
    )


def test_no_condition_means_empty_not_a_default():
    assert extract_conditions("Our method improves PSNR by 0.42 dB.") == ()
