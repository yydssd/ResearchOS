# P5 补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补完 P5 审查与权威计划复审留下的五项未偿：`FAILURE` 事件、三组混淆矩阵、幂等/主键/CWD、断言强度、文档偏差登记。

**Architecture:** 不改级联与配对。B 组把四种失败从「静默/中止」改为「记事件 + 继续」，事件写入既有 `events` 表；C 组把 `summarise` 拆出按子集的混淆矩阵；D 组加固存储与脚本的可重复性；E 组把只查「键存在」的断言换成值断言。

**Tech Stack:** Python 3.12 / pytest / SQLAlchemy / SQLite。解释器 `D:/Anaconda/envs/reOS/python.exe`，仓库根 `D:\ResearchOS`，分支 `p5-contradiction`。

---

### Task 1: 跨 run 拒收不得中止 run

**Files:**
- Modify: `src/research_os/domain/enums.py`（`FailureType`）
- Modify: `src/research_os/orchestration/supervisor.py:361-365`
- Test: `tests/integration/test_contradiction_run.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/integration/test_contradiction_run.py`：

```python
def test_cross_run_rejection_is_logged_and_the_run_survives(session, tmp_path, monkeypatch):
    """Section 25: a rejected pair must leave a failure event, not kill the run.

    A cross-run row means the store was written outside this run. Refusing it is
    right; aborting the whole research run because of it is not - P5 relates
    claims, it does not gate the run.
    """
    from research_os.domain.enums import EventType, FailureType
    from research_os.storage.repositories import SqlContradictionRepository

    def reject(self, run_id, items):
        raise ValueError("cross_run_pair: c1 / c2")

    monkeypatch.setattr(SqlContradictionRepository, "replace_for_run", reject)

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    result = _slice(Supervisor(session), paper, tmp_path)

    failures = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.FAILURE
    ]
    assert any(event.failure_type is FailureType.CROSS_RUN_PAIR for event in failures)
    assert "cross_run_pair" in " ".join(event.message for event in failures)
    assert result["memo"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_run.py::test_cross_run_rejection_is_logged_and_the_run_survives -q`

Expected: FAIL — `AttributeError: CROSS_RUN_PAIR`（枚举不存在），或 `ValueError` 直接抛出 `run_vertical_slice`。

- [ ] **Step 3: 加枚举与捕获**

`src/research_os/domain/enums.py`，在 `FailureType` 里 `CONTRADICTION_UNRESOLVED` 之后加：

```python
    CROSS_RUN_PAIR = "CROSS_RUN_PAIR"
```

`src/research_os/orchestration/supervisor.py`，把这一行：

```python
        replaced = SqlContradictionRepository(self._session).replace_for_run(run.id, assessments)
```

替换为：

```python
        try:
            replaced = SqlContradictionRepository(self._session).replace_for_run(run.id, assessments)
        except ValueError as exc:
            # Plan §25 asks for a persisted failure event, not for the run to die.
            # Refusing a cross-run pair is correct; cascading the exception out of
            # run_vertical_slice would lose the memo over a dirty storage row.
            self._log(
                run.id,
                EventType.FAILURE,
                str(exc),
                {"run_id": run.id, "rejected": len(assessments)},
                failure_type=FailureType.CROSS_RUN_PAIR,
            )
            assessments, replaced = [], 0
```

确认文件顶部已 import `FailureType`（`grep -n "FailureType" src/research_os/orchestration/supervisor.py | head -3`）；若没有，加到 `research_os.domain.enums` 的 import 列表里。

- [ ] **Step 4: 跑测试确认通过**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_run.py -q`

Expected: PASS（4 tests）。

- [ ] **Step 5: 提交**

```bash
git add src/research_os/domain/enums.py src/research_os/orchestration/supervisor.py tests/integration/test_contradiction_run.py
git commit -m "fix(p5): a cross-run pair is logged, not fatal

Plan section 25 requires failure events to be persisted. A rejected pair was
raising out of run_vertical_slice and losing the memo over a storage row written
outside this run. Now it is recorded as CROSS_RUN_PAIR and assessment writing
continues with an empty set."
```

---

### Task 2: 单对判定异常不得中断其余对

**Files:**
- Modify: `src/research_os/research/contradiction.py`（`PairingStats`、`assess`）
- Modify: `src/research_os/orchestration/supervisor.py`（事件）
- Test: `tests/unit/test_contradiction_assessor.py`
- Test: `tests/integration/test_contradiction_run.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/unit/test_contradiction_assessor.py`：

```python
def test_one_bad_pair_does_not_stop_the_others(monkeypatch):
    """A single malformed pair must cost one judgement, not the whole run.

    The counter is the only evidence that a pair was dropped for an error rather
    than for a missing scope, so it has to be distinct from the skip counters.
    """
    import research_os.research.contradiction as module

    real = module.assess_pair
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(a, b)

    monkeypatch.setattr(module, "assess_pair", flaky)

    assessments, stats = module.HeuristicContradictionAssessor().assess(
        [_claim("UP"), _claim("LEVEL"), _claim("UP"), _claim("LEVEL")]
    )

    assert stats.failed_pairs == 1
    assert len(assessments) == 1
    assert stats.emitted_by_type == {"TRUE_CONTRADICTION": 1}
