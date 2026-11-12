"""Claim construction: identity, merge, relations (plan §16).

Grouping is by `ClaimIdentity`, never by wording similarity. Two sentences that
read alike but differ in dataset, task, metric, direction, condition or reported
value stay two claims - the plan forbids collapsing `A improves Rain100H` and
`A improves SIDD` into `A improves image restoration`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Protocol

from research_os.domain.enums import ClaimStatus, ClaimType, EvidenceRelation
from research_os.domain.models import (
    Claim,
    ClaimEvidenceRelation,
    DocumentChunk,
    Evidence,
    QuantitativeEvidence,
)
from research_os.research.claims import (
    ClaimIdentity,
    classify_claim,
    extract_identity,
    may_merge,
)
from research_os.research.scope import BlockScope, build_section_scopes

# A sentence becomes a claim candidate when it asserts something measurable, or
# when it hedges: speculation is a claim with no supporting evidence, and the memo
# must show it as such rather than silently dropping it.
_CLAIM_MARKERS = re.compile(
    r"(improve|outperform|achieve|gain|reduc|increase|enable|demonstrate|show|report|reach|"
    r"%|\bPSNR\b|\bSSIM\b|\berror\b|\baccuracy\b)",
    re.IGNORECASE,
)
_SPECULATION_MARKERS = re.compile(
    r"(we believe|believe that|suggest|hypothesiz|may\b|could\b|might\b|future work|we expect|"
    r"potentially|we hope|in principle|generalizes to other)",
    re.IGNORECASE,
)
_COMPARATIVE = re.compile(r"(improve|outperform|better|gain|surpass|exceed)", re.IGNORECASE)


class ClaimBuilder(Protocol):
    def build(
        self,
        evidence: list[Evidence],
        quantitative: list[QuantitativeEvidence] | None = None,
        chunks: list[DocumentChunk] | None = None,
    ) -> tuple[list[Claim], list[ClaimEvidenceRelation]]: ...


class HeuristicClaimBuilder:
    """Identity -> group -> one SUPPORTS relation per supporting evidence."""

    def build(
        self,
        evidence: list[Evidence],
        quantitative: list[QuantitativeEvidence] | None = None,
        chunks: list[DocumentChunk] | None = None,
    ) -> tuple[list[Claim], list[ClaimEvidenceRelation]]:
        quantitative = quantitative or []
        scopes: dict[str, BlockScope] = build_section_scopes(chunks or [])
        quant_by_evidence: dict[str, list[QuantitativeEvidence]] = defaultdict(list)
        for row in quantitative:
            quant_by_evidence[row.evidence_id].append(row)

        groups: list[dict] = []
        for item in evidence:
            text = item.text.strip()
            if not (_CLAIM_MARKERS.search(text) or _SPECULATION_MARKERS.search(text)):
                continue
            identity = extract_identity(
                text,
                source_version_id=item.source_version_id,
                scope=scopes.get(item.chunk_id or ""),
                quantitative=quant_by_evidence.get(item.id, []),
            )
            for group in groups:
                if may_merge(group["identity"], identity):
                    group["evidence"].append(item)
                    break
            else:
                groups.append({"identity": identity, "evidence": [item], "text": text})

        claims: list[Claim] = []
        relations: list[ClaimEvidenceRelation] = []
        for group in groups:
            identity: ClaimIdentity = group["identity"]
            supporting: list[Evidence] = group["evidence"]
            status, confidence, flags = classify_claim(
                group["text"], identity, supporting, quant_by_evidence
            )
            claim = Claim(
                text=group["text"],
                claim_type=(
                    ClaimType.COMPARATIVE
                    if _COMPARATIVE.search(group["text"])
                    else ClaimType.FACTUAL
                ),
                scope=identity.label() or None,
                conditions=list(identity.conditions) + flags,
                status=status,
                confidence_label=confidence,
                identity_key=identity.key(),
            )
            claims.append(claim)
            if status is ClaimStatus.UNSUPPORTED:
                continue  # speculation: nothing in the evidence supports it
            rationale = (
                f"merged by identity key: {identity.key()}"
                if len(supporting) > 1
                else "claim text derived from this evidence sentence"
            )
            for item in supporting:
                relations.append(
                    ClaimEvidenceRelation(
                        claim_id=claim.id,
                        evidence_id=item.id,
                        relation=EvidenceRelation.SUPPORTS,
                        rationale=rationale,
                    )
                )
        return claims, relations
