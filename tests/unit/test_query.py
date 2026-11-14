"""Deterministic query generation for source discovery (plan §14)."""

from research_os.sources.query import build_queries, extract_keyterms


def test_extract_keyterms_drops_stopwords_and_dedupes():
    question = "Does spatial degradation conditioning provide value in all-in-one image restoration?"
    terms = extract_keyterms(question)
    assert terms[0] == "spatial"
    assert "does" not in terms
    assert "in" not in terms
    assert len(terms) == len(set(terms))


def test_extract_keyterms_preserves_hyphenated_terms():
    assert "all-in-one" in extract_keyterms("all-in-one image restoration")


def test_extract_keyterms_handles_empty_input():
    assert extract_keyterms("") == []
    assert build_queries("") == []


def test_build_queries_adds_one_breadth_variant():
    assert build_queries("all-in-one image restoration") == [
        "all-in-one image restoration",
        "all-in-one image restoration survey",
    ]


def test_build_queries_respects_cap_and_avoids_duplicate_variant():
    assert build_queries("all-in-one image restoration", max_queries=1) == ["all-in-one image restoration"]
    assert build_queries("a survey of image restoration") == ["survey image restoration"]
