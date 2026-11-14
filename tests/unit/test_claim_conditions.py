"""Conditions describe the experimental setup a claim's number came from."""

from __future__ import annotations

from research_os.research.claims import extract_identity
from research_os.research.conditions import extract_conditions
from research_os.research.scope import BlockScope


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


def test_conditions_carry_their_provenance():
    """Sentence-level conditions are stated by the sentence itself. That is the
    strongest tier, and the only one that can later support a contradiction:
    an inherited condition says "someone in this section said so", not "this
    claim used it"."""
    identity = extract_identity(
        "We train a Transformer backbone and improve PSNR on SIDD.",
        source_version_id="sv_1",
        scope=None,
        quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer",)
    assert identity.conditions_from == "sentence"


def test_inherited_conditions_are_tagged_with_where_they_came_from():
    scope = BlockScope(
        task="denoising",
        datasets=frozenset({"SIDD"}),
        inherited_from={"conditions": "section-first-mention"},
        conditions=("backbone=transformer",),
    )

    identity = extract_identity(
        "The gain reaches 0.42 dB on SIDD.",
        source_version_id="sv_1",
        scope=scope,
        quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer",)
    assert identity.conditions_from == "section-first-mention"


def test_no_conditions_means_no_provenance():
    identity = extract_identity(
        "Our method improves PSNR by 0.42 dB on SIDD.",
        source_version_id="sv_1",
        scope=None,
        quantitative=[],
    )

    assert identity.conditions == ()
    assert identity.conditions_from is None
