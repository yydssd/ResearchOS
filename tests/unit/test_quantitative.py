"""Deterministic quantitative evidence extraction (plan §15).

Numbers only become structured when a metric word and a value appear together;
guessing is worse than returning nothing, because these rows later gate
cross-paper comparisons.
"""

from __future__ import annotations

from research_os.documents.chunks import chunk_pages
from research_os.documents.loader import load_markdown
from research_os.research.evidence_extractor import HeuristicEvidenceExtractor
from research_os.research.quantitative import HeuristicQuantitativeExtractor

EXTRACTOR = HeuristicQuantitativeExtractor()


def test_extracts_metric_value_and_comparator():
    facts = EXTRACTOR.extract_from_text(
        "On SIDD, the method achieves 39.18 dB PSNR compared with 39.01 dB for the baseline.",
        evidence_id="e1",
    )

    assert len(facts) == 1
    fact = facts[0]
    assert fact.metric == "PSNR"
    assert fact.value == 39.18
    assert fact.comparator_value == 39.01
    assert fact.dataset == "SIDD"
    assert fact.protocol == "dB"


def test_extracts_one_fact_per_metric_in_the_same_sentence():
    facts = EXTRACTOR.extract_from_text(
        "On the Rain100H benchmark, our method improves the baseline PSNR by 0.42 dB "
        "and SSIM by 0.013.",
        evidence_id="e2",
    )

    metrics = {f.metric for f in facts}
    assert {"PSNR", "SSIM"} <= metrics
    psnr = next(f for f in facts if f.metric == "PSNR")
    assert psnr.value == 0.42
    assert psnr.dataset == "Rain100H"
    assert psnr.protocol == "dB"
    # SSIM is unitless here even though the sentence also mentions dB.
    ssim = next(f for f in facts if f.metric == "SSIM")
    assert ssim.protocol is None
    assert [f.seq for f in facts] == list(range(len(facts)))


def test_extracts_percent_protocol():
    facts = EXTRACTOR.extract_from_text(
        "The method improves FID by 12.5% on the COCO dataset.", evidence_id="e3"
    )
    assert facts[0].metric == "FID"
    assert facts[0].value == 12.5
    assert facts[0].protocol == "percent"


def test_ignores_text_without_metric_or_value():
    assert EXTRACTOR.extract_from_text("We propose a gated attention block.", evidence_id="e4") == []
    assert EXTRACTOR.extract_from_text("PSNR is important for restoration.", evidence_id="e5") == []


def test_extract_from_evidence_links_back_to_evidence_id(tmp_path):
    fixture = tmp_path / "paper.md"
    fixture.write_text(
        "# Results\n\nOn SIDD our method achieves 39.18 dB PSNR compared with 39.01 dB for the baseline model.",
        encoding="utf-8",
    )
    chunks = chunk_pages(load_markdown(fixture), source_version_id="sv_q")
    evidence = HeuristicEvidenceExtractor().extract(chunks)

    facts = EXTRACTOR.extract(evidence)

    assert facts
    assert all(f.evidence_id == evidence[0].id for f in facts)
