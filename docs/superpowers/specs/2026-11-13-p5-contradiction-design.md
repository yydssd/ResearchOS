# P5 — Contradiction Analysis · 设计规格

- **日期**：2026-11-13（W3 / Day 5）
- **对应计划**：§17（Phase 5 — Contradiction Analysis），受 §2.2 可追溯、§25 失败模型约束
- **前置状态**：P0 ✅、P1 ✅、P2 ✅、P3 ✅、P4 ✅（163 tests，tag `w3-p4.1`）
- **范围**：主张对之间的矛盾判定与呈现，含三处 **P4 前置修正**（direction 语义、conditions 扩充、
  subject 单位词误抽）。不做 P6 memo 结构重排、P7 反证搜索。

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

计划 §17 的硬约束：**默认结果不得是 `TRUE_CONTRADICTION`**。本规格把它实现为
「只有范围被**证实**相同、方向被**证实**对立时才升级为真矛盾」——不是靠顺序把结果压下去，
而是靠证据门槛让它很少成立。§2.5 给出了这个门槛的实测可达性。

## 2. 实测：现有标签不足以支撑判定

**样本**：P4 留出集 20 篇未见论文，1063 条 SUPPORTED 且带 `identity_key` 的主张。

### 2.1 direction 的语义错误（必须先修）

| 现象 | 数字 | 后果 |
|---|---|---|
| `LEVEL` 主张命中 `achiev/reach/report` | **196 / 196** | 当前 `LEVEL` 全部是「报告了一个数值」，没有一条是「明确说无改善」。`UP vs LEVEL` 不是对立 |
| `UP` 主张含 `reduce/increase` | **150 / 491** | 方向有歧义：`reduces error` 变好，`reduces PSNR` 变坏 |
| 含明确「无改善/变差」表述的主张 | **13 / 1063** | 真正可用的反向信号极少 |

现有实现（`research/claims.py`）：`DIRECTION_UP` = `improv|gain|outperform|better|surpass|exceed|reduce|increase`；
`DIRECTION_LEVEL` = `achiev|reach|report`。「提高 PSNR」与「报告 PSNR 为 30 dB」可以同时成立，
把它们判为对立是语义错误。

### 2.2 conditions 几乎抽不到，且条件写在章节而非句子

| 现象 | 数字 |
|---|---|
| 现有 conditions 覆盖率（单句） | **28 / 1063（2.6%）** |
| 其中 `setting` / `granularity` / `backbone` | 26 / 2 / 1 |
| 具名对里「双方 conditions 都非空且相等」 | **1 对** |
| 具名对里「至少一方为空」 | **1046 / 1047** |

按 §4.2 扩充四类模式后，单句覆盖率升到 143 条（13.4%）：
`backbone` 60 / `degradation` 56 / `baseline` 19 / `training` 13。

但真正的跃迁来自**块级继承**（P4 已在 task/dataset 上验证过这条路）：条件通常写在实验节标题或
该节首个点名句，而不在每条主张的句子里。

| conditions 来源 | 覆盖主张 | 占比 |
|---|---|---|
| 仅单句 | 143 | 13.4% |
| + 章节标题 | 138（本轮统计口径略窄） | 13.0% |
| **+ 节内首个点名句** | **684** | **64.3%** |

因此 §4.2 采用三级继承，并记录 **provenance**（`sentence` / `heading` / `section-first-mention`）。
继承来的条件必须能被读者看出是继承的——否则又是一次「用沉默当证据」。

### 2.3 subject 把单位词当方法名（顺带修）

`dB` 里的大写 `B` 触发「内部有大写即专名」规则，于是 `db` 成为跨 **9 篇文档**、15 条主张的假方法名
（`... improvement is over 55 dB on dehazing` → `subject=db`）。它是留出集里跨文档重复最多的
"具名主语"，直接污染配对与统计，必须在 P5 之前修掉。

### 2.4 配对规模

| 配对规则 | 组数 | 候选对 | 跨文档对 |
|---|---|---|---|
| 同 subject + 同 task（具名） | 99 | **1047** | **137** |
| 同 task + dataset 相等 | 19 | 1471 | 772 |
| 仅同 task | 5 | 425220 | 395015 |

