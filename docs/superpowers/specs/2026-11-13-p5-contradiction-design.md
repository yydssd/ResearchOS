# P5 — Contradiction Analysis · 设计规格

- **日期**：2026-11-13（W3 / Day 5）
- **对应计划**：§17（Phase 5 — Contradiction Analysis），受 §2.2 可追溯、§25 失败模型约束
- **前置状态**：P0 ✅、P1 ✅、P2 ✅、P3 ✅、P4 ✅（163 tests，tag `w3-p4.1`）
- **范围**：主张对之间的矛盾判定与呈现，含一处 **P4 前置修正**（direction 语义）。不做 P6 memo 结构重排、P7 反证搜索。

---

## 1. 目标

把「两条主张互相矛盾」从人工判断变成**可审计的判定**：输出计划 §17 要求的关系之一，
并说明**是哪一维**导致的、**证据在哪**。

```text
Claim × Claim（同 task、subject 可比）
   → 级联比较 dataset → conditions → metric → direction
   → ContradictionAssessment（relationship + explanation + confidence + 证据位置）
   → memo 的 # Contradictions and Open Questions
```

计划 §17 的硬约束：**默认结果不得是 `TRUE_CONTRADICTION`**。本规格把这条约束实现为
「只有范围被**证实**相同、方向被**证实**对立时才升级为真矛盾」——不是靠顺序把结果压下去，
而是靠证据门槛让它很少成立。

## 2. 实测：现有标签不足以支撑判定

**样本**：P4 留出集 20 篇未见论文，1063 条 SUPPORTED 且带 `identity_key` 的主张。

### 2.1 direction 的语义错误（必须先修）

| 现象 | 数字 | 后果 |
|---|---|---|
| `LEVEL` 主张命中 `achiev/reach/report` | **196 / 196** | 当前 `LEVEL` 全部是「报告了一个数值」，没有一条是「明确说无改善」。`UP vs LEVEL` 不是对立 |
| `UP` 主张含 `reduce/increase` | **150 / 491** | 方向本身歧义：`reduces error` 变好，`reduces PSNR` 变坏 |
| 含明确「无改善/变差」表述的主张 | **13 / 1063** | 真正可用的「反向」信号极少 |

现有实现（`research/claims.py`）：`DIRECTION_UP` = `improv|gain|outperform|better|surpass|exceed|reduce|increase`；
`DIRECTION_LEVEL` = `achiev|reach|report`。用户指出的正是这条：**「提高 PSNR」与「报告 PSNR 为 30 dB」可以同时成立**。

### 2.2 conditions 几乎抽不到

| 现象 | 数字 |
|---|---|
| 抽到 conditions 的主张 | **28 / 1063（2.6%）** |
| 其中 `setting` / `granularity` / `backbone` | 26 / 2 / 1 |
| 具名对里「双方 conditions 都非空且相等」 | **1 对** |
| 具名对里「至少一方为空」 | **1046 / 1047** |

因此 **「两边都是空列表」只能说明没抽到，不能说明设置一致**。把空当真相同，等于用抽取器的
沉默去证明实验可比。

### 2.3 配对规模

| 配对规则 | 组数 | 候选对 | 跨文档对 |
|---|---|---|---|
| 同 subject + 同 task（具名） | 99 | **1047** | **137** |
| 同 task + dataset 相等 | 19 | 1471 | 772 |
| 仅同 task | 5 | 425220 | 395015 |

具名 1047 对中：数据集不同 **387** 对；方向相反（按现标签）**224** 对。

同文档 `self@` 对需要预处理，否则单篇论文内部产生 6177 对：

| 预处理 | 剩余对 |
|---|---|
| 无 | 6177 |
| 双方都有 dataset | 148 |
| **双方都有 dataset 与 metric（采用）** | **16** |
| 再加双方都有 direction | 9 |

采用 16 这一档，因它与级联第 1 步的跳过条件一致；再加 direction 会误杀正要报
`INSUFFICIENT_EVIDENCE` 的对象。**合计候选对 1047 + 16 = 1063 对 / 20 篇**，
`MAX_PAIRS` 上限 50000 不会在这批数据上触发。

