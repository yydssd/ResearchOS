"""Read-only audit of method acquisition (spec 2026-11-14).

I/O is separate from arithmetic: `summarise` is a pure function so the tests can
inject synthetic system sides and assert exact numbers. No production code is
modified; the pipeline is only *observed*.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.research.claim_builder import HeuristicClaimBuilder
from research_os.research.evidence_extractor import HeuristicEvidenceExtractor
from research_os.research.method_description import validate_description
from research_os.research.methods import extract_methods, setup_filled
from research_os.research.quantitative import HeuristicQuantitativeExtractor

CACHE = Path(__file__).resolve().parents[1] / ".holdout_cache"
LAYERS = ("L1", "L2", "L3", "L4")
LABELS = ("present", "absent", "ambiguous")
DOMAINS = ("image_restoration", "agent_in_mc")


def load_labels(path: Path, *, require_full_corpus: bool = False) -> list[dict]:
    """Validate the frozen schema. A present cell without locatable evidence is
    rejected here so it can never quietly become a denominator."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["labels"]
    ids = [row["arxiv_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate arxiv_id in labels")
    for row in rows:
        if row["domain"] not in DOMAINS:
            raise ValueError(f"unknown domain: {row['domain']}")
        if set(row["layers"]) != set(LAYERS):
            raise ValueError(f"{row['arxiv_id']}: incomplete layers")
        for layer in LAYERS:
            cell = row["layers"][layer]
            if cell["label"] not in LABELS:
                raise ValueError(f"{row['arxiv_id']}/{layer}: bad label")
            if cell["label"] == "present":
                if not cell["evidence"]:
                    raise ValueError(f"{row['arxiv_id']}/{layer}: present without evidence")
                for ev in cell["evidence"]:
                    if len(ev["quote"]) > 40 or not ev["quote"].strip():
                        raise ValueError(f"{row['arxiv_id']}/{layer}: bad quote")
                    if (ev["section"] is None and ev["page_label"] is None
                            and ev["chunk_index"] is None):
                        raise ValueError(f"{row['arxiv_id']}/{layer}: evidence has no location")
    if require_full_corpus:
        if len(ids) != 40 or {row["domain"] for row in rows} != set(DOMAINS):
            raise ValueError("labels must contain exactly 40 papers across both domains")
    return rows


def _named_subject(claim) -> bool:
    if not claim.identity_key:
        return False
    subject = claim.identity_key.split("|")[0]
    return bool(subject) and not subject.startswith("self@")


def system_side(arxiv_id: str, cache: Path = CACHE, describer=None) -> dict:
    """Observe (never modify) the current pipeline's output for one paper.

    L1/L2/L4 read `MethodProfile` instead of the `conditions` strings they used to
    borrow: the old mapping scored L2 from `backbone=` and L4 from `training=`, so
    components and setup could break completely and the audit would still report
    the same numbers (design §6.7).

    `describer` is passed in, never built here: the provider and the budget belong
    to the caller (design §7.3). With a describer, L3 is genuinely measured - the
    points go through the same validator the run uses, so a point the run would
    refuse is refused here too rather than being counted as coverage.
    """
    chunks = chunk_pages(load_html(cache / f"{arxiv_id}.html"), f"sv_{arxiv_id}")
    extraction = extract_methods(chunks)
    profile = extraction.profiles[0] if extraction.profiles else None

    points = list(profile.points) if profile else []
    if describer is not None:
        attempt = describer.describe(chunks)
        if attempt.response is None:
            points, l3_cause = [], "LLM 输出被拒"
        else:
            outcome = validate_description(attempt.response, chunks)
            points = outcome.points
            # design §10.1 closes the cause set: a refused quote is "no source
            # location", a malformed answer is "output refused", and an empty
            # answer means the model said nothing - the same fact as no describer.
            if points:
                l3_cause = None
            elif outcome.reason in ("METHOD_POINT_UNLOCATABLE", "METHOD_STATEMENT_UNSUPPORTED"):
                l3_cause = "无来源定位"
            elif outcome.reason == "METHOD_DESCRIPTION_REJECTED":
                l3_cause = "LLM 输出被拒"
            else:
                l3_cause = "LLM 未启用"
    else:
        l3_cause = None if points else "LLM 未启用"


    evidence = HeuristicEvidenceExtractor().extract(chunks)
    quantitative = HeuristicQuantitativeExtractor().extract(evidence)
    claims, _ = HeuristicClaimBuilder().build(
        evidence, quantitative=quantitative, chunks=chunks
    )
    return {
        "L1": bool(profile and profile.name),
        "L1_ambiguous": bool(profile and profile.source_version_id in extraction.ambiguous),
        "L2": bool(profile and profile.components),
        "L3": bool(points),
        "L3_cause": l3_cause,
        "L4": bool(profile and setup_filled(profile.setup)),
        "proxy": sum(1 for claim in claims if _named_subject(claim)),
        "empty": not claims and not quantitative,
    }


def covered_for(layer: str, side: dict) -> bool:
    """Which observation makes a layer count as covered (design §6.7).

    Every branch reads the side, including L3: a constant there is how the layer
    stayed invisible for a whole measurement cycle.
    """
    if layer == "L1":
        return bool(side["L1"])
    if layer == "L2":
        return bool(side["L2"])
    if layer == "L3":
        return bool(side["L3"])
    if layer == "L4":
        return bool(side["L4"])
    raise ValueError(f"unknown layer: {layer}")


def cause_for(layer: str, side: dict) -> str:
    """Direct reason a present cell was not covered (design §10.1).

    A closed set: every gap gets one of these, so "unexplained uncovered" stays
    at zero and no cell can be left without a conclusion.
    """
    if side["empty"]:
        return "无来源定位"
    if layer == "L1" and side.get("L1_ambiguous"):
        return "命名歧义"
    if layer == "L3":
        # After S3 the field exists, so "no field" would be a lie. The observation
        # carries the real cause; the old string survives only for sides built
        # before the field existed (synthetic fixtures, S2 reports).
        return side.get("L3_cause") or "无结构化字段"
    # L1/L2/L4 all have a field; what failed is the pattern vocabulary reaching
    # this paper's wording.
    return "词表未覆盖"


def summarise(labels: list[dict], sides: dict[str, dict], domain_size: int | None = None) -> dict:
    """`domain_size` exists for synthetic fixtures; None derives each domain's
    size from the labels so unequal corpora cannot share a wrong denominator."""
    sizes = Counter(row["domain"] for row in labels)
    present = Counter()
    covered = Counter()
    proxy = Counter()
    ambiguous = Counter()
    gaps = Counter()
    cells = []

    for row in labels:
        arxiv_id, domain = row["arxiv_id"], row["domain"]
        side = sides[arxiv_id]
        proxy[domain] += side["proxy"]
        for layer in LAYERS:
            cell = row["layers"][layer]
            label = cell["label"]
            hit = covered_for(layer, side) and label == "present"
            if label == "present":
                present[f"{domain}|{layer}"] += 1
                if hit:
                    covered[f"{domain}|{layer}"] += 1
                else:
                    gaps[f"{domain}|{layer}|{cause_for(layer, side)}"] += 1
            elif label == "ambiguous":
                ambiguous[f"{domain}|{layer}"] += 1
            cells.append({
                "arxiv_id": arxiv_id, "domain": domain, "layer": layer,
                "label": label, "covered": bool(hit),
            })

    domains = {row["domain"] for row in labels}
    A, C, over = {}, {}, {}
    for domain in domains:
        for layer in LAYERS:
            key = f"{domain}|{layer}"
            p, c = present[key], covered[key]
            size = domain_size if domain_size is not None else sizes[domain]
            A[key] = (p, size)
            C[key] = "N/A" if p == 0 else (c, p)
            over[key] = (c, size)

    proxy_out = {d: proxy[d] for d in domains}
    proxy_out["total"] = sum(proxy.values())
    ambiguous_out = dict(ambiguous)
    ambiguous_out["total"] = sum(ambiguous.values())
    return {
        "A": A, "C": C, "covered_over_20": over,
        "gaps": dict(gaps), "proxy": proxy_out,
        "ambiguous": ambiguous_out, "cells": cells,
    }


def print_report(report: dict) -> None:
    print("=== method acquisition audit ===")
    print("A = present/domain_size   C = covered/present (N/A when present=0)")
    print("C denominators differ per cell; do not compare C across layers or domains.")
    print("Cells with present < 5 are not read as trends.")
    for key in sorted(report["A"]):
        a = report["A"][key]
        c = report["C"][key]
        c_text = "N/A" if c == "N/A" else f"{c[0]}/{c[1]}"
        o = report["covered_over_20"][key]
        size_label = f"covered/{a[1]}"
        print(f"  {key:<28} A={a[0]}/{a[1]}  C={c_text:<8} {size_label}={o[0]}/{o[1]}")
    print("\n=== gap causes ===")
    for key, count in sorted(report["gaps"].items()):
        print(f"  {key:<40} {count}")
    print("\n=== proxy (claim subject, NOT section 15 method) ===")
    print(" ", dict(report["proxy"]))
    print("=== ambiguous (excluded from every ratio) ===")
    print(" ", dict(report["ambiguous"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument(
        "--describer",
        choices=("none", "recorded"),
        default="none",
        help="recorded replays tests/fixtures/method_descriptions (design §7.6)",
    )
    args = parser.parse_args()

    labels = load_labels(args.labels, require_full_corpus=True)
    describer = None
    if args.describer == "recorded":
        from research_os.config import Settings
        from research_os.llm.factory import build_describer

        describer = build_describer(
            Settings(llm_provider="recorded", llm_fixture_dir="tests/fixtures/method_descriptions")
        )
    sides = {row["arxiv_id"]: system_side(row["arxiv_id"], args.cache, describer) for row in labels}
    report = summarise(labels, sides)
    print_report(report)


if __name__ == "__main__":
    main()
