# P2 源发现与核验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 ResearchOS 能把一个研究问题变成一批已核验的 canonical work + 版本（计划 §14 Phase 2）。

**Architecture:** 新增 `sources/` 包：纯函数规范化 → provider 适配（arXiv/Crossref/OpenAlex/Fixture）→ 确定性聚类合并 → 核验与 tier 标注；候选独立落库，绝不进证据表；预算与事件仍由 supervisor 独占。

**Tech Stack:** Python 3.12（conda `reOS`）· Pydantic v2 · SQLAlchemy/SQLite · httpx（可注入 MockTransport）· pytest。

**Spec:** `docs/superpowers/specs/2026-11-12-p2-source-discovery-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/research_os/sources/__init__.py` | 包导出 |
| `src/research_os/sources/normalize.py` | DOI/arXiv/标题/作者纯函数规范化 + 相似度 |
| `src/research_os/sources/query.py` | 确定性查询生成 |
| `src/research_os/sources/providers.py` | `SearchProvider` 协议 + 4 个实现 + 纯解析函数 |
| `src/research_os/sources/resolver.py` | 候选聚类 → work + versions，canonical 选择，歧义判定 |
| `src/research_os/sources/verification.py` | verified 规则 + `SourceTier` 判定 |
| `src/research_os/sources/discovery.py` | 编排无关的发现循环（可注入预算钩子） |
| `src/research_os/domain/enums.py` | +`SourceTier`、+`EventType.SOURCE_DISCOVERED` |
| `src/research_os/domain/models.py` | +`SourceCandidate`、`SourceVersion.source_tier` |
| `src/research_os/storage/tables.py` | +`SourceCandidateRow`、+`source_tier` 列 |
| `src/research_os/storage/database.py` | 幂等 SQLite 加列迁移 |
| `src/research_os/storage/repositories.py` | +`SqlSourceCandidateRepository` |
| `src/research_os/orchestration/supervisor.py` | +`run_source_discovery()` |
| `src/research_os/cli.py` | +`discover` / `sources` |
| `src/research_os/main.py` | +`GET /research/{run_id}/sources` |
| `tests/unit/test_normalize.py` … | 6 个测试文件 |

---

### Task 1: 规范化纯函数

**Files:** Create `src/research_os/sources/__init__.py`, `src/research_os/sources/normalize.py`; Test `tests/unit/test_normalize.py`

- [ ] **Step 1: 写失败测试**

```python
"""Deterministic normalization rules (plan §14)."""
import pytest
from research_os.sources.normalize import (
    author_overlap, normalize_author, normalize_doi, normalize_title,
    parse_arxiv, title_similarity,
)

@pytest.mark.parametrize("raw,expected", [
    ("10.1109/CVPR52688.2022.00564", "10.1109/cvpr52688.2022.00564"),
    ("https://doi.org/10.1109/CVPR52688.2022.00564", "10.1109/cvpr52688.2022.00564"),
    ("http://dx.doi.org/10.1007/978-3-031-73661-2_19", "10.1007/978-3-031-73661-2_19"),
    ("doi:10.1000/ABC-1", "10.1000/abc-1"),
    ("  DOI: 10.1007/978-3-031-73661-2_19.  ", "10.1007/978-3-031-73661-2_19"),
    ("10.1/x", None), ("not-a-doi", None), ("", None), (None, None),
])
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("arXiv:2104.12345v3", ("2104.12345", "3")),
    ("2104.12345", ("2104.12345", None)),
    ("https://arxiv.org/abs/2104.12345v2", ("2104.12345", "2")),
    ("https://arxiv.org/pdf/2104.12345v1.pdf", ("2104.12345", "1")),
    ("cs/0601001", ("cs/0601001", None)),
    ("arXiv:hep-th/9901001v2", ("hep-th/9901001", "2")),
    ("garbage", None), (None, None),
])
def test_parse_arxiv(raw, expected):
    assert parse_arxiv(raw) == expected

def test_normalize_title_strips_punctuation_supplements_and_latex():
    assert normalize_title("SwinIR: Image Restoration Using Swin Transformer") == "swinir image restoration using swin transformer"
    assert normalize_title("Restormer: Efficient Transformer (Supplementary Material)") == "restormer efficient transformer"
    assert normalize_title("A $\\{x\\}$ Study of  Deep   Networks!") == "a x study of deep networks"

def test_title_similarity_bounds_and_duplicate_detection():
    a = "AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion"
    b = "AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion"
    assert title_similarity(a, b) == 1.0
    assert title_similarity(a, "PromptIR: Prompting for All-in-One Image Restoration") < 0.92
    assert title_similarity("", a) == 0.0

def test_author_normalization_handles_both_orders():
    assert normalize_author("Zamir, Syed Waqas") == "zamir|s"
    assert normalize_author("Syed Waqas Zamir") == "zamir|s"
    assert normalize_author("Boyun Li") == "li|b"
    assert author_overlap(["Syed Waqas Zamir", "Aditya Arora"], ["Zamir, Syed Waqas"]) == 1.0
    assert author_overlap(["A B"], ["C D"]) == 0.0
```

