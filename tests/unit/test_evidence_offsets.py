"""Evidence offsets and provenance gating (plan §2.2, §15).

An offset is only useful if `source[start:end]` is exactly the quoted text, so
these tests assert equality against the original chunk rather than just
non-None values.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk, Evidence
from research_os.research.evidence_extractor import (
    HeuristicEvidenceExtractor,
    has_location,
    is_complete_sentence,
    sentence_spans,
)

TEXT = (
    "On the Rain100H benchmark, our method improves PSNR by 0.42 dB and SSIM by 0.013. "
    "On SIDD the method achieves 39.18 dB compared with 39.01 dB for the baseline."
)

# Long enough to pass the length gate, but it is a run of navigation labels: no
# sentence is ever terminated, so nothing here can carry a claim.
CHROME = (
    "Bibliographic Explorer Toggle Bibliographic Explorer (What is the Explorer?) "
    "Connected Papers Toggle Connected Papers (What is Connected Papers?) "
    "Links to Code Toggle CatalyzeX Code Finder for Papers"
)


def test_sentence_spans_preserve_offsets_and_decimals():
    spans = sentence_spans(TEXT)

    assert len(spans) == 2
    for start, end, sentence in spans:
        assert TEXT[start:end] == sentence
    assert "39.18 dB" in spans[1][2]


def test_sentence_spans_handle_newlines_and_multiple_spaces():
    text = "First finding is long enough to keep.\n\nSecond finding is also long enough to keep."
    spans = sentence_spans(text)

    assert len(spans) == 2
    assert all(text[s:e] == sentence for s, e, sentence in spans)


def test_evidence_offsets_point_at_original_text():
    chunk = DocumentChunk(
        source_version_id="sv_1",
        chunk_index=0,
        text=TEXT,
        section="Results",
        page_index=0,
        page_label="md",
    )

    evidence = HeuristicEvidenceExtractor().extract([chunk])

    assert evidence
    for ev in evidence:
        assert ev.char_start is not None and ev.char_end is not None
        assert chunk.text[ev.char_start : ev.char_end] == ev.text
        assert ev.content_hash
        assert ev.chunk_id == chunk.id


def test_has_location_flags_evidence_without_provenance():
    located = Evidence(source_version_id="sv", text="x", chunk_id="c1", page_label="p.1")
    section_only = Evidence(source_version_id="sv", text="x", section="Results")
    bare = Evidence(source_version_id="sv", text="x")

    assert has_location(located) is True
    assert has_location(section_only) is True
    assert has_location(bare) is False


def test_is_complete_sentence_requires_terminal_punctuation():
    assert is_complete_sentence("The method reaches 39.18 dB PSNR on SIDD.") is True
    assert is_complete_sentence("Does the gating mechanism help restoration?") is True
    assert is_complete_sentence("It improves PSNR by 0.42 dB!") is True
    # closing quotes/brackets after the terminator are common in prose
    assert is_complete_sentence('They write that "the model is robust."') is True
    assert is_complete_sentence("See Section 4 for the ablation study.)") is True
    # labels and truncated fragments are not sentences
    assert is_complete_sentence("Bibliographic Explorer Toggle Connected Papers") is False
    assert is_complete_sentence("Demos") is False
    assert is_complete_sentence("Access Paper:") is False


def test_label_fragments_never_become_evidence():
    """Site chrome is long but unterminated, so it must not become Evidence.

    Regression guard: an arXiv abstract page produced 19 evidence objects, 10 of
    which were navigation labels ("Recommenders and Search Tools", "Demos", ...).
    Those would flow into claim synthesis and contradiction detection as if they
    were findings.
    """
    chunk = DocumentChunk(
        source_version_id="sv_1",
        chunk_index=0,
        text=CHROME,
        section="Bookmark",
        page_label="html",
    )

    assert len(CHROME) >= 60, "the guard must be the punctuation rule, not the length gate"
    assert HeuristicEvidenceExtractor().extract([chunk]) == []


def test_prose_ending_in_question_or_quote_is_kept():
    text = (
        "Is the degradation model practical for real-world blind super-resolution applications? "
        'The authors conclude that "the degradation model is practical and effective in real cases."'
    )
    chunk = DocumentChunk(source_version_id="sv_1", chunk_index=0, text=text, page_label="html")

    evidence = HeuristicEvidenceExtractor().extract([chunk])

    assert len(evidence) == 2
    for ev in evidence:
        assert chunk.text[ev.char_start : ev.char_end] == ev.text
