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
from dataclasses import dataclass, field

from research_os.domain.enums import ClaimStatus, ConfidenceLabel
from research_os.domain.models import QuantitativeEvidence
from research_os.research.conditions import extract_conditions
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
    r"we\s+propose|this\s+paper\s+proposes|proposed\s+(?:method|model|approach|network)|"
    r"the\s+(?:proposed\s+)?(?:method|model|approach|network))\b",
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

# Units and metric names are never subjects. `dB` is the reason this exists: its
# inner capital satisfied the proper-noun test, so `db` was read as a method
# name in 9 of the 20 hold-out papers.
NOT_A_SUBJECT = frozenset(
    {"db", "psnr", "ssim", "lpips", "fid", "mae", "mse", "percent", "%", "×"}
)
# Direction is the claim's conclusion about quality, not the raw movement of the
# number: "reduces error" is an improvement, "reduces PSNR" is not, and "reports
# 39.18 dB" asserts no direction at all. The old three-value scheme put
# achiev/reach/report into LEVEL, which made "improves PSNR" and "reports 30 dB"
# look like opposites (196 of 196 LEVEL claims on the hold-out were of that kind).
_IMPROVE = re.compile(
    r"\b(improv\w*|gain\w*|outperform\w*|better|surpass\w*|exceed\w*|raises?)\b", re.IGNORECASE
)
# `lowers`/`lowered` only: the adjective ("the lower layers") must not read as a
# degradation verb, which is why the pattern is not a bare `lower\w*`.
_DEGRADE = re.compile(
    r"\b(degrades?|drops?|worse|hurts?|fails? on|lowers|lowered|lowering)\b", re.IGNORECASE
)
_NO_GAIN = re.compile(
    r"\b(no (?:clear |significant )?(?:gain|improvement|difference)|"
    r"fails? to improv\w*|does not improv\w*|without (?:any )?improvement|"
    r"on par with|comparable to|"
    r"unchanged|no change|(?:stays?|remains?|leaves?) (?:the )?(?:same|unchanged))\b",
    re.IGNORECASE,
)
_ERROR_SIDE = r"(?:error|loss|noise|artifact\w*|complexity|params|parameters)"
_QUALITY_SIDE = r"(?:psnr|ssim|accuracy|performance|quality)"
_REDUCE_LOWERS_ERROR = re.compile(rf"\breduc\w*\s+(?:the\s+)?{_ERROR_SIDE}\b", re.IGNORECASE)
_REDUCE_LOWERS_QUALITY = re.compile(rf"\breduc\w*\s+(?:the\s+)?{_QUALITY_SIDE}\b", re.IGNORECASE)
_INCREASE_RAISES_QUALITY = re.compile(rf"\bincreas\w*\s+(?:the\s+)?{_QUALITY_SIDE}\b", re.IGNORECASE)
_INCREASE_RAISES_ERROR = re.compile(rf"\bincreas\w*\s+(?:the\s+)?{_ERROR_SIDE}\b", re.IGNORECASE)
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
    # Provenance, not identity: `self` was inferred from an explicit
    # self-reference ("our method") or defaulted from the surrounding scope.
    # Downstream needs the difference; the merge key must not see it.
    subject_inferred: bool = field(default=False, compare=False)
    # Provenance of the conditions tuple: "sentence", "heading",
    # "section-first-mention", or None. Excluded from the key for the same reason
    # as subject_inferred: it says where the value came from, not what it is.
    conditions_from: str | None = field(default=None, compare=False)

    def key(self) -> str:
        """Stable, parseable identity string: missing fields render as empty.

        `str(None)` would put the literal "None" in the key, which is
        indistinguishable from a method actually named "None" and forces every
        reader to special-case it.
        """
        dataset = ",".join(sorted(d.lower() for d in self.dataset))
        metric = ",".join(sorted(m.lower() for m in self.metric))
        return "|".join(
            [
                self.subject or "",
                self.task or "",
                dataset,
                metric,
                self.direction or "",
                ";".join(self.conditions),
                ";".join(self.value_bucket),
            ]
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


def _subject(text: str) -> tuple[str | None, bool]:
    """Subject of the claim: a named method, or the sentinel `self`.

    Returns `(subject, inferred)` so callers can tell "our method" from a subject
    defaulted out of the surrounding scope.

    Two filters earn their keep on real full text: a capitalised word at the very
    start of the sentence is grammar, not a proper noun ("Motivated experiments show
    ..."), and a name may appear anywhere in the clause, not only at its start
    ("The results show that Restormer improves ...").
    """
    match = PREDICATE.search(text)
    prefix = text[: match.start()] if match else text
    if SELF_REFERENCE.search(prefix):
        return "self", False
    dataset_words = {d.lower() for d in DATASETS}
    metric_words = {m.lower() for m in METRICS}
    sentence_start = len(prefix) - len(prefix.lstrip())
    for token_match in re.finditer(r"[A-Za-z][A-Za-z0-9\-]*", prefix):
        token = token_match.group(0)
        low = token.lower()
        if (
            low in COMMON_CAPS
            or low in dataset_words
            or low in metric_words
            or low in NOT_A_SUBJECT
        ):
            continue
        has_inner_caps = any(char.isupper() for char in token[1:])
        is_acronym = token.isupper() and len(token) >= 2
        has_digit = any(char.isdigit() for char in token)
        if token_match.start() == sentence_start and not (has_inner_caps or is_acronym or has_digit):
            continue  # sentence-initial capitalisation proves nothing
        looks_named = has_inner_caps or is_acronym or has_digit or (token[0].isupper() and len(token) >= 6)
        if looks_named:
            return low, False
    return None, False


def _conditions(text: str, scope: BlockScope | None) -> tuple[tuple[str, ...], str | None]:
    """Sentence conditions win; otherwise inherit the section's, with provenance."""
    own = extract_conditions(text)
    if own:
        return own, "sentence"
    if scope is not None and scope.conditions:
        return scope.conditions, scope.inherited_from.get("conditions")
    return (), None


def _direction(text: str) -> str | None:
    """UP / DOWN / LEVEL / None. Negation is checked first so that
    "fails to improve" is LEVEL rather than UP."""
    if _NO_GAIN.search(text):
        return "LEVEL"
    if _DEGRADE.search(text) or _REDUCE_LOWERS_QUALITY.search(text) or _INCREASE_RAISES_ERROR.search(text):
        return "DOWN"
    if _IMPROVE.search(text) or _REDUCE_LOWERS_ERROR.search(text) or _INCREASE_RAISES_QUALITY.search(text):
        return "UP"
    return None


def _buckets(quantitative: list[QuantitativeEvidence]) -> tuple[str, ...]:
    buckets = []
    for row in quantitative:
        if row.metric and row.value is not None:
            digits = _BUCKET_DIGITS.get(row.metric.upper(), 1)
            buckets.append(f"{row.metric.lower()}={round(row.value, digits)}")
        elif row.delta is not None:
            buckets.append(f"{row.unit or 'unit'}:{round(row.delta, 2)}")
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
    subject, inferred = _subject(text)
    if subject is None and (task or datasets or metrics) and not THIRD_PARTY.search(text):
        # In the paper's own evaluation prose the implicit subject is its method.
        subject = "self"
        inferred = True
    if subject == "self":
        subject = f"self@{source_version_id}"
    direction = _direction(text)
    conditions, conditions_from = _conditions(text, scope)
    return ClaimIdentity(
        subject=subject,
        task=task,
        dataset=frozenset(datasets),
        metric=frozenset(metrics),
        direction=direction,
        conditions=conditions,
        value_bucket=_buckets(quantitative),
        subject_inferred=inferred,
        conditions_from=conditions_from,
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