```

追加到 `tests/integration/test_contradiction_run.py`：

```python
def test_failed_pairs_are_reported_in_an_event(session, tmp_path, monkeypatch):
    import research_os.research.contradiction as module
    from research_os.domain.enums import EventType, FailureType

    def always_boom(a, b):
        raise RuntimeError("boom")

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    supervisor = Supervisor(session)
    monkeypatch.setattr(module, "assess_pair", always_boom)
    monkeypatch.setattr(
        supervisor, "_assessor", module.HeuristicContradictionAssessor()
    )

    result = _slice(supervisor, paper, tmp_path)

    failures = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.FAILURE
        and event.failure_type is FailureType.CONTRADICTION_UNRESOLVED
    ]
    assert failures, "expected a CONTRADICTION_UNRESOLVED failure event"
    assert failures[0].payload["failed_pairs"] >= 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_contradiction_assessor.py tests/integration/test_contradiction_run.py -q`

Expected: FAIL — `AttributeError: 'PairingStats' object has no attribute 'failed_pairs'`；第二个测试因异常直接抛出而 ERROR。

- [ ] **Step 3: 加计数与捕获**

`src/research_os/research/contradiction.py`，`PairingStats` 里 `skipped_same_value` 之后加：

```python
    failed_pairs: int = 0  # assess_pair raised; distinct from any scope skip
```

`HeuristicContradictionAssessor.assess` 把循环体改成：

```python
        for a, b in pairs:
            try:
                result = assess_pair(a, b)
            except Exception:  # noqa: BLE001 - one bad pair must not stop the rest
                # Swallowing silently is what plan §25 forbids; the count is
                # surfaced as a failure event by the supervisor.
                stats.failed_pairs += 1
                continue
            if result is None:
