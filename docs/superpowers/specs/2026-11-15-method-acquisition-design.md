# 方法获取能力设计（2026-11-15）

> 背景：`docs/evaluation/2026-11-14-method-acquisition-audit.md` 在 40 篇留出集上实测出
> **L1 方法身份 0/20、L3 方法描述 0/20**（两个领域都是 0），L2 为 19/20 与 10/20，
> L4 为 11/19 与 14/20，缺口合计 105 = 159 − 54。审计脚本只度量、不修复；
> 本文设计**补上这四层的抽取能力**。
>
> 与上一份 spec 的关系：`2026-11-14-method-acquisition-measurement-design.md` §7
> 「明确不做」列出了「不扩词表、不引入 LLM、不改 `identity_key`」。本文**正是**
> 解禁这三条，逐条给出理由，不是遗忘。
>
> **修订记录（2026-11-15）**：第一版经独立子代理审验判 `NEEDS WORK`（4 Blocker /
> 10 Major / 8 Minor）。本文按审验意见重写：拆为 S1–S4 四个独立实施阶段；LLM 接线
> 从「插一个步骤」改为可实施的同步适配器 + 预算计数；`unit` 回填从「每次启动执行」
> 改为「列刚添加时一次性执行」；`conditions` 的 provenance 从整体覆盖改为按 kind；
> 验收从「≥1/20 即过」改为守恒式 + 零容忍；归因键从 `source_version_id` 改为
> `(subject, source_version_id)`。审验报告逐条处置见 §14。

## 0. 决策记录

| 项 | 结论 | 来源 |
|---|---|---|
| 抽取机制 | **分层混合**：L1 名字、L2 组件、L4 设置走确定性；**只有 L3 描述**走 LLM | 用户 2026-11-15 确认 |
| 方法身份与 `identity_key` | **独立实体**，不进 identity；`subject` 仍为 `self@<source_version_id>` | 用户 2026-11-15 确认 |
| P4 的 model scale / evaluation protocol | **接进 `conditions` 并进 `identity_key`**，接受合并行为改变；必须 before/after 双份登记 | 用户 2026-11-15 确认 |
| L3 存储形态 | **结构化要点** `list[{aspect, statement, quote, chunk_id}]`，不是自由散文 | 用户 2026-11-15 确认 |
| 实施分期 | 拆 **S1–S4** 四个阶段，各自独立计划与验收，顺序 S1→S2→S3→S4 | 审验 M9；本文 §3 |

## 1. 计划依据

| 位置 | 要求 | 本文的落点 |
|---|---|---|
| §15 / P3（`md:838-856`） | 「**Where possible**, represent quantitative evidence separately」（`md:838`）；`QuantitativeEvidence` 的 `method: str \| None`（`md:847`）、`protocol: str \| None`（`md:853`），理由「avoid invalid cross-paper comparisons」（`md:856`） | S1 修 `protocol` 语义；S2 让 `method` 写真名 |
| §16 / P4（`md:864-885`） | 主张不得因措辞相近合并，须区分 7 维；其中 **model scale**（`md:880`）、**evaluation protocol**（`md:881`）当前无落点 | S4 新增 `scale=` 与 `protocol=` |
| §16 其余 5 维（`md:875-881`） | dataset · task · metric · architecture · training setup | 已落（architecture 仅 `backbone=` 一词，见 §12 登记） |
| §2.5（`md:168-192`） | 确定性 9 项 vs LLM 语义判断 7 项，含 `evidence extraction`、`claim normalization`、`scope comparison`（`md:184-192`） | §7 只把 L3 交给 LLM |
| §7.4（`md:475`） | 「Never store only an LLM-generated summary without source location」 | §7.4 四道防线 |
| §2.2（`md:104-117`） | 追溯链 `conclusion → claim → evidence → source version → location` | §6.1 `name_quote` + `chunk_id` |
| §8（`md:570`） | `official repository > paper description` 的权威层级 | **本文不实现**，见 §12 登记为待办 |
| §19（`md:960-981`） | Falsification 要求「inspect source code when relevant」 | **本文不实现**，见 §12 登记为待办 |
| §26 预算（`md:1166-1175`） | `max_llm_calls: 80`、`max_cost_usd: 5.0` | §7.3 计数点与检查点 |
| §7.5（`md:488`） | `Claim.conditions: list[str]` | §8 两种新条件仍走该字段 |
| §35（`md:1439-1443`） | 「Before introducing major infrastructure, answer: What current measurable problem does this solve?」 | §6.5 不引入 Alembic |

## 2. 实测起点（不是结论）

