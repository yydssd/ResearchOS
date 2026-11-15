# S4：`conditions` 两个新维度 + 按 kind 的 provenance 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 P4 的七维里最后两维（**model scale**、**evaluation protocol**）真正进入 `conditions`，并把 provenance 从「整条一个 tier」改成**按 kind 各记各的**——否则新增两个高频模式后，一句 `ours achieves 70% success rate` 会把继承来的 `training=` / `backbone=` 整条覆盖掉，同时把 tier 升成 `sentence`，从而允许一个没有依据的 `TRUE_CONTRADICTION`。

**Architecture:** `conditions` 的内部表示从 `tuple[str, ...]` 升级为 **`dict[kind] -> value` + `dict[kind] -> tier`**，`identity_key` 仍是 7 段、第 6 段仍是排序后的 `kind=value;...`（键不变、段数不变、值域扩两类）。按 kind 补齐继承、按 kind 判 tier；矛盾判定只对**两侧都有的 kind**要求 tier 已确认，缺任一即 `INSUFFICIENT_EVIDENCE`（HD-014 的「继承只可否证，不可证实」原样保留）。

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
- **不改**矛盾级联的**关系类型**与**判定顺序**（设计 §11）：只改「能不能确认同一设置」这一步。
- 存量数据库里旧的 `conditions_from=<tier>` 标记**不迁移**：它们是度量产物，不是生产数据；读不到就按「未确认」处理（安全方向），并登记为已知限制。

---

## 文件结构

| 文件 | 责任 | 改动 |
|---|---|---|
| `src/research_os/research/conditions.py` | 条件抽取 | 新增 `extract_condition_map()`（kind→value 的原始形态）+ `scale=` / `protocol=` 两类；`extract_conditions()` 改为它的薄包装（保持 tuple 返回） |
| `src/research_os/research/scope.py` | 块级继承 | `BlockScope` 从「一个 tuple + 一个 tier」改为「dict + 每 kind 的 tier」；继承按 kind 补齐 |
| `src/research_os/research/claims.py` | 身份 | `ClaimIdentity` 增 `condition_tiers`（provenance，不进 key）；`_conditions()` 改为按 kind 合并 |
| `src/research_os/research/claim_builder.py` | 落库形态 | 每条 claim 的 flags 从 `conditions_from=<tier>` 改为 `condition_tier=<kind>:<tier>` |
| `src/research_os/research/contradiction.py` | 矛盾判定 | `_conditions_from()` → `_condition_tiers()`；TRUE_CONTRADICTION 的门改为「两侧共有 kind 的 tier 都确认」 |
| `scripts/holdout_contradiction_quality.py`、`scripts/evaluate_contradiction.py` | 离线分析 | 跟随 flag 形态 |
| `docs/evaluation/2026-11-15-s4-*.md` | 报告 | 三份 before/after |

---

### Task 1: `conditions.py` —— 原始形态 + 两个新 kind

**Files:**
- Modify: `src/research_os/research/conditions.py`
- Test: `tests/unit/test_claim_conditions.py`（追加 4 条）

- [ ] **Step 1: 先把测试辅助函数改成按 kind**

`tests/unit/test_contradiction_cascade.py` 的 `_claim()` 目前只收 `conditions_from` 这一个 tier，改为：

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

然后把该文件里所有 `conditions_from="sentence"` 的调用改成
`conditions="backbone=transformer", tiers={"backbone": "sentence"}`（`heading` / `section-first-mention`
同理）；把断言 `conditions_from` 文字的地方删掉——那个 flag 已不存在。

- [ ] **Step 2: 写会失败的测试**

在 `tests/unit/test_claim_conditions.py` 末尾追加：

```python
def test_condition_map_is_the_primitive_and_the_tuple_is_derived():
    """`extract_conditions` keeps its tuple contract for every existing caller;
    the map is what per-kind provenance needs (S4)."""
    from research_os.research.conditions import extract_condition_map

    assert extract_condition_map("A Transformer trained from scratch.") == {
        "backbone": "transformer",
        "training": "from-scratch",
    }
    # Sorted by kind: `backbone` before `training`, deterministically.
    assert extract_conditions("A Transformer trained from scratch.") == (
        "backbone=transformer",
        "training=from-scratch",
    )


def test_model_scale_is_a_condition():
    """P4's seven dimensions include model scale (plan §16); it had no home."""
    assert extract_condition_map("We train a 7B model.") == {"scale": "7b"}
    assert extract_condition_map("Experiments run on 8×A100 GPUs.") == {"scale": "8xa100"}


def test_evaluation_protocol_is_a_condition():
    assert extract_condition_map("We evaluate zero-shot.") == {"protocol": "zero-shot"}
    assert extract_condition_map("Reported under the 5-shot setting.") == {"protocol": "5-shot"}


def test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale():
    """Same boundary as S2's MethodSetup (design §6.3): "success rate" is a metric
    and a dB value is a unit; reading either as a condition would let two claims
    look like they share a setup."""
    assert extract_condition_map("It improves PSNR by 0.42 dB.") == {}
    assert extract_condition_map("It reaches a 70% success rate.") == {}
```

- [ ] **Step 2: 运行，确认失败**

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

预期：11 passed（原 7 + 4）。

