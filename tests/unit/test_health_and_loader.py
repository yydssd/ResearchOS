"""Health endpoint and document loader/chunk tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_os.documents.chunks import chunk_pages
from research_os.documents.loader import load_document, load_markdown, load_pdf
from research_os.main import app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "ResearchOS"


def test_markdown_loader_sections():
    pages = load_markdown(FIXTURES / "sample_paper.md")
    assert len(pages) >= 5
    assert any(p.section == "Abstract" for p in pages)
    assert any("PSNR" in p.text for p in pages)


def test_pdf_loader_roundtrip(tmp_path):
    import fitz

    pdf_path = tmp_path / "mini.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "All-in-one restoration improves PSNR on Rain100H by 0.42 dB.")
    page.insert_text((72, 110), "We believe the method may generalize to other tasks.")
    doc.save(str(pdf_path))
    doc.close()

    pages = load_pdf(pdf_path)
    assert len(pages) >= 1
    assert pages[0].page_label == "p.1"
    assert "Rain100H" in pages[0].text


def test_load_document_auto_dispatch():
    pages = load_document(FIXTURES / "sample_paper.md", "auto")
    assert len(pages) > 0


def test_chunks_preserve_provenance():
    pages = load_markdown(FIXTURES / "sample_paper.md")
    chunks = chunk_pages(pages, source_version_id="sv_1")
    assert len(chunks) >= 3
    first = chunks[0]
    assert first.source_version_id == "sv_1"
    assert first.chunk_index == 0
    assert first.content_hash == first.compute_hash()
    assert all(c.content_hash for c in chunks)