## 3. 设计决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 判定引擎**纯确定性级联**，零 LLM | 与 P4 一致（ADR-020~025）；可复现；LLM 版留给 P8 作对照 |
| D2 | 配对键 = **同 task + subject 可比**，不要求 dataset 相同 | §17 范例的两条主张数据集不同，若要求数据集有交集则范例永不成立 |
| D3 | 跨文档 `self@` 不配对；同文档 `self@` 配对但**不享有任何判定特权** | 两个 `self@` 是不同方法；同一文档内也不能凭「同源」推断设置一致 |
| D4 | **先修 direction 语义**（见 §4）：`achiev/reach/report` 归 `None`，`LEVEL` 只留「明确无改善」 | 196/196 的 `LEVEL` 是数值陈述；不修则「提升 vs 报告数值」被当成矛盾 |
| D5 | `TRUE_CONTRADICTION` 需 **范围被证实相同**：dataset 相等、**双方 conditions 都非空且相等**、metric 有交集、方向对立 | 空 conditions ≠ 相同（2.6% 覆盖率）；缺失不得当证据用 |
| D6 | `COMPLEMENTARY` = **范围不同但方向相同**（互补发现），confidence `MEDIUM` | 「同方向」只说明不冲突，不足以称互补；互补的语义是「在不同条件下都成立，互相补充」 |
| D7 | `confidence_label` 是来源标注，不是打分；`COMPLEMENTARY` 最高 `MEDIUM` | 条件抽取不全，任何「一致」判断都带不确定性 |
| D8 | P5 **不修改** claim 的 `status` / `confidence_label` | P4 状态语义刚钉死（ADR-022）；两层语义不得混 |
| D9 | 统计必须报**截断前总量、已评估量、覆盖率**，跳过按原因分解 | 否则「没发现矛盾」会被误读为「不存在矛盾」 |
| D10 | 落库补**唯一约束与跨 run 校验**，重复运行幂等 | 现有表无唯一约束；跨 run 配对会污染审计链（ADR-019） |

## 4. 前置修正：direction 语义（P4 amendment）

现有三值语义混用了「质量方向」与「有无陈述」。改为四值，并把 `LEVEL` 的含义收窄：

| 值 | 含义 | 触发 |
|---|---|---|
| `UP` | 明确声称**变好** | `improves`、`gains`、`outperforms`、`surpasses`、`better than`、`exceeds`；`reduces error/loss/noise/artifact/complexity`；`increases PSNR/SSIM/accuracy` |
| `DOWN` | 明确声称**变差** | `degrades`、`drops`、`worse than`、`hurts`、`fails on`；`reduces PSNR/SSIM/accuracy/performance`；`increases error/loss/noise` |
| `LEVEL` | 明确声称**无改善/无差异** | `no improvement`、`no gain`、`no significant difference`、`fails to improve`、`does not improve`、`without improvement`、`on par with`、`comparable to` |
| `None` | 只陈述数值，**无方向断言** | `achieves`、`reaches`、`reports`、`obtains`、`yields` + 数值 |

`reduce/increase` 必须看宾语极性（见上表），不能再一律记 `UP`。

**已知代价（实测）**：P4 合并门槛从 **111 条降到 75 条**——36 条原先靠「reports X dB」
拿到 `LEVEL` 的主张失去方向，不再满足「subject + dataset + direction 齐全」。这是修正而非退步：
「报告了 39.18 dB」本来就不构成可合并的方向主张。

该修正先行落地（TDD）：`claims.py` 的方向规则 + 现有断言 `LEVEL` 的测试更新 + P4 spec 加注。
不改 `identity_key` 结构，只改取值与判定。

## 5. 级联

`assess_pair(a, b) -> ContradictionAssessment | None`，**按顺序首个命中即定论**：

| # | 条件 | 结论 | confidence |
|---|---|---|---|
| 1 | 任一方缺 dataset 或 metric | **跳过**，按原因计数 | — |
| 2 | dataset 集合不相等 | 方向相同 → `COMPLEMENTARY`；否则 `SCOPE_DIFFERENCE` | MEDIUM |
| 3 | 双方 conditions 非空且不相等 | 同上 | MEDIUM |
| 4 | metric 集合无交集 | `EXPERIMENTAL_INCOMPATIBILITY` | MEDIUM |
| 5 | 任一方 conditions 为空 | `INSUFFICIENT_EVIDENCE`（无法证实设置一致） | LOW |
| 6 | 任一方 direction 为 `None` | `INSUFFICIENT_EVIDENCE` | LOW |
| 7 | direction 对立（`UP`↔`LEVEL`、`UP`↔`DOWN`、`DOWN`↔`LEVEL`） | `TRUE_CONTRADICTION` | DISPUTED |
| 8 | direction 相同，双方都有数值且不同 | `EXPERIMENTAL_INCOMPATIBILITY`（同设置报不同数值，说明设置其实不同） | MEDIUM |
| 9 | direction 相同，一方无数值 | `INSUFFICIENT_EVIDENCE` | LOW |
| 10 | direction 相同，数值也相同 | **跳过**（P4 应已合并，理论不可达；命中即为缺陷，记事件） | — |

