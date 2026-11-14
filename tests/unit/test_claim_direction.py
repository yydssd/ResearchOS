"""Direction expresses the claim's conclusion about quality, not metric movement."""

from __future__ import annotations

import pytest

from research_os.research.claims import extract_identity
from research_os.research.scope import BlockScope


def _direction(text: str) -> str | None:
    return extract_identity(
        text, source_version_id="sv_1", scope=BlockScope("image restoration"), quantitative=[]
    ).direction


@pytest.mark.parametrize(
    "text",
    [
        "Our method improves PSNR by 0.42 dB on Rain100H.",
        "The model outperforms every baseline on SIDD.",
        "It reduces the error by a wide margin on GoPro.",
        "The design increases PSNR on Urban100.",
    ],
)
def test_improvement_is_up(text):
    assert _direction(text) == "UP"


@pytest.mark.parametrize(
    "text",
    [
        "The method degrades performance on real-world data.",
        "It drops 0.4 dB under heavy rain.",
        "Removing the module reduces PSNR on SIDD.",
        "The variant increases the error on Rain100L.",
    ],
)
def test_degradation_is_down(text):
    assert _direction(text) == "DOWN"


@pytest.mark.parametrize(
    "text",
    [
        "Restormer achieves 39.18 dB on SIDD.",
        "The model reaches 0.955 SSIM on GoPro.",
        "We report 32.5 dB averaged over the five datasets.",
        "It obtains the best score on Urban100.",
    ],
)
def test_reported_value_has_no_direction(text):
    """A measurement is not a claim of change; 'achieves' must not become LEVEL."""
    assert _direction(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Spatial conditioning shows no gain on SIDD with a CNN backbone.",
        "The module yields no significant difference on Rain100H.",
        "The variant fails to improve PSNR on GoPro.",
        "Performance is on par with the baseline on SIDD.",
    ],
)
def test_explicit_no_gain_is_level(text):
    assert _direction(text) == "LEVEL"


def test_negation_beats_the_word_it_negates():
    """`fails to improve` contains `improve`; LEVEL must win over UP."""
    assert _direction("The module fails to improve PSNR on Rain100H.") == "LEVEL"


def test_verb_pairs_that_raise_and_lower_are_directions():
    """`raises PSNR` and `lowers PSNR` say which way quality moved without using
    any word the old list knew. Three fixtures depended on this and had hand-written
    directions the rules could not reproduce."""
    assert _direction("NAFNet raises PSNR on SIDD to 39.40 dB.") == "UP"
    assert _direction("NAFNet lowers PSNR on SIDD to 38.90 dB.") == "DOWN"


def test_explicit_no_change_is_level():
    """`leaves ... unchanged` is the clearest possible statement of no gain, yet
    it read as None because the list only knew 'no improvement' and 'on par with'."""
    assert _direction("NAFNet leaves PSNR on SIDD unchanged at 39.18 dB.") == "LEVEL"
    assert _direction("The score stays the same on SIDD.") == "LEVEL"
    assert _direction("There is no change in accuracy.") == "LEVEL"


def test_lower_as_an_adjective_is_not_a_degradation_verb():
    """`lower` used adjectivally must not be read as 'lowers'. Adding the verb must
    not turn every 'the lower layers' into a claim of degradation."""
    assert _direction("The lower layers carry high-frequency texture.") is None
