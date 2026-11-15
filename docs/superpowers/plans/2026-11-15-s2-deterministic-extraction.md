# S2：确定性 L1 / L2 / L4 方法获取 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让方法的三层（L1 名字、L2 组件、L4 可复现设置）在库里**各有落点**，并且「没抽到」与「抽到但是空」在数据里可区分——当前这两件事长得一模一样，是 `L1 = 0/20`、`L3 = 0/20` 被误读成「抽错」的根因。

**Architecture:** 纯确定性抽取（不引入 LLM，invariant 2.5）：`research/patterns.py` 集中所有模式，`research/methods.py` 用它们产出一个 `MethodProfile`（名字 + 组件 + 设置 + `missing_layers`）。抽取是纯函数（`chunks -> MethodProfile`），由 supervisor 落库、审计脚本直接观察，两条路径共用同一实现，所以「审计通过但能力坏掉」不可能发生。审计脚本的 L1/L2/L4 判据从「蹭 conditions」改成读 `MethodProfile`。

**Tech Stack:** Python 3.12 / Pydantic v2 / SQLAlchemy 2 / SQLite / pytest。解释器 `D:/Anaconda/envs/reOS/python.exe`。

**设计依据：** `docs/superpowers/specs/2026-11-15-method-acquisition-design.md` §4.1（三个模型）、§6（确定性抽取）、§6.5（存储）、§6.6（memo）、§6.7（审计脚本）、§10.1–§10.4（验收）。
**回归基线：** `333 passed, 2 skipped / 335 collected`（S1 收官实测）。本计划只允许新增用例，不允许既有用例消失；每个任务末尾的期望数字都以此递推。

**前置说明（写给执行者）：**
- 跑测试**必须** `-o addopts=""`，否则 `-q` 变 `-qq`、汇总行消失；`--basetemp` 每次换新目录名。
- 本计划里的正则已在探针脚本中逐条跑过：单句用例（`we introduce LangProp` / `our framework, Voyager,` / `Voyager, our proposed method` / `8×A100` / `7B` / `zero-shot` / `pass@1`）全部按预期命中；**并且已在 40 篇留出集上实跑过一遍**（`.holdout_cache` 现存，只读）。实跑暴露了单句用例看不出的三类假名字，已写成下面的排除规则、每条一条负例：句首动名词（`Introducing a small weight ... increases PSNR`）、长名字的片段（`Spectral-based Spatial Grouping Transformer` 抓成 `Spectral-based`）、同位语误判（`Then, the framework is applied`）。实跑结果见 Task 10 Step 1 的参考值。若实测与测试不一致，**以实现 + 测试为准**，回来改本计划。
- **不准**为了让测试变绿去放宽断言、改 `_buckets`、改 `identity_key`、改 contradiction 级联。S2 不碰 identity、不改主张数。
- S2 显式**不做**：L3 的任何 LLM 接线（S3）、`conditions` 新增 `scale=`/`protocol=`（S4）、扩领域词表（`lexicon.py` 保持只有图像复原，MC 词表独立立项）。

---

## 文件结构

| 文件 | 责任 | 本计划改动 |
|---|---|---|
| `src/research_os/research/patterns.py` | 方法获取用到的全部模式与词表 | **新建** |
| `src/research_os/research/methods.py` | `MethodProfile` 抽取（L1/L2/L4 + `missing_layers`）+ 主张归因计数 | **新建** |
| `src/research_os/domain/models.py` | 领域模型 | 新增 `MethodPoint` / `MethodSetup` / `MethodProfile` |
| `src/research_os/domain/enums.py` | 枚举 | `EventType` 加两项、`TaskType` 加 `EXTRACT_METHOD` |
| `src/research_os/storage/tables.py` | 表结构 | 新增 `MethodProfileRow` / `MethodPointRow`（新表，走 `create_all`） |
| `src/research_os/storage/repositories.py` | 仓储 | 新增 `SqlMethodProfileRepository`（`upsert` / `get` / `list_by_run` / `profiles_for`） |
| `src/research_os/orchestration/supervisor.py` | 编排 | 注入 `method_extractor`；新增 3b 步（方法档案），并把名字传给定量抽取 |
| `src/research_os/research/quantitative.py` | 写入点 | `method` 不再只写常量 `"proposed method"`（设计 §10.3） |
| `src/research_os/reporting/memo.py` | 渲染 | 新增 `# Methods` 段 + 两个归因计数 |
| `scripts/method_acquisition_audit.py` | 只读审计 | `system_side` 改读 `MethodProfile`；L3 判据改为观测而非硬编码 |
| `architect.md` / `docs/handover/...` | 文档 | ADR-034、已知限制、实施偏差、交接 |

---

### Task 1: `patterns.py` —— 把模式集中到一处

**Files:**
- Create: `src/research_os/research/patterns.py`
- Test: `tests/unit/test_method_patterns.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_patterns.py`：

```python
"""Every naming construction and vocabulary the method extractors use.

These tests are the contract for `patterns.py`: if a construction stops matching
"We introduce LangProp", the L1 layer silently drops to zero and every acceptance
number moves with it.
"""

from __future__ import annotations

from research_os.research.patterns import (
    COMPONENT_TAILS,
    COMPONENT_WORDS,
    EVAL_PROTOCOL,
    HYPERPARAMETERS,
    NAME_CONSTRUCTIONS,
    REPOSITORY_URL,
    SCALE_GPU,
    SCALE_PARAMS,
    domain_patterns,
)


def _names(text: str) -> list[str]:
    return [
        match.group("name")
        for _, pattern in NAME_CONSTRUCTIONS
        for match in pattern.finditer(text)
    ]


def test_all_three_naming_constructions_fire():
    assert _names("We introduce LangProp, a framework for policy learning.") == ["LangProp"]
    assert _names("Our framework, Voyager, learns an ever-growing skill library.") == ["Voyager"]
    assert _names("Voyager, our proposed method, stores code as skills.") == ["Voyager"]
    # The apposition must close with a comma. Without that requirement
    # "Then, the framework is applied" reads as a name - the one false positive
    # of this construction on the 40-paper hold-out set.
    assert _names("Then, the framework is applied to a policy.") == []


def test_a_lowercase_object_after_a_verb_is_not_a_name():
    """`[A-Z]` is load-bearing: without it "we propose a method that achieves"
    hands back "achieves", which then flows into every quantitative row."""
    assert _names("we propose a method that achieves 39.18 dB on SIDD.") == []
    assert _names("In this paper we propose a lightweight conditioning module.") == []
    assert _names("Motivated experiments show that our method improves PSNR.") == []


def test_scale_and_protocol_patterns_do_not_read_a_unit_as_a_scale():
    assert SCALE_PARAMS.findall("a 7B model") == [("7", "B")]
    assert SCALE_PARAMS.findall("1.3B parameters") == [("1.3", "B")]
    assert SCALE_PARAMS.findall("improves PSNR by 0.42 dB") == []
    assert SCALE_GPU.findall("trained on 8×A100 GPUs") == [("8", "A100")]


def test_protocol_vocabulary_is_closed():
    assert EVAL_PROTOCOL.findall("evaluated zero-shot and 5-shot, pass@1") == [
        "zero-shot",
        "5-shot",
        "pass@1",
    ]
    # A metric unit is not an evaluation protocol (design §6.3).
    assert EVAL_PROTOCOL.findall("39.18 dB PSNR and 0.95 SSIM") == []


def test_repository_and_hyperparameter_patterns():
    assert REPOSITORY_URL.findall("Code is at https://github.com/foo/bar.") == [
        "https://github.com/foo/bar."
    ]
    text = "trained for 100 epochs with learning rate 3e-4 and batch size 32 using AdamW"
    found = {name: pattern.findall(text) for name, pattern in HYPERPARAMETERS}
    assert found["lr"] == ["3e-4"]
    assert found["batch"] == ["32"]
    assert found["epochs"] == ["100"]
    assert found["optimizer"] == ["AdamW"]


def test_the_domain_hook_exists_but_is_empty():
    """Structure only: the Minecraft vocabulary is a separate design (§12.1).
    A test that pins it empty fails the day someone adds a group without saying
    why, which is the point."""
    assert domain_patterns(None).component_words == frozenset()
    assert domain_patterns("agent_in_mc").component_words == frozenset()
    # The design's own list (design §6.2), pinned so a word cannot appear or
    # vanish without the change showing up as a test diff. `transformer` is in it:
    # the point of this vocabulary is portability across domains, not that every
    # word is architectural in the narrow sense.
    assert COMPONENT_WORDS == frozenset(
        {
            "encoder", "decoder", "attention", "transformer", "memory", "planner",
            "buffer", "graph", "gate", "adapter", "head", "tokenizer", "retrieval",
        }
    )
    assert "module" in COMPONENT_TAILS
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_patterns.py -q --basetemp=.pytest_tmp_s2_t1_red
```

预期：`ModuleNotFoundError: No module named 'research_os.research.patterns'`。

- [ ] **Step 3: 新建 `patterns.py`**

`src/research_os/research/patterns.py`：

```python
"""Every pattern the method-acquisition extractors use (design §6.4).

One home for these vocabularies: the name reader, the component reader and the
setup reader all consult the same objects, so they cannot drift into disagreeing
about what a method name looks like.

`GENERIC` always applies. A domain group would be layered on top of it, but no
domain group exists yet: the Minecraft vocabulary is a separate design (design
§12.1), and inventing one here would repeat the mistake that zeroes that domain —
`lexicon.py`'s image-restoration `DATASETS` list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- L1: how a paper names its own method ---------------------------------
# Only explicit naming constructions count. "our method improves PSNR" states no
# name, and the captured token must be capitalised: without that, "we propose a
# method that achieves ..." would hand back "achieves" (design §6.1).
#
# The design lists four constructions; they collapse to three patterns because
# "this work presents X" has the same shape as "we present X", and the first
# pattern already alternates the subject. Two patterns for one sentence would
# count the same name twice.
#
# The apposition requires its closing comma ("X, our method, does ..."). That is
# what separates a real apposition from a discourse marker: "Then, the framework
# is applied" is not a naming sentence, and on the hold-out set it was the only
# false positive this construction produced.
_PROPOSE_VERBS = r"(?i:propose|proposes|introduce|introduces|present|presents|call|calls)"

NAME_CONSTRUCTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "we_verb",
        re.compile(
            rf"\b(?i:we|this paper|this work)\s+{_PROPOSE_VERBS}\s+(?:it\s+)?"
            r"(?P<name>[A-Z][A-Za-z0-9\-]{2,})"
        ),
    ),
    (
        "our_named",
        re.compile(
            r"\b(?i:our)\s+(?i:method|approach|model|framework|system)\s*"
            r"(?:,\s*|\s+(?i:called|named|dubbed)\s+)(?P<name>[A-Z][A-Za-z0-9\-]{2,})"
        ),
    ),
    (
        "apposition",
        re.compile(
            r"(?P<name>[A-Z][A-Za-z0-9\-]{2,})\s*,\s*(?i:our|the)\s+"
            r"(?i:proposed\s+)?(?i:method|approach|model|framework)\s*,"
        ),
    ),
)

# Verbs that appear where a name would, and generic nouns that a naming sentence
# can legitimately capture but that are not names. "We introduce Transformer"
# reads as a name to any regex; the exclusion is what keeps it out.
PREDICATES: frozenset[str] = frozenset(
    {
        "achieves", "achieve", "improves", "improve", "outperforms", "outperform",
        "gains", "gain", "reports", "report", "reduces", "reduce", "increases",
        "increase", "enables", "enable", "yields", "yield", "surpasses", "surpass",
        "demonstrates", "demonstrate", "reaches", "reach", "obtains", "obtain",
        "shows", "show", "uses", "use", "builds", "build",
    }
)
GENERIC_NOUNS: frozenset[str] = frozenset(
    {
        "transformer", "cnn", "convnet", "unet", "gan", "diffusion", "baseline",
        "method", "approach", "model", "framework", "network", "module", "system",
        "attention", "encoder", "decoder", "results", "result", "paper", "work",
    }
)

# --- L2: what counts as a component --------------------------------------
# Structural vocabulary, chosen because these words mean the same thing in an
# image-restoration paper and in a Minecraft-agent paper; unlike a dataset list
# they do not become useless the moment the domain changes (design §6.2).
COMPONENT_WORDS: frozenset[str] = frozenset(
    {
        "encoder", "decoder", "attention", "transformer", "memory", "planner",
        "buffer", "graph", "gate", "adapter", "head", "tokenizer", "retrieval",
    }
)
COMPONENT_PHRASES: tuple[str, ...] = ("reward model",)
COMPONENT_TAILS: tuple[str, ...] = (
    "module", "network", "block", "layer", "branch", "mechanism",
)

# --- L4: reproducible setup ----------------------------------------------
# `protocol` is a closed vocabulary on purpose: "top-1" and "success rate" are
# metrics and "\d+ episodes" is a budget, not an evaluation protocol. Treating a
# metric as a protocol means claiming two claims share a protocol because they
# share a metric (design §6.3).
EVAL_PROTOCOL = re.compile(r"\b(zero-?shot|few-?shot|\d+-shot|pass@\d+)\b", re.IGNORECASE)
# Upper-case B/M only, and never glued to a preceding word or dot, so "0.42 dB"
# and "39.18 dB" cannot read as "42 dB" -> 42B parameters.
SCALE_PARAMS = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([BM])\b")
SCALE_GPU = re.compile(r"(\d+)\s?[×x]\s?(A100|H100|V100|GPU|TPU)\b", re.IGNORECASE)
REPOSITORY_URL = re.compile(r"https?://(?:github\.com|gitlab\.com|huggingface\.co)/[^\s)\]>,;]+")
HYPERPARAMETERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("lr", re.compile(r"(?i)\blearning rate\b[^\d]{0,12}(\d+(?:\.\d+)?(?:[eE]-?\d+)?)")),
    ("batch", re.compile(r"(?i)\bbatch(?: size)?\b[^\d]{0,12}(\d+)")),
    ("epochs", re.compile(r"(?i)\b(\d+)\s+epochs?\b")),
    ("steps", re.compile(r"(?i)\b(\d+)\s+(?:training\s+)?steps?\b")),
    ("optimizer", re.compile(r"(?i)\b(adamw|adam|sgd|rmsprop)\b")),
)


@dataclass(frozen=True)
class DomainPatterns:
    """A domain's extra vocabulary, layered on top of `GENERIC`."""

    name_constructions: tuple[tuple[str, re.Pattern[str]], ...] = ()
    component_words: frozenset[str] = frozenset()
    component_tails: tuple[str, ...] = ()


# Deliberately empty: laying the hook is not the same as filling it (design §6.4).
DOMAINS: dict[str, DomainPatterns] = {}


def domain_patterns(domain: str | None) -> DomainPatterns:
    """Extra patterns for *domain*, or an empty group.

    Callers layer the result on top of the module-level `GENERIC` objects; this
    function never subtracts, so a missing domain degrades to generic-only.
    """
    return DOMAINS.get((domain or "").strip().lower(), DomainPatterns())
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_patterns.py -v --basetemp=.pytest_tmp_s2_t1_green
```

