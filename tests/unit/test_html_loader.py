"""HTML loader: heading-based sections with boilerplate removed (plan §15)."""

from __future__ import annotations

from pathlib import Path

from research_os.documents.html import html_to_pages
from research_os.documents.loader import load_document, source_type_for
from research_os.domain.enums import SourceType

HTML = """<html><head><style>.x{color:red}</style><script>alert(1)</script></head>
<body>
<nav>menu</nav>
<h1>Restormer</h1>
<p>Efficient transformer for high-resolution restoration.</p>
<h2>Results</h2>
<p>PSNR 39.18 dB on SIDD &amp; a 0.42 dB gain on Rain100H.</p>
<ul><li>Tested on GoPro.</li></ul>
<footer>copyright</footer>
</body></html>"""


def test_html_sections_and_boilerplate_are_handled():
    pages = html_to_pages(HTML)

    assert [p.section for p in pages] == ["Restormer", "Results", "Results"]
    assert all(
        token not in p.text for p in pages for token in ("alert", "menu", "copyright", "color:red")
    )
    # entities are unescaped
    assert any("&" in p.text for p in pages)
    assert all(p.page_label == "html" and p.page_index == 0 for p in pages)


def test_load_document_dispatches_html(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(HTML, encoding="utf-8")

    pages = load_document(path, "auto")

    assert pages
    assert any(p.section == "Results" for p in pages)
    assert any("GoPro" in p.text for p in pages)


def test_main_container_excludes_site_chrome():
    page = """<body><div>Skip to main content</div><main>
    <h2>Abstract</h2><p>Restormer achieves 39.18 dB PSNR on SIDD.</p></main>
    <footer>Copyright 2026</footer></body>"""

    pages = html_to_pages(page)

    assert len(pages) == 1
    assert pages[0].section == "Abstract"
    assert "Skip to main" not in pages[0].text


def test_source_type_detects_html_and_readme(tmp_path):
    assert source_type_for(tmp_path / "a.html") == SourceType.HTML
    assert source_type_for(tmp_path / "README.md") == SourceType.README
    assert source_type_for(tmp_path / "notes.md") == SourceType.MARKDOWN
