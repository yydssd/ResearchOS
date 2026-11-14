# P5 补齐设计（2026-11-14）

> 背景：P5 已交付（tag `w3-p5`），独立代码审查判「Needs work」，权威计划
> `ResearchOS-Implementation-Plan.md` v1.1 复审另发现 §25 与 §2.5 两处未满足。
> 本文只覆盖**未偿项的补齐**，不重新设计 P5。

## 0. 范围

| 块 | 内容 | 来源 |
|---|---|---|
| A | 方向词表补否定式与规则盲区 | 审查 #7 · **已完成** |
| B | `FAILURE` 事件与错误处理 | 计划 §25 · 审查 #8 |
| C | 三组 5×5 混淆矩阵 | spec §9 #3 · 审查 #10 |
| D | 幂等内容断言、`replaced` 断言、主键去截断、CWD 无关 | 审查 #10/#11 · spec §9 #14 |
| E | 空断言补强（4 处）+ 关键覆盖缺口 | 审查 #9 |
| F | 验收口径、文档同步、偏差索引 | 计划 §34#11 |

**不做**：重写级联、改配对键、放宽任何判定门槛、给 P5 引入 LLM。专项：
「第二轮独立盲标」需要独立标注者，不由 agent 扮演（见 §6）。

## 1. A — 方向词表（已完成，记录在此以便追溯）

已落地：`_IMPROVE` 增 `raises?`；`_DEGRADE` 增 `lowers|lowered|lowering`（**不含**形容词
`lower`，否则 "the lower layers" 会被判为下降）；`_NO_GAIN` 增 `unchanged|no change|stays/remains/leaves ... same`。

配套：`tests/unit/test_fixture_consistency.py` 把 26 条夹具的 52 个 direction 段钉到规则上。
审计中修正 15 处（11 规则漏词 + 4 key 手误），accuracy 仍 100%。

## 2. B — `FAILURE` 事件与错误处理

计划 §25：「**Do not silently swallow exceptions. Persist failure events.**」这是祈使句，不是建议。
当前 P5 路径 0 条 failure 事件，且跨 run 的 `ValueError` 会冲出 `run_vertical_slice` 中止整个 run。

### 2.1 四种失败，四种处置

| 触发 | 处置 | FailureType |
|---|---|---|
| `replace_for_run` 拒收跨 run 主张对 | 捕获 `ValueError` → 记事件 → 本次写 0 条 → **run 继续** | `CROSS_RUN_PAIR`（新增） |
| 单对判定抛异常 | `assess()` 内逐对 `try/except Exception` → 计数 → 继续其余对 | `CONTRADICTION_UNRESOLVED` |
| 级联第 10 行命中（同向同值） | `skipped_same_value` 之外再记一次事件（P4 合并门槛漏了） | `CONTRADICTION_UNRESOLVED` |
| 评估涉及的 claim 找不到可定位证据 | 评估后批量检查 → 记事件（带 claim ids） | `CITATION_LOCATION_MISSING` |

「可定位」的定义必须与 memo 一致，否则两处会说不同的话：一条 claim 可定位**当且仅当**
`claim_evidence_relations` 里存在 `relation=SUPPORTS` 的行。这与 `_claim_location` 的输出严格对应
——它在该 claim 没有 supports 时渲染 `no locatable evidence`。evidence 有 section 无偏移仍算可定位，
因为 memo 会退化成 `sv · section`；偏移缺失只影响精度，不影响可追溯性。

### 2.2 为什么"跨 run 不中止 run"

计划 §17 把 P5 定位为「pairwise assessment」，不是 run 的把关者；§25 要求的是**记录**失败而非
**传播**失败。一个跨 run 脏行说明存储被外部写过，那是数据问题，不该让整次研究失败。
但事件必须落库，否则就是"静默吞掉"。

### 2.3 数据流

```
assess(claims) -> (assessments, stats)
    stats.failed_pairs: int          # 新增，逐对异常计数
supervisor:
    try: replaced = replace_for_run(...)
    except ValueError as exc:  log FAILURE(CROSS_RUN_PAIR, payload={error, run_id}); assessments=[]; replaced=0
    if stats.failed_pairs:     log FAILURE(CONTRADICTION_UNRESOLVED, payload={failed_pairs})
    if stats.skipped_same_value: log FAILURE(CONTRADICTION_UNRESOLVED, payload={skipped_same_value})
    involved = {id for a in assessments for id in (a.claim_a_id, a.claim_b_id)}
    unlocatable = sorted(cid for cid in involved if not supports(cid))
    if unlocatable:            log FAILURE(CITATION_LOCATION_MISSING, payload={claim_ids})
    log CONTRADICTION_ASSESSED(...)   # 无论上面是否发生，都记统计
```

`CITATION_LOCATION_MISSING` 已在 `FailureType` 中存在，无需新增。

### 2.4 测试

- 跨 run 对 → run 完成、事件含 `cross_run_pair`、assessments 为空、后续 memo 仍生成
- 单对异常（注入一个 `assess_pair` 抛错的桩）→ 其余对仍产出判定、事件计数为 1
- 同值缺陷 → 事件出现
- 评估涉及无证据 claim → 事件带该 claim id