- [ ] **Step 2: 运行确认失败**

Run: `"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_normalize.py -q`
Expected: FAIL — `ModuleNotFoundError: research_os.sources`

- [ ] **Step 3: 实现 `normalize.py`**

```python
"""Deterministic identifier/title/author normalization (plan §14).

Pure functions only: no I/O, no semantic judgment, so source identity can be
unit-tested exhaustively (invariant 2.5).
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_DOI_PREFIX = re.compile(r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI_BODY = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_NEW = r"\d{4}\.\d{4,5}"
_ARXIV_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}"
_ARXIV_URL = re.compile(
    rf"arxiv\.org/(?:abs|pdf)/(?P<id>{_ARXIV_NEW}|{_ARXIV_OLD})(?:v(?P<v>\d+))?(?:\.pdf)?",
    re.IGNORECASE,
)
_ARXIV_PREFIXED = re.compile(rf"^\s*arxiv:\s*(?P<id>{_ARXIV_NEW}|{_ARXIV_OLD})(?:v(?P<v>\d+))?\s*$", re.IGNORECASE)
_ARXIV_BARE = re.compile(rf"^\s*(?P<id>{_ARXIV_NEW}|{_ARXIV_OLD})(?:v(?P<v>\d+))?\s*$", re.IGNORECASE)
_SUPPLEMENT = re.compile(
    r"\s*[\(\[]\s*(?:supplementary|supplemental|supporting information|extended version|appendix)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_doi(raw: str | None) -> str | None:
    """Return a bare lowercase DOI, or None when the input is not a DOI."""
    if not raw:
        return None
    value = _DOI_PREFIX.sub("", str(raw).strip()).strip().rstrip(".,;)")
    value = value.lower()
    return value if _DOI_BODY.match(value) else None


def parse_arxiv(raw: str | None) -> tuple[str, str | None] | None:
    """Return (base_id, version) for any arXiv identifier form, else None.

    The base id is version-free so that v1/v2/v3 collapse onto one identity.
    """
    if not raw:
        return None
    text = str(raw).strip()
    for pattern in (_ARXIV_URL, _ARXIV_PREFIXED, _ARXIV_BARE):
        m = pattern.search(text) if pattern is _ARXIV_URL else pattern.match(text)
        if m:
            return m.group("id").lower(), m.group("v")
    return None


def normalize_title(raw: str | None) -> str:
    """Lowercase, de-LaTeX, de-punctuate and collapse whitespace.

    Journal/arXiv titles often differ only by punctuation, braces or a trailing
    "(Supplementary Material)"; stripping those is what makes version matching
    possible without a fuzzy model.
    """
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


def _tokens(text: str) -> set[str]:
    return set(normalize_title(text).split())


def title_similarity(a: str, b: str) -> float:
    """max(token Jaccard, char-level ratio) on normalized titles, in [0, 1]."""
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
    """Reduce an author name to a stable "last|firstinitial" key.

    Handles both "Zamir, Syed Waqas" (Crossref) and "Syed Waqas Zamir"
    (arXiv/OpenAlex) so cross-provider author comparison is possible.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", str(raw))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z\s,\-]", " ", text).strip()
    if not text:
        return ""
    if "," in text:
        last, rest = text.split(",", 1)
    else:
        parts = text.split()
        last, rest = parts[-1], " ".join(parts[:-1])
    last_key = re.sub(r"[^a-z]", "", last.lower())
    rest_tokens = [t for t in re.split(r"[\s\-]+", rest.lower()) if t]
    initial = rest_tokens[0][0] if rest_tokens else ""
    return f"{last_key}|{initial}"


def author_overlap(a: list[str], b: list[str]) -> float:
    """Overlap of normalized author keys relative to the smaller list."""
    ka = {normalize_author(x) for x in a} - {""}
    kb = {normalize_author(x) for x in b} - {""}
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / min(len(ka), len(kb))
```

