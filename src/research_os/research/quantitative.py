"""Deterministic quantitative evidence extraction (plan §15).

Why deterministic: extracting "PSNR 39.18 on SIDD" is pattern matching, not
semantic judgment (invariant 2.5). The value of the structure is that these rows
can later be grouped by dataset+metric, which is what stops a paper from being
"compared" against another paper evaluated on a different dataset.

Deliberately conservative: no metric word, or no numeric value near it, means no
record. A wrong number is worse than a missing one here.
"""

from __future__ import annotations

import re
from typing import Protocol

from research_os.domain.models import Evidence, QuantitativeEvidence
from research_os.research.claims import COMMON_CAPS, NOT_A_SUBJECT, SELF_REFERENCE
from research_os.research.lexicon import DATASETS, METRICS

_METRIC_RE = re.compile(r"\b(" + "|".join(METRICS) + r")\b", re.IGNORECASE)
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")
# A value is only attributed to a metric when it sits close to it; "PSNR 39.18"
# and "39.18 dB PSNR" are both legitimate, a number in the next clause is not.
_NEAR_WINDOW = 16
_RANGE_RE = re.compile(r"from\s+(\d+(?:\.\d+)?)\s*(?:dB|%|)\s*to\s+(\d+(?:\.\d+)?)")
_COMPARATOR_RE = re.compile(r"(?:for|than)\s+the\s+([a-z][a-z0-9 \-]{2,30})", re.IGNORECASE)
_PROPOSED_RE = re.compile(r"\b(?:our|the proposed)\s+(?:method|model|approach)\b", re.IGNORECASE)
_DATASET_INLINE = re.compile(r"\bon (?:the )?([A-Z][A-Za-z0-9\-]{2,})")

# The verb that separates a subject from its object, imported in spirit from
# claims.PREDICATE: duplicated here because the quantitative reader must not
# depend on claim-building behaviour changing under it.
_PREDICATE_RE = re.compile(
    r"\b(improves?|improved|outperforms?|achieves?|gains?|reduces?|increases?|"
    r"surpass(?:es|ed)?|enables?|yields?|reports?|reaches?|demonstrates?)\b",
    re.IGNORECASE,
)

# Delta pass (P4 spec §7). Most result sentences state a gain without naming the
# metric ("+0.44 dB", "a 0.11 dB improvement"), so requiring a metric word would
# leave 78% of value-bearing sentences with no structured fact at all.
_DELTA_WORD = re.compile(r"(gain|improv|increas|reduc|margin|boost|better)", re.IGNORECASE)
_DELTA_VALUE = re.compile(r"(?P<sign>[+\-−])?\s*(?P<value>\d+(?:\.\d+)?)\s?(?P<unit>dB|%)\b", re.IGNORECASE)
_DELTA_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s?dB\s*(?:to|→)\s*(\d+(?:\.\d+)?)\s?dB", re.IGNORECASE
)


def _dataset(text: str) -> str | None:
    lowered = text.lower()
    for name in DATASETS:
        if name.lower() in lowered:
            return name
    inline = _DATASET_INLINE.search(text)
    return inline.group(1) if inline else None


def _numbers(segment: str, base_offset: int) -> list[tuple[int, int, float]]:
    """Numbers in a slice with absolute offsets.

    A match glued to a preceding digit is dropped: the slice may start in the
    middle of a number ("9.18" out of "39.18"), and a truncated value is worse
    than no value.
    """
    found: list[tuple[int, int, float]] = []
    for match in _NUMBER.finditer(segment):
        if match.start() > 0 and segment[match.start() - 1].isdigit():
            continue
        found.append((base_offset + match.start(), base_offset + match.end(), float(match.group(1))))
    return found


def _nearest_number(text: str, metric_start: int, metric_end: int) -> tuple[float, int, int] | None:
    """Value closest to the metric token, with its span.

    Distance decides, because both orders occur in real papers: "39.18 dB PSNR"
    (value before) and "PSNR by 0.42 dB" (value after). Comparing distances is
    what keeps the comparator's number ("compared with 39.01") from being taken
    as the result.
    """
    after_base = metric_end
    after = _numbers(text[after_base : after_base + _NEAR_WINDOW + 12], after_base)
    before_base = max(0, metric_start - _NEAR_WINDOW - 12)
    before = _numbers(text[before_base:metric_start], before_base)

    candidates: list[tuple[int, float, int, int]] = []
    for start, end, value in after:
        distance = start - metric_end
        if distance <= _NEAR_WINDOW:
            candidates.append((distance, value, start, end))
    for start, end, value in before:
        distance = metric_start - end
        if distance <= _NEAR_WINDOW:
            candidates.append((distance, value, start, end))
    if not candidates:
        return None
    # Ties prefer the value after the metric ("PSNR 39.18").
    candidates.sort(key=lambda item: (item[0], 0))
    _, value, start, end = candidates[0]
    return value, start, end


def _unit_near(text: str, value_end: int) -> str | None:
    """Unit attached to *this* value, not to the sentence as a whole.

    A sentence can report "PSNR by 0.42 dB and SSIM by 0.013"; giving both the
    "dB" unit would silently mislabel the SSIM number.
    """
    tail = text[value_end : value_end + 6]
    if re.search(r"\bdB\b", tail, re.IGNORECASE):
        return "dB"
    if "%" in tail:
        return "percent"
    return None


