# S1：`protocol` → `unit` 语义拆分 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `QuantitativeEvidence.protocol` 里被误用的「单位」（`dB`/`percent`）拆到新字段 `unit`，让 `protocol` 回到计划 §15 赋予它的语义（评测协议），并且**不改变任何渲染输出、不改变 `value_bucket`、不损坏既有数据库**。

**Architecture:** 纯字段拆分，五个关注面必须同时对齐：领域模型、表结构、仓储映射、写入点（`quantitative.py`）、读取点（`claims.py` 的 `value_bucket`、`memo.py` 的三处渲染/导出）。迁移用 `database.py` 既有的幂等加列机制（ADR-011），但回填语句**只在列刚被 `ALTER` 出来时执行一次**——无条件执行会在第二次 `init_db()` 把 `unit` 写成 NULL。

**Tech Stack:** Python 3.12 / Pydantic v2 / SQLAlchemy 2 / SQLite / pytest。解释器 `D:/Anaconda/envs/reOS/python.exe`。

**设计依据：** `docs/superpowers/specs/2026-11-15-method-acquisition-design.md` §5（S1）。
**回归基线：** `328 collected / 326 passed / 2 skipped`。本计划只允许新增用例，不允许既有用例消失。

---

## 文件结构

| 文件 | 责任 | 本计划改动 |
|---|---|---|
| `src/research_os/domain/models.py` | 领域模型 | `QuantitativeEvidence` 加 `unit` 字段 |
| `src/research_os/storage/tables.py` | 表结构 | `QuantitativeEvidenceRow` 加 `unit` 列 |
| `src/research_os/storage/database.py` | 建表与幂等迁移 | `_ADDED_COLUMNS` 登记 `unit`；新增 `_ONE_TIME_BACKFILLS` |
| `src/research_os/storage/repositories.py` | 双向映射 | `create_many` / `_to_domain` 加 `unit` |
| `src/research_os/research/quantitative.py` | 写入点 | `protocol=` → `unit=`（两处） |
| `src/research_os/research/claims.py` | `value_bucket` 读取点 | `row.protocol` → `row.unit` |
| `src/research_os/reporting/memo.py` | 渲染与导出 | 三处 `fact.protocol` → `fact.unit`；`inspect_claim` 键改名 |
| `architect.md` | ADR | 新增 ADR-033 |

---

### Task 1: 加 `unit` 字段与列（不改变任何行为）

**Files:**
- Modify: `src/research_os/domain/models.py:154`
- Modify: `src/research_os/storage/tables.py:111`
- Modify: `src/research_os/storage/database.py:59-63`
- Modify: `src/research_os/storage/repositories.py:378-412`
- Test: `tests/unit/test_repositories.py`（追加）

- [ ] **Step 1: 写会失败的测试**

`tests/unit/test_repositories.py` 需要补两个 import。现有的
`from research_os.storage.repositories import (...)` 块里加一行：

```python
    SqlQuantitativeEvidenceRepository,
```

`from research_os.domain.models import (...)` 块里加一行：

```python
    QuantitativeEvidence,
```

然后在文件末尾追加：
```python
def test_quantitative_evidence_keeps_unit_apart_from_protocol(db):
    """plan §15 gives `protocol` to the evaluation protocol. The unit ("dB") is a
    different fact and used to be stored there; a row that carries both must come
    back with both, unchanged."""
    with session_scope() as s:
        work = ResearchWork(canonical_title="W")
        SqlWorkRepository(s).create(work)
        sv = SourceVersion(work_id=work.id, source_type=SourceType.PDF, title="W.pdf", local_path="x.pdf")
        SqlSourceVersionRepository(s).create(sv)
        ev = Evidence(source_version_id=sv.id, text="PSNR 39.18 dB on SIDD.")
        SqlEvidenceRepository(s).create(ev)
        SqlQuantitativeEvidenceRepository(s).create_many(
            [
                QuantitativeEvidence(
                    evidence_id=ev.id, seq=0, dataset="SIDD", metric="PSNR",
                    value=39.18, unit="dB", protocol="zero-shot",
                )
            ]
        )
    with session_scope() as s:
        rows = SqlQuantitativeEvidenceRepository(s).list_all()
        assert len(rows) == 1
        assert rows[0].unit == "dB"
        assert rows[0].protocol == "zero-shot"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_repositories.py::test_quantitative_evidence_keeps_unit_apart_from_protocol -v
```

