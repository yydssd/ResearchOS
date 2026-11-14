"""Source layer: discovery, normalization, verification (plan §14).

This package turns search results into canonical works. It contains no
semantic judgment and no evidence: candidates are discovery metadata only.
"""

from research_os.sources.normalize import (
    author_overlap,
    normalize_author,
    normalize_doi,
    normalize_title,
    parse_arxiv,
    title_similarity,
)

__all__ = [
    "author_overlap",
    "normalize_author",
    "normalize_doi",
    "normalize_title",
    "parse_arxiv",
    "title_similarity",
]