预期：6 passed。

- [ ] **Step 5: 全量**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  -q --basetemp=.pytest_tmp_s2_t1_all
```

预期：`339 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/patterns.py tests/unit/test_method_patterns.py
git commit -m "feat(methods): centralise the patterns the method readers share

Three naming constructions cover the design's four rows: 'this work presents X'
has the same shape as 'we present X', and two patterns for one sentence would
count the same name twice. The capture is capitalised on purpose - otherwise
'we propose a method that achieves' returns 'achieves'."
```

---

### Task 2: 三个领域模型

**Files:**
- Modify: `src/research_os/domain/models.py:168`（插在 `QuantitativeEvidence` 之后、`Claim` 之前）
- Test: `tests/unit/test_method_models.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_models.py`：

```python
"""The three method models (design §4.1).

`missing_layers` is the point of the whole design: it turns "this paper has no
L3" into a stored fact, because an empty list and an absent layer used to look
identical in the database.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_os.domain.models import MethodPoint, MethodProfile, MethodSetup


def test_setup_defaults_to_everything_unknown():
    setup = MethodSetup()
    assert setup.scale is None
    assert setup.protocol is None
    assert setup.hyperparameters == []
    assert setup.repository is None


def test_profile_carries_the_name_quote_and_chunk_together():
    profile = MethodProfile(
        source_version_id="sv_1",
        name="LangProp",
        name_quote="We introduce LangProp, a framework for policy learning.",
        name_chunk_id="chunk_1",
        components=["attention", "gating mechanism"],
        setup=MethodSetup(scale="8xa100", protocol="zero-shot"),
        missing_layers=["L3"],
    )
    assert profile.name == "LangProp"
    assert profile.name_chunk_id == "chunk_1"
    assert profile.missing_layers == ["L3"]
    assert profile.points == []


def test_a_point_is_structured_not_prose():
    """`statement` is a bounded claim and `quote` is the verbatim support: the
    design forbids storing free prose with no source location."""
    point = MethodPoint(
        aspect="mechanism",
        statement="Degradation maps are fused by a gated attention block.",
        quote="Our method estimates per-pixel degradation maps from the input.",
        chunk_id="chunk_1",
        section="Method",
    )
    assert point.aspect == "mechanism"
    with pytest.raises(ValidationError):
        MethodPoint(aspect="vibes", statement="x", quote="y", chunk_id="c")
    with pytest.raises(ValidationError):
        MethodPoint(aspect="goal", statement="x" * 201, quote="y", chunk_id="c")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_models.py -q --basetemp=.pytest_tmp_s2_t2_red
```

预期：`ImportError: cannot import name 'MethodPoint' from 'research_os.domain.models'`。

- [ ] **Step 3: 加三个模型**

`src/research_os/domain/models.py`：在文件顶部 `from pydantic import BaseModel, Field, field_validator` 一行改成

```python
from typing import Literal

from pydantic import BaseModel, Field, field_validator
```

（`from __future__ import annotations` 已在文件首行下方，`Literal` 必须放在 `typing` 导入处。）

在 `QuantitativeEvidence` 类定义之后、`class Claim(BaseModel):` 之前插入：

```python
class MethodPoint(BaseModel):
    """One structured statement about the method, with its source location.

    Structured points rather than free prose (design §4.1/§0): a statement with
    no locatable quote is exactly what plan §7.4 forbids storing.
    """

    id: str = Field(default_factory=lambda: new_id("mpoint"))
    aspect: Literal["goal", "mechanism", "why_it_works", "io"]
    statement: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1)
    chunk_id: str
    section: str | None = None


class MethodSetup(BaseModel):
    """Paper-level reproducible setup (plan §15 protocol slot, P4 model scale).

    `scale` and `protocol` are normalised ("8xa100", "zero-shot") and stay out of
    `identity_key` until S4; `hyperparameters` never enters identity because the
    seven P4 dimensions have no hyperparameter slot (design §8.3).
    """

    scale: str | None = None
    protocol: str | None = None
    hyperparameters: list[str] = []
    repository: str | None = None


class MethodProfile(BaseModel):
    """What one paper says about its own method (design §4.1).

    Identity is `(run_id, source_version_id)` at the storage layer: a profile is
    never merged across papers, and the method name deliberately does not enter
    `ClaimIdentity` (design §0).
    """

    id: str = Field(default_factory=lambda: new_id("mp"))
    source_version_id: str
    name: str | None = None
    aliases: list[str] = []
    # A name without a location is not evidence (plan §2.2): both are written or
    # neither is, and the extractor drops the name when either is missing.
    name_quote: str | None = None
    name_chunk_id: str | None = None
    components: list[str] = []
    setup: MethodSetup = Field(default_factory=MethodSetup)
    points: list[MethodPoint] = []
    # Subset of {"L1","L2","L3","L4"}: the layers this paper did NOT yield. An
    # empty list means "everything was obtained", which must stay distinguishable
    # from "nothing was attempted" (design §4.1).
    missing_layers: list[str] = []
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_models.py -v --basetemp=.pytest_tmp_s2_t2_green
```

预期：3 passed。

- [ ] **Step 5: 全量**

预期：`342 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/domain/models.py tests/unit/test_method_models.py
git commit -m "feat(domain): add the method profile, setup and point models

missing_layers is the point of the design: it turns 'this paper has no L3' into
a stored fact, because an absent layer and an empty one used to look identical."
```

---

### Task 3: L1 —— 名字抽取

**Files:**
- Create: `src/research_os/research/methods.py`
- Test: `tests/unit/test_method_name.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_name.py`：

```python
"""L1: the paper's own method name (design §6.1, §10.2/§10.3).

Two acceptance rules live in these tests and nowhere else:
- the name must be a verbatim substring of the chunk it claims to come from;
- sentence-initial capitalisation alone is not naming evidence (claims.py:169),
  with one documented exception: the apposition form "X, our method" *is* the
  evidence, and X is sentence-initial by construction.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.research.methods import extract_methods


def _chunk(text: str, *, section: str, index: int = 0, svid: str = "sv_1") -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{svid}_{index}",
        source_version_id=svid,
        section=section,
        chunk_index=index,
        text=text,
    )


def _profile(chunks):
    return extract_methods(chunks).profiles[0]


def test_name_comes_from_an_explicit_naming_sentence():
    profile = _profile(
        [_chunk("We propose LangProp, a framework for policy learning.", section="Abstract")]
    )
    assert profile.name == "LangProp"
    assert profile.name_chunk_id == "chunk_sv_1_0"
    # The quote must be locatable verbatim inside the chunk it points at.
    assert profile.name_quote in "We propose LangProp, a framework for policy learning."
    assert "L1" not in profile.missing_layers


def test_the_apposition_form_survives_the_sentence_initial_filter():
    """`Voyager, our proposed method, ...` opens the sentence; the construction
    itself is the naming evidence, so the claims.py:169 filter must not eat it."""
    profile = _profile(
        [_chunk("Voyager, our proposed method, stores code in a skill library.", section="Abstract")]
    )
    assert profile.name == "Voyager"


def test_a_sentence_initial_capital_alone_is_not_a_name():
    profile = _profile(
        [_chunk("Motivated experiments show that gating helps on SIDD.", section="Abstract")]
    )
    assert profile.name is None
    assert "L1" in profile.missing_layers


def test_predicates_datasets_metrics_and_generic_nouns_are_never_names():
    for text in (
        "We introduce a Transformer backbone for restoration.",
        "We propose SIDD as the evaluation benchmark.",
        "This paper introduces PSNR as the evaluation metric.",
    ):
        profile = _profile([_chunk(text, section="Abstract")])
        assert profile.name is None, text


def test_a_fragment_of_a_longer_name_is_not_a_name():
    """Measured on the hold-out set: the single-token `X` of design §6.1 lands on
    the first word of a multi-word name, and that word is an adjective, not a
    name. All three sentences below produced a wrong name before the two
    structural rejections (`_acceptable`'s trailing-character check and
    `_candidates`' "followed by a capitalised word" check)."""
    for text in (
        "We propose Spectral-based Spatial Grouping Transformer (SSGformer) for restoration.",
        "In this work, we present Language-conditioned Large-scale restoration model (LLaRS).",
        "In this paper, we propose Multi-τ Liquid-Mamba for sequence modelling.",
    ):
        profile = _profile([_chunk(text, section="Abstract")])
        assert profile.name is None, text


def test_the_abstract_outranks_the_method_section():
    """Source tier decides, not first appearance in the file: the abstract names
    the method the paper wants to be known by."""
    profile = _profile(
        [
            _chunk("Our framework, Voyager, learns skills.", section="Method", index=1),
            _chunk("We introduce LangProp in this work.", section="Abstract", index=0),
        ]
    )
    assert profile.name == "LangProp"
    assert profile.aliases == ["Voyager"]


