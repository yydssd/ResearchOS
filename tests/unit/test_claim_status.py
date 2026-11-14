"""Claim status semantics (P4 spec §8, plan §16).

The distinction these tests protect: `UNSUPPORTED` means "no supporting evidence".
"Weak, unstructured, or out-of-scope evidence" is a LOW-confidence flag on a
SUPPORTED claim. Collapsing the two turns `unsupported` into a synonym for
"low confidence", and the memo then cannot tell a guess from a measurement.
"""

from __future__ import annotations

from research_os.domain.enums import ClaimStatus, ConfidenceLabel
from research_os.domain.models import Evidence, QuantitativeEvidence
from research_os.research.claims import classify_claim, extract_identity


def _identity(text: str = "On Rain100H, our method improves PSNR by 0.42 dB."):
    return extract_identity(
        text, source_version_id="sv_1", scope=None, quantitative=[]
    )


def _evidence(text: str) -> Evidence:
    return Evidence(source_version_id="sv_1", text=text, chunk_id="c1", page_label="md")


def test_speculation_is_unsupported():
    status, confidence, _ = classify_claim(
        "We believe spatial cues may help on easier benchmarks.", _identity(), [], {}
    )

    assert status is ClaimStatus.UNSUPPORTED
    assert confidence is ConfidenceLabel.LOW


def test_value_without_structured_fact_stays_supported_but_low():
    """The sentence does support the claim; what is missing is structure."""
    text = "The gain is 0.11 dB on the harder split, which we discuss below."
    status, confidence, flags = classify_claim(text, _identity(text), [_evidence(text)], {})

    assert status is ClaimStatus.SUPPORTED
    assert confidence is ConfidenceLabel.LOW
    assert "quantitative_unstructured" in flags


def test_value_outside_any_scope_is_flagged_too():
    text = "The gain is 0.11 dB on the harder split, which we discuss below."
    _, _, flags = classify_claim(text, _identity(text), [_evidence(text)], {})

    assert "scope_undetermined" in flags


def test_grounded_value_stays_medium_confidence():
    text = "On Rain100H, our method improves PSNR by 0.42 dB."
    evidence = _evidence(text)
    quantitative = {"e-1": [QuantitativeEvidence(evidence_id="e-1", metric="PSNR", value=0.42)]}
    evidence.id = "e-1"

    status, confidence, flags = classify_claim(text, _identity(text), [evidence], quantitative)

    assert status is ClaimStatus.SUPPORTED
    assert confidence is ConfidenceLabel.MEDIUM
    assert flags == []


def test_comparative_without_control_is_flagged():
    text = "Experimental results demonstrate that the method outperforms state-of-the-art methods."
    status, confidence, flags = classify_claim(text, _identity(text), [_evidence(text)], {})

    assert status is ClaimStatus.SUPPORTED
    assert confidence is ConfidenceLabel.LOW
    assert "comparative_unsubstantiated" in flags


def test_comparative_with_a_control_is_not_flagged():
    text = "The method outperforms the baseline compared with prior work on this benchmark."
    _, _, flags = classify_claim(text, _identity(text), [_evidence(text)], {})

    assert "comparative_unsubstantiated" not in flags


def test_plain_qualitative_claim_keeps_medium_confidence():
    """Demoting every qualitative claim would make confidence useless: on real
    abstracts that is 100% of claims."""
    text = "The gating mechanism adaptively weights degradation-specific cues."
    status, confidence, flags = classify_claim(text, _identity(text), [_evidence(text)], {})

    assert status is ClaimStatus.SUPPORTED
    assert confidence is ConfidenceLabel.MEDIUM
    assert flags == []