预期：`FAILED`，`TypeError: QuantitativeEvidence.__init__() got an unexpected keyword argument 'unit'`（Pydantic 会报 `unexpected keyword argument 'unit'`）。

- [ ] **Step 3: 加字段与列**

`src/research_os/domain/models.py`，在 `protocol: str | None = None` **之后**加：

```python
    # The unit attached to this value ("dB"/"percent"). It lives apart from
    # `protocol` because plan §15 gives that slot to the evaluation protocol
    # ("zero-shot"), and a field named protocol holding "dB" made every delta
    # bucket read `dB:0.44` while pretending to be a protocol.
    unit: str | None = None
```

`src/research_os/storage/tables.py`，在 `protocol` 列之后加：

```python
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

`src/research_os/storage/database.py` 的 `_ADDED_COLUMNS` 改为：

```python
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "source_versions": {"source_tier": "VARCHAR(32)"},
    "quantitative_evidence": {"delta": "FLOAT", "unit": "VARCHAR(32)"},
    "claims": {"identity_key": "VARCHAR(256)"},
}
```

`src/research_os/storage/repositories.py` 的 `create_many` 里，在 `protocol=fact.protocol,` 之后加一行：

```python
                    unit=fact.unit,
```

`_to_domain` 里，在 `protocol=row.protocol,` 之后加一行：

```python
            unit=row.unit,
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_repositories.py -v
```

预期：全绿，含新用例。

- [ ] **Step 5: 跑全量，确认没有回归**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest -q --basetemp=.pytest_tmp_s1_t1
```

预期：`326 passed, 2 skipped` → 现在应为 `327 passed, 2 skipped`（多 1 条新用例）。若有既有用例变红，**停下**：本步骤不允许任何行为变化。

- [ ] **Step 6: 提交**

```bash
git add src/research_os/domain/models.py src/research_os/storage/tables.py \
        src/research_os/storage/database.py src/research_os/storage/repositories.py \
        tests/unit/test_repositories.py
git commit -m "feat(quant): add a unit field beside protocol

Plan §15 gives QuantitativeEvidence.protocol to the evaluation protocol, but
the implementation stored the unit (dB/percent) there. Adding the field first,
with no writer or reader change, keeps the behaviour identical until the flip."
```

---

### Task 2: 按数据幂等的回填

**Files:**
- Modify: `src/research_os/storage/database.py:56-103`
- Test: `tests/unit/test_database.py`（追加）

- [ ] **Step 1: 写会失败的三个测试**

`tests/unit/test_database.py` 顶部已有 `from sqlalchemy import inspect, text` 与
`from research_os.storage.database import session_scope`，需要补：

```python
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from research_os.storage import tables  # noqa: F401  (registers models on Base)
from research_os.storage.database import Base, init_db
```

追加：