| 层 | 图像复原 | Agent in MC | 系统侧为何是这个数 |
|---|---|---|---|
| L1 方法身份 | `C = 0/20`（`covered/20 = 0`） | `C = 0/20`（`0`） | `method` 只在 `_PROPOSED_RE` 命中时写常量 `"proposed method"`，其余为 `None`；**没有任何一行写出真名** |
| L2 方法构成 | `C = 19/20`（`19`） | `C = 10/20`（`10`） | 靠 `conditions` 的 `backbone=` / `baseline=` 蹭到，不是真组件 |
| L3 方法描述 | 结构性缺失 | 结构性缺失 | 全文任何模型都没有可存描述的位置 |
| L4 可复现设置 | `C = 11/19`（`11`） | `C = 14/20`（`14`） | 只靠 `training=` 一个槽 |

两点必须说清，否则验收会被误读：

- L2/L4 的分数是**蹭到的**，不是抽得好。
- L1/L3 的 0 **不是抽错，是没地方存**。第一动作是加落点，不是调正则。

另有一条会直接影响 §6.1 与 §7 的事实：`architect.md:144` 记录「20 篇实测 476 条 self 中
425 条是**推断**而来，抽样 12 条仅 2 条为真自指」。所以「这句在讲本文方法」这个判断
本身就不牢靠——任何依赖它的归因都不能宣称精度。

## 3. 分期（本文是设计，不可直接实施）

单次改动横跨数据模型、抽取、identity、迁移、编排、memo、审计脚本七个关注面且互相耦合，
before/after 差异无法归因到具体一项。拆四刀，按依赖排序：

| 阶段 | 范围 | 独立理由 | 验收 |
|---|---|---|---|
| **S1** | `protocol`→`unit` 语义修正：`unit` 字段/列、一次性回填、写路径迁移、`_buckets` 改读 | 修一个**既有缺陷**，与方法获取无关；可单独回滚 | `value_bucket` 逐字不变；`init_db()` 两次幂等；既有测试数不变 |
| **S2** | 确定性 L1/L2/L4 + `MethodProfile`/`MethodSetup`/`MethodPoint` + 存储 + memo + **审计脚本扩展** | 不碰 identity，不改主张数，可独立度量 | L1/L2/L4 守恒式；L1 零容忍精度；L3 全为「有原因未覆盖」 |
| **S3** | L3：同步 `MethodDescriber` + async 适配器 + provider 配置 + 预算计数 + 4 个事件 + 录制回放 | 依赖 S2 的表；async/预算/配置是独立风险面 | L3 守恒式；无 provider / 超预算 / 坏 schema / 坏 quote 四条路径都有事件 |
| **S4** | `conditions` 新增 `scale=`/`protocol=` + **按 kind 的 provenance** + 级联安全 + before/after 三份报告 | 只有它改变主张宇宙，必须独占一个度量周期 | 合并数变化逐项可解释；`TRUE_CONTRADICTION` 不因新维度增加 |

S1 必须先做：否则 `MethodSetup.protocol`、`QuantitativeEvidence.protocol`、
`conditions` 的 `protocol=` 三个同名概念并存，S2 一落地就冲突。
S4 必须最后且独占周期：否则主张数的变化无法归因到「新条件」还是「新抽取」。

**每个阶段单独出计划、单独提交、单独验收；前一阶段的验收未过不进入下一阶段。**

## 4. 架构与数据模型

### 4.1 三个新模型（S2 引入）

```python
class MethodPoint(BaseModel):
    aspect: Literal["goal", "mechanism", "why_it_works", "io"]
    statement: str          # ≤200 字符
    quote: str              # ≥4 词，且在声明 chunk 内唯一出现
    chunk_id: str
    section: str | None     # memo 要打印的章节名

class MethodSetup(BaseModel):
    scale: str | None = None          # 归一化后 "8xa100" / "7b" / "34m"
    protocol: str | None = None       # "zero-shot" / "5-shot"
    hyperparameters: list[str] = []   # "lr=3e-4" / "batch=32" / "epochs=100"
    repository: str | None = None     # 官方仓库 URL（只是入口，不是 §8 的权威层级）

class MethodProfile(BaseModel):
    source_version_id: str
    name: str | None = None
    aliases: list[str] = []
    name_quote: str | None = None
    name_chunk_id: str | None = None  # 名字必须可定位（§2.2）
    components: list[str] = []
    setup: MethodSetup = MethodSetup()
    points: list[MethodPoint] = []
    missing_layers: list[str] = []    # 子集 of {"L1","L2","L3","L4"}
```