def test_two_names_at_the_same_tier_in_one_chunk_are_ambiguous():
    """Design §6.1: same tier and same position means the paper has not chosen a
    name; guessing here would be the multi-method mistake (§4.1)."""
    extraction = extract_methods(
        [
            _chunk(
                "We introduce CALVIN for control and we introduce SOAP for planning.",
                section="Abstract",
            )
        ]
    )
    profile = extraction.profiles[0]
    assert profile.name is None
    assert extraction.ambiguous["sv_1"] == ("CALVIN", "SOAP")
    assert "L1" in profile.missing_layers
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_name.py -q --basetemp=.pytest_tmp_s2_t3_red
```

预期：`ModuleNotFoundError: No module named 'research_os.research.methods'`。

- [ ] **Step 3: 建 `methods.py`，只做 L1**

`src/research_os/research/methods.py`：

```python
"""Deterministic method acquisition: name, components, setup (design §6).

L1/L2/L4 are pattern matching, so they stay deterministic (invariant 2.5). Only
the L3 description needs an LLM, and that is S3; the `MethodDescriber` protocol
lands here later without changing this module's shape.

Two properties are load-bearing:

- A field is either confidently extracted or absent. No guessing, because a wrong
  method name would be attributed to every quantitative row of the paper.
- `missing_layers` is computed here, not by the caller: "the paper has no L3" has
  to reach the database as a fact, or an empty field and a failed extraction stay
  indistinguishable (design §4.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from research_os.domain.models import DocumentChunk, MethodProfile, MethodSetup
from research_os.research.claims import COMMON_CAPS, NOT_A_SUBJECT
from research_os.research.evidence_extractor import sentence_spans
from research_os.research.lexicon import DATASETS, METRICS
from research_os.research.patterns import (
    COMPONENT_PHRASES,
    COMPONENT_TAILS,
    COMPONENT_WORDS,
    EVAL_PROTOCOL,
    HYPERPARAMETERS,
    NAME_CONSTRUCTIONS,
    PREDICATES,
    GENERIC_NOUNS,
    REPOSITORY_URL,
    SCALE_GPU,
    SCALE_PARAMS,
    domain_patterns,
)

# Source tiers: the abstract is where a paper states the name it wants to be
# known by, and a conclusion mention is usually a recap. Everything else ranks
# last, which is still better than no candidate at all.
_TIERS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("abstract",), 0),
    (("introduction", "intro"), 1),
    (("method", "approach", "proposed"), 2),
    (("conclusion", "discussion", "result", "experiment"), 3),
)
_UNKNOWN_TIER = 4

# Words that cannot be the start of a component noun phrase.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "our", "its", "this", "these", "that", "their", "and",
        "or", "of", "for", "with", "in", "on", "to", "by", "as", "is", "are",
        "was", "were", "we", "it", "which", "each", "every", "one", "two",
        "three", "per", "same", "new", "single", "into", "from", "than", "then",
        "uses", "use", "using", "based", "via", "at", "be", "has", "have",
    }
)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")
_MAX_MODIFIERS = 2

_EXCLUDED_NAMES: frozenset[str] = (
    PREDICATES
    | GENERIC_NOUNS
    | frozenset(word.lower() for word in COMMON_CAPS)
    | frozenset(name.lower() for name in DATASETS)
    | frozenset(metric.lower() for metric in METRICS)
    | NOT_A_SUBJECT
)


@dataclass(frozen=True)
class MethodExtraction:
    """Profiles plus what only the caller can persist.

    The two event kinds (ambiguous name, multiple names) are facts *about* the
    extraction that the profile model has no room for; returning them keeps the
    "never invent state" rule while letting the supervisor log them (design §7.5
    classifies both as ordinary events, not failures).
    """

    profiles: list[MethodProfile]
    ambiguous: dict[str, tuple[str, ...]] = field(default_factory=dict)


class MethodExtractor(Protocol):
    def extract(self, chunks: list[DocumentChunk], domain: str | None = None) -> MethodExtraction: ...


def _tier(section: str | None) -> int:
    low = (section or "").lower()
    for needles, tier in _TIERS:
        if any(needle in low for needle in needles):
            return tier
    return _UNKNOWN_TIER


def _sentence_initial(text: str, position: int) -> bool:
    """True when *position* is the first visible character of its sentence."""
    head = text[:position]
    boundary = max(head.rfind(". "), head.rfind("! "), head.rfind("? "), head.rfind("\n"))
    start = boundary + 1
    return not text[start:position].strip()


def _quote_for(text: str, start: int, end: int) -> str:
    """The sentence containing the match, verbatim from the chunk.

    Verbatim matters: `name_quote` is the reader's only way to check that the
    name really appears where the row claims (plan §2.2).
    """
    for span_start, span_end, sentence in sentence_spans(text):
        if span_start <= start and end <= span_end:
            return sentence
    return text[start:end]


def _acceptable(name: str, *, at_start: bool, construction: str) -> bool:
    low = name.lower()
    if low in _EXCLUDED_NAMES:
        return False
    if not name[-1].isalnum():
        # "we propose Multi-<tau> Liquid-Mamba" hands back "Multi-": the token
        # class cut the tail, so the capture is a fragment, not a name.
        return False
    if not at_start or construction == "apposition":
        # The apposition form ("X, our method") is itself the evidence, and X is
        # sentence-initial by construction — the one documented exception to the
        # claims.py:169 rule.
        return True
    # Sentence-initial capitalisation proves nothing on its own; inner caps,
    # acronym shape or a digit do (claims.py:169).
    has_inner_caps = any(char.isupper() for char in name[1:])
    is_acronym = name.isupper() and len(name) >= 2
    has_digit = any(char.isdigit() for char in name)
    return has_inner_caps or is_acronym or has_digit


def _continues_a_longer_name(text: str, end: int) -> bool:
    """True when the match runs on into a longer capitalised noun phrase.

    "We propose Spectral-based Spatial Grouping Transformer (SSGformer)" captures
    "Spectral-based"; the real name is either the whole phrase or the acronym in
    parentheses, and either one appears in its own naming sentence, so dropping
    the fragment loses coverage but removes a wrong name. `and` is included
    because "Robust and Efficient Planning (REPOA)" has the same shape.

    Only horizontal whitespace counts: PDF text breaks lines mid-sentence, so
    matching any whitespace would read the next line's capitalised first word as a
    continuation and reject a name that is actually complete.
    """
    return re.match(r"[ \t]+(?:and[ \t]+)?[A-Z]", text[end:]) is not None


@dataclass(frozen=True)
class _Candidate:
    tier: int
    chunk_index: int
    position: int
    name: str
    quote: str
    chunk_id: str


def _candidates(chunks: list[DocumentChunk], domain: str | None) -> list[_Candidate]:
    extra = domain_patterns(domain)
    constructions = NAME_CONSTRUCTIONS + extra.name_constructions
    found: list[_Candidate] = []
    for chunk in chunks:
        text = chunk.text
        for label, pattern in constructions:
            for match in pattern.finditer(text):
                name = match.group("name")
                start, end = match.start("name"), match.end("name")
                if not _acceptable(name, at_start=_sentence_initial(text, start), construction=label):
                    continue
                if _continues_a_longer_name(text, end):
                    # "we propose Spectral-based Spatial Grouping Transformer": the
                    # captured token is the head of a longer proper noun phrase, so
                    # a single-token name would be a fragment (design §6.1 fixes one
                    # X, and half a name is worse than none: it flows into every
                    # quantitative row of the paper).
                    continue
                found.append(
                    _Candidate(
                        tier=_tier(chunk.section),
                        chunk_index=chunk.chunk_index,
                        position=start,
                        name=name,
                        quote=_quote_for(text, start, end),
                        chunk_id=chunk.id,
                    )
                )
    return found


def _pick_name(candidates: list[_Candidate]) -> tuple[_Candidate | None, tuple[str, ...], tuple[str, ...]]:
    """(chosen, competing names when ambiguous, aliases)."""
    if not candidates:
        return None, (), ()
    best_tier = min(item.tier for item in candidates)
    ordered = sorted((item for item in candidates if item.tier == best_tier), key=lambda i: (i.chunk_index, i.position))
    # Same tier, same chunk, different names: the paper has not chosen. Guessing
    # would attribute one method's numbers to the other (design §4.1).
    same_chunk = {item.name for item in ordered if item.chunk_index == ordered[0].chunk_index}
    if len(same_chunk) > 1:
        return None, tuple(sorted(same_chunk)), ()
    chosen = ordered[0]
    aliases = tuple(sorted({item.name for item in candidates if item.name != chosen.name}))
    return chosen, (), aliases


def _profile_for(source_version_id: str, chunks: list[DocumentChunk], domain: str | None) -> tuple[MethodProfile, tuple[str, ...]]:
    candidates = _candidates(chunks, domain)
    chosen, competing, aliases = _pick_name(candidates)
    profile = MethodProfile(source_version_id=source_version_id)
    if chosen is not None:
        profile.name = chosen.name
        profile.name_quote = chosen.quote
        profile.name_chunk_id = chosen.chunk_id
    profile.aliases = list(aliases)
    return profile, competing


def extract_methods(chunks: list[DocumentChunk], domain: str | None = None) -> MethodExtraction:
    """One profile per source version, ordered by first appearance."""
    by_source: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_version_id, []).append(chunk)

    profiles: list[MethodProfile] = []
    ambiguous: dict[str, tuple[str, ...]] = {}
    for source_version_id, group in by_source.items():
        ordered = sorted(group, key=lambda chunk: chunk.chunk_index)
        profile, competing = _profile_for(source_version_id, ordered, domain)
        if competing:
            ambiguous[source_version_id] = competing
        profile.missing_layers = _missing_layers(profile)
        profiles.append(profile)
    return MethodExtraction(profiles=profiles, ambiguous=ambiguous)


def _missing_layers(profile: MethodProfile) -> list[str]:
    missing: list[str] = []
    if not profile.name:
        missing.append("L1")
    if not profile.components:
        missing.append("L2")
    # L3 has no producer until S3: the layer is reported missing, never silently
    # folded into "no problem found".
    missing.append("L3")
    if not setup_filled(profile.setup):
        missing.append("L4")
    return missing


def setup_filled(setup: MethodSetup) -> bool:
    """True when the profile carries at least one reproducible setting."""
    return bool(setup.scale or setup.protocol or setup.hyperparameters or setup.repository)
```

> 说明：`COMPONENT_*`、`EVAL_PROTOCOL`、`HYPERPARAMETERS`、`REPOSITORY_URL`、`SCALE_*` 在 Task 4 才用；本步先导入不报错（未使用导入会触发 lint，但本仓库没有 ruff，见 §10 环境坑）。

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_name.py -v --basetemp=.pytest_tmp_s2_t3_green
```

预期：7 passed。若 `test_two_names_at_the_same_tier_in_one_chunk_are_ambiguous` 红：确认两个 `We introduce` 都在同一 chunk、同一 tier；若 `_candidates` 把 `CALVIN` 判成 `SOAP` 的重复，检查 `_pick_name` 的 `same_chunk` 是否按 `ordered[0].chunk_index` 判定。

- [ ] **Step 5: 全量**

预期：`349 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/methods.py tests/unit/test_method_name.py
git commit -m "feat(methods): read the method name from explicit naming sentences only

A name must be locatable (quote + chunk) and must not be a predicate, a dataset,
a metric or a generic noun. The apposition form is the one documented exception
to the sentence-initial filter: 'Voyager, our method' is the evidence itself."
```

---

### Task 4: L2 组件 + L4 设置

**Files:**
- Modify: `src/research_os/research/methods.py`（在 `_missing_layers` 之前加三个函数，并接到 `_profile_for`）
- Test: `tests/unit/test_method_layers.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_layers.py`：

```python
"""L2 components and L4 setup (design §6.2/§6.3).

Both layers are additive evidence that a paper describes a *system*: components
say what it is made of, setup says how to reproduce it. Neither may be inferred
from wording similarity - "our method works well" is not a component.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.research.methods import extract_methods


def _chunk(text: str, *, section: str = "Method", index: int = 0, svid: str = "sv_1") -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{svid}_{index}",
        source_version_id=svid,
        section=section,
        chunk_index=index,
        text=text,
    )


def _profile(*chunks: DocumentChunk):
    return extract_methods(list(chunks)).profiles[0]


def test_structural_noun_phrases_become_components():
    profile = _profile(
        _chunk(
            "We propose a lightweight conditioning module that injects degradation "
            "location maps into the restoration network. Our method fuses them with "
            "the feature stream using a gated attention block."
        )
    )
    assert "lightweight conditioning module" in profile.components
    assert "restoration network" in profile.components
    assert "gated attention block" in profile.components
    assert "L2" not in profile.missing_layers


def test_vocabulary_words_and_phrases_count_too():
    profile = _profile(
        _chunk("The planner queries a retrieval buffer and trains a reward model offline.")
    )
    assert "planner" in profile.components
    assert "retrieval" in profile.components
    assert "buffer" in profile.components
    assert "reward model" in profile.components


def test_a_bare_tail_word_is_not_a_component():
    """`module` on its own says nothing about the system; only a qualified noun
    phrase does. Otherwise every paper that says "this module" scores L2."""
    profile = _profile(_chunk("This module is described in the appendix."))
    assert profile.components == []
    assert "L2" in profile.missing_layers


def test_setup_reads_protocol_scale_and_repository():
    profile = _profile(
        _chunk(
            "We train on 8×A100 GPUs and evaluate zero-shot. Code is available at "
            "https://github.com/foo/langprop. Training uses learning rate 3e-4 for "
            "100 epochs with batch size 32 on AdamW."
        )
    )
    assert profile.setup.scale == "8xa100"
    assert profile.setup.protocol == "zero-shot"
    assert profile.setup.repository == "https://github.com/foo/langprop"
    assert "lr=3e-4" in profile.setup.hyperparameters
    assert "epochs=100" in profile.setup.hyperparameters
    assert "batch=32" in profile.setup.hyperparameters
    assert "optimizer=adamw" in profile.setup.hyperparameters
    assert "L4" not in profile.missing_layers


def test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale():
    """design §6.3: "top-1" and "success rate" are metrics, and a dB value is a
    unit. Reading either as a protocol/scale would claim two claims share a setup
    because they share a metric."""
    profile = _profile(_chunk("Our method reports 39.18 dB PSNR, a 0.42 dB gain."))
    assert profile.setup.protocol is None
    assert profile.setup.scale is None
    assert "L4" in profile.missing_layers