```python
@pytest.fixture()
def file_database():
    """`init_db(url=...)` replaces the global engine and session factory for the
    rest of the process. Without restoring them, a later test that does not take
    the `db` fixture would silently talk to this test's deleted temp file."""
    yield
    init_db(url="sqlite:///:memory:")


def _old_database_without_unit(url: str) -> None:
    """A pre-S1 database: today's schema minus the unit column.

    Derived from the model instead of hand-written DDL, so "old database" stays
    equal to "current schema minus unit" forever. A hand-written table drifts the
    moment the model gains a column, and the test would keep passing against a
    table that no real database ever had.
    """
    engine = create_engine(url)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE quantitative_evidence DROP COLUMN unit")
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, delta) "
            "VALUES ('e#0','e',0,'dB',0.44)"
        )
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, delta) "
            "VALUES ('e#1','e',1,'percent',0.5)"
        )
    engine.dispose()


def test_unit_backfill_moves_the_old_unit_and_clears_protocol(tmp_path: Path, file_database):
    """`protocol` used to hold the unit. The backfill must move it, not copy it:
    leaving "dB" in protocol would make the field lie about being a protocol."""
    url = f"sqlite:///{tmp_path / 'old.db'}"
    _old_database_without_unit(url)

    init_db(url=url)

    with session_scope() as session:
        rows = session.execute(
            text("SELECT id, unit, protocol FROM quantitative_evidence ORDER BY id")
        ).all()
    assert rows == [("e#0", "dB", None), ("e#1", "percent", None)]


def test_second_init_db_does_not_destroy_the_backfilled_unit(tmp_path: Path, file_database):
    """The backfill runs on every init_db(), so it must be idempotent by data:
    an unguarded `unit = protocol` would set unit to NULL on the second pass,
    because the first pass already cleared protocol. This test is the reason the
    statements carry WHERE clauses instead of running unconditionally."""
    url = f"sqlite:///{tmp_path / 'twice.db'}"
    _old_database_without_unit(url)

    init_db(url=url)
    with session_scope() as session:
        session.execute(
            text("UPDATE quantitative_evidence SET protocol = 'zero-shot' WHERE id = 'e#0'")
        )

    init_db(url=url)  # second start-up, as every CLI run and every test fixture does

    with session_scope() as session:
        row = session.execute(
            text("SELECT unit, protocol FROM quantitative_evidence WHERE id = 'e#0'")
        ).one()
    assert row == ("dB", "zero-shot")


def test_backfill_normalises_vocabulary_and_never_drops_a_unit(tmp_path: Path, file_database):
    """Legacy rows are not constrained by the extractor: a hand-edited database may
    say 'DB', 'dB ', or carry an empty-string unit. The guards normalise the first
    two and treat the third as "no value" - with `unit IS NULL` the empty string
    would count as filled, the protocol would be cleared, and the unit would be
    gone with no copy left anywhere. A real protocol ('zero-shot') must survive."""
    url = f"sqlite:///{tmp_path / 'variants.db'}"
    _old_database_without_unit(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE quantitative_evidence ADD COLUMN unit VARCHAR(32)"
        )
        conn.exec_driver_sql(
            "INSERT INTO quantitative_evidence (id, evidence_id, seq, protocol, unit) VALUES "
            "('v#0','e',0,'DB',NULL),"
            "('v#1','e',1,'dB ',NULL),"
            "('v#2','e',2,'dB',''),"
            "('v#3','e',3,'percent','dB'),"
            "('v#4','e',4,'zero-shot',NULL)"
        )
    engine.dispose()

    init_db(url=url)

    with session_scope() as session:
        rows = session.execute(
            text("SELECT id, unit, protocol FROM quantitative_evidence "
                 "WHERE id LIKE 'v#%' ORDER BY id")
        ).all()
    assert rows == [
        ("v#0", "dB", None),      # 'DB' normalised
        ("v#1", "dB", None),      # trailing space normalised
        ("v#2", "dB", None),      # empty-string unit counts as "no value"
        ("v#3", "dB", None),      # an existing unit wins, the old copy is cleared
        ("v#4", None, "zero-shot"),  # a real protocol is not a unit and is untouched
    ]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_database.py -v -k "unit or backfill"
```

预期：三条都 `FAILED`。第一条拿到 `("e#0", None, "dB")`——列被加上但没回填；第二条同样拿不到 `("dB", "zero-shot")`；第三条的变体行（`DB` 大写 / `dB ` 带尾空格 / unit 为空串）全部停在原值。

- [ ] **Step 3: 加按数据幂等的回填**

**不要**把回填挂在 `if name not in existing:` 分支里。`unit` 列一旦被某次 `init_db()`
建出来（例如两个提交之间跑过一次），后续就再也不会进那个分支，回填被永久跳过，
而全量测试全绿——只有真实库里静默失去单位。改为语句自带数据守卫、可重复执行，
与同文件里既有的无条件 `DELETE FROM contradiction_assessments WHERE rowid NOT IN (...)`
是同一模式。

`src/research_os/storage/database.py`，在 `_ADDED_INDEXES` **之前**加：