`missing_layers` 是刻意设计的：让「这篇的 L3 没拿到」变成**落库的事实**。上一轮的问题
正是「空」与「抽到但是空」在数据里长得一模一样。

**一篇论文多个方法**：`2409.19479` 实测含 CALVIN / SOAP / LangProp / Voggite
（`tests/fixtures/method_acquisition/ANNOTATION.md:194`）。本文只收一个 `name`，
其余进 `aliases`，并在 `missing_layers` 无法表达时由 §10 的守恒式外单独记一条事件
`METHOD_MULTI_NAME`。**这是已知限制，不假装解决了**（§12 登记）。

### 4.2 归因键必须是 `(subject, source_version_id)`

不加外键，由查询层解析，但**只看 `source_version_id` 是错的**：

- `claims.py:156-174` 的 `_subject()` 对第三方方法名**不绑 source version**，只有
  `self` 才变成 `self@<svid>`（`claims.py:229-230`）。
- 因此论文 B（自己的方法是 WISE）写「Restormer improves Rain100H PSNR」，其证据只来自
  B。若只按 svid 归因，这条**关于 Restormer 的主张**会被渲染成 B 的方法 WISE——
  正是「把一篇的方法名安到另一篇结论上」，只是从跨篇搬到了单篇内部。

规则：

| 情形 | 处置 |
|---|---|
| `subject` ∈ `{profile.name, *profile.aliases}` 且证据来自 1 个 svid | 正常归因 |
| `subject == "self@<svid>"` 且证据来自 1 个 svid | 归到该 svid 的 profile |
| `subject` 是该篇的第三方方法名（不在 profile 里） | 记 `unattributed_subject`，不归因 |
| 证据跨 >1 个 svid | 记 `multi_source`，不归因 |
| 同一 work 的多个版本落在同一 run | 按 work 归一后视为同一篇；不判 `multi_source` |

跨源合并的**实测频率是 0**（`architect.md:147`：20 篇 73 个可合并键，跨文档命中 0 组），
上一版把它写成未知风险是错的。`multi_source` 仍需实现，因为它防的是**错误归因**，
不是因为它常见；`unattributed_subject` 才是主路径。

### 4.3 不加 `Claim` / `ClaimIdentity` 字段

`identity_key` 仍是 7 段。S4 只往第 6 段（`conditions`）加两种新条件值，段数不变。

## 5. S1：`protocol` → `unit`

### 5.1 问题

计划 `md:853` 的 `protocol` 指评测协议；实现里 `quantitative.py:94-105` 的 `_unit_near()`
只返回 `"dB"` / `"percent"` / `None`，写入点 `quantitative.py:143` 与 `:192`。
字段名与语义不符，且挡住了真正的评测协议。

### 5.2 改法

1. `domain/models.py` 的 `QuantitativeEvidence` **新增 `unit: str | None`**（上一版漏了
   这步，导致 `claims.py` 读不到）。
2. `storage/tables.py` 新增 `unit` 列；`database.py::_ADDED_COLUMNS` 登记。
3. `quantitative.py:143` 与 `:192` 的 `protocol=` 改为 `unit=`。
4. `claims.py:206` 的 `row.protocol or 'unit'` 改为 `row.unit or 'unit'`。

### 5.3 回填必须是「列刚添加时一次性执行」

`init_db()` 每次 CLI run、每次 FastAPI 启动、每个测试 fixture 都会执行
`_apply_sqlite_migrations`（`database.py:51`）。若照上一版写的「无条件
`UPDATE ... SET unit = protocol`」：

- 第一次：`unit='dB'`、`protocol=NULL`。
- 第二次：`SET unit = protocol` 把 `unit` 写成 **NULL**，单位信息全丢；若新抽取已写入
  `protocol='zero-shot'`，则 `unit` 变成 `'zero-shot'`、`protocol` 被清空，两列同时错。

这是数据损坏级，不是「改动量估计偏低」。正确做法：

- 回填只写在 `_ADDED_COLUMNS` 的 `if name not in existing:` 分支内——即**这一列刚刚
  被加上**时才跑，天然只执行一次。
- SQL 加白名单：`UPDATE quantitative_evidence SET unit = protocol WHERE unit IS NULL
  AND protocol IN ('dB','percent')`；随后 `UPDATE ... SET protocol = NULL WHERE unit IS
  NOT NULL AND protocol IN ('dB','percent')`。
- 回归测试：`init_db()` → 写一行 `unit='db'`、`protocol='zero-shot'` → 再 `init_db()`
  → 断言两列都不变。**删除一次性条件后该测试必红。**

