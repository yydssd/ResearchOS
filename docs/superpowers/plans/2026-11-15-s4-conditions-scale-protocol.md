# S4：`conditions` 两个新维度 + 按 kind 的 provenance 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 P4 的七维里最后两维（**model scale**、**evaluation protocol**）真正进入 `conditions`，并把 provenance 从「整条一个 tier」改成**按 kind 各记各的**——否则新增两个高频模式后，一句 `ours achieves 70% success rate` 会把继承来的 `training=` / `backbone=` 整条覆盖掉，同时把 tier 升成 `sentence`，从而允许一个没有依据的 `TRUE_CONTRADICTION`。

**Architecture:** `conditions` 的内部表示从 `tuple[str, ...]` 升级为 **`dict[kind] -> value` + `dict[kind] -> tier`**，`identity_key` 仍是 7 段、第 6 段仍是排序后的 `kind=value;kind=value`（分号连接，键不变、段数不变、值域扩两类）。按 kind 补齐继承、按 kind 判 tier；矛盾判定只对**两侧都有的 kind**要求 tier 已确认，缺任一即 `INSUFFICIENT_EVIDENCE`（HD-014 的「继承只可否证，不可证实」原样保留）。

**Tech Stack:** Python 3.12 / Pydantic v2 / SQLAlchemy 2 / SQLite / pytest。解释器 `D:/Anaconda/envs/reOS/python.exe`。

**设计依据：** `docs/superpowers/specs/2026-11-15-method-acquisition-design.md` §8（全节）、§10.5（三份报告）、§11（明确不做）。
**回归基线：** `408 passed, 2 skipped / 410 collected`（S3 收官实测）。

**这是唯一改变主张宇宙的阶段（设计 §8.4）。** 因此：
- **before/after 必须并列**，三份报告缺一不可，**禁止只报新数字**；
- `identity_key` 段数仍 7，`ClaimIdentity.key()` 的拼接格式不变；
- 每个任务结束后**必须**跑一次全量：主张数变化只能出现在 Task 6（合并行为），不能散落在别处。

**前置约束：**
- 跑测试**必须** `-o addopts=""`，`--basetemp` 每次换新目录名。
- **不改** `subject`、`_subject()`、`value_bucket`、`_buckets()`、`mergeable()` 的门槛三条（subject/dataset/direction）。
- **不改**矛盾级联的**关系类型**与**判定顺序**（设计 §11）：只改 `assess_pair` 里 `if (direction_a, direction_b) in OPPOSITE:` 那一个分支的门；实跑 `diff` 对照 `contradiction.py` 只允许两处改动（`_conditions_from` 函数定义 + OPPOSITE 门），其余 8 个分支逐字不动（审验证据见 Task 5 Step 4）。
- 存量数据库里旧的 `conditions_from=<tier>` 标记**不迁移**：它们是度量产物，不是生产数据；读不到就按「未确认」处理（安全方向），并登记为已知限制。
- `claims.py:180` 的 `if own: return own, "sentence"` 正是交接文档 §11「判定逻辑上的已知雷（不要顺手改）」点名的那处。**S4 改它不是顺手改**：设计 §8.2 逐字要求「provenance 从整体一个 tier 改为按 kind 记录」，交接 §9 起手四条也把它列为 S4 范围。因此它只允许在 Task 3 独占修改，且必须带 §8.2 的对照测试；不得夹带 §11 里其它四条（方向词表、`_buckets` 的 `.lower()`、dataset 门槛、P5 盲标）。
- **`identity_key` 第 6 段的新值不得含 `;` 与 `|`**（设计 §8.1、交接 §9 起手第 4 条）：`";".join` 会被值里的 `;` 撕成幽灵条件，`"|".join` 会被值里的 `|` 撕成第 8 段。Task 1 必带断言，实跑后果见 Task 1 Step 2。
- **本计划逐条点名所有要改的既有断言**，不写「若有用例红就改」。审验在仓库外副本按本计划的接口改动（`BlockScope.conditions` tuple→dict、`ClaimIdentity.conditions_from` 消失、flag `conditions_from=`→`condition_tier=`）跑全量，实测**17 条既有断言会红**，逐条清单与新断言见各任务 Step 1/2；Task 7 Step 5 用该清单核对。

**审验实测基线（本轮，仓库外副本，未改仓库任何文件）：**
```
$ cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_review4_baseline
408 passed, 2 skipped, 1 warning in 9.85s
$ "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" --collect-only -q --basetemp=.pytest_tmp_review4_collect
410 tests collected in 1.21s
```

---

## 文件结构

| 文件 | 责任 | 改动 |
|---|---|---|
| `src/research_os/research/conditions.py` | 条件抽取 | 新增 `extract_condition_map()`（kind→value 的原始形态）+ `scale=` / `protocol=` 两类；`extract_conditions()` 改为它的薄包装（保持 tuple 返回） |
| `src/research_os/research/scope.py` | 块级继承 | `BlockScope` 从「一个 tuple + 一个 tier」改为「dict + 每 kind 的 tier」；继承按 kind 补齐 |
| `src/research_os/research/claims.py` | 身份 | `ClaimIdentity` 增 `condition_tiers`（provenance，不进 key）；`_conditions()` 改为按 kind 合并 |
| `src/research_os/research/claim_builder.py` | 落库形态 | 每条 claim 的 flags 从 `conditions_from=<tier>` 改为 `condition_tier=<kind>:<tier>` |
| `src/research_os/research/contradiction.py` | 矛盾判定 | `_conditions_from()` → `_condition_tiers()` + `_kinds()`；TRUE_CONTRADICTION 的门改为「两侧共有 kind 的 tier 都确认」 |
| `src/research_os/reporting/memo.py` | 只读 | **不改代码**：`memo.py:497` 把 `claim.conditions`（= `kind=value` + flags）用 `", ".join` 渲染成 `- Conditions:` 行，`claim_builder` 改 flag 后这一行会原样多出 `condition_tier=...`。这是可观察面，必须登记；实测 `tests/integration/test_claim_synthesis.py::test_memo_shows_scope_conditions_and_grounding` 只断言 `"Conditions:" in memo`，仍绿 |
| `scripts/holdout_contradiction_quality.py` | 离线分析 | `_tier()` + `tiers` 统计段（第 34–38、70–79、108–115 行）是**按 tier 的统计口径**，不是展示；须按每 claim 的多 kind 重写（Task 6 Step 1） |
| `scripts/evaluate_contradiction.py` | 离线分析 / **判定输入** | 第 59–63 行从 `pairs.json` 读 `a_conditions_from` 并构造 `Claim.conditions` flag 供 `assess_pair` 判定——**不是展示**；须改成按 `a_key`/`b_key` 第 6 段的 kind 生成 `condition_tier=...`。它的回归锁是 `tests/unit/test_evaluate_contradiction.py::test_the_fixture_set_matches_the_cascade_it_pins` |
| `tests/fixtures/contradiction/pairs.json` | 夹具 | 26 对里 4 对（p04/p14/p15/p26）标 `conditions_from=sentence` 且期望 `TRUE_CONTRADICTION`；`note`/`ANNOTATION.md` 里的 `a_conditions_from` 表述同步（不删旧字段，加按 kind 的映射规则） |
| `docs/evaluation/2026-11-15-s4-*.md` | 报告 | 三份 before/after |

---

### Task 1: `conditions.py` —— 原始形态 + 两个新 kind

**Files:**
- Modify: `src/research_os/research/conditions.py`
- Test: `tests/unit/test_claim_conditions.py`（追加 4 条）

- [ ] **Step 1: 不动任何测试辅助函数（顺序约束，审验修正）**

`tests/unit/test_contradiction_cascade.py` 的 `_claim()` 改造**整体移到 Task 5 Step 1**，与 `contradiction.py` 的门同一步切换。

理由（仓库外副本实跑）：若按原写法在 Task 1 就把 `_claim()` 改成发 `condition_tier=<kind>:<tier>`，而 `contradiction.py` 仍是旧门 `_conditions_from()`（读 `conditions_from=`），则只改 `conditions.py` + 该文件后：

```
$ pytest -o addopts="" -q tests/unit/test_contradiction_cascade.py
7 failed, 15 passed
FAILED ...::test_same_explicit_scope_and_opposite_direction_is_a_true_contradiction
FAILED ...::test_equal_but_inherited_conditions_do_not_prove_a_contradiction
FAILED ...::test_heading_level_conditions_are_evidence
FAILED ...::test_every_opposite_pair_combination[UP-LEVEL] / [UP-DOWN] / [DOWN-LEVEL]
FAILED ...::test_sentence_level_conditions_are_evidence
E   AssertionError: assert <ContradictionType.INSUFFICIENT_EVIDENCE> == <ContradictionType.TRUE_CONTRADICTION>
```

即 Task 1 Step 5 的 `412 passed` 不可能达成。因此 Task 1 **只允许**改 `src/research_os/research/conditions.py` 与 `tests/unit/test_claim_conditions.py`。

`test_contradiction_cascade.py` 里 `conditions_from=` 字面量共 **18 处**（16 处 `_claim()` 调用参数 + 辅助函数签名默认值 + 生成 flag 的 f-string），另有 2 条断言读 explanation 文案。逐条清单与新写法见 Task 5 Step 1，本任务一处都不动。

- [ ] **Step 2a: 写会失败的测试**

先把 `tests/unit/test_claim_conditions.py` 第 5–6 行改成模块级导入：

