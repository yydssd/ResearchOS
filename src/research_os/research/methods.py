"""Deterministic method acquisition: name, components, setup (design §6).

L1/L2/L4 are pattern matching, so they stay deterministic (invariant 2.5). Only
the L3 description needs an LLM, and that is S3; the `MethodDescriber` protocol
lands here later without changing this module's shape.

Two properties are load-bearing:

- A field is either confidently extracted or absent. No guessing, because a wrong
  method name would be attributed to every quantitative row of the paper.
- `missing_layers` is computed here, not by the caller: "the paper has no L3" has
  to reach the database as a fact, or an empty field and a failed extraction stay
  indistinguishable (design §4.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from research_os.domain.models import DocumentChunk, MethodProfile, MethodSetup
from research_os.research.claims import COMMON_CAPS, NOT_A_SUBJECT
from research_os.research.evidence_extractor import sentence_spans
from research_os.research.lexicon import DATASETS, METRICS
from research_os.research.patterns import (
    COMPONENT_PHRASES,
    COMPONENT_TAILS,
    COMPONENT_WORDS,
    EVAL_PROTOCOL,
    HYPERPARAMETERS,
    NAME_CONSTRUCTIONS,
    PREDICATES,
    GENERIC_NOUNS,
    REPOSITORY_URL,
    SCALE_GPU,
    SCALE_PARAMS,
    domain_patterns,
)

# Source tiers: the abstract is where a paper states the name it wants to be
# known by, and a conclusion mention is usually a recap. Everything else ranks
# last, which is still better than no candidate at all.
_TIERS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("abstract",), 0),
    (("introduction", "intro"), 1),
    (("method", "approach", "proposed"), 2),
    (("conclusion", "discussion", "result", "experiment"), 3),
)
_UNKNOWN_TIER = 4

# Words that cannot be the start of a component noun phrase.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "our", "its", "this", "these", "that", "their", "and",
        "or", "of", "for", "with", "in", "on", "to", "by", "as", "is", "are",
        "was", "were", "we", "it", "which", "each", "every", "one", "two",
        "three", "per", "same", "new", "single", "into", "from", "than", "then",
        "uses", "use", "using", "based", "via", "at", "be", "has", "have",
    }
)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")
_MAX_MODIFIERS = 2

_EXCLUDED_NAMES: frozenset[str] = (
    PREDICATES
    | GENERIC_NOUNS
    | frozenset(word.lower() for word in COMMON_CAPS)
    | frozenset(name.lower() for name in DATASETS)
    | frozenset(metric.lower() for metric in METRICS)
    | NOT_A_SUBJECT
)


@dataclass(frozen=True)
class MethodExtraction:
    """Profiles plus what only the caller can persist.

    The two event kinds (ambiguous name, multiple names) are facts *about* the
    extraction that the profile model has no room for; returning them keeps the
    "never invent state" rule while letting the supervisor log them (design §7.5
    classifies both as ordinary events, not failures).
    """

    profiles: list[MethodProfile]
    ambiguous: dict[str, tuple[str, ...]] = field(default_factory=dict)


class MethodExtractor(Protocol):
    def extract(self, chunks: list[DocumentChunk], domain: str | None = None) -> MethodExtraction: ...


def _tier(section: str | None) -> int:
    low = (section or "").lower()
    for needles, tier in _TIERS:
        if any(needle in low for needle in needles):
            return tier
    return _UNKNOWN_TIER


def _sentence_initial(text: str, position: int) -> bool:
    """True when *position* is the first visible character of its sentence."""
    head = text[:position]
    boundary = max(head.rfind(". "), head.rfind("! "), head.rfind("? "), head.rfind("\n"))
    start = boundary + 1
    return not text[start:position].strip()


def _quote_for(text: str, start: int, end: int) -> str:
    """The sentence containing the match, verbatim from the chunk.

    Verbatim matters: `name_quote` is the reader's only way to check that the
    name really appears where the row claims (plan §2.2).
    """
    for span_start, span_end, sentence in sentence_spans(text):
        if span_start <= start and end <= span_end:
            return sentence
    return text[start:end]


def _acceptable(name: str, *, at_start: bool, construction: str) -> bool:
    low = name.lower()
    if low in _EXCLUDED_NAMES:
        return False
    if not name[-1].isalnum():
        # "we propose Multi-<tau> Liquid-Mamba" hands back "Multi-": the token
        # class cut the tail, so the capture is a fragment, not a name.
        return False
    if not at_start or construction == "apposition":
        # The apposition form ("X, our method") is itself the evidence, and X is
        # sentence-initial by construction — the one documented exception to the
        # claims.py:169 rule.
        return True
    # Sentence-initial capitalisation proves nothing on its own; inner caps,
    # acronym shape or a digit do (claims.py:169).
    has_inner_caps = any(char.isupper() for char in name[1:])
    is_acronym = name.isupper() and len(name) >= 2
    has_digit = any(char.isdigit() for char in name)
    return has_inner_caps or is_acronym or has_digit


def _continues_a_longer_name(text: str, end: int) -> bool:
    """True when the match runs on into a longer capitalised noun phrase.

    "We propose Spectral-based Spatial Grouping Transformer (SSGformer)" captures
    "Spectral-based"; the real name is either the whole phrase or the acronym in
    parentheses, and either one appears in its own naming sentence, so dropping
    the fragment loses coverage but removes a wrong name. `and` is included
    because "Robust and Efficient Planning (REPOA)" has the same shape.

    Only horizontal whitespace counts: PDF text breaks lines mid-sentence, so
    matching any whitespace would read the next line's capitalised first word as a
    continuation and reject a name that is actually complete.
    """
    return re.match(r"[ \t]+(?:and[ \t]+)?[A-Z]", text[end:]) is not None


@dataclass(frozen=True)
class _Candidate:
    tier: int
    chunk_index: int
    position: int
    name: str
    quote: str
    chunk_id: str


def _candidates(chunks: list[DocumentChunk], domain: str | None) -> list[_Candidate]:
    extra = domain_patterns(domain)
    constructions = NAME_CONSTRUCTIONS + extra.name_constructions
    found: list[_Candidate] = []
    for chunk in chunks:
        text = chunk.text
        for label, pattern in constructions:
            for match in pattern.finditer(text):
                name = match.group("name")
                start, end = match.start("name"), match.end("name")
                if not _acceptable(name, at_start=_sentence_initial(text, start), construction=label):
                    continue
                if _continues_a_longer_name(text, end):
                    # "we propose Spectral-based Spatial Grouping Transformer": the
                    # captured token is the head of a longer proper noun phrase, so
                    # a single-token name would be a fragment (design §6.1 fixes one
                    # X, and half a name is worse than none: it flows into every
                    # quantitative row of the paper).
                    continue
                found.append(
                    _Candidate(
                        tier=_tier(chunk.section),
                        chunk_index=chunk.chunk_index,
                        position=start,
                        name=name,
                        quote=_quote_for(text, start, end),
                        chunk_id=chunk.id,
                    )
                )
    return found


def _pick_name(candidates: list[_Candidate]) -> tuple[_Candidate | None, tuple[str, ...], tuple[str, ...]]:
    """(chosen, competing names when ambiguous, aliases)."""
    if not candidates:
        return None, (), ()
    best_tier = min(item.tier for item in candidates)
    ordered = sorted((item for item in candidates if item.tier == best_tier), key=lambda i: (i.chunk_index, i.position))
    # Same tier, same chunk, different names: the paper has not chosen. Guessing
    # would attribute one method's numbers to the other (design §4.1).
    same_chunk = {item.name for item in ordered if item.chunk_index == ordered[0].chunk_index}
    if len(same_chunk) > 1:
        return None, tuple(sorted(same_chunk)), ()
    chosen = ordered[0]
    aliases = tuple(sorted({item.name for item in candidates if item.name != chosen.name}))
    return chosen, (), aliases


def _profile_for(source_version_id: str, chunks: list[DocumentChunk], domain: str | None) -> tuple[MethodProfile, tuple[str, ...]]:
    candidates = _candidates(chunks, domain)
    chosen, competing, aliases = _pick_name(candidates)
    profile = MethodProfile(source_version_id=source_version_id)
    if chosen is not None:
        profile.name = chosen.name
        profile.name_quote = chosen.quote
        profile.name_chunk_id = chosen.chunk_id
    profile.aliases = list(aliases)
    return profile, competing


def extract_methods(chunks: list[DocumentChunk], domain: str | None = None) -> MethodExtraction:
    """One profile per source version, ordered by first appearance."""
    by_source: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_version_id, []).append(chunk)

    profiles: list[MethodProfile] = []
    ambiguous: dict[str, tuple[str, ...]] = {}
    for source_version_id, group in by_source.items():
        ordered = sorted(group, key=lambda chunk: chunk.chunk_index)
        profile, competing = _profile_for(source_version_id, ordered, domain)
        if competing:
            ambiguous[source_version_id] = competing
        profile.missing_layers = _missing_layers(profile)
        profiles.append(profile)
    return MethodExtraction(profiles=profiles, ambiguous=ambiguous)


def _missing_layers(profile: MethodProfile) -> list[str]:
    missing: list[str] = []
    if not profile.name:
        missing.append("L1")
    if not profile.components:
        missing.append("L2")
    # L3 has no producer until S3: the layer is reported missing, never silently
    # folded into "no problem found".
    missing.append("L3")
    if not setup_filled(profile.setup):
        missing.append("L4")
    return missing


def setup_filled(setup: MethodSetup) -> bool:
    """True when the profile carries at least one reproducible setting."""
    return bool(setup.scale or setup.protocol or setup.hyperparameters or setup.repository)