### 5.4 `value_bucket` 的影响要说准

`claims.py:199-207` 里只有 **delta 行**读 `row.protocol`，而 delta 行的 `protocol` 恒为
`"dB"`/`"percent"`。回填后 `unit` 同值 → 历史行的 bucket **逐字不变**。
上一版说「该改动改写 `value_bucket`」是错的。

真正的风险是漏改：若 `quantitative.py` 的写入点没迁到 `unit`，新行的 `unit` 为 `None`，
`row.unit or 'unit'` 会把 delta bucket 从 `db:0.44` 变成 `unit:0.44`，历史行与新行永不
合并。因此 S1 的验收必须包含：**delta 行的 bucket 与迁移前逐字相同**（构造夹具断言）。

## 6. S2：确定性 L1 / L2 / L4

### 6.1 L1 方法名

**只接受显式命名句式**：

| 构式 | 例子 |
|---|---|
| `we (propose\|introduce\|present\|call) (it )?X` | we introduce LangProp |
| `our (method\|approach\|model\|framework\|system)[,]? (called\|named\|dubbed)? X` | our framework, Voyager, |
| `X, (our\|the) (proposed )?(method\|approach)` | LangProp, our proposed method |
| `this (paper\|work) (proposes\|presents\|introduces) X` | This work presented LangProp |

**`X` 的边界必须写死**：`[A-Z][A-Za-z0-9\-]{2,}` 且**不得是谓词**（
`achieves/improves/outperforms/gains/reports/reduces/increases/enables`）与
`COMMON_CAPS`。不写这条，`we propose a method that achieves …` 会抽到 `achieves`，
再经 §6.1 填进 `QuantitativeEvidence.method`，污染所有数值行。

候选必须通过四道排除（`COMMON_CAPS`、`DATASETS`、`METRICS`、`NOT_A_SUBJECT`），且
**句首大写词不能单独作为命名证据**（沿用 `claims.py:169` 的判据：句首位置 + 无内部
大写 + 非缩写 + 无数字 → 跳过；句首但含内部大写/缩写/数字的仍可接受）。

多个候选按**来源层级**取（摘要 > 引言 > 方法章 > 结论），同层取首次出现；
同层同位置并列 → `name = None` + `METHOD_NAME_AMBIGUOUS` 事件。不做词频猜测。

名字必须**可定位**：`name_quote` + `name_chunk_id` 同时落库，缺一即 `name = None`。

### 6.2 L2 组件

结构名词短语：`{encoder, decoder, attention, transformer, memory, planner, buffer,
graph, gate, adapter, head, tokenizer, retrieval, reward model}` +
`X (module|network|block|layer|branch|mechanism)`。

选这批词的理由：结构性词汇在图像复原与 Minecraft agent 两类论文里语义一致；不像
`DATASETS` 那样换域即废（MC 归零的直接原因正是数据集词表）。

### 6.3 L4 可复现设置

| 子项 | 抓法 | 是否进 identity |
|---|---|---|
| `repository` | URL 正则，限 `github.com` / `gitlab` / `huggingface.co` | 否（只进 `MethodSetup`） |
| `hyperparameters` | `learning rate`/`lr`/`batch size`/`epochs`/`steps`/优化器名 + 就近数值 | 否（P4 七维无超参） |
| `scale` | `\d+(\.\d+)?\s?[bm]\b`；`\d+\s?[×x]\s?(a100\|h100\|v100\|gpu)`，归一化为 `8xa100` / `7b` | 是（§8.1） |
| `protocol` | **只收** `zero-shot` / `few-shot` / `\d+-shot` / `pass@\d` | 是（§8.1） |

`top-1`、`success rate`、`\d+ episodes` **不进 identity**：前两个是**指标**，
第三个是**预算**，都不是评测协议。把指标当协议，就是拿「相同指标」冒充「相同协议」。

### 6.4 模式外置

所有模式集中到 `research/patterns.py`：`GENERIC` 组恒先生效，领域组叠加。
**本次不新增任何领域组**——Minecraft 词表是独立议题（§12），但结构先铺好。

### 6.5 存储

- `method_profiles`：`id`、`run_id`、`source_version_id`、`name`、`name_quote`、
  `name_chunk_id`、`aliases_json`、`components_json`、`setup_json`、`missing_layers_json`；
  **唯一约束 `(run_id, source_version_id)`**（追溯输出按 run 作用域，ADR-019）
- `method_points`：`id`、`profile_id`（外键）、`aspect`、`statement`、`quote`、`chunk_id`、`section`

