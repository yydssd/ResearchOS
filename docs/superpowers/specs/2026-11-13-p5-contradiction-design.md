# P5 — Contradiction Analysis · 设计规格

- **日期**：2026-11-13（W3 / Day 5）
- **对应计划**：§17（Phase 5 — Contradiction Analysis），受 §2.2 可追溯、§25 失败模型约束
- **前置状态**：P0 ✅、P1 ✅、P2 ✅、P3 ✅、P4 ✅（163 tests，tag `w3-p4.1`）
- **范围**：只做主张对之间的矛盾判定与呈现。不做 P6 memo 结构重排、P7 反证搜索、不改主张层语义。

---

## 1. 目标

把「两条主张互相矛盾」从一句人工判断，变成**有据可查的判定**：给定两条主张，输出它们属于
计划 §17 要求的五种关系之一，并说明**是哪一维**导致的。

```text
Claim × Claim（同 task、subject 可比）
   → 级联比较 identity 七维（dataset → conditions → metric → direction）
   → ContradictionAssessment（relationship + explanation + confidence_label）
   → memo 的 # Contradictions and Open Questions
```

计划 §17 的硬约束：**默认结果不得是 `TRUE_CONTRADICTION`**。本文档 §5 的级联顺序就是这条约束的
可执行版本——先判「范围是否相同」这类确定事实，方向相反只有在其余维度全等时才升级为真矛盾。

## 2. 配对规模实测（设计由这些数字驱动）

**样本**：P4 留出集 20 篇未见论文（`docs/evaluation/holdout-ids-2026-11-12.txt`），
1063 条 SUPPORTED 且带 `identity_key` 的主张。

| 维度分布 | 数量 |
|---|---|
| subject：具名 / `self@` / 无 | 544 / 459 / 60 |
| direction：`UP` / `LEVEL` / 缺失 | 491 / 196 / 376 |

| 配对规则 | 组数 | 候选对 | 跨文档对 |
|---|---|---|---|
| 同 subject + 同 task（具名） | 99 | **1047** | **137** |
| 同 task + dataset 相等 | 19 | 1471 | 772 |
| 同 subject + task + dataset | 32 | 111 | 3 |
| 仅同 task | 5 | 425220 | 395015 |

对「同 subject + 同 task」这 1047 对再切片：**387 对数据集不同**（`SCOPE_DIFFERENCE` 的来源）、
**224 对方向相反**（真矛盾的候选）。

同文档 `self@` 对需要一道预处理，否则单篇论文内部就产生 6177 对：

| 预处理 | 剩余对 |
|---|---|
| 无 | 6177 |
| 双方都有 dataset | 148 |
| **双方都有 dataset 与 metric（采用）** | **16** |
| 再加双方都有 direction | 9 |

采用「双方都有 dataset 与 metric」，因为它与级联第 1 步的跳过条件完全一致——
这些对本来就会被跳过，提前过滤只是省掉无用遍历，不改变任何判定结果。
若连 direction 也要求，则会误杀「同 scope 但缺方向」这一类，而那正是要报 `INSUFFICIENT_EVIDENCE` 的对象。

合计候选对：**1047 + 16 = 1063 对 / 20 篇**。

| 观察 | 数字 | 对设计的含义 |
|---|---|---|
| 仅按 task 配对 | 42.5 万对 | 组合爆炸，task 必须与 subject 或 dataset 组合 |
| task 分布集中度 | `image restoration` 916/1063 | task 无法单独区分主题，不能作唯一配对键 |
| 同文档 `self@` 对 | 6177 对 → 要求双方有 dataset 与 direction 后 **61 对** | 同文档对比必须收紧，否则噪声淹没结果 |
| 方向缺失 | 376/1063（35%）；配对中一方缺方向 858 对 | 缺方向的处置决定产物规模 |
| 跨文档具名 subject | `adair` 出现在 3 篇；`db` 出现在 9 篇 | 跨文档矛盾机制上可达；`db` 疑为误抽，需在实现时核查 |

**结论**：配对键选 subject + task，不选 dataset。理由是 §17 的范例
（*spatial conditioning* 在 Rain100H/Transformer 与 SIDD/CNN 上结论不同 → `SCOPE_DIFFERENCE`）
两条主张**数据集不同**，若要求 dataset 有交集，该范例永远配不成对，而它正是本阶段要判对的第一样例。

