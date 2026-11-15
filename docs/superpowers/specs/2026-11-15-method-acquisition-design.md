# 方法获取能力实现设计（2026-11-15）

> 背景：`docs/evaluation/2026-11-14-method-acquisition-audit.md` 在 40 篇留出集上实测出
> **L1 方法身份 0/20、L3 方法描述 0/20**（两个领域都是 0），L2 为 19/20 与 10/20，
> L4 为 11/19 与 14/20，缺口合计 105 = 159 − 54。审计脚本只度量、不修复；
> 本文设计**补上这四层的抽取能力**，是那条度量线的后续实施。
>
> 与上一份 spec 的关系：`2026-11-14-method-acquisition-measurement-design.md` §7
> 「明确不做」列出了「不扩词表、不引入 LLM、不改 `identity_key`」。本文**正是**
> 解禁这三条，逐条给出理由，不是遗忘。

## 0. 决策记录

| 项 | 结论 | 来源 |
|---|---|---|
| 抽取机制 | **分层混合**：L1 名字、L2 组件、L4 设置走确定性；**只有 L3 描述**走 LLM（1 次/篇） | 用户 2026-11-15 确认 |
| 方法身份与 `identity_key` | **独立实体**，不进 identity；`subject` 仍为 `self@<source_version_id>` | 用户 2026-11-15 确认 |
| P4 的 model scale / evaluation protocol | **接进 `conditions` 并进 `identity_key`**，接受合并行为改变；必须做 before/after 对照并双份登记 | 用户 2026-11-15 确认 |
| L3 存储形态 | **结构化要点** `list[{aspect, statement, quote, chunk_id}]`，不是自由散文 | 用户 2026-11-15 确认 |

## 1. 计划依据

| 位置 | 要求 | 本文的落点 |
|---|---|---|
| §15 / P3（`md:841-856`） | `QuantitativeEvidence` 必须有 `method: str \| None`（`md:847`）与 `protocol: str \| None`（`md:853`），理由「avoid invalid cross-paper comparisons」（`md:856`） | §5.3 修 `protocol` 语义；§4.1 让 `method` 写真名；§6.1 `unit` 拆列 |
| §16 / P4（`md:864-885`） | 主张不得因措辞相近合并，须区分 7 维：dataset · task · metric · architecture · training setup · **model scale**（`md:880`）· **evaluation protocol**（`md:881`） | §5.1 新增 `scale=` 与 `protocol=` 两种条件 |
| §2.5（`md:168-192`） | 确定性 9 项 vs LLM 语义判断 7 项，其中含 `evidence extraction`、`claim normalization`、`scope comparison`（`md:184-192`） | §4 分层依据：只有 L3 落在「semantic judgment」 |
| §7.4（`md:475`） | 「Never store only an LLM-generated summary without source location」 | §4.4 `quote` 必须逐字可定位，否则丢弃 |
| §8（`md:570`） | `official repository > paper description` 的权威层次 | §4.3 `repository` 单独成型并标注为最高权威来源 |
| §17（`md:1171`） | `max_llm_calls: 80` | §7.2 每篇 1 次，20 篇留出集 20 次，在预算内 |
| §7.5（`md:488`） | `Claim.conditions: list[str]` | §5.1 两种新条件仍走该字段，不新增列 |
| §1.2 不变量 | `结论 → 主张 → 证据 → 来源位置`，链断即标 unsupported | §4.4 与 §7.4 的 `missing_layers` 是该不变量在方法层的具体化 |

## 2. 度量给出的起点（不是结论）

| 层 | 图像复原 | Agent in MC | 系统侧为何是这个数 |
|---|---|---|---|
| L1 方法身份 | `C = 0/20` | `C = 0/20` | `QuantitativeEvidence.method` 恒为常量 `"proposed method"`，不是真名 |
| L2 方法构成 | `C = 19/20` | `C = 10/20` | 靠 `conditions` 的 `backbone=` / `baseline=` 蹭到，不是真组件 |
| L3 方法描述 | 结构性缺失 | 结构性缺失 | **全文任何模型都没有可存描述的位置** |
| L4 可复现设置 | `C = 11/19` | `C = 14/20` | 只靠 `training=` 一个槽 |

两点必须说清楚，否则本文的验收会被误读：

- L2/L4 的分数是**蹭到的**，不是抽得好。它们靠的是条件字段的副产品。
- L1/L3 的 0 **不是抽错，是没地方存**。所以本文的第一动作是加落点，不是调正则。