```python
# Statements that are safe to run on every start-up because each carries its own
# data guard. `protocol` used to hold the unit ("dB"/"percent") because plan §15's
# protocol slot had no other home. Two decisions are load-bearing:
#
# - The guard is `COALESCE(unit,'') = ''`, not `unit IS NULL`. Everywhere else in
#   this codebase an empty string means "no value" (memo.py:144, claims.py:206);
#   with `IS NULL` a row whose unit is '' would be judged "already filled", its
#   protocol would be cleared, and the unit would vanish without being copied.
# - The comparison is `lower(trim(...))`. Legacy rows are not constrained by the
#   extractor - a hand-edited row may say 'DB' or 'dB '. Missing those leaves the
#   unit in protocol, which then collapses dB:0.44 to unit:0.44 once the reader
#   flips. One statement per vocabulary item rather than CASE..ELSE, so a future
#   unit cannot be silently mapped onto 'percent'.
#
# Ordering: this must run after the ALTER loop, because it reads `unit` and an old
# database only gets that column there. Do not drop the "quantitative_evidence"
# entry from _ADDED_COLUMNS just because the model has the column - create_all
# never ALTERs an existing table.
_IDEMPOTENT_BACKFILLS: tuple[str, ...] = (
    "UPDATE quantitative_evidence SET unit = 'dB' "
    "WHERE COALESCE(unit, '') = '' AND lower(trim(protocol)) = 'db'",
    "UPDATE quantitative_evidence SET unit = 'percent' "
    "WHERE COALESCE(unit, '') = '' AND lower(trim(protocol)) = 'percent'",
    "UPDATE quantitative_evidence SET protocol = NULL "
    "WHERE COALESCE(unit, '') <> '' AND lower(trim(protocol)) IN ('db', 'percent')",
)
```

`_apply_sqlite_migrations` 里，在加列的循环**之后**、`_ADDED_INDEXES` 循环之前加：

```python
        for statement in _IDEMPOTENT_BACKFILLS:
            conn.exec_driver_sql(statement)
```

加列循环本身**保持原样**，不挂任何回填：

```python
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_database.py -v
```

预期：全绿。

- [ ] **Step 5: 跑全量**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest -q --basetemp=.pytest_tmp_s1_t2
```

预期：`330 passed, 2 skipped`（326 + Task 1 的 1 条 + 本任务 3 条）。

- [ ] **Step 6: 提交**

```bash
git add src/research_os/storage/database.py tests/unit/test_database.py
git commit -m "feat(db): move the old unit out of protocol, idempotently

An unguarded `unit = protocol` would null the column on the second init_db(),
because the first pass already cleared protocol. The statements therefore carry
data guards, which also keeps the backfill working for databases where an earlier
start-up already added the column. Two more decisions are pinned by tests: the
guard treats an empty-string unit as "no value" (as the rest of the codebase
does), and it normalises case and whitespace so a hand-edited legacy row still
migrates instead of leaving its unit behind in protocol."
```

---

### Task 3: 翻转写入点、读取点、渲染点（必须一起改）

**Files:**
- Modify: `src/research_os/research/quantitative.py:94-105,143,192`
- Modify: `src/research_os/research/claims.py:206`
- Modify: `src/research_os/reporting/memo.py:144,169`
- Test: `tests/unit/test_quantitative.py:30,45,48,52,58,93`
- Test: `tests/integration/test_evidence_quality.py:58`
- Test: `tests/unit/test_claim_identity.py`（追加 1 条）

**为什么必须一起改**：写完 `unit` 而 `_buckets` 还读 `protocol`，delta 行的 bucket 会从
`dB:0.44` 变成 `unit:0.44`，历史行与新行永不合并；`memo.py` 还读 `protocol` 则所有数值
丢掉单位。三者任何一个单独改，测试都会红在别处。

- [ ] **Step 1: 先把既有断言改成新语义（这会红）**

`tests/unit/test_quantitative.py`：

- 第 30 行 `assert fact.protocol == "dB"` → `assert fact.unit == "dB"`
- 第 45 行 `assert psnr.protocol == "dB"` → `assert psnr.unit == "dB"`
- 第 48 行 `assert ssim.protocol is None` → `assert ssim.unit is None`
- 第 52 行 `def test_extracts_percent_protocol():` → `def test_extracts_percent_unit():`
- 第 58 行 `assert facts[0].protocol == "percent"` → `assert facts[0].unit == "percent"`
- 第 93 行 `assert row.protocol == "dB"` → `assert row.unit == "dB"`

`tests/integration/test_evidence_quality.py` 第 58 行：

```python
        assert psnr_sidd.unit == "dB"
```

在 `tests/unit/test_claim_identity.py` 末尾追加（先读该文件的 `_identity` 辅助函数签名再写，
它已接收 `quantitative=`）：

```python
def test_delta_bucket_label_survives_the_unit_split():
    """The bucket label is part of the identity key (ADR-021). Moving the unit out
    of `protocol` must not rename it: `dB:0.44` and `unit:0.44` would never merge,
    so a re-run after the migration would split every delta claim from its history."""
    identity = _identity(
        "Our method brings a gain of +0.44 dB on SIDD.",
        quantitative=[
            QuantitativeEvidence(evidence_id="e", unit="dB", delta=0.44, comparator_value=39.29)
        ],
    )

    assert identity.value_bucket == ("dB:0.44",)