同文档 `self@` 对需预处理：

| 预处理 | 剩余对 |
|---|---|
| 无 | 6177 |
| 双方都有 dataset | 148 |
| **双方都有 dataset 与 metric（采用）** | **16** |
| 再加双方都有 direction | 9 |

采用 16 这一档，与级联第 1 步的跳过条件一致。**合计候选对 1047 + 16 = 1063 对 / 20 篇**。

### 2.5 真矛盾为什么不可达：语料里没有负向主张

按 §5 的严格门槛逐层收窄（已用四值 direction 与「dataset 非空」重算）：

| 收窄条件 | 仅单句 conditions | 块级继承 conditions |
|---|---|---|
| 具名对（同 subject + 同 task，双方 dataset 非空） | 1047 | 1047 |
| + 双方都抽到 conditions | 3 | 67 |
| + 两侧 conditions 相等 | 2 | 30 |
| + **方向对立** | **0** | **0** |
| + dataset 相等且 metric 有交集 | 0 | 0 |

**根因不是 conditions，是方向**：1063 条主张里只有 **2 条 `LEVEL` + 16 条 `DOWN`**（合计 1.7%），
其余全部在报告提升。论文的写作习惯决定它很少写「某方法没有改善」；负向结果集中在消融
（「去掉 X 会变差」），而那时主语是本文自己的组件，构不成跨方法对立。

> 过程记录：一次中间统计曾得出「4 对可达」，复核后是探针自身的两个缺陷——用了旧的
> `direction` 标签（`achieves the best` 被判 `LEVEL`，新语义应为 `None`），且把「双方 dataset
> 都为空」当成相等。修正后为 0。这类偏差正是 §9 要求分层报告的原因。

**结论**：`TRUE_CONTRADICTION` 在本语料上结构性不可达，扩充 conditions 与继承人条件都改变不了。
本阶段不放松门槛（§9 #16），该类型的正确性只能由构造夹具验证；其真实召回要等语料里出现
「复现/再评估」类论文（属 P2 发现层策略，不在 P5 范围内）。

## 3. 设计决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 判定引擎**纯确定性级联**，零 LLM | 与 P4 一致（ADR-020~025）；可复现；LLM 版留给 P8 作对照 |
| D2 | 配对键 = **同 task + subject 可比**，不要求 dataset 相同 | §17 范例的两条主张数据集不同，若要求数据集有交集则范例永不成立 |
| D3 | 跨文档 `self@` 不配对；同文档 `self@` 配对但**无判定特权** | 两个 `self@` 是不同方法；同源也不能证明设置一致 |
| D4 | **修 direction 语义**（§4.1）：`achiev/reach/report` → `None`，`LEVEL` 只留明确无改善，`reduce/increase` 看宾语极性 | 196/196 的 `LEVEL` 是数值陈述 |
| D5 | **扩充 conditions** 到 backbone / degradation / baseline / training 四类，并允许**块级继承**（句 → 章节标题 → 节内首个点名句），继承必须带 provenance | 单句覆盖率 2.6% → 13.4%，继承后 → 64.3%；条件写在实验节而不是每条句子里 |
| D6 | **修 subject 单位词**（§4.3）：`dB`、指标名、单位不得成为 subject | `db` 跨 9 篇文档，会制造大量假配对 |
| D7 | `TRUE_CONTRADICTION` 需**范围被证实相同**：dataset 相等、双方 conditions 非空且相等、metric 有交集、方向对立 | 空 conditions ≠ 相同；缺失不得当证据用 |
| D8 | `COMPLEMENTARY` = **范围不同但方向相同**（互补发现），confidence `MEDIUM` | 「同方向」只说明不冲突；互补的语义是「在不同条件下都成立」 |
| D9 | `confidence_label` 是来源标注，不是打分；`COMPLEMENTARY` 最高 `MEDIUM` | 条件抽取不全，任何「一致」判断都带不确定性 |
| D10 | P5 **不修改** claim 的 `status` / `confidence_label` | P4 状态语义刚钉死（ADR-022） |
| D11 | 统计必须报**截断前总量、已评估量、覆盖率**，跳过按原因分解 | 否则「没发现矛盾」会被误读为「不存在矛盾」 |
| D12 | 落库补**唯一约束与跨 run 校验**，重复运行幂等 | 现有表无唯一约束；跨 run 配对会污染审计链（ADR-019） |
| D13 | 结论依赖**继承条件**时 confidence 降一级（`MEDIUM`→`LOW`），`explanation` 注明 provenance | 继承条件弱于句子明写；不能与显式条件同等对待 |
| D14 | P5 的产出定位为**可比性判定**，不是"矛盾发现器"；真实语料上真矛盾为 0 属预期 | 语料只有 1.7% 负向主张（§2.5），把"找不到矛盾"当成失败会诱导放松门槛 |