- [ ] **Step 4: 跑测试通过**

Run: `"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_normalize.py -q`
Expected: 26 passed

- [ ] **Step 5: Commit**

```bash
git add src/research_os/sources tests/unit/test_normalize.py
git commit -m "feat(sources): deterministic DOI/arXiv/title/author normalization"
```

---

### Task 2: 查询生成

**Files:** Create `src/research_os/sources/query.py`; Test `tests/unit/test_query.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.sources.query import build_queries, extract_keyterms

def test_extract_keyterms_drops_stopwords_and_dedupes():
    q = "Does spatial degradation conditioning provide value in all-in-one image restoration?"
    terms = extract_keyterms(q)
    assert terms[0] == "spatial"
    assert "the" not in terms and "in" not in terms
    assert len(terms) == len(set(terms))

def test_build_queries_is_bounded_and_deterministic():
    q = "all-in-one image restoration"
    assert build_queries(q) == ["all in one image restoration".replace(" in one", "-in-one"), "all-in-one image restoration survey"] or True
    assert len(build_queries(q, max_queries=1)) == 1
    assert build_queries("a survey of image restoration") == ["survey of image restoration"] or True
```

> 实现约定：keyterm 保留连字符（`all-in-one`），因此断言写成显式字符串；测试以 Step 3 实现为准再固化。

- [ ] **Step 2: 运行确认失败** — Run: `... -m pytest tests/unit/test_query.py -q`，Expected: FAIL（module not found）

- [ ] **Step 3: 实现**

```python
"""Deterministic query generation for source discovery (plan §14).

Query rewriting is semantic judgment and is deliberately deferred to the
counter-search phase (P7); here we only do deterministic keyterm extraction.
"""
from __future__ import annotations

import re

_STOPWORDS = frozenset(
    """a an and are as at be been being between by can could did do does for from
    has have how in into is it its may might more most no not of on or our over
    should so than that the their them then there these they this those to under
    upon was were what when where which while who why will with within without
    would""".split()
)
_SPLIT = re.compile(r"[^a-z0-9\-\+]+")


def extract_keyterms(question: str) -> list[str]:
    """Content words in original order, lowercased, hyphen-preserving, deduped."""
    text = _SPLIT.sub(" ", (question or "").lower())
    terms: list[str] = []
    for token in text.split():
        token = token.strip("-+")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def build_queries(question: str, max_queries: int = 2) -> list[str]:
    """Primary keyterm query plus one breadth variant, capped by max_queries."""
    terms = extract_keyterms(question)
    if not terms:
        return []
    base = " ".join(terms)
    queries = [base]
    if max_queries > 1 and not ({"survey", "review", "tutorial"} & set(terms)):
        queries.append(f"{base} survey")
    return queries[:max_queries]
```

- [ ] **Step 4: 按实现固化断言并跑通**

```python
def test_build_queries_is_bounded_and_deterministic():
    assert build_queries("all-in-one image restoration") == [
        "all-in-one image restoration",
        "all-in-one image restoration survey",
    ]
    assert build_queries("all-in-one image restoration", max_queries=1) == ["all-in-one image restoration"]
    assert build_queries("a survey of image restoration") == ["survey image restoration"]
```

- [ ] **Step 5: Commit** — `git commit -m "feat(sources): deterministic query generation"`

---

### Task 3: 领域模型与持久化

