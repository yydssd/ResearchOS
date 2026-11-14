"""Compare the blind annotation sheet against the fixture labels.

Purpose: turn the fixture accuracy from a self-consistency number into a real
one. The sheet is filled without seeing `expected`; this script is the first
thing allowed to look at both, and it reports agreement plus every disagreement
so they can be adjudicated one by one.

    python scripts/compare_annotation_sheet.py                      # check + compare
    python scripts/compare_annotation_sheet.py --csv path/to.csv

Exit codes: 0 = every row filled and valid; 1 = incomplete or invalid sheet.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

SHEET = Path("docs/evaluation/annotation-sheet-2026-11-14.csv")
FIXTURE = Path("tests/fixtures/contradiction/pairs.json")
LABELS = {
    "TRUE_CONTRADICTION",
    "SCOPE_DIFFERENCE",
    "EXPERIMENTAL_INCOMPATIBILITY",
    "COMPLEMENTARY",
    "INSUFFICIENT_EVIDENCE",
    "SKIP",
}


def _normalise(value: str) -> str:
    return (value or "").strip().upper().replace(" ", "_").replace("-", "_")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=SHEET)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8-sig")))
    expected = {
        entry["id"]: entry["expected"]
        for entry in json.loads(FIXTURE.read_text(encoding="utf-8"))["pairs"]
    }

    missing, invalid = [], []
    for row in rows:
        label = _normalise(row.get("your_label", ""))
        if not label:
            missing.append(row["id"])
        elif label not in LABELS:
            invalid.append((row["id"], row.get("your_label")))

    print(f"rows                    {len(rows)}")
    print(f"blank labels            {len(missing)}" + (f"  {missing}" if missing else ""))
    print(f"invalid labels          {len(invalid)}" + (f"  {invalid}" if invalid else ""))
    if missing or invalid:
        print("\nSheet is not complete - fill every row with one of:")
        print("  " + ", ".join(sorted(LABELS)))
        return 1

    labelled = [(row["id"], _normalise(row["your_label"]), row.get("your_reason", "")) for row in rows]
    agree = [(i, lab) for i, lab, _ in labelled if expected[i] == lab]
    differ = [(i, lab, expected[i], reason) for i, lab, reason in labelled if expected[i] != lab]

    print(f"\nagreement               {len(agree)}/{len(labelled)} "
          f"({len(agree) / len(labelled):.1%})")
    print(f"disagreements           {len(differ)}")
    if differ:
        print("\nid    your label                      machine label                   your reason")
        for ident, manual, machine, reason in differ:
            print(f"{ident:<5} {manual:<32} {(machine or 'None'):<32} {reason}")
        print("\nEach row above is 'machine wrong' / 'annotation wrong' / 'rule undefined' -")
        print("record the verdict in ANNOTATION.md before changing any expected value.")

    distribution = Counter(label for _, label, _ in labelled)
    print("\nlabel distribution:")
    for label, count in distribution.most_common():
        print(f"  {label:<32} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