## 3. 数据模型

### 3.1 三个新模型（`domain/models.py`）

```python
class MethodPoint(BaseModel):
    aspect: Literal["goal", "mechanism", "why_it_works", "io"]
    statement: str          # 一句话，≤200 字符
    quote: str              # 必须能在声明的 chunk 里逐字找到
    chunk_id: str

class MethodSetup(BaseModel):
    scale: str | None = None          # "7b" / "34m params" / "8xa100"
    protocol: str | None = None       # "zero-shot" / "5-shot" / "pass@1"
    hyperparameters: list[str] = []   # "lr=3e-4" / "batch=32" / "epochs=100"
    repository: str | None = None     # 官方仓库 URL

class MethodProfile(BaseModel):
    source_version_id: str
    name: str | None = None
    aliases: list[str] = []
    name_quote: str | None = None
    components: list[str] = []
    setup: MethodSetup = MethodSetup()
    points: list[MethodPoint] = []
    missing_layers: list[str] = []    # 子集 of {"L1","L2","L3","L4"}
```

`missing_layers` 是刻意设计的：让「这篇的 L3 没拿到」变成**落库的事实**，而不是一次
静默的空列表。上一轮的问题正是「空」和「抽到但是空」在数据里长得一模一样。

### 3.2 为什么不在 `Claim` 上加外键

`Claim` 没有 `source_version_id`，但它通过 `ClaimEvidenceRelation → Evidence.source_version_id`
已经能到达来源。再加一列 `method_profile_id` 就是同一事实存两份，两份会漂移。
「主张挂上方法」由查询层按 `source_version_id` 解析，`Claim` 一个字段都不改。

**代价要写明，不能含糊**：`supervisor.py:384` 的
`self._builder.build(evidence, quantitative=facts, chunks=all_chunks)` 是**一次性传入
全部来源**的 evidence，而 `claims.py` 的 `_subject()` 对第三方方法名**不做
source-version 绑定**（只有 `self` 会变成 `self@<svid>`）。因此两条来自不同论文、
都写「Restormer improves Rain100H PSNR」的句子，`identity_key` 完全相同，会被合并成
**一条主张、证据跨两篇**。

所以归因的返回值是**集合**，不是单个 profile：

- 证据只涉及 1 个 source version → 归到该 profile，正常渲染。
- 证据涉及 >1 个 source version → 该主张标记 `multi_source`，**不归到任何单个方法**，
  memo 里显示「多来源主张，未归因」，并计入事件 payload。

「取第一个」或「取多数」都是错的：那会把一篇论文的方法名安到另一篇的结论上，
正是「用不可靠信号替代证据」。跨来源主张的实际条数**由实现后实测得出**，
不在此处预设（见 §10 重测清单）。

### 3.3 不新增 `Claim`/`ClaimIdentity` 字段

`identity_key` 仍是 7 段。§5 只往第 6 段（`conditions`）里加两种新条件值，段数不变、
解析逻辑不变。

## 4. 抽取策略

### 4.1 L1 方法名（确定性，宁可 None 不猜）

**只接受显式命名句式**：

- `we (propose|introduce|present|call) (it )?X`
- `our (method|approach|model|framework|system)[,]? (called|named|dubbed)? X`
- `X, (our|the) (proposed )?(method|approach)`
- 标题/摘要中 `this (paper|work) (proposes|presents|introduces) X`

候选必须通过现有四道排除（`COMMON_CAPS`、`DATASETS`、`METRICS`、`NOT_A_SUBJECT`），
并且**不能是句首大写词**（沿用 `claims.py:169` 的判据：句首大写不证明专有名词）。

多个候选同时命中时，按**来源层级**取（摘要 > 引言 > 方法章 > 结论），同层取首次出现；
同层同位置仍并列则**记为 None 并输出 `METHOD_NAME_AMBIGUOUS` 事件**，不掷骰子。

无显式命名句式 → `name = None`。**不做词频猜测**：猜错的名字会经由 §5.3 污染所有
`QuantitativeEvidence.method`，空着至少是诚实的，而且 `missing_layers` 会记录它。

`aliases` 只收同一命名句式的并列形式（`X (also called Y)`），不做缩写推断。

### 4.2 L2 组件（确定性）

从方法章节抽结构名词短语：`{encoder, decoder, attention, transformer, memory, planner,
buffer, graph, gate, adapter, loss, head, tokenizer, retrieval, reward model}` +
`X (module|network|block|layer|branch|mechanism)` 形态。