第 2、3 步的「方向相同」要求**两个方向都非空**：缺失一律 `SCOPE_DIFFERENCE`（范围不同本身成立，
不需要方向作证）。

`explanation` 必须点明哪一维、带原始值：

```text
dataset differs: rain100h vs sidd
conditions differ: backbone=cnn vs backbone=transformer
conditions not extracted on either side; setup cannot be confirmed
metric has no overlap: psnr vs lpip
direction not stated on side B: "Restormer achieves 39.18 dB on SIDD"
same scope, opposite direction: UP vs LEVEL
same scope, same direction, different values: psnr=39.18 vs psnr=38.50
```

不允许「模型认为」「可能」。输出按 `relationship`（真矛盾 → 实验不兼容 → 范围差异 → 互补 →
证据不足）再按 `(claim_a_id, claim_b_id)` 排序，保证两次运行 memo 段逐字节相同。

## 6. 组件、落库与追溯

**模块**：`src/research_os/research/contradiction.py`

```text
pair_candidates(claims) -> (list[tuple[Claim, Claim]], PairingStats)
assess_pair(a, b) -> ContradictionAssessment | None
ContradictionAssessor (Protocol) -> assess(claims) -> ContradictionResult
HeuristicContradictionAssessor
ContradictionResult: assessments / stats
PairingStats: total_before_cap, evaluated, skipped{missing_dataset, missing_metric,
              self_prefilter, cap_truncated}, emitted_by_type
```

**落库**（现有 `contradiction_assessments` 表补齐三件事）：

1. **唯一约束** `(claim_a_id, claim_b_id)`：幂等 DDL（`CREATE UNIQUE INDEX IF NOT EXISTS`），
   与既有 `_ADDED_COLUMNS` 迁移风格一致，不引入 Alembic。
2. **跨 run 校验**：两条 claim 的 `run_id` 必须存在且相等，且等于当前 run；否则拒收并记
   `FAILURE`（`reason=cross_run_pair`）。claim 不带 `source_version_id`，文档归属一律经
   `ClaimEvidenceRelation → Evidence.source_version_id` 追溯，不新增列。
3. **重复运行幂等**：按 `run_id` 先删后写（`DELETE` where claim in run），事件记录 `replaced` 数。
   同一输入两次运行结果逐条相同。

**追溯链**：`claim → relations → evidence → chunk`，memo 每条 assessment 渲染双方主张文本 +
证据位置（`sv_xxx · section · chars a-b`）。`SUPPORTED` 主张必有证据，缺失即缺陷，渲染
`no locatable evidence` 并记事件，不静默。

**编排**：supervisor 在 `claims → relations` 之后、memo 之前调用；任务用现成
`TaskType.CHECK_CONTRADICTION`；新增 `EventType.CONTRADICTION_ASSESSED`，payload 含五类计数、
跳过分解、`total_before_cap / evaluated / coverage`、`replaced`。

**memo**：`# Contradictions and Open Questions` 分节，顺序固定；每节首行写规模与覆盖率：

```text
Assessed 1063 of 1063 candidate pairs (100%). Skipped: 0 missing dataset,
0 missing metric, 0 self-pair prefilter, 0 truncated by cap.

## True contradictions (0)
## Experimental incompatibilities (n)
## Scope differences (n)
## Complementary findings (n)   # 按 subject 折叠为一行
## Insufficient evidence (n)
```

无判定时写 `No comparable claim pair in this run.`，不留空段。

## 7. 错误处理

| 情况 | 处置 |
|---|---|
| claim 集为空 / 无可配对 | 不报错；memo 写明；事件 0 |
| 单对判定异常 | 捕获 → `FAILURE` → 继续其余对；该对不落库 |
| 超过 `MAX_PAIRS` | 截断（按 id 序），事件报 `total_before_cap`、`evaluated`、`coverage` |
| 跨 run 配对 | 拒收 + 事件；不计入任何类型计数 |
| 同一对重复 | 唯一索引兜底；落库前按 `(a, b)` 去重 |
| 第 10 步命中（同值同向） | 说明 P4 合并漏了，记 `FAILURE`，不产出 assessment |
| 历史 run 旧数据 | `list_by_run` 只取本 run；跨 run 不可见 |

