# 方法获取能力度量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-11-14-method-acquisition-measurement-design.md`，对 40 篇留出集论文做一次只读度量，产出可复跑的审计脚本、标注夹具与评估报告；不改任何生产代码。

**Architecture:** `labels.json`（40 篇 × 4 层，owner-derived 且先冻结）是唯一标注输入；`scripts/method_acquisition_audit.py` 用现有 pipeline 逐篇重算系统侧认领对象，经纯函数 `summarise(labels, sides, domain_size)` 汇总三个数字。计算与 I/O 分离，使回归测试能用合成夹具注入 `sides`、断言具体数值。标注阶段与系统产出严格隔离。

**Tech Stack:** Python 3.11+ / pydantic models / `load_html` + `chunk_pages` / `HeuristicEvidenceExtractor` / `HeuristicQuantitativeExtractor` / `HeuristicClaimBuilder` / pytest。

---

## 文件结构

| 文件 | 职责 | 状态 |
|---|---|---|
| `tests/fixtures/method_acquisition/labels.json` | 160 格标注（唯一标注输入，含证据片段） | 新建，Task 1 冻结 |
| `tests/fixtures/method_acquisition/ANNOTATION.md` | 协议、逐条依据、诚实性声明、隔离顺序记录 | 新建，Task 1 冻结 |
| `scripts/method_acquisition_audit.py` | 校验 labels、重算系统侧、汇总、打印 | 新建，Task 3 |
| `tests/unit/test_method_acquisition_audit.py` | 合成夹具上的强断言 + 变异锚点 | 新建，Task 2 |
| `docs/evaluation/2026-11-14-method-acquisition-audit.md` | 三层数字、缺口分布、待办登记 | 新建，Task 4 |
| `docs/evaluation/holdout-ids-2026-11-14-agent-in-mc.txt` | Agent in MC 20 篇清单（已存在于工作树，未跟踪） | 提交，Task 1 |
| `README.md` / `architect.md` / `human_decision.md` | 同步度量能力与诚实性口径 | 修改，Task 5 |
| `docs/superpowers/specs/2026-11-14-method-acquisition-measurement-design.md` §10 | 实施偏差登记 | 修改，Task 5 |

**不新增**任何 `src/` 文件；`protocol` 单位字段不参与度量。

## 全局约束（每个 Task 都适用）

- 解释器 `D:/Anaconda/envs/reOS/python.exe`；pytest 用 `--basetemp=.pytest_tmp_mam`（仓库 `.pytest_tmp` 有残留会触发安全删除守卫）。
- 严格 TDD：先写会失败的测试、看到真实红灯、再写实现。
- 每个 Task 单独提交，提交信息写「为什么」。
- **隔离防线**：Task 1 完成并冻结提交之前，禁止读取或运行 `src/research_os/research/*` 的抽取产物、禁止运行审计脚本。Task 1 的子 agent prompt 必须显式包含这条禁令。
- 报告禁用「准确率 / quality / agreement / 正确率」等词。

---

### Task 1: 冻结标注夹具（隔离阶段）

**Files:**
- Create: `tests/fixtures/method_acquisition/labels.json`
- Create: `tests/fixtures/method_acquisition/ANNOTATION.md`
- Commit: `docs/evaluation/holdout-ids-2026-11-14-agent-in-mc.txt`

- [ ] **Step 1: 提交留出集清单并建目录**

```bash
cd /d/ResearchOS
mkdir -p tests/fixtures/method_acquisition
git add docs/evaluation/holdout-ids-2026-11-14-agent-in-mc.txt
git commit -m "data(eval): record the 20 Agent-in-MC hold-out paper ids"
```

预期：`git status --short` 只剩 `?? tests/fixtures/method_acquisition/`（空目录不显示则为 clean）。

- [ ] **Step 2: 导出候选证据（只读，仅看 HTML 原文）**

运行下列只读命令。它**只**用 `load_html` / `chunk_pages` 把原文按章节切块并打印，`Heuristic*` 抽取器一律不得调用。输出重定向到 gitignored 的 `.holdout_cache/annotation_candidates.txt`，按 `arxiv_id | domain | section | chunk_index | quote` 每行一条，每篇最多 40 行、每层各取最相关若干行。

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe - > .holdout_cache/annotation_candidates.txt <<'PY'
from pathlib import Path
from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html