## 3. 设计决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 判定引擎为**纯确定性级联**，零 LLM 参与 | 与 P4 的 deterministic-first 一致（ADR-020~025）；可复现、零成本；LLM 版本留给 P8 作对照基线 |
| D2 | 配对键 = **同 task + subject 可比**，不要求 dataset 相同 | §17 范例靠跨数据集成立；dataset 相同与否是**判定结果**（`SCOPE_DIFFERENCE`），不是配对前提 |
| D3 | 「同一 subject」= **同一个对象**：具名相等，或同一文档内的两条 `self@`；跨文档 `self@` 永不判矛盾 | 同文档方向相反是论文内部不一致，是有价值信号；跨文档的两个 `self@` 是不同方法 |
| D4 | 级联顺序 **scope → metric → direction**，首个命中即定论 | 计划 §17：默认不得判真矛盾。数据集/条件差异是确定事实，方向相反只是表面冲突 |
| D5 | 缺 dataset 或 metric → **静默跳过并计数**；缺 direction 且其余全等 → `INSUFFICIENT_EVIDENCE` | 范围信息缺失时连「是否同一范围」都无法断言，判「证据不足」等于替证据说话 |
| D6 | `confidence_label` 是**来源标注**，不是打分 | `TRUE_CONTRADICTION→DISPUTED`、`SCOPE_DIFFERENCE`/`EXPERIMENTAL_INCOMPATIBILITY→MEDIUM`、`COMPLEMENTARY→HIGH`、`INSUFFICIENT_EVIDENCE→LOW` |
| D7 | P5 **不修改** claim 的 `status` 与 `confidence_label` | P4 的状态语义刚钉死（ADR-022）；P5 顺手改会让两层语义边界糊掉 |
| D8 | fixture **真实句子为主 + 构造补齐**，真实/构造分开统计准确率 | 真实语料真矛盾近乎为零，纯构造会把「规则的测试」当成「能力的验收」 |

## 4. 配对规则

`pair_candidates(claims) -> list[(Claim, Claim)]`，确定性，无随机：

1. 双方 `status == SUPPORTED`（P4 已把无支撑证据标出，不重复判定）。
2. 双方 `task` 非空且相等。
3. subject 可比，满足其一：
   - 双方 subject 都是具名且相等；
   - 双方都是 `self@`，且 `source_version_id` 相同（同一文档）。
4. 排除同一 claim 自配；`(a, b)` 按 claim id 字典序规范化，保证不重复、可复现。
5. 规模上限 `MAX_PAIRS = 50_000`；超出时按 claim id 顺序截断，并记事件（见 §7）。

`self@` 对额外要求双方都有 dataset 与 metric——实测这把这个桶从 6177 对压到 16 对，
且被砍掉的对在级联第 1 步就会被跳过，不改变判定结果，只省掉无用遍历（§2 有完整阶梯）。

## 5. 判定级联

`assess_pair(a, b) -> ContradictionAssessment | None`，**按顺序首个命中即定论**：

| # | 条件 | 结论 | confidence |
|---|---|---|---|
| 1 | 任一方缺 dataset 或 metric | **跳过**（返回 None，计数） | — |
| 2 | dataset 集合不相等 | `SCOPE_DIFFERENCE` | MEDIUM |
| 3 | `conditions` 不相等 | `SCOPE_DIFFERENCE` | MEDIUM |
| 4 | metric 集合无交集 | `EXPERIMENTAL_INCOMPATIBILITY` | MEDIUM |
| 5 | 任一方缺 direction | `INSUFFICIENT_EVIDENCE` | LOW |
| 6 | direction 相同 | `COMPLEMENTARY` | HIGH |
| 7 | direction 相反 | `TRUE_CONTRADICTION` | DISPUTED |

第 7 步的前提（同一对象）已由配对规则保证，因此级联内部不再重复判断 subject。

`explanation` 必须写成可审计的一句，点名**哪一维**导致该结论：

```text
dataset differs: rain100h vs sidd
conditions differ: backbone=cnn vs backbone=transformer
metric has no overlap: psnr vs lpip
direction missing on side B: "Restormer cuts the error on SIDD"
same scope, opposite direction: UP vs LEVEL
same scope, same direction: UP vs UP (values 39.18 vs 38.50 dB)
```

不允许出现「模型认为」「可能」这类措辞——判定是规则的结果，解释必须指回规则。

输出顺序固定：按 `relationship`（真矛盾 → 实验不兼容 → 范围差异 → 互补 → 证据不足）再按
`(claim_a_id, claim_b_id)` 排序，保证同一输入两次运行产生逐字节相同的 memo 段。

## 6. 编排与呈现

**模块**：`src/research_os/research/contradiction.py`

```text
pair_candidates(claims) -> list[tuple[Claim, Claim]]
assess_pair(a, b) -> ContradictionAssessment | None
ContradictionAssessor (Protocol)  -> assess(claims) -> ContradictionResult
HeuristicContradictionAssessor    # 配对 + 逐对级联 + 统计
ContradictionResult: assessments / stats{considered, skipped_missing_scope, emitted_by_type}
```

Protocol 与既有 `ClaimBuilder` / `EvidenceExtractor` / `QuantitativeExtractor` 同构，
便于 P8 用 LLM 版本替换而不改调用方。

**落库**：复用现表 `contradiction_assessments`（`claim_a_id` / `claim_b_id` / `relationship` /
`explanation` / `confidence_label`），**不加列**。查询新增 `list_by_run(run_id)`，通过
`claims.run_id` join——ADR-019 要求追溯类输出一律 run 作用域，P3 已因全库 `list_all()` 踩过一次。

**编排**：supervisor 在 `claims → relations` 之后、memo 之前插入：