## 4. 前置修正（P4 amendment，先行落地）

三项都要求 TDD：先写失败测试，再改实现；现有 163 条测试中受影响的断言逐条列出理由，不得静默改。

### 4.1 direction 四值语义

| 值 | 含义 | 触发 |
|---|---|---|
| `UP` | 明确声称**变好** | `improves`、`gains`、`outperforms`、`surpasses`、`better than`、`exceeds`；`reduces error/loss/noise/artifact/complexity`；`increases PSNR/SSIM/accuracy/performance` |
| `DOWN` | 明确声称**变差** | `degrades`、`drops`、`worse than`、`hurts`、`fails on`；`reduces PSNR/SSIM/accuracy/performance`；`increases error/loss/noise` |
| `LEVEL` | 明确声称**无改善/无差异** | `no improvement`、`no gain`、`no significant difference`、`fails to improve`、`does not improve`、`without improvement`、`on par with`、`comparable to` |
| `None` | 只陈述数值，**无方向断言** | `achieves`、`reaches`、`reports`、`obtains`、`yields` + 数值；以及无法判定极性的 `reduce/increase` |

`reduce/increase` 必须看宾语极性，不能再一律记 `UP`。判定优先级：`LEVEL` → `DOWN` → `UP` → `None`
（否定式优先，避免 `fails to improve` 被 `improve` 抢先判成 `UP`）。

**实测取值变化**：`UP 491/LEVEL 196/None 376` → **`UP 369 / DOWN 16 / LEVEL 2 / None 676`**。
`None` 大幅上升是回归到真实情况：六成主张只是陈述数值。

**对 P4 的代价（接受）**：合并门槛（subject + dataset + direction 齐全）从 **111 条降到 71 条**。
「报告了 39.18 dB」本来就不该是可合并的方向主张。

### 4.2 conditions 四类扩充

| 类别 | 抽取规则 | 取值示例 |
|---|---|---|
| `backbone` | `transformer(s)` / `cnn(s)` / `convolutional` / `convnet` / `mamba` / `u-net` / `diffusion` | `backbone=transformer` |
| `degradation` | `noise level N`、`level N`、`sigma=N`、`heavy/light rain`、`dense/thick haze`、`severe/mild/moderate` | `degradation=25`、`degradation=heavy` |
| `baseline` | `compared with/to X`、`over X`（X 为首字母大写专名） | `baseline=mprnet` |
| `training` | `from scratch`、`pretrained`、`finetuned` | `training=from-scratch` |

规则：每类**最多取一个值**（首个命中）；值小写归一；同一主张可命中多类，按类别名排序拼接。
不推断、不填默认值——抽不到就是没有。

**三级继承**（与 P4 的 task/dataset 继承同一机制，ADR-020/024）：

| 优先级 | 来源 | provenance |
|---|---|---|
| 1 | 主张所在句子 | `sentence` |
| 2 | 该块所属章节标题 | `heading` |
| 3 | 该节首个命中条件的块（只取首个，避免整节并集把多设置混在一起） | `section-first-mention` |

`provenance` 不进入 `identity_key`（与 `subject_inferred` 同理：是来源信息，不是身份），
但必须随 claim 落库并在 memo 与 `inspect-claim` 中显示。继承条件参与判定时 confidence 降一级（D13）。

**实测覆盖率**：单句 `28/1063（2.6%）` → 四类模式 `143（13.4%）` → 加继承 **`684（64.3%）`**。
四类分别为 60 / 56 / 19 / 13 条。

