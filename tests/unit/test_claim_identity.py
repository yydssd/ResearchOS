"""Claim identity: what makes two claims "the same claim" (P4 spec §5, plan §16).

Every assertion here exists because the naive version failed on real papers:
multi-metric sentences lost the metric dimension, full-sentence subject search
took the object for the subject, and "our method" from two papers merged.
"""

from __future__ import annotations

from research_os.domain.models import QuantitativeEvidence
from research_os.research.claims import ClaimIdentity, extract_identity, may_merge
from research_os.research.scope import BlockScope


def _identity(text: str, sv: str = "sv_1", scope=None, quantitative=None) -> ClaimIdentity:
    return extract_identity(
        text,
        source_version_id=sv,
        scope=scope,
        quantitative=quantitative or [],
    )


def test_dataset_makes_two_claims_different():
    """Plan §16 acceptance: Rain100H and SIDD must never collapse into one."""
    a = _identity("On the Rain100H benchmark, our method improves PSNR by 0.42 dB.")
    b = _identity("On the SIDD dataset, our method improves PSNR by 0.42 dB.")

    assert a.dataset == frozenset({"Rain100H"})
    assert b.dataset == frozenset({"SIDD"})
    assert a.key() != b.key()
    assert not may_merge(a, b)


def test_multiple_metrics_are_kept_as_a_set():
    """'PSNR ... and SSIM ...' is the most common result sentence; returning None
    for 'ambiguous' throws the whole dimension away."""
    identity = _identity("On Rain100H, our method improves PSNR by 0.42 dB and SSIM by 0.013.")

    assert identity.metric == frozenset({"PSNR", "SSIM"})


def test_subject_comes_from_the_clause_before_the_predicate():
    """'the model' after the verb is the object, not the subject."""
    identity = _identity("The gating mechanism enables the model to weight cues.")

    assert identity.subject is None


def test_proper_noun_subject_is_normalised():
    identity = _identity("On Rain100H, Restormer improves PSNR by 0.42 dB.")

    assert identity.subject == "restormer"


def test_self_subject_is_bound_to_its_source():
    a = _identity("Our method improves PSNR by 0.42 dB on Rain100H.", sv="sv_a")
    b = _identity("Our method improves PSNR by 0.42 dB on Rain100H.", sv="sv_b")

    assert a.subject == "self@sv_a"
    assert b.subject == "self@sv_b"
    assert a.key() != b.key()


def test_third_party_sentence_gets_no_implicit_self_subject():
    """A baseline's number must not be recorded as this paper's own result."""
    identity = _identity("On Rain100H, the previous method improves PSNR by 0.42 dB.")

    assert identity.subject is None


def test_scope_fills_in_what_the_sentence_omits():
    scope = BlockScope(task="super-resolution", datasets=frozenset({"Set5"}), inherited_from={})

    identity = _identity("The maximum gain reaches 0.26 dB here.", scope=scope)

    assert identity.task == "super-resolution"
    assert identity.dataset == frozenset({"Set5"})


def test_sentence_wins_over_inherited_dataset():
    scope = BlockScope(task="denoising", datasets=frozenset({"Set5"}), inherited_from={})

    identity = _identity("On SIDD the method improves PSNR by 0.42 dB.", scope=scope)

    assert identity.dataset == frozenset({"SIDD"})
    assert identity.task == "denoising"


def test_value_bucket_differs_when_values_differ():
    low = _identity(
        "On Rain100H, Restormer improves PSNR by 0.42 dB.",
        quantitative=[QuantitativeEvidence(evidence_id="e", metric="PSNR", value=39.2)],
    )
    high = _identity(
        "On Rain100H, Restormer improves PSNR by 0.42 dB.",
        quantitative=[QuantitativeEvidence(evidence_id="e", metric="PSNR", value=39.5)],
    )

    assert low.value_bucket != high.value_bucket
    assert not may_merge(low, high)


def test_merge_requires_a_fully_determined_scope():
    """'unknown' is not 'identical': two bare claims must not merge."""
    a = _identity("The gating mechanism enables better weighting of cues.")
    b = _identity("The gating mechanism enables better weighting of cues.")

    assert a.key() == b.key()
    assert not may_merge(a, b)


def test_label_is_human_readable():
    identity = _identity("On Rain100H, our method improves PSNR by 0.42 dB.")

    assert "Rain100H" in identity.label()
    assert "PSNR" in identity.label()