- 任务用现成的 `TaskType.CHECK_CONTRADICTION`；
- 新增 `EventType.CONTRADICTION_ASSESSED`，payload 带五类计数与跳过数；
- 单对判定异常不中断整轮：捕获、记事件、继续（与 P2 provider 失败策略一致）；
- 达到 `MAX_PAIRS` 时记事件说明截断，不静默。

**memo**：`# Contradictions and Open Questions` 从占位句改为分节渲染，顺序固定：

```text
## True contradictions (n)
- same scope, opposite direction: UP vs LEVEL
  A: "<claim text>"  (run scope)
  B: "<claim text>"

## Experimental incompatibilities (n)
## Scope differences (n)
## Complementary findings (n)      # 按 subject 折叠成一行汇总，避免淹没 memo
## Insufficient evidence (n)
## Skipped for missing scope (n)
```

无判定时写明确的一句（`No comparable claim pair in this run.`），不留空段。

## 7. 错误处理

| 情况 | 处置 |
|---|---|
| claim 集为空 / 无可配对 | 不报错，memo 写明「无可比主张对」，事件记 0 |
| 单对判定抛异常 | 捕获 → `FAILURE` 事件 → 继续其余对；该对不落库 |
| 配对数超上限 | 截断到 `MAX_PAIRS`（按 id 序），记事件说明截断量 |
| 同一对重复产出 | 由 `(a, b)` 规范化 + 唯一索引保证；落库前按 `(claim_a_id, claim_b_id)` 去重 |
| 历史 run 的旧数据 | `list_by_run` 只取本 run，不受污染 |

## 8. 明确不做

- LLM 参与判定或写解释（P8 作对照基线时再引入）。
- 数值大小的矛盾判定（`39.18` vs `38.5` 不算矛盾——不同方法不同设置本就不同）；数值差异只进 explanation，不改类型。
- 跨指标换算（dB 与 % 不互转）、跨数据集数值比较。
- 代词消解与表格解析（dataset 覆盖率的独立技术债，见 architect 限制 11）。
- 修改 claim 状态、置信度或 identity（D7）。
- memo 结构重排（属 P6）。

## 9. 验收

1. **§17 范例**：`Spatial conditioning improves Rain100H with Transformer` 与
   `Spatial conditioning shows no gain on SIDD with CNN` → `SCOPE_DIFFERENCE`（因 dataset 不同），
   **不得**为 `TRUE_CONTRADICTION`。
2. **真矛盾**：同一具名 subject、同 dataset、同 metric、同 conditions、方向相反 → `TRUE_CONTRADICTION`
   + `DISPUTED`。
3. **文档内部不一致**：同一文档两条 `self@`、同 dataset/指标、方向相反 → `TRUE_CONTRADICTION`。
4. **跨文档 self@**：两篇论文各自的 `self@`、同 task 同 dataset、方向相反 → **不产出** assessment。
5. **范围差异**：同 subject 同 task、dataset 不同 → `SCOPE_DIFFERENCE`，explanation 含两个数据集名。
6. **实验不兼容**：dataset 与 conditions 相同、metric 集合无交集 → `EXPERIMENTAL_INCOMPATIBILITY`。
7. **证据不足**：dataset 相等、metric 有交集、conditions 相等，但一方缺 direction →
   `INSUFFICIENT_EVIDENCE`；若缺 dataset 或 metric → 该对**不落库**，只进 `skipped_missing_scope` 计数。
8. **互补**：同 scope 同方向 → `COMPLEMENTARY`，confidence `HIGH`。
9. **fixture 集**：≥20 对，真实语料配对 ≥12 对 + 构造补齐至 ≥20 对；五类均有覆盖；
   分类准确率 **≥85%**，且**真实子集与构造子集分别报告**。真实子集未达 85% 时如实记录，不调规则凑数。
10. **不修改主张**：P5 跑完后 claim 的 `status` / `confidence_label` 与跑之前逐条相等。
11. **留出集回归**：20 篇缓存跑通，报告五类分布与 `skipped_missing_scope`；真实语料真矛盾为 0 时
    如实记录为结果，不作为失败。
12. `pytest` 全绿，现有 163 条测试不回归。

## 10. 已知限制

1. 判定完全依赖 P4 的 identity 质量：dataset 覆盖率仅 17%，因此大量对会落在「跳过」或
   `INSUFFICIENT_EVIDENCE`，真矛盾的可见性受此上限约束。
2. 具名 subject 抽取存在误报（留出集里 `db` 出现在 9 篇文档），会让不相关的对进入同一组；
   判定本身仍要求 dataset/指标/条件一致，因此不会凭空造矛盾，但会产生无意义的 `COMPLEMENTARY`。
3. 方向来自词表（UP/LEVEL），`improves`/`degrades` 之外的表述（如 `closes the gap`）抽不到方向，
   落到 `INSUFFICIENT_EVIDENCE`。
4. 数值矛盾不判定：同一方法同一数据集报出不同数值（复现失败）目前记为 `COMPLEMENTARY`，
   explanation 里带出数值差，但不升级为矛盾类型。
5. `self@` 同文档内部的「方向相反」可能是同一方法在不同消融设置下的正常差异，当前一律判
   `TRUE_CONTRADICTION`；`conditions` 能区分一部分，剩余部分会误报。
