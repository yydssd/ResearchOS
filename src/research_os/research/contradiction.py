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

from research_os.domain.enums import ClaimStatus
from research_os.domain.models import Claim

MAX_PAIRS = 50_000


@dataclass
class PairingStats:
    """Everything a reader needs to tell 'no contradiction' from 'not compared'."""

    total_before_cap: int = 0
    evaluated: int = 0
    skipped_missing_dataset: int = 0
    skipped_missing_metric: int = 0
    skipped_self_prefilter: int = 0
    skipped_cap: int = 0
    emitted_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return self.evaluated / self.total_before_cap if self.total_before_cap else 0.0


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
