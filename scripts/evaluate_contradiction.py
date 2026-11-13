"""Layered accuracy report for the P5 cascade (P5 spec §9).

A single accuracy number hides everything that matters here: the classes are
unbalanced (the corpus produces almost no true contradictions), so 'always
answer SCOPE_DIFFERENCE' scores well. This reports per-subset accuracy, a full
confusion matrix, TRUE_CONTRADICTION precision/recall, and the skip rate.

    python scripts/evaluate_contradiction.py [--json tests/fixtures/contradiction/pairs.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim
from research_os.research.contradiction import assess_pair, pair_candidates

TYPES = [t.value for t in ContradictionType]
COLUMNS = TYPES + ["SKIPPED"]
# Six-character prefixes are ambiguous (`TRUE_C` next to `EXPERI`), so the header
# gets an explicit alias instead of a slice.
ALIASES = {
    "TRUE_CONTRADICTION": "TRUE_CON",
    "EXPERIMENTAL_INCOMPATIBILITY": "EXPERIM",
    "SCOPE_DIFFERENCE": "SCOPE",
    "COMPLEMENTARY": "COMPLEM",
    "INSUFFICIENT_EVIDENCE": "INSUFF",
    "SKIPPED": "SKIPPED",
}
FIXTURE = Path("tests/fixtures/contradiction/pairs.json")


def _claim(key: str, text: str, ident: str) -> Claim:
    return Claim(
        id=ident,
        text=text,
        identity_key=key,
        status=ClaimStatus.SUPPORTED,
        confidence_label=ConfidenceLabel.LOW,
    )


def evaluate(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for entry in payload["pairs"]:
        ident = entry["id"]
        a = _claim(entry["a_key"], entry["a_text"], f"{ident}_a")
        b = _claim(entry["b_key"], entry["b_text"], f"{ident}_b")
        for side, claim in (("a", a), ("b", b)):
            provenance = entry.get(f"{side}_conditions_from")
            if provenance:
                # Provenance is not identity: it travels on the claim's conditions
                # list, the same way the builder stores it (D13).
                claim.conditions = [f"conditions_from={provenance}"]

        pairs, _ = pair_candidates([a, b])
        if not pairs:
            actual = None  # never became a candidate: not judged, not wrong
        else:
            result = assess_pair(a, b)
            actual = result.relationship.value if result else None
        rows.append(
            {
                "id": ident,
                "source": entry["source"],
                "expected": entry["expected"],
                "actual": actual,
            }
        )
    return rows


def summarise(rows: list[dict]) -> dict:
    def block(subset: list[dict]) -> dict:
        judged = [r for r in subset if r["expected"] is not None]
        # Only a pair that should have been judged and was not counts as skipped;
        # an unpaired fixture has no verdict by design and is not a miss.
        skipped = sum(1 for r in subset if r["expected"] is not None and r["actual"] is None)
        correct = sum(1 for r in judged if r["expected"] == r["actual"])
        return {
            "n": len(subset),
            "judged": len(judged),
            "skipped": skipped,
            "correct": correct,
            "accuracy": round(correct / len(judged), 3) if judged else 0.0,
        }

    confusion = {expected: {column: 0 for column in COLUMNS} for expected in TYPES}
    for row in rows:
        if row["expected"] is None:
            continue
        column = row["actual"] or "SKIPPED"
        confusion[row["expected"]][column] += 1

    tp = sum(1 for r in rows if r["expected"] == "TRUE_CONTRADICTION" and r["actual"] == "TRUE_CONTRADICTION")
    fp = sum(1 for r in rows if r["actual"] == "TRUE_CONTRADICTION" and r["expected"] != "TRUE_CONTRADICTION")
    fn = sum(1 for r in rows if r["expected"] == "TRUE_CONTRADICTION" and r["actual"] != "TRUE_CONTRADICTION")
    return {
        "overall": block([r for r in rows]),
        "real": block([r for r in rows if r["source"] == "real"]),
        "constructed": block([r for r in rows if r["source"] == "constructed"]),
        "TRUE_CONTRADICTION": {
            "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
        },
        "confusion": confusion,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=str(FIXTURE))
    args = parser.parse_args()

    rows = evaluate(Path(args.json))
    report = summarise(rows)

    for name in ("overall", "real", "constructed"):
        block = report[name]
        print(f"{name:<12} n={block['n']:<3} judged={block['judged']:<3} "
              f"correct={block['correct']:<3} skipped={block['skipped']:<3} acc={block['accuracy']:.1%}")
    print(f"\nTRUE_CONTRADICTION precision={report['TRUE_CONTRADICTION']['precision']:.1%} "
          f"recall={report['TRUE_CONTRADICTION']['recall']:.1%}")

    print("\nconfusion (rows = expected, cols = actual)")
    width = max(len(name) for name in TYPES) + 2
    header = "".join(f"{ALIASES[c]:>8}" for c in COLUMNS)
    print(f"{'':<{width}}{header}")
    for expected, row in report["confusion"].items():
        cells = "".join(f"{row[c]:>8}" for c in COLUMNS)
        print(f"{expected:<{width}}{cells}")

    print(
        "\nNote: fixture labels were derived from the same rules the cascade implements.\n"
        "Agreement therefore measures regression, not correctness. TRUE_CONTRADICTION\n"
        "recall is unverified on real text: the hold-out corpus contains no such pair,\n"
        "and the constructed ones were written from the rules they are meant to test."
    )

    wrong = [r for r in rows if r["expected"] is not None and r["actual"] != r["expected"]]
    if wrong:
        print("\nmisclassified:")
        for row in wrong:
            print(f"  {row['id']} ({row['source']}): expected {row['expected']}, got {row['actual']}")


if __name__ == "__main__":
    main()