def test_missing_layers_always_reports_l3_until_s3_exists():
    """L3 has no producer until S3, so it is missing even when everything else
    landed: "the paper describes no mechanism" and "nobody looked" stay apart."""
    bare = _profile(_chunk("We introduce LangProp and evaluate on CALVIN.", section="Abstract"))
    assert bare.name == "LangProp"
    assert "L3" in bare.missing_layers

    complete = extract_methods(
        [
            _chunk(
                "We introduce LangProp, a framework. Our method uses a gating "
                "mechanism and is trained with learning rate 3e-4.",
                section="Abstract",
            )
        ]
    ).profiles[0]
    # L1 (name), L2 (gating mechanism) and L4 (lr=3e-4) all landed here, so the
    # list is exactly the one layer no code can fill yet.
    assert complete.missing_layers == ["L3"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_layers.py -q --basetemp=.pytest_tmp_s2_t4_red
```

预期：**4 红 2 绿**。红的是 `test_structural_noun_phrases_become_components`、`test_vocabulary_words_and_phrases_count_too`、`test_setup_reads_protocol_scale_and_repository`、`test_missing_layers_always_reports_l3_until_s3_exists`（`profile.components == []`、`profile.setup.scale is None`——这些字段还没有生产者）。两个负例 `test_a_bare_tail_word_is_not_a_component` 与 `test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale` 在这一步**天然是绿的**：没有生产者时当然不会误抽。它们的作用是之后挡住「组件抽过头 / 把 dB 当协议」，**不要为了让它们变红去改断言**（审验时实跑确认过是 4 红 2 绿）。

- [ ] **Step 3: 实现 L2 与 L4**

`src/research_os/research/methods.py`：在 `def _missing_layers(` **之前**插入：

```python
_COMPONENT_WORD_RE = re.compile(
    r"\b(" + "|".join(sorted(COMPONENT_WORDS)) + r")\b", re.IGNORECASE
)


def _component_phrases(text: str, tails: tuple[str, ...]) -> set[str]:
    """Qualified noun phrases ending in a structural tail ("gated attention block").

    Up to two modifiers, and a stopword ends the phrase: "a lightweight
    conditioning module" yields "lightweight conditioning module", while "the
    module" yields nothing because `the` is not a modifier.
    """
    tail_re = re.compile(r"\b(?P<tail>" + "|".join(tails) + r")\b", re.IGNORECASE)
    found: set[str] = set()
    for match in tail_re.finditer(text):
        modifiers: list[str] = []
        for token in reversed(list(_TOKEN.finditer(text[: match.start()]))):
            if len(modifiers) >= _MAX_MODIFIERS:
                break
            word = token.group(0).lower()
            if word in _STOPWORDS:
                break
            modifiers.append(word)
        if modifiers:
            found.add(" ".join([*reversed(modifiers), match.group("tail").lower()]))
    return found


def _components(chunks: list[DocumentChunk], domain: str | None) -> list[str]:
    extra = domain_patterns(domain)
    tails = COMPONENT_TAILS + extra.component_tails
    words = COMPONENT_WORDS | extra.component_words
    word_re = _COMPONENT_WORD_RE if words == COMPONENT_WORDS else re.compile(
        r"\b(" + "|".join(sorted(words)) + r")\b", re.IGNORECASE
    )
    found: set[str] = set()
    for chunk in chunks:
        text = chunk.text
        found |= {match.group(1).lower() for match in word_re.finditer(text)}
        found |= {phrase for phrase in COMPONENT_PHRASES if phrase in text.lower()}
        found |= _component_phrases(text, tails)
    return sorted(found)


def _scale(text: str) -> str | None:
    """First scale mention in this chunk, normalised ("8xa100" / "7b").

    Parameters and device counts are different facts sharing one slot (design
    §4.1); first occurrence wins, which is the only rule that stays stable when a
    paper mentions both.
    """
    options: list[tuple[int, str]] = []
    for match in SCALE_PARAMS.finditer(text):
        options.append((match.start(), f"{match.group(1)}{match.group(2).lower()}"))
    for match in SCALE_GPU.finditer(text):
        options.append((match.start(), f"{match.group(1)}x{match.group(2).lower()}"))
    return min(options)[1] if options else None


def _protocol(text: str) -> str | None:
    match = EVAL_PROTOCOL.search(text)
    if match is None:
        return None
    return re.sub(r"\s+", "", match.group(1).lower()).replace("zeroshot", "zero-shot").replace(
        "fewshot", "few-shot"
    )


def _setup(chunks: list[DocumentChunk]) -> MethodSetup:
    """First occurrence per field, in reading order: a setup is paper-level."""
    setup = MethodSetup()
    for chunk in chunks:
        text = chunk.text
        if setup.repository is None:
            match = REPOSITORY_URL.search(text)
            if match:
                # Trailing punctuation belongs to the sentence, not the URL.
                setup.repository = match.group(0).rstrip(".,;:")
        if setup.scale is None:
            setup.scale = _scale(text)
        if setup.protocol is None:
            setup.protocol = _protocol(text)
        for name, pattern in HYPERPARAMETERS:
            match = pattern.search(text)
            if match is None:
                continue
            value = f"{name}={match.group(1).lower()}"
            if value not in setup.hyperparameters:
                setup.hyperparameters.append(value)
    return setup
```

再把 `_profile_for` 的三行改成：

```python
def _profile_for(source_version_id: str, chunks: list[DocumentChunk], domain: str | None) -> tuple[MethodProfile, tuple[str, ...]]:
    candidates = _candidates(chunks, domain)
    chosen, competing, aliases = _pick_name(candidates)
    profile = MethodProfile(source_version_id=source_version_id)
    if chosen is not None:
        profile.name = chosen.name
        profile.name_quote = chosen.quote
        profile.name_chunk_id = chosen.chunk_id
    profile.aliases = list(aliases)
    profile.components = _components(chunks, domain)
    profile.setup = _setup(chunks)
    return profile, competing
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_layers.py tests/unit/test_method_name.py -v \
  --basetemp=.pytest_tmp_s2_t4_green
```

预期：13 passed（`test_method_layers.py` 6 条 + `test_method_name.py` 7 条）。若 `test_a_bare_tail_word_is_not_a_component` 红：确认 `"This module is"` 里 `this` 在 `_STOPWORDS` 中且 `_component_phrases` 在 `modifiers` 为空时不产出。

- [ ] **Step 5: 全量**

预期：`355 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/methods.py tests/unit/test_method_layers.py
git commit -m "feat(methods): add the component and setup readers

L2 counts qualified structural noun phrases, not bare tail words: 'this module'
is not a component. L4 keeps the design's closed protocol vocabulary - a metric
read as a protocol would claim two claims share a setup because they share a
metric."
```

---

### Task 5: 存储 —— 两张新表与仓储

**Files:**
- Modify: `src/research_os/storage/tables.py`（文件末尾追加两个 Row 类）
- Modify: `src/research_os/storage/repositories.py`（Protocol 区 + 实现区各加一段）
- Test: `tests/unit/test_method_store.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_store.py`：

```python
"""Method profile storage (design §6.5).

Identity is (run_id, source_version_id): a profile is scoped to a run the same
way claims and assessments are (ADR-019), so re-running a question does not
overwrite the previous run's methods.
"""

from __future__ import annotations

from research_os.domain.models import MethodProfile, MethodSetup
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlMethodProfileRepository


def _profile(svid: str = "sv_1", name: str | None = "LangProp") -> MethodProfile:
    return MethodProfile(
        source_version_id=svid,
        name=name,
        name_quote="We introduce LangProp." if name else None,
        name_chunk_id="chunk_1" if name else None,
        aliases=["Voyager"],
        components=["attention", "gating mechanism"],
        setup=MethodSetup(scale="8xa100", protocol="zero-shot", hyperparameters=["lr=3e-4"]),
        missing_layers=["L3"],
    )


def test_profile_round_trips_with_its_json_columns(db):
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(), run_id="run_1")
    with session_scope() as session:
        stored = SqlMethodProfileRepository(session).get("run_1", "sv_1")

    assert stored is not None
    assert stored.name == "LangProp"
    assert stored.name_chunk_id == "chunk_1"
    assert stored.aliases == ["Voyager"]
    assert stored.components == ["attention", "gating mechanism"]
    assert stored.setup.scale == "8xa100"
    assert stored.setup.hyperparameters == ["lr=3e-4"]
    assert stored.missing_layers == ["L3"]


def test_upsert_converges_instead_of_duplicating(db):
    """The vertical slice is re-runnable; a second save must leave one row."""
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(), run_id="run_1")
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(name="LangProp2"), run_id="run_1")
    with session_scope() as session:
        profiles = SqlMethodProfileRepository(session).list_by_run("run_1")

    assert len(profiles) == 1
    assert profiles[0].name == "LangProp2"


def test_two_runs_keep_their_own_profile(db):
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(), run_id="run_1")
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(name="Other"), run_id="run_2")
    with session_scope() as session:
        first = SqlMethodProfileRepository(session).profiles_for("run_1", ["sv_1"])
        second = SqlMethodProfileRepository(session).profiles_for("run_2", ["sv_1"])

    assert first["sv_1"].name == "LangProp"
    assert second["sv_1"].name == "Other"


def test_profiles_for_is_scoped_to_the_requested_ids(db):
    with session_scope() as session:
        repo = SqlMethodProfileRepository(session)
        repo.upsert(_profile("sv_1"), run_id="run_1")
        repo.upsert(_profile("sv_2", name=None), run_id="run_1")
        found = repo.profiles_for("run_1", ["sv_1", "sv_2", "sv_missing"])

    assert set(found) == {"sv_1", "sv_2"}
    assert found["sv_2"].name is None


def test_points_are_replaced_not_appended(db):
    from research_os.domain.models import MethodPoint

    profile = _profile()
    profile.points = [
        MethodPoint(aspect="goal", statement="Restore all degradations.", quote="q1", chunk_id="chunk_1")
    ]
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(profile, run_id="run_1")
    profile.points = [
        MethodPoint(aspect="mechanism", statement="Fuse maps by gating.", quote="q2", chunk_id="chunk_2")
    ]
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(profile, run_id="run_1")
    with session_scope() as session:
        stored = SqlMethodProfileRepository(session).get("run_1", "sv_1")

    assert [point.aspect for point in stored.points] == ["mechanism"]
    assert stored.points[0].quote == "q2"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_store.py -q --basetemp=.pytest_tmp_s2_t5_red
```

预期：`ImportError: cannot import name 'SqlMethodProfileRepository'`。

- [ ] **Step 3: 加表**

`src/research_os/storage/tables.py`：把 sqlalchemy 导入行改成

```python
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
```

文件末尾追加：

```python
class MethodProfileRow(Base):
    """What one paper says about its own method (design §6.5).

    The unique constraint, not the primary key, is what makes the pair identity:
    ADR-030 showed that a truncated composite id collides on exactly the rows
    this table must keep apart. `points` live in their own table because they are
    enumerated and counted; the rest are attributes never queried alone, so JSON
    keeps them in one row.
    """

    __tablename__ = "method_profiles"
    __table_args__ = (UniqueConstraint("run_id", "source_version_id", name="uq_method_profile"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), index=True)
    source_version_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aliases_json: Mapped[list] = mapped_column(JSON, default=list)
    components_json: Mapped[list] = mapped_column(JSON, default=list)
    setup_json: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_layers_json: Mapped[list] = mapped_column(JSON, default=list)


class MethodPointRow(Base):
    __tablename__ = "method_points"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64), ForeignKey("method_profiles.id"), index=True)
    aspect: Mapped[str] = mapped_column(String(32))
    statement: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[str] = mapped_column(String(64))
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4: 加 Protocol 与实现**

`src/research_os/storage/repositories.py`：在 `class ClaimRepository(Protocol):` **之前**插入 Protocol：

```python
class MethodProfileRepository(Protocol):
    def upsert(self, profile: MethodProfile, run_id: str) -> MethodProfile: ...

    def get(self, run_id: str, source_version_id: str) -> MethodProfile | None: ...

    def list_by_run(self, run_id: str) -> list[MethodProfile]: ...

    def profiles_for(self, run_id: str, source_version_ids: list[str]) -> dict[str, MethodProfile]: ...
```

在导入块里加 `MethodPoint, MethodProfile, MethodSetup`（`from research_os.domain.models import (...)` 内按字母序插入 `MethodPoint`、`MethodProfile`、`MethodSetup`）。

文件末尾追加：

```python
def _profile_id(run_id: str, source_version_id: str) -> str:
    """Deterministic id for the (run, source) pair.

    Digest rather than a truncated pair: ADR-030 recorded two different claim
    pairs colliding after `[:10]` truncation, and this table has the same shape.
    """
    digest = hashlib.sha1(f"{run_id}|{source_version_id}".encode("utf-8")).hexdigest()[:16]
    return f"mp_{digest}"


class SqlMethodProfileRepository:
    """Per-run method profiles with their points (design §6.5)."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, profile: MethodProfile, run_id: str) -> MethodProfile:
        profile_id = _profile_id(run_id, profile.source_version_id)
        # The stored id is the pair digest, so the object the caller holds must
        # carry it too - otherwise the value returned here and the value `get()`
        # reads back disagree, and a second write would look like a new row.
        profile.id = profile_id
        row = self._s.get(t.MethodProfileRow, profile_id)
        if row is None:
            row = t.MethodProfileRow(
                id=profile_id, run_id=run_id, source_version_id=profile.source_version_id
            )
            self._s.add(row)
        row.name = profile.name
        row.name_quote = profile.name_quote
        row.name_chunk_id = profile.name_chunk_id
        row.aliases_json = list(profile.aliases)
        row.components_json = list(profile.components)
        row.setup_json = profile.setup.model_dump()
        row.missing_layers_json = list(profile.missing_layers)

        # Points are replaced, never appended: a re-run must converge on one copy
        # (the same reason `replace_for_run` exists for assessments).
        self._s.execute(delete(t.MethodPointRow).where(t.MethodPointRow.profile_id == profile_id))
        self._s.flush()
        for index, point in enumerate(profile.points):
            self._s.add(
                t.MethodPointRow(
                    id=f"{profile_id}#{index}",
                    profile_id=profile_id,
                    aspect=point.aspect,
                    statement=point.statement,
                    quote=point.quote,
                    chunk_id=point.chunk_id,
                    section=point.section,
                )
            )
        self._s.flush()
        return profile

    def upsert_many(self, profiles: list[MethodProfile], run_id: str) -> list[MethodProfile]:
        for profile in profiles:
            self.upsert(profile, run_id)
        return profiles

    def _to_domain(self, row: t.MethodProfileRow) -> MethodProfile:
        points = self._s.scalars(
            select(t.MethodPointRow)
            .where(t.MethodPointRow.profile_id == row.id)
            .order_by(t.MethodPointRow.id)
        ).all()
        return MethodProfile(
            id=row.id,
            source_version_id=row.source_version_id,
            name=row.name,
            name_quote=row.name_quote,
            name_chunk_id=row.name_chunk_id,
            aliases=list(row.aliases_json or []),
            components=list(row.components_json or []),
            setup=MethodSetup(**(row.setup_json or {})),
            points=[
                MethodPoint(
                    id=point.id,
                    aspect=point.aspect,
                    statement=point.statement,
                    quote=point.quote,
                    chunk_id=point.chunk_id,
                    section=point.section,
                )
                for point in points
            ],
            missing_layers=list(row.missing_layers_json or []),
        )

    def get(self, run_id: str, source_version_id: str) -> MethodProfile | None:
        row = self._s.get(t.MethodProfileRow, _profile_id(run_id, source_version_id))
        return self._to_domain(row) if row else None

    def list_by_run(self, run_id: str) -> list[MethodProfile]:
        # Ordered, unlike `SqlEventRepository.list_by_run`: the memo renders one
        # section per profile and its output must not depend on rowid.
        rows = self._s.scalars(
            select(t.MethodProfileRow)
            .where(t.MethodProfileRow.run_id == run_id)
            .order_by(t.MethodProfileRow.source_version_id)
        ).all()
        return [self._to_domain(row) for row in rows]

    def profiles_for(self, run_id: str, source_version_ids: list[str]) -> dict[str, MethodProfile]:
        """One query for all profiles (design §6.5: no loop over ids).

        `_to_domain` reads the points of each profile it materialises, so the
        result costs one query plus one per profile; that is the shape the
        attribution path needs (a handful of papers), not a per-id round trip.
        """
        if not source_version_ids:
            return {}
        rows = self._s.scalars(
            select(t.MethodProfileRow).where(
                t.MethodProfileRow.run_id == run_id,
                t.MethodProfileRow.source_version_id.in_(source_version_ids),
            )
        ).all()
        return {row.source_version_id: self._to_domain(row) for row in rows}
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_store.py -v --basetemp=.pytest_tmp_s2_t5_green
```

