"""Deterministic source-identity normalization (plan §14).

Pure functions only, so every rule is pinned down by an assertion here.
"""

import pytest

from research_os.sources.normalize import (
    author_overlap,
    normalize_author,
    normalize_doi,
    normalize_title,
    parse_arxiv,
    title_similarity,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("10.1109/CVPR52688.2022.00564", "10.1109/cvpr52688.2022.00564"),
        ("https://doi.org/10.1109/CVPR52688.2022.00564", "10.1109/cvpr52688.2022.00564"),
        ("http://dx.doi.org/10.1007/978-3-031-73661-2_19", "10.1007/978-3-031-73661-2_19"),
        ("doi:10.1000/ABC-1", "10.1000/abc-1"),
        ("  DOI: 10.1007/978-3-031-73661-2_19.  ", "10.1007/978-3-031-73661-2_19"),
        ("10.1/x", None),
        ("not-a-doi", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("arXiv:2104.12345v3", ("2104.12345", "3")),
        ("2104.12345", ("2104.12345", None)),
        ("https://arxiv.org/abs/2104.12345v2", ("2104.12345", "2")),
        ("https://arxiv.org/pdf/2104.12345v1.pdf", ("2104.12345", "1")),
        ("cs/0601001", ("cs/0601001", None)),
        ("arXiv:hep-th/9901001v2", ("hep-th/9901001", "2")),
        ("garbage", None),
        (None, None),
    ],
)
def test_parse_arxiv(raw, expected):
    assert parse_arxiv(raw) == expected


def test_normalize_title_strips_punctuation_supplements_and_latex():
    assert (
        normalize_title("SwinIR: Image Restoration Using Swin Transformer")
        == "swinir image restoration using swin transformer"
    )
    assert (
        normalize_title("Restormer: Efficient Transformer (Supplementary Material)")
        == "restormer efficient transformer"
    )
    assert normalize_title("A $\\{x\\}$ Study of  Deep   Networks!") == "a x study of deep networks"


def test_title_similarity_bounds_and_duplicate_detection():
    title = "AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion"
    assert title_similarity(title, title) == 1.0
    assert title_similarity(title, "PromptIR: Prompting for All-in-One Image Restoration") < 0.92
    assert title_similarity("", title) == 0.0


def test_author_normalization_handles_both_name_orders():
    assert normalize_author("Zamir, Syed Waqas") == "zamir|s"
    assert normalize_author("Syed Waqas Zamir") == "zamir|s"
    assert normalize_author("Boyun Li") == "li|b"
    assert normalize_author("") == ""


def test_author_overlap_is_relative_to_the_smaller_list():
    assert author_overlap(["Syed Waqas Zamir", "Aditya Arora"], ["Zamir, Syed Waqas"]) == 1.0
    assert author_overlap(["A B"], ["C D"]) == 0.0
    assert author_overlap([], ["C D"]) == 0.0