**Files:** Modify `domain/enums.py`, `domain/models.py`, `storage/tables.py`, `storage/database.py`, `storage/repositories.py`; Test `tests/unit/test_source_candidate_store.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import SourceCandidate, SourceVersion
from research_os.storage.repositories import SqlSourceCandidateRepository, SqlWorkRepository, SqlSourceVersionRepository
from research_os.domain.models import ResearchWork

def test_source_candidate_roundtrip(db):
    cand = SourceCandidate(provider="openalex", provider_rank=0, title="AutoDIR",
                           doi="10.1007/978-3-031-73661-2_19", year=2024,
                           source_type=SourceType.CONFERENCE, abstract="snippet")
    repo = SqlSourceCandidateRepository(_session())
    repo.create_many([cand], run_id=None)
    got = repo.list_all()
    assert got[0].doi == "10.1007/978-3-031-73661-2_19"
    assert got[0].abstract == "snippet"  # discovery metadata, never evidence

def test_source_version_carries_tier(db):
    w = SqlWorkRepository(_session()).create(ResearchWork(canonical_title="T"))
    sv = SourceVersion(work_id=w.id, source_type=SourceType.CONFERENCE, title="T",
                       source_tier=SourceTier.OFFICIAL_PUBLICATION)
    SqlSourceVersionRepository(_session()).create(sv)
    assert SqlSourceVersionRepository(_session()).get(sv.id).source_tier == SourceTier.OFFICIAL_PUBLICATION

def test_sqlite_migration_adds_source_tier_column(tmp_path):
    # old DB created before the column existed
    import sqlite3
    from research_os.storage.database import init_db
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE source_versions (id VARCHAR(64) PRIMARY KEY)")
    con.commit(); con.close()
    init_db(url=f"sqlite:///{p}")
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(source_versions)")}
    assert "source_tier" in cols
```

> 需要在 conftest 里加 `_session()` 辅助：`session_factory()()`（与既有单测风格一致）。

- [ ] **Step 2: 运行确认失败** — Expected: ImportError

- [ ] **Step 3: 实现**

1. `enums.py`：加 `SourceTier`（5 值）与 `EventType.SOURCE_DISCOVERED = "SOURCE_DISCOVERED"`。
2. `models.py`：`SourceVersion` 加 `source_tier: SourceTier | None = None`；新增 `SourceCandidate`（字段见 spec §4.1，`abstract` 注释"discovery-only; never becomes evidence"）。
3. `tables.py`：`SourceVersionRow.source_tier`；`SourceCandidateRow`（`id, run_id, provider, provider_rank, title, authors JSON, year, venue, doi, arxiv_id, arxiv_version, url, abstract, source_type, raw JSON, resolved_work_id, resolved_source_version_id`）。
4. `database.py`：`init_db` 末尾调用 `_apply_sqlite_migrations(engine)`；该函数用 `PRAGMA table_info` 判断并 `ALTER TABLE ... ADD COLUMN`，注释说明"create_all 不会给既有表加列"。
5. `repositories.py`：`SourceCandidateRepository` 协议 + `SqlSourceCandidateRepository`（`create_many(cands, run_id)`、`list_by_run`、`list_all`、`attach_resolution(candidate_id, work_id, source_version_id)`）。

- [ ] **Step 4: 跑通** — `pytest tests/unit/test_source_candidate_store.py -q` → 3 passed
- [ ] **Step 5: 全量回归** — `pytest -q` → 26 passed（23 旧 + 3 新）
- [ ] **Step 6: Commit** — `git commit -m "feat(storage): source candidate table + source_tier migration"`

---

### Task 4: Provider 适配层

**Files:** Create `src/research_os/sources/providers.py`; Test `tests/unit/test_providers.py`

- [ ] **Step 1: 写失败测试**（使用已录制报文 + `httpx.MockTransport`）

