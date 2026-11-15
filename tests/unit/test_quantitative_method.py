"""`QuantitativeEvidence.method` names the method the row belongs to (§15).

Before this, `method` was the constant "proposed method" whenever
`_PROPOSED_RE` matched, so L1 could never be observed per row: a row said
"proposed method" even when the paper had a name, and a row about a baseline's
number said nothing at all (design §10.3).
"""

from __future__ import annotations

from research_os.research.quantitative import HeuristicQuantitativeExtractor

EXTRACTOR = HeuristicQuantitativeExtractor()


def test_a_self_sentence_carries_the_papers_own_name():
    facts = EXTRACTOR.extract_from_text(
        "Our method improves the baseline PSNR by 0.42 dB.", "e1", method_name="LangProp"
    )
    assert [fact.method for fact in facts] == ["LangProp"]


def test_a_named_third_party_method_is_not_the_papers_name():
    """"Restormer improves Rain100H PSNR" is a row about Restormer. Filling it
    with the paper's own name is the cross-attribution §4.2 exists to prevent."""
    facts = EXTRACTOR.extract_from_text(
        "Restormer improves Rain100H PSNR by 0.44 dB.", "e1", method_name="LangProp"
    )
    assert [fact.method for fact in facts] == ["Restormer"]
    # A sentence-initial opener is not a subject, and it is not adjacent to the
    # predicate either: on the hold-out set this sentence used to produce a
    # method called "Introducing".
    facts = EXTRACTOR.extract_from_text(
        "Introducing a small weight increases the PSNR to 32.75 dB.", "e1", method_name="LangProp"
    )
    assert [fact.method for fact in facts] == [None]


def test_no_name_and_no_named_subject_leaves_method_empty():
    facts = EXTRACTOR.extract_from_text(
        "The gain is 0.11 dB on Rain100L.", "e1", method_name=None
    )
    assert [fact.method for fact in facts] == [None]


def test_the_placeholder_survives_when_the_paper_has_no_name():
    """Design §10.3 does not remove the old behaviour - it narrows it. With no
    resolved name, "our method" still has to say something."""
    facts = EXTRACTOR.extract_from_text(
        "Our method improves the baseline PSNR by 0.42 dB.", "e1", method_name=None
    )
    assert [fact.method for fact in facts] == ["proposed method"]
