"""Claim identity and status: what makes two claims "the same claim" (plan §16).

Deterministic only - no LLM. Identity is what the merge gate compares, so every
field is either confidently extracted or None, and `may_merge` refuses to merge
on unknowns: "unknown" is not "identical".

Two rules learned the hard way on real papers (see P4 spec §2):
- the subject lives in the clause before the predicate, otherwise "the model" in
  "the gating mechanism enables the model" is taken for the subject;
- `subject` is bound to its source version when it is the paper's own method, so
  "our method" from two different papers can never be one claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from research_os.domain.enums import ClaimStatus, ConfidenceLabel
from research_os.domain.models import QuantitativeEvidence
from research_os.research.lexicon import DATASETS, METRICS, THIRD_PARTY
from research_os.research.scope import BlockScope

# The verb that separates subject from object. Deliberately narrow: a broad verb
# list picks up "the blur is approximated by", which has no real subject.
PREDICATE = re.compile(
    r"\b(improves?|improved|outperforms?|outperformed|achieves?|achieved|gains?|gained|"
    r"reduces?|reduced|increases?|increased|surpass(?:es|ed)?|enables?|yields?|"
    r"reports?|reported|reaches?|demonstrates?)\b",
    re.IGNORECASE,
)
SELF_REFERENCE = re.compile(
    r"\b(?:our\s+(?:method|approach|model|framework|network|system|proposed)|"
    r"we\s+propose|this\s+paper\s+proposes|the\s+(?:proposed\s+)?(?:method|model|approach|network))\b",
    re.IGNORECASE,
)
# Capitalised words that are never a method name (sentence openers, meta nouns).
COMMON_CAPS = frozenset(
    {
        "the", "this", "that", "these", "those", "on", "in", "for", "with", "we", "our",
        "however", "specifically", "although", "to", "it", "both", "have", "link", "results",
        "result", "experiments", "experimental", "table", "figure", "figures", "abstract",
        "authors", "moreover", "therefore", "thus", "as", "at", "by", "from", "and", "but",
        "while", "recently", "since", "given", "compared", "unlike", "among", "notably",
        "finally", "significant", "similarly", "overall", "first", "second", "third",
    }
)
DIRECTION_UP = re.compile(
    r"\b(improv\w*|gain\w*|outperform\w*|better|surpass\w*|exceed\w*|reduc\w*|increas\w*)",
    re.IGNORECASE,
)
DIRECTION_LEVEL = re.compile(r"\b(achiev\w*|reach\w*|report\w*)", re.IGNORECASE)
CONDITION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(cnn|transformer|convolutional)\b\s+backbone", re.IGNORECASE), "backbone"),
    (re.compile(r"\b(synthetic|real[- ]world)\b", re.IGNORECASE), "setting"),
    (re.compile(r"\b(video|single[- ]image)\b", re.IGNORECASE), "granularity"),
)
_BUCKET_DIGITS = {"PSNR": 2, "SSIM": 3, "LPIPS": 3, "FID": 1, "MAE": 2, "MSE": 2}


@dataclass(frozen=True)
class ClaimIdentity:
    """The dimension vector a merge decision is made on."""

    subject: str | None
    task: str | None
    dataset: frozenset[str]
    metric: frozenset[str]
    direction: str | None
    conditions: tuple[str, ...]
    value_bucket: tuple[str, ...]

    def key(self) -> str:
        dataset = ",".join(sorted(d.lower() for d in self.dataset))
        metric = ",".join(sorted(m.lower() for m in self.metric))
        return (
            f"{self.subject}|{self.task}|{dataset}|{metric}|{self.direction}"
            f"|{';'.join(self.conditions)}|{';'.join(self.value_bucket)}"
        )

    def label(self) -> str:
        """Human-readable scope, shown in the memo and `claims`."""
        parts = [
            self.task,
            ", ".join(sorted(self.dataset)),
            ", ".join(sorted(self.metric)),
            self.direction,
        ]
        return " · ".join(part for part in parts if part)


def _subject(text: str) -> str | None:
    """Subject of the claim: a named method, or the sentinel `self`."""
    match = PREDICATE.search(text)
    prefix = text[: match.start()] if match else text
    if SELF_REFERENCE.search(prefix):
        return "self"
    dataset_words = {d.lower() for d in DATASETS}
    metric_words = {m.lower() for m in METRICS}
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]*", prefix):
        low = token.lower()
        if low in COMMON_CAPS or low in dataset_words or low in metric_words:
            continue
        looks_named = (
            any(char.isupper() for char in token[1:])  # SwinIR, NAFNet
            or (token.isupper() and len(token) >= 2)  # BSRGAN, CNN
            or any(char.isdigit() for char in token)  # Rain100H
            or (token[0].isupper() and len(token) >= 6)  # Restormer
        )
        if looks_named:
            return low
    return None


def _conditions(text: str) -> tuple[str, ...]:
    found = []
    for pattern, name in CONDITION_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(f"{name}={match.group(1).lower().replace(' ', '-')}")
    return tuple(sorted(found))


def _buckets(quantitative: list[QuantitativeEvidence]) -> tuple[str, ...]:
    buckets = []
    for row in quantitative:
        if row.metric and row.value is not None:
            digits = _BUCKET_DIGITS.get(row.metric.upper(), 1)
            buckets.append(f"{row.metric.lower()}={round(row.value, digits)}")
        elif row.delta is not None:
            buckets.append(f"{row.protocol or 'unit'}:{round(row.delta, 2)}")
    return tuple(sorted(set(buckets)))


def extract_identity(
    text: str,
    *,
    source_version_id: str,
    scope: BlockScope | None,
    quantitative: list[QuantitativeEvidence],
) -> ClaimIdentity:
    low = text.lower()
    datasets = {d for d in DATASETS if d.lower() in low}
    metrics = {m for m in METRICS if re.search(rf"\b{m}\b", text, re.IGNORECASE)}
    task: str | None = None
    if scope is not None:
        datasets = datasets or set(scope.datasets)
        task = scope.task
    subject = _subject(text)
    if subject is None and (task or datasets or metrics) and not THIRD_PARTY.search(text):
        # In the paper's own evaluation prose the implicit subject is its method.
        subject = "self"
    if subject == "self":
        subject = f"self@{source_version_id}"
    direction = (
        "UP"
        if DIRECTION_UP.search(text)
        else ("LEVEL" if DIRECTION_LEVEL.search(text) else None)
    )
    return ClaimIdentity(
        subject=subject,
        task=task,
        dataset=frozenset(datasets),
        metric=frozenset(metrics),
        direction=direction,
        conditions=_conditions(text),
        value_bucket=_buckets(quantitative),
    )


def mergeable(identity: ClaimIdentity) -> bool:
    """Plan §16: only merge when the scope is fully determined.

    Without this gate two sentences whose dataset could not be extracted would
    merge on `None == None`, which is exactly the "A improves image restoration"
    degeneration the plan forbids.
    """
    return bool(identity.subject and identity.dataset and identity.direction)


def may_merge(a: ClaimIdentity, b: ClaimIdentity) -> bool:
    if not (mergeable(a) and mergeable(b)):
        return False
    if a.value_bucket != b.value_bucket:
        return False  # different reported values are P5's input, not a duplicate
    return a.key() == b.key()


SPECULATION = re.compile(
    r"(we believe|believe that|suggest|hypothesiz|may |could |might |future work|"
    r"we expect|potentially|we hope|in principle|generalizes to other)",
    re.IGNORECASE,
)
VALUE_WITH_UNIT = re.compile(r"\d+(?:\.\d+)?\s?(dB|%|percent|×)\b", re.IGNORECASE)
COMPARATIVE = re.compile(r"\b(outperform\w*|better than|surpass\w*|state-of-the-art|sota)\b", re.IGNORECASE)
CONTROL = re.compile(r"\b(compared (?:with|to)|than|versus|vs\.?)\b", re.IGNORECASE)


def classify_claim(
    text: str,
    identity: ClaimIdentity,
    evidence: list[object],
    quant_by_evidence: dict[str, list[QuantitativeEvidence]],
) -> tuple[ClaimStatus, ConfidenceLabel, list[str]]:
    """(status, confidence, flags) for one claim.

    `UNSUPPORTED` means "no supporting evidence" and nothing else. A claim whose
    evidence exists but whose numbers are unstructured, out of scope, or
    unchecked stays SUPPORTED at LOW confidence with a named flag - otherwise
    "unsupported" silently degrades into a synonym for "low confidence"
    (P4 spec §8).
    """
    if SPECULATION.search(text):
        return ClaimStatus.UNSUPPORTED, ConfidenceLabel.LOW, []

    flags: list[str] = []
    has_value = bool(VALUE_WITH_UNIT.search(text))
    grounded = any(
        quant_by_evidence.get(getattr(item, "id", ""), []) for item in evidence
    )
    if has_value and not grounded:
        flags.append("quantitative_unstructured")
    if has_value and not identity.dataset and not identity.metric:
        flags.append("scope_undetermined")
    if COMPARATIVE.search(text) and not CONTROL.search(text) and not grounded:
        flags.append("comparative_unsubstantiated")
    confidence = ConfidenceLabel.LOW if flags else ConfidenceLabel.MEDIUM
    return ClaimStatus.SUPPORTED, confidence, flags
