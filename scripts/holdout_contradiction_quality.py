"""Reproduce the P5 numbers in docs/evaluation/2026-11-13-p5-contradiction.md.

The report's section 3 figures used to come from an ad-hoc probe that was never
committed, so "20 papers ran through P5" could not be verified by anyone else.
This script is that missing evidence: it rebuilds claims from the cached pages,
runs the same assessor the supervisor uses, and prints every counter the report
transcribes. No network access; `.holdout_cache/` is gitignored and re-fetchable.

    python scripts/holdout_contradiction_quality.py
    python scripts/holdout_contradiction_quality.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.research.claim_builder import HeuristicClaimBuilder
from research_os.research.contradiction import HeuristicContradictionAssessor
from research_os.research.evidence_extractor import HeuristicEvidenceExtractor
from research_os.research.quantitative import HeuristicQuantitativeExtractor

CACHE = Path(".holdout_cache")
DEFAULT_IDS = Path("docs/evaluation/holdout-ids-2026-11-12.txt")


def _ids(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _tier(claim) -> str | None:
    for item in claim.conditions:
        if item.startswith("conditions_from="):
            return item.split("=", 1)[1]
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", type=Path, default=DEFAULT_IDS)
    args = parser.parse_args()

    claims = []
    chunks_total = evidence_total = 0
    for arxiv_id in _ids(args.ids_file):
        path = CACHE / f"{arxiv_id}.html"
        chunks = chunk_pages(load_html(path), f"sv_{arxiv_id}")
        evidence = HeuristicEvidenceExtractor().extract(chunks)
        quantitative = HeuristicQuantitativeExtractor().extract(evidence)
        built, _ = HeuristicClaimBuilder().build(
            evidence, quantitative=quantitative, chunks=chunks
        )
        claims.extend(built)
        chunks_total += len(chunks)
        evidence_total += len(evidence)

    supported = [c for c in claims if c.status.value == "SUPPORTED"]
    directions = Counter((c.identity_key or "").split("|")[4] or "None" for c in supported)
    mergeable = sum(
        1 for c in supported
        if (c.identity_key or "").split("|")[0]
        and (c.identity_key or "").split("|")[2]
        and (c.identity_key or "").split("|")[4]
    )

    assessments, stats = HeuristicContradictionAssessor().assess(claims)
    tier_by_id = {c.id: _tier(c) for c in claims}
    tiers = Counter()
    for item in assessments:
        pair = {tier_by_id.get(item.claim_a_id), tier_by_id.get(item.claim_b_id)}
        if "section-first-mention" in pair:
            tiers["either_side_first_mention"] += 1
        elif pair & {"heading"}:
            tiers["heading_involved"] += 1
        else:
            tiers["sentence_or_unspecified"] += 1

    print("=== inputs ===")
    print(f"papers                    {len(_ids(args.ids_file))}")
    print(f"chunks                    {chunks_total}")
    print(f"evidence                  {evidence_total}")
    print(f"claims                    {len(claims)} (supported {len(supported)})")
    print(f"claims with a dataset     {sum(1 for c in supported if (c.identity_key or '').split('|')[2])}")
    print(f"claims with a metric      {sum(1 for c in supported if (c.identity_key or '').split('|')[3])}")
    print(f"merge gate satisfied      {mergeable}/{len(supported)}")
    print("\n=== directions (supported) ===")
    for name in ("UP", "None", "DOWN", "LEVEL"):
        print(f"  {name:<6} {directions[name]:>5} ({directions[name]/len(supported):.1%})")
    print(f"non-negative (UP+None)    {directions['UP'] + directions['None']} "
          f"({(directions['UP'] + directions['None'])/len(supported):.1%})")

    print("\n=== pairing ===")
    print(f"total_before_cap          {stats.total_before_cap}")
    print(f"evaluated                 {stats.evaluated}")
    print(f"coverage                  {stats.coverage:.1%}")
    print(f"skipped_missing_dataset   {stats.skipped_missing_dataset}")
    print(f"skipped_missing_metric    {stats.skipped_missing_metric}")
    print(f"skipped_self_prefilter    {stats.skipped_self_prefilter}")
    print(f"skipped_same_value        {stats.skipped_same_value}")
    print(f"skipped_cap               {stats.skipped_cap}")
    print(f"assessments               {len(assessments)}")
    print("by type:")
    for name, count in sorted(stats.emitted_by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<32} {count}")
    print("\n=== condition provenance of assessed pairs ===")
    for name, count in tiers.most_common():
        print(f"  {name:<32} {count}")
    downgraded = sum(
        1 for a in assessments
        if "provenance" in a.explanation or "inherited" in a.explanation
    )
    print(f"D13 downgrades            {downgraded}")


if __name__ == "__main__":
    main()
