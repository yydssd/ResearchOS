"""Pairwise contradiction assessment over claim identity (P5 spec §4-§5).

Why the pairing key is subject+task and not dataset: the plan's own example -
"spatial conditioning helps on Rain100H with a Transformer" versus "no gain on
SIDD with a CNN" - sits on two different datasets. Requiring a dataset overlap
would make the example unpairable, and the expected answer (SCOPE_DIFFERENCE)
unreachable.

Why self subjects pair only inside one document: two papers' "our method" are
different methods; comparing them would invent a shared object that does not
exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Protocol

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim, ContradictionAssessment

MAX_PAIRS = 50_000


@dataclass
class PairingStats:
    """Everything a reader needs to tell 'no contradiction' from 'not compared'."""

    total_before_cap: int = 0
    evaluated: int = 0
    skipped_missing_dataset: int = 0
    skipped_missing_metric: int = 0
    skipped_self_prefilter: int = 0
    skipped_same_value: int = 0  # P4 should have merged these; a hit is a defect
    failed_pairs: int = 0  # assess_pair raised; distinct from any scope skip
    failed_by_error: dict[str, int] = field(default_factory=dict)  # error type -> count
    first_failure: str | None = None  # enough context to start debugging
    skipped_cap: int = 0
    emitted_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def judged(self) -> int:
        """Pairs the assessor did not raise on.

        Scope skips are included: this subtracts only pairs that failed, and is
        the denominator behind `coverage`. A pair skipped for a missing dataset
        was still attempted and still cannot produce a comparison, which is what
        coverage measures.
        """
        return max(self.evaluated - self.failed_pairs, 0)

    @property
    def coverage(self) -> float:
        return self.judged / self.total_before_cap if self.total_before_cap else 0.0


def _parts(claim: Claim) -> list[str]:
    return (claim.identity_key or "").split("|")


def _subject(claim: Claim) -> str | None:
    parts = _parts(claim)
    return (parts[0] or None) if len(parts) >= 7 else None


def _task(claim: Claim) -> str | None:
    parts = _parts(claim)
    return (parts[1] or None) if len(parts) >= 7 else None


def _datasets(claim: Claim) -> frozenset[str]:
    parts = _parts(claim)
    return frozenset(filter(None, parts[2].split(","))) if len(parts) >= 7 else frozenset()


def _metrics(claim: Claim) -> frozenset[str]:
    parts = _parts(claim)
    return frozenset(filter(None, parts[3].split(","))) if len(parts) >= 7 else frozenset()


def pair_candidates(claims: list[Claim]) -> tuple[list[tuple[Claim, Claim]], PairingStats]:
    """All comparable pairs, deterministically ordered, capped at MAX_PAIRS."""
    stats = PairingStats()
    groups: dict[tuple[str, str], list[Claim]] = {}
    for claim in claims:
        if claim.status != ClaimStatus.SUPPORTED or not claim.identity_key:
            continue
        subject, task = _subject(claim), _task(claim)
        if not subject or not task:
            continue
        groups.setdefault((task, subject), []).append(claim)

    pairs: list[tuple[Claim, Claim]] = []
    for (_, subject), group in sorted(groups.items()):
        group = sorted(group, key=lambda c: c.id)
        for a, b in combinations(group, 2):
            if subject.startswith("self@") and not (
                _datasets(a) and _metrics(a) and _datasets(b) and _metrics(b)
            ):
                stats.skipped_self_prefilter += 1
                continue
            pairs.append((a, b))

    stats.total_before_cap = len(pairs)
    if len(pairs) > MAX_PAIRS:
        stats.skipped_cap = len(pairs) - MAX_PAIRS
        pairs = pairs[:MAX_PAIRS]
    stats.evaluated = len(pairs)
    return pairs, stats


def _directions(claim: Claim) -> str | None:
    parts = _parts(claim)
    return (parts[4] or None) if len(parts) >= 7 else None


def _conditions(claim: Claim) -> tuple[str, ...]:
    parts = _parts(claim)
    return tuple(filter(None, parts[5].split(";"))) if len(parts) >= 7 else ()


def _condition_tiers(claim: Claim) -> dict[str, str]:
    """kind -> tier, read from the per-kind flags (ADR-036).

    A row written before S4 carries `conditions_from=<tier>` and no per-kind
    flags; it reads as "no confirmed kinds", which is the safe direction - an old
    measurement row must not license a TRUE_CONTRADICTION it never supported.
    """
    tiers: dict[str, str] = {}
    for item in claim.conditions:
        if item.startswith("condition_tier="):
            kind, _, tier = item.split("=", 1)[1].partition(":")
            if kind and tier:
                tiers[kind] = tier
    return tiers


def _kinds(claim: Claim) -> set[str]:
    return {item.split("=", 1)[0] for item in _conditions(claim)}


def _buckets(claim: Claim) -> tuple[str, ...]:
    parts = _parts(claim)
    return tuple(filter(None, parts[6].split(";"))) if len(parts) >= 7 else ()


OPPOSITE = {("UP", "LEVEL"), ("LEVEL", "UP"), ("UP", "DOWN"), ("DOWN", "UP"), ("DOWN", "LEVEL"), ("LEVEL", "DOWN")}

# Provenance tiers that actually prove a claim used the setup it names (HD-014).
# Anything else - including a missing tag - is not evidence of a shared setup.
_CONFIRMED_TIERS = frozenset({"sentence", "heading"})


def _assessment(a: Claim, b: Claim, relation: ContradictionType, explanation: str, confidence: ConfidenceLabel):
    return ContradictionAssessment(
        claim_a_id=a.id,
        claim_b_id=b.id,
        relationship=relation,
        explanation=explanation,
        confidence_label=confidence,
    )


def assess_pair(a: Claim, b: Claim) -> ContradictionAssessment | None:
    """Ordered cascade; first match wins. Returns None when the pair is skipped.

    The order is the plan's "default must not be TRUE_CONTRADICTION" made
    executable: dataset and conditions are facts, an opposite direction is only a
    surface clash, and a missing condition is never read as an agreeing one.
    """
    datasets_a, datasets_b = _datasets(a), _datasets(b)
    metrics_a, metrics_b = _metrics(a), _metrics(b)
    if not datasets_a or not datasets_b or not metrics_a or not metrics_b:
        return None

    direction_a, direction_b = _directions(a), _directions(b)
    same_direction = direction_a is not None and direction_a == direction_b

    if datasets_a != datasets_b:
        relation = ContradictionType.COMPLEMENTARY if same_direction else ContradictionType.SCOPE_DIFFERENCE
        return _assessment(
            a, b, relation,
            f"dataset differs: {','.join(sorted(datasets_a))} vs {','.join(sorted(datasets_b))}",
            ConfidenceLabel.MEDIUM,
        )

    conditions_a, conditions_b = _conditions(a), _conditions(b)
    if conditions_a and conditions_b and conditions_a != conditions_b:
        relation = ContradictionType.COMPLEMENTARY if same_direction else ContradictionType.SCOPE_DIFFERENCE
        return _assessment(
            a, b, relation,
            f"conditions differ: {';'.join(conditions_a)} vs {';'.join(conditions_b)}",
            ConfidenceLabel.MEDIUM,
        )

    if not (metrics_a & metrics_b):
        return _assessment(
            a, b, ContradictionType.EXPERIMENTAL_INCOMPATIBILITY,
            f"metric has no overlap: {','.join(sorted(metrics_a))} vs {','.join(sorted(metrics_b))}",
            ConfidenceLabel.MEDIUM,
        )

    if not conditions_a or not conditions_b:
        return _assessment(
            a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
            "conditions not extracted on at least one side; setup cannot be confirmed",
            ConfidenceLabel.LOW,
        )

    if direction_a is None or direction_b is None:
        missing = "A" if direction_a is None else "B"
        return _assessment(
            a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
            f"direction not stated on side {missing}",
            ConfidenceLabel.LOW,
        )

    if (direction_a, direction_b) in OPPOSITE:
        shared = _kinds(a) & _kinds(b)
        tiers_a, tiers_b = _condition_tiers(a), _condition_tiers(b)
        unconfirmed = [
            kind
            for kind in sorted(shared)
            if tiers_a.get(kind) not in _CONFIRMED_TIERS or tiers_b.get(kind) not in _CONFIRMED_TIERS
        ]
        if not shared or unconfirmed:
            reason = (
                "no condition kind is shared, so the setup cannot be the same one"
                if not shared
                else f"kind(s) {', '.join(unconfirmed)} not confirmed on both sides"
            )
            return _assessment(
                a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
                f"opposite direction, but {reason}",
                ConfidenceLabel.LOW,
            )
        return _assessment(
            a, b, ContradictionType.TRUE_CONTRADICTION,
            f"same scope, opposite direction: {direction_a} vs {direction_b}",
            ConfidenceLabel.DISPUTED,
        )

    buckets_a, buckets_b = _buckets(a), _buckets(b)
    if buckets_a and buckets_b and buckets_a != buckets_b:
        return _assessment(
            a, b, ContradictionType.EXPERIMENTAL_INCOMPATIBILITY,
            f"same scope, same direction, different values: {';'.join(buckets_a)} vs {';'.join(buckets_b)}",
            ConfidenceLabel.MEDIUM,
        )

    if not buckets_a or not buckets_b:
        # Spec §5 row 9: one side reporting no value cannot corroborate a
        # same-direction claim, so the pair is left unjudged rather than skipped.
        missing_values = "A" if not buckets_a else "B"
        return _assessment(
            a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
            f"same direction, value not reported on side {missing_values}",
            ConfidenceLabel.LOW,
        )

    return None


class ContradictionAssessor(Protocol):
    """Same shape as ClaimBuilder/EvidenceExtractor so P8 can swap in an LLM
    assessor without touching the supervisor."""

    def assess(self, claims: list[Claim]) -> tuple[list[ContradictionAssessment], PairingStats]: ...


class HeuristicContradictionAssessor:
    """Deterministic pairing plus the cascade. No LLM, no randomness."""

    def assess(self, claims: list[Claim]) -> tuple[list[ContradictionAssessment], PairingStats]:
        pairs, stats = pair_candidates(claims)
        assessments: list[ContradictionAssessment] = []
        for a, b in pairs:
            try:
                result = assess_pair(a, b)
            except Exception as exc:  # boundary: one bad pair must not stop the batch
                # Logging does not exist in this repo, so the event is the only
                # observation channel: keep the error type and one concrete pair.
                stats.failed_pairs += 1
                name = type(exc).__name__
                stats.failed_by_error[name] = stats.failed_by_error.get(name, 0) + 1
                if stats.first_failure is None:
                    detail = str(exc)
                    stats.first_failure = (
                        f"{name}: {detail[:500]}{'…' if len(detail) > 500 else ''}"
                        f" [{a.id} vs {b.id}]"
                    )
                continue
            if result is None:
                if _datasets(a) and _datasets(b) and _metrics(a) and _metrics(b):
                    # With a dataset and a metric on both sides, same direction
                    # and the same value is the only silent path left: P4 was
                    # supposed to merge that pair, so a hit is a defect and is
                    # counted rather than hidden.
                    stats.skipped_same_value += 1
                elif not _datasets(a) or not _datasets(b):
                    stats.skipped_missing_dataset += 1
                else:
                    stats.skipped_missing_metric += 1
                continue
            assessments.append(result)
            stats.emitted_by_type[result.relationship.value] = (
                stats.emitted_by_type.get(result.relationship.value, 0) + 1
            )
        # `evaluated` is already set by pair_candidates; re-assigning here would
        # be a dead store that silently hides a future divergence.
        return assessments, stats
