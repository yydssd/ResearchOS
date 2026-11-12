"""HTML loading with heading-based section provenance (plan §15).

Uses the standard library parser rather than BeautifulSoup: the only structure we
need is "which heading owns this paragraph", and `html.parser` gives that
without a new dependency. If real-world pages later defeat it, swap in bs4 behind
`html_to_pages` (ADR-014 records this deviation from plan §5).
"""

from __future__ import annotations

import re
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
# Content containers: when a page has one, only text inside it is content.
_CONTENT_TAGS = frozenset({"main", "article"})

# ar5iv keeps the rendered form and the LaTeX source side by side ("96%96\%",
# "1×11\times 1", "10×10\times"). Left in place one number reads as two or three,
# which corrupts numeric extraction and inflates evidence. The patterns are
# ordered most-specific first: the long form carries the repeated operand, the
# short form only the trailing command.
_ECHO_TIMES_LONG = re.compile(r"(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)\1\\(?:times)\s*\2")
_ECHO_TIMES_SHORT = re.compile(r"(\d+(?:\.\d+)?×\d+(?:\.\d+)?)\\(?:times)")
_ECHO_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\%(\d+(?:\.\d+)?)\\%")


def _collapse(text: str) -> str:
    """Normalize one block: undo ar5iv's LaTeX echo, then collapse whitespace."""
    text = unescape(text)
    text = _ECHO_TIMES_LONG.sub(r"\1×\2", text)  # 1×11\times 1 -> 1×1
    text = _ECHO_TIMES_SHORT.sub(r"\1", text)  # 10×10\times   -> 10×10
    text = _ECHO_PERCENT.sub(r"\1%", text)  # 96%96\%       -> 96%
    return " ".join(text.split())


class _SectionParser(HTMLParser):
    """Collects (section, text, in_content) blocks; headings define the section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str | None, str, bool]] = []
        self._section: str | None = None
        self._buffer: list[str] = []
        self._heading_buffer: list[str] = []
        self._in_heading = False
        self._skip_depth = 0
        self._content_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _CONTENT_TAGS:
            # Flush before entering so text that precedes <main> is not attributed
            # to the content container.
            self._flush()
            self._content_depth += 1
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
        if tag in _CONTENT_TAGS:
            self._flush()
            self._content_depth = max(0, self._content_depth - 1)
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
            self.blocks.append((self._section, text, self._content_depth > 0))


def html_to_pages(raw_html: str) -> list[PageText]:
    """Convert HTML into section-tagged blocks.

    HTML has no reliable page numbers, so page_index is 0 and page_label is
    "html"; the section name carries the locatable provenance instead.

    When the page marks a content container (<main>/<article>), blocks outside it
    are dropped: on real sites that removes cookie banners and "skip to main
    content" style chrome, which otherwise becomes fake evidence.
    """
    parser = _SectionParser()
    parser.feed(raw_html)
    parser.close()
    parser._flush()

    has_content_container = any(in_content for _, _, in_content in parser.blocks)
    selected = [
        (section, text)
        for section, text, in_content in parser.blocks
        if in_content or not has_content_container
    ]
    return [
        PageText(page_index=0, page_label="html", text=text, section=section)
        for section, text in selected
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