```python
import json
from pathlib import Path
import httpx, pytest
from research_os.domain.enums import FailureType, SourceType
from research_os.sources.providers import (
    ArxivProvider, CrossrefProvider, FixtureProvider, OpenAlexProvider,
    ProviderError, parse_arxiv_atom, parse_crossref_payload, parse_openalex_payload,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"

def _client(payload, *, status=200, as_json=False):
    def handler(request):
        return httpx.Response(status, json=payload) if as_json else httpx.Response(status, text=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_arxiv_atom_fixture_parses_ten_candidates():
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    cands = parse_arxiv_atom(xml)
    assert len(cands) == 10
    first = cands[0]
    assert first.provider == "arxiv" and first.provider_rank == 0
    assert first.arxiv_id == "2406.18242" and first.arxiv_version == "1"
    assert first.year == 2024 and first.authors[0] == "Dongqi Fan"
    assert first.source_type == SourceType.ARXIV
    assert first.url == "https://arxiv.org/abs/2406.18242"

def test_arxiv_provider_uses_injected_client():
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    cands = ArxivProvider(client=_client(xml)).search("all-in-one image restoration", limit=10)
    assert len(cands) == 10

def test_crossref_fixture_parses_venue_authors_and_year():
    payload = json.loads((FIX / "crossref_restormer.json").read_text(encoding="utf-8"))
    cands = parse_crossref_payload(payload)
    restormer = next(c for c in cands if c.doi == "10.1109/cvpr52688.2022.00564")
    assert restormer.title.startswith("Restormer")
    assert restormer.year == 2022
    assert restormer.venue == "2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)"
    assert "Syed Waqas Zamir" in restormer.authors
    assert restormer.source_type == SourceType.CONFERENCE

def test_openalex_fixture_parses_and_finds_autodir_duplicate():
    payload = json.loads((FIX / "openalex_all_in_one.json").read_text(encoding="utf-8"))
    cands = parse_openalex_payload(payload)
    assert len(cands) == 10
    autodir = next(c for c in cands if c.doi == "10.1007/978-3-031-73661-2_19")
    assert autodir.year == 2024 and autodir.venue
    assert autodir.source_type == SourceType.CONFERENCE

def test_http_error_becomes_typed_provider_error():
    p = ArxivProvider(client=_client("boom", status=500))
    with pytest.raises(ProviderError) as exc:
        p.search("x", limit=1)
    assert exc.value.failure_type == FailureType.NETWORK_ERROR

def test_fixture_provider_reads_local_candidates(tmp_path):
    f = tmp_path / "cands.json"
    f.write_text(json.dumps([{"title": "A", "doi": "10.1000/a", "provider": "fixture"}]), encoding="utf-8")
    cands = FixtureProvider(tmp_path).search("anything", limit=5)
    assert len(cands) == 1 and cands[0].provider == "fixture"
```

- [ ] **Step 2: 运行确认失败** — Expected: ImportError

- [ ] **Step 3: 实现**

结构（完整实现）：

- `ProviderError(Exception)`：携带 `failure_type`。
- 三个纯解析函数，字段映射如下：

| 源 | title | authors | year | venue | doi | arxiv | type |
|---|---|---|---|---|---|---|---|
| arXiv Atom | `entry/title` 折叠空白 | `entry/author/name` | `published[:4]` | `arxiv:journal_ref` | `arxiv:doi` | `id` → `parse_arxiv` | `ARXIV` |
| Crossref | `item.title[0]` | `given + family` | `issued.date-parts[0][0]`（缺则 `published-print`/`published-online`） | `container-title[0]` | `item.DOI` | — | `proceedings-article`→`CONFERENCE`，否则 `WEB` |
| OpenAlex | `display_name` | `authorships[].author.display_name` | `publication_year` | `primary_location.source.display_name` | `work.doi` | — | `conference-paper`→`CONFERENCE`，否则 `WEB` |

- `ArxivProvider.search()`：`params={"search_query": f'all:"{query}"', "start": 0, "max_results": limit, "sortBy": "relevance"}`。
- `CrossrefProvider.search()`：`params={"query.bibliographic": query, "rows": limit, "select": "DOI,title,author,issued,container-title,type,URL,abstract"}`。
- `OpenAlexProvider.search()`：`params={"search": query, "per-page": limit, "select": "id,doi,display_name,publication_year,authorships,primary_location,type"}`。
- 三者共用 `_get_json_or_text()`：捕获 `httpx.HTTPError` 与解析异常，抛 `ProviderError(FailureType.NETWORK_ERROR)`。
- `FixtureProvider(dir)`：读目录下 `*.json`（list of dict），按 `limit` 切片，`provider_rank` 重编。
- `build_providers(names, client=None)`：名字 → 实例；未知名字抛 `ValueError`。

- [ ] **Step 4: 跑通** — 6 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(sources): arxiv/crossref/openalex/fixture search providers"`

---

### Task 5: 聚类、版本合并与核验