## 8. 明确不做

- LLM 参与判定或写解释（P8 作对照基线时再引入）。
- 数值大小作为矛盾类型：`39.18` vs `38.50` 只在同 scope 同方向时记 `EXPERIMENTAL_INCOMPATIBILITY`，
  不判「谁对」。
- 跨指标换算、跨数据集数值比较。
- 代词消解、表格解析（dataset 覆盖率的独立技术债，architect 限制 11）。
- 修改 claim 状态/置信度/identity（D8）。
- memo 结构重排（属 P6）。

## 9. 验收

**夹具与标注**

1. fixture ≥ 24 对：真实语料配对 ≥ 12 对 + 构造补齐，五类全覆盖。
2. **两轮独立标注**：第二轮不看首轮标签重新标注，报一致率与逐条分歧；分歧由人工裁决并记入
   fixture 的 `notes`。构造样本必须注明「为覆盖该类而造」，不得混入真实子集统计。
3. 报告口径分开：**真实子集 / 构造子集 / 合计** 三组，各自给混淆矩阵（5×5）。
4. **`TRUE_CONTRADICTION` 单独报 precision 与 recall**；总准确率 ≥85% 只作下限，不作唯一指标——
   类别不均衡时「全判 SCOPE_DIFFERENCE」也能拿到高分。

**语义**

5. 「提升 PSNR」vs「报告 PSNR 为 30 dB」→ **不得**为 `TRUE_CONTRADICTION`（前者 `UP`，后者 `None`
   → `INSUFFICIENT_EVIDENCE`）。
6. §17 范例（spatial conditioning，Rain100H/Transformer vs SIDD/CNN，方向对立）→ `SCOPE_DIFFERENCE`。
7. 同 subject 同 dataset 同 metric、方向对立、**conditions 双方空** → `INSUFFICIENT_EVIDENCE`，
   不得判真矛盾；双方 conditions 显式相等时 → `TRUE_CONTRADICTION` + `DISPUTED`。
8. `COMPLEMENTARY` 只在**范围不同且方向相同**时产出；同范围同方向不产出互补。
9. 跨文档 `self@` 不产出 assessment；同文档 `self@` 与具名对适用同一门槛。
10. `reduces error` → `UP`；`reduces PSNR` → `DOWN`；`reports 39.18 dB` → `None`；
    `no improvement` → `LEVEL`。

**工程**

11. 统计口径完整：`total_before_cap / evaluated / coverage` 与跳过分解出现在事件与 memo 中。
12. 落库幂等：同一 run 跑两次，assessment 条数与内容逐条相同，`replaced` 数可查。
13. 跨 run 配对被拒收并记事件。
14. P5 跑完后 claim 的 `status` / `confidence_label` 与跑之前逐条相等。
15. 留出集 20 篇跑通，报告五类分布与覆盖率。

**关于真实语料的诚实结论**

16. 按 2.1/2.2 的实测（conditions 覆盖率 2.6%，显式反向表述 13/1063），真实语料上
    `TRUE_CONTRADICTION` **预期为 0**。此时规格要求：明确写「该类召回无法在真实语料上验证，
    仅由构造夹具覆盖」，**不得**为凑出非零结果放松 D5 的条件门槛。
17. `pytest` 全绿；现有 163 条测试中因 direction 语义变更需要更新的断言，
    必须在计划里逐条列出并说明理由，不得静默改断言。

## 10. 已知限制

1. `conditions` 抽取只覆盖 3 类模式、覆盖率 2.6%，因此真矛盾门槛在真实语料上几乎不可能满足；
   本阶段的可信度建立在「不轻易断言矛盾」，不是「能找出矛盾」。
2. direction 修正后，`reports/achieves` 类主张不再有方向，P4 合并门槛从 111 降到 75。
3. 具名 subject 抽取存在误报（`db` 出现在 9 篇文档），会让不相关主张进同一组；判定仍要求
   dataset/指标一致，不会凭空造矛盾，但会产生无意义的 `COMPLEMENTARY`。
4. `reduce/increase` 的宾语极性靠词表判断，`reduces the gap`、`reduces artifacts while improving
   fidelity` 这类复合句仍可能判错方向。
5. 同 scope 同方向但数值不同的两条主张记为 `EXPERIMENTAL_INCOMPATIBILITY`，不区分「复现失败」
   与「设置不同」——两者在当前信息下不可分辨。
6. 真实语料无真矛盾，因此该类的召回率**在本阶段无法验证**，只能由构造夹具保证规则正确性。