```python
from research_os.research.claims import extract_identity, may_merge
from research_os.research.conditions import extract_condition_map, extract_conditions
```

**审验修正（必改）**：原计划只在第 1 条用例里写了局部 `import`，其余 3 条直接用 `extract_condition_map` 却没有导入。实跑（只改 `conditions.py` + 追加原 4 条用例）：

```
$ pytest -o addopts="" -q tests/unit/test_claim_conditions.py
3 failed, 10 passed
E   NameError: name 'extract_condition_map' is not defined
FAILED ...::test_model_scale_is_a_condition
FAILED ...::test_evaluation_protocol_is_a_condition
FAILED ...::test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale
```

不补这个 import，Task 1 Step 4 的 `13 passed` 永远达不到。改成模块级导入后，红阶段正是 Step 2 预期的 `ImportError: cannot import name 'extract_condition_map'`（收集期失败）。

然后在末尾追加 4 条（**不新增第 5 条**：§8.1 的禁分隔符断言并入第 1 条，用例数仍为 +4）：

```python
def test_condition_map_is_the_primitive_and_the_tuple_is_derived():
    """`extract_conditions` keeps its tuple contract for every existing caller;
    the map is what per-kind provenance needs (S4)."""
    assert extract_condition_map("A Transformer trained from scratch.") == {
        "backbone": "transformer",
        "training": "from-scratch",
    }
    # Sorted by kind: `backbone` before `training`, deterministically.
    assert extract_conditions("A Transformer trained from scratch.") == (
        "backbone=transformer",
        "training=from-scratch",
    )
    # 设计 §8.1 / §9 / 交接 §9.4：值里的 ';' 会被 ";".join 撕成幽灵条件，
    # '|' 会把 identity_key 撕成第 8 段。两类必须拦在抽取器出口。
    # 实跑后果：值 "protocol=5-shot;x=y" → _conditions(claim) 解析成
    #   ('protocol=5-shot', 'x=y', 'scale=7b')，凭空多一个 kind；
    #   值 "protocol=zero|shot" → key.split("|") 得 8 段（应为 7）。
    for text in (
        "A Transformer trained from scratch.",
        "We train a 7B model.",
        "Experiments run on 8×A100 GPUs.",
        "We evaluate zero-shot.",
        "Reported under the 5-shot setting.",
        "It improves PSNR by 0.42 dB.",
        "At noise level 25 the gain is largest.",
        "Compared with MPRNet, the gain is 0.4 dB.",
    ):
        assert all(
            ";" not in value and "|" not in value
            for value in extract_condition_map(text).values()
        ), text


def test_model_scale_is_a_condition():
    """P4's seven dimensions include model scale (plan §16); it had no home."""
    assert extract_condition_map("We train a 7B model.") == {"scale": "7b"}
    assert extract_condition_map("Experiments run on 8×A100 GPUs.") == {"scale": "8xa100"}


def test_evaluation_protocol_is_a_condition():
    assert extract_condition_map("We evaluate zero-shot.") == {"protocol": "zero-shot"}
    assert extract_condition_map("Reported under the 5-shot setting.") == {"protocol": "5-shot"}

    # 设计 §9 / 交接 §9 起手第 3 条「必带对照测试」：仅在这两维不同的两句
    # → may_merge() == False（「字段有值」不算通过）。原计划把这条漏了，
    # 并入本用例，不新增用例数（累计数仍 +4）。
    a = extract_identity(
        "Our method improves PSNR on SIDD under zero-shot evaluation.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    b = extract_identity(
        "Our method improves PSNR on SIDD under 5-shot evaluation.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    c = extract_identity(
        "We train a 7B model and improve PSNR on SIDD.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    d = extract_identity(
        "We train a 70B model and improve PSNR on SIDD.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    assert a.conditions == ("protocol=zero-shot",)
    assert b.conditions == ("protocol=5-shot",)
    assert c.conditions == ("scale=7b",)
    assert d.conditions == ("scale=70b",)
    assert not may_merge(a, b) and not may_merge(c, d)
    assert may_merge(a, a)  # 对照：同设置仍能合并，不是「一律不合并」的假通过


def test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale():
    """Same boundary as S2's MethodSetup (design §6.3): "success rate" is a metric
    and a dB value is a unit; reading either as a condition would let two claims
    look like they share a setup."""
    assert extract_condition_map("It improves PSNR by 0.42 dB.") == {}
    assert extract_condition_map("It reaches a 70% success rate.") == {}
```

- [ ] **Step 2b: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_claim_conditions.py -q --basetemp=.pytest_tmp_s4_t1_red
```

预期：`ImportError: cannot import name 'extract_condition_map'`。

- [ ] **Step 3: 实现**

`src/research_os/research/conditions.py`：把 `extract_conditions` 整体替换为：

```python
# Two new kinds for P4's last two dimensions (design §8.1). Both vocabularies are
# closed and both are reused verbatim from the S2 patterns, so a value that enters
# `conditions` here is the same string a `MethodSetup` would carry - one
# vocabulary, two readers.
_SCALE_PARAMS = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([BM])\b")
_SCALE_GPU = re.compile(r"(\d+)\s?[×x]\s?(A100|H100|V100|GPU|TPU)\b", re.IGNORECASE)
_PROTOCOL = re.compile(r"\b(zero-?shot|few-?shot|\d+-shot|pass@\d+)\b", re.IGNORECASE)


def _scale(text: str) -> str | None:
    """First scale mention, normalised the same way `MethodSetup` does it."""
    options: list[tuple[int, str]] = []
    for match in _SCALE_PARAMS.finditer(text):
        options.append((match.start(), f"{match.group(1)}{match.group(2).lower()}"))
    for match in _SCALE_GPU.finditer(text):
        options.append((match.start(), f"{match.group(1)}x{match.group(2).lower()}"))
    return min(options)[1] if options else None


def _protocol(text: str) -> str | None:
    match = _PROTOCOL.search(text)
    if match is None:
        return None
    return re.sub(r"\s+", "-", match.group(1).lower()).replace("zeroshot", "zero-shot").replace(
        "fewshot", "few-shot"
    )


def extract_condition_map(text: str) -> dict[str, str]:
    """The setup this sentence names, one value per kind, no defaults.

    A dict rather than a tuple because S4 needs to know *which kind* came from
    where: `conditions_from` used to describe the whole tuple, so one new
    high-frequency pattern would overwrite everything the section had established
    (design §8.2). Kinds are always the same six; a missing kind is absent, never
    defaulted.
    """
    found: dict[str, str] = {}

    match = _BACKBONE.search(text)
    if match:
        found["backbone"] = match.group(1).lower().rstrip("s")

    match = _DEGRADATION.search(text)
    if match:
        found["degradation"] = match.group(1) or match.group(2) or match.group(3).lower()

    match = _BASELINE.search(text)
    if match:
        found["baseline"] = match.group(1).lower()

    match = _TRAINING.search(text)
    if match:
        found["training"] = re.sub(r"\s+", "-", match.group(1).lower())

    scale = _scale(text)
    if scale:
        found["scale"] = scale

    protocol = _protocol(text)
    if protocol:
        found["protocol"] = protocol

    return found


def extract_conditions(text: str) -> tuple[str, ...]:
    """`kind=value` strings, sorted by kind. Kept as the tuple contract every
    existing caller and test relies on; new code should use the map."""
    return tuple(f"{kind}={value}" for kind, value in sorted(extract_condition_map(text).items()))
```

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_claim_conditions.py -v --basetemp=.pytest_tmp_s4_t1_green
```

预期：**13 passed（原 9 + 4）**。审验修正：原计划写「11 passed（原 7 + 4）」，`grep -c '^def test_' tests/unit/test_claim_conditions.py` 实测原有 **9** 条，补模块级 import 后实跑该文件 `13 passed in 0.11s`。

- [ ] **Step 5: 全量（关键：这一步不该改主张数）**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  -q --basetemp=.pytest_tmp_s4_t1_all
```

预期：`412 passed, 2 skipped`（= 基线 408 + 4）。审验实跑（仓库外副本，只改 `conditions.py` + 上述 import + 4 条用例）：`411 passed, 3 skipped`——副本缺 `.holdout_cache/` 使一条 opt-in 用例从 pass 转 skip，收集数仍 414 = 410 + 4；在有 cache 的仓库内即 `412 passed, 2 skipped`。

**逐条核对（替换原计划的「若有用例红就改」）**：本任务改动的唯一生产行为是新增两类条件值，会红的只可能是 `test_claim_conditions.py` 里 7 条既有 `extract_conditions(...) == (...)` 断言——它们的输入句（Transformer/CNN/noise level/heavy/MPRNet/from scratch/0.42 dB）**都不含** scale/protocol 模式，实测全绿。

夹具连带效应（B 类实测，40 篇留出集 + 4 个夹具目录）：`tests/fixtures/named_paper.md:18` 的 `We train on 8×A100 GPUs and evaluate zero-shot.` 是唯一命中句，after 版该 fixture 产出的 claim 第 6 段由 `''` 变为 `'protocol=zero-shot;scale=8xa100'`；但引用它的 `test_method_run.py` / `test_method_memo.py` / `test_method_description_run.py` / `test_llm_budget.py` 都不断言主张数、identity_key 或 `- Conditions:` 行的具体值，实测 **0 条红**；唯一断言 Conditions 行的 `test_claim_synthesis.py::test_memo_shows_scope_conditions_and_grounding` 用的是不含新 kind 的 `sample_paper.md`，仍绿。`sample_paper.md`、`contradiction/pairs.json`、`claim_merge/` 均无 `8×A100`/`zero-shot`/`5-shot`/`7B` 类句子。因此本任务无需改任何集成测试断言；40 篇留出集的逐句类变化（146 句命中、455 条 claim 第 6 段变化、主张数 1173→1173 不变）登记进 Task 6 报告，不在本任务处理。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/conditions.py tests/unit/test_claim_conditions.py
git commit -m "feat(conditions): add model scale and evaluation protocol

P4's seven dimensions had five homes; these were the two without one. The
primitive is a kind->value map because provenance now has to be per kind, and the
tuple stays as a thin wrapper so existing callers do not change behaviour."
```