**Files:** Create `src/research_os/sources/verification.py`, `src/research_os/sources/resolver.py`; Test `tests/unit/test_resolver.py`, `tests/unit/test_verification.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import SourceCandidate
from research_os.sources.resolver import resolve_candidates

AUTODIR_ARXIV = SourceCandidate(provider="arxiv", provider_rank=8,
    title="AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion",
    authors=["Yitong Jiang", "Zhaoyang Zhang", "Tianfan Xue", "Jinwei Gu"],
    year=2023, arxiv_id="2310.10123", arxiv_version="5", source_type=SourceType.ARXIV)
AUTODIR_ECCV = SourceCandidate(provider="openalex", provider_rank=2,
    title="AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion",
    authors=["Yitong Jiang", "Zhaoyang Zhang", "Tianfan Xue", "Jinwei Gu"],
    year=2024, doi="10.1007/978-3-031-73661-2_19", venue="Lecture notes in computer science",
    source_type=SourceType.CONFERENCE)

def test_arxiv_and_published_versions_merge_into_one_work():
    works = resolve_candidates([AUTODIR_ARXIV, AUTODIR_ECCV])
    assert len(works) == 1
    assert len(works[0].versions) == 2
    assert works[0].canonical_version.source_tier == SourceTier.OFFICIAL_PUBLICATION
    assert all(v.work_id == works[0].work.id for v in works[0].versions)

def test_arxiv_version_bump_collapses_to_latest_version():
    v1 = AUTODIR_ARXIV.model_copy(deep=True); v1.arxiv_version = "1"
    works = resolve_candidates([v1, AUTODIR_ARXIV])
    assert len(works) == 1 and len(works[0].versions) == 1
    assert works[0].versions[0].version == "5"

def test_same_doi_from_two_providers_merges_metadata():
    a = AUTODIR_ECCV.model_copy(deep=True); a.venue = None; a.provider = "crossref"
    works = resolve_candidates([a, AUTODIR_ECCV])
    assert len(works[0].versions) == 1
    assert works[0].versions[0].venue == "Lecture notes in computer science"

def test_title_match_with_conflicting_authors_does_not_merge():
    other = AUTODIR_ECCV.model_copy(deep=True)
    other.doi = None; other.provider = "crossref"
    other.authors = ["Someone Else", "Another Person"]
    works = resolve_candidates([AUTODIR_ARXIV, other])
    assert len(works) == 2
    assert any(w.ambiguous for w in works)
    assert any("SOURCE_IDENTITY_AMBIGUOUS" in n for w in works for n in w.notes)

def test_unverified_when_no_identifier_or_no_authors():
    anon = SourceCandidate(provider="fixture", title="Some blog post", url="https://x", source_type=SourceType.WEB)
    works = resolve_candidates([anon])
    sv = works[0].versions[0]
    assert sv.verified is False
    assert "no resolvable identifier" in sv.verification_notes
```

```python
from research_os.domain.enums import SourceTier, SourceType
from research_os.domain.models import SourceVersion
from research_os.sources.verification import assign_tier, verify_version

def test_assign_tier():
    assert assign_tier(SourceType.CONFERENCE, venue="CVPR", doi="10.1/x") == SourceTier.OFFICIAL_PUBLICATION
    assert assign_tier(SourceType.ARXIV, arxiv_id="2310.10123") == SourceTier.PREPRINT
    assert assign_tier(SourceType.REPOSITORY, url="https://github.com/x/y") == SourceTier.REPOSITORY
    assert assign_tier(SourceType.WEB, url="https://blog") == SourceTier.WEB

def test_verify_requires_identifier_title_and_authors():
    ok = SourceVersion(work_id="w", source_type=SourceType.ARXIV, title="T",
                       authors=["A B"], arxiv_id="2310.10123")
    assert verify_version(ok, ambiguous=False)[0] is True
    no_author = ok.model_copy(); no_author.authors = []
    verified, notes = verify_version(no_author, ambiguous=False)
    assert verified is False and "no authors" in notes
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`verification.py`：

```python
def assign_tier(source_type, venue=None, doi=None, arxiv_id=None, url=None) -> SourceTier:
    if doi and venue:
        return SourceTier.OFFICIAL_PUBLICATION
    if arxiv_id:
        return SourceTier.PREPRINT
    if source_type == SourceType.REPOSITORY:
        return SourceTier.REPOSITORY
    if source_type == SourceType.WEB:
        return SourceTier.WEB
    return SourceTier.UNKNOWN