**对 P4 的影响**：conditions 参与 `identity_key`，条件变多会让键更容易不同，
同键合并更保守。这符合「范围更精确才允许合并」的方向，但需在计划中量化前后合并数。

### 4.3 subject 单位词与指标名过滤

`METRICS` 与单位词（`dB`、`%`、`×`）加入 subject 的停用集；`dB` 之所以被抽中，是因为
「token 内部有大写即视为专名」的规则对 `dB` 成立。修法：在 `_subject()` 的跳过条件里加入
单位词与指标名（大小写不敏感）。

验收：`... over 55 dB on dehazing` → `subject` 不得为 `db`。

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
| 7 | direction 对立（`UP`↔`LEVEL`、`UP`↔`DOWN`、`DOWN`↔`LEVEL`） | `TRUE_CONTRADICTION` | DISPUTED（任一侧条件为继承时 LOW） |
| 8 | direction 相同，双方都有数值且不同 | `EXPERIMENTAL_INCOMPATIBILITY` | MEDIUM |
| 9 | direction 相同，一方无数值 | `INSUFFICIENT_EVIDENCE` | LOW |
| 10 | direction 相同，数值也相同 | **跳过**（P4 应已合并；命中即缺陷，记事件） | — |

第 2、3 步的「方向相同」要求**两个方向都非空**；缺失一律 `SCOPE_DIFFERENCE`（范围不同本身成立，
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
2. **跨 run 校验**：两条 claim 的 `run_id` 必须存在、相等且等于当前 run；否则拒收并记
   `FAILURE`（`reason=cross_run_pair`）。claim 不带 `source_version_id`，文档归属一律经
   `ClaimEvidenceRelation → Evidence.source_version_id` 追溯，不新增列。
3. **重复运行幂等**：按 `run_id` 先删后写，事件记录 `replaced` 数；同一输入两次运行结果逐条相同。

**追溯链**：`claim → relations → evidence → chunk`，memo 每条 assessment 渲染双方主张文本 +
证据位置（`sv_xxx · section · chars a-b`）。`SUPPORTED` 主张必有证据；缺失即缺陷，渲染
`no locatable evidence` 并记事件，不静默。

**编排**：supervisor 在 `claims → relations` 之后、memo 之前调用；任务用现成
`TaskType.CHECK_CONTRADICTION`；新增 `EventType.CONTRADICTION_ASSESSED`，payload 含五类计数、
跳过分解、`total_before_cap / evaluated / coverage`、`replaced`。

**memo**：`# Contradictions and Open Questions` 分节，顺序固定；首行报规模与覆盖率：

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
| 超过 `MAX_PAIRS`（50000） | 截断（按 id 序），事件报 `total_before_cap`、`evaluated`、`coverage` |
| 跨 run 配对 | 拒收 + 事件；不计入任何类型计数 |
| 同一对重复 | 唯一索引兜底；落库前按 `(a, b)` 去重 |
| 第 10 步命中 | 说明 P4 合并漏了，记 `FAILURE`，不产出 assessment |
| 历史 run 旧数据 | `list_by_run` 只取本 run；跨 run 不可见 |

## 8. 明确不做

- LLM 参与判定或写解释（P8 作对照基线时再引入）。
- 数值大小作为矛盾类型：同 scope 同方向不同数值只记 `EXPERIMENTAL_INCOMPATIBILITY`，不判「谁对」。
- 跨指标换算、跨数据集数值比较。
- 代词消解、表格解析（dataset 覆盖率的独立技术债，architect 限制 11）。
- 修改 claim 状态/置信度/identity（D10）。
- memo 结构重排（属 P6）。

## 9. 验收

**夹具与标注**

1. fixture ≥ 24 对：真实语料配对 ≥ 12 对 + 构造补齐，五类全覆盖。
2. **两轮独立标注**：第二轮不看首轮标签重新标注，报一致率与逐条分歧；分歧由人工裁决并记入
   fixture `notes`。构造样本必须注明「为覆盖该类而造」，不得混入真实子集统计。
3. 报告口径分开：**真实子集 / 构造子集 / 合计** 三组，各自给 5×5 混淆矩阵。
4. **`TRUE_CONTRADICTION` 单独报 precision 与 recall**；总准确率 ≥85% 只作下限——类别不均衡时
   「全判 SCOPE_DIFFERENCE」也能拿高分。

