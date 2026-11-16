"""Validate what the describer wrote (design §7.4).

Four defences, in this order, because they have different blast radii:

1. schema (aspect / lengths / chunk id)  -> reject the whole answer
2. quote locates (verbatim, >=4 words, unique in its chunk) -> drop the point
3. statement is supported by the quote (>=2 content words shared) -> drop the point
4. no describer / over budget is decided by the caller (it owns the budget)

The split exists so that one bad point costs one point, while a malformed answer
costs the paper: keeping points from a response we know broke its contract would
be trusting the part we cannot check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from research_os.domain.models import DocumentChunk, MethodPoint
from research_os.llm.base import MethodDescriptionResponse

_ASPECTS = frozenset({"goal", "mechanism", "why_it_works", "io"})
_MAX_STATEMENT = 200
_MIN_QUOTE_WORDS = 4
_MIN_SHARED_WORDS = 2

# Words that carry no claim; a statement "supported" only by these is supported
# by grammar, not by the quote.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
        "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
        "these", "those", "we", "our", "as", "at", "from", "which", "each", "than",
        "then", "not", "no", "can", "may", "uses", "use", "using", "via",
    }
)
# The schema's own vocabulary is not evidence: a statement whose only overlap with
# its quote is "mechanism" is supported by the label, not by the sentence
# (design §7.4.2 excludes aspect words explicitly).
_ASPECT_WORDS = frozenset({"goal", "mechanism", "why", "it", "works", "io"})
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class DescriptionOutcome:
    """Validated points plus the one reason worth logging when none survived."""

    points: list[MethodPoint]
    reason: str | None = None


def _content_words(text: str) -> set[str]:
    return {
        word
        for word in _WORD.findall(text.lower())
        if len(word) > 2 and word not in _STOPWORDS and word not in _ASPECT_WORDS
    }


_SENTENCE_END = ".!?:;"
_HEADING_LINE = re.compile(r"(?m)^#{1,6} .*$")


def _locates(quote: str, chunk_text: str) -> bool:
    """Verbatim after folding, >=4 words, unique, and a whole sentence (design §7.4, D33).

    Fold both sides: chunks break lines mid-sentence, and the fold used for
    containment must be the one used for uniqueness. Headings are stripped first,
    or the first sentence of every section looks like a fragment. Measured on 290
    recorded points: 15 were complete sentences, 214 began mid-clause.
    """
    collapsed = " ".join(quote.split())
    if len(collapsed.split()) < _MIN_QUOTE_WORDS:
        return False
    flat = " ".join(_HEADING_LINE.sub(" ", chunk_text).split())
    if flat.count(collapsed) != 1:
        return False
    at = flat.find(collapsed)
    before = flat[:at].rstrip()
    after = flat[at + len(collapsed) :].lstrip()
    starts = not before or before[-1] in _SENTENCE_END
    ends = collapsed[-1] in _SENTENCE_END or not after or after[0] in _SENTENCE_END
    return starts and ends


def _span(quote: str, text: str) -> tuple[int, int] | None:
    """Character range of the quote in the RAW chunk text.

    Whitespace-tolerant on purpose: the quote is folded for comparison, the raw
    text still holds the line breaks, and a plain find() would miss those. The
    returned range is an envelope in the original text, which is what a reader
    needs to jump to.
    """
    pattern = r"\s+".join(re.escape(word) for word in quote.split())
    match = re.search(pattern, text)
    return (match.start(), match.end()) if match else None

def validate_description(
    response: MethodDescriptionResponse, chunks: list[DocumentChunk]
) -> DescriptionOutcome:
    by_id = {chunk.id: chunk for chunk in chunks}
    sections = {chunk.id: chunk.section for chunk in chunks}

    # Defence 1: the contract itself. One violation rejects the answer.
    for draft in response.points:
        if draft.aspect not in _ASPECTS:
            return DescriptionOutcome([], "METHOD_DESCRIPTION_REJECTED")
        if not draft.statement.strip() or len(draft.statement) > _MAX_STATEMENT:
            return DescriptionOutcome([], "METHOD_DESCRIPTION_REJECTED")
        if draft.chunk_id not in by_id:
            return DescriptionOutcome([], "METHOD_DESCRIPTION_REJECTED")

    points: list[MethodPoint] = []
    reason: str | None = None
    for draft in response.points:
        chunk = by_id[draft.chunk_id]
        # Defence 2: it has to be findable again.
        if not _locates(draft.quote, chunk.text):
            reason = reason or "METHOD_POINT_UNLOCATABLE"
            continue
        # Defence 3: the statement has to be about the quote, not merely
        # accompanied by it.
        shared = _content_words(draft.statement) & _content_words(draft.quote)
        if len(shared) < _MIN_SHARED_WORDS:
            reason = reason or "METHOD_STATEMENT_UNSUPPORTED"
            continue
        span = _span(draft.quote, chunk.text)
        points.append(
            MethodPoint(
                aspect=draft.aspect,
                statement=" ".join(draft.statement.split()),
                quote=" ".join(draft.quote.split()),
                chunk_id=draft.chunk_id,
                section=draft.section or sections.get(draft.chunk_id),
                char_start=span[0] if span else None,
                char_end=span[1] if span else None,
            )
        )
    return DescriptionOutcome(points, reason)