for name, domain in (
    ("docs/evaluation/holdout-ids-2026-11-12.txt", "image_restoration"),
    ("docs/evaluation/holdout-ids-2026-11-14-agent-in-mc.txt", "agent_in_mc"),
):
    for aid in [x.strip() for x in Path(name).read_text(encoding="utf-8").splitlines() if x.strip()]:
        chunks = chunk_pages(load_html(Path(".holdout_cache") / f"{aid}.html"), f"sv_{aid}")
        for chunk in chunks[:40]:
            quote = " ".join(chunk.text.split())[:40]
            section = chunk.section or "(none)"
            print(f"{aid}\t{domain}\t{section}\t{chunk.chunk_index}\t{quote}")
PY
wc -l .holdout_cache/annotation_candidates.txt
```

预期：40 个不同 `arxiv_id`，行数 ≤1600。此文件在 `.holdout_cache/`，不提交。

- [ ] **Step 3: 逐层判定并生成 labels.json**

按 spec §4 的逐层 `present` 判据，读候选证据并在必要时回看 `.holdout_cache/{id}.html` 原句，为 40 篇 × 4 层各定一个 `label`。`present` 必须附至少一条 `evidence`，字段按 spec §4 schema：`section`（可为 null）、`page_label`、`chunk_index`、`quote`（≤40 Unicode 字符，句内唯一可定位子串）。`section=null` 时必须有 `page_label` 或 `chunk_index`。

生成命令（把判定结果写成一个 JSON 后由校验器检查）：

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe - <<'PY'
import json
from pathlib import Path

# ROWS 由标注者逐篇填入；此处给出结构契约，实际为 40 个对象。
# 每个对象：arxiv_id, domain, layers.{L1..L4}.{label, evidence}
out = Path("tests/fixtures/method_acquisition/labels.json")
data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"labels": []}

LAYERS = ("L1", "L2", "L3", "L4")
LABELS = {"present", "absent", "ambiguous"}
DOMAINS = {"image_restoration", "agent_in_mc"}
rows = data["labels"]
assert len(rows) == 40, f"expected 40 papers, got {len(rows)}"
ids = [r["arxiv_id"] for r in rows]
assert len(set(ids)) == 40, "duplicate arxiv_id"
assert {r["domain"] for r in rows} == DOMAINS
for r in rows:
    assert set(r["layers"]) == set(LAYERS), f"{r['arxiv_id']}: incomplete layers"
    for layer in LAYERS:
        cell = r["layers"][layer]
        assert cell["label"] in LABELS, f"{r['arxiv_id']}/{layer}: bad label"
        if cell["label"] == "present":
            assert cell["evidence"], f"{r['arxiv_id']}/{layer}: present without evidence"
            for ev in cell["evidence"]:
                assert len(ev["quote"]) <= 40, f"{r['arxiv_id']}/{layer}: quote too long"
                assert ev["quote"].strip(), "empty quote"
                assert (ev["section"] is not None
                        or ev["page_label"] is not None
                        or ev["chunk_index"] is not None), "no location"
print(f"OK: {len(rows)} papers, {len(rows) * 4} cells, "
      f"{sum(c['label'] == 'present' for r in rows for c in r['layers'].values())} present")
PY
```

预期：`OK: 40 papers, 160 cells, N present`。**这一步必须由子 agent 真正逐篇读原文完成，不得用规则批量推断 label**——用规则推断正是 spec §5 禁止的「不可靠信号替代证据」。

- [ ] **Step 4: 写 ANNOTATION.md（完整文本骨架）**