`aliases`/`components`/`setup`/`missing_layers` 用 JSON 列：它们是同一条 profile 的附属
属性，从不被单独查询或 join。`points` 拆表因为它要被逐条遍历和计数。

迁移走 `_ADDED_COLUMNS`（只加列）+ `create_all`（建新表），不引入 Alembic（§35）。

仓储：`upsert(profile, run_id)`、`get(run_id, svid)`、`list_by_run(run_id)`、
`profiles_for(run_id, svids)`（归因用，一次查询，不循环打库）。按
`(run_id, source_version_id)` 幂等。

### 6.6 memo

新增 Methods 段，每篇一栏：名字（带 section）、组件、scale/protocol、仓库、
L3 要点（`statement` + `[section]`）、`未获取：…`。

三条必须成行，即使为 0：`missing_layers`、`多来源主张：N（未归因）`、
`未归因主语：N`。「0」和「没统计」必须能区分。

### 6.7 审计脚本必须扩展（否则新能力不可观测）

`scripts/method_acquisition_audit.py` 当前：

- `:97` `if layer == "L3": return False` —— 硬编码；
  `tests/unit/test_method_acquisition_audit.py:111` 断言 `is False`。不改这两处，
  §10 的「L3 从 0 起来」**永远观测不到**。
- `:60-88` `system_side()` 只跑 extractor + builder，**看不到 `MethodProfile`**；
  L2 判据是 `conditions` 有 `backbone=`/`baseline=`（`:85`），L4 只认 `training=`（`:86`）。
  新加的 `components`/`setup` 不进指标 → 新能力可以完全坏掉而验收通过。

S2 必须：把 `system_side()` 改为读 `MethodProfile`（L1 用 `name` 非空，L2 用
`components` 非空或 conditions 命中，L4 用 `setup` 任一子项非空），并把现有那条
`assert covered_for("L3", ...) is False` 改成随实现变化。**S2 不碰 L3，L3 仍返回
「无结构化字段」，但那条断言要改成显式表达「S2 阶段 L3 无落点」，而不是硬编码常量。**

## 7. S3：L3 的 LLM 接线

上一版写「插一个阶段」是不可实施的：全仓库**没有** provider 装配、没有配置项、
没有 `llm_calls` 递增点，且 `LLMProvider.generate` 是 `async def` 而切片是同步方法。

### 7.1 同步协议 + async 适配器

```python
class MethodDescriber(Protocol):
    def describe(self, chunks: list[DocumentChunk]) -> MethodDescriptionResponse | None: ...
```

- `AsyncProviderDescriber`：内部 `asyncio.run(provider.generate(...))`。
- 构造时与调用时都 `asyncio.get_running_loop()` 探测；若已在事件循环里，抛 typed
  error（`LLMInEventLoopError`），**禁止静默嵌套**。
- 从 `Supervisor.__init__` 注入，与 `EvidenceExtractor` / `ClaimBuilder` 同构。
- 测试注入 fake sync describer，不引入事件循环。

### 7.2 provider 配置

`config.py` 增加 `llm_provider`（默认 `none`）、`llm_model`、`llm_api_key`。
装配点：`cli.py` / `main.py` 构造 `Supervisor` 时按 `llm_provider` 选择
`AsyncProviderDescriber` 或 `None`。**`UnavailableProvider` 从未被实例化过，
不能声称「当前默认是它」**；默认是「不装配 describer」。

### 7.3 预算计数与检查点（当前完全缺失）

`_check_budget()`（`supervisor.py:127-131`）只读 `exceeded()`，**从不递增任何计数器**；
`budget.llm_calls` 全仓库无写入点，`exceeded()` 的 `llm_calls >= max_llm_calls`
永远为假。按上一版实施 = LLM 调用无上限、成本上限永不生效。

必须在 S3 补齐：

- 调用**前**：`if llm_calls >= max_llm_calls or cost_usd >= max_cost_usd: skip + 事件`
- 调用**后**：`llm_calls += 1`；provider 返回用量则 `cost_usd += cost`，否则不回填。
- 边界写死为「先查后加」，避免 80/81 的 off-by-one。
- 回归测试：`max_llm_calls=0` → 0 次调用、每篇一条 `METHOD_DESCRIPTION_SKIPPED`；
  `max_llm_calls=2` + 3 篇 → 恰好 2 次调用、第 3 篇有事件。

### 7.4 四道防线

1. `quote` 去空白折叠后**逐字出现**在声明的 `chunk_id` 文本里；**≥4 词**且在该 chunk 内
   **唯一出现**。不满足 → 丢弃该点 + `METHOD_POINT_UNLOCATABLE`。
   （上一版缺长度与唯一性：`quote="attention"` 到处命中。）