- [ ] **Step 5: 全量（关键：这一步不该改主张数）**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  -q --basetemp=.pytest_tmp_s4_t1_all
```

预期：`412 passed, 2 skipped`。**若有 claim 数量/identity 相关用例红，停下**：新 kind 会改变 `identity_key` 第 6 段，这正是 Task 6 要独占度量周期的地方；本任务只允许「包含 scale/protocol 句子的夹具用例」变化，逐条核对这些用例，并在 Task 6 的报告里登记。

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
- Test: `tests/unit/test_scope.py`（改 2 条、追加 1 条）

- [ ] **Step 1: 改测试**

`tests/unit/test_scope.py` 里凡是断言 `scope.conditions == (...)` 的地方，改成断言 map 与 tiers。追加：

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
        "Our method reaches 70% with 5-shot on SIDD.", "sv_1", scope=scope, quantitative=[]
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
        "The Transformer backbone improves PSNR on SIDD.", "sv_1", scope=scope, quantitative=[]
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

预期：全绿。若 `test_claim_identity.py` 有断言 `identity.conditions_from`，改成 `condition_tiers`（该字段已不存在，属本阶段允许的接口变更）。

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

- [ ] **Step 1: 改测试**

`test_claim_merge.py` 里断言 `conditions_from=` 的那条改成：

```python
def test_conditions_provenance_is_recorded_per_kind():
    """One flag per kind, `condition_tier=<kind>:<tier>`. A single flag could not
    say "the backbone was inherited but the protocol was stated"."""
    ...
    tagged = [c for c in claims if any(p.startswith("condition_tier=") for p in c.conditions)]
    assert tagged
    assert all(
        p.split("=", 1)[1].count(":") == 1
        for c in tagged for p in c.conditions if p.startswith("condition_tier=")
    )
```

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
- Test: `tests/unit/test_contradiction_cascade.py`（改 1 条、追加 2 条）

- [ ] **Step 1: 写会失败的测试**

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


def test_every_shared_kind_confirmed_still_reaches_a_true_contradiction():
    a = _claim(direction="UP", conditions="backbone=transformer", tiers={"backbone": "sentence"})
    b = _claim(direction="DOWN", conditions="backbone=transformer", tiers={"backbone": "heading"})

    result = assess_pair(a, b)

    assert result.relationship is ContradictionType.TRUE_CONTRADICTION
```

（`_claim()` 在 Step 1 已改成收 `tiers`；`identity_key` 第 6 段带 `kind=value`，`conditions` 列表带 `condition_tier=<kind>:<tier>`。）

- [ ] **Step 3: 运行，确认失败**

预期：`assert ContradictionType.INSUFFICIENT_EVIDENCE is ContradictionType.TRUE_CONTRADICTION`（旧实现只看一个 tier）。

- [ ] **Step 4: 实现**

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

- [ ] **Step 5: 运行 + 全量**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_contradiction_cascade.py -q --basetemp=.pytest_tmp_s4_t5_green
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s4_t5_all
```

预期：`418 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/contradiction.py tests/unit/test_contradiction_cascade.py
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

- [ ] **Step 1: 脚本跟随**

两处读 `conditions_from=` 的地方改为读 `condition_tier=`（多值，按 `、` 连接后原样带出）；这两处只是展示，不改判据。

- [ ] **Step 2: 重跑三条度量（before 一列不删不改）**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" scripts/holdout_claim_quality.py --papers 20 \
  > .s4_claim_after.txt 2>&1; tail -20 .s4_claim_after.txt
"D:/Anaconda/envs/reOS/python.exe" scripts/holdout_contradiction_quality.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt \
  > .s4_contra_after.txt 2>&1; tail -20 .s4_contra_after.txt
"D:/Anaconda/envs/reOS/python.exe" scripts/method_acquisition_audit.py \
  --labels tests/fixtures/method_acquisition/labels.json > .s4_method_after.txt 2>&1; tail -20 .s4_method_after.txt
```

每份都要记：主张总数、`identity_key` 唯一数、合并组数、`TRUE_CONTRADICTION` 数、L1–L4 四格。

- [ ] **Step 3: 三份报告**

每份都用同一结构（before 必须来自既有报告，**不许重算覆盖**）：

```markdown
# S4 实测：<指标>（2026-11-15）

> before 来源：`docs/evaluation/<旧报告>.md`（原数字未改）
> after 命令：`<上面的命令>`

## 1. before / after

| 指标 | before | after | 差值 | 解释 |
|---|---|---|---|---|
| … | … | … | … | … |

## 2. 变化归因（设计 §8.4 要求）

S4 同时做了两件方向相反的事，**必须分开归因**：

1. 新增 `scale=` / `protocol=` → 命中句的 `identity_key` 变化 → 部分合并拆开 → 主张数**上升**。
2. provenance 改为按 kind → 此前被整条覆盖的 `training=` / `backbone=` 回到 key 里 → 部分句子的 key 变化 → 主张数**再变**（方向不定）。

逐条列出：哪些新增主张来自 ①、哪些来自 ②、哪些两者都有。**只报总数视为未完成。**

## 3. 已知未解决
```

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
| 1 | 两维真的改变合并结果 | 仅在这两维不同的两句 → `may_merge() == False`（「字段有值」不算通过） |
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
