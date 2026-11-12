"""Evidence extraction.

Week 1 ships a deterministic heuristic extractor (invariant 2.5: prefer
deterministic code); the LLM-backed semantic extractor plugs in through the
same interface later. Evidence always carries an identifiable source location
(invariant 2.1 / plan §7.4).
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


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries while protecting decimal points
    (e.g. '39.18 dB' must not be cut at the dot)."""
    protected = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


class EvidenceExtractor(Protocol):
    def extract(self, chunks: list[DocumentChunk]) -> list[Evidence]: ...


class HeuristicEvidenceExtractor:
    """Sentence-level extraction with source-location provenance."""

    def extract(self, chunks: list[DocumentChunk]) -> list[Evidence]:
        evidence: list[Evidence] = []
        seen: set[str] = set()
        for chunk in chunks:
            text = chunk.text
            for sentence in _split_sentences(text.replace("\n", " ")):
                if len(sentence) < _MIN_EVIDENCE_CHARS:
                    continue
                if _BOILERPLATE.match(sentence):
                    continue
                digest = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                pos = chunk.text.find(sentence)
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
                        char_start=pos if pos >= 0 else None,
                        char_end=pos + len(sentence) if pos >= 0 else None,
                        content_hash=digest,
                    )
                )
        return evidence
