"""Provenance-preserving chunking (plan §15)."""

from __future__ import annotations

from research_os.domain.models import DocumentChunk, new_id
from research_os.documents.loader import PageText

DEFAULT_MAX_CHARS = 1200


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into bounded pieces, preferring paragraph then sentence
    boundaries so provenance (page/section) stays meaningful per chunk."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    # prefer paragraph boundaries
    parts: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            parts.append(para)
        else:
            # split long paragraphs at sentence-ish boundaries
            current = ""
            for sentence in para.replace("\n", " ").split(". "):
                piece = sentence.rstrip(".") + "."
                if current and len(current) + len(piece) > max_chars:
                    parts.append(current.strip())
                    current = piece
                else:
                    current += (" " if current else "") + piece
            if current.strip():
                parts.append(current.strip())
    return [p for p in parts if p]


def chunk_pages(pages: list[PageText], source_version_id: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[DocumentChunk]:
    """Turn pages into provenance-preserving chunks (plan §15): each chunk
    retains source_version_id, page label/index, section, chunk_index and a
    content hash for deduplication."""
    chunks: list[DocumentChunk] = []
    idx = 0
    for page in pages:
        for text in _split_into_chunks(page.text, max_chars):
            chunk = DocumentChunk(
                id=new_id("chunk"),
                source_version_id=source_version_id,
                page_index=page.page_index,
                page_label=page.page_label,
                section=page.section,
                chunk_index=idx,
                text=text,
            )
            chunk.content_hash = chunk.compute_hash()
            chunks.append(chunk)
            idx += 1
    return chunks
