"""Block-level scope inheritance (P4 spec §4).

The 10-document probe showed identity taken from one sentence reaches a complete
key 0 times in 215 claims: papers name the task in the subsection heading and the
dataset in the first sentence of that subsection. These tests pin that behaviour.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.research.scope import BlockScope, build_section_scopes


def _chunk(index: int, section: str, text: str, sv: str = "sv_1") -> DocumentChunk:
    return DocumentChunk(
        source_version_id=sv, chunk_index=index, text=text, section=section, page_label="html"
    )


def test_task_is_inherited_from_the_section_heading():
    chunks = [_chunk(0, "Classical image SR.", "The maximum PSNR gain reaches 0.26 dB on Manga109.")]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[0].id].task == "super-resolution"
    assert scopes[chunks[0].id].inherited_from["task"] == "heading"


def test_dataset_is_inherited_from_the_sections_first_naming_sentence():
    chunks = [
        _chunk(0, "Classical image SR.", "We evaluate on Set5 and Urban100 with scale factor 4."),
        _chunk(1, "Classical image SR.", "The method improves the score further on this dataset."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].datasets == frozenset({"Set5", "Urban100"})
    assert scopes[chunks[1].id].inherited_from["datasets"] == "section-first-mention"


def test_inheritance_does_not_leak_across_sections():
    chunks = [
        _chunk(0, "Classical image SR.", "We evaluate on Set5."),
        _chunk(1, "RGB Image Denoising.", "Table 2 compares every method on this task."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].task == "denoising"
    assert scopes[chunks[1].id].datasets == frozenset()


def test_inheritance_does_not_leak_across_sources():
    chunks = [
        _chunk(0, "Results", "We evaluate on Set5.", sv="sv_a"),
        _chunk(1, "Results", "The numbers are summarised in the appendix.", sv="sv_b"),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].datasets == frozenset()


def test_heading_that_names_a_dataset_wins_over_body():
    chunks = [_chunk(0, "4.2 SIDD denoising", "The method reaches the best score here.")]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[0].id].datasets == frozenset({"SIDD"})
    assert scopes[chunks[0].id].inherited_from["datasets"] == "heading"


def test_empty_section_yields_an_empty_scope():
    chunks = [_chunk(0, "", "Some prose without any task or dataset name at all.")]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[0].id] == BlockScope(task=None, datasets=frozenset(), inherited_from={})


def test_section_without_a_task_falls_back_to_the_document_task():
    """On the 20-paper hold-out, 1082 of 1242 claim sentences got no task: the
    task lives in the abstract ("all-in-one image restoration"), while headings
    say "8 Further Ablation Study" or "1 Introduction". Falling back to the
    document's own task keeps those claims mergeable without inventing scope."""
    chunks = [
        _chunk(0, "Abstract", "We present a unified model for image restoration."),
        _chunk(1, "8 Further Ablation Study", "Removing the prompt drops the score by 0.3 dB."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].task == "image restoration"
    assert scopes[chunks[1].id].inherited_from["task"] == "document"


def test_heading_task_beats_the_document_task():
    chunks = [
        _chunk(0, "Abstract", "We present a unified model for image restoration."),
        _chunk(1, "RGB Image Denoising.", "The gain over the baseline is 0.2 dB."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].task == "denoising"
    assert scopes[chunks[1].id].inherited_from["task"] == "heading"


def test_document_task_is_taken_from_the_abstract_first():
    """A later section may study a second task; the paper's own task is the one
    the abstract declares."""
    chunks = [
        _chunk(0, "Abstract", "We present a unified model for image restoration."),
        _chunk(1, "Related work", "Early work studied super-resolution in isolation."),
        _chunk(2, "5 Conclusion", "The method is robust across degradations."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[2].id].task == "image restoration"


def test_document_task_does_not_cross_sources():
    chunks = [
        _chunk(0, "Abstract", "We present a unified model for image restoration.", sv="sv_a"),
        _chunk(1, "5 Conclusion", "The method is robust across degradations.", sv="sv_b"),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].task is None


def test_conditions_are_inherited_from_the_section():
    """Conditions live in the experiment section, not in each sentence: single
    sentence coverage is 2.6%, section inheritance lifts it to 64.3%."""
    chunks = [
        _chunk(0, "4.1 SIDD denoising", "We train a Transformer backbone for 300 epochs."),
        _chunk(1, "4.1 SIDD denoising", "The gain over the baseline reaches 0.42 dB."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].conditions == {"backbone": "transformer"}
    assert scopes[chunks[1].id].condition_tiers == {"backbone": "section-first-mention"}


def test_first_condition_mention_applies_to_the_rest_of_the_section():
    """Inheritance is deliberately blind to contrast: a sentence introducing an
    ablation ("with a CNN backbone") makes the CNN setup the section default for
    the sentences that follow, even where the paper means its own model. The
    provenance tag is what keeps this honest downstream - P5 downgrades a
    verdict that rests on inherited conditions instead of trusting it.
    """
    chunks = [
        _chunk(0, "4.2 Ablation", "With a CNN backbone the gain disappears."),
        _chunk(1, "4.2 Ablation", "The full model reaches 32.8 dB."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].conditions == {"backbone": "cnn"}


def test_inheritance_fills_only_the_missing_kinds():
    """A heading that names the backbone must not erase a `training=` the section
    established two chunks later: S4 inherits per kind (design §8.2)."""
    from research_os.domain.models import DocumentChunk
    from research_os.research.scope import build_section_scopes

    chunks = [
        DocumentChunk(id="c0", source_version_id="sv", section="4 Method", page_index=0,
                      chunk_index=0, text="We train a Transformer backbone."),
        DocumentChunk(id="c1", source_version_id="sv", section="4 Method", page_index=0,
                      chunk_index=1, text="All models are trained from scratch."),
    ]
    scopes = build_section_scopes(chunks)

    assert scopes["c1"].conditions == {"backbone": "transformer", "training": "from-scratch"}
    assert scopes["c1"].condition_tiers == {
        "backbone": "section-first-mention",
        "training": "section-first-mention",
    }


def test_a_heading_condition_keeps_its_own_tier_when_a_sentence_adds_another_kind():
    from research_os.domain.models import DocumentChunk
    from research_os.research.scope import build_section_scopes

    chunks = [
        DocumentChunk(id="c0", source_version_id="sv", section="4.1 Transformer backbone",
                      page_index=0, chunk_index=0, text="Results follow."),
        DocumentChunk(id="c1", source_version_id="sv", section="4.1 Transformer backbone",
                      page_index=0, chunk_index=1, text="We evaluate zero-shot."),
    ]
    scopes = build_section_scopes(chunks)

    assert scopes["c1"].conditions == {"backbone": "transformer", "protocol": "zero-shot"}
    assert scopes["c1"].condition_tiers == {
        "backbone": "heading",
        "protocol": "section-first-mention",
    }
