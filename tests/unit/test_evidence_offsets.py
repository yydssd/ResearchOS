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
    sentence_spans,
)

TEXT = (
    "On the Rain100H benchmark, our method improves PSNR by 0.42 dB and SSIM by 0.013. "
    "On SIDD the method achieves 39.18 dB compared with 39.01 dB for the baseline."
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
