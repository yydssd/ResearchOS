"""HTML loading with heading-based section provenance (plan §15).

Uses the standard library parser rather than BeautifulSoup: the only structure we
need is "which heading owns this paragraph", and `html.parser` gives that
without a new dependency. If real-world pages later defeat it, swap in bs4 behind
`html_to_pages` (ADR-014 records this deviation from plan §5).
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from research_os.domain.enums import FailureType
from research_os.documents.loader import DocumentLoadError, PageText

# Chrome that never carries research content.
_SKIP_TAGS = frozenset({"script", "style", "nav", "footer", "header", "aside", "form", "noscript"})
# Elements whose text becomes one provenance-bearing block.
_BLOCK_TAGS = frozenset({"p", "li", "blockquote", "pre", "td", "figcaption"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def _collapse(text: str) -> str:
    return " ".join(unescape(text).split())


class _SectionParser(HTMLParser):
    """Collects (section, text) blocks; headings define the current section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str | None, str]] = []
        self._section: str | None = None
        self._buffer: list[str] = []
        self._heading_buffer: list[str] = []
        self._in_heading = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._in_heading = True
            self._heading_buffer = []
            return
        if tag in _BLOCK_TAGS:
            # Nested blocks (li > p) start a fresh block; the outer close flushes
            # whatever remains, so no text is lost.
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _HEADING_TAGS and self._in_heading:
            self._section = _collapse("".join(self._heading_buffer)) or self._section
            self._in_heading = False
            self._heading_buffer = []
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_heading:
            self._heading_buffer.append(data)
        else:
            self._buffer.append(data)

    def _flush(self) -> None:
        text = _collapse("".join(self._buffer))
        self._buffer = []
        if text:
            self.blocks.append((self._section, text))


def html_to_pages(raw_html: str) -> list[PageText]:
    """Convert HTML into section-tagged blocks.

    HTML has no reliable page numbers, so page_index is 0 and page_label is
    "html"; the section name carries the locatable provenance instead.
    """
    parser = _SectionParser()
    parser.feed(raw_html)
    parser.close()
    parser._flush()
    return [
        PageText(page_index=0, page_label="html", text=text, section=section)
        for section, text in parser.blocks
    ]


def load_html(path: str | Path) -> list[PageText]:
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - normalize any read failure
        raise DocumentLoadError(FailureType.SOURCE_UNAVAILABLE, f"cannot read {p}: {exc}") from exc
    pages = html_to_pages(raw)
    if not pages:
        raise DocumentLoadError(FailureType.SOURCE_UNAVAILABLE, f"no readable text in {p}")
    return pages
