"""Claim construction.

Deterministic heuristic for Week 1: claim-like sentences become candidate
claims; speculation sentences become UNSUPPORTED claims. The LLM-backed
normalizer plugs in later through the same interface.
"""

from __future__ import annotations

import re
from typing import Protocol

from research_os.domain.enums import ClaimStatus, ClaimType, ConfidenceLabel, EvidenceRelation
from research_os.domain.models import Claim, ClaimEvidenceRelation, Evidence, new_id

_CLAIM_MARKERS = re.compile(
    r"(improve|outperform|achieve|gain|reduc|increase|enable|demonstrate|show|report|reach|"
    r"%|\bPSNR\b|\bSSIM\b|\berror\b|\baccuracy\b)",
    re.IGNORECASE,
)
_SPECULATION_MARKERS = re.compile(
    r"(we believe|believe that|suggest|hypothesiz|may |could |might |future work|we expect|potentially|"
    r"we hope|in principle|generalizes to other)",
    re.IGNORECASE,
)
_DATASETS = [
    "Rain100H",
    "Rain100L",
    "SIDD",
    "DND",
    "GoPro",
    "REDS",
    "ImageNet",
    "COCO",
    "CIFAR-10",
    "CIFAR-100",
    "BSD",
    "Set5",
    "Set14",
    "Urban100",
    "Manga109",
    "Cityscapes",
]


class ClaimBuilder(Protocol):
    def build(self, evidence: list[Evidence]) -> tuple[list[Claim], list[ClaimEvidenceRelation]]: ...


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_scope(text: str) -> str | None:
    hits = [d for d in _DATASETS if d.lower() in text.lower()]
    if hits:
        return ", ".join(hits)
    # fall back to any all-caps acronym-like token
    m = re.search(r"\b[A-Z][A-Z0-9]{2,}\b", text)
    return m.group(0) if m else None


class HeuristicClaimBuilder:
    def build(self, evidence: list[Evidence]) -> tuple[list[Claim], list[ClaimEvidenceRelation]]:
        claims: list[Claim] = []
        relations: list[ClaimEvidenceRelation] = []
        seen_claims: set[str] = set()

        for ev in evidence:
            text = ev.text.strip()
            key = _normalize(text)
            if key in seen_claims:
                continue
            if _SPECULATION_MARKERS.search(text):
                claim = Claim(
                    text=text,
                    claim_type=ClaimType.MECHANISTIC,
                    scope=_extract_scope(text),
                    status=ClaimStatus.UNSUPPORTED,
                    confidence_label=ConfidenceLabel.LOW,
                )
                seen_claims.add(key)
                claims.append(claim)
                continue
            if _CLAIM_MARKERS.search(text):
                claim = Claim(
                    text=text,
                    claim_type=ClaimType.COMPARATIVE if re.search(r"(improve|outperform|better|gain)", text, re.I)
                    else ClaimType.FACTUAL,
                    scope=_extract_scope(text),
                    status=ClaimStatus.SUPPORTED,
                    confidence_label=ConfidenceLabel.MEDIUM,
                )
                seen_claims.add(key)
                claims.append(claim)
                relations.append(
                    ClaimEvidenceRelation(
                        claim_id=claim.id,
                        evidence_id=ev.id,
                        relation=EvidenceRelation.SUPPORTS,
                        rationale="heuristic: claim text is directly derived from this evidence sentence",
                    )
                )
        return claims, relations
