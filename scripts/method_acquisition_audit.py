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
from research_os.research.quantitative import HeuristicQuantitativeExtractor

CACHE = Path(".holdout_cache")
LAYERS = ("L1", "L2", "L3", "L4")
LABELS = ("present", "absent", "ambiguous")
DOMAINS = ("image_restoration", "agent_in_mc")
PLACEHOLDER_METHOD = "proposed method"


def load_labels(path: Path) -> list[dict]:
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
    return rows


def _named_subject(claim) -> bool:
    if not claim.identity_key:
        return False
    subject = claim.identity_key.split("|")[0]
    return bool(subject) and not subject.startswith("self@")


def system_side(arxiv_id: str, cache: Path = CACHE) -> dict:
    """Observe (never modify) the current pipeline's output for one paper.

    `QuantitativeEvidence.protocol` deliberately does NOT appear: it stores a
    unit ("dB"/"percent"), not an evaluation protocol.
    """
    chunks = chunk_pages(load_html(cache / f"{arxiv_id}.html"), f"sv_{arxiv_id}")
    evidence = HeuristicEvidenceExtractor().extract(chunks)
    quantitative = HeuristicQuantitativeExtractor().extract(evidence)
    claims, _ = HeuristicClaimBuilder().build(
        evidence, quantitative=quantitative, chunks=chunks
    )
    conditions = [cond for claim in claims for cond in claim.conditions]
    return {
        "structured": any(
            q.method and q.method != PLACEHOLDER_METHOD for q in quantitative
        ),
        "proxy": sum(1 for claim in claims if _named_subject(claim)),
        "L2": any(cond.startswith(("backbone=", "baseline=")) for cond in conditions),
        "L4": any(cond.startswith("training=") for cond in conditions),
        "empty": not claims and not quantitative,
    }


def covered_for(layer: str, side: dict) -> bool:
    """The fixed claim-object mapping from spec section 5."""
    if layer == "L1":
        return bool(side["structured"])
    if layer == "L2":
        return bool(side["L2"])
    if layer == "L3":
        return False  # no field exists: structural absence, not an extraction error
    if layer == "L4":
        return bool(side["L4"])
    raise ValueError(f"unknown layer: {layer}")


def cause_for(layer: str, side: dict) -> str:
    """Direct reason a present cell was not covered. Three values only."""
    if side["empty"]:
        return "无来源定位"
    if layer == "L2":
        return "词表未覆盖"
    return "无结构化字段"


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
    print("C denominators differ per cell; do not compare C across layers.\n")
    for key in sorted(report["A"]):
        a = report["A"][key]
        c = report["C"][key]
        c_text = "N/A" if c == "N/A" else f"{c[0]}/{c[1]}"
        o = report["covered_over_20"][key]
        print(f"  {key:<28} A={a[0]}/{a[1]}  C={c_text:<8} covered/domain={o[0]}/{o[1]}")
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
    args = parser.parse_args()

    labels = load_labels(args.labels)
    sides = {row["arxiv_id"]: system_side(row["arxiv_id"], args.cache) for row in labels}
    report = summarise(labels, sides)
    print_report(report)


if __name__ == "__main__":
    main()
