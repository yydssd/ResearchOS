"""Claim merging by identity, not by wording (plan §16, P4 spec §6).

Merging is the only place where two evidence objects become one claim, so the
gate is deliberately strict: subject + dataset + direction must all be known, all
six comparable dimensions must match, and the reported value must agree. Two
papers reporting 0.42 dB and 0.51 dB on the same benchmark are *not* duplicates -
they are the disagreement P5 exists to assess, and merging them would hide it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_os.documents.chunks import chunk_pages
from research_os.documents.loader import load_markdown
from research_os.research.claim_builder import HeuristicClaimBuilder
from research_os.research.evidence_extractor import HeuristicEvidenceExtractor
from research_os.research.quantitative import HeuristicQuantitativeExtractor

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "claim_merge"


def _build(names: list[str]):
    evidence, quantitative, chunks = [], [], []
    for index, name in enumerate(names):
        source_version_id = f"sv_{index}"
        doc_chunks = chunk_pages(load_markdown(FIXTURES / name), source_version_id)
        doc_evidence = HeuristicEvidenceExtractor().extract(doc_chunks)
        chunks.extend(doc_chunks)
        evidence.extend(doc_evidence)
        quantitative.extend(HeuristicQuantitativeExtractor().extract(doc_evidence))
    return HeuristicClaimBuilder().build(evidence, quantitative=quantitative, chunks=chunks)


def test_identical_identity_and_value_merges_into_one_claim():
    claims, relations = _build(["paper_a.md", "paper_b.md"])

    assert len(claims) == 1
    assert len(relations) == 2
    assert {relation.claim_id for relation in relations} == {claims[0].id}
    assert "merged by identity key" in relations[0].rationale


def test_same_identity_but_different_value_stays_separate():
    claims, _ = _build(["paper_a.md", "paper_c.md"])

    assert len(claims) == 2, "different reported values are P5's input, not duplicates"
    assert claims[0].identity_key != claims[1].identity_key


def test_our_method_from_two_papers_never_merges():
    """Two papers' own methods are different methods, however alike the sentence."""
    claims, _ = _build(["paper_self_a.md", "paper_self_b.md"])

    assert len(claims) == 2
    assert claims[0].identity_key != claims[1].identity_key


def test_identity_key_is_persisted_on_the_claim():
    claims, _ = _build(["paper_a.md"])

    assert claims[0].identity_key
    assert claims[0].identity_key.startswith("restormer|")


def test_single_source_still_produces_a_relation_per_evidence():
    claims, relations = _build(["paper_a.md"])

    assert len(claims) == 1
    assert len(relations) == 1
    assert "derived from this evidence" in relations[0].rationale


def test_speculation_still_becomes_an_unsupported_claim():
    """The builder must not drop speculation: it is a claim with no evidence."""
    claims, relations = _build(["paper_speculation.md"])

    assert any(claim.status.value == "UNSUPPORTED" for claim in claims)
    unsupported = next(claim for claim in claims if claim.status.value == "UNSUPPORTED")
    assert all(relation.claim_id != unsupported.id for relation in relations)


def test_close_values_are_not_bucketed_together():
    """0.42 vs 0.44 dB is a real disagreement, not a rounding artefact; one
    decimal of PSNR would silently merge them."""
    claims, _ = _build(["paper_a.md", "paper_d.md"])

    assert len(claims) == 2