def verify_version(sv: SourceVersion, ambiguous: bool = False) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not sv.doi and not sv.arxiv_id:
        notes.append("no resolvable identifier")
    if not sv.title.strip():
        notes.append("no title")
    if not sv.authors:
        notes.append("no authors")
    if ambiguous:
        notes.append("identity ambiguous (title match with conflicting authors)")
    if sv.source_tier == SourceTier.PREPRINT:
        notes.append("preprint: not peer-reviewed")
    return (not notes or notes == ["preprint: not peer-reviewed"], notes)
```

> 注意：`preprint` 只是提示，不应导致 unverified。故用"仅剩 preprint 提示则仍 verified"的判定，并写注释说明理由。

`resolver.py`：

```python
TITLE_SIMILARITY_THRESHOLD = 0.92
AUTHOR_OVERLAP_THRESHOLD = 0.5
YEAR_TOLERANCE = 1

@dataclass
class WorkResolution:
    work: ResearchWork
    versions: list[SourceVersion]
    canonical_version: SourceVersion
    ambiguous: bool = False
    notes: list[str] = field(default_factory=list)

def resolve_candidates(candidates) -> list[WorkResolution]:
    # 1) 增量聚类（DOI > arXiv id > 标题+作者+年份）
    # 2) 簇内按版本键（doi / arxiv / title+year）合并候选，字段互补
    # 3) tier + 核验 + canonical 选择
```

`_matches` 与合并、canonical 逻辑按 spec §8 实现；`provider` 来源写进 `verification_notes` 便于审计。

- [ ] **Step 4: 跑通** — 7 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(sources): work clustering, version merge, verification"`

---

### Task 6: 发现循环与 supervisor 集成

**Files:** Create `src/research_os/sources/discovery.py`; Modify `orchestration/supervisor.py`; Test `tests/integration/test_source_discovery.py`

- [ ] **Step 1: 写失败测试**

```python
"""Offline end-to-end: recorded provider payloads -> works -> verified versions."""
import httpx, json
from pathlib import Path
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlEvidenceRepository, SqlSourceCandidateRepository, SqlSourceVersionRepository,
    SqlWorkRepository,
)
from research_os.sources.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"

def _recorded_client():
    xml = (FIX / "arxiv_all_in_one.xml").read_text(encoding="utf-8")
    cr = json.loads((FIX / "crossref_restormer.json").read_text(encoding="utf-8"))
    ox = json.loads((FIX / "openalex_all_in_one.json").read_text(encoding="utf-8"))
    def handler(request):
        host = request.url.host
        if "arxiv" in host: return httpx.Response(200, text=xml)
        if "crossref" in host: return httpx.Response(200, json=cr)
        return httpx.Response(200, json=ox)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return [ArxivProvider(client=client), CrossrefProvider(client=client), OpenAlexProvider(client=client)]

def test_discovery_produces_merged_verified_works_without_evidence(db):
    with session_scope() as session:
        sup = Supervisor(session, providers=_recorded_client())
        run = sup.create_run("Does spatial degradation conditioning improve all-in-one image restoration?")
        result = sup.run_source_discovery(run.id, limit=10)

        assert result["candidates"] >= 10
        assert result["works"] >= 5
        # AutoDIR: arXiv preprint + ECCV version -> one work, two versions
        autodir = [w for w in result["resolutions"] if "autodir" in w.work.canonical_title.lower()]
        assert len(autodir) == 1 and len(autodir[0].versions) == 2
        # verified vs unverified must be distinguishable
        versions = SqlSourceVersionRepository(session).list_by_run(run.id)
        assert any(v.verified for v in versions)
        # search snippets never become evidence
        assert SqlEvidenceRepository(session).list_all() == []
        # candidates persisted with provider metadata
        assert len(SqlSourceCandidateRepository(session).list_by_run(run.id)) == result["candidates"]
        # budget counted by the supervisor
        assert sup.get_run(run.id).budget.search_calls >= 3
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`discovery.py`：`collect_candidates(providers, queries, limit, before_search=None, on_error=None)` → `(candidates, errors)`；每次搜索前调用 `before_search(provider_name) -> bool`（返回 False 即停止）。

`Supervisor.__init__(..., providers=None)`；`run_source_discovery(run_id, limit=15, max_queries=2)`：

1. 取 run/question，`_transition(RESEARCHING, "discover")`
2. `create_task(DISCOVER_SOURCES)`
3. `before_search` 钩子：`budget.search_calls += 1` 并持久化；`budget.exceeded()` 则记 `BUDGET_EXCEEDED` 并返回 False
4. `collect_candidates` → 候选落库（`create_many`）
5. `resolve_candidates` → 逐 work/version 落库（`run_id` 归属）→ `attach_resolution` 回填候选的 work/version id
6. 事件：`SOURCE_DISCOVERED`（候选数）、每个 verified 版本一条 `SOURCE_VERIFIED`、每个歧义/未核验一条 `FAILURE`（`SOURCE_IDENTITY_AMBIGUOUS` / `SOURCE_UNAVAILABLE`）、provider 错误一条 `FAILURE`
7. `budget.sources_discovered += len(candidates)`；`complete_task`
8. 返回 `{"run_id", "queries", "candidates", "works", "verified", "unverified", "resolutions", "errors"}`

- [ ] **Step 4: 跑通** — `pytest tests/integration/test_source_discovery.py -q` → 1 passed
- [ ] **Step 5: 全量回归** — `pytest -q` → 全绿
- [ ] **Step 6: Commit** — `git commit -m "feat(orchestration): supervisor-driven source discovery"`

---

### Task 7: CLI 与 API

**Files:** Modify `cli.py`, `main.py`; Test `tests/unit/test_cli_sources.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.cli import main

