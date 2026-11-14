"""Deterministic identifier, title, and author normalization (plan §14).

Pure functions only: no I/O and no semantic judgment, so source identity can be
unit-tested exhaustively (invariant 2.5: prefer deterministic code over LLM
calls). Everything a provider returns must pass through here before it is
compared against anything else.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# DOI may arrive as a bare identifier or wrapped in a resolver URL / "doi:" prefix.
_DOI_PREFIX = re.compile(r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI_BODY = re.compile(r"^10\.\d{4,9}/\S+$")

# arXiv new-style (2104.12345) and old-style (cs/0601001, hep-th/9901001) ids.
_ARXIV_NEW = r"\d{4}\.\d{4,5}"
_ARXIV_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}"
_ARXIV_URL = re.compile(
    rf"arxiv\.org/(?:abs|pdf)/(?P<id>{_ARXIV_NEW}|{_ARXIV_OLD})(?:v(?P<v>\d+))?(?:\.pdf)?",
    re.IGNORECASE,
)
_ARXIV_PREFIXED = re.compile(rf"^\s*arxiv:\s*(?P<id>{_ARXIV_NEW}|{_ARXIV_OLD})(?:v(?P<v>\d+))?\s*$", re.IGNORECASE)
_ARXIV_BARE = re.compile(rf"^\s*(?P<id>{_ARXIV_NEW}|{_ARXIV_OLD})(?:v(?P<v>\d+))?\s*$", re.IGNORECASE)

# Journal/arXiv versions of one paper often differ only by a trailing
# "(Supplementary Material)" / "(extended version)" marker.
_SUPPLEMENT = re.compile(
    r"\s*[\(\[]\s*(?:supplementary|supplemental|supporting information|extended version|appendix)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?")
_NON_WORD = re.compile(r"[^a-z0-9]+")
_NON_NAME = re.compile(r"[^A-Za-z\s,\-]")
_NON_LETTER = re.compile(r"[^a-z]")


def normalize_doi(raw: str | None) -> str | None:
    """Return a bare lowercase DOI, or None when the input is not a DOI.

    Normalizing here is what lets Crossref, OpenAlex and arXiv metadata meet on
    the same identity key instead of looking like three different works.
    """
    if not raw:
        return None
    value = _DOI_PREFIX.sub("", str(raw).strip()).strip().rstrip(".,;)")
    value = value.lower()
    return value if _DOI_BODY.match(value) else None


def parse_arxiv(raw: str | None) -> tuple[str, str | None] | None:
    """Return ``(base_id, version)`` for any arXiv identifier form, else None.

    The base id is deliberately version-free so that v1/v2/v3 collapse onto a
    single identity; the version is kept only to pick a canonical version.
    """
    if not raw:
        return None
    text = str(raw).strip()
    for pattern in (_ARXIV_URL, _ARXIV_PREFIXED, _ARXIV_BARE):
        # The URL form appears inside a longer string; the other two are anchored.
        match = pattern.search(text) if pattern is _ARXIV_URL else pattern.match(text)
        if match:
            return match.group("id").lower(), match.group("v")
    return None


def normalize_title(raw: str | None) -> str:
    """Lowercase, de-LaTeX, de-punctuate and collapse whitespace."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw))
    while _SUPPLEMENT.search(text):
        text = _SUPPLEMENT.sub(" ", text)
    text = _LATEX_CMD.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("$", " ")
    text = text.lower()
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.split())


def title_similarity(a: str, b: str) -> float:
    """Similarity of two titles in [0, 1].

    Token Jaccard catches reordered/abbreviated titles while the character-level
    ratio catches punctuation-only differences; taking the max avoids missing
    either. Both are deterministic - no embedding model needed.
    """
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    union = ta | tb
    jaccard = len(ta & tb) / len(union) if union else 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    return max(jaccard, ratio)


def normalize_author(raw: str | None) -> str:
    """Reduce an author name to a stable ``"last|firstinitial"`` key.

    Crossref emits "Zamir, Syed Waqas" while arXiv/OpenAlex emit "Syed Waqas
    Zamir"; both must map to the same key or cross-provider author comparison
    silently fails.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", str(raw))
    # Drop combining marks so "Müller" and "Muller" compare equal.
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _NON_NAME.sub(" ", text).strip()
    if not text:
        return ""
    if "," in text:
        last, rest = text.split(",", 1)
    else:
        parts = text.split()
        last, rest = parts[-1], " ".join(parts[:-1])
    last_key = _NON_LETTER.sub("", last.lower())
    rest_tokens = [t for t in re.split(r"[\s\-]+", rest.lower()) if t]
    initial = rest_tokens[0][0] if rest_tokens else ""
    return f"{last_key}|{initial}"


def author_overlap(a: list[str], b: list[str]) -> float:
    """Overlap of normalized author keys relative to the smaller list.

    Relative-to-smaller avoids penalizing a paper whose metadata lists only the
    first author.
    """
    ka = {normalize_author(x) for x in a} - {""}
    kb = {normalize_author(x) for x in b} - {""}
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / min(len(ka), len(kb))