预期：5 passed。

- [ ] **Step 6: 全量**

预期：`360 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/storage/tables.py src/research_os/storage/repositories.py \
        tests/unit/test_method_store.py
git commit -m "feat(store): persist method profiles per run

The unique constraint on (run_id, source_version_id) is the identity - a
digest id, because ADR-030 showed truncated ids collide. Points are replaced on
save so a re-run converges instead of accumulating."
```

---

### Task 6: 编排 —— 把方法档案接进竖切

**Files:**
- Modify: `src/research_os/domain/enums.py`（`EventType` 加两项、`TaskType` 加一项）
- Modify: `src/research_os/orchestration/supervisor.py`（构造注入 + 新 3b 步）
- Test: `tests/integration/test_method_run.py`（新建）
- Test fixture: `tests/fixtures/named_paper.md`（新建）

- [ ] **Step 1: 建夹具论文**

新建 `tests/fixtures/named_paper.md`：

```markdown
# LangProp: Closing the Loop with Programmatic Policies

## Abstract

We introduce LangProp, a framework that turns a language model's proposals into
executable policies. Our method keeps the policy code under version control and
reuses it across tasks.

## Method

LangProp, our proposed method, stores each policy as code and scores it by
execution feedback. The retrieval buffer keeps the last hundred programs, and a
gating mechanism decides which of them are reused.

## Results

On the CALVIN benchmark the method improves the success rate by 4.2 percent
over the baseline. We train on 8×A100 GPUs and evaluate zero-shot.

## References

[1] Someone et al., A Baseline, 2024.
```

- [ ] **Step 2: 写会失败的测试**

新建 `tests/integration/test_method_run.py`：

```python
"""The vertical slice stores a method profile per paper (design §6).

Read back from the database rather than from the supervisor's return value: the
point of the layer is that the profile survives the process.
"""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import EventType
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlEventRepository, SqlMethodProfileRepository, SqlSourceVersionRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _run(tmp_path, paper: str = "named_paper.md") -> tuple[str, list[str]]:
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Does programmatic policy reuse help?", domain="agent in mc")
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / paper), "named_paper", "markdown")],
            reports_dir=tmp_path,
        )
        source_ids = [sv.id for sv in SqlSourceVersionRepository(session).list_by_run(run.id)]
        return run.id, source_ids


def test_the_run_persists_one_profile_with_a_name(db, tmp_path):
    run_id, source_ids = _run(tmp_path)

    with session_scope() as session:
        profiles = SqlMethodProfileRepository(session).list_by_run(run_id)

    assert len(profiles) == 1
    assert profiles[0].source_version_id == source_ids[0]
    assert profiles[0].name == "LangProp"
    assert profiles[0].name_chunk_id
    assert "L3" in profiles[0].missing_layers


def test_the_run_persists_the_setup_it_could_read(db, tmp_path):
    run_id, _ = _run(tmp_path)

    with session_scope() as session:
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert profile.setup.scale == "8xa100"
    assert profile.setup.protocol == "zero-shot"
    assert any(component.endswith("mechanism") for component in profile.components)


def test_an_ambiguous_paper_logs_an_event_instead_of_a_name(db, tmp_path):
    """An unlogged ambiguity is indistinguishable from "no naming sentence",
    which is exactly the confusion `missing_layers` exists to end."""
    paper = tmp_path / "two_names.md"
    paper.write_text(
        "# Two Methods\n\n## Abstract\n\nWe introduce Alpha for control and we "
        "introduce Beta for planning.\n",
        encoding="utf-8",
    )

    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Which method?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id, sources=[(str(paper), "two_names", "markdown")], reports_dir=tmp_path
        )
        events = [
            event
            for event in SqlEventRepository(session).list_by_run(run.id)
            if event.event_type == EventType.METHOD_NAME_AMBIGUOUS
        ]
        profiles = SqlMethodProfileRepository(session).list_by_run(run.id)

    assert len(events) == 1
    assert events[0].failure_type is None  # ordinary event, not a failure (design §7.5)
    assert sorted(events[0].payload["candidates"]) == ["Alpha", "Beta"]
    assert profiles[0].name is None


def test_a_second_paper_on_the_same_run_gets_its_own_profile(db, tmp_path):
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Two papers?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[
                (str(FIXTURES / "named_paper.md"), "named", "markdown"),
                (str(FIXTURES / "sample_paper.md"), "sample", "markdown"),
            ],
            reports_dir=tmp_path,
        )
        profiles = SqlMethodProfileRepository(session).list_by_run(run.id)

    assert len(profiles) == 2
    assert {profile.name for profile in profiles} == {"LangProp", None}
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/integration/test_method_run.py -q --basetemp=.pytest_tmp_s2_t6_red
```

预期：三种红，各来自不同原因，别把它们混成一条：
- `test_the_run_persists_one_profile_with_a_name` 在 `assert len(profiles) == 1` 上失败（3b 步骤还不存在，一行 profile 都没落库）；
- `test_an_ambiguous_paper_logs_an_event_instead_of_a_name` 在 `EventType.METHOD_NAME_AMBIGUOUS` 上抛 `AttributeError`（枚举还没加）；
- `test_a_second_paper_on_the_same_run_gets_its_own_profile` 同上，`len(profiles) == 2` 失败。

- [ ] **Step 4: 加枚举**

`src/research_os/domain/enums.py`：

`EventType` 里 `CONTRADICTION_ASSESSED = "CONTRADICTION_ASSESSED"` 之后加两行：

```python
    # Ordinary events, not failures: design §7.5 keeps them out of `FailureType`
    # so the failure count stays a count of things that broke.
    METHOD_NAME_AMBIGUOUS = "METHOD_NAME_AMBIGUOUS"
    METHOD_MULTI_NAME = "METHOD_MULTI_NAME"
```

`TaskType` 里 `EXTRACT_EVIDENCE = "EXTRACT_EVIDENCE"` 之后加一行：

```python
    EXTRACT_METHOD = "EXTRACT_METHOD"
```

- [ ] **Step 5: 接线 supervisor**

`src/research_os/orchestration/supervisor.py`：

导入块加（`from research_os.research.methods import MethodExtractor, extract_methods` 与仓储 `SqlMethodProfileRepository`，`TaskType` 已在导入里）：

```python
from research_os.research.methods import MethodExtractor, extract_methods
```

`__init__` 的签名加一个参数并保存：

```python
    def __init__(
        self,
        session: Session,
        evidence_extractor: EvidenceExtractor | None = None,
        claim_builder: ClaimBuilder | None = None,
        providers: list[SearchProvider] | None = None,
        quantitative_extractor: QuantitativeExtractor | None = None,
        contradiction_assessor: ContradictionAssessor | None = None,
        method_extractor: MethodExtractor | None = None,
    ) -> None:
        self._session = session
        self._extractor = evidence_extractor or HeuristicEvidenceExtractor()
        self._builder = claim_builder or HeuristicClaimBuilder()
        self._quantitative = quantitative_extractor or HeuristicQuantitativeExtractor()
        self._assessor = contradiction_assessor or HeuristicContradictionAssessor()
        # Method acquisition is deterministic (design §6); the L3 describer that
        # is not deterministic arrives in S3 as a separate, optional component.
        self._methods = method_extractor
        self._providers = providers
```

> 适配说明：`HeuristicMethodExtractor` 在 Task 6 不新建——`extract_methods` 是模块级函数。为了让注入点与其它组件同构，这里允许 `method_extractor` 为 `None`，调用时回退到模块函数：

在 `run_vertical_slice` 的 3) 定量证据**之前**插入 3b（并把原来的 3)、4) 注释编号顺延为 4)、5)，只是注释，不改行为）：

```python
        # 3) method acquisition (design §6): name, components, setup per source.
        # Runs before the quantitative pass because that pass fills
        # `QuantitativeEvidence.method` with the resolved name (design §10.3).
        method_task = create_task(self._session, run.id, TaskType.EXTRACT_METHOD, status=TaskStatus.RUNNING)
        extraction = (
            self._methods.extract(all_chunks, domain=question.domain)
            if self._methods is not None
            else extract_methods(all_chunks, domain=question.domain)
        )
        SqlMethodProfileRepository(self._session).upsert_many(extraction.profiles, run.id)
        for source_version_id, candidates in extraction.ambiguous.items():
            # Logged, not swallowed: "no name because the paper never chooses one"
            # and "no name because nothing matched" are different defects.
            self._log(
                run.id,
                EventType.METHOD_NAME_AMBIGUOUS,
                f"ambiguous method name: {', '.join(candidates)}",
                {"source_version_id": source_version_id, "candidates": list(candidates)},
            )
        for profile in extraction.profiles:
            if profile.aliases:
                self._log(
                    run.id,
                    EventType.METHOD_MULTI_NAME,
                    f"{len(profile.aliases) + 1} method names in one paper",
                    {
                        "source_version_id": profile.source_version_id,
                        "name": profile.name,
                        "aliases": list(profile.aliases),
                    },
                )
        complete_task(
            self._session,
            method_task,
            output_ids=[profile.source_version_id for profile in extraction.profiles],
        )
```

导入 `SqlMethodProfileRepository`：在 `from research_os.storage.repositories import (...)` 里按字母序加 `SqlMethodProfileRepository,`。

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/integration/test_method_run.py -v --basetemp=.pytest_tmp_s2_t6_green
```

预期：4 passed。若 `test_the_run_persists_the_setup_it_could_read` 红且 `components` 为空：检查 `_component_phrases` 里 `gating mechanism` 是否被 `_STOPWORDS` 截断（`a gating mechanism` → `gating mechanism`）。

- [ ] **Step 7: 全量**

预期：`364 passed, 2 skipped`。

- [ ] **Step 8: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/domain/enums.py src/research_os/orchestration/supervisor.py \
        tests/integration/test_method_run.py tests/fixtures/named_paper.md
git commit -m "feat(run): extract and persist a method profile per paper

Runs before the quantitative pass, because that pass writes the resolved name
into each row. Ambiguity and multi-name papers log ordinary events, not
failures, so the failure count stays a count of things that broke."
```

---

### Task 7: 行级 `method` 填充（设计 §10.3）

**Files:**
- Modify: `src/research_os/research/quantitative.py:151-205`
- Modify: `src/research_os/orchestration/supervisor.py`（把名字传进去）
- Test: `tests/unit/test_quantitative_method.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_quantitative_method.py`：

```python
"""`QuantitativeEvidence.method` names the method the row belongs to (§15).

Before this, `method` was the constant "proposed method" whenever
`_PROPOSED_RE` matched, so L1 could never be observed per row: a row said
"proposed method" even when the paper had a name, and a row about a baseline's
number said nothing at all (design §10.3).
"""

from __future__ import annotations

from research_os.research.quantitative import HeuristicQuantitativeExtractor

EXTRACTOR = HeuristicQuantitativeExtractor()


def test_a_self_sentence_carries_the_papers_own_name():
    facts = EXTRACTOR.extract_from_text(
        "Our method improves the baseline PSNR by 0.42 dB.", "e1", method_name="LangProp"
    )
    assert [fact.method for fact in facts] == ["LangProp"]


def test_a_named_third_party_method_is_not_the_papers_name():
    """"Restormer improves Rain100H PSNR" is a row about Restormer. Filling it
    with the paper's own name is the cross-attribution §4.2 exists to prevent."""
    facts = EXTRACTOR.extract_from_text(
        "Restormer improves Rain100H PSNR by 0.44 dB.", "e1", method_name="LangProp"
    )
    assert [fact.method for fact in facts] == ["Restormer"]
    # A sentence-initial opener is not a subject, and it is not adjacent to the
    # predicate either: on the hold-out set this sentence used to produce a
    # method called "Introducing".
    facts = EXTRACTOR.extract_from_text(
        "Introducing a small weight increases the PSNR to 32.75 dB.", "e1", method_name="LangProp"
    )
    assert [fact.method for fact in facts] == [None]


def test_no_name_and_no_named_subject_leaves_method_empty():
    facts = EXTRACTOR.extract_from_text(
        "The gain is 0.11 dB on Rain100L.", "e1", method_name=None
    )
    assert [fact.method for fact in facts] == [None]


def test_the_placeholder_survives_when_the_paper_has_no_name():
    """Design §10.3 does not remove the old behaviour - it narrows it. With no
    resolved name, "our method" still has to say something."""
    facts = EXTRACTOR.extract_from_text(
        "Our method improves the baseline PSNR by 0.42 dB.", "e1", method_name=None
    )
    assert [fact.method for fact in facts] == ["proposed method"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_quantitative_method.py -q --basetemp=.pytest_tmp_s2_t7_red
```