**语义**

5. 「提升 PSNR」vs「报告 PSNR 为 30 dB」→ **不得**为 `TRUE_CONTRADICTION`（前者 `UP`，后者 `None`
   → `INSUFFICIENT_EVIDENCE`）。
5b. 条件来自继承时，结论的 confidence 比显式条件低一级，且 `explanation` 必须写出
   provenance（如 `conditions inherited from section: backbone=transformer`）。
6. §17 范例（spatial conditioning，Rain100H/Transformer vs SIDD/CNN，方向对立）→ `SCOPE_DIFFERENCE`。
7. 同 subject 同 dataset 同 metric、方向对立、**conditions 双方空** → `INSUFFICIENT_EVIDENCE`；
   双方 conditions 显式相等 → `TRUE_CONTRADICTION` + `DISPUTED`。
8. `COMPLEMENTARY` 只在**范围不同且方向相同**时产出；同范围同方向不产出任何 assessment。
9. 跨文档 `self@` 不产出 assessment；同文档 `self@` 与具名对适用同一门槛。

**direction 与 conditions（前置修正）**

10. `reduces error` → `UP`；`reduces PSNR` → `DOWN`；`reports 39.18 dB` → `None`；
    `no improvement` → `LEVEL`；`fails to improve` → `LEVEL`（否定式优先于 `improve`）。
11. conditions：`Transformer-based` → `backbone=transformer`；`noise level 25` → `degradation=25`；
    `compared with MPRNet` → `baseline=mprnet`；`trained from scratch` → `training=from-scratch`。
12. `... over 55 dB on dehazing` → subject 不得为 `db`；`PSNR`/`SSIM`/`dB`/`%` 不得成为 subject。

**工程**

13. 统计口径完整：`total_before_cap / evaluated / coverage` 与跳过分解出现在事件与 memo 中。
14. 落库幂等：同一 run 跑两次，assessment 条数与内容逐条相同，`replaced` 数可查。
15. 跨 run 配对被拒收并记事件；P5 跑完后 claim 的 `status` / `confidence_label` 与跑前逐条相等。
16. 留出集 20 篇跑通，报五类分布与覆盖率。**按 §2.5，真矛盾预期为 0**：报告必须写明
    「该类召回无法在真实语料上验证，仅由构造夹具覆盖」，并给出原因（负向主张仅 1.7%）。
    **不得**为凑非零结果放松 D7 的门槛，也不得通过扩大 subject 匹配范围去制造对立。
17. `pytest` 全绿；因 §4 三项修正需要更新的既有断言，必须在计划中逐条列出并说明理由。

## 10. 已知限制

1. 真矛盾在真实语料上结构性不可达（§2.5）：语料中 98.3% 的主张都在报告提升，只有 2 条
   `LEVEL` + 16 条 `DOWN`，方向对立对为 0。这与 conditions 覆盖率无关，扩充与继承都不改变它。
   本阶段的可信度建立在「不轻易断言矛盾」，不是「能找出矛盾」。
2. direction 修正后六成主张无方向（`None`），P4 合并门槛从 111 降到 71。
3. 具名 subject 仍有误抽风险：`dB` 已修，但缩写、模型代号（`MIRNet` 与 `MIRNet-v2`）仍可能被当成
   同一或不同 subject。
4. `reduce/increase` 的宾语极性靠词表，`reduces the gap`、`reduces artifacts while improving
   fidelity` 这类复合句仍可能判错。
5. 同 scope 同方向但数值不同记为 `EXPERIMENTAL_INCOMPATIBILITY`，不区分「复现失败」与「设置不同」。
6. `baseline` 作为条件只取 1 个对照名，多基线主张（`vs MPRNet and Restormer`）会被简化。
7. 真矛盾召回在本阶段**无法用真实语料验证**，只能由构造夹具保证规则正确性。要让该类型在真实
   语料上出现，需要发现层引入"复现/再评估/基准研究"类论文（属 P2 策略），不是判定层能解决的。
8. 块级继承的条件可能与该节内其他实验不符（同一节常并列多个设置）；`provenance` + 降一级
   confidence 是缓解手段，不是消除手段。
