"""Evidence extraction with exact source offsets (plan §2.2, §15).

Week 1 shipped a deterministic heuristic extractor (invariant 2.5: prefer
deterministic code); the LLM-backed semantic extractor plugs in through the same
interface later. Evidence always carries an identifiable source location
(invariant 2.1 / plan §7.4).

Offset correctness is part of that contract: sentences are located by interval
in the *original* chunk text, never by searching a rewritten copy, because a
citation is only checkable if `chunk.text[start:end]` is the quoted sentence.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from research_os.domain.enums import EvidenceType
from research_os.domain.models import DocumentChunk, Evidence, new_id

# Lines that are navigation/boilerplate rather than content.
_BOILERPLATE = re.compile(
    r"^\s*(arxiv|doi|accepted|received|corresponding author|e-mail|github|project page"
    r"|references|bibliography|©|copyright)\b",
    re.IGNORECASE,
)
_MIN_EVIDENCE_CHARS = 60

# A sentence ends at . ! or ? followed by whitespace. Decimals ("39.18") are safe
# because the dot there is not followed by whitespace.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Sentence intervals (start, end, sentence) over the unmodified text."""
    spans: list[tuple[int, int, str]] = []

    def _push(raw: str, offset: int) -> None:
        stripped = raw.strip()
        if not stripped:
            return
        lead = len(raw) - len(raw.lstrip())
        start = offset + lead
        spans.append((start, start + len(stripped), stripped))

    start = 0
    for match in _BOUNDARY.finditer(text):
        _push(text[start : match.start()], start)
        start = match.end()
    _push(text[start:], start)
    return spans


def _split_sentences(text: str) -> list[str]:
    """Sentence strings only (kept for callers that do not need offsets)."""
    return [sentence for _, _, sentence in sentence_spans(text)]


def has_location(evidence: Evidence) -> bool:
    """True when the evidence can be located again inside its source (plan §2.2).

    A chunk id is sufficient because chunks carry page/section themselves; a bare
    section or page label also counts for sources loaded without chunking.
    """
    return bool(evidence.chunk_id or evidence.section or evidence.page_label)


class EvidenceExtractor(Protocol):
    def extract(self, chunks: list[DocumentChunk]) -> list[Evidence]: ...


class HeuristicEvidenceExtractor:
    """Sentence-level extraction with source-location provenance."""

    def extract(self, chunks: list[DocumentChunk]) -> list[Evidence]:
        evidence: list[Evidence] = []
        seen: set[str] = set()
        for chunk in chunks:
            for start, end, sentence in sentence_spans(chunk.text):
                if len(sentence) < _MIN_EVIDENCE_CHARS:
                    continue
                if _BOILERPLATE.match(sentence):
                    continue
                digest = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                evidence.append(
                    Evidence(
                        id=new_id("e"),
                        source_version_id=chunk.source_version_id,
                        evidence_type=EvidenceType.TEXT,
                        text=sentence,
                        section=chunk.section,
                        page_index=chunk.page_index,
                        page_label=chunk.page_label,
                        chunk_id=chunk.id,
                        char_start=start,
                        char_end=end,
                        content_hash=digest,
                    )
                )
        return evidence