```markdown
# 方法获取度量 · 标注说明

本夹具是 **owner-derived**（由本会话 owner 侧的 agent 逐篇阅读缓存 HTML 原文得出），
**不是独立标注、不是盲标**。不得用于计算任何正确率、一致率或质量结论；
`present` 只作为可获取率 `A` 与系统覆盖率 `C` 的分母。
`tests/fixtures/contradiction/ANNOTATION.md` 记录的 self-consistency 教训同样适用。

## 隔离顺序

1. 标注阶段：先只读 HTML 原文，产出 160 格判定与证据片段，写入 `labels.json`。
2. 本文件与 `labels.json` 在同一个提交中冻结；该提交即隔离顺序的证据，
   复核者可用 `git log --oneline -- tests/fixtures/method_acquisition/` 核对。
3. 冻结之后才实现、运行 `scripts/method_acquisition_audit.py`。
   标注阶段禁止查看 `claims` / `quantitative_evidence` / `identity_key` / `conditions`
   等系统侧产出，也禁止运行审计脚本。

## 逐层判据

（逐字抄录 spec §4 的「逐层 present 判据」表与「规则」段。）

## 逐条依据

（40 篇 × 4 层：每格给出 label；`present` 附 `section` + quote，`absent` /
`ambiguous` 给出一句理由。`ambiguous` 单独列出，不并入任何比率。）

## 已知限制

- 标注由同一侧产生，存在主观性；`ambiguous` 即为主观边界的显式出口。
- 本夹具不回答「系统抽得对不对」。
```

在 `## 隔离顺序` 之前新增一行「标注时间：」并记录实际读文起止时间（UTC+8）；
逐层判据表与规则段逐字抄录 spec §4；「逐条依据」40 篇 × 4 层每格给出 label，
`present` 附 `section` + quote，`absent` / `ambiguous` 各给一句理由。

- [ ] **Step 5: 冻结提交（先于任何脚本）**

```bash
cd /d/ResearchOS
git add tests/fixtures/method_acquisition/labels.json tests/fixtures/method_acquisition/ANNOTATION.md
git commit -m "data(eval): freeze the owner-derived method-acquisition labels

Frozen before any audit code exists: the present counts are the denominator of
the coverage ratio, so they must not be influenced by seeing system output."
git rev-parse HEAD   # 记入 ANNOTATION.md 的冻结 SHA，若已填入则核对一致
```

- [ ] **Step 6: 独立审验 Task 1**

派子 agent 只读核对：160 格齐全、`present` 有证据、`section=null` 有替代定位、`ambiguous` 单列、`ANNOTATION.md` 首段声明与隔离顺序齐全、提交历史里标注提交早于任何脚本提交。输出 `Approved: YES/NO` + 问题清单。按相同流程修订到 YES。

---

### Task 2: TDD 红灯 — 强断言测试

**Files:**
- Test: `tests/unit/test_method_acquisition_audit.py`

- [ ] **Step 1: 写失败测试（完整文件）**