```

（其余分支不变，注意 `continue` 之后原来的 `if result is None:` 要保留，缩进对齐。）

supervisor 在 `EventType.CONTRADICTION_ASSESSED` 那次 `self._log` **之前**插入：

```python
        if stats.failed_pairs:
            self._log(
                run.id,
                EventType.FAILURE,
                f"{stats.failed_pairs} pairs could not be judged",
                {"failed_pairs": stats.failed_pairs},
                failure_type=FailureType.CONTRADICTION_UNRESOLVED,
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_contradiction_assessor.py tests/integration/test_contradiction_run.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/research_os/research/contradiction.py src/research_os/orchestration/supervisor.py tests/unit/test_contradiction_assessor.py tests/integration/test_contradiction_run.py
git commit -m "fix(p5): count a failed pair instead of losing the batch

One raising pair used to abort assess() and take every later pair with it. It is
now counted in PairingStats.failed_pairs and surfaced as a failure event, so the
drop is visible rather than silent."
```

---

### Task 3: 同值缺陷与无定位证据都要落事件

**Files:**
- Modify: `src/research_os/orchestration/supervisor.py`
- Test: `tests/unit/test_contradiction_assessor.py`（同值）
- Test: `tests/integration/test_contradiction_run.py`（无定位）

- [ ] **Step 1: 写失败测试**

追加到 `tests/integration/test_contradiction_run.py`：

```python
def test_assessed_claims_without_evidence_are_reported(session, tmp_path):
    """The memo prints 'no locatable evidence'; §6 also wants an event, so the
    gap is visible in the run's failure record and not only in prose."""
    from research_os.domain.enums import EventType, FailureType

    paper = tmp_path / "paper.md"
    paper.write_text(PAPER_BODY, encoding="utf-8")
    supervisor = Supervisor(session)
    monkeypatch_target = "research_os.orchestration.supervisor._unlocatable_claims"

    import research_os.orchestration.supervisor as sup

    original = sup._unlocatable_claims
    sup._unlocatable_claims = lambda assessments, relations: ["c_fake"]
    try:
        result = _slice(supervisor, paper, tmp_path)
    finally:
        sup._unlocatable_claims = original

    failures = [
        event
        for event in SqlEventRepository(session).list_by_run(result["run_id"])
        if event.event_type is EventType.FAILURE
        and event.failure_type is FailureType.CITATION_LOCATION_MISSING
    ]
    assert failures
    assert failures[0].payload["claim_ids"] == ["c_fake"]
```

追加到 `tests/unit/test_contradiction_assessor.py`：

```python
def test_same_value_pairs_are_reported_as_a_failure(session_or_none=None):
    """Skipped for an identical value means P4 should have merged the pair. The
    counter already existed; the event is what makes it actionable."""
    from research_os.domain.models import Claim
    from research_os.domain.enums import ClaimStatus

    def claim(direction):
        return Claim(
            text="x",
            status=ClaimStatus.SUPPORTED,
            identity_key=f"m|t|sidd|psnr|{direction}|backbone=cnn|psnr=39.18",
            conditions=["conditions_from=sentence"],
        )

    assessments, stats = HeuristicContradictionAssessor().assess([claim("UP"), claim("UP")])

    assert assessments == []
    assert stats.skipped_same_value == 1
```

（这个测试只锁计数；事件由 Task 1 的 supervisor 路径覆盖，见 Step 3 的第二个 `if`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_run.py::test_assessed_claims_without_evidence_are_reported -q`

Expected: FAIL — `AttributeError: module 'research_os.orchestration.supervisor' has no attribute '_unlocatable_claims'`。

- [ ] **Step 3: 实现函数与两处事件**

`src/research_os/orchestration/supervisor.py`，模块级（放在 `class Supervisor` 之前）加：

```python
def _unlocatable_claims(assessments, relations) -> list[str]:
    """Claims that took part in an assessment but have no SUPPORTS relation.

    Same definition the memo uses: a claim with no supporting evidence renders as
    "no locatable evidence", so the event and the prose cannot disagree.
    """
    involved = {cid for item in assessments for cid in (item.claim_a_id, item.claim_b_id)}
    supported = {
        relation.claim_id
        for relation in relations
        if relation.relation is EvidenceRelation.SUPPORTS
    }
    return sorted(cid for cid in involved if cid not in supported)
```

确认已 import `EvidenceRelation`（`grep -n "EvidenceRelation" src/research_os/orchestration/supervisor.py`）；若没有，加到 `research_os.domain.enums` 的 import。

在 Task 2 插入的 `if stats.failed_pairs:` 之后，加：

```python
        if stats.skipped_same_value:
            self._log(
                run.id,
                EventType.FAILURE,
                f"{stats.skipped_same_value} pairs share an identical value",
                {"skipped_same_value": stats.skipped_same_value},
                failure_type=FailureType.CONTRADICTION_UNRESOLVED,
            )

        unlocatable = _unlocatable_claims(assessments, relations)
        if unlocatable:
            self._log(
                run.id,
                EventType.FAILURE,
                f"{len(unlocatable)} assessed claims have no locatable evidence",
                {"claim_ids": unlocatable},
                failure_type=FailureType.CITATION_LOCATION_MISSING,
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_run.py tests/unit/test_contradiction_assessor.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/research_os/orchestration/supervisor.py tests/integration/test_contradiction_run.py tests/unit/test_contradiction_assessor.py
git commit -m "feat(p5): log identical-value skips and claims without locatable evidence

Both were already visible (a counter and a memo phrase) but neither was in the
failure record, so a run could look clean while carrying a P4 dedup defect or a
claim nobody can trace. Section 6 asks for the event as well as the rendering."
```

---

### Task 4: 三组混淆矩阵

**Files:**
- Modify: `scripts/evaluate_contradiction.py`
- Test: `tests/unit/test_evaluate_contradiction.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/unit/test_evaluate_contradiction.py`：

```python
def test_confusion_is_reported_per_subset():
    """Spec §9 #3: real, constructed and combined each need their own matrix.

    Averaging them hides the only comparison that matters - whether the rules work
    on real sentences or only on the ones written to match them.
    """
    rows = [
        {"id": "r1", "source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "SCOPE_DIFFERENCE"},
        {"id": "r2", "source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "TRUE_CONTRADICTION"},
        {"id": "c1", "source": "constructed", "expected": "COMPLEMENTARY", "actual": "COMPLEMENTARY"},
    ]

    report = summarise(rows)

    assert report["confusion"]["SCOPE_DIFFERENCE"]["SCOPE_DIFFERENCE"] == 1
    assert report["confusion_by_subset"]["real"]["SCOPE_DIFFERENCE"]["TRUE_CONTRADICTION"] == 1
    assert report["confusion_by_subset"]["constructed"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 1
    assert report["confusion_by_subset"]["real"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_evaluate_contradiction.py::test_confusion_is_reported_per_subset -q`

Expected: FAIL — `KeyError: 'confusion_by_subset'`。

- [ ] **Step 3: 抽出函数并加子集矩阵**

`scripts/evaluate_contradiction.py`，把现在的

```python
    confusion = {expected: {column: 0 for column in COLUMNS} for expected in TYPES}
    for row in rows:
        if row["expected"] is None:
            continue
        column = row["actual"] or "SKIPPED"
        confusion[row["expected"]][column] += 1
```

替换为：

```python
    confusion = _confusion(rows)
```

并在 `summarise` 之前加：

```python
def _confusion(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Expected x actual counts. SKIPPED is a real column: a pair that was never
    judged must be visible, or the matrix silently flatters the classifier."""
    table = {expected: {column: 0 for column in COLUMNS} for expected in TYPES}
    for row in rows:
        if row["expected"] is None:
            continue
        table[row["expected"]][row["actual"] or "SKIPPED"] += 1
    return table
```

`summarise` 的 return 字典里，`"confusion": confusion,` 改为：

```python
        "confusion": confusion,
        "confusion_by_subset": {
            "real": _confusion([r for r in rows if r["source"] == "real"]),
            "constructed": _confusion([r for r in rows if r["source"] == "constructed"]),
        },
```

`main()` 里把打印矩阵那段改成打印三张：

```python
    print("\nconfusion (rows = expected, cols = actual)")
    width = max(len(name) for name in TYPES) + 2
    header = "".join(f"{ALIASES[c]:>8}" for c in COLUMNS)
    for label, table in (
        ("overall", report["confusion"]),
        ("real", report["confusion_by_subset"]["real"]),
        ("constructed", report["confusion_by_subset"]["constructed"]),
    ):
        print(f"\n[{label}]")
        print(f"{'':<{width}}{header}")
        for expected, row in table.items():
            cells = "".join(f"{row[c]:>8}" for c in COLUMNS)
            print(f"{expected:<{width}}{cells}")
```

- [ ] **Step 4: 跑测试与脚本**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_evaluate_contradiction.py -q`

Expected: PASS（6 tests）。

Run: `D:/Anaconda/envs/reOS/python.exe scripts/evaluate_contradiction.py`

Expected: 三个 `[overall]` / `[real]` / `[constructed]` 小节，每节 5 行 6 列。

- [ ] **Step 5: 提交**

```bash
git add scripts/evaluate_contradiction.py tests/unit/test_evaluate_contradiction.py
git commit -m "feat(eval): per-subset confusion matrices

Spec section 9 item 3 wants real, constructed and combined reported separately.
One combined matrix lets a rule that only works on hand-written sentences look
identical to one that works on real ones."
```

---

### Task 5: 幂等要断言内容，不只是条数

**Files:**
- Modify: `tests/integration/test_contradiction_storage.py`

- [ ] **Step 1: 改写既有测试**

把 `test_replace_for_run_is_idempotent` 整个函数替换为：

```python
def test_replace_for_run_is_idempotent(session):
    """Rerunning must reproduce the same rows, not just the same count.

    Counting alone passes even if the second run writes a different relationship
    or explanation, which is exactly the kind of drift a rerun is supposed to
    prove absent.
    """
    _seed(session, "run_1", ("c1", "c2"))
    repo = SqlContradictionRepository(session)
    items = [_assessment("c1", "c2")]

    repo.replace_for_run("run_1", items)
    session.commit()
    first = [
        (a.claim_a_id, a.claim_b_id, a.relationship.value, a.explanation, a.confidence_label.value)
        for a in repo.list_by_run("run_1")
    ]

    deleted = repo.replace_for_run("run_1", items)
    session.commit()
    second = [
        (a.claim_a_id, a.claim_b_id, a.relationship.value, a.explanation, a.confidence_label.value)
        for a in repo.list_by_run("run_1")
    ]

    assert deleted == 1
    assert len(second) == 1
    assert second == first
```

- [ ] **Step 2: 跑测试**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_storage.py -q`

Expected: PASS（实现已经是先删后写，这一步只加固断言）。若 FAIL，说明 `create()` 或 `_to_domain` 有非确定性字段，先修它们。

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_contradiction_storage.py
git commit -m "test(storage): assert rerun reproduces content, not just row count

Count equality passed for any pair of assessments with the same endpoints. The
test now compares relationship, explanation and confidence across the rerun."
```

---

### Task 6: 主张对的主键不再截断

**Files:**
- Modify: `src/research_os/storage/repositories.py`（`create`）
- Test: `tests/integration/test_contradiction_storage.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/integration/test_contradiction_storage.py`：

```python
def test_two_distinct_pairs_sharing_a_prefix_are_both_stored(session):
    """The row id used to be con_<a[:10]>_<b[:10]>. Two genuinely different pairs
    whose claim ids share ten characters collided on the primary key and the
    second was rejected as a duplicate - a false rejection no unique index on the
    columns can repair, because the collision happens before it is consulted."""
    _seed(session, "run_1", ("c_AAAAAAAA11", "c_BBBBBBBB11", "c_AAAAAAAA22", "c_BBBBBBBB22"))
    repo = SqlContradictionRepository(session)

    repo.create(_assessment("c_AAAAAAAA11", "c_BBBBBBBB11"))
    session.commit()
    repo.create(_assessment("c_AAAAAAAA22", "c_BBBBBBBB22"))
    session.commit()

    stored = {(a.claim_a_id, a.claim_b_id) for a in repo.list_by_run("run_1")}
    assert stored == {("c_AAAAAAAA11", "c_BBBBBBBB11"), ("c_AAAAAAAA22", "c_BBBBBBBB22")}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_storage.py::test_two_distinct_pairs_sharing_a_prefix_are_both_stored -q`

Expected: FAIL — `IntegrityError: UNIQUE constraint failed: contradiction_assessments.id`。

- [ ] **Step 3: 改用哈希主键**

`src/research_os/storage/repositories.py` 顶部 import 区加 `import hashlib`。

在 `class SqlContradictionRepository` 之前加：

```python
def _assessment_id(claim_a_id: str, claim_b_id: str) -> str:
    """Full-fidelity id for the pair.

    Truncating each id to ten characters made two different pairs collide on the
    primary key, and the second was rejected before the column-level unique index
    could tell them apart.
    """
    digest = hashlib.sha1(f"{claim_a_id}|{claim_b_id}".encode("utf-8")).hexdigest()
    return f"con_{digest[:16]}"
```

把 `create` 里的 `id=f"con_{a.claim_a_id[:10]}_{a.claim_b_id[:10]}",` 改为：

```python
                id=_assessment_id(a.claim_a_id, a.claim_b_id),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_storage.py -q`

Expected: PASS（9 tests）。

- [ ] **Step 5: 提交**

```bash
git add src/research_os/storage/repositories.py tests/integration/test_contradiction_storage.py
git commit -m "fix(storage): derive the assessment id from a digest, not a prefix

con_<a[:10]>_<b[:10]> made two distinct pairs collide on the primary key and the
second was silently rejected as a duplicate. The column-level unique index never
saw it, because the collision happened first. Old rows keep their ids: the field
is a key, not part of any identity or trace."
```

---

### Task 7: 评估脚本与测试不再依赖当前工作目录

**Files:**
- Modify: `scripts/evaluate_contradiction.py`（`FIXTURE`）
- Modify: `tests/unit/test_evaluate_contradiction.py`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_evaluate_contradiction.py` 顶部把两个 `from scripts.evaluate_contradiction import ...` 之后追加：

```python
def test_the_fixture_path_does_not_depend_on_the_working_directory(monkeypatch, tmp_path):
    """239 green tests used to depend on being run from the repository root.

    The script resolved `tests/fixtures/...` relatively, so running the same file
    from another directory failed with FileNotFoundError while looking like a code
    bug.
    """
    from scripts.evaluate_contradiction import FIXTURE

    assert FIXTURE.is_absolute()
    assert FIXTURE.exists()

    monkeypatch.chdir(tmp_path)
    assert FIXTURE.exists()
    assert evaluate(FIXTURE)
```

（`evaluate` 需已在文件顶部 import；现有 import 是 `from scripts.evaluate_contradiction import summarise`，改成同时导入 `evaluate` 与 `FIXTURE`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_evaluate_contradiction.py::test_the_fixture_path_does_not_depend_on_the_working_directory -q`

Expected: FAIL — `assert False`（`FIXTURE.is_absolute()` 为假）。

- [ ] **Step 3: 改为基于 `__file__`**

`scripts/evaluate_contradiction.py`：

```python
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "contradiction" / "pairs.json"
```

`tests/unit/test_evaluate_contradiction.py`：把所有 `Path("tests/fixtures/contradiction/pairs.json")` 换成 `FIXTURE`（从 `scripts.evaluate_contradiction` 导入）。

- [ ] **Step 4: 跑测试并从别处验证**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_evaluate_contradiction.py -q`

Expected: PASS（7 tests）。

Run（在 `tests/` 目录下执行，验证不依赖 CWD）：

```bash
cd tests && PYTHONPATH=.. D:/Anaconda/envs/reOS/python.exe -m pytest unit/test_evaluate_contradiction.py -q
```

Expected: PASS，无 `FileNotFoundError`。

- [ ] **Step 5: 提交**

```bash
git add scripts/evaluate_contradiction.py tests/unit/test_evaluate_contradiction.py
git commit -m "fix(eval): resolve the fixture path from the module, not the cwd

The evaluation script and its tests both used a relative path, so the suite was
only green when run from the repository root. Now the path is absolute and a test
chdirs away to prove it."
```

---

### Task 8: 把四处「键存在」断言换成值断言

**Files:**
- Modify: `tests/integration/test_contradiction_run.py`
- Modify: `tests/integration/test_contradiction_memo.py`
- Modify: `tests/unit/test_evaluate_contradiction.py`

- [ ] **Step 1: 逐处改写**

`tests/integration/test_contradiction_run.py`，`test_assessment_records_an_event_with_skip_accounting` 里把

```python
    for field in ("assessments", "total_before_cap", "evaluated", "coverage",
                  "skipped_missing_dataset", "skipped_missing_metric",
                  "skipped_self_prefilter", "skipped_cap", "skipped_same_value",
                  "by_type", "replaced"):
        assert field in payload, field
```

替换为：

```python
    # Values, not key names: filling every field with 0 would have passed.
    assert payload["assessments"] == sum(payload["by_type"].values())
    assert payload["evaluated"] == payload["total_before_cap"] - payload["skipped_cap"]
    assert 0.0 <= payload["coverage"] <= 1.0
    assert payload["assessments"] >= 1, "the fixture pair is a true contradiction"
```

`tests/integration/test_contradiction_memo.py`，`test_inspect_claim_exposes_partners_and_provenance` 里把

```python
    assert "contradictions" in detail
    assert detail["contradictions"], "the paired claim should appear as a partner"
    assert "relationship" in detail["contradictions"][0]
```

替换为：

```python
    partners = detail["contradictions"]
    assert len(partners) == 1
    assert partners[0]["relationship"] == "TRUE_CONTRADICTION"
    assert partners[0]["claim_id"] != claim.id
    assert partners[0]["claim_id"] in {
        a.claim_a_id for a in SqlContradictionRepository(session).list_by_run(run_id)
    } | {a.claim_b_id for a in SqlContradictionRepository(session).list_by_run(run_id)}
```

（该文件需 import `SqlContradictionRepository`：`from research_os.storage.repositories import SqlClaimRepository, SqlContradictionRepository`。）

同文件 `test_memo_lists_the_assessment_with_its_reason` 里把

```python
    assert "Assessed" in memo and "coverage" in memo.lower()
    assert "same scope, opposite direction" in memo or "SCOPE_DIFFERENCE" in memo
    assert "chars" in memo  # evidence location travels with the claim text
```

替换为：

```python
    assert "Assessed 1 of 1 candidate pairs (coverage 100%)" in memo
    assert "same scope, opposite direction: LEVEL vs UP" in memo
    assert "## True contradictions (1)" in memo
    assert "chars " in memo
```

`tests/unit/test_evaluate_contradiction.py`，`test_confusion_matrix_is_square_over_the_five_types` 里补：

```python
    assert report["confusion"]["COMPLEMENTARY"]["COMPLEMENTARY"] == 1
    assert sum(report["confusion"]["COMPLEMENTARY"].values()) == 1
```

- [ ] **Step 2: 跑测试确认通过**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/integration/test_contradiction_run.py tests/integration/test_contradiction_memo.py tests/unit/test_evaluate_contradiction.py -q`

Expected: PASS。若有断言不符，**先判断是实现问题还是新断言写错**：`payload["evaluated"] == total_before_cap - skipped_cap` 若失败，说明 `PairingStats` 的算术口径有问题，要修实现而不是放宽断言。

- [ ] **Step 3: 反向验证（关键）**

临时把 `scripts/evaluate_contradiction.py` 的 `_confusion` 里 `table[row["expected"]][row["actual"] or "SKIPPED"] += 1` 注释掉，跑：

```bash
D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_evaluate_contradiction.py -q
```

Expected: FAIL（单元格计数为 0）。确认后**恢复该行**。

- [ ] **Step 4: 提交**

```bash
git add tests/integration/test_contradiction_run.py tests/integration/test_contradiction_memo.py tests/unit/test_evaluate_contradiction.py
git commit -m "test(p5): assert values where the tests only asserted presence

Four assertions checked that a key existed rather than what it held: an event
payload of all zeroes, any partner at all, any occurrence of the word 'coverage',
and a confusion-matrix key set built from a constant. Each now pins the value,
and the matrix one was verified to fail when the accumulation is removed."
```

---

### Task 9: 补三个覆盖缺口

**Files:**
- Test: `tests/unit/test_contradiction_assessor.py`（缺 metric、截断）
- Test: `tests/unit/test_contradiction_cascade.py`（条件不等 + 同向）

- [ ] **Step 1: 写测试**

追加到 `tests/unit/test_contradiction_assessor.py`：

```python
def test_pairs_missing_only_a_metric_are_counted_as_such():
    """The missing-dataset branch used to catch these too, so the metric counter
    was never exercised and could have been wired to the wrong branch."""
    from research_os.domain.models import Claim
    from research_os.domain.enums import ClaimStatus

    def claim(metric):
        return Claim(
            text="x",
            status=ClaimStatus.SUPPORTED,
            identity_key=f"m|t|sidd|{metric}||backbone=cnn|",
            conditions=["conditions_from=sentence"],
        )

    assessments, stats = HeuristicContradictionAssessor().assess([claim(""), claim("psnr")])

    assert assessments == []
    assert stats.skipped_missing_metric == 1
    assert stats.skipped_missing_dataset == 0


def test_truncation_is_counted_and_shrinks_the_coverage_denominator(monkeypatch):
    """MAX_PAIRS is 50 000 in production, so `skipped_cap` was untested and could
    have stayed at zero forever."""
    import research_os.research.contradiction as module
    from research_os.domain.models import Claim
    from research_os.domain.enums import ClaimStatus

    monkeypatch.setattr(module, "MAX_PAIRS", 2)

    def claim(direction, bucket):
        return Claim(
            text="x",
            status=ClaimStatus.SUPPORTED,
            identity_key=f"m|t|sidd|psnr|{direction}|backbone=cnn|{bucket}",
            conditions=["conditions_from=sentence"],
        )

    claims = [
        claim("UP", "psnr=1"),
        claim("LEVEL", "psnr=1"),
        claim("DOWN", "psnr=1"),
    ]
    _, stats = module.HeuristicContradictionAssessor().assess(claims)

    assert stats.total_before_cap == 3
    assert stats.skipped_cap == 1
    assert stats.evaluated == 2
    assert stats.coverage == pytest.approx(2 / 3)
```

（`pytest` 需已 import。）

追加到 `tests/unit/test_contradiction_cascade.py`：

```python
def test_different_conditions_with_the_same_direction_are_complementary():
    """Row 3 has two arms: opposite directions give SCOPE_DIFFERENCE (covered),
    same direction gives COMPLEMENTARY (not covered). Without this the same-direction
    arm could return anything."""
    a = _claim(direction="UP", conditions="backbone=transformer", conditions_from="sentence")
    b = _claim(direction="UP", conditions="backbone=cnn", conditions_from="sentence", bucket="psnr=38.5")

    assert _relationship(a, b) == ContradictionType.COMPLEMENTARY
```

- [ ] **Step 2: 跑测试**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest tests/unit/test_contradiction_assessor.py tests/unit/test_contradiction_cascade.py -q`

Expected: PASS。若 `test_truncation...` 失败，检查 `pair_candidates` 是否在截断后仍把 `total_before_cap` 设为截断前的数量（这是既有正确行为）。

- [ ] **Step 3: 提交**

```bash
git add tests/unit/test_contradiction_assessor.py tests/unit/test_contradiction_cascade.py
git commit -m "test(p5): cover the metric-only skip, the pair cap and row-3 same direction

Three branches had no test: skipped_missing_metric, skipped_cap (unreachable
without lowering MAX_PAIRS), and the COMPLEMENTARY arm of row 3."
```

---

### Task 10: 文档与偏差登记

**Files:**
- Modify: `architect.md`（ADR-031/032、维护记录、计数）
- Modify: `docs/superpowers/specs/2026-11-13-p5-contradiction-design.md`（§11 偏差）
- Modify: `docs/evaluation/2026-11-13-p5-contradiction.md`（事件与矩阵）
- Modify: `README.md`（测试数）

- [ ] **Step 1: 补两条 ADR**

`architect.md` 的 ADR 表末尾（ADR-030 之后）加：

```markdown
| ADR-031 | P5 的矛盾判定用**确定性级联**，不走 LLM，尽管计划 §2.5 把 contradiction judgment 列为 LLM 适用场景。理由：判定输入是已落库的七维 identity，输出是五选一的关系，全部可枚举；确定性实现让同一输入必然得出同一结论，也让"这条为什么被判成矛盾"能在代码里逐行指出。换 LLM 的入口留在 `ContradictionAssessor` 协议上，P8 需要时替换，supervisor 不用改 | ACTIVE |
| ADR-032 | 评估工具放 `scripts/`（`holdout_claim_quality.py`、`holdout_contradiction_quality.py`、`evaluate_contradiction.py`），不建计划 §6 里的 `evaluation/` 包。理由：三者都是离线一次性分析，不被 runtime 引用；建包会把它们变成公开 API，需要版本与稳定性承诺，而当前没有第二个消费者 | ACTIVE |
```

- [ ] **Step 2: 补 spec 偏差行**

`docs/superpowers/specs/2026-11-13-p5-contradiction-design.md` 的 §11 偏差表末尾（第 15 行之后）加：

```markdown
| 16 | §9 #3 混淆矩阵 | 输出 **5 行 × 6 列**（含 `SKIPPED`），不是 5×5；并按 overall / real / constructed 出三张 | `SKIPPED` 必须有落脚处，删掉它会让"该判未判"无处显示；三张分开是因为合并会把"只在构造样本上成立"和"在真实句子上也成立"平均掉 |
| 17 | §6/§7 `FAILURE` 事件 | 补齐：跨 run 拒收 → `CROSS_RUN_PAIR` 且 run 继续；单对异常 → `failed_pairs` 计数 + `CONTRADICTION_UNRESOLVED`；同值缺陷 → 事件；无定位证据 → `CITATION_LOCATION_MISSING` | 计划 §25 要求持久化失败事件；此前 P5 路径 0 条，且跨 run 会中止整个 run |
```

- [ ] **Step 3: 补评估报告一段**

`docs/evaluation/2026-11-13-p5-contradiction.md` 末尾追加：

```markdown
## Failure events (2026-11-14)

P5 now persists four kinds of failure instead of swallowing them (plan §25):
`CROSS_RUN_PAIR` when storage holds a pair spanning two runs (the run continues),
`CONTRADICTION_UNRESOLVED` for a pair that raised and for an identical-value pair
that P4 should have merged, and `CITATION_LOCATION_MISSING` for an assessed claim
with no supporting evidence. The confusion matrix is printed three times - overall,
real, constructed - because a single one lets rules that only work on hand-written
sentences look identical to rules that work on real ones.
```

- [ ] **Step 4: 更新计数**

`README.md` 与 `architect.md` 里 `pytest` 的数字改为本任务 Step 5 实跑得到的值。

- [ ] **Step 5: 全量验证并提交**

Run: `D:/Anaconda/envs/reOS/python.exe -m pytest`

Expected: 全绿，记录通过数。

```bash
git add README.md architect.md docs/superpowers/specs/2026-11-13-p5-contradiction-design.md docs/evaluation/2026-11-13-p5-contradiction.md
git commit -m "docs(p5): register the deterministic-cascade and evaluation-location deviations

Two places where the implementation diverged from the authoritative plan and had
never been written down: contradiction judgement is deterministic although plan
section 2.5 lists it as an LLM task, and the evaluators live in scripts/ rather
than an evaluation/ package. Both now have ADRs, and the spec deviation table
records the 5x6 matrix and the failure events."
```

---

## Self-Review

**Spec coverage**

| spec 节 | 任务 |
|---|---|
| §2 B 跨 run / 单对异常 / 同值 / 无定位 | Task 1 / 2 / 3 / 3 |
| §3 C 三组矩阵 | Task 4 |
| §4.1 幂等内容 | Task 5 |
| §4.2 主键去截断 | Task 6 |
| §4.3 CWD | Task 7 |
| §5 E 断言强度 + 三缺口 | Task 8 / 9 |
| §7 偏差登记 | Task 10 |

**占位符扫描**：无 TBD / "add error handling" / "similar to Task N"。每个代码步骤都给了完整代码。

**类型一致性**：`failed_pairs`（Task 2 定义，Task 2 消费）、`_unlocatable_claims`（Task 3 定义与消费）、`_confusion`（Task 4 定义与消费，Task 8 反向验证引用）、`FIXTURE`（Task 7 改为绝对路径，同任务的两处消费一起改）均一致。

**已知风险**

- Task 2 的 integration 测试用 `monkeypatch.setattr(supervisor, "_assessor", ...)`：`_assessor` 是实例属性，`monkeypatch.setattr` 对实例设置会在测试结束时自动还原。若不work，改为构造函数注入 `Supervisor(session, contradiction_assessor=...)`。
- Task 8 的 `payload["evaluated"] == total_before_cap - skipped_cap` 依赖 `PairingStats` 的算术闭合；该闭合已在仓储审查中实测成立（15 = 4 + 11），若新测试失败应先核查 `pair_candidates` 而不是改断言。