```

- [ ] **Step 2: 运行，确认失败**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_quantitative.py tests/unit/test_claim_identity.py -v
```

预期：`test_quantitative.py` 里 4 条红（`fact.unit` 拿到 `None`，值还被写进了 `protocol`），
`test_claim_identity.py` 的新用例红在 `assert ('unit:0.44',) == ('dB:0.44',)`——
因为 `_buckets` 仍在读 `row.protocol`，而它是 `None`，于是走 `or 'unit'` 分支。
这条红正是我们要防的那件事。

- [ ] **Step 3: 改写入点**

`src/research_os/research/quantitative.py` 第 94-99 行 docstring 里的 `"dB" protocol`
改为 `"dB" unit`：

```python
def _unit_near(text: str, value_end: int) -> str | None:
    """Unit attached to *this* value, not to the sentence as a whole.

    A sentence can report "PSNR by 0.42 dB and SSIM by 0.013"; giving both the
    "dB" unit would silently mislabel the SSIM number.
    """
```

第 143 行：

```python
        unit="dB" if match.group("unit").lower() == "db" else "percent",
```

第 192 行：

```python
                    unit=_unit_near(text, value_end),
```

- [ ] **Step 4: 改读取点与渲染点**

`src/research_os/research/claims.py` 第 206 行：

```python
            buckets.append(f"{row.unit or 'unit'}:{round(row.delta, 2)}")
```

`src/research_os/reporting/memo.py` 第 144 行：

```python
    unit = {"dB": " dB", "percent": "%"}.get(fact.unit or "", "")
```

第 169 行：

```python
            key = (fact.dataset or "unspecified", fact.metric or fact.unit or "unspecified")
```

- [ ] **Step 5: 运行，确认全绿**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/unit/test_quantitative.py tests/unit/test_claim_identity.py tests/integration/test_evidence_quality.py -v
```

预期：全绿。

- [ ] **Step 6: 跑全量 + 检查 memo 输出未变**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest -q --basetemp=.pytest_tmp_s1_t3
```

预期：`331 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
git add src/research_os/research/quantitative.py src/research_os/research/claims.py \
        src/research_os/reporting/memo.py tests/unit/test_quantitative.py \
        tests/unit/test_claim_identity.py tests/integration/test_evidence_quality.py
git commit -m "refactor(quant): write and read the unit through its own field

Writer, bucket reader and memo renderer move together on purpose: flipping any
one of them alone renames every delta bucket from dB:0.44 to unit:0.44, which
would split new claims from their history (ADR-021)."
```

---

### Task 4: `inspect_claim` 输出键改名

**Files:**
- Modify: `src/research_os/reporting/memo.py:503`
- Test: `tests/integration/test_claim_synthesis.py`（追加）

- [ ] **Step 1: 写会失败的测试**

在 `tests/integration/test_claim_synthesis.py` 末尾追加。该文件已有 `_run_fixture_slice`
与 `inspect_claim` / `SqlClaimRepository` 的 import，直接复用：

```python
def test_inspect_claim_reports_unit_not_protocol(db, tmp_path):
    """`inspect_claim` is a public surface (CLI `inspect-claim`). It used to emit
    a key named "protocol" whose value was a unit ("dB"), so a reader of that
    payload would conclude the row carried an evaluation protocol."""
    run_id = _run_fixture_slice(tmp_path)

    facts = []
    with session_scope() as session:
        for claim in SqlClaimRepository(session).list_by_run(run_id):
            info = inspect_claim(session, run_id, claim.id)
            for entry in info["chain"]:
                facts.extend(entry["quantitative"])

    assert facts, "the fixture must produce at least one quantitative fact"
    assert any(fact["unit"] == "dB" for fact in facts)
    assert all("protocol" not in fact for fact in facts)
```

- [ ] **Step 2: 运行，确认失败**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/integration/test_claim_synthesis.py -v -k unit
```

预期：`FAILED`（`assert all("unit" in fact ...)` 失败，因为键还叫 `protocol`）。

- [ ] **Step 3: 改键名**

`src/research_os/reporting/memo.py` 第 503 行：

```python
                        "unit": fact.unit,