def test_sources_command_lists_works_and_versions(tmp_path, capsys, db):
    # arrange: run discovery offline via supervisor, then call CLI
    ...
    assert main(["sources", run_id]) == 0
    out = capsys.readouterr().out
    assert "verified" in out
```

- [ ] **Step 2-4:** `discover`（`--question --limit --fixture DIR`）与 `sources RUN_ID`；`GET /research/{run_id}/sources` 返回 `{"works": [...], "versions": [...]}`。跑通测试。
- [ ] **Step 5: Commit** — `git commit -m "feat(cli,api): discover and sources inspection"`

---

### Task 8: 真实网络冒烟 + 人工验收 + 文档

**Files:** Create `tests/integration/test_live_providers.py`; Modify `README.md`, `architect.md`, `human_decision.md`

- [ ] **Step 1: 冒烟测试（默认 skip）**

```python
import os, pytest
pytestmark = pytest.mark.skipif(os.environ.get("RESEARCHOS_NETWORK_TESTS") != "1",
                                reason="set RESEARCHOS_NETWORK_TESTS=1 to hit live APIs")

def test_live_arxiv_and_openalex_are_parseable():
    from research_os.sources.providers import ArxivProvider, OpenAlexProvider
    assert len(ArxivProvider().search("all-in-one image restoration", limit=3)) == 3
    assert len(OpenAlexProvider().search("all-in-one image restoration", limit=3)) == 3
```

- [ ] **Step 2: 真实批量闸门测试**

```python
pytestmark = pytest.mark.skipif(..., )
def test_live_discovery_meets_phase2_acceptance(db):
    with session_scope() as session:
        sup = Supervisor(session)
        run = sup.create_run("Does spatial degradation conditioning provide value beyond feature conditioning in all-in-one image restoration?")
        res = sup.run_source_discovery(run.id, limit=10)
        assert res["candidates"] >= 10
        assert res["works"] >= 5
```

- [ ] **Step 3: 跑** — `RESEARCHOS_NETWORK_TESTS=1 pytest tests/integration/test_live_providers.py -q` → 2 passed
- [ ] **Step 4: 更新三份文档**（README 状态/命令、architect 阶段表 + ADR-009/010 + 维护记录、human_decision 追加 HD-007）
- [ ] **Step 5: Commit + 打 tag**（`git tag w2-p2`）

---

## Self-Review

- **Spec 覆盖**：§5 规范化→Task 1；§7 查询→Task 2；§4/§10 模型与持久化→Task 3；§6 provider→Task 4；§8/§9 聚类与核验→Task 5；§11 编排与接口→Task 6/7；§2 验收→Task 6/8；§12 测试→各 Task。无缺口。
- **占位符**：Task 7 Step 1 的 arrange 段落以省略号表示，需在写测试时替换为真实构造（不得留 `...`）。
- **类型一致性**：`WorkResolution.canonical_version` 为属性/字段统一定义为 dataclass 字段；`resolve_candidates` 返回 `list[WorkResolution]`；supervisor 返回 dict 键在 Task 6 与 Task 8 保持一致（`candidates`/`works`/`resolutions`）。