预期：`TypeError: extract_from_text() got an unexpected keyword argument 'method_name'`。

- [ ] **Step 3: 改写入点**

`src/research_os/research/quantitative.py`：

顶部导入加：

```python
from research_os.research.claims import COMMON_CAPS, NOT_A_SUBJECT, SELF_REFERENCE
```

（三个名字都在 `claims.py` 顶层：`SELF_REFERENCE` 是既有定义，`COMMON_CAPS` / `NOT_A_SUBJECT` 本计划首次引用。`quantitative.py` 反向导入 `claims` 不成环——`claims.py` 只导 models / conditions / lexicon / scope。）

在 `_unit_near` 之后加：

```python
_NAMED_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9\-]{2,})\b")
_EXCLUDED_NAMES = (
    frozenset(word.lower() for word in COMMON_CAPS)
    | frozenset(name.lower() for name in DATASETS)
    | frozenset(metric.lower() for metric in METRICS)
    | NOT_A_SUBJECT
)


def _named_method(text: str, predicate_start: int) -> str | None:
    """The method named before the predicate, verbatim.

    Verbatim because `method` is read by a human and compared against the paper:
    lowercasing here would make "LangProp" and "langprop" look like two methods.

    Two ordering rules, both measured on the hold-out set:

    - Only the clause before the predicate counts ("... by 0.42 dB on SIDD" is a
      dataset, not a method), and the **nearest** candidate wins. A subject head
      sits next to its predicate; a sentence-initial opener does not
      ("Introducing a small weight ... increases PSNR" used to hand back
      "Introducing").
    - A sentence-initial `-ing` word is never a name: "Training improves PSNR"
      would otherwise be read as a method called Training.
    """
    prefix = text[:predicate_start]
    sentence_start = len(prefix) - len(prefix.lstrip())
    for match in reversed(list(_NAMED_TOKEN.finditer(prefix))):
        token = match.group(1)
        if token.lower() in _EXCLUDED_NAMES:
            continue
        if not token[-1].isalnum():
            continue  # "Multi-" is a fragment cut by the token class
        if match.start() == sentence_start and token.lower().endswith("ing"):
            continue
        has_inner_caps = any(char.isupper() for char in token[1:])
        is_acronym = token.isupper() and len(token) >= 2
        has_digit = any(char.isdigit() for char in token)
        if has_inner_caps or is_acronym or has_digit or (token[0].isupper() and len(token) >= 6):
            return token
    return None
```

把 `extract_from_text` 的签名与 `method` 赋值改掉：

```python
    def extract_from_text(
        self, text: str, evidence_id: str, method_name: str | None = None
    ) -> list[QuantitativeEvidence]:
        facts: list[QuantitativeEvidence] = []
        sentence_range = _RANGE_RE.search(text)
        dataset = _dataset(text)
        comparator_match = _COMPARATOR_RE.search(text)
        comparator = comparator_match.group(1).strip() if comparator_match else None
        # The row's method: a named third-party method wins, because the sentence
        # is about it; otherwise the paper's own name, and only then the constant
        # placeholder (design §10.3).
        predicate = _PREDICATE_RE.search(text)
        named = _named_method(text, predicate.start()) if predicate else None
        if named is not None:
            method = named
        elif SELF_REFERENCE.search(text) or _PROPOSED_RE.search(text):
            method = method_name or "proposed method"
        else:
            method = None
```

`_delta_fact` 这一步**不用改**：`quantitative.py:196` 已经把它收到的 `method` 传进去了，delta 行与 metric 行共用同一个值。上面改完 `method` 的赋值，两处自动一致。

在模块顶部 `_PROPOSED_RE` 之后加：

```python
# The verb that separates a subject from its object, imported in spirit from
# claims.PREDICATE: duplicated here because the quantitative reader must not
# depend on claim-building behaviour changing under it.
_PREDICATE_RE = re.compile(
    r"\b(improves?|improved|outperforms?|achieves?|gains?|reduces?|increases?|"
    r"surpass(?:es|ed)?|enables?|yields?|reports?|reaches?|demonstrates?)\b",
    re.IGNORECASE,
)
```

`extract` 改为透传名字：

```python
    def extract(
        self, evidence: list[Evidence], method_names: dict[str, str] | None = None
    ) -> list[QuantitativeEvidence]:
        method_names = method_names or {}
        facts: list[QuantitativeEvidence] = []
        for ev in evidence:
            facts.extend(
                self.extract_from_text(ev.text, ev.id, method_name=method_names.get(ev.source_version_id))
            )
        return facts
```

协议 `QuantitativeExtractor` 同步改签名：

```python
class QuantitativeExtractor(Protocol):
    def extract(
        self, evidence: list[Evidence], method_names: dict[str, str] | None = None
    ) -> list[QuantitativeEvidence]: ...
```

- [ ] **Step 4: supervisor 传名字**

`run_vertical_slice` 的定量一步改为：

```python
        facts = self._quantitative.extract(
            evidence,
            method_names={
                profile.source_version_id: profile.name
                for profile in extraction.profiles
                if profile.name
            },
        )
```

- [ ] **Step 5: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_quantitative_method.py tests/unit/test_quantitative.py \
  tests/integration/test_evidence_quality.py -v --basetemp=.pytest_tmp_s2_t7_green
```

预期：全绿。

- [ ] **Step 6: 全量**

预期：`368 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/quantitative.py \
        src/research_os/orchestration/supervisor.py tests/unit/test_quantitative_method.py
git commit -m "feat(quant): fill each row's method with the name the paper chose

The placeholder stays for papers with no name, but a named third-party subject
wins: a row about Restormer must not be labelled with the paper's own method
(design §10.3, §4.2)."
```

---

### Task 8: memo 的 Methods 段与归因计数

**Files:**
- Modify: `src/research_os/research/methods.py`（加 `attribute_claims`）
- Modify: `src/research_os/reporting/memo.py:35-46`（`RunGraph`）、`:60-106`（收集）、`:437-439`（渲染顺序）
- Test: `tests/unit/test_method_memo.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_memo.py`：

```python
"""The memo must show what the method layer got and what it did not (§6.6).

Three lines are mandatory even when they are zero, because "0" and "not counted"
have to be distinguishable to a reader.
"""

from __future__ import annotations

from pathlib import Path

from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run
from research_os.storage.database import session_scope

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _memo(tmp_path, paper: str = "named_paper.md") -> str:
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Does programmatic policy reuse help?", domain="agent in mc")
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / paper), "named_paper", "markdown")],
            reports_dir=tmp_path,
        )
        return build_memo_from_run(session, run.id) or ""


def test_the_memo_names_the_method_with_its_section(db, tmp_path):
    memo = _memo(tmp_path)
    section = memo.split("# Methods", 1)[1].split("\n# ", 1)[0]

    assert "LangProp" in section
    # The section a name came from is what makes the claim checkable.
    assert "Abstract" in section


def test_the_memo_shows_components_and_setup(db, tmp_path):
    section = _memo(tmp_path).split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "gating mechanism" in section
    assert "8xa100" in section
    assert "zero-shot" in section


def test_missing_layers_are_printed_as_a_line(db, tmp_path):
    section = _memo(tmp_path).split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "未获取：L3" in section or "未获取： L3" in section


def test_the_two_attribution_counters_are_present_even_when_zero(db, tmp_path):
    section = _memo(tmp_path).split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "多来源主张：" in section
    assert "未归因主语：" in section


def test_a_paper_with_no_name_says_so_instead_of_staying_silent(db, tmp_path):
    section = _memo(tmp_path, paper="sample_paper.md").split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "未获取" in section
    assert "L1" in section
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_memo.py -q --basetemp=.pytest_tmp_s2_t8_red
```

预期：`IndexError: list index out of range`（memo 里还没有 `# Methods` 段）。

- [ ] **Step 3: 加归因函数**

`src/research_os/research/methods.py` 末尾追加：

```python
@dataclass(frozen=True)
class Attribution:
    """How many claims could not be attached to a paper's own method (§4.2).

    Two different failures, counted apart: `multi_source` is one claim carried by
    several papers, `unattributed_subject` is a subject that is neither the
    paper's method nor a resolved name. Collapsing them would hide which of the
    two is growing.
    """

    multi_source: int = 0
    unattributed_subject: int = 0


def attribute_claims(
    claims: list[object],
    support_sources: dict[str, set[str]],
    profiles: list[MethodProfile],
) -> Attribution:
    """Count claims that cannot be attributed to a profile (design §4.2).

    `support_sources` maps claim id -> the source versions its supporting
    evidence came from; the caller owns that lookup because it already holds the
    relation graph.

    Only claims with a subject take part: an empty subject is a claim with no
    subject slot, not a mis-attribution. `self@<svid>` is the paper's own method
    by construction, so it is never counted - blaming the method layer for it
    would point at the wrong defect.
    """
    known = set()
    for profile in profiles:
        if profile.name:
            known.add(profile.name.lower())
        known |= {alias.lower() for alias in profile.aliases}

    multi_source = 0
    unattributed = 0
    for claim in claims:
        key = getattr(claim, "identity_key", None) or ""
        subject = key.split("|")[0]
        if not subject:
            continue
        sources = support_sources.get(getattr(claim, "id", ""), set())
        if len(sources) > 1:
            multi_source += 1
            continue
        if subject.startswith("self@"):
            continue
        if subject.lower() not in known:
            unattributed += 1
    return Attribution(multi_source=multi_source, unattributed_subject=unattributed)
```

- [ ] **Step 4: memo 收集与渲染**

`src/research_os/reporting/memo.py`：

`RunGraph` 加三个字段：

```python
    methods: list[MethodProfile] = field(default_factory=list)
    attribution: Attribution = field(default_factory=Attribution)
    # source_version_id -> the section the name was found in. Resolved while the
    # session is open, because the memo only keeps domain objects.
    method_name_sections: dict[str, str] = field(default_factory=dict)
```

导入：把 `MethodProfile` 加进既有的 `research_os.domain.models` 导入块，把 `SqlChunkRepository` / `SqlMethodProfileRepository` 加进既有的 `research_os.storage.repositories` 导入块（都按字母序），另外新增一行：

```python
from research_os.research.methods import Attribution, attribute_claims
```

`collect_run_graph` 在 `return RunGraph(...)` 之前算好：

```python
    methods = SqlMethodProfileRepository(session).list_by_run(run_id)
    support_sources: dict[str, set[str]] = {}
    for claim_id, supporting in supports.items():
        support_sources[claim_id] = {ev.source_version_id for ev in supporting}
    attribution = attribute_claims(claims, support_sources, methods)
    name_sections: dict[str, str] = {}
    for profile in methods:
        if not profile.name_chunk_id:
            continue
        chunk = SqlChunkRepository(session).get(profile.name_chunk_id)
        if chunk is not None and chunk.section:
            name_sections[profile.source_version_id] = chunk.section
```

并把 `methods=methods, attribution=attribution, method_name_sections=name_sections` 加进 `RunGraph(...)`。

在 `_render_quantitative_section` 之后新增：

```python
def _render_methods_section(graph: RunGraph) -> list[str]:
    """What each paper says about its own method, and what it does not (§6.6).

    Every line prints even when empty: "no name" and "we did not look" must not
    read the same, which is the whole reason `missing_layers` is stored. The two
    counters are run-level, so they print even when no profile was stored at all.
    """
    lines = ["# Methods", ""]
    if not graph.methods:
        lines.append("- No method profile was extracted for this run.")
        lines.append("")
    else:
        titles = {source.id: source.title for source in graph.sources}
        for profile in graph.methods:
            lines.append(f"## {titles.get(profile.source_version_id, profile.source_version_id)}")
            lines.append("")
            if profile.name:
                section = graph.method_name_sections.get(profile.source_version_id)
                suffix = f" · _{section}_" if section else ""
                lines.append(f"- Name: {profile.name}{suffix}")
            else:
                lines.append("- Name: _not extracted_")
            if profile.aliases:
                lines.append(f"- Other names: {', '.join(profile.aliases)}")
            lines.append(
                f"- Components: {', '.join(profile.components) if profile.components else '_none_'}"
            )
            setup = profile.setup
            setup_parts = []
            if setup.scale:
                setup_parts.append(f"scale={setup.scale}")
            if setup.protocol:
                setup_parts.append(f"protocol={setup.protocol}")
            if setup.hyperparameters:
                setup_parts.append("hyperparameters=" + ", ".join(setup.hyperparameters))
            if setup.repository:
                setup_parts.append(f"repository={setup.repository}")
            lines.append(f"- Setup: {' · '.join(setup_parts) if setup_parts else '_none_'}")
            if profile.points:
                for point in profile.points:
                    lines.append(
                        f"- {point.aspect}: {point.statement} _[{point.section or point.chunk_id}]_"
                    )
            else:
                lines.append("- Description: _not extracted at S2 (the L3 describer arrives in S3)_")
            lines.append(
                f"- 未获取：{', '.join(profile.missing_layers) if profile.missing_layers else '无'}"
            )
            lines.append("")
    lines.append(f"- 多来源主张：{graph.attribution.multi_source}（未归因）")
    lines.append(f"- 未归因主语：{graph.attribution.unattributed_subject}")
    lines.append("")
    return lines
```