2. `statement` 的内容词（去停用词、去 aspect 词）至少 **2 个**出现在 `quote` 里，
   否则 `METHOD_STATEMENT_UNSUPPORTED`。这是防「quote 真、statement 编造」——
   形式合规但实质是「有位置的编造」，正是 `md:475` 要防的。
3. `aspect` ∈ 四枚举、`statement` ≤200 字符、`chunk_id` ∈ 本次输入。不合 → 整篇丢弃 +
   `METHOD_DESCRIPTION_REJECTED`，**不落半成品**。
4. 无 provider / 超预算 → `METHOD_DESCRIPTION_SKIPPED` + `missing_layers` 加 `"L3"`。
   **不把「没调」呈现成「调了没结果」**。

### 7.5 事件归类

现有惯例是 `EventType.FAILURE` + `FailureType.X`（`enums.py:113-141` 无 `METHOD_*`）。
本轮新增 `FailureType` 四项：`METHOD_POINT_UNLOCATABLE`、`METHOD_STATEMENT_UNSUPPORTED`、
`METHOD_DESCRIPTION_REJECTED`、`METHOD_DESCRIPTION_SKIPPED`；另有两项是普通事件而非失败：
`METHOD_NAME_AMBIGUOUS`、`METHOD_MULTI_NAME`（用 `EventType.FAILURE` 会污染失败计数）。

### 7.6 离线可复现

加 recorded fixture provider（仿 `ADR-010` 的录制回放）：把 40 篇的 L3 响应录成夹具，
使 L3 的 covered 可重复重跑。**否则 §10 的 L3 验收在无 provider 的默认配置下必然失败。**

## 8. S4：identity 两个新维度与 provenance 重构

### 8.1 两种新条件

`conditions.py` 的四类扩为六类，新增 `scale=` 与 `protocol=`（取值见 §6.3），沿用
「每类最多一个值、不设默认、值小写归一」。

`tuple(sorted(found))` 按前缀排序安全（`backbone` < `baseline` < `degradation` <
`protocol` < `scale` < `training`），`";"` 拼接与 `contradiction.py` / `memo.py` 的解析
不受影响——**前提是新值不含 `;` 与 `|`**，需加断言。

### 8.2 provenance 必须按 kind（这是 S4 的核心，不是附带）

现状 `claims.py:177-184`：

```python
own = extract_conditions(text)
if own:
    return own, "sentence"        # 整体覆盖 + tier 直接升到 sentence
```

**句子只要命中任何一类条件就整体替换继承值**，并把 `conditions_from` 标成 `sentence`。
新增两个高频模式后：

- 一句 `"ours achieves 70% success rate"` → `own = ("protocol=...",)`，**丢掉**章节继承
  的 `training=` / `backbone=` → L2/L4 覆盖率下降，直接违反 §10 硬要求。
- 同一句的 tier 被升为 `sentence`，而 `contradiction.py:146` 的
  `_CONFIRMED_TIERS = {"sentence", "heading"}` 把它当作「已证实的同一设置」→
  允许 `TRUE_CONTRADICTION`。这违反 HD-014（继承只可否证相同，不可证实相同）与
  计划 `md:917`「默认结果不得是 `TRUE_CONTRADICTION`」。

改法：`conditions` 的 provenance 从「整体一个 tier」改为**按 kind 记录**
`dict[kind] -> (value, tier)`；继承时按类补齐缺失的 kind，各自的 tier 保留原值；
`identity_key` 仍拼接排序后的 `kind=value`（**键不变，值域不变**）；
`contradiction.py` 的确认判据改为「参与本次比较的每个 kind 的 tier 都在
`_CONFIRMED_TIERS` 内」。

必带对照测试：一句只含 `protocol=` 的句子，**仍保留**继承来的 `training=`，
且其 tier 仍是 `section-first-mention`。

### 8.3 三处 `protocol` 的层级

| 位置 | 粒度 | 谁消费 |
|---|---|---|
| `MethodSetup.protocol` | 论文级 | memo、profile |
| `QuantitativeEvidence.protocol` | 单行数值 | P7 比对 |
| `conditions` 的 `protocol=` | 单句主张 | `identity_key` 第 6 段 |

三者可一致但不保证一致（一句只描述 5-shot 结果，论文整体另有 zero-shot）。
`hyperparameters` **不进** `conditions`——P4 七维里没有超参。

### 8.4 影响与度量

新增两维会改变命中句的 `identity_key`，部分合并拆开、主张数上升；按 kind 的 provenance
又会把此前被整体覆盖掉的条件补回，方向相反。**两者必须一起度量、一起登记**，
禁止只报新数字、隐去旧数字。

