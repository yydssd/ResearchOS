"""Score a filled L3 annotation sheet against the blind model judgement.

Why a script and not a one-off: the agreement number only means something if the
same computation runs every time. Two numbers are reported, and the second one is
the honest one at this sample size:

- raw agreement, per stratum (the sheet is stratified 5 partial + 5 supported, so
  a pooled number would be inflated by the design);
- Cohen's kappa on the binary "supported vs not" collapse, with an explicit note
  that n=10 makes it unstable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

VERDICTS = ("supported", "partial", "unsupported", "unclear")
DEFAULT_SHEET = Path("docs/evaluation/2026-11-16-l3-annotation.json")
DEFAULT_JUDGEMENT = Path("docs/evaluation/2026-11-15-l3-judgement.json")


def _binary(verdict: str) -> str:
    return "supported" if verdict == "supported" else "not"


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa over the binary collapse; 0.0 when chance agrees fully."""
    if not pairs:
        return 0.0
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    human_sup = sum(1 for a, _ in pairs if a == "supported") / n
    model_sup = sum(1 for _, b in pairs if b == "supported") / n
    pe = human_sup * model_sup + (1 - human_sup) * (1 - model_sup)
    if pe == 1.0:
        return 0.0
    return round((po - pe) / (1 - pe), 3)


def score(sheet: dict, judgement: dict) -> dict:
    """Compare a filled sheet with the model's verdicts.

    Raises when a verdict is missing or unknown: an unfilled row scored as
    "disagreement" would silently deflate the number.
    """
    model = {v["id"]: v["verdict"] for v in judgement["verdicts"]}
    rows = []
    missing = []
    for item in sheet["items"]:
        verdict = (item.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            missing.append(item["id"])
            continue
        reference = model.get(item["source_id"])
        if reference is None:
            raise ValueError(f"{item['id']}: source_id {item['source_id']} is not in the judgement file")
        rows.append(
            {
                "id": item["id"],
                "source_id": item["source_id"],
                "human": verdict,
                "model": reference,
                "agree": verdict == reference,
                "stratum": reference,
            }
        )
    if missing:
        raise ValueError(f"unfilled or invalid verdict: {', '.join(missing)}")
    if not rows:
        raise ValueError("no rows to score")

    by_stratum: dict[str, tuple[int, int]] = {}
    for row in rows:
        agree, total = by_stratum.get(row["stratum"], (0, 0))
        by_stratum[row["stratum"]] = (agree + (1 if row["agree"] else 0), total + 1)

    pairs = [(_binary(row["human"]), _binary(row["model"])) for row in rows]
    return {
        "rows": rows,
        "agreement": round(sum(1 for row in rows if row["agree"]) / len(rows), 3),
        "by_stratum": {k: (a, t, round(a / t, 3)) for k, (a, t) in sorted(by_stratum.items())},
        "kappa_binary": kappa(pairs),
        "n": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    parser.add_argument("--judgement", type=Path, default=DEFAULT_JUDGEMENT)
    args = parser.parse_args(argv)

    report = score(
        json.loads(args.sheet.read_text(encoding="utf-8")),
        json.loads(args.judgement.read_text(encoding="utf-8")),
    )
    print(f"n = {report['n']}   raw agreement = {report['agreement']:.1%}   "
          f"kappa(binary) = {report['kappa_binary']:.3f}")
    print("\n| id | human | model | agree |")
    print("|---|---|---|---|")
    for row in report["rows"]:
        mark = "yes" if row["agree"] else "**no**"
        print(f"| {row['id']} | {row['human']} | {row['model']} | {mark} |")
    print("\nby stratum (the sheet is 5 partial + 5 supported by design):")
    for stratum, (agree, total, rate) in report["by_stratum"].items():
        print(f"  model={stratum:<10} {agree}/{total} = {rate:.0%}")
    print("\nkappa on n=10 is unstable: treat it as a floor check, not an estimate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