`render_memo` 里 `lines.extend(_render_quantitative_section(graph))` 之后加一行：

```python
    lines.extend(_render_methods_section(graph))
```

- [ ] **Step 5: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_memo.py -v --basetemp=.pytest_tmp_s2_t8_green
```

预期：5 passed。若 `test_the_memo_names_the_method_with_its_section` 红在 `Abstract`：说明 `name_chunk_id` 指向 Method 段（apposition 形式先命中），检查 `_pick_name` 的 tier 排序是否把 Abstract 排在前面。

- [ ] **Step 6: 全量**

预期：`373 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/methods.py src/research_os/reporting/memo.py \
        tests/unit/test_method_memo.py
git commit -m "feat(memo): add the Methods section with its two attribution counters

Every line prints even at zero: 'no name' and 'we did not look' must not read
the same, which is why missing_layers is stored rather than inferred at render
time."
```

---

### Task 9: 审计脚本改读 `MethodProfile`（设计 §6.7）

**Files:**
- Modify: `scripts/method_acquisition_audit.py:67-113`
- Test: `tests/unit/test_method_acquisition_audit.py`（改 `SIDES`、`test_layer_mapping`）

- [ ] **Step 1: 先把测试改成新判据（这会红）**

`tests/unit/test_method_acquisition_audit.py`：

导入行删掉 `PLACEHOLDER_METHOD`，改成：

```python
from scripts.method_acquisition_audit import (
    cause_for,
    covered_for,
    load_labels,
    summarise,
)
```

`SIDES` 整块替换为：

```python
# `L3` is observed from the profile's points, not hardcoded: the previous audit
# returned False for L3 by construction, which is why the layer could never be
# seen to start working.
#
# Covered cells with this table, and nothing else: a1/L1, a2/L4, b1/L1, b1/L2.
# `b2/L1` is present in the labels but not covered here - it is the ambiguous
# name, which is exactly the case the `命名歧义` cause exists for.
SIDES = {
    "a1": {"L1": True,  "L1_ambiguous": False, "L2": False, "L3": False, "L4": False,
           "proxy": 2, "empty": False},
    "a2": {"L1": False, "L1_ambiguous": False, "L2": False, "L3": False, "L4": True,
           "proxy": 0, "empty": False},
    "b1": {"L1": True,  "L1_ambiguous": False, "L2": True,  "L3": False, "L4": False,
           "proxy": 1, "empty": False},
    "b2": {"L1": False, "L1_ambiguous": True,  "L2": False, "L3": False, "L4": False,
           "proxy": 3, "empty": False},
}
```

`test_layer_mapping` 替换为：

```python
def test_layer_mapping():
    assert covered_for("L1", SIDES["a1"]) is True
    assert covered_for("L1", SIDES["a2"]) is False
    assert covered_for("L2", SIDES["b1"]) is True
    assert covered_for("L4", SIDES["a2"]) is True
    # L3 must read the observation, not a constant: a profile with a point turns
    # the cell green even though S2 has no describer.
    assert covered_for("L3", SIDES["a1"]) is False
    assert covered_for("L3", {**SIDES["a1"], "L3": True}) is True
    assert cause_for("L3", SIDES["a1"]) == "无结构化字段"
    # Both other causes must be reachable, or cause_for could collapse to a
    # constant and every test above would still pass.
    empty_side = {**SIDES["a1"], "empty": True}
    assert cause_for("L4", empty_side) == "无来源定位"
    assert cause_for("L2", SIDES["a2"]) == "词表未覆盖"
    # A paper that named two methods gets the ambiguity cause, not "no field".
    assert cause_for("L1", SIDES["b2"]) == "命名歧义"
```

`test_gap_causes_are_classified` 里 `report["gaps"]["d1|L1|无结构化字段"] == 1` 改成 `report["gaps"]["d1|L1|命名歧义"] == 1`（`b2` 现在是歧义）；其余三行不变，合计仍是 4。

`test_every_cell_is_traceable_to_an_arxiv_id` 里的 `sum(... if c["covered"]) == 4` **保持 `== 4`，不要改**。旧集合是 `a1/L1`、`a2/L4`、`b1/L2`、`b2/L1`；新判据下 `b2/L1` 从覆盖变不覆盖（它的标注是 present，但 `SIDES["b2"]["L1"]` 为 False，原因 `命名歧义`），同时 `SIDES["b1"]["L1"]` 从 False 变 True、`b1/L1` 这格（标注 present）从**不**覆盖变覆盖。两处相抵，净数仍是 4。加一行注释说明这四格是哪四个，否则下一个人看到 `b2` 掉了却数字没变会以为断言写错了。

- [ ] **Step 2: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_acquisition_audit.py -q --basetemp=.pytest_tmp_s2_t9_red
```

预期：`KeyError: 'structured'`（`covered_for` 的 L1 分支还在读 `side["structured"]`，新 `SIDES` 已经没有这个键）与 `命名歧义` 断言失败。

- [ ] **Step 3: 改 `system_side` / `covered_for` / `cause_for`**

`scripts/method_acquisition_audit.py`：

导入加：

```python
from research_os.research.methods import extract_methods, setup_filled
```

同时删掉模块顶部的 `PLACEHOLDER_METHOD = "proposed method"`（`:25`）：它的唯一读者是上面那条测试导入，`system_side` 不再比对占位名之后它就是死代码，留着会让下一个人以为 L1 还在看定量行。`structured` 键一并从返回值里消失——全仓库只有两处读它（`covered_for` 与本测试的 `SIDES`），都在本任务里改掉；`grep -rn '"structured"' src/ scripts/` 剩下的只有 `holdout_claim_quality.py:193` 一个同名但无关的本地计数键。

`system_side` 整体替换为：

```python
def system_side(arxiv_id: str, cache: Path = CACHE) -> dict:
    """Observe (never modify) the current pipeline's output for one paper.

    L1/L2/L4 now read `MethodProfile` instead of the `conditions` strings they
    used to borrow: the old mapping scored L2 from `backbone=` and L4 from
    `training=`, so the newly added components and setup could break completely
    and the audit would still report the same numbers (design §6.7).
    """
    chunks = chunk_pages(load_html(cache / f"{arxiv_id}.html"), f"sv_{arxiv_id}")
    extraction = extract_methods(chunks)
    profile = extraction.profiles[0] if extraction.profiles else None
    evidence = HeuristicEvidenceExtractor().extract(chunks)
    quantitative = HeuristicQuantitativeExtractor().extract(evidence)
    claims, _ = HeuristicClaimBuilder().build(
        evidence, quantitative=quantitative, chunks=chunks
    )
    return {
        "L1": bool(profile and profile.name),
        "L1_ambiguous": bool(profile and profile.source_version_id in extraction.ambiguous),
        "L2": bool(profile and profile.components),
        "L3": bool(profile and profile.points),
        "L4": bool(profile and setup_filled(profile.setup)),
        "proxy": sum(1 for claim in claims if _named_subject(claim)),
        "empty": not claims and not quantitative,
    }
```

`covered_for` 替换为：

```python
def covered_for(layer: str, side: dict) -> bool:
    """Which observation makes a layer count as covered (design §6.7).

    Every branch reads the side, including L3: a constant there is how the layer
    stayed invisible for a whole measurement cycle.
    """
    if layer == "L1":
        return bool(side["L1"])
    if layer == "L2":
        return bool(side["L2"])
    if layer == "L3":
        return bool(side["L3"])
    if layer == "L4":
        return bool(side["L4"])
    raise ValueError(f"unknown layer: {layer}")
```

`cause_for` 替换为：

```python
def cause_for(layer: str, side: dict) -> str:
    """Direct reason a present cell was not covered (design §10.1).

    A closed set: every gap gets one of these, so "unexplained uncovered" stays
    at zero and no cell can be left without a conclusion.
    """
    if side["empty"]:
        return "无来源定位"
    if layer == "L1" and side.get("L1_ambiguous"):
        return "命名歧义"
    if layer == "L2":
        return "词表未覆盖"
    return "无结构化字段"
```

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_acquisition_audit.py -v --basetemp=.pytest_tmp_s2_t9_green
```

预期：7 passed。

- [ ] **Step 5: 全量**

预期：`373 passed, 2 skipped`（本任务只改用例判据，不新增用例）。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add scripts/method_acquisition_audit.py tests/unit/test_method_acquisition_audit.py
git commit -m "refactor(audit): read L1/L2/L4 from the method profile

The old mapping scored L2 from conditions' backbone= and L4 from training=, so
the new components and setup could have been broken end to end with the audit
still reporting the same numbers. L3 now reads the profile's points instead of
returning a constant."
```

---

### Task 10: 重测 + 报告 + ADR + 交接

**Files:**
- Modify: `architect.md`（ADR-034、已知限制、维护记录）
- Modify: `docs/superpowers/specs/2026-11-15-method-acquisition-design.md`（§13 实施偏差）
- Create: `docs/evaluation/2026-11-15-method-acquisition-s2.md`
- Modify: `docs/handover/2026-11-15-method-acquisition-handover.md`

- [ ] **Step 1: 重跑审计，拿到 before/after**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" scripts/method_acquisition_audit.py \
  --labels tests/fixtures/method_acquisition/labels.json | tee /tmp/s2_audit.txt
```

预期（**验收数字必须重跑后填入报告，不得照抄本节**）：L1/L2/L4 的 `C` 应当上升，L3 应仍为 `0/20` 且原因行是 `无结构化字段`；`gaps` 合计应从 105 下降。把实测输出**原样**贴进报告，before 一列用 `docs/evaluation/2026-11-14-method-acquisition-audit.md` 的数字。

**审验时的预跑参考值（只用于发现实现漂移，不是验收值）**：按下文的代码在本机 `.holdout_cache` 上跑一遍（`.holdout_cache` 里 47 个 html，labels 覆盖 40 篇），得到

| | 图像复原 | Agent in MC |
|---|---|---|
| L1 | 16/20 | 16/20 |
| L2 | 20/20 | 20/20 |
| L3 | 0/20 | 0/20 |
| L4 | 18/19 | 20/20 |

`gaps` 合计 `49`（105 − 56）。L1 一共产出 32 个名字，逐个对照 `name_quote` 全是真名字（`AdaIR` / `SSGformer` / `LLaRS` / `DAR-Net` / `Voyager` / `WISE` 一类），**没有一个是片段或虚词**。这个数字是逐步量出来的：只有设计原本的三条构式时是 **36 个名字、其中 9 个不是该篇的方法名**（`Spectral-based` / `Language-conditioned` / `Continuous` / `Multi-` / `Flexible` / `Frequency` / `Robust` / `Then`，外加 `2310.18293` 的 `MQRL`——它是损失函数名，该篇真名 `UtilityIR` 只出现在图注里）；加上"尾随非字母数字"+"同位语闭合逗号"+"后接大写词"三条后剩 32 个名字、1 个假名字（`Robust`）；再加 `and` 连接那一条才归零。剩下 8 篇没抽出名字，报告第 4 节要逐篇写原因（`2310.18293` 是其中一例）。**实跑偏离这张表超过 1 格，先查是不是把 Task 1/3/7 的某条排除规则漏掉了**，不要直接写报告。

行级（设计 §10.3，分母 = `SELF_REFERENCE` 或 `_PROPOSED_RE` 命中行 + 含具名第三方方法的行）：预跑得 170 行定量行，其中 100 行 `method` 非空——42 行等于该篇解析出的名字、2 行仍是占位 `proposed method`、56 行是第三方名（`Restormer` 一类，也含 `Liquid-Mamba` 这种片段，见报告 §5）。

- [ ] **Step 2: 写报告**

新建 `docs/evaluation/2026-11-15-method-acquisition-s2.md`，结构固定：

```markdown
# 方法获取能力 · S2 实测（2026-11-15）