## 9. 测试策略

| 类别 | 内容 |
|---|---|
| 单元 | 每个抽取器的正例 + **负例**（句首大写词、数据集名、`dB`、谓词 `achieves` 都不是方法名） |
| 单元 | `scale=`/`protocol=` **确实改变合并结果**：仅在这两维不同的两句 → `may_merge() == False`。「字段有值」不算通过 |
| 单元 | provenance 按 kind：只含 `protocol=` 的句子仍保留继承 `training=` 且 tier 不变 |
| 契约 | fake describer：坏 schema / 不可定位 quote / 短 quote / statement 与 quote 无词重叠 / 不存在的 chunk_id，五条路径各有事件 |
| 集成 | profile 落库、points 读回、memo 三段计数成行、重跑幂等、跨 run 各留一份 |
| 集成 | 归因四情形（§4.2 表）各一例 |
| 迁移 | `init_db()` 两次幂等：`unit` 与 `protocol` 都不变；delta bucket 逐字不变 |
| 变异锚点 | 删「一次性回填」条件 → 迁移测试必红；删 quote 长度/唯一性 → 契约测试必红；删谓词排除 → 负例必红；删按 kind provenance → 继承测试必红 |

回归基线：当前 `328 collected / 326 passed / 2 skipped`。每个阶段结束时既有数字保持不变，
新增用例另计，总数 = `326 + 新增`。

## 10. 验收（不预设阈值，但必须可证伪）

上一版「L1/L3 从 0 起来」字面等于 `≥1/20` 即通过，只抽到 1 篇就算达标——比预设阈值更弱。

### 10.1 守恒式（主力判据）

对每个 `(领域, 层)`：

```
covered + explained_uncovered == present 且 unexplained_uncovered == 0
```

`explained` 的原因只能来自**闭合枚举**，且必须能追到落库的事件或 `missing_layers`：

| 原因 | 来源 |
|---|---|
| `词表未覆盖` | 无事件，但同类格子的既有统计 |
| `无结构化字段` | 该阶段尚未实现该层（如 S2 的 L3） |
| `无来源定位` | `METHOD_POINT_UNLOCATABLE` / `METHOD_STATEMENT_UNSUPPORTED` |
| `LLM 未启用` | `METHOD_DESCRIPTION_SKIPPED` |
| `LLM 输出被拒` | `METHOD_DESCRIPTION_REJECTED` |
| `命名歧义` | `METHOD_NAME_AMBIGUOUS` |

**不允许出现「无法解释的未覆盖」。** 这迫使每篇都有结论，而不是「抽到 1 篇就算过」。

### 10.2 L1 零容忍精度

每个产出的 `name` 必须同时满足：

1. 是原文的逐字子串（可从 `name_quote` 定位）；
2. 匹配一个**独立于抽取器**的命名构式清单（第二套正则，写在测试里，不复用
   `patterns.py`）。

任何一条不满足即视为该阶段失败。**没有阈值。**

### 10.3 L1 按行而非按篇

`QuantitativeEvidence.method` 的覆盖率按**行**报：分母 = 该篇所有 `_PROPOSED_RE` 命中行
+ 所有含具名第三方方法的数值行；分子 = 其中 `method` 非空且等于已解析名字的行。
「任一行有值即整篇 covered」会把 1 行填对算成整篇达标。

同时修正填充条件：`method` 在「句子点名了 self 或具名第三方方法」时就填，
不再只依赖 `_PROPOSED_RE`（`quantitative.py:157`）；否则 §15 的字段大部分仍为空，
而按篇计又会被 1 行抬高。**接 `architect.md:144` 的教训（476 条 self 里 425 条是推断、
抽样 12 条仅 2 条为真）：`method` 的精度不宣称，只报行级覆盖率与 `subject_inferred` 比例。**

### 10.4 L2 / L4 与 L3

- L2/L4：比较**逐篇布尔向量的 before/after**，不只比总数；每一处下降逐篇给理由，
  否则回滚。新 `components` / `setup` 纳入判据（依赖 §6.7 的脚本扩展）。
- L3：用 recorded fixture provider 重跑（§7.6），同样按守恒式；无 provider 的 run
  只允许进「有原因未覆盖」。

### 10.5 重测产物

| 产物 | 命令 |
|---|---|
| 方法四层 | `python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json` |
| 主张质量 | `python scripts/holdout_claim_quality.py --ids-file …` |
| 矛盾质量 | `python scripts/holdout_contradiction_quality.py --ids-file …` |