```python
"""Synthetic fixtures pin the arithmetic; real labels are checked for contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.method_acquisition_audit import (
    load_labels,
    summarise,
    covered_for,
    cause_for,
    PLACEHOLDER_METHOD,
)

DOMAINS = ("d0", "d1")
LAYERS = ("L1", "L2", "L3", "L4")


def _cell(label, quote=None):
    evidence = [] if quote is None else [
        {"section": "Method", "page_label": None, "chunk_index": 0, "quote": quote}
    ]
    return {"label": label, "evidence": evidence}


def _row(arxiv_id, domain, spec):
    return {
        "arxiv_id": arxiv_id,
        "domain": domain,
        "layers": {layer: _cell(spec[layer][0], spec[layer][1]) for layer in LAYERS},
    }


# present/absent/ambiguous are arranged so every branch below has one hit.
LABELS = [
    _row("a1", "d0", {"L1": ("present", "we introduce A"),
                      "L2": ("absent", None),
                      "L3": ("present", "A routes skills"),
                      "L4": ("absent", None)}),
    _row("a2", "d0", {"L1": ("absent", None),
                      "L2": ("absent", None),
                      "L3": ("ambiguous", None),
                      "L4": ("present", "lr = 3e-4")}),
    _row("b1", "d1", {"L1": ("present", "B is a planner"),
                      "L2": ("present", "B uses a CNN"),
                      "L3": ("present", "B stores memory"),
                      "L4": ("present", "batch 32")}),
    _row("b2", "d1", {"L1": ("present", "B2 extends B"),
                      "L2": ("absent", None),
                      "L3": ("absent", None),
                      "L4": ("absent", None)}),
]

SIDES = {
    "a1": {"structured": True,  "proxy": 2, "L2": False, "L4": False, "empty": False},
    "a2": {"structured": False, "proxy": 0, "L2": False, "L4": True,  "empty": False},
    "b1": {"structured": False, "proxy": 1, "L2": True,  "L4": False, "empty": False},
    "b2": {"structured": True,  "proxy": 3, "L2": False, "L4": False, "empty": False},
}


def test_availability_and_coverage_values():
    report = summarise(LABELS, SIDES, domain_size=2)

    assert report["A"]["d0|L1"] == (1, 2)
    assert report["A"]["d0|L2"] == (0, 2)
    assert report["A"]["d1|L1"] == (2, 2)

    assert report["C"]["d0|L1"] == (1, 1)
    assert report["C"]["d0|L2"] == "N/A"
    assert report["C"]["d0|L3"] == (0, 1)
    assert report["C"]["d0|L4"] == (1, 1)
    assert report["C"]["d1|L1"] == (1, 2)
    assert report["C"]["d1|L2"] == (1, 1)
    assert report["C"]["d1|L4"] == (0, 1)


def test_covered_over_20_and_proxy_and_ambiguous():
    report = summarise(LABELS, SIDES, domain_size=2)

    assert report["covered_over_20"]["d0|L1"] == (1, 2)
    assert report["proxy"] == {"d0": 2, "d1": 4, "total": 6}
    assert report["ambiguous"] == {"total": 1, "d0|L3": 1}


def test_gap_causes_are_classified():
    report = summarise(LABELS, SIDES, domain_size=2)
    assert report["gaps"]["d0|L3|无结构化字段"] == 1
    assert report["gaps"]["d1|L1|无结构化字段"] == 1
    assert report["gaps"]["d1|L3|无结构化字段"] == 1
    assert report["gaps"]["d1|L4|无结构化字段"] == 1
    assert sum(report["gaps"].values()) == 4


def test_every_cell_is_traceable_to_an_arxiv_id():
    report = summarise(LABELS, SIDES, domain_size=2)
    assert len(report["cells"]) == 16
    assert {c["arxiv_id"] for c in report["cells"]} == {"a1", "a2", "b1", "b2"}
    assert all({"layer", "label", "covered"} <= set(c) for c in report["cells"])
    assert sum(1 for c in report["cells"] if c["covered"]) == 4
    assert sum(1 for c in report["cells"] if c["label"] == "ambiguous") == 1


def test_layer_mapping():
    assert covered_for("L1", SIDES["a1"]) is True
    assert covered_for("L1", SIDES["a2"]) is False
    assert covered_for("L2", SIDES["b1"]) is True
    assert covered_for("L3", SIDES["a1"]) is False
    assert covered_for("L4", SIDES["a2"]) is True
    assert cause_for("L3", SIDES["a1"]) == "无结构化字段"
    # Both other causes must be reachable, or cause_for could collapse to a
    # constant and every test above would still pass.
    empty_side = {"structured": False, "proxy": 0, "L2": False, "L4": False, "empty": True}
    assert cause_for("L4", empty_side) == "无来源定位"
    assert cause_for("L2", SIDES["a2"]) == "词表未覆盖"


def test_real_labels_pass_the_contract():
    """The frozen fixture must be loadable, not just the synthetic one."""
    path = Path(__file__).resolve().parents[2] / "tests/fixtures/method_acquisition/labels.json"
    rows = load_labels(path)
    assert len(rows) == 40
    assert len({r["arxiv_id"] for r in rows}) == 40


def test_load_labels_rejects_a_present_cell_without_evidence(tmp_path):
    bad = {"labels": [
        _row("x", "image_restoration", {layer: ("present", None) for layer in LAYERS})
    ]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="present without evidence"):
        load_labels(path)
```

