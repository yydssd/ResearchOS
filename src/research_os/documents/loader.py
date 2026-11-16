"""Document loading: PDF and Markdown with page/section provenance (plan §15)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_os.domain.enums import FailureType, SourceType
from research_os.domain.models import new_id


class DocumentLoadError(Exception):
    def __init__(self, failure_type: FailureType, message: str) -> None:
        super().__init__(message)
        self.failure_type = failure_type


@dataclass(frozen=True)
class PageText:
    page_index: int
    page_label: str
    text: str
    section: str | None = None


def load_pdf(path: str | Path) -> list[PageText]:
    import fitz  # PyMuPDF

    p = Path(path)
    try:
        doc = fitz.open(str(p))
    except Exception as exc:  # noqa: BLE001 - normalize any parse failure
        raise DocumentLoadError(FailureType.PDF_PARSE_ERROR, f"cannot open PDF {p}: {exc}") from exc
    try:
        pages: list[PageText] = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append(PageText(page_index=i, page_label=f"p.{i + 1}", text=text))
        return pages
    finally:
        doc.close()


def load_markdown(path: str | Path) -> list[PageText]:
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise DocumentLoadError(FailureType.SOURCE_UNAVAILABLE, f"cannot read {p}: {exc}") from exc

    sections: list[PageText] = []
    current_section: str | None = None
    buffer: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if buffer:
                sections.append(
                    PageText(page_index=0, page_label="md", text="\n".join(buffer).strip(), section=current_section)
                )
                buffer = []
            current_section = stripped.lstrip("#").strip()
        else:
            buffer.append(line)
    if buffer:
        sections.append(
            PageText(page_index=0, page_label="md", text="\n".join(buffer).strip(), section=current_section)
        )
    return [s for s in sections if s.text]


def load_document(path: str | Path, source_type: str = "auto") -> list[PageText]:
    p = Path(path)
    st = source_type.lower()
    if st == "pdf" or (st == "auto" and p.suffix.lower() == ".pdf"):
        return load_pdf(p)
    if st == "html" or (st == "auto" and p.suffix.lower() in {".html", ".htm"}):
        # Imported lazily: html.py imports PageText/DocumentLoadError from this
        # module, so a top-level import here would be circular.
        from research_os.documents.html import load_html

        return load_html(p)
    if st in ("markdown", "md", "readme") or (st == "auto" and p.suffix.lower() in {".md", ".markdown", ".txt"}):
        return load_markdown(p)
    raise DocumentLoadError(FailureType.SOURCE_UNAVAILABLE, f"unsupported document type: {p.suffix}")


def source_type_for(path: str | Path, declared: str = "auto") -> SourceType:
    """Resolve the SourceType from an explicit declaration or the file name.

    A README is tagged as such (not as generic Markdown) so that downstream code
    can use a different source-authority tier for repository documentation
    (plan §8: a repository is authoritative for implementation details).
    """
    if declared not in ("auto", ""):
        try:
            return SourceType(declared)
        except ValueError:
            pass
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return SourceType.PDF
    if suffix in {".html", ".htm"}:
        return SourceType.HTML
    if suffix in {".md", ".markdown", ".txt"}:
        if p.stem.lower().startswith("readme"):
            return SourceType.README
        return SourceType.MARKDOWN
    return SourceType.WEB


def make_source_version(
    work_id: str,
    path: str,
    title: str = "",
    source_type: SourceType | None = None,
    verified: bool = False,
) -> tuple:
    """Build a SourceVersion domain object plus its work id (helper for slices)."""
    from research_os.domain.models import SourceVersion

    st = source_type or source_type_for(path)
    sv = SourceVersion(
        work_id=work_id,
        source_type=st,
        title=title or Path(path).stem,
        local_path=path,
        verified=verified,
    )
    return sv


def full_text_link(source) -> str | None:
    """The address a stored method point should link to.

    The canonical URL is preferred; a locally loaded paper has none, so its path
    is the only address a reader can check. A missing version yields None rather
    than a guess: a wrong link is worse than no link, because nothing marks it as
    wrong once it is rendered.
    """
    if source is None:
        return None
    return source.url or source.local_path or None
