"""L2 components and L4 setup (design §6.2/§6.3).

Both layers are additive evidence that a paper describes a *system*: components
say what it is made of, setup says how to reproduce it. Neither may be inferred
from wording similarity - "our method works well" is not a component.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.research.methods import extract_methods


def _chunk(text: str, *, section: str = "Method", index: int = 0, svid: str = "sv_1") -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{svid}_{index}",
        source_version_id=svid,
        section=section,
        chunk_index=index,
        text=text,
    )


def _profile(*chunks: DocumentChunk):
    return extract_methods(list(chunks)).profiles[0]


def test_structural_noun_phrases_become_components():
    profile = _profile(
        _chunk(
            "We propose a lightweight conditioning module that injects degradation "
            "location maps into the restoration network. Our method fuses them with "
            "the feature stream using a gated attention block."
        )
    )
    assert "lightweight conditioning module" in profile.components
    assert "restoration network" in profile.components
    assert "gated attention block" in profile.components
    assert "L2" not in profile.missing_layers


def test_vocabulary_words_and_phrases_count_too():
    profile = _profile(
        _chunk("The planner queries a retrieval buffer and trains a reward model offline.")
    )
    assert "planner" in profile.components
    assert "retrieval" in profile.components
    assert "buffer" in profile.components
    assert "reward model" in profile.components


def test_a_bare_tail_word_is_not_a_component():
    """`module` on its own says nothing about the system; only a qualified noun
    phrase does. Otherwise every paper that says "this module" scores L2."""
    profile = _profile(_chunk("This module is described in the appendix."))
    assert profile.components == []
    assert "L2" in profile.missing_layers


def test_setup_reads_protocol_scale_and_repository():
    profile = _profile(
        _chunk(
            "We train on 8×A100 GPUs and evaluate zero-shot. Code is available at "
            "https://github.com/foo/langprop. Training uses learning rate 3e-4 for "
            "100 epochs with batch size 32 on AdamW."
        )
    )
    assert profile.setup.scale == "8xa100"
    assert profile.setup.protocol == "zero-shot"
    assert profile.setup.repository == "https://github.com/foo/langprop"
    assert "lr=3e-4" in profile.setup.hyperparameters
    assert "epochs=100" in profile.setup.hyperparameters
    assert "batch=32" in profile.setup.hyperparameters
    assert "optimizer=adamw" in profile.setup.hyperparameters
    assert "L4" not in profile.missing_layers


def test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale():
    """design §6.3: "top-1" and "success rate" are metrics, and a dB value is a
    unit. Reading either as a protocol/scale would claim two claims share a setup
    because they share a metric."""
    profile = _profile(_chunk("Our method reports 39.18 dB PSNR, a 0.42 dB gain."))
    assert profile.setup.protocol is None
    assert profile.setup.scale is None
    assert "L4" in profile.missing_layers


def test_missing_layers_always_reports_l3_until_s3_exists():
    """L3 has no producer until S3, so it is missing even when everything else
    landed: "the paper describes no mechanism" and "nobody looked" stay apart."""
    bare = _profile(_chunk("We introduce LangProp and evaluate on CALVIN.", section="Abstract"))
    assert bare.name == "LangProp"
    assert "L3" in bare.missing_layers

    complete = extract_methods(
        [
            _chunk(
                "We introduce LangProp, a framework. Our method uses a gating "
                "mechanism and is trained with learning rate 3e-4.",
                section="Abstract",
            )
        ]
    ).profiles[0]
    # L1 (name), L2 (gating mechanism) and L4 (lr=3e-4) all landed here, so the
    # list is exactly the one layer no code can fill yet.
    assert complete.missing_layers == ["L3"]
