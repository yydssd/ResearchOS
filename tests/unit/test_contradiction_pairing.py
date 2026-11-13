"""Pairing decides what can even be compared (P5 spec §4)."""

from __future__ import annotations

from research_os.domain.enums import ClaimStatus
from research_os.domain.models import Claim
from research_os.research.contradiction import pair_candidates


def _claim(key: str, text: str = "x") -> Claim:
    return Claim(text=text, status=ClaimStatus.SUPPORTED, identity_key=key)


def test_same_named_subject_and_task_are_paired():
    a = _claim("restormer|image restoration|sidd|psnr|UP||psnr=39.18")
    b = _claim("restormer|image restoration|gopro|psnr|UP||psnr=32.5")

    pairs, stats = pair_candidates([a, b])

    assert len(pairs) == 1
    assert stats.total_before_cap >= 1


def test_different_subjects_are_not_paired():
    a = _claim("restormer|image restoration|sidd|psnr|UP||")
    b = _claim("mprnet|image restoration|sidd|psnr|UP||")

    pairs, _ = pair_candidates([a, b])

    assert pairs == []


def test_different_tasks_are_not_paired():
    a = _claim("restormer|image restoration|sidd|psnr|UP||")
    b = _claim("restormer|denoising|sidd|psnr|UP||")

    pairs, _ = pair_candidates([a, b])

    assert pairs == []


def test_self_subjects_pair_only_inside_one_document():
    a = _claim("self@sv_a|image restoration|sidd|psnr|UP||")
    b = _claim("self@sv_a|image restoration|sidd|psnr|LEVEL||")
    c = _claim("self@sv_b|image restoration|sidd|psnr|UP||")

    pairs, _ = pair_candidates([a, b, c])

    # Claim ids are random uuids, so the pair is compared on the sorted id tuple.
    assert [(x.id, y.id) for x, y in pairs] == [tuple(sorted((a.id, b.id)))]


def test_self_pairs_need_dataset_and_metric_on_both_sides():
    """Without the prefilter a single document yields 6177 self-pairs; with it, 16."""
    a = _claim("self@sv_a|image restoration||psnr|UP||")
    b = _claim("self@sv_a|image restoration|sidd|psnr|UP||")

    pairs, stats = pair_candidates([a, b])

    assert pairs == []
    assert stats.skipped_self_prefilter == 1


def test_unsupported_claims_are_not_paired():
    a = Claim(text="x", status=ClaimStatus.SUPPORTED, identity_key="m|image restoration|sidd|psnr|UP||")
    b = Claim(text="y", status=ClaimStatus.UNSUPPORTED, identity_key="m|image restoration|sidd|psnr|LEVEL||")

    pairs, _ = pair_candidates([a, b])

    assert pairs == []


def test_pairs_are_ordered_and_deduplicated():
    a = _claim("m|image restoration|sidd|psnr|UP||")
    b = _claim("m|image restoration|sidd|psnr|LEVEL||")

    pairs, _ = pair_candidates([b, a])

    assert len(pairs) == 1
    first, second = pairs[0]
    assert first.id < second.id