选这批词的理由：它们是**结构性词汇**，在图像复原与 Minecraft agent 两类论文里
语义一致；不像 `DATASETS` 那样换域即废（上一轮 MC 归零的直接原因正是数据集词表）。

### 4.3 L4 可复现设置（确定性）

| 子项 | 抓法 | 为什么能跨域 |
|---|---|---|
| `repository` | URL 正则，限 `github.com` / `gitlab` / `huggingface.co` | 完全跨域稳定；且 §8 给了它最高权威层级 |
| `hyperparameters` | `learning rate`/`lr`/`batch size`/`epochs`/`steps`/优化器名 + 就近数值 | 机器学习论文通用 |
| `scale` | `\d+(\.\d+)?\s?[bm]\b`（参数规模）、`\d+\s?[×x]\s?(a100\|h100\|v100\|gpu)` | 大模型与 agent 论文通用 |
| `protocol` | `zero-shot`/`few-shot`/`\d+-shot`/`pass@\d`/`top-1`/`\d+ episodes`/`success rate` | 评测协议词汇跨域复用 |

### 4.4 L3 方法描述（唯一 LLM 环节）

输入：该篇方法章节的 chunks（按 `section` 匹配 `method*`/`approach*`/`architecture*`，
无匹配则退回全文前 N 个 chunk，N 由 token 预算给定并在事件里记录）。

输出契约：`MethodDescriptionResponse(points: list[MethodPoint])`。

**三道防线**，缺一不可：

1. **`quote` 必须逐字出现在该 `chunk_id` 的文本里**（去空白后子串匹配）。不满足 →
   丢弃该点，记 `METHOD_POINT_UNLOCATABLE` 事件。这是 §7.4 的可执行形式。
2. **`aspect` 必须是四个枚举值之一**；`statement` ≤200 字符。不合 schema →
   整篇丢弃，记 `METHOD_DESCRIPTION_REJECTED`，**不落半成品**。
3. **`chunk_id` 必须是本次输入里真实存在的 id**，防止 LLM 造 id。

### 4.5 模式外置

所有模式集中到 `research/patterns.py`：`GENERIC` 组恒先生效，领域组在其上叠加。
**本次不新增任何领域组**——Minecraft 词表是独立议题（见 §12），但结构先铺好，
那时只需加一个组，不必重写正则。

## 5. `identity_key` 的两个新条件维度

### 5.1 `scale=` 与 `protocol=`

`conditions.py` 的四类（backbone / degradation / baseline / training）扩为六类，
新增 `scale=` 与 `protocol=`，沿用该模块已有三条纪律：**每类最多一个值、不设默认、
值小写归一**。

### 5.2 对合并行为的影响（必须承认）

`conditions` 是 `identity_key` 第 6 段，`may_merge()` 要求 `a.key() == b.key()`。
新增两类条件后，凡命中新模式的句子其 key 改变，部分现有合并会拆开，主张数会上升。

**这是修一个真实缺陷，不是回归**，但必须按 §10 的方式度量并双份登记，
禁止只报新数字、隐去旧数字。

### 5.3 `protocol` 的语义修正

计划 `md:853` 的 `protocol` 指评测协议；实现里 `quantitative.py` 的 `_unit_near()`
把 `"dB"`/`"percent"` 写进了它。修法：

- `quantitative_evidence` 新增 `unit` 列；迁移执行 `UPDATE ... SET unit = protocol`
  后把 `protocol` 置空（下一次抽取会写真实协议）。
- `claims.py:206` 的 `row.protocol or 'unit'` 改为 `row.unit or 'unit'`。
- 该改动同样改写 `value_bucket`（第 7 段），因此与 §5.1 合并到**同一个度量周期**，
  只跑一次 before/after，不跑两次。

**本文有三处叫 `protocol`，层级不同，不得混用**：

| 位置 | 粒度 | 含义 | 谁消费 |
|---|---|---|---|
| `MethodSetup.protocol` | 论文级 | 这篇整体怎么评（zero-shot / 5-shot） | memo、profile |
| `QuantitativeEvidence.protocol` | 单行数值 | 这个数字在什么协议下取得 | `value_bucket` 不读它；P7 比对会读 |
| `conditions` 的 `protocol=` | 单句主张 | 这句主张在什么协议下成立 | `identity_key` 第 6 段 |

