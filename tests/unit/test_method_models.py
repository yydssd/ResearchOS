"""The three method models (design §4.1).

`missing_layers` is the point of the whole design: it turns "this paper has no
L3" into a stored fact, because an empty list and an absent layer used to look
identical in the database.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_os.domain.models import MethodPoint, MethodProfile, MethodSetup


def test_setup_defaults_to_everything_unknown():
    setup = MethodSetup()
    assert setup.scale is None
    assert setup.protocol is None
    assert setup.hyperparameters == []
    assert setup.repository is None


def test_profile_carries_the_name_quote_and_chunk_together():
    profile = MethodProfile(
        source_version_id="sv_1",
        name="LangProp",
        name_quote="We introduce LangProp, a framework for policy learning.",
        name_chunk_id="chunk_1",
        components=["attention", "gating mechanism"],
        setup=MethodSetup(scale="8xa100", protocol="zero-shot"),
        missing_layers=["L3"],
    )
    assert profile.name == "LangProp"
    assert profile.name_chunk_id == "chunk_1"
    assert profile.missing_layers == ["L3"]
    assert profile.points == []


def test_a_point_is_structured_not_prose():
    """`statement` is a bounded claim and `quote` is the verbatim support: the
    design forbids storing free prose with no source location."""
    point = MethodPoint(
        aspect="mechanism",
        statement="Degradation maps are fused by a gated attention block.",
        quote="Our method estimates per-pixel degradation maps from the input.",
        chunk_id="chunk_1",
        section="Method",
    )
    assert point.aspect == "mechanism"
    with pytest.raises(ValidationError):
        MethodPoint(aspect="vibes", statement="x", quote="y", chunk_id="c")
    with pytest.raises(ValidationError):
        MethodPoint(aspect="goal", statement="x" * 201, quote="y", chunk_id="c")


def test_a_point_keeps_the_link_to_its_source():
    """A point is long-lived data: joining back to the source version at render
    time loses the link as soon as that version is pruned, so the link is stored
    with the point. Absent means absent - never a made-up URL."""
    point = MethodPoint(
        aspect="mechanism", statement="s", quote="q", chunk_id="chunk_1",
        source_url="https://arxiv.org/abs/2401.00001",
    )
    assert point.source_url == "https://arxiv.org/abs/2401.00001"
    assert MethodPoint(aspect="goal", statement="s", quote="q", chunk_id="c").source_url is None
