# P3 证据质量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让证据可查、可定位、可数值比较：多格式加载 + 分块落库 + 精确字符偏移 + 位置强校验 + 定量证据结构化（计划 §15）。

**Architecture:** 加载器扩到 HTML；`DocumentChunk` 落独立表使 `Evidence.chunk_id` 可解析；句子切分改为在原文上取区间以获得精确偏移；位置缺失的证据拒收并记事件；定量证据用确定性正则抽取后单独成表。

**Tech Stack:** Python 3.12（conda `reOS`）· Pydantic v2 · SQLAlchemy/SQLite · PyMuPDF · 标准库 `html.parser` · pytest。

**Spec:** `docs/superpowers/specs/2026-11-12-p3-evidence-quality-design.md`

---

## 文件结构

| 文件 | 变更 |
|---|---|
| `src/research_os/documents/html.py` | 新建：`load_html` / `html_to_pages`（stdlib HTMLParser） |
| `src/research_os/documents/loader.py` | 修改：分派 `.html/.htm`，README → `SourceType.README` |
| `src/research_os/domain/models.py` | 修改：`DocumentChunk` 无需改；`Evidence` 增加说明注释 |
| `src/research_os/storage/tables.py` | 修改：`ChunkRow`、`QuantitativeEvidenceRow` |
| `src/research_os/storage/repositories.py` | 修改：`SqlChunkRepository`、`SqlQuantitativeEvidenceRepository` |
| `src/research_os/research/evidence_extractor.py` | 修改：`_sentence_spans` 精确偏移；`has_location` 校验 |
| `src/research_os/research/quantitative.py` | 新建：确定性定量抽取 |
| `src/research_os/orchestration/supervisor.py` | 修改：落 chunks、位置校验、定量抽取 |
| `src/research_os/reporting/memo.py` | 修改：证据位置 + `# Quantitative Evidence` 段 + inspect 增强 |
| `tests/unit/test_html_loader.py` … | 新建 4 个测试文件 + 1 个集成测试 |

---

### Task 1: HTML 加载

**Files:** Create `documents/html.py`; Modify `documents/loader.py`; Test `tests/unit/test_html_loader.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.domain.enums import SourceType
from research_os.documents.html import html_to_pages
from research_os.documents.loader import load_document, source_type_for

HTML = """<html><head><style>.x{}</style><script>alert(1)</script></head>
<body><nav>menu</nav>
<h1>Restormer</h1><p>Efficient transformer for high-resolution restoration.</p>
<h2>Results</h2><p>PSNR 39.18 dB on SIDD &amp; 0.42 dB gain on Rain100H.</p>
<ul><li>Tested on GoPro.</li></ul>
<footer>copyright</footer></body></html>"""

def test_html_sections_and_boilerplate():
    pages = html_to_pages(HTML)
    sections = [p.section for p in pages]
    assert sections == ["Restormer", "Results", "Results"]
    assert all("alert" not in p.text and "menu" not in p.text and "copyright" not in p.text for p in pages)
    assert any("&" in p.text for p in pages)          # entity unescaped
    assert all(p.page_label == "html" and p.page_index == 0 for p in pages)

def test_load_document_dispatches_html(tmp_path):
    f = tmp_path / "page.html"; f.write_text(HTML, encoding="utf-8")
    pages = load_document(f, "auto")
    assert pages and any(p.section == "Results" for p in pages)

def test_source_type_detects_html_and_readme(tmp_path):
    assert source_type_for(tmp_path / "a.html") == SourceType.HTML
    assert source_type_for(tmp_path / "README.md") == SourceType.README
    assert source_type_for(tmp_path / "notes.md") == SourceType.MARKDOWN
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/unit/test_html_loader.py -q` → ImportError
- [ ] **Step 3: 实现** `html.py`：`_HtmlTextParser(HTMLParser)`，`handle_starttag` 处理 `h1..h6`（开新节）/`p,li,blockquote,pre,td`（开新块）/`script,style,nav,footer,header,aside,form`（置 `_skip=True`）；`handle_endtag` 收块；`handle_data` 累积（`html.unescape`）；`html_to_pages` 折叠空白、丢弃空块。`loader.py` 增加 `.html/.htm` 分派与 README 识别。
- [ ] **Step 4: 跑通** — 3 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(documents): html loader with heading-based sections"`

---

### Task 2: 分块持久化