三者可以一致但不保证一致：一句主张可能只描述 5-shot 结果，而论文整体另有 zero-shot。
`MethodSetup.hyperparameters` **不进** `conditions`——P4 的 7 维里没有超参，
把它塞进 identity 会是凭空的合并判别维度。

## 6. 存储

### 6.1 新表

- `method_profiles`：`id`、`run_id`、`source_version_id`、`name`、`name_quote`、
  `aliases_json`、`components_json`、`setup_json`、`missing_layers_json`；
  **唯一约束 `(run_id, source_version_id)`**（理由见下）
- `method_points`：`id`、`profile_id`（外键）、`aspect`、`statement`、`quote`、`chunk_id`

`run_id` 必须在唯一键里：`SqlSourceVersionRepository.create(sv, run_id=…)` 表明同一个
source version 可以参与多次 run，只按 `source_version_id` 唯一会让第二次 run 覆盖
第一次的画像。追溯类输出一律按 `run_id` 作用域（ADR-019），这里不是例外。

`aliases`/`components`/`setup`/`missing_layers` 用 JSON 列。理由：它们是**同一条 profile
的附属属性**，从不被单独查询或 join；拆表只会增加读取往返。`points` 拆表是因为它
需要被逐条遍历和计数。

### 6.2 迁移

走既有 `database.py` 的 `_ADDED_COLUMNS` 轻量机制（新表由 `create_all` 建，
`unit` 列由 `_ADDED_COLUMNS` 补）。不引入 Alembic——plan §35 要求「没有可度量需求
就不加基础设施」，本次唯一的数据改写是 `unit` 回填，一条 `UPDATE` 足够。

### 6.3 仓库接口

`SqlMethodRepository`：`upsert(profile, run_id)`、`get(run_id, source_version_id)`、
`list_by_run(run_id)`、`profiles_for(run_id, source_version_ids)`（归因用，一次查询
解决，不在循环里逐条打库）。`upsert` 按 `(run_id, source_version_id)` 幂等，
重跑不产生重复行。

## 7. 编排

### 7.1 阶段位置（关键）

**必须插在定量抽取之前**，因为 `QuantitativeEvidence.method` 要用 L1 的名字填。
现有顺序是 `load → chunks → evidence → quantitative(371) → claims(384) → …`，
新顺序为：

```
load → chunks → 方法画像(L1/L2/L4 确定性 + L3 LLM) → evidence → quantitative → claims → …
```

`QuantitativeExtractor.extract` 增加关键字参数
`method_names: Mapping[str, str | None] | None = None`，**按 `source_version_id` 索引**，
缺省为 `{}`；`_PROPOSED_RE` 命中时写 `method = method_names.get(evidence.source_version_id)`。
必须是映射而不是单个字符串：`extract()` 同样一次性收到全部来源的 evidence，
传一个名字等于把第一篇的方法名安到所有论文头上。**同时删除常量 `"proposed method"`**。

### 7.2 预算

每篇 1 次调用。`_check_budget()` 现有逻辑够用；超预算时**不静默跳过**：
记 `METHOD_DESCRIPTION_SKIPPED`，`missing_layers` 加 `"L3"`，memo 写明「N 篇因预算未做描述」。

### 7.3 无 provider

`UnavailableProvider` 存在时（当前默认），L3 一律空，同样记
`METHOD_DESCRIPTION_SKIPPED`。**不把「没调」呈现成「调了没结果」**——这两件事在
memo 里必须能区分。

### 7.4 新失败事件

| 事件 | 触发 |
|---|---|
| `METHOD_POINT_UNLOCATABLE` | LLM 给的 `quote` 不在声明 chunk 里 |
| `METHOD_DESCRIPTION_REJECTED` | LLM 输出不合 schema / `chunk_id` 不存在 |
| `METHOD_DESCRIPTION_SKIPPED` | 无 provider 或预算耗尽 |
| `METHOD_NAME_AMBIGUOUS` | 同层同位置多个命名候选并列，记 None |

## 8. memo

新增 Methods 段，每篇一栏：

```
### <论文标题> — 方法：LangProp
- 组件：graph encoder · policy head
- 规模：7b · 8×A100
- 协议：zero-shot
- 仓库：https://github.com/...
- 做了什么（goal）：<statement> [<section>]
- 为何有效（why_it_works）：<statement> [<section>]
- 未获取：L3（无 provider）
```

`missing_layers` 必须在 memo 里显式成行。只显示拿到了什么、不显示没拿到什么，
正是上一轮「看起来 160/160 present」那类问题的同构。