```

- [ ] **Step 4: 运行，确认通过**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest tests/integration/test_claim_synthesis.py tests/integration/test_evidence_quality.py -v
```

预期：全绿。

- [ ] **Step 5: 全量**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest -q --basetemp=.pytest_tmp_s1_t4
```

预期：`332 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
git add src/research_os/reporting/memo.py tests/integration/test_claim_synthesis.py
git commit -m "refactor(memo): rename the inspect-claim payload key to unit

The key said protocol and the value was dB, so anyone reading the payload drew
the wrong conclusion about what the row carries."
```

---

### Task 5: ADR-033 + 文档同步 + 回归核对

**Files:**
- Modify: `architect.md`（ADR 表 + 已知限制）
- Modify: `README.md`（若其中描述了定量字段）
- Test: 无新增

- [ ] **Step 1: 先看 README 有没有描述该字段**

```bash
grep -n "protocol\|定量\|QuantitativeEvidence" README.md
```

有则按实际措辞同步；无则跳过 README，**不要为了同步而编内容**。

- [ ] **Step 2: 加 ADR-033**

`architect.md` 的 ADR 表末尾（ADR-032 之后）加一行：

```markdown
| ADR-033 | `QuantitativeEvidence` 的**单位**从 `protocol` 拆出为 `unit`（见维护记录 2026-11-15）。计划 §15 给 `protocol` 的语义是**评测协议**，而实现把 `dB`/`percent` 存在该字段里：`value_bucket` 因此产出 `dB:0.44` 这类「伪协议」标签，`inspect_claim` 也把单位当协议报给调用方。拆分**不改变**任何渲染输出与 `value_bucket` 标签（ADR-021 的合并键稳定），`protocol` 在 S4 之前保持为空——空字段比如实标注的错字段更容易被发现 | ACTIVE |
```

- [ ] **Step 3: 在「已知限制」里加一条**

`architect.md` 的「已知限制」小节末尾加：

```markdown
13. `QuantitativeEvidence.protocol` 自 2026-11-15 起为空：单位已迁到 `unit`，评测协议要等 S4。读到空的 `protocol` 是**已知**状态，不是抽取失败。
```

- [ ] **Step 4: 跑全量并与基线对账**

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest -q --basetemp=.pytest_tmp_s1_t5
```

预期：`332 passed, 2 skipped`。同时核对收集数：

```bash
"D:/Anaconda/envs/reOS/python.exe" -m pytest --collect-only -q --basetemp=.pytest_tmp_s1_collect | tail -3
```

预期：`334 tests collected`（328 + 6 条新用例）。**若收集数少于 334，说明有用例被静默删除或覆盖，停下查。**

- [ ] **Step 5: 提交**

```bash
git add architect.md README.md
git commit -m "docs(arch): record the protocol/unit split as ADR-033

Also states in the known-limits list that an empty protocol is expected until
S4, so a reader does not read the emptiness as an extraction failure."
```

- [ ] **Step 6: 收尾核对（不提交，只报告）**

```bash
git log --oneline master..HEAD | head -10
git diff --stat master..HEAD -- src/ tests/
```

确认：5 个提交、`src/` 改动只涉及上表 7 个文件、没有意外删行。

---

## 验收（S1 完成判据）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | `value_bucket` 标签逐字不变 | Task 3 的 `test_delta_bucket_label_survives_the_unit_split` 断言 `("dB:0.44",)` |
| 2 | memo 渲染输出不变（单位仍显示） | `tests/integration/test_evidence_quality.py` 断言 `"39.18" in memo`；Task 3 Step 6 全量绿 |
| 3 | `init_db()` 两次幂等 | Task 2 的 `test_second_init_db_does_not_destroy_the_backfilled_unit` |
| 4 | 既有用例一条不少 | Task 5 Step 4 的收集数 `334` |
| 5 | `protocol` 不再被用作单位 | `grep -rn "fact.protocol\|row.protocol" src/` 只应命中 `repositories.py` 的映射 | 

## 明确不做（S1 边界）

- 不抽取真实评测协议（`zero-shot` 等），那是 S4。
- 不改 `conditions`、不改 `identity_key`、不改矛盾判定。
- 不引入 Alembic（ADR-011 / 计划 §35）。
- 不改 `scripts/method_acquisition_audit.py`——它已经声明 `protocol` 不计入 L4 覆盖，
  拆分后该声明仍然成立，不需要动。
