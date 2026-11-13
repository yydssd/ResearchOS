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