- [ ] **Step 2: 跑测试看真实红灯**

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_method_acquisition_audit.py --basetemp=.pytest_tmp_mam
```

预期：`ModuleNotFoundError: No module named 'scripts.method_acquisition_audit'`。**记录该输出**；没有红灯不得写实现。

- [ ] **Step 3: 提交红灯测试**

```bash
cd /d/ResearchOS
git add tests/unit/test_method_acquisition_audit.py
git commit -m "test(eval): pin the method-acquisition arithmetic with synthetic cells"
```

---

### Task 3: 实现审计脚本（绿灯）

**Files:**
- Create: `scripts/method_acquisition_audit.py`

- [ ] **Step 1: 写最小实现（完整文件）**

```python
"""Read-only audit of method acquisition (spec 2026-11-14).

I/O is separate from arithmetic: `summarise` is a pure function so the tests can
inject synthetic system sides and assert exact numbers. No production code is
modified; the pipeline is only *observed*.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.research.claim_builder import HeuristicClaimBuilder
from research_os.research.evidence_extractor import HeuristicEvidenceExtractor
from research_os.research.quantitative import HeuristicQuantitativeExtractor

CACHE = Path(".holdout_cache")
LAYERS = ("L1", "L2", "L3", "L4")
LABELS = ("present", "absent", "ambiguous")
DOMAINS = ("image_restoration", "agent_in_mc")
PLACEHOLDER_METHOD = "proposed method"


def load_labels(path: Path) -> list[dict]:
    """Validate the frozen schema. A present cell without locatable evidence is
    rejected here so it can never quietly become a denominator."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["labels"]
    ids = [row["arxiv_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate arxiv_id in labels")
    for row in rows:
        if row["domain"] not in DOMAINS:
            raise ValueError(f"unknown domain: {row['domain']}")
        if set(row["layers"]) != set(LAYERS):
            raise ValueError(f"{row['arxiv_id']}: incomplete layers")
        for layer in LAYERS:
            cell = row["layers"][layer]
            if cell["label"] not in LABELS:
                raise ValueError(f"{row['arxiv_id']}/{layer}: bad label")
            if cell["label"] == "present":
                if not cell["evidence"]:
                    raise ValueError(f"{row['arxiv_id']}/{layer}: present without evidence")
                for ev in cell["evidence"]:
                    if len(ev["quote"]) > 40 or not ev["quote"].strip():
                        raise ValueError(f"{row['arxiv_id']}/{layer}: bad quote")
                    if (ev["section"] is None and ev["page_label"] is None
                            and ev["chunk_index"] is None):
                        raise ValueError(f"{row['arxiv_id']}/{layer}: evidence has no location")
    return rows


def _named_subject(claim) -> bool:
    if not claim.identity_key:
        return False
    subject = claim.identity_key.split("|")[0]
    return bool(subject) and not subject.startswith("self@")


def system_side(arxiv_id: str, cache: Path = CACHE) -> dict:
    """Observe (never modify) the current pipeline's output for one paper.

    `QuantitativeEvidence.protocol` deliberately does NOT appear: it stores a
    unit ("dB"/"percent"), not an evaluation protocol.
    """
    chunks = chunk_pages(load_html(cache / f"{arxiv_id}.html"), f"sv_{arxiv_id}")
    evidence = HeuristicEvidenceExtractor().extract(chunks)
    quantitative = HeuristicQuantitativeExtractor().extract(evidence)
    claims, _ = HeuristicClaimBuilder().build(
        evidence, quantitative=quantitative, chunks=chunks
    )
    conditions = [cond for claim in claims for cond in claim.conditions]
    return {
        "structured": any(
            q.method and q.method != PLACEHOLDER_METHOD for q in quantitative
        ),
        "proxy": sum(1 for claim in claims if _named_subject(claim)),
        "L2": any(cond.startswith(("backbone=", "baseline=")) for cond in conditions),
        "L4": any(cond.startswith("training=") for cond in conditions),
        "empty": not claims and not quantitative,
    }


def covered_for(layer: str, side: dict) -> bool:
    """The fixed claim-object mapping from spec section 5."""
    if layer == "L1":
        return bool(side["structured"])
    if layer == "L2":
        return bool(side["L2"])
    if layer == "L3":
        return False  # no field exists: structural absence, not an extraction error
    if layer == "L4":
        return bool(side["L4"])
    raise ValueError(f"unknown layer: {layer}")


def cause_for(layer: str, side: dict) -> str:
    """Direct reason a present cell was not covered. Three values only."""
    if side["empty"]:
        return "无来源定位"
    if layer == "L2":
        return "词表未覆盖"
    return "无结构化字段"


def summarise(labels: list[dict], sides: dict[str, dict], domain_size: int | None = None) -> dict:
    """`domain_size` exists for synthetic fixtures; None derives each domain's
    size from the labels so unequal corpora cannot share a wrong denominator."""
    sizes = Counter(row["domain"] for row in labels)
    present = Counter()
    covered = Counter()
    proxy = Counter()
    ambiguous = Counter()
    gaps = Counter()
    cells = []

    for row in labels:
        arxiv_id, domain = row["arxiv_id"], row["domain"]
        side = sides[arxiv_id]
        proxy[domain] += side["proxy"]
        for layer in LAYERS:
            cell = row["layers"][layer]
            label = cell["label"]
            hit = covered_for(layer, side) and label == "present"
            if label == "present":
                present[f"{domain}|{layer}"] += 1
                if hit:
                    covered[f"{domain}|{layer}"] += 1
                else:
                    gaps[f"{domain}|{layer}|{cause_for(layer, side)}"] += 1
            elif label == "ambiguous":
                ambiguous[f"{domain}|{layer}"] += 1
            cells.append({
                "arxiv_id": arxiv_id, "domain": domain, "layer": layer,
                "label": label, "covered": bool(hit),
            })

    domains = {row["domain"] for row in labels}
    A, C, over = {}, {}, {}
    for domain in domains:
        for layer in LAYERS:
            key = f"{domain}|{layer}"
            p, c = present[key], covered[key]
            size = domain_size if domain_size is not None else sizes[domain]
            A[key] = (p, size)
            C[key] = "N/A" if p == 0 else (c, p)
            over[key] = (c, size)

    proxy_out = {d: proxy[d] for d in domains}
    proxy_out["total"] = sum(proxy.values())
    ambiguous_out = dict(ambiguous)
    ambiguous_out["total"] = sum(ambiguous.values())
    return {
        "A": A, "C": C, "covered_over_20": over,
        "gaps": dict(gaps), "proxy": proxy_out,
        "ambiguous": ambiguous_out, "cells": cells,
    }


def print_report(report: dict) -> None:
    print("=== method acquisition audit ===")
    print("A = present/domain_size   C = covered/present (N/A when present=0)")
    print("C denominators differ per cell; do not compare C across layers.\n")
    for key in sorted(report["A"]):
        a = report["A"][key]
        c = report["C"][key]
        c_text = "N/A" if c == "N/A" else f"{c[0]}/{c[1]}"
        o = report["covered_over_20"][key]
        print(f"  {key:<28} A={a[0]}/{a[1]}  C={c_text:<8} covered/domain={o[0]}/{o[1]}")
    print("\n=== gap causes ===")
    for key, count in sorted(report["gaps"].items()):
        print(f"  {key:<40} {count}")
    print("\n=== proxy (claim subject, NOT section 15 method) ===")
    print(" ", dict(report["proxy"]))
    print("=== ambiguous (excluded from every ratio) ===")
    print(" ", dict(report["ambiguous"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()

    labels = load_labels(args.labels)
    sides = {row["arxiv_id"]: system_side(row["arxiv_id"], args.cache) for row in labels}
    report = summarise(labels, sides)
    print_report(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑测试确认绿灯**

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_method_acquisition_audit.py --basetemp=.pytest_tmp_mam
```

预期：`8 passed`。

- [ ] **Step 3: 变异验证（证明断言非空）**

在仓库外副本里把 `summarise` 的 `present[f"{domain}|{layer}"] += 1` 改成 `+= 0`，重跑同一测试，必须红在 `test_availability_and_coverage_values`；恢复后复跑绿。把两次输出记入 Task 报告。

- [ ] **Step 4: 提交**

```bash
cd /d/ResearchOS
git add scripts/method_acquisition_audit.py
git commit -m "feat(eval): read-only method-acquisition audit with pure arithmetic"
```

- [ ] **Step 5: 独立审验 Task 3**

派子 agent 只读核对：`protocol` 未参与、L3 恒 False、`structured` 排除常量占位符、`cause_for` 三值、纯函数边界、强断言是否会被删计算逻辑杀死。输出 `Approved: YES/NO`；按相同流程修订到 YES。

---

### Task 4: 跑真实语料并写评估报告

**Files:**
- Create: `docs/evaluation/2026-11-14-method-acquisition-audit.md`

- [ ] **Step 1: 跑 40 篇**

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json | tee /tmp/mam_report.txt
```

预期：8 行 `A/C/covered` 汇总 + 缺口分布 + proxy + ambiguous；`present=0` 的格子打印 `N/A`。

- [ ] **Step 2: 由脚本生成结果表格（不手抄、不留占位）**

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe - > /tmp/mam_tables.md <<'PY'
from pathlib import Path
from scripts.method_acquisition_audit import load_labels, system_side, summarise

labels = load_labels(Path("tests/fixtures/method_acquisition/labels.json"))
sides = {r["arxiv_id"]: system_side(r["arxiv_id"]) for r in labels}
r = summarise(labels, sides)
print("| 领域 | 层 | present | A | covered | C | covered/20 |")
print("|---|---|---|---|---|---|---|")
for key in sorted(r["A"]):
    domain, layer = key.split("|")
    p, size = r["A"][key]
    c = r["C"][key]
    ct = "N/A" if c == "N/A" else f"{c[0]}/{c[1]}"
    cov = 0 if c == "N/A" else c[0]
    o = r["covered_over_20"][key]
    print(f"| {domain} | {layer} | {p} | {p}/{size} | {cov} | {ct} | {o[0]}/{o[1]} |")
print("\n| 缺口成因 | 计数 |")
print("|---|---|")
for k, v in sorted(r["gaps"].items()):
    print(f"| {k} | {v} |")
print(f"\nproxy（claim subject，不等于 §15 的 method）：{r['proxy']}")
print(f"ambiguous（不计入任何比率）：{r['ambiguous']}")
PY
cat /tmp/mam_tables.md
```

- [ ] **Step 3: 写报告，把上一步输出原样粘进 §2 / §3**

```markdown
# 方法获取能力度量（2026-11-14）

> 复现：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`
> 标注：`tests/fixtures/method_acquisition/ANNOTATION.md`（owner-derived，非独立、非盲标）
> 本报告的 `C` 与项目既有 `coverage`（judged/total_before_cap）**不是同一指标、分母不同，两者无关**。

## 1. 语料与口径
40 篇（图像复原 20 / Agent in MC 20），4 层 × 2 领域 = 8 组。
`A = present/20`；`C = covered/present`，分母逐格不同，**不可跨层 / 跨领域比较**；
`present < 5` 的格子不作趋势解读；`present=0` 记 `N/A`。

## 2. 结果

## 3. 缺口分布

## 4. 读法边界
- L3 的 0 来自**结构性缺失**（无对应字段），不是抽取错误。
- 本报告只量可获取性与覆盖率，不建 gold label，不报任何准确率或质量结论。

## 5. 待办登记
- 既有 `coverage 100%` 的口径问题（scope skip 计入 `judged`）：独立立项。
- §2.5 未逐项登记 deviation ADR：独立立项。
- 第二轮独立标注：需独立标注者。
```

把 Step 2 生成的第一张表原样粘到 §2 标题下，第二张表与 `proxy` / `ambiguous`
两行原样粘到 §3 标题下；两张表必须来自命令输出，不得手写或估算。
报告全文不得出现「准确率 / quality / agreement / 正确率」。

- [ ] **Step 4: 提交**

```bash
cd /d/ResearchOS
git add docs/evaluation/2026-11-14-method-acquisition-audit.md
git commit -m "docs(eval): report the measured method-acquisition availability and coverage"
```

---

### Task 5: 文档同步与偏差登记

**Files:**
- Modify: `README.md`、`architect.md`、`human_decision.md`
- Modify: `docs/superpowers/specs/2026-11-14-method-acquisition-measurement-design.md` §10

- [ ] **Step 1: 追加 HD 条目**

在 `human_decision.md` 的 `_后续人类决策按上述格式追加。_` **之前**插入 HD-016，按现有 6 字段格式（日期 / 背景 / 决策 / 理由 / 状态 / 影响），内容为：范围取广义 (b)、路径 C 先度量、标注基准 owner-derived 且非独立非盲标、只算可获取率与覆盖率、不算正确率；理由引用 HD-015 的 self-consistency 教训与 §2.5 未逐项登记的偏差。

- [ ] **Step 2: 同步 README / architect**

- `README.md`：在评估/脚本说明处加一行 `scripts/method_acquisition_audit.py` 的用途与复现命令；测试数字改为实测值（`319 + 新增用例数`）。
- `architect.md`：维护记录表追加 2026-11-14 一行；ADR 表**不新增** ADR（本次无架构决策），但在维护记录里注明「§2.5 未逐项登记 deviation ADR」为待办。

- [ ] **Step 3: 填 spec §10 实施偏差表**

把 §10 的散文改成表格，逐行登记实际与设计的差异。至少要处理：
- `summarise` 的 `domain_size` 默认 `None`（按 labels 逐领域计数），合成夹具显式传 2
  —— 是测试注入的细化，不是偏差；
- `cause_for` 的三值映射（`empty` → 无来源定位 / `L2` → 词表未覆盖 / 其余 → 无结构化字段）
  是 spec §6 只给成因名称、未给判定逻辑的细化，须在表中写明规则；
- 若标注阶段有任何与 §4 判据不同的处置，逐条写明理由。

若无偏差，写「无实施偏差，仅两处细化」并列两行，不许留空表。

- [ ] **Step 4: 提交**

```bash
cd /d/ResearchOS
git add README.md architect.md human_decision.md docs/superpowers/specs/2026-11-14-method-acquisition-measurement-design.md
git commit -m "docs: sync the method-acquisition measurement and its honesty wording"
```

---

### Task 6: 全量验证与独立审验

- [ ] **Step 1: 全量测试**

```bash
cd /d/ResearchOS && D:/Anaconda/envs/reOS/python.exe -m pytest --basetemp=.pytest_tmp_mam
```

预期：既有 `319 passed, 2 skipped` 保持，新增用例另计；总数 = `319 + 新增用例数`。

- [ ] **Step 2: 生产代码未改的核对**

```bash
cd /d/ResearchOS && git diff --name-only <Task-1 之前的一次提交>..HEAD | grep '^src/' || echo "no production changes"
```

预期：`no production changes`。

- [ ] **Step 3: 独立审验整体**

派子 agent（**先读 spec、计划、四个产物、`ANNOTATION.md`，再判断**）核对：
1. 160 格齐全、隔离顺序在提交历史中成立；
2. `protocol` 未参与、`proxy` 单列、L3 结构性缺失与抽错分开、`N/A` 真实输出；
3. 报告 §2/§3 用的是实跑数字、无禁用词；
4. 验收判据逐条成立，含变异锚点；
5. 文档同步与 HD-016；
6. `git diff` 无 `src/` 改动。
输出 `READY / NEEDS WORK` + 问题清单。

- [ ] **Step 4: 修订到 READY 并收尾**

按审验意见修订、复审到 `READY`，确认 `git status --short` 干净（除用户未要求提交的产物外）。报告最终提交 SHA 与实测数字。**不主动推送远程**——除非用户明确要求。

---

## Self-Review（写计划时已做）

**Spec coverage**：§4 标注协议 → Task 1；§5 认领映射 → Task 3 `covered_for`；§6 三个数字与口径 → Task 3 `summarise` + Task 4 报告；§7 不做清单 → 全局约束 + Task 6 `git diff`；§8 验收判据 → Task 2 强断言 / Task 3 变异锚点 / Task 6 全量；§9 文档同步 → Task 5；§10 偏差表 → Task 5 Step 3。

**Placeholder scan**：计划中不含 TBD / TODO / `______` / 时间占位 /「适当处理」/「类似 Task N」/
「按层 × 领域 × 成因计数」这类括号说明。ANNOTATION.md 模板的隔离顺序用提交历史做证据；
评估报告 §2/§3 的表格由 Task 4 Step 2 的命令生成后原样粘贴，不手抄、不估算。

**Type consistency**：`summarise(labels, sides, domain_size)`、`covered_for(layer, side)`、`cause_for(layer, side)`、`load_labels(path)` 在 Task 2 测试与 Task 3 实现中签名一致；`side` 的键 `structured/proxy/L2/L4/empty` 在合成夹具与 `system_side` 中一致；`A`/`C` 的 key 统一为 `f"{domain}|{layer}"`。