## 3. C — 三组混淆矩阵

spec §9 #3 要「真实子集 / 构造子集 / 合计，各自 5×5」。

现状：`summarise(rows)` 只算一张全量矩阵，且是 5 行 × 6 列（多 `SKIPPED`）。

设计：
- `summarise(rows)` 返回体新增 `confusion_by_subset: {"real": ..., "constructed": ...}`，`confusion` 保留为合计。
- 仍是 **5 行 × 6 列**。理由：`SKIPPED` 必须有落脚处，删掉它会让"该判未判"无处显示。
  这与 spec 的「5×5」是**有意的覆盖**，写进 §7 偏差表，不静默改口径。
- 打印三张表并标注行/列含义。

测试：断言 `confusion_by_subset` 的键存在；断言某子集某单元格的具体值（删掉累加循环必须失败）。

## 4. D — 幂等、主键、CWD

### 4.1 幂等内容断言

`test_replace_for_run_is_idempotent` 现在只比条数。改为逐字段比较
`(claim_a_id, claim_b_id, relationship, explanation, confidence_label)` 的有序列表，
并断言事件 payload 的 `replaced` 等于第二次删除的行数。

### 4.2 主键去截断

`create()` 的行 id 是 `con_<a[:10]>_<b[:10]>`，两对不同的主张若前 10 字符相同会撞主键，被误拒。
改为 `con_` + `sha1(f"{a}|{b}")[:16]`。旧行不迁移：id 只是主键，不参与判定、配对或追溯，
新格式不会与任何旧 id 相撞（旧格式是 `con_<10 位>_<10 位>`，新格式是 `con_` + 16 位十六进制，
长度与分隔符都不同）。

测试：构造两个前 10 字符相同、实际不同的对，断言都能写入。

### 4.3 CWD 无关

`scripts/evaluate_contradiction.py` 与 `tests/unit/test_evaluate_contradiction.py` 用相对路径
`tests/fixtures/...`，只在仓库根成立。改为基于 `Path(__file__).resolve().parents[N]`。
测试：从 `tests/` 目录运行该测试文件仍通过。

## 5. E — 断言强度

审查点名 4 处只查"键存在/容器非空"，加 3 处关键缺口：

| 位置 | 现在 | 改为 |
|---|---|---|
| `test_contradiction_run.py` 事件 payload | 12 个键存在 | 断言 `assessments == 实际条数`、`evaluated == total_before_cap`、`by_type` 之和等于判定数 |
| `test_contradiction_memo.py` `inspect_claim` | `"relationship" in ...` | 断言具体 `relationship` 值与该对唯一 id |
| `test_contradiction_memo.py` memo 文本 | `"coverage" in memo` | 断言具体百分比与某条 `dataset differs:` 的解释文本 |
| `test_evaluate_contradiction.py` 混淆矩阵 | 只验键集合 | 断言具体单元格计数 |
| 缺口：`skipped_missing_metric` | 无 | 单测构造只缺 metric 的对 |
| 缺口：`skipped_cap` | 无 | 用 `monkeypatch.setattr(contradiction, "MAX_PAIRS", 2)` 调小后造 3 对，断言 `skipped_cap == 1` 且 `coverage == 2/3` |
| 缺口：级联行 3 同向 | 无 | 条件不等 + 同向 → `COMPLEMENTARY` |

## 6. 外部依赖（不由 agent 充当）

**第二轮独立盲标**仍然缺席。本次改为「专家复核」（owner 逐条裁决，23 接受 / 3 纠正），
已在 `ANNOTATION.md` 记为 `expert review`，与 `blind annotation` 明确区分。
补齐工作**不会**声称独立一致率；`TRUE_CONTRADICTION` 的 precision/recall 在真实语料仍不可测。

## 7. 偏差登记

- spec §9 #3 要求 5×5，实现保持 5×6（含 `SKIPPED`）——记入 spec §11 偏差表。
- 计划 §2.5 把 `contradiction judgment` 列为 LLM 适用场景，实现为确定性级联——
  补 ADR-031 说明理由（确定性优先、可复现、`ContradictionAssessor` 协议留给 P8 换 LLM）。
- 计划 §6 的 `evaluation/metrics.py|runner.py` 未建，实际在 `scripts/`——补 ADR-032。

## 8. 顺序与验收

1. B（FAILURE）——行为变更，最先评审
2. C（三组矩阵）
3. D（幂等/主键/CWD）
4. E（断言强度）
5. F（文档、偏差表、ADR-031/032）

每块 TDD、单独提交。完成判据：

- `pytest` 全绿且新增断言能失败（删掉对应实现逻辑后测试必红）
- 一次真实 run 的 `FAILURE` 事件可查
- 三张混淆矩阵输出且单元格值有断言
- 从非仓库根目录跑评估脚本仍通过
- `git status` 干净，`w3-p5` 标签指向最终提交
