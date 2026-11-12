"""Hold-out evaluation for P4 claim synthesis (20 unseen papers).

Nothing here is tuned to the numbers it reports: the papers come from a live
arXiv query and have never been used while building the extractor. Run it with a
network connection:

    python scripts/holdout_claim_quality.py [--papers 20] [--query "..."]

What it measures, and why each number matters:

- identity coverage   - how often a claim gets subject+dataset+direction, i.e. how
                        often the merge gate could even apply (P4 spec §6)
- grounding split     - structured vs unstructured vs none, the (b) channel's reach
                        (P4 spec §8)
- cross-document merges - expected to be rare; a non-zero count without a shared
                        method+dataset would mean an over-eager gate
- kept-apart groups   - claims that look alike and were correctly not merged

Full text comes from ar5iv (LaTeX echo is stripped by the loader since P4 task 1).
"""

from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.research.claim_builder import HeuristicClaimBuilder
from research_os.research.claims import ClaimIdentity, mergeable
from research_os.research.evidence_extractor import HeuristicEvidenceExtractor
from research_os.research.quantitative import HeuristicQuantitativeExtractor
from research_os.sources.providers import ArxivProvider

HEADERS = {"User-Agent": "ResearchOS/0.1 (hold-out evaluation)"}
CACHE = Path(".holdout_cache")


def collect_ids(query: str, wanted: int) -> list[str]:
    candidates = ArxivProvider().search(query, limit=wanted * 2)
    ids: list[str] = []
    for candidate in candidates:
        if candidate.arxiv_id and candidate.arxiv_id not in ids:
            ids.append(candidate.arxiv_id)
        if len(ids) >= wanted:
            break
    return ids


def fetch(arxiv_id: str) -> Path | None:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{arxiv_id}.html"
    if path.exists():
        return path
    url = f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"
    try:
        response = httpx.get(url, headers=HEADERS, timeout=90, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001 - evaluation harness
        print(f"  fetch failed {arxiv_id}: {exc}")
        return None
    if response.status_code != 200 or len(response.text) < 4096:
        print(f"  no full text for {arxiv_id} ({response.status_code})")
        return None
    path.write_text(response.text, encoding="utf-8")
    time.sleep(2)  # ar5iv is a volunteer service
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--papers", type=int, default=20)
    parser.add_argument(
        "--ids-file",
        default=None,
        help="read arXiv ids from a file (one per line) instead of querying the API; "
        "use this when the network blocks export.arxiv.org",
    )
    parser.add_argument("--query", default="all-in-one image restoration spatial degradation conditioning")
    args = parser.parse_args()

    if args.ids_file:
        ids = [line.strip() for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines() if line.strip()]
        ids = ids[: args.papers]
    else:
        ids = collect_ids(args.query, args.papers)
    print(f"discovered {len(ids)} paper ids from a live arXiv query\n")

    builder = HeuristicClaimBuilder()
    totals = Counter()
    all_claims: list[tuple[str, object]] = []
    identities: list[ClaimIdentity] = []
    per_doc: list[tuple[str, int, int, int, int, int]] = []

    for index, arxiv_id in enumerate(ids, start=1):
        path = fetch(arxiv_id)
        if path is None:
            totals["docs_failed"] += 1
            continue
        try:
            chunks = chunk_pages(load_html(path), f"sv_{arxiv_id}")
            evidence = HeuristicEvidenceExtractor().extract(chunks)
            quantitative = HeuristicQuantitativeExtractor().extract(evidence)
            claims, relations = builder.build(evidence, quantitative=quantitative, chunks=chunks)
        except Exception as exc:  # noqa: BLE001 - evaluation harness
            print(f"  pipeline failed {arxiv_id}: {type(exc).__name__}: {exc}")
            totals["docs_failed"] += 1
            continue

        supported = sum(1 for claim in claims if claim.status.value == "SUPPORTED")
        print(
            f"[{index:>2}/{len(ids)}] {arxiv_id}  chunks={len(chunks):>4} evidence={len(evidence):>4} "
            f"quant={len(quantitative):>3} claims={len(claims):>3} supported={supported}"
        )
        totals["docs"] += 1
        totals["chunks"] += len(chunks)
        totals["evidence"] += len(evidence)
        totals["quantitative"] += len(quantitative)
        totals["claims"] += len(claims)
        totals["supported"] += supported
        totals["unsupported"] += len(claims) - supported
        totals["relations"] += len(relations)
        totals["delta_rows"] += sum(1 for row in quantitative if row.delta is not None)
        per_doc.append((arxiv_id, len(chunks), len(evidence), len(quantitative), len(claims), supported))
        all_claims.extend((arxiv_id, claim) for claim in claims)

    if not totals["docs"]:
        print("no document could be processed")
        return

    # identity coverage: computed the same way the merge gate decides
    for _, claim in all_claims:
        if claim.identity_key and claim.status.value == "SUPPORTED":
            parts = claim.identity_key.split("|")
            if len(parts) >= 7:
                identities.append(
                    ClaimIdentity(
                        subject=parts[0] or None,
                        task=parts[1] or None,
                        dataset=frozenset(filter(None, parts[2].split(","))),
                        metric=frozenset(filter(None, parts[3].split(","))),
                        direction=parts[4] or None,
                        conditions=tuple(filter(None, parts[5].split(";"))),
                        value_bucket=tuple(filter(None, parts[6].split(";"))),
                    )
                )

    grounded = Counter()
    flags = Counter()
    for _, claim in all_claims:
        conditions = claim.conditions or []
        if "quantitative_unstructured" in conditions:
            grounded["unstructured"] += 1
        else:
            grounded["structured_or_none"] += 1
        for flag in conditions:
            if flag in {
                "quantitative_unstructured",
                "scope_undetermined",
                "comparative_unsubstantiated",
            }:
                flags[flag] += 1

    # cross-document merge audit: one key must not collect distant sources
    by_key: dict[str, set[str]] = defaultdict(set)
    for doc, claim in all_claims:
        if claim.status.value == "SUPPORTED" and claim.identity_key:
            by_key[claim.identity_key].add(doc)
    cross_doc = {key: docs for key, docs in by_key.items() if len(docs) > 1}

    print("\n=== totals ===")
    for name in ("docs", "docs_failed", "chunks", "evidence", "quantitative", "claims",
                 "supported", "unsupported", "relations", "delta_rows"):
        print(f"  {name:<16}{totals[name]}")
    print(f"\n  identity fully determined (merge gate would apply): "
          f"{sum(1 for i in identities if mergeable(i))}/{len(identities)}")
    print(f"  claims with a task inherited from a heading: {sum(1 for i in identities if i.task)}")
    print(f"  claims with a dataset: {sum(1 for i in identities if i.dataset)}")
    print(f"  claims with a metric: {sum(1 for i in identities if i.metric)}")
    print(f"  grounded: {dict(grounded)}")
    print(f"  quality flags: {dict(flags)}")
    print(f"\n  cross-document merge keys: {len(cross_doc)} (each should be a genuine duplicate)")
    for key, docs in list(cross_doc.items())[:5]:
        print(f"    {key}  <- {sorted(docs)}")

    print("\n=== per document ===")
    for arxiv_id, chunks, evidence, quant, claims, supported in per_doc:
        print(f"  {arxiv_id:<12} chunks={chunks:>4} evidence={evidence:>4} quant={quant:>3} "
              f"claims={claims:>3} supported={supported:>3}")


if __name__ == "__main__":
    main()
