"""Deterministic query generation for source discovery (plan §14).

Query rewriting is a semantic judgment, so it is deliberately deferred to the
counter-search phase (P7). Here we only extract content terms and one breadth
variant - deterministic, auditable, and cheap to test.
"""

from __future__ import annotations

import re

_STOPWORDS = frozenset(
    """a an and are as at be been being between by can could did do does for from
    has have how in into is it its may might more most no not of on or our over
    should so than that the their them then there these they this those to under
    upon was were what when where which while who why will with within without
    would""".split()
)

# Hyphens and plus signs are kept: "all-in-one" and "c++" are meaningful terms.
_SPLIT = re.compile(r"[^a-z0-9\-\+]+")
_BREADTH_TERMS = frozenset({"survey", "review", "tutorial"})


def extract_keyterms(question: str) -> list[str]:
    """Content words in original order: lowercased, hyphen-preserving, deduped."""
    text = _SPLIT.sub(" ", (question or "").lower())
    terms: list[str] = []
    for token in text.split():
        token = token.strip("-+")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def build_queries(question: str, max_queries: int = 2) -> list[str]:
    """Primary keyterm query plus one breadth variant, capped by ``max_queries``.

    The breadth variant ("... survey") exists because discovery aims at coverage,
    not precision; the extra results are still only candidates (plan §14).
    """
    terms = extract_keyterms(question)
    if not terms:
        return []
    base = " ".join(terms)
    queries = [base]
    if max_queries > 1 and not (_BREADTH_TERMS & set(terms)):
        queries.append(f"{base} survey")
    return queries[:max_queries]