跨来源主张（§3.2）单列一行计数：`多来源主张：N（未归因）`。N 为 0 时也打印，
因为「0」和「没统计」在 memo 里必须能区分。

## 9. 测试

### 9.1 单元

- 每个抽取器：正例 + **负例**（该抽不到的必须抽不到）。负例至少覆盖
  「句首大写词不是方法名」「数据集名不是方法名」「`dB` 不是方法名」三类，
  对应用户上一轮否决过的历史误判。
- `scale=`/`protocol=` **确实改变合并结果**的对照测试：构造仅在这两维不同的两句，
  断言 `may_merge() == False`。这是 P4 要求的可证伪形式，
  **「字段有值」不算通过**。

### 9.2 契约（fake provider）

- 返回不合 schema → 整篇丢弃 + `METHOD_DESCRIPTION_REJECTED`。
- 返回的 `quote` 不在 chunk 里 → 该点丢弃 + `METHOD_POINT_UNLOCATABLE`，
  同批其它合法点保留。
- 返回不存在的 `chunk_id` → 同上。

### 9.3 集成

- 一次 run 后 profile 落库、`points` 可逐条读回、memo 含 Methods 段与 `missing_layers`。
- **跨来源归因**：构造两篇各写「Restormer improves Rain100H PSNR」的源，断言合并成
  一条主张、其证据跨 2 个 source version、归因结果为 `multi_source` 而**不是**任一篇的
  方法名（§3.2 的可证伪形式）。
- 预算耗尽路径：`max_llm_calls=0` 时 run 仍完成，L3 为空且有事件。
- 重跑幂等：同 run 跑两次不产生重复 profile；**不同 run 用同一 source version
  各自留一份 profile**，互不覆盖。

### 9.4 变异锚点

删掉 §4.4 第 1 条（`quote` 逐字校验）→ 9.2 的不可定位测试**必红**。
删掉 §5.1 的 `scale`/`protocol` 规则 → 9.1 的对照测试**必红**。
不接受只断言键存在或容器非空的测试。

## 10. 验收

**不预设阈值。** 度量先行的意思是先量再定，把目标数字拍出来再让实现去够，
就是本文要避免的那种验收。

硬要求只有三条：

1. L1 与 L3 的 `covered/present` 从 **0** 起来（`present` 为 0 的格子仍记 `N/A`）。
2. L2 与 L4 任何一格**不得下降**；有下降必须解释原因或回滚该部分改动。
3. 所有数字以 `covered/present` 分数 + `present`/`covered` 绝对值 + `covered/20`
   的既有格式呈现（沿用审计报告口径），并在评估报告里**并列 before / after**。

重测清单：

| 产物 | 命令 | 期望 |
|---|---|---|
| 方法四层 | `python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json` | 逐格 before/after |
| 主张质量 | `python scripts/holdout_claim_quality.py --ids-file …` | 主张数、合并率变化 |
| 矛盾质量 | `python scripts/holdout_contradiction_quality.py --ids-file …` | 候选对、判定数变化 |

三份报告全部进 `docs/evaluation/`，旧数字**不删不改**，只在新报告里对照。

## 11. 明确不做

- **不新增领域词表**（Minecraft/agent 词表是独立议题，见 §12）。本次只做结构外置。
- 不让方法名进 `identity_key`、不改 `subject`、不改配对语义。
- 不改矛盾判定级联、不改 `coverage` 口径、不修 `SqlEventRepository.list_by_run` 的 `ORDER BY`。
- 不做第二轮独立盲标、不建 gold label、不算任何正确率。
- 不把 L2/L4 的既有分数当「已达标」——§2 已说明它们是副产品。

## 12. 待办登记（本次不修）

1. **领域词表可移植**：`lexicon.py` 只有图像复原，是 20 篇 MC 归零的直接原因。
   本次只外置结构，不新增领域组。
2. **L3 的第二轮独立盲标**：本次 `covered` 仍以 owner-derived 标注为分母，
   不是质量结论。
3. `SqlEventRepository.list_by_run` 缺 `ORDER BY`，memo 取 `events[-1]` 依赖 SQLite rowid。
4. `replaced` payload 值断言、`inspect_claim` partner 成员断言。
5. §2.5 其余 6 项确定性实现的 deviation ADR 逐项登记。

## 13. 实施偏差

| # | 计划/设计 | 实际 | 性质与理由 |
|---|---|---|---|
