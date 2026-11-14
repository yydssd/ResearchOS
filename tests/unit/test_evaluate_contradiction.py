"""The report must separate real from constructed pairs, not average them away."""

from __future__ import annotations

from scripts.evaluate_contradiction import FIXTURE, evaluate, summarise


def test_precision_and_recall_are_reported_for_true_contradiction():
    rows = [
        {"source": "real", "expected": "TRUE_CONTRADICTION", "actual": "TRUE_CONTRADICTION"},
        {"source": "real", "expected": "TRUE_CONTRADICTION", "actual": "SCOPE_DIFFERENCE"},
        {"source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "TRUE_CONTRADICTION"},
        {"source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "SCOPE_DIFFERENCE"},
    ]

    report = summarise(rows)

    assert report["overall"]["accuracy"] == 0.5
    assert report["TRUE_CONTRADICTION"]["precision"] == 0.5
    assert report["TRUE_CONTRADICTION"]["recall"] == 0.5


def test_skipped_is_counted_separately_from_a_wrong_label():
    rows = [
        {"source": "real", "expected": None, "actual": None},
        {"source": "real", "expected": "SCOPE_DIFFERENCE", "actual": None},
    ]

    report = summarise(rows)

    assert report["overall"]["skipped"] == 1
    assert report["overall"]["accuracy"] == 0.0


def test_confusion_matrix_is_square_over_the_five_types():
    rows = [{"source": "constructed", "expected": "COMPLEMENTARY", "actual": "COMPLEMENTARY"}]

    report = summarise(rows)

    assert set(report["confusion"]["COMPLEMENTARY"]) == {
        "TRUE_CONTRADICTION",
        "EXPERIMENTAL_INCOMPATIBILITY",
        "SCOPE_DIFFERENCE",
        "COMPLEMENTARY",
        "INSUFFICIENT_EVIDENCE",
        "SKIPPED",
    }
    # The key set above is built from a constant, so emptying the accumulation
    # loop would still pass it; these pin the cell the single row lands in.
    assert report["confusion"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 1
    assert sum(report["confusion"]["COMPLEMENTARY"].values()) == 1


def test_pairing_level_exclusions_are_not_counted_as_wrong():
    """p17 and p18 are `null` because pairing never produced the pair. That is a
    different fact from "the cascade judged it and declined" - both are silence,
    but only one of them is the cascade's decision."""
    rows = {row["id"]: row for row in evaluate(FIXTURE)}

    assert rows["p17"]["actual"] is None
    assert rows["p18"]["actual"] is None


def test_confusion_is_reported_per_subset():
    """Spec §9 #3: real, constructed and combined each need their own matrix.

    Averaging them hides the only comparison that matters - whether the rules work
    on real sentences or only on the ones written to match them.
    """
    rows = [
        {"id": "r1", "source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "SCOPE_DIFFERENCE"},
        {"id": "r2", "source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "TRUE_CONTRADICTION"},
        {"id": "c1", "source": "constructed", "expected": "COMPLEMENTARY", "actual": "COMPLEMENTARY"},
    ]

    report = summarise(rows)

    assert report["confusion"]["SCOPE_DIFFERENCE"]["SCOPE_DIFFERENCE"] == 1
    # COMPLEMENTARY->COMPLEMENTARY only exists in the constructed row: without this
    # the overall matrix could silently degrade into the real one and still pass.
    assert report["confusion"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 1
    assert report["confusion_by_subset"]["real"]["SCOPE_DIFFERENCE"]["TRUE_CONTRADICTION"] == 1
    assert report["confusion_by_subset"]["constructed"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 1
    assert report["confusion_by_subset"]["real"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 0


def test_an_unknown_source_is_rejected_rather_than_dropped():
    """A third source would vanish from all three matrices without a word, and the
    per-subset sums would stop adding up to the overall one."""
    import pytest as _pytest

    rows = [{"id": "x", "source": "holdout", "expected": "COMPLEMENTARY", "actual": "COMPLEMENTARY"}]

    with _pytest.raises(ValueError, match="unknown fixture source"):
        summarise(rows)


def test_the_fixture_set_matches_the_cascade_it_pins():
    """This is a regression lock, not a quality measure: the labels were derived
    from the same rules, so agreement proves the rules still behave as written,
    never that they are right."""
    wrong = [r for r in evaluate(FIXTURE) if r["expected"] != r["actual"]]

    assert wrong == []


def test_the_fixture_path_does_not_depend_on_the_working_directory(monkeypatch, tmp_path):
    """The suite used to be green only when run from the repository root.

    The script resolved `tests/fixtures/...` relatively, so running the same file
    from another directory failed with FileNotFoundError while looking like a code
    bug.
    """
    assert FIXTURE.is_absolute()
    assert FIXTURE.exists()

    monkeypatch.chdir(tmp_path)
    assert FIXTURE.exists()
    assert evaluate(FIXTURE)