---

### Task 2: `scope.py` —— 按 kind 继承

**Files:**
- Modify: `src/research_os/research/scope.py`
- Test: `tests/unit/test_scope.py`（改 3 条断言、追加 2 条）

- [ ] **Step 1: 改测试（逐条点名，替换原计划的「凡是…的地方」）**

`tests/unit/test_scope.py` 共 **3 条**断言要改（审验实跑：装配接口改动后该文件 2 条显红 + 1 条被前一条掩盖的 KeyError）：

| 行 | 原断言 | 新断言 | 实跑报错 |
|---|---|---|---|
| 144 | `assert scopes[chunks[1].id].conditions == ("backbone=transformer",)` | `assert scopes[chunks[1].id].conditions == {"backbone": "transformer"}` | `AssertionError: assert {'backbone': 'transformer'} == ('backbone=transformer',)` |
| 145 | `assert scopes[chunks[1].id].inherited_from["conditions"] == "section-first-mention"` | `assert scopes[chunks[1].id].condition_tiers == {"backbone": "section-first-mention"}` | Task 2 实现不再写 `provenance["conditions"]`；实跑 `inherited_from -> {'task': 'heading', 'datasets': 'heading'}`、`inherited_from["conditions"] -> KeyError 'conditions'`。该键在 `src/` 里已无消费点（唯一读点 `claims.py:183` 由 Task 3 删除），**不要**为它补兼容写入 |
| 162 | `assert scopes[chunks[1].id].conditions == ("backbone=cnn",)` | `assert scopes[chunks[1].id].conditions == {"backbone": "cnn"}` | `AssertionError: assert {'backbone': 'cnn'} == ('backbone=cnn',)` |

第 78 行 `assert scopes[chunks[0].id] == BlockScope(task=None, datasets=frozenset(), inherited_from={})` **不改**：新增字段都是默认空 dict，两边相等仍成立（实测该条未红）。`BlockScope(...)` 既有构造都是关键字参数且未传 `conditions`，不受「tuple→dict」影响；`test_claim_direction.py:13` 的 `BlockScope("image restoration")` 是位置参数但只占 `task`，仍有效。

追加 **2 条**（原 Files 行写「追加 1 条」与代码块、Step 5 累计数 +2 矛盾；在装配后副本实跑 `2 passed, 12 deselected`）：

```python
def test_inheritance_fills_only_the_missing_kinds():
    """A heading that names the backbone must not erase a `training=` the section
    established two chunks later: S4 inherits per kind (design §8.2)."""
    from research_os.domain.models import DocumentChunk
    from research_os.research.scope import build_section_scopes

    chunks = [
        DocumentChunk(id="c0", source_version_id="sv", section="4 Method", page_index=0,
                      chunk_index=0, text="We train a Transformer backbone."),
        DocumentChunk(id="c1", source_version_id="sv", section="4 Method", page_index=0,
                      chunk_index=1, text="All models are trained from scratch."),
    ]
    scopes = build_section_scopes(chunks)

    assert scopes["c1"].conditions == {"backbone": "transformer", "training": "from-scratch"}
    assert scopes["c1"].condition_tiers == {
        "backbone": "section-first-mention",
        "training": "section-first-mention",
    }


def test_a_heading_condition_keeps_its_own_tier_when_a_sentence_adds_another_kind():
    from research_os.domain.models import DocumentChunk
    from research_os.research.scope import build_section_scopes

    chunks = [
        DocumentChunk(id="c0", source_version_id="sv", section="4.1 Transformer backbone",
                      page_index=0, chunk_index=0, text="Results follow."),
        DocumentChunk(id="c1", source_version_id="sv", section="4.1 Transformer backbone",
                      page_index=0, chunk_index=1, text="We evaluate zero-shot."),
    ]
    scopes = build_section_scopes(chunks)

    assert scopes["c1"].conditions == {"backbone": "transformer", "protocol": "zero-shot"}
    assert scopes["c1"].condition_tiers == {
        "backbone": "heading",
        "protocol": "section-first-mention",
    }
```

- [ ] **Step 2: 运行，确认失败**

预期：`AttributeError: 'BlockScope' object has no attribute 'condition_tiers'`。

- [ ] **Step 3: 实现**

`src/research_os/research/scope.py`：`BlockScope` 改为

```python
@dataclass(frozen=True)
class BlockScope:
    """Task/dataset/condition context a claim inherits from its section.

    Conditions are a kind->value map plus a kind->tier map, not one tuple with one
    tier: S4 added two high-frequency kinds, and a single tier would either
    over-claim (a `sentence` covering an inherited backbone) or under-claim (an
    inherited backbone sinking a sentence-stated protocol). Each kind keeps the
    tier it actually came from.
    """

    task: str | None = None
    datasets: frozenset[str] = frozenset()
    inherited_from: dict[str, str] = field(default_factory=dict)
    conditions: dict[str, str] = field(default_factory=dict)
    condition_tiers: dict[str, str] = field(default_factory=dict)
```

`build_section_scopes` 里条件那段改为：

```python
        conditions: dict[str, str] = extract_condition_map(section or "")
        tiers: dict[str, str] = {kind: "heading" for kind in conditions}
        if not conditions:
            for member in group:
                found = extract_condition_map(member.text)
                if found:
                    conditions = dict(found)
                    tiers = {kind: "section-first-mention" for kind in found}
                    break
        # Per-kind top-up: a heading that names one kind must not stop the section
        # from contributing the others (design §8.2).
        for member in group:
            for kind, value in extract_condition_map(member.text).items():
                if kind not in conditions:
                    conditions[kind] = value
                    tiers[kind] = "section-first-mention"
```

并把 `BlockScope(task, inherited, dict(provenance), conditions)` 改成
`BlockScope(task, inherited, dict(provenance), conditions, tiers)`。

**注意**：上面这段新代码**不再写** `provenance["conditions"]`（原第 105/111 行的 `heading` / `section-first-mention` 两处随旧分支一起删除）。这不是遗漏：provenance 已按 kind 落在 `condition_tiers`，一个全局 `inherited_from["conditions"]` 无法表达「backbone 来自 heading、protocol 来自首句」，留着会误导。Step 1 已把 `test_scope.py:145` 改为断言 `condition_tiers`；`inherited_from` 此后只保留 `task` / `datasets` 两个键。

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_scope.py -v --basetemp=.pytest_tmp_s4_t2_green
```

预期：全绿（含两条新用例）。

- [ ] **Step 5: 全量**

预期：`414 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/scope.py tests/unit/test_scope.py
git commit -m "feat(scope): inherit conditions per kind, with per-kind tiers