_NAMED_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9\-]{2,})\b")
_EXCLUDED_NAMES = (
    frozenset(word.lower() for word in COMMON_CAPS)
    | frozenset(name.lower() for name in DATASETS)
    | frozenset(metric.lower() for metric in METRICS)
    | NOT_A_SUBJECT
)


def _named_method(text: str, predicate_start: int) -> str | None:
    """The method named before the predicate, verbatim.

    Verbatim because `method` is read by a human and compared against the paper:
    lowercasing here would make "LangProp" and "langprop" look like two methods.

    Two ordering rules, both measured on the hold-out set:

    - Only the clause before the predicate counts ("... by 0.42 dB on SIDD" is a
      dataset, not a method), and the **nearest** candidate wins. A subject head
      sits next to its predicate; a sentence-initial opener does not
      ("Introducing a small weight ... increases PSNR" used to hand back
      "Introducing").
    - A sentence-initial `-ing` word is never a name: "Training improves PSNR"
      would otherwise be read as a method called Training.
    """
    prefix = text[:predicate_start]
    sentence_start = len(prefix) - len(prefix.lstrip())
    for match in reversed(list(_NAMED_TOKEN.finditer(prefix))):
        token = match.group(1)
        if token.lower() in _EXCLUDED_NAMES:
            continue
        if not token[-1].isalnum():
            continue  # "Multi-" is a fragment cut by the token class
        if match.start() == sentence_start and token.lower().endswith("ing"):
            continue
        has_inner_caps = any(char.isupper() for char in token[1:])
        is_acronym = token.isupper() and len(token) >= 2
        has_digit = any(char.isdigit() for char in token)
        if has_inner_caps or is_acronym or has_digit or (token[0].isupper() and len(token) >= 6):
            return token
    return None


class QuantitativeExtractor(Protocol):
    def extract(
        self, evidence: list[Evidence], method_names: dict[str, str] | None = None
    ) -> list[QuantitativeEvidence]: ...


def _delta_fact(
    text: str,
    evidence_id: str,
    dataset: str | None,
    comparator: str | None,
    method: str | None,
) -> QuantitativeEvidence | None:
    """A gain stated as "+0.44 dB" / "a 0.11 dB improvement", with no metric name.

    Only called when the metric pass produced nothing, otherwise the same number
    would be stored twice (once attributed to PSNR, once as a delta).
    A gain word is required: "0.42 dB" on its own is an absolute measurement.
    """
    if not _DELTA_WORD.search(text):
        return None
    match = _DELTA_VALUE.search(text)
    if match is None:
        return None
    low, high = None, None
    span = _DELTA_RANGE.search(text)
    if span is not None:
        low, high = float(span.group(1)), float(span.group(2))
    return QuantitativeEvidence(
        evidence_id=evidence_id,
        seq=0,
        dataset=dataset,
        metric=None,
        method=method,
        value=high,
        comparator=comparator,
        comparator_value=low,
        unit="dB" if match.group("unit").lower() == "db" else "percent",
        delta=float(match.group("value")),
    )


class HeuristicQuantitativeExtractor:
    """Regex extraction of metric/value/dataset/comparator per evidence sentence."""

    def extract_from_text(
        self, text: str, evidence_id: str, method_name: str | None = None
    ) -> list[QuantitativeEvidence]:
        facts: list[QuantitativeEvidence] = []
        sentence_range = _RANGE_RE.search(text)
        dataset = _dataset(text)
        comparator_match = _COMPARATOR_RE.search(text)
        comparator = comparator_match.group(1).strip() if comparator_match else None
        # The row's method: a named third-party method wins, because the sentence
        # is about it; otherwise the paper's own name, and only then the constant
        # placeholder (design §10.3).
        predicate = _PREDICATE_RE.search(text)
        named = _named_method(text, predicate.start()) if predicate else None
        if named is not None:
            method = named
        elif SELF_REFERENCE.search(text) or _PROPOSED_RE.search(text):
            method = method_name or "proposed method"
        else:
            method = None

        seen: set[str] = set()
        for match in _METRIC_RE.finditer(text):
            metric = match.group(1).upper()
            if metric in seen:
                continue
            seen.add(metric)

            comparator_value = None
            if sentence_range:
                value = float(sentence_range.group(2))
                value_end = sentence_range.end(2)
                comparator_value = float(sentence_range.group(1))
            else:
                nearest = _nearest_number(text, match.start(), match.end())
                if nearest is None:
                    continue
                value, _value_start, value_end = nearest
                compared = re.search(
                    r"compared\s+(?:with|to)\s+(\d+(?:\.\d+)?)", text[match.end() :], re.IGNORECASE
                )
                if compared:
                    comparator_value = float(compared.group(1))

            facts.append(
                QuantitativeEvidence(
                    evidence_id=evidence_id,
                    seq=len(facts),
                    dataset=dataset,
                    metric=metric,
                    method=method,
                    value=value,
                    comparator=comparator,
                    comparator_value=comparator_value,
                    unit=_unit_near(text, value_end),
                )
            )
        if not facts:
            delta_fact = _delta_fact(text, evidence_id, dataset, comparator, method)
            if delta_fact is not None:
                facts.append(delta_fact)
        return facts

    def extract(
        self, evidence: list[Evidence], method_names: dict[str, str] | None = None
    ) -> list[QuantitativeEvidence]:
        method_names = method_names or {}
        facts: list[QuantitativeEvidence] = []
        for ev in evidence:
            facts.extend(
                self.extract_from_text(ev.text, ev.id, method_name=method_names.get(ev.source_version_id))
            )
        return facts