**Files:** Modify `storage/tables.py`, `storage/repositories.py`; Test `tests/unit/test_chunk_store.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.documents.chunks import chunk_pages
from research_os.documents.loader import load_markdown
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlChunkRepository

FIX = Path(__file__).resolve().parents[1] / "fixtures"

def test_chunks_roundtrip_with_provenance(db):
    chunks = chunk_pages(load_markdown(FIX / "sample_paper.md"), source_version_id="sv_1")
    with session_scope() as s:
        SqlChunkRepository(s).create_many(chunks)
    with session_scope() as s:
        got = SqlChunkRepository(s).list_by_source("sv_1")
        assert len(got) == len(chunks)
        assert got[0].content_hash == chunks[0].content_hash
        assert got[0].section == chunks[0].section
        assert SqlChunkRepository(s).get(chunks[0].id).text == chunks[0].text
```

- [ ] **Step 2: 运行确认失败** — ImportError
- [ ] **Step 3: 实现** `ChunkRow`（id/source_version_id/page_index/page_label/section/chunk_index/text/content_hash，`source_version_id` 建索引）与 `SqlChunkRepository`（`create_many` / `get` / `list_by_source`）。
- [ ] **Step 4: 跑通** — 1 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(storage): persist document chunks with provenance"`

---

### Task 3: 精确字符偏移 + 位置强校验

