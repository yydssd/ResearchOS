"""L1: the paper's own method name (design §6.1, §10.2/§10.3).

Two acceptance rules live in these tests and nowhere else:
- the name must be a verbatim substring of the chunk it claims to come from;
- sentence-initial capitalisation alone is not naming evidence (claims.py:169),
  with one documented exception: the apposition form "X, our method" *is* the
  evidence, and X is sentence-initial by construction.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.research.methods import extract_methods


def _chunk(text: str, *, section: str, index: int = 0, svid: str = "sv_1") -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{svid}_{index}",
        source_version_id=svid,
        section=section,
        chunk_index=index,
        text=text,
    )


def _profile(chunks):
    return extract_methods(chunks).profiles[0]


def test_name_comes_from_an_explicit_naming_sentence():
    profile = _profile(
        [_chunk("We propose LangProp, a framework for policy learning.", section="Abstract")]
    )
    assert profile.name == "LangProp"
    assert profile.name_chunk_id == "chunk_sv_1_0"
    # The quote must be locatable verbatim inside the chunk it points at.
    assert profile.name_quote in "We propose LangProp, a framework for policy learning."
    assert "L1" not in profile.missing_layers


def test_the_apposition_form_survives_the_sentence_initial_filter():
    """`Voyager, our proposed method, ...` opens the sentence; the construction
    itself is the naming evidence, so the claims.py:169 filter must not eat it."""
    profile = _profile(
        [_chunk("Voyager, our proposed method, stores code in a skill library.", section="Abstract")]
    )
    assert profile.name == "Voyager"


def test_a_sentence_initial_capital_alone_is_not_a_name():
    profile = _profile(
        [_chunk("Motivated experiments show that gating helps on SIDD.", section="Abstract")]
    )
    assert profile.name is None
    assert "L1" in profile.missing_layers


def test_predicates_datasets_metrics_and_generic_nouns_are_never_names():
    for text in (
        "We introduce a Transformer backbone for restoration.",
        "We propose SIDD as the evaluation benchmark.",
        "This paper introduces PSNR as the evaluation metric.",
    ):
        profile = _profile([_chunk(text, section="Abstract")])
        assert profile.name is None, text


def test_a_fragment_of_a_longer_name_is_not_a_name():
    """Measured on the hold-out set: the single-token `X` of design §6.1 lands on
    the first word of a multi-word name, and that word is an adjective, not a
    name. All three sentences below produced a wrong name before the two
    structural rejections (`_acceptable`'s trailing-character check and
    `_candidates`' "followed by a capitalised word" check)."""
    for text in (
        "We propose Spectral-based Spatial Grouping Transformer (SSGformer) for restoration.",
        "In this work, we present Language-conditioned Large-scale restoration model (LLaRS).",
        "In this paper, we propose Multi-τ Liquid-Mamba for sequence modelling.",
    ):
        profile = _profile([_chunk(text, section="Abstract")])
        assert profile.name is None, text


def test_the_abstract_outranks_the_method_section():
    """Source tier decides, not first appearance in the file: the abstract names
    the method the paper wants to be known by."""
    profile = _profile(
        [
            _chunk("Our framework, Voyager, learns skills.", section="Method", index=1),
            _chunk("We introduce LangProp in this work.", section="Abstract", index=0),
        ]
    )
    assert profile.name == "LangProp"
    assert profile.aliases == ["Voyager"]


def test_two_names_at_the_same_tier_in_one_chunk_are_ambiguous():
    """Design §6.1: same tier and same position means the paper has not chosen a
    name; guessing here would be the multi-method mistake (§4.1)."""
    extraction = extract_methods(
        [
            _chunk(
                "We introduce CALVIN for control and we introduce SOAP for planning.",
                section="Abstract",
            )
        ]
    )
    profile = extraction.profiles[0]
    assert profile.name is None
    assert extraction.ambiguous["sv_1"] == ("CALVIN", "SOAP")
    assert "L1" in profile.missing_layers