三份报告进 `docs/evaluation/`，旧数字**不删不改**，只在新报告里并列 before/after。

## 11. 明确不做

- 不实现 §8 的来源权威层级（repository 只是 URL，不是 tier）。
- 不实现 §19 的「inspect source code」。
- 不扩领域词表（MC 词表独立立项，§12）。
- 不让方法名进 `identity_key`、不改 `subject`、不改配对语义。
- 不改矛盾判定级联的**关系类型**（只改 provenance 的确认判据，§8.2）。
- 不改 `coverage` 口径、不修 `SqlEventRepository.list_by_run` 的 `ORDER BY`。
- 不做第二轮独立盲标、不建 gold label、不算任何正确率。
- 不宣称 `components` 让 architecture 维达标（仍是 `backbone=` 一个词，§12）。

## 12. 待办登记（本次不修）

1. **领域词表可移植**：`lexicon.py` 只有图像复原，是 MC 归零的直接原因。
2. **architecture 维**：`components` 不进 identity，P4 的该维仍只有 `backbone=` 一词。
   若要满足，需单独设计「架构身份」及其与 `subject` 的关系。
3. **§8 来源权威层级**：`SourceTier.REPOSITORY`（`enums.py:31`）已在来源解析中使用
   （`sources/resolver.py:31`、`sources/verification.py:33`），但从未与
   `MethodSetup.repository` 打通：仓库 URL 只是一个字符串，没有 tier，
   `repository` 与论文描述冲突时取谁没有规则。
4. **§19 Falsification 的源码检查**：方法获取的最高价值来源，未接。
5. **一篇多方法**：`2409.19479` 一类只取一个 `name`，其余进 `aliases`。
6. **L3 第二轮独立盲标**：`covered` 仍以 owner-derived 标注为分母，不是质量结论。
7. `SqlEventRepository.list_by_run` 缺 `ORDER BY`，memo 取 `events[-1]` 依赖 SQLite rowid。
8. `replaced` payload 值断言、`inspect_claim` partner 成员断言。
9. §2.5 其余 6 项确定性实现的 deviation ADR 逐项登记。
10. §21 指标清单无方法抽取指标；本轮新增四层度量需登记进 §21 / `README.md`。

## 13. 实施偏差

| # | 计划/设计 | 实际 | 性质与理由 |
|---|---|---|---|

## 14. 审验意见处置

| 编号 | 级别 | 处置 |
|---|---|---|
| B1 LLM 通路不存在 | Blocker | §7 重写：同步协议 + async 适配器 + provider 配置 + 预算计数点 + 事件归 `FailureType` |
| B2 `unit` 回填损坏数据 | Blocker | §5.3 改为「列刚添加时一次性执行」+ 白名单 WHERE + 幂等测试 |
| B3 新条件触发整体覆盖与 tier 升级 | Blocker | §8.2 改为按 kind 的 provenance，附继承保留对照测试 |
| B4 验收不可证伪 + 脚本硬编码 L3 | Blocker | §10 换守恒式 + 零容忍 + 行级；§6.7 明确要求扩展脚本与其测试 |
| M1 归因只看 svid | Major | §4.2 改为 `(subject, svid)`，四情形表 + 单篇第三方/多版本用例 |
| M2 `name_quote` 不可定位 | Major | §4.1/§4.1 增 `name_chunk_id`，缺一即 `name = None` |
| M3 `X` 边界未定义 | Major | §6.1 写死 `X` 的正则与谓词排除 |
| M4 `method` 仍受 `_PROPOSED_RE` 限制 | Major | §10.3 改填充条件 + 行级覆盖率 + 不宣称精度 |
| M5 `unit` 缺字段、写路径未迁 | Major | §5.2 四步 + §5.4 delta bucket 逐字不变断言 |
| M6 L3 缺第四道防线 | Major | §7.4 增 quote ≥4 词且唯一 + statement/quote 词重叠 |
| M7 §8 权威层级无落点 | Major | §11 明确不做 + §12.3 登记 |
| M8 一篇多方法 | Major | §4.1 记 `METHOD_MULTI_NAME` + §12.5 登记 |
| M9 改动面过大 | Major | §3 拆 S1–S4，各自计划与验收 |
| M10 architecture 维仍只有 backbone | Major | §11/§12.2 登记为未满足，不用 §16 暗示已覆盖 |
| m1–m8 | Minor | 已修：§26 行号、§2.2 引用、"Where possible" 措辞、`method` 非「恒为常量」、句首判据表述、事件归类、回归基线、`scale` 归一化格式 |