> 命令：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`
> 判据：设计 §10.1 守恒式 + §10.2 L1 零容忍 + §10.4 逐篇向量；**不预设阈值**。

## 1. before / after（同一 40 篇、同一 160 格）

| 层 | 图像复原 before | 图像复原 after | Agent in MC before | Agent in MC after |
|---|---|---|---|---|
| L1 | 0/20 | … | 0/20 | … |
| L2 | 19/20 | … | 10/20 | … |
| L3 | 0/20 | … | 0/20 | … |
| L4 | 11/19 | … | 14/20 | … |

## 2. 守恒式

每格 `covered + explained == present`，`unexplained == 0`。逐格列出 explanations 的取值分布。

## 3. 逐篇向量（L2/L4）

设计 §10.4 要求比逐篇布尔向量，不只比总数：任何一篇下降都要给理由，否则回滚。

## 4. L1 精度（零容忍）

逐篇列出 name + quote + 三条判据，缺一条即该篇失败：

| 篇 | name | name_quote | ①逐字子串 | ②独立构式 | ③不是片段 |
|---|---|---|---|---|---|

判据：

1. `name` 是 `name_quote` 的逐字子串，且整条 `name_quote` 逐字出现在它指向的 chunk 里。
2. `name` 命中**下面这套独立构式**（照设计 §6.1 的四行手写，**不复用 `patterns.py`**；写进报告而不是写进 `tests/`，理由见偏差 D13。这里用波浪线围栏是为了不提前关掉本节外层的代码块，落地时照抄即可）：

   ~~~
   \b(?i:we|this paper|this work)\s+(?i:propose|introduce|present|call)(?:s|d|es)?\s+(?:it\s+)?(?P<X>[A-Z][^\s,.;]{2,})
   \b(?i:our)\s+(?i:method|approach|model|framework|system)[,]?\s+(?i:called|named|dubbed)?\s*(?P<X>[A-Z][^\s,.;]{2,})
   (?P<X>[A-Z][^\s,.;]{2,})\s*,\s*(?i:our|the)\s+(?i:proposed\s+)?(?i:method|approach|model|framework)\s*,
   ~~~

3. `name` 不是更长名字的片段：在 `name_quote` 里，`name` 后面紧跟的若不是逗号/句末/括号，而是另一个大写词或 `and + 大写词`，该篇判失败（这条是审验时在留出集上量出来的，见偏差 D10）。

**任一篇失败 → S2 不通过**，没有阈值。

## 4b. 行级 L1 覆盖（设计 §10.3，与按篇分开报）

分母 = 每篇里 `SELF_REFERENCE` 或 `_PROPOSED_RE` 命中的定量行 + 含具名第三方方法的定量行；分子 = 其中 `method` 非空且等于该篇解析名字的行。逐篇报 `分子/分母`，并报 `subject_inferred` 占比。**不宣称`method` 的精度**（`architect.md:144`：476 条 self 里 425 条是推断）——这一节只报覆盖率与 `subject_inferred` 比例。

## 5. 已知未解决

- L3 仍为 0：S3 未实施，`missing_layers` 已逐篇落库。
- L1/L2 在 agent_in_mc 上的残差：领域词表未扩（设计 §12.1）。
- L1 召回受命名句式限制：标注里写在图注/标题里的名字（如 `2310.18293` 的 `UtilityIR`）抽不到，`missing_layers` 记为 `L1`，不假装抽到了。
- `QuantitativeEvidence.method` 会收到片段型第三方名（如 `Liquid-Mamba`、`CEA-IR-S`），因为它是「谓词前最近的具名 token」，不做名字完整性判断；§4b 已声明不宣称精度。
```

- [ ] **Step 3: ADR-034 + 已知限制**

`architect.md` 的 ADR 表末尾（ADR-033 之后）加：

```markdown
| ADR-034 | 方法获取的 L1/L2/L4 走**确定性**模式（设计 §6），L3 描述留给 LLM（S3）。理由：名字/组件/设置是模式匹配，同一篇文档必须得出同一结果，否则 `MethodProfile` 无法作为 `QuantitativeEvidence.method` 的归因依据；而「这段在讲方法机理」是语义判断，正则必然做不好。为了让「没抽到」可观测，`MethodProfile.missing_layers` **落库**：空字段与未抽取在数据里必须不同形。审计脚本同步改为读 `MethodProfile`——否则新字段坏掉也能验收通过 | ACTIVE |
```

「已知限制」末尾（第 13 条之后）加：

```markdown
14. 方法 L1/L2 在 agent_in_mc 上仍有残差：`lexicon.py` 只有图像复原词表，S2 只铺了 `patterns.py` 的领域组结构（`DOMAINS` 为空）。扩 MC 词表是独立立项，不在四阶段内。
15. 一篇多方法只收一个 `name`，其余进 `aliases` 并记 `METHOD_MULTI_NAME`；同层同 chunk 并列时 `name` 留空并记 `METHOD_NAME_AMBIGUOUS`。**归属没有解决**，只是不再假装解决了。
16. L1 只认命名句式：名字只写在图注/标题里的论文（留出集 `2310.18293`，真名 `UtilityIR` 只出现在 "Overview of proposed UtilityIR"）抽不到，`missing_layers` 记为 `["L1"]`。`QuantitativeEvidence.method` 的第三方名可能是片段（`Liquid-Mamba`、`CEA-IR-S`），按设计 §10.3 只报行级覆盖率，**不宣称精度**。
```

维护记录加一行（日期 2026-11-15，内容写 S2 与测试数变化）。

- [ ] **Step 4: 设计 §13 实施偏差**

`docs/superpowers/specs/2026-11-15-method-acquisition-design.md` 的 §13 表末尾追加（编号从 D3 起）：

```markdown
| D3 | §6.1 的排除项是「谓词 + COMMON_CAPS + DATASETS + METRICS + NOT_A_SUBJECT」 | 再加一组 `GENERIC_NOUNS`（transformer/cnn/unet/gan/diffusion/baseline/method/…） | 谓词排除本来就是设计原文的要求，不在偏差之列；通用名词不在设计要求里，但 "We introduce Transformer" / "We propose the baseline" 对任何正则都像名字，而 §10.2 是**零容忍**精度：一个假名字就把整个阶段判失败。加的是同类排除（不是新机制），负例在 `test_method_name.py` 的 `test_predicates_datasets_metrics_and_generic_nouns_are_never_names` |
| D4 | §6.1 四处命名构式 | `patterns.py` 实现三条 | "this work presents X" 与 "we present X" 同形，第一条的 `we\|this paper\|this work` 交替已覆盖；两条并写会把同一个名字数两遍（候选重复会污染歧义判定） |
| D5 | §6.1 句首大写词不能单独作为命名证据（沿用 claims.py:169） | 同位语式 `X, our method` 例外 | 该构式里 X **必然**是句首，且构式本身就是命名证据；不例外就等于删掉这一整条构式。其余构式严格照 169 行判据执行，正反例都在 `test_method_name.py` |
| D6 | §6.1 只说「歧义记 METHOD_NAME_AMBIGUOUS」 | 判定为「同 tier、同 chunk、不同名」 | 纯按 (tier, 位置) 并列在实际文本里不可能发生，那条事件会成死代码；按 chunk 判定的触发点正是 §4.1 点名的一篇多方法论文 |
| D7 | §4.1 的 `MethodProfile` 没有 `id` | 模型加 `id`（`new_id("mp")`），存储用 `(run_id, source_version_id)` 摘要做主键 | 与其它领域模型一致（`Evidence`/`Claim` 都有 id），且 §6.5 的仓储签名 `get(run_id, svid)` 需要主键；摘要而非截断，因为 ADR-030 记录过截断撞键 |
| D8 | §6 未提编排任务 | `TaskType` 加 `EXTRACT_METHOD`，`EventType` 加 `METHOD_NAME_AMBIGUOUS` / `METHOD_MULTI_NAME` | 竖切里每个抽取步骤都有 task（EVIDENCE/CLAIM/CONTRADICTION），方法档案不建 task 会让「这一步没跑」不可观测；两个事件按 §7.5 的归类**不**进 `FailureType` |
| D9 | §6.7 只说 `system_side` 改读 `MethodProfile` | 顺带删掉 `system_side` 的 `structured` 键 | L1 判据改成 `profile.name` 之后该键无人读，留着会让下一个人以为 L1 还看定量行；设计 §10.3 的行级覆盖另由 `QuantitativeEvidence.method` 承担 |
| D10 | §6.1 的 `X` 边界是 `[A-Z][A-Za-z0-9\-]{2,}` + 四道排除 | 再加三条**结构**拒绝：名字末字符必须是字母或数字（否掉 `Multi-`）、名字后紧跟大写词或 `and + 大写词` 则弃（否掉 `Spectral-based Spatial…`、`Robust and Efficient…`）、同位语构式要求闭合逗号（否掉 `Then, the framework is applied`） | §10.2 是**零容忍**精度，而设计给的边界在真实摘要上会抓虚词和片段。实测（40 篇留出集，只读）：原样 36 个名字、9 个不是该篇方法名；三条加上后 32 个名字、剩 1 个假名（`Robust`）；再加 `and` 那一条归零。代价是 L1 覆盖从 19+17 降到 16+16，降的 4 篇全是假名（其中 `2310.18293` 原判 `MQRL` 是损失函数名）。**收紧，不是放宽**；三条各有负例在 `test_method_patterns.py` / `test_method_name.py` |
| D11 | §6.7 的 L2 判据是「`components` 非空**或** conditions 命中」 | `system_side` 的 L2 只读 `profile.components`，不再接受 `conditions` 的 `backbone=`/`baseline=` 兜底 | 设计允许并存，但保留旧兜底会让「组件抽取彻底坏掉」被 `conditions` 掩盖——那正是 §6.7 要修的缺陷本身。实测（同一 40 篇，旧判据与新判据逐篇对比）：图像 19/20 → 20/20、MC 10/20 → 20/20，**没有任何一篇下降**，所以这不是靠放宽换来的上升 |
| D12 | §10.3 的填充条件是 `_PROPOSED_RE` | 改为 `SELF_REFERENCE.search(text) or _PROPOSED_RE.search(text)`，并取谓词前**最近**的具名 token 作第三方方法名 | §10.3 自己要求「句子点名了 self 或具名第三方方法时就填」，而 `SELF_REFERENCE` 才是本仓库对 self 的定义（含 `the method`）。两处必带：①行级分母必须用同一谓词（报告 §4b），否则分子分母不同源；②取最近 token，否则句首动名词会被当成方法名（实测 `Introducing`/`Replacing`/`Starting`/`Further`/`Following`/`Increasing`/`Multi-` 共 7 类 14 行）。代价是 `method` 非空行从 106 降到 100（共 170 行），换来的是假名字消失；§10.3 已声明不宣称 `method` 精度 |
| D13 | §10.2 要求第二套命名构式清单「写在测试里，不复用 `patterns.py`」 | 写在评测报告 `docs/evaluation/2026-11-15-method-acquisition-s2.md` 的 §4，随每次实测留痕；`tests/` 只放抽取器的回归锁 | 第二套构式要跑在 40 篇留出集上，而 `.holdout_cache` 是 gitignored 的，`test_fixture_provenance.py` 因此只能 opt-in skip——把门禁放进会被 skip 的测试等于没有门禁。报告里的清单仍然独立于 `patterns.py`（手写、来源是设计 §6.1 的四行），并且强制逐篇留结论 |
```

- [ ] **Step 5: 更新交接文档**

把 §0 一句话状态、§5 任务表、§9 下一步改成 S2 已完成、下一步 S3 计划；把 §6 的基线数字改成实测的 `373 passed / 2 skipped / 375 collected`（以实际为准）。交接文档的原则不变：与实测不一致时以实测为准，并回来改它。

- [ ] **Step 6: 全量 + 收尾核对**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s2_final
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" --collect-only -q \
  --basetemp=.pytest_tmp_s2_collect | tail -3
git status --short
git diff --stat master..HEAD -- src/ tests/ scripts/
```

预期：`373 passed, 2 skipped`、`375 tests collected`、工作区干净。收集数少于 375 = 有用例被静默删除，停下查。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add architect.md docs/
git commit -m "docs(arch): record S2, the deterministic method layers

ADR-034 pins why L1/L2/L4 are deterministic and why missing_layers is stored.
The evaluation report keeps the before numbers untouched and puts the after
numbers beside them, per design §10.5."
```

---

## 验收（S2 完成判据）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | 三层各有落点 | `test_the_run_persists_one_profile_with_a_name`（name + `name_chunk_id`）与 `test_the_run_persists_the_setup_it_could_read`（components + scale/protocol）都从库里读回，不读 supervisor 的返回值 |
| 2 | 「没抽到」与「抽到为空」可区分 | `missing_layers` 落库，且 `test_a_paper_with_no_name_says_so_instead_of_staying_silent` |
| 3 | L1 精度零容忍 | `test_method_name.py` 的负例 + 报告第 4 节的逐条核对 |
| 4 | 审计脚本能观测新能力 | `system_side` 读 `MethodProfile`（L2 = `profile.components` 非空、L4 = `setup_filled`）。**变异锚点在实跑上，不在单测上**：注释掉 `_profile_for` 里 `profile.components = _components(...)` 一行再重跑审计，L2 的 `C` 会从 20/20 掉下来；`test_layer_mapping` 只锁映射函数本身（它的 `SIDES` 是手写的，删生产者它不会红），所以这一条必须用审计脚本验，不能只看 pytest |
| 5 | 不扰动 identity 与主张数 | 全量测试中 claim 相关用例一条不改；`identity_key` 相关文件零改动 |
| 6 | 既有用例一条不少 | 收集数 `375`（335 + 40 条新增）|

## 明确不做（S2 边界）

- 不接 LLM、不做 L3、不建 `MethodDescriber`（S3）。
- 不往 `conditions` 加 `scale=` / `protocol=`，不改 `identity_key`（S4）。
- 不扩 `lexicon.py` 的领域词表（独立立项）。
- 不改 `_buckets`、不改矛盾级联、不改 `coverage` 口径。
- 不宣称 `components` 让 P4 的 architecture 维达标：该维仍只有 `backbone=` 一个词（设计 §11/§12.2）。

---

## 实施记录（执行后回填，不改上文）

- 实际新增用例 **41** 条（不是 40）：`test_a_scheme_less_repository_url_is_still_a_repository`
  是实现期按设计 §10.4「逐篇下降必须给理由、否则回滚」补的——留出集 `2507.22498` 的 L4
  因该文只写 scheme-less URL 而从 True 掉成 False，选择修而不是解释（设计 §13 D14）。
- 因此基线是 **`374 passed / 2 skipped / 376 collected`**，各任务累计数比上文各 +1 之后逐级自洽
  （339→342→349→355→360→364→368→373→**374**）。
- 另修了审计的原因标签（设计 §13 D15）：L1/L4 的缺口记「词表未覆盖」，只有 L3 记「无结构化字段」。
- 实测结果与 Task 10 的预跑参考表**逐格一致**（L1 16/16、L2 20/20、L3 0/0、L4 18/19 与 20/20），
  只是 L4 第一格在 D14 修复后由 18/19 变成 **19/19**，`gaps` 由 49 变成 **48**。
