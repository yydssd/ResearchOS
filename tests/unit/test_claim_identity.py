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
        quantitative=[QuantitativeEvidence(evidence_id="e", metric="PSNR", value=39.18)],
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


def test_key_uses_empty_fields_not_the_string_none():
    """`str(None)` in a key makes it unparseable: '' and 'None' would collide and
    every reader has to special-case the literal string."""
    identity = ClaimIdentity(
        subject=None, task=None, dataset=frozenset(), metric=frozenset(),
        direction=None, conditions=(), value_bucket=(),
    )

    assert identity.key() == "||||||"
    assert "None" not in identity.key()


def test_key_round_trips_through_split():
    identity = _identity("On Rain100H, Restormer improves PSNR by 0.42 dB.")
    parts = identity.key().split("|")

    assert len(parts) == 7
    assert parts[0] == "restormer"
    assert parts[2] == "rain100h"
    assert parts[3] == "psnr"


def test_sentence_initial_word_is_not_a_method_name():
    """Capitalisation at the start of a sentence is grammar, not a proper noun.

    On real full text this rule is what keeps 'Motivated', 'Extensive' and
    'Recently' out of the subject slot; without it they doubled as method names.
    """
    for opener in ("Motivated", "Extensive", "Recently"):
        identity = _identity(
            f"{opener} experiments on the benchmark show that the model improves PSNR by 0.4 dB."
        )
        assert identity.subject != opener.lower(), opener


def test_proposed_method_is_the_papers_own_method():
    identity = _identity("Proposed method significantly outperforms the SOTA methods on SIDD.")

    assert identity.subject == "self@sv_1"


def test_method_name_inside_a_sentence_is_still_found():
    identity = _identity("The results show that Restormer improves PSNR by 0.42 dB on Rain100H.")

    assert identity.subject == "restormer"


def test_implicit_self_is_marked_as_inferred():
    """A sentence with no self-reference still gets `self` when the scope is
    known ("the reported gains reach 0.4 dB"). That default is useful but weak:
    on the hold-out 10 of 12 sampled `self` claims were mechanism prose or
    figure captions, so downstream must be able to tell the two apart."""
    identity = _identity("The reported gains on SIDD reach 0.4 dB in our study.")

    assert identity.subject == "self@sv_1"
    assert identity.subject_inferred is True


def test_explicit_self_reference_is_not_marked_as_inferred():
    identity = _identity("Our method improves PSNR by 0.42 dB on Rain100H.")

    assert identity.subject == "self@sv_1"
    assert identity.subject_inferred is False


def test_inferred_subject_does_not_change_the_key():
    """The flag is provenance, not identity: same scope must still merge."""
    implicit = _identity("The reported gains on SIDD reach 0.4 dB in this study.")
    explicit = _identity("Our model gains 0.4 dB on SIDD in this study.")

    assert implicit.subject_inferred is True
    assert implicit.key() == explicit.key()


def test_unit_words_are_not_method_names():
    """'dB' has an inner capital, so the proper-noun rule accepted it and `db`
    became the most repeated named subject across the hold-out (9 papers)."""
    for text in (
        "The performance improvement is over 55 dB on dehazing.",
        "The gain reaches 0.42 dB on Rain100H compared with the previous work.",
        "It improves 3.1 % over the strongest competitor.",
    ):
        identity = _identity(text)
        assert identity.subject not in {"db", "psnr", "ssim"}, text