A heading that names the backbone used to freeze the whole tuple. Two new
high-frequency kinds make that untenable, so each kind is filled independently and
carries the tier it actually came from."
```

---

### Task 3: `claims.py` —— 按 kind 合并 + 按 kind 的 tier

**Files:**
- Modify: `src/research_os/research/claims.py:86-125,177-185,232-243`
- Test: `tests/unit/test_claim_conditions.py`（追加 2 条）

- [ ] **Step 1: 写会失败的测试**

**审验修正**：`extract_identity` 的签名是 `(text, *, source_version_id, scope, quantitative)`（`claims.py:210`），`source_version_id` 是 **keyword-only**。原计划两条新用例把 `"sv_1"` 当位置参数传，实跑 `TypeError: extract_identity() takes 1 positional argument but 2 positional arguments (and 2 keyword-only arguments) were given`；下面已改为 `source_version_id="sv_1"`，改后实跑 `1 passed`。

```python
def test_a_sentence_stating_one_kind_keeps_the_inherited_others():
    """The core of design §8.2: "ours reaches 70% with 5-shot" states a protocol
    and nothing else, so the section's backbone and training must survive, each
    with its own tier."""
    scope = BlockScope(
        task="denoising",
        datasets=frozenset({"SIDD"}),
        inherited_from={"conditions": "section-first-mention"},
        conditions={"backbone": "transformer", "training": "from-scratch"},
        condition_tiers={"backbone": "section-first-mention", "training": "section-first-mention"},
    )
    identity = extract_identity(
        "Our method reaches 70% with 5-shot on SIDD.",
        source_version_id="sv_1", scope=scope, quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer", "protocol=5-shot", "training=from-scratch")
    assert identity.condition_tiers == {
        "protocol": "sentence",
        "backbone": "section-first-mention",
        "training": "section-first-mention",
    }


def test_a_sentence_kind_overrides_the_inherited_value_for_that_kind_only():
    scope = BlockScope(
        conditions={"backbone": "cnn"},
        condition_tiers={"backbone": "section-first-mention"},
    )
    identity = extract_identity(
        "The Transformer backbone improves PSNR on SIDD.",
        source_version_id="sv_1", scope=scope, quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer",)
    assert identity.condition_tiers == {"backbone": "sentence"}
```

- [ ] **Step 2: 运行，确认失败**

预期：`AttributeError: 'ClaimIdentity' object has no attribute 'condition_tiers'`。

- [ ] **Step 3: 实现**

`ClaimIdentity`：把 `conditions_from: str | None` 换成

```python
    # Provenance, not identity: which tier each kind's value came from. Excluded
    # from the key for the same reason `subject_inferred` is - it says where a
    # value came from, not what it is. S4 made this per kind because one tier for
    # the whole tuple either over- or under-claims (design §8.2).
    condition_tiers: dict[str, str] = field(default_factory=dict, compare=False)
```

`_conditions()` 改为：

```python
def _conditions(text: str, scope: BlockScope | None) -> tuple[tuple[str, ...], dict[str, str]]:
    """Sentence kinds win per kind; inherited kinds fill the rest, each keeping
    its own tier.

    Per kind, not per tuple: a sentence that states only a protocol must not drop
    the section's backbone, and its own tier must not leak onto the inherited
    values (design §8.2's counter-example).
    """
    own = extract_condition_map(text)
    merged: dict[str, str] = {}
    tiers: dict[str, str] = {}
    if scope is not None:
        for kind, value in scope.conditions.items():
            merged[kind] = value
            tiers[kind] = scope.condition_tiers.get(kind, "section-first-mention")
    for kind, value in own.items():
        merged[kind] = value  # a sentence value supersedes the inherited one
        tiers[kind] = "sentence"
    ordered = tuple(f"{kind}={merged[kind]}" for kind in sorted(merged))
    return ordered, tiers
```

`extract_identity()` 里 `conditions, conditions_from = _conditions(...)` 改成
`conditions, condition_tiers = _conditions(...)`，并把 `conditions_from=conditions_from` 换成
`condition_tiers=condition_tiers`。

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_claim_conditions.py tests/unit/test_claim_identity.py -v \
  --basetemp=.pytest_tmp_s4_t3_green
```

预期：全绿。

**审验修正（逐条点名，替换原计划指向 `test_claim_identity.py` 的空条件句）**：`grep -n 'conditions_from' tests/unit/test_claim_identity.py` **0 命中**——`conditions_from` 的 3 条断言全在 `tests/unit/test_claim_conditions.py`。装配 `ClaimIdentity.conditions_from` 删除后的实测：

```
FAILED tests/unit/test_claim_conditions.py::test_conditions_carry_their_provenance
  E  AttributeError: 'ClaimIdentity' object has no attribute 'conditions_from'
FAILED tests/unit/test_claim_conditions.py::test_inherited_conditions_are_tagged_with_where_they_came_from
  E  AttributeError: 'tuple' object has no attribute 'items'   (claims.py:189)
FAILED tests/unit/test_claim_conditions.py::test_no_conditions_means_no_provenance
  E  AttributeError: 'ClaimIdentity' object has no attribute 'conditions_from'
```

逐条改（都在 `test_claim_conditions.py`）：

| 行 | 原 | 新 |
|---|---|---|
| 54 | `assert identity.conditions_from == "sentence"` | `assert identity.condition_tiers == {"backbone": "sentence"}` |
| 58–63 | `BlockScope(..., inherited_from={"conditions": "section-first-mention"}, conditions=("backbone=transformer",))` | `BlockScope(task="denoising", datasets=frozenset({"SIDD"}), conditions={"backbone": "transformer"}, condition_tiers={"backbone": "section-first-mention"})` —— 第 62 行的 tuple 不改成 dict 会触发上面的 `'tuple' object has no attribute 'items'` |
| 72 | `assert identity.conditions == ("backbone=transformer",)` | **不改**：`identity.conditions` 仍是 tuple（`_conditions` 返回的 `ordered`），只有 `BlockScope.conditions` 变 dict |
| 73 | `assert identity.conditions_from == "section-first-mention"` | `assert identity.condition_tiers == {"backbone": "section-first-mention"}` |
| 85 | `assert identity.conditions_from is None` | `assert identity.condition_tiers == {}` |

`tests/unit/test_claim_identity.py` **一条都不改**（实测 22 条全绿）；`test_claim_identity.py:73/82` 的 `BlockScope(task=..., datasets=..., inherited_from={})` 未传 `conditions`，用默认空 dict，不受影响；`test_claim_identity.py:123` 的 `ClaimIdentity(...)` 构造也没传 `conditions_from`，新增字段有默认值。

- [ ] **Step 5: 全量**

预期：`416 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/claims.py tests/unit/test_claim_conditions.py
git commit -m "feat(claims): merge conditions per kind and track a tier per kind

identity_key keeps its seven segments and its sorted kind=value format; only the
provenance moves from one tier per tuple to one tier per kind."
```

---

### Task 4: `claim_builder.py` —— 落库形态改为按 kind

**Files:**
- Modify: `src/research_os/research/claim_builder.py:101-108`
- Test: `tests/unit/test_claim_merge.py`（改 1 条）

- [ ] **Step 1: 改测试（逐条点名 + 删 `...` 占位符）**

`tests/unit/test_claim_merge.py::test_condition_provenance_reaches_the_claim` 有 **3 条**断言读旧 flag（第 110、112、114 行），装配后实测：

```
FAILED tests/unit/test_claim_merge.py::test_condition_provenance_reaches_the_claim
E   AssertionError: expected the inherited condition to be tagged on the claim
E   assert []
```

原计划的新函数体写了 `...`（Ellipsis 占位）且 `claims` 未定义——**跑不起来**。整条替换为（在装配后副本实跑 `9 passed`）：

```python
def test_conditions_provenance_is_recorded_per_kind():
    """One flag per kind, `condition_tier=<kind>:<tier>`. A single flag could not
    say "the backbone was inherited but the protocol was stated"."""
    claims, _ = _build(["paper_conditions.md"])

    # 原第 110 行：改前缀；原第 112 行：改成带 kind 的具体值断言，不只断言存在
    tagged = [c for c in claims if any(p.startswith("condition_tier=") for p in c.conditions)]
    assert tagged, "expected the inherited condition to be tagged on the claim"
    assert "condition_tier=backbone:section-first-mention" in tagged[0].conditions
    # 旧形态必须真的消失（只断言新形态在，会让「两种都在」的错实现通过）
    assert all(not p.startswith("conditions_from=") for c in tagged for p in c.conditions)
    # 原第 114 行：provenance 仍不进 identity_key，只是换了前缀
    assert "condition_tier" not in (tagged[0].identity_key or "")
    assert all(
        p.split("=", 1)[1].count(":") == 1
        for c in tagged for p in c.conditions if p.startswith("condition_tier=")
    )
```

（`paper_conditions.md` 的 section 首句只给 `backbone`，tier 为 `section-first-mention`，故上面具体值固定。）

- [ ] **Step 2: 实现**

`claim_builder.py` 里替换 flag 那一段：

```python
            for kind, tier in sorted(identity.condition_tiers.items()):
                # Provenance per kind, persisted beside the quality flags: the
                # cascade needs to know which kinds a claim actually stated, and a
                # single tier for the whole tuple cannot say that (design §8.2).
                flags = [*flags, f"condition_tier={kind}:{tier}"]
```

- [ ] **Step 3: 运行 + 全量**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_claim_merge.py tests/integration/test_claim_synthesis.py -q \
  --basetemp=.pytest_tmp_s4_t4_green
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s4_t4_all
```

预期：`416 passed, 2 skipped`（本任务只改形态，不改用例数）。

- [ ] **Step 4: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/claim_builder.py tests/unit/test_claim_merge.py
git commit -m "feat(claims): persist one provenance flag per condition kind

The cascade has to know which kinds a claim stated, and 'conditions_from=sentence'
cannot express 'backbone inherited, protocol stated'."
```

---

### Task 5: `contradiction.py` —— 按 kind 确认同一设置

**Files:**
- Modify: `src/research_os/research/contradiction.py:118-135,213-242`
- Test: `tests/unit/test_contradiction_cascade.py`（改辅助函数 2 处 + **16 处** `conditions_from=` 调用 + **2 条** explanation 断言、追加 2 条）
- Test: `tests/unit/test_contradiction_assessor.py`（改 **3 处** flag 构造，原计划完全漏了这个文件）
- Test: `tests/unit/test_evaluate_contradiction.py`（由 Task 6 的脚本改动带绿，本任务不动）

- [ ] **Step 1: 把 `_claim()` 切换成按 kind（从 Task 1 移来，本任务与门同一步）**

`tests/unit/test_contradiction_cascade.py` 的 `_claim()` 改为收 `tiers`，并生成**每 kind 一个** flag：

```python
def _claim(
    subject="restormer",
    dataset="sidd",
    metric="psnr",
    direction="UP",
    conditions="",
    bucket="psnr=39.18",
    text="x",
    tiers: dict[str, str] | None = None,
) -> Claim:
    key = "|".join([subject, "image restoration", dataset, metric, direction, conditions, bucket])
    flags = [f"condition_tier={kind}:{tier}" for kind, tier in sorted((tiers or {}).items())]
    return Claim(text=text, status=ClaimStatus.SUPPORTED, identity_key=key, conditions=flags)
```

（`identity_key` 第 6 段带 `kind=value`，`conditions` 列表带 `condition_tier=<kind>:<tier>`；两者本任务必须一起切，见 Task 1 Step 1 的实跑证据。）

- [ ] **Step 2: 逐条点名 16 处调用 + 2 条 explanation 断言（替换原计划的「改 1 条」）**

`grep -n "conditions_from=" tests/unit/test_contradiction_cascade.py` 共 **18** 处字面量：第 20 行签名默认值、第 23 行生成 flag 的 f-string（Step 1 已改）、其余 **16 处**是 `_claim()` 调用参数：

| 行 | 用例 | 原值 | 新写法 |
|---|---|---|---|
| 74, 76 | `test_different_conditions_with_the_same_direction_are_complementary` | `sentence` | `tiers={"backbone": "sentence"}` |
| 97, 98 | `test_same_explicit_scope_and_opposite_direction_is_a_true_contradiction` | `sentence` | 同上 |
| 131, 132 | `test_equal_but_inherited_conditions_do_not_prove_a_contradiction` | `section-first-mention` | `tiers={"backbone": "section-first-mention"}` |
| 144, 145 | `test_heading_level_conditions_are_evidence` | `heading` | `tiers={"backbone": "heading"}` |
| 153, 154 | `test_inherited_conditions_can_still_disprove_a_shared_setup` | `section-first-mention` | 同 131 |
| 166, 167 | `test_every_opposite_pair_combination`（parametrize 3 组） | `sentence` | 同 74 |
| 199, 200 | `test_unknown_provenance_tier_cannot_prove_a_contradiction` | **`legacy-unknown`** | `tiers={"backbone": "legacy-unknown"}` —— 原计划括号里只写了 `heading`/`section-first-mention`，漏了这一组；它测「未知 tier 仍不确认」，必须保留 |
| 208, 209 | `test_sentence_level_conditions_are_evidence` | `sentence` | 同 74 |

`test_missing_provenance_cannot_prove_a_contradiction`（第 186–187 行）本来就不传 tier，**不改调用**，只改它的断言。

还有 **2 条**读 explanation 文案的断言（原计划未点名，实测必红，因为新门文案是 `opposite direction, but kind(s) backbone not confirmed on both sides`）：

| 行 | 原断言 | 新断言 | 实测报错 |
|---|---|---|---|
| 138 | `assert "inherited" in result.explanation` | `assert "backbone" in result.explanation and "not confirmed" in result.explanation` | `AssertionError: assert 'inherited' in 'opposite direction, but kind(s) backbone not confirmed on both sides'` |
| 193 | `assert "provenance missing" in result.explanation` | `assert "not confirmed" in result.explanation` | `AssertionError: assert 'provenance missing' in 'opposite direction, but kind(s) backbone not confirmed on both sides'` |

`tests/unit/test_contradiction_assessor.py` 的 `_claim()` 是**另一个**辅助函数（不共享），第 24、116、141 行直接写 `conditions=["conditions_from=sentence"]`，3 处全改成 `conditions=["condition_tier=backbone:sentence"]`（其 `identity_key` 第 6 段恒为 `backbone=cnn`）。不改断言——实测该文件的 2 条红是

```
FAILED ...::test_emitted_types_are_counted
  E  AssertionError: assert {'INSUFFICIENT_EVIDENCE': 1} == {'TRUE_CONTRADICTION': 1}
FAILED ...::test_one_bad_pair_does_not_stop_the_others
  E  AssertionError: assert {'INSUFFICIENT_EVIDENCE'} == {'TRUE_CONTRADICTION'}
```

改完 flag 后两文件的完整改造在装配后副本实跑 `30 passed in 0.19s`（cascade 24 + assessor 6）。

- [ ] **Step 3: 追加 2 条新用例（写会失败的测试）**

```python
def test_one_unconfirmed_kind_blocks_a_true_contradiction():
    """HD-014, per kind: a shared setup needs *every* shared kind confirmed. The
    inherited backbone makes "same setup" unproven even though the protocol was
    stated in both sentences."""
    a = _claim(direction="UP", conditions="backbone=transformer;protocol=5-shot",
               tiers={"backbone": "section-first-mention", "protocol": "sentence"})
    b = _claim(direction="DOWN", conditions="backbone=transformer;protocol=5-shot",
               tiers={"backbone": "sentence", "protocol": "sentence"})

    result = assess_pair(a, b)

    assert result.relationship is ContradictionType.INSUFFICIENT_EVIDENCE
    assert "backbone" in result.explanation
    assert "protocol" not in result.explanation  # 只点名未确认的 kind，正是「按 kind」的锁


def test_every_shared_kind_confirmed_still_reaches_a_true_contradiction():
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "sentence"})
    b = _claim(direction="DOWN", conditions="backbone=transformer", tiers={"backbone": "heading"})

    result = assess_pair(a, b)

    assert result.relationship is ContradictionType.TRUE_CONTRADICTION
```

**鉴别力说明**：旧门 `_conditions_from()` 读不到 `condition_tier=`，一律降级为 `INSUFFICIENT_EVIDENCE`，所以第一条用例的 `relationship` 断言在旧门下**也已通过**，它的红→绿来自 explanation 里出现具体 kind 名；真正承担行为红→绿的是第二条（旧门 `INSUFFICIENT_EVIDENCE` → 新门 `TRUE_CONTRADICTION`）。两条一起才构成变异锚点。

- [ ] **Step 4: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_contradiction_cascade.py -k "unconfirmed_kind or every_shared_kind" -q \
  --basetemp=.pytest_tmp_s4_t5_red
```

**审验修正**：原计划写的预期 `assert ContradictionType.INSUFFICIENT_EVIDENCE is ContradictionType.TRUE_CONTRADICTION`（旧实现只看一个 tier）**不是实际报错**。仓库外副本实跑（旧门 + 新 `_claim()`）：

```
$ pytest ... -k "unconfirmed_kind or every_shared_kind"
FAILED ...::test_one_unconfirmed_kind_blocks_a_true_contradiction
E   AssertionError: assert 'backbone' in 'opposite direction, but side A/B: conditions provenance missing or unknown; setup not confirmed'
FAILED ...::test_every_shared_kind_confirmed_still_reaches_a_true_contradiction
E   AssertionError: assert <ContradictionType.INSUFFICIENT_EVIDENCE: 'INSUFFICIENT_EVIDENCE'> is <ContradictionType.TRUE_CONTRADICTION: 'TRUE_CONTRADICTION'>
2 failed, 22 deselected in 0.22s
```

- [ ] **Step 5: 实现**

`_conditions_from` 换成：

```python
def _condition_tiers(claim: Claim) -> dict[str, str]:
    """kind -> tier, read from the per-kind flags (ADR-036).

    A row written before S4 carries `conditions_from=<tier>` and no per-kind
    flags; it reads as "no confirmed kinds", which is the safe direction - an old
    measurement row must not license a TRUE_CONTRADICTION it never supported.
    """
    tiers: dict[str, str] = {}
    for item in claim.conditions:
        if item.startswith("condition_tier="):
            kind, _, tier = item.split("=", 1)[1].partition(":")
            if kind and tier:
                tiers[kind] = tier
    return tiers


def _kinds(claim: Claim) -> set[str]:
    return {item.split("=", 1)[0] for item in _conditions(claim)}
```

TRUE_CONTRADICTION 前的门改为：

```python
    if (direction_a, direction_b) in OPPOSITE:
        shared = _kinds(a) & _kinds(b)
        tiers_a, tiers_b = _condition_tiers(a), _condition_tiers(b)
        unconfirmed = [
            kind
            for kind in sorted(shared)
            if tiers_a.get(kind) not in _CONFIRMED_TIERS or tiers_b.get(kind) not in _CONFIRMED_TIERS
        ]
        if not shared or unconfirmed:
            reason = (
                "no condition kind is shared, so the setup cannot be the same one"
                if not shared
                else f"kind(s) {', '.join(unconfirmed)} not confirmed on both sides"
            )
            return _assessment(
                a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
                f"opposite direction, but {reason}",
                ConfidenceLabel.LOW,
            )
        return _assessment(
            a, b, ContradictionType.TRUE_CONTRADICTION,
            f"same scope, opposite direction: {direction_a} vs {direction_b}",
            ConfidenceLabel.DISPUTED,
        )
```

（`ConfidenceLabel.DISPUTED` 保持原样：本阶段不改置信标签。）

**级联逐分支核对（设计 §11 / ADR-028 / HD-014，实跑）**：`diff -u` 现有 `contradiction.py` 与本计划的改动只允许 **2 处**（`_conditions_from` 函数定义 → `_condition_tiers` + `_kinds`；`OPPOSITE` 分支的门）。其余 8 个分支逐字不动，实跑关系类型与顺序：

| 分支 | 结果（实跑） |
|---|---|
| dataset 不同 | `SCOPE_DIFFERENCE` |
| conditions 不同 | `SCOPE_DIFFERENCE` / `COMPLEMENTARY`（**不看 provenance**——HD-014「继承条件不相等仍可否证相同」原样保留） |
| metric 无交集 | `EXPERIMENTAL_INCOMPATIBILITY` |
| 一侧无 conditions | `INSUFFICIENT_EVIDENCE` |
| 方向缺失 | `INSUFFICIENT_EVIDENCE: direction not stated on side B` |
| **OPPOSITE 门（唯一改动）** | 共有 kind 全确认 → `TRUE_CONTRADICTION`；否则 `INSUFFICIENT_EVIDENCE` |
| bucket 不同 | `EXPERIMENTAL_INCOMPATIBILITY` |
| 一侧无 bucket | `INSUFFICIENT_EVIDENCE` |

**四种组合实跑**（新门，`assess_pair`）：① 两侧共有 kind 全确认 → `TRUE_CONTRADICTION` / `DISPUTED`；② 一侧某 kind 未确认（或两侧都继承）→ `INSUFFICIENT_EVIDENCE`，explanation `kind(s) backbone[, protocol] not confirmed on both sides`；③ 两侧共有 kind 为空：disjoint 条件被**前置的「conditions 不同」分支**判 `SCOPE_DIFFERENCE`，两侧全空被「一侧无 conditions」判 `INSUFFICIENT_EVIDENCE`——**都走不到新门**。因此实现里的 `if not shared` 分支在真实级联中是防御性死代码（`conditions_a == conditions_b` 且都非空才到 OPPOSITE），但保留它作安全网；不要为「触发它」去改前置分支，那会违反 §11。

**`_kinds()` 不会把 flag 当条件**：`_kinds(claim)` 调的是现有 `_conditions(claim)`（`contradiction.py:118`，从 `identity_key` 第 6 段解析），**不是** `claim.conditions` 列表。实跑：给 `claim.conditions` 塞 `subject_inferred`、`quantitative_unstructured`、`conditions_from=sentence`、`scope_undetermined` 后，`_kinds(claim)` 仍只返回 `['backbone', 'protocol']`，`_condition_tiers(claim)` 只返回 `{'backbone': 'sentence', 'protocol': 'heading'}`（只认 `condition_tier=` 前缀）。flag 不进 key，因此不会被误读成 kind。

- [ ] **Step 6: 运行 + 全量**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_contradiction_cascade.py -q --basetemp=.pytest_tmp_s4_t5_green
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s4_t5_all
```

预期：`418 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/contradiction.py tests/unit/test_contradiction_cascade.py tests/unit/test_contradiction_assessor.py
git commit -m "feat(contradiction): require every shared condition kind to be confirmed

HD-014 per kind: an inherited backbone no longer hides behind a sentence-stated
protocol. Legacy rows without per-kind flags read as unconfirmed, which is the
direction that cannot invent a contradiction."
```

---

### Task 6: 离线脚本跟随 + 三份 before/after 报告

**Files:**
- Modify: `scripts/holdout_contradiction_quality.py:36`、`scripts/evaluate_contradiction.py:59`
- Create: `docs/evaluation/2026-11-15-s4-claim-quality.md`
- Create: `docs/evaluation/2026-11-15-s4-contradiction-quality.md`
- Create: `docs/evaluation/2026-11-15-s4-method-acquisition.md`

- [ ] **Step 1: 脚本跟随（原计划「两处只是展示，不改判据」是错的，审验重写）**

`--help` 实跑确认两处性质不同：**没有一处是「只是展示」**。

**① `scripts/evaluate_contradiction.py:59-63` 是判定输入**，不是展示——它构造 `Claim.conditions` flag 直接喂给 `assess_pair`。原计划说「改为读新标记（多值按 `、` 连接后原样带出）」会产出 `condition_tier=backbone:sentence、protocol:sentence` 这种乱串，新门 `partition(":")` 解析出的 tier 不在 `_CONFIRMED_TIERS`，26 对夹具会全崩。实跑（只改源码、脚本未改）：

```
overall n=26 judged=21 correct=17 acc=81.0%
TRUE_CONTRADICTION precision=0.0% recall=0.0%
misclassified: p04 / p14 / p15 / p26  expected TRUE_CONTRADICTION, got INSUFFICIENT_EVIDENCE
FAILED tests/unit/test_evaluate_contradiction.py::test_the_fixture_set_matches_the_cascade_it_pins
```

正确改法（`pairs.json` 仍存每侧一个全局 tier，kind 从该侧 `identity_key` 第 6 段取，正是新门读的地方）：

```python
        for side, claim in (("a", a), ("b", b)):
            provenance = entry.get(f"{side}_conditions_from")
            if provenance:
                # S4: one flag per kind. pairs.json keeps one global tier per
                # side; the kinds come from that side's identity_key 6th segment,
                # which is exactly what the new per-kind gate reads.
                segment = (claim.identity_key or "").split("|")[5]
                kinds = [item.split("=", 1)[0] for item in segment.split(";") if item]
                claim.conditions = [
                    f"condition_tier={kind}:{provenance}" for kind in sorted(set(kinds))
                ]
```

改后实跑 `acc=100.0%`、`precision/recall=100.0%`、`tests/unit/test_evaluate_contradiction.py 8 passed`。`pairs.json` 的 `a_conditions_from` / `b_conditions_from` 字段**不删改名**（`note` 与 `ANNOTATION.md` 里补一句「该全局 tier 按第 6 段 kind 展开成每 kind 一个 flag」），`test_fixture_consistency.py` 只读 `a_key`/`a_text`，不受影响。

**② `scripts/holdout_contradiction_quality.py:34-38,70-79,108-115` 是统计口径**，不是展示。`_tier()` 返回单个 tier，后面 `pair = {tier_a, tier_b}`、`if "section-first-mention" in pair` 全是单值语义。只把第 36 行的前缀改成 `condition_tier=`（多值连接）会让整段失效。实跑（只改源码、脚本未改）：

```
=== condition provenance of assessed pairs ===   (基线: either_side_first_mention 25 / sentence_or_unspecified 5)
  sentence_or_unspecified          30          <-- 25 条 section-first-mention 全部丢失
```

正确改法：

```python
def _tiers(claim) -> set[str]:
    """Every kind's tier, read off the per-kind flags (S4)."""
    return {
        item.split("=", 1)[1].split(":", 1)[1]
        for item in claim.conditions
        if item.startswith("condition_tier=")
    }
```
```python
    tiers_by_id = {c.id: _tiers(c) for c in claims}
    tiers = Counter()
    for item in assessments:
        pair = tiers_by_id.get(item.claim_a_id, set()) | tiers_by_id.get(item.claim_b_id, set())
        if "section-first-mention" in pair:
            tiers["either_side_first_mention"] += 1
        elif pair & {"heading"}:
            tiers["heading_involved"] += 1
        else:
            tiers["sentence_or_unspecified"] += 1
```

改后实跑 `either_side_first_mention 27 / heading_involved 2 / sentence_or_unspecified 1`（基线 25 / 0 / 5）：口径从「整条一个 tier」变成「每 kind 一个 tier 的并集」，一条 claim 可同时贡献多个 tier，数字变化**必须**在报告 §1 并列登记为 before/after，不许说成「无变化」。

- [ ] **Step 2: 重跑三条度量（before 一列不删不改）**

**审验修正 1 — 参数**：设计 §10.5 三条命令都用 `--ids-file`；原计划第一条写成 `--papers 20`，会走 `collect_ids()` 实时 arXiv 查询（见脚本 `:100-104`），拿到的是**另一批**论文，与另外两个脚本的固定 20 篇不可并列，且离线环境必失败。`--help` 实跑的真实参数：

```
$ python scripts/holdout_claim_quality.py --help
usage: ... [-h] [--papers PAPERS] [--ids-file IDS_FILE] [--query QUERY]
  --ids-file IDS_FILE  read arXiv ids from a file ... instead of querying the API
$ python scripts/holdout_contradiction_quality.py --help
usage: ... [-h] [--ids-file IDS_FILE]          # 只有 --ids-file，没有 --papers
$ python scripts/method_acquisition_audit.py --help
usage: ... [-h] --labels LABELS [--cache CACHE] [--describer {none,recorded}]
$ python scripts/evaluate_contradiction.py --help
usage: ... [-h] [--json JSON]
```

**审验修正 2 — 临时文件**：原计划把输出写进仓库内 `.s4_*.txt`，`.gitignore` 只忽略 `.pytest_tmp*` / `.holdout_cache/`，这 3 个文件会成为未跟踪文件，Task 7 Step 5 的「工作区干净」直接失败。改写到仓库外临时目录。

```bash
cd /d/ResearchOS && OUT="$(mktemp -d)"
"D:/Anaconda/envs/reOS/python.exe" scripts/holdout_claim_quality.py \
  --ids-file docs/evaluation/holdout-ids-2026-11-12.txt \
  > "$OUT/s4_claim_after.txt" 2>&1 && tail -20 "$OUT/s4_claim_after.txt"
"D:/Anaconda/envs/reOS/python.exe" scripts/holdout_contradiction_quality.py \
  --ids-file docs/evaluation/holdout-ids-2026-11-12.txt \
  > "$OUT/s4_contra_after.txt" 2>&1 && tail -20 "$OUT/s4_contra_after.txt"
"D:/Anaconda/envs/reOS/python.exe" scripts/method_acquisition_audit.py \
  --labels tests/fixtures/method_acquisition/labels.json \
  > "$OUT/s4_method_after.txt" 2>&1 && tail -20 "$OUT/s4_method_after.txt"
```

三条用 `&&`（原计划用 `;`，脚本失败也会 tail 而掩盖失败）。`--ids-file` 给定时 `--papers` 默认 20，正好等于 `holdout-ids-2026-11-12.txt` 的 20 行，不必另给。

**每份要记的指标与 before 来源**（`docs/evaluation/` 现有报告逐格核对）：

| 指标 | before 来源（原数字不删不改） |
|---|---|
| 主张总数 / supported / merge gate / 方向分布 / `TRUE_CONTRADICTION` 数 | `docs/evaluation/2026-11-13-p5-contradiction.md` §3（1173 / 1075 / 73 / 真矛盾 0） |
| 条件 provenance 分布 | `docs/evaluation/2026-11-13-p5-contradiction.md`（25 / 0 / 5，见本任务 Step 1 实跑） |
| L1–L4 四格、gaps | `docs/evaluation/2026-11-14-method-acquisition-audit.md` / `2026-11-15-method-acquisition-s2.md` |
| `identity_key` 唯一数、合并组数 | **既有报告没有这两个指标**——不许虚构 before。在 S4 动手**之前**用 `git worktree add "$(mktemp -d)/s3" HEAD` 建一个 S3 快照工作树（HEAD 即 S3 收官提交，见交接 §0），在其中的 `.holdout_cache/` 副本上用同一 `--ids-file` 跑一次同一个脚本得到，作为「新增 before」并列登记并注明来源；仍**不覆盖**任何既有报告文件 |

- [ ] **Step 3: 三份报告**

每份都用同一结构（before 必须来自既有报告，**不许重算覆盖**、**旧数字不删不改**）。三份的 before 来源对应：

| 报告文件 | before 来源 |
|---|---|
| `docs/evaluation/2026-11-15-s4-claim-quality.md` | `docs/evaluation/2026-11-13-p5-contradiction.md` §3 + S3 快照重跑（见 Step 2 表） |
| `docs/evaluation/2026-11-15-s4-contradiction-quality.md` | `docs/evaluation/2026-11-13-p5-contradiction.md` §3 / §5 |
| `docs/evaluation/2026-11-15-s4-method-acquisition.md` | `docs/evaluation/2026-11-14-method-acquisition-audit.md` + `2026-11-15-method-acquisition-s2.md` |

```markdown
# S4 实测：主张质量（2026-11-15）

> before 来源：`docs/evaluation/2026-11-13-p5-contradiction.md` §3（原数字未改）
> after 命令：`python scripts/holdout_claim_quality.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt`

## 1. before / after

| 指标 | before | after | 差值 | 解释 |
|---|---|---|---|---|
| claims | 1173 | 1173 | 0 | 见 §2 |
| supported | 1075 | 1075 | 0 | |
| relations | 1081 | 1081 | 0 | |
| distinct mergeable keys | 73 | 73 | 0 | |

## 2. 变化归因（设计 §8.4 要求，逐句类，不是只报总数）

S4 同时做了两件方向相反的事，**必须分开归因**，但**方向以实测为准，不得预设「上升」**：

1. 新增 `scale=` / `protocol=` → 命中句的 `identity_key` 第 6 段变化。
2. provenance 改为按 kind → 此前被整条覆盖的 `training=` / `backbone=` 回到 key 里。

审验实跑（仓库外副本，S3 代码 vs 本计划装配代码，同一 `--ids-file`）：

- **40 篇留出集**：命中句 146（scale 89 / protocol 57），第 6 段带 `scale=`/`protocol=` 的 claim **455 条**，claims 总数 **2576 → 2576**（不变）。
- **20 篇 `holdout_claim_quality.py` 口径**：claims **1173 → 1173**、supported **1075 → 1075**、relations **1081 → 1081**、`distinct mergeable keys 73 → 73`，per-document 每篇 claims 数逐篇相同。
- 即：**第 6 段变了很多行，主张数一条没变**。原因是 `mergeable()` 要求 subject+dataset+direction 三者齐全（20 篇里只有 73 条满足），而按 kind 继承让同一 section 的所有句子继承到**相同**的条件，合并边界不变。

因此 §2 必须逐条列出：哪些句子的第 6 段因 ① 变化、哪些因 ② 变化、哪些两者都有，以及**为什么这些变化没有拆开或合并任何一条主张**。「只报总数」或照抄设计 §8.4 的「主张数上升」都视为未完成。`TRUE_CONTRADICTION` 在 20 篇留出集上 before/after 都是 0（`assessments 30`、五类分布逐格相同），同样并列登记。

## 3. 已知未解决
```

另外两份报告把 §1 的指标行换成各自的：`contradiction-quality` 记 `assessments 30`、五类分布、`condition provenance`（25/0/5 → 27/2/1，见 Step 1）、`D13 downgrades 0`；`method-acquisition` 记 L1–L4 四格与 `gaps`。三份都保留「before 原数字未改」一行。

- [ ] **Step 4: 验收判据（设计 §8.4/§10）**

- `TRUE_CONTRADICTION` **不得因新维度增加**；若增加，逐对给出理由或回滚 Task 5。
- 主张数变化必须**逐项可解释**；解释不了的变化 → 回滚对应任务，不许「先合并再说」。

- [ ] **Step 5: 提交**

```bash
cd /d/ResearchOS && git add scripts/holdout_contradiction_quality.py scripts/evaluate_contradiction.py docs/evaluation/
git commit -m "docs(eval): measure S4 with before/after beside each other

Two changes pull the claim count in opposite directions, so each report attributes
the delta per sentence class instead of reporting one number."
```

---

### Task 7: ADR + 已知限制 + 设计 §13 + 交接

**Files:**
- Modify: `architect.md`（ADR-036、限制 19–20、维护记录）
- Modify: `docs/superpowers/specs/2026-11-15-method-acquisition-design.md`（§13 D22–D24）
- Modify: `docs/handover/2026-11-15-method-acquisition-handover.md`

- [ ] **Step 1: ADR-036**

```markdown
| ADR-036 | `conditions` 的内部表示改为 `dict[kind] -> value` + `dict[kind] -> tier`，`identity_key` 仍是 7 段、第 6 段仍排序拼接；矛盾判定只对**两侧共有**的 kind 要求 tier 确认。理由：S4 新增的 `scale=` / `protocol=` 是高频模式，整条覆盖会让一句 `5-shot` 抹掉继承来的 `training=`（覆盖率直接下降），并把 tier 升到 `sentence`，从而允许一个没有依据的 `TRUE_CONTRADICTION`。代价：旧库里的 `conditions_from=<tier>` 不再被读（按未确认处理），登记为已知限制 | ACTIVE |
```

- [ ] **Step 2: 已知限制**

```markdown
19. 存量数据库里的 `conditions_from=<tier>` 标记**不迁移**：S4 起读 `condition_tier=<kind>:<tier>`，旧行按「没有已确认 kind」处理。这是安全方向（不会凭空产生矛盾），但意味着**旧 run 的评估结果不能与新 run 直接比矛盾数**。
20. provenance 按 kind 之后，`identity_key` 第 6 段仍可能出现「同一句在不同 section 下 key 不同」的情况——继承是按 kind 补齐的，但 section 不同则继承值不同。这不是缺陷，是 ADR-027 的「继承即 section 上下文」原样延续。
```

- [ ] **Step 3: 设计 §13 D22–D24**

```markdown
| D22 | §8.2 「按 kind 记录 `dict[kind] -> (value, tier)`」 | 值仍是 `tuple[str, ...]`（进 key），tier 单列 `dict[kind] -> tier` | `ClaimIdentity.key()` 与矛盾判定都按 tuple 读；把值也改成 dict 会同时改读端与快照格式，收益为零。tier 与值分开存，正是「键不含 provenance」的既有约定 |
| D23 | §8.2 未说旧数据怎么办 | 旧 `conditions_from=` 不迁移，按未确认处理 | 迁移需要知道每条旧 claim 的每个 kind 来自哪一层，而旧数据只存了一个全局 tier——按它反推会给每个 kind 编一个来源。宁可少确认，不可错确认 |
| D24 | §8.1 说 `protocol` 取值见 §6.3 | 复用 S2 的 `_PROTOCOL` / `_SCALE_*` 正则字面量（`conditions.py` 内部复制，不 import `patterns.py`） | 两个模块服务不同层（单句 vs 论文级），共同的只有正则字面量；抽公共函数会让「改一处、两处行为一起变」，而它们需要独立演进（S2 的 scale 允许 `8xa100`，S4 的 condition 值还要过 `;`/`|` 断言） |
```

- [ ] **Step 3b: 本计划审验偏差（D25 起，记在本计划，不改动设计 §13 的 D1–D24）**

编号接 Task 7 Step 3 的 D22–D24（设计 §13 现到 D21），格式沿用设计 §13 的 `| # | 计划/设计 | 实际 | 性质与理由 |`：

| # | 计划/设计 | 实际（审验实测） | 处理 |
|---|---|---|---|
| D25 | 设计 §10.5 三条重测命令都用 `--ids-file` | 原计划 Task 6 Step 2 第一条写 `--papers 20`，触发 `collect_ids()` 实时 arXiv 查询，得到的是另一批论文，与另两个脚本的固定 20 篇不可并列，且离线必失败 | 改为 `--ids-file docs/evaluation/holdout-ids-2026-11-12.txt`；`--help` 实跑的真实参数写进 Step 2（尤其 `holdout_contradiction_quality.py` **只有** `--ids-file`） |
| D26 | 设计 §8.4「新增两维……部分合并拆开、主张数上升」；原计划报告模板 §2 写死「主张数**上升**」 | 实跑 before/after 逐格相同：20 篇 `holdout_claim_quality.py` claims 1173→1173、supported 1075→1075、relations 1081→1081、`distinct mergeable keys 73→73`；40 篇 claims 2576→2576；第 6 段带新 kind 的 claim 455 条但主张数不变 | 模板 §2 改成逐句类归因 + 实测数字，**不预设方向**，并写明原因（满足 `mergeable()` 门槛的句子仅 73 条、按 kind 继承让整节条件一致）；设计 §8.4 原文作为当时的预期保留、不删不改，报告里注明「本语料上未上升」 |
| D27 | 设计 §8.1/§9、交接 §9 起手第 4 条：「新值不得含 `;` 与 `|`（需断言）」 | 原计划 Task 1 的 4 条用例无此断言 | 并入 Task 1 第 1 条用例（遍历 8 个输入断言所有值不含分隔符），**不增用例数**以保住 418/420；实跑后果：值含 `;` → `_conditions(claim)` 解析出 `('protocol=5-shot','x=y','scale=7b')` 凭空多一个 kind，值含 `|` → `key.split("|")` 变 8 段 |
| D28 | 设计 §8.4「三份报告逐句类归因」、HD-015「26 对 100% 只是回归锁」；原计划 Task 6 Step 1 称「两处只是展示，不改判据」 | 实跑：`evaluate_contradiction.py:59` 是**判定输入**（源码改后脚本未改 → 4 条夹具 p04/p14/p15/p26 降级、acc 81.0%、回归锁红）；`holdout_contradiction_quality.py:36` 是**统计口径**（改前 25 条 `section-first-mention` 全丢、30 条全归 `sentence_or_unspecified`） | Task 6 Step 1 重写两处完整代码（前者按第 6 段 kind 展开 flag，后者 `_tiers()` 按 kind 聚合），点名 `test_evaluate_contradiction.py` 与 `pairs.json`；改后 acc 100%、回归锁 8 passed、统计 27/2/1 |
| D29 | 交接 §11「已知雷不要顺手改」、设计 §3「S4 独占一个度量周期」；原计划 Task 1 Step 1 先改 `test_contradiction_cascade.py::_claim()` 发 `condition_tier=`，门到 Task 5 才改 | 实跑（旧门 + 新 `_claim()`）`7 failed, 15 passed`，Task 1 Step 5 的 `412 passed` 不可能达成；`conditions_from=` 共 18 处字面量 | `_claim()` 改造整体移到 Task 5 Step 1、与门同一步切换；Task 1 只动 `conditions.py` + `test_claim_conditions.py`；`claims.py:180` 的修改明确标注为设计 §8.2 授权（非 §11 禁止的顺手改） |
| D30 | 原计划多处代码块不可执行 / 计数与编号不实 | 实跑：Task 1 的 3 条用例 `NameError: name 'extract_condition_map' is not defined`；Task 3 两条用例 `TypeError: extract_identity() takes 1 positional argument but 2 positional arguments ... were given`；Task 4 `...` 占位使 `claims` 未定义；Task 1 Step 4「11 passed（原 7+4）」实为 13（原 9+4）；Task 1 有两个 `Step 2`、Task 5 缺 `Step 2` | 逐条修正：补模块级 import、改 `source_version_id="sv_1"`、补全测试体、改 `13 passed`、Task 1 的两个 Step 2 改为 2a/2b、Task 5 重编号 Step 1–7；装配后副本实跑新用例 `1 passed` / `9 passed` / `30 passed` |
| D31 | 设计 §9、交接 §9「必带的两条对照测试」之 ②「仅在这两维不同的两句 → `may_merge() == False`（字段有值不算通过）」 | 原计划 7 个任务的用例里没有一条调 `may_merge`；验收表判据 1 却写了这条 | 把断言并入 Task 1 Step 2 的 `test_evaluation_protocol_is_a_condition`（含 `may_merge(a, a)` 对照，实跑 `not may_merge(a,b) and not may_merge(c,d)` 为真），**并入而非新增用例**，保住 10 条 / `418 passed / 420 collected`；验收判据 1 的「怎么验」改为指向该用例 |

- [ ] **Step 4: 维护记录 + 交接**

`architect.md` 维护记录加 S4 一行（测试数、三份报告、`TRUE_CONTRADICTION` 是否变化）。
交接文档：§0 改「S1–S4 全部收官，方法获取四阶段完成」；§6 数字改实测；§9 改成「后续待办」（不再有 S5）；§12 待办更新（#10 指标登记仍未做）。

- [ ] **Step 5: 收尾核对**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s4_final
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" --collect-only -q --basetemp=.pytest_tmp_s4_collect | tail -3
git status --short
```

预期：`418 passed, 2 skipped`、`420 tests collected`、工作区干净。

**计数核对（审验逐项数过）**：基线 `408 passed / 410 collected`；新增用例 **10 条** = Task 1 `+4`（`test_claim_conditions.py`）+ Task 2 `+2`（`test_scope.py` 的两条新用例）+ Task 3 `+2`（`test_claim_conditions.py`）+ Task 4 `+0`（改断言不改用例数）+ Task 5 `+2`（`test_contradiction_cascade.py`）。各任务末尾累计数逐项自洽：`412 → 414 → 416 → 416 → 418`，收官 `418 passed / 420 collected`。§8.1 的禁分隔符断言**并入** Task 1 第 1 条用例（不是第 5 条），所以不用改累计数；Task 5 的 `_claim()` 改造只改辅助函数与断言，也不增减用例数。

**逐条点名核对清单**（审验在仓库外副本按接口改动跑全量，实测 `17 failed, 391 passed, 2 skipped`；下面每一条都已在对应任务的 Step 1/2 给出新断言，收官时用这份清单点名核对，不许再写「若有用例红就改」）：

| # | 文件 | 会红的断言 | 处置任务 |
|---|---|---|---|
| 1–3 | `tests/unit/test_claim_conditions.py` | 第 54/73/85 行 `identity.conditions_from`；第 62 行 `conditions=("backbone=transformer",)` 触发 `'tuple' object has no attribute 'items'` | Task 3 Step 4 |
| 4 | `tests/unit/test_claim_merge.py` | 第 110/112/114 行 `conditions_from=` 三条 | Task 4 Step 1 |
| 5–6 | `tests/unit/test_contradiction_assessor.py` | 第 24/116/141 行 `conditions=["conditions_from=sentence"]` 导致 `test_emitted_types_are_counted`、`test_one_bad_pair_does_not_stop_the_others` 变 `INSUFFICIENT_EVIDENCE` | Task 5 Step 2 |
| 7–14 | `tests/unit/test_contradiction_cascade.py` | `test_same_explicit_scope...`、`test_equal_but_inherited...`（含第 138 行 `"inherited"`）、`test_heading_level...`、`test_every_opposite_pair_combination` ×3、`test_missing_provenance...`（第 193 行 `"provenance missing"`）、`test_sentence_level...` | Task 5 Step 2 |
| 15 | `tests/unit/test_evaluate_contradiction.py` | `test_the_fixture_set_matches_the_cascade_it_pins`（p04/p14/p15/p26） | Task 6 Step 1 |
| 16–17 | `tests/unit/test_scope.py` | 第 144/162 行 tuple 断言、第 145 行 `inherited_from["conditions"]`（KeyError） | Task 2 Step 1 |

**核对通过（题目清单里实测不会红，不要为它们加断言）**：`test_claim_identity.py`（22 条）、`test_contradiction_pairing.py`（7 条）、`test_fixture_consistency.py`（1 条）、`test_claim_synthesis.py`、`test_contradiction_run.py`、`test_contradiction_memo.py`、`test_evidence_quality.py`、`test_method_run.py` 在装配后副本全部保持绿——它们不读 `conditions_from`、不读 `BlockScope.conditions`、也不主张数/identity_key 的具体值；`named_paper.md` 的新 kind 只改变第 6 段内容，不改变这些断言。

**工作区干净**：Task 6 Step 2 的三份输出已改写到仓库外 `$(mktemp -d)`，`--basetemp` 用 `.pytest_tmp_s4_*`（`.gitignore` 的 `/.pytest_tmp*/` 已覆盖），因此 `git status --short` 应只剩本计划已列出的改动文件。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add architect.md docs/
git commit -m "docs(arch): record S4, the last two identity dimensions

ADR-036 pins the per-kind representation and what it costs: old rows stop being
read as confirmed, which is the only safe direction for a contradiction gate."
```

---

## 验收（S4 完成判据）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | 两维真的改变合并结果 | `test_claim_conditions.py::test_evaluation_protocol_is_a_condition` 里 `assert not may_merge(a, b) and not may_merge(c, d)` + 对照 `assert may_merge(a, a)`（设计 §9 / 交接 §9 必带，已并入 Task 1 Step 2） |
| 2 | 按 kind 的继承 | `test_a_sentence_stating_one_kind_keeps_the_inherited_others` |
| 3 | 矛盾门按 kind | `test_one_unconfirmed_kind_blocks_a_true_contradiction` |
| 4 | `identity_key` 段数不变 | `len(key.split("|")) == 7` 的既有断言仍绿 |
| 5 | `TRUE_CONTRADICTION` 不因新维增加 | 报告 §1 的 before/after 数字 + 逐对理由 |
| 6 | 变化可归因 | 三份报告的 §2 逐句类归因 |
| 7 | 既有用例一条不少 | 收集数 `420` |

## 明确不做（S4 边界）

- 不改矛盾级联的**关系类型**与**判定顺序**（只改「能否确认同一设置」）。
- 不把 `hyperparameters` 放进 `conditions`（P4 七维里没有超参）。
- 不改 `subject` / `_subject()` / `mergeable()` 的门槛三条。
- 不迁移存量库的旧 provenance 标记（见已知限制 19）。
- 不开 S5：四阶段到此为止，剩下的都是设计 §12 的独立立项（域名词表、架构身份、来源权威层级、§19 源码检查）。