**Files:** Modify `research/evidence_extractor.py`; Test `tests/unit/test_evidence_offsets.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.domain.models import DocumentChunk
from research_os.research.evidence_extractor import (
    HeuristicEvidenceExtractor, has_location, sentence_spans,
)

TEXT = ("On the Rain100H benchmark, our method improves PSNR by 0.42 dB and SSIM by 0.013. "
        "On SIDD the method achieves 39.18 dB compared with 39.01 dB for the baseline.")

def test_sentence_spans_preserve_offsets_and_decimals():
    spans = sentence_spans(TEXT)
    assert len(spans) == 2
    for start, end, sentence in spans:
        assert TEXT[start:end] == sentence
    assert "39.18 dB" in spans[1][2]

def test_evidence_offsets_point_at_original_text():
    chunk = DocumentChunk(source_version_id="sv_1", chunk_index=0, text=TEXT, section="Results", page_index=0, page_label="md")
    evidence = HeuristicEvidenceExtractor().extract([chunk])
    assert evidence
    for ev in evidence:
        assert ev.char_start is not None and ev.char_end is not None
        assert chunk.text[ev.char_start:ev.char_end] == ev.text
        assert ev.content_hash

def test_has_location_flags_evidence_without_provenance():
    from research_os.domain.models import Evidence
    located = Evidence(source_version_id="sv", text="x", chunk_id="c1", page_label="p.1")
    bare = Evidence(source_version_id="sv", text="x")
    assert has_location(located) is True
    assert has_location(bare) is False
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**

```python
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Sentence (start, end, text) intervals over the ORIGINAL text.

    Splitting must not rewrite the text: evidence offsets are only trustworthy
    if text[start:end] is exactly the quoted sentence. Decimal points are safe
    because the boundary requires whitespace after the punctuation.
    """
    spans, start = [], 0
    for match in _BOUNDARY.finditer(text):
        end = match.start()
        spans.append((start, end, text[start:end].strip()))
        start = match.end()
    spans.append((start, len(text), text[start:].strip()))
    return [(s, s + len(t), t) for s, e, t in spans if t]  # recompute end after strip
```

实现要点：`extract()` 遍历 `sentence_spans(chunk.text)`，用 `(start, start+len(sentence))` 作为偏移（strip 后重新计算），boilerplate/最短长度/去重规则不变。

`has_location(ev)`：`bool(ev.chunk_id or ev.section or ev.page_label)`。

- [ ] **Step 4: 跑通** — 3 passed（注意：旧的 `_split_sentences` 若被其它模块引用需保留或同步改名）
- [ ] **Step 5: Commit** — `git commit -m "fix(evidence): exact character offsets from original chunk text"`

---

### Task 4: 定量证据抽取

**Files:** Create `research/quantitative.py`; Modify `storage/tables.py`, `storage/repositories.py`; Test `tests/unit/test_quantitative.py`

- [ ] **Step 1: 写失败测试**

```python
from research_os.research.quantitative import HeuristicQuantitativeExtractor

def test_extracts_metric_value_and_dataset():
    facts = HeuristicQuantitativeExtractor().extract_from_text(
        "On SIDD, the method achieves 39.18 dB PSNR compared with 39.01 dB for the baseline.", evidence_id="e1")
    assert facts[0].metric == "PSNR"
    assert facts[0].value == 39.18
    assert facts[0].comparator_value == 39.01
    assert facts[0].dataset == "SIDD"
    assert facts[0].protocol == "dB"

def test_extracts_gain_with_dataset_in_same_sentence():
    facts = HeuristicQuantitativeExtractor().extract_from_text(
        "On the Rain100H benchmark, our method improves the baseline PSNR by 0.42 dB and SSIM by 0.013.", evidence_id="e2")
    metrics = {f.metric for f in facts}
    assert {"PSNR", "SSIM"} <= metrics
    psnr = next(f for f in facts if f.metric == "PSNR")
    assert psnr.value == 0.42 and psnr.dataset == "Rain100H" and psnr.protocol == "dB"

def test_ignores_text_without_metric_or_value():
    assert HeuristicQuantitativeExtractor().extract_from_text("We propose a gated attention block.", evidence_id="e3") == []
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** `_METRIC = re.compile(r"\b(PSNR|SSIM|LPIPS|FID|MAE|MSE)\b", re.I)`；对每个指标匹配，在其后 ≤16 字符内取第一个数字（`(\d+(?:\.\d+)?)`）；dataset 用词表 + `\bon (?:the )?([A-Z][A-Za-z0-9\-]{2,})`；comparator_value 用 `compared (?:with|to)\s+(\d+(?:\.\d+)?)` 或 `from\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)`（后者 value=to）；protocol：含 `dB` → "dB"，含 `%` → "percent"。返回 `list[QuantitativeEvidence]`，与 `HeuristicEvidenceExtractor` 同风格 `extract(evidence: list[Evidence])`。
  表：`quantitative_evidence(evidence_id PK/FK, dataset, metric, method, value, comparator, comparator_value, protocol)`；仓储 `create_many` / `list_by_evidence` / `list_all`。
- [ ] **Step 4: 跑通** — 4 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(evidence): deterministic quantitative evidence extraction"`

---

### Task 5: 编排与呈现

**Files:** Modify `orchestration/supervisor.py`, `reporting/memo.py`; Test `tests/integration/test_evidence_quality.py`

- [ ] **Step 1: 写失败测试**

```python
def test_vertical_slice_persists_chunks_offsets_and_quantitative_facts(tmp_path, db):
    # run_vertical_slice on sample_paper.md
    # assert: chunks in DB; every evidence.chunk_id resolvable;
    #         chunk.text[start:end] == evidence.text;
    #         >= 3 quantitative rows; memo contains "# Quantitative Evidence"
    ...

def test_evidence_without_location_is_rejected(db):
    # inject a chunk-free evidence by monkeypatching the extractor to return an
    # evidence without chunk_id/page_label/section -> not persisted + FAILURE event
    ...
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：supervisor 在 chunk 生成后 `SqlChunkRepository.create_many`；抽取后过滤 `has_location`，缺失者记 `CITATION_LOCATION_MISSING` 事件并计入 warnings；再跑定量抽取落库；memo 增加位置与 `# Quantitative Evidence` 段（按 dataset+metric 分组，附「跨数据集不可直接比较」提示）；`inspect_claim` 增加 `chunk_id/section/page_label/char_range`。
- [ ] **Step 4: 跑通** — 2 passed
- [ ] **Step 5: 全量回归** — `pytest` 全绿
- [ ] **Step 6: Commit** — `git commit -m "feat(orchestration): persist chunks, gate provenance, wire quantitative evidence"`

---

### Task 6: 文档与验收

**Files:** `README.md`, `architect.md`, `human_decision.md`

- [ ] **Step 1** 更新 README（P3 状态、支持格式、测试数）
- [ ] **Step 2** 更新 architect（阶段表 P3 ✅、ADR-014/015/016、维护记录）
- [ ] **Step 3** human_decision 追加 HD-009（第三天范围 = P3；HTML 用标准库而非 bs4 属实现派生决策，登记在 architect ADR-014）
- [ ] **Step 4** 真实跑一次垂直切片，记录产物（证据数/定量条数/memo 片段）
- [ ] **Step 5** Commit + tag `w2-p3`

---

## Self-Review

- **Spec 覆盖**：D1→Task 2；D2→Task 3；D3→Task 3/5；D4→Task 1；D5→Task 4；§7 呈现→Task 5；§9 验收→Task 5/6。
- **占位符**：Task 5 测试步骤用注释描述断言要点，实施时须写成真实断言（不得留 `...`）。
- **类型一致性**：`sentence_spans` 返回 `(start, end, sentence)`；`has_location(Evidence) -> bool`；仓储命名 `SqlChunkRepository.list_by_source`、`SqlQuantitativeEvidenceRepository.list_by_evidence`。
