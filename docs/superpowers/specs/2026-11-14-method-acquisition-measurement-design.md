# 方法获取能力度量设计（2026-11-14）

> 背景：以 `Agent in MC`（Minecraft 智能体）为主题的 20 篇全新留出集跑完后，
> 定量通道整体归零（`quantitative` 170 → 0）、`task` 标题继承 98.2% → 23.4%、
> P5 判定 30 → 0。这些数字由 `scripts/holdout_claim_quality.py` 与
> `scripts/holdout_contradiction_quality.py` 在两个 ids 清单上实跑得到（清单见 §3）。
> 复审权威计划 `ResearchOS-Implementation-Plan.md` v1.1 后确认：
> 计划把「方法」列为**独立于数值**的结构化能力，而当前实现从未真正建成。
> 本文只设计**一次只读度量**，不实现任何抽取能力。
>
> 修订记录：2026-11-14 经独立子代理审验（`f133f7a` 版本）判 NEEDS WORK，
> 6 条 Important + 5 条 Minor 已按最小清单修入本文。

## 0. 决策记录

| 项 | 结论 | 来源 |
|---|---|---|
| 「方法获取」的范围 | **(b) 广义**：方法身份 + 方法描述 + 实现细节 + 可复现实验设置，不止可比较的结构化身份 | 用户 2026-11-14 确认 |
| 路径 | **C 先度量**：先量现状，再决定「最小补全」还是「按 §2.5 引入 LLM」 | 用户 2026-11-14 确认 |
| 标注基准 | **选项 1**：owner-derived reference，显式声明非独立、非盲标；只算可获取率与覆盖率，**不算正确率** | 用户 2026-11-14 确认 |

## 1. 计划依据

| 位置 | 要求 | 与本设计的关系 |
|---|---|---|
| §2.2（`md:104-117`）、§7.4（`md:446-475`） | 追溯链 `conclusion → claim → relation → evidence → source version → location`；`md:475`「Never store only an LLM-generated summary without source location」 | §4 要求 `present` 必须附可定位证据的**计划依据** |
| §7.5（`md:477-493`） | `Claim.conditions: list[str]` | §5 L2/L4 认领对象的字段来源 |
| §8（`md:567-570`） | 「For implementation details: official repository > paper description」 | §3 L4「代码/仓库链接」的权威层次 |
| §15 Phase 3（`md:841-856`） | `QuantitativeEvidence` 必须有 `method: str \| None`，与 dataset/metric/value/comparator/protocol 并列，理由是 "avoid invalid cross-paper comparisons" | §16 要求的结构化方法身份 |
| §16 Phase 4（`md:871-881`） | 主张不得因措辞相近合并，须按 7 个维度区分：dataset · task · metric · **architecture** · **training setup** · **model scale** · **evaluation protocol** | §3 四层设计的主要来源 |
| §17（`md:913-914`） | 以 Transformer / CNN backbone 作 scope 差异范例 | §5 L2 认领 `backbone=` 的依据 |
| §2.5（`md:184-192`） | **共 7 项**语义判断场景；与本设计相关的 4 项是 `evidence extraction`、`claim normalization`、`scope comparison`、`contradiction judgment` | 判断「确定性实现是否为偏差」的基准 |
| §2.6 / §21 | 每个能力引入时须有 fixtures 与 measurable tests；§21 现有指标清单里**没有方法抽取指标** | 本次度量的定位 |
| §19（`md:955-981`） | Falsification 要 "inspect source code when relevant"、检查参数量与消融 | §3 L4 的补充来源（「属于可复现设置层」是本设计的解读，非原文措辞） |
| §30 | `evidence extraction` 排第 4、`claim synthesis` 排第 11 | 方法获取是地基，不是后续加分项 |
| §36（`md:1490`） | DoD 要求至少 5 个 benchmark tasks | 本设计不新增 benchmark，仅作度量，不据此宣称 DoD 达标 |

**偏差登记的现状**：`architect.md:112` 的 `ADR-031` 是唯一专门针对 §2.5 单项
（`contradiction judgment`）的 deviation ADR。其余 6 项的确定性实现散见于
`architect.md:31`（核心不变量 5）、`:85`（ADR-004）、`:97`（ADR-016），
**未逐项登记为 §2.5 deviation ADR**。本次**不修**，只在评估报告的「待办登记」
小节列出，实施阶段另行立项。措辞不用「偏差未登记」——那会抹掉已有的散见记录。

## 2. 当前实现差距（度量的起点，不是结论）

- `method` 字段存在：`domain/models.py:150`、`storage/tables.py:107`，
  `repositories.py:390/407` 读写齐全；但 `research/quantitative.py:157` 只赋
  `method = "proposed method" if _PROPOSED_RE.search(text) else None`
  ——**常量占位符，从不写真实方法名**。
- 7 个 scope 维度只落了部分：`identity_key` 是
  `subject|task|dataset|metric|direction|conditions|value_bucket`；
  `research/conditions.py` 只有 `backbone=`、`training=`、`degradation=`、`baseline=`。
  **model scale、evaluation protocol 无落点**，architecture 被压成 backbone 一个词。
- **一处实现偏差**（审验 I1）：计划 §15 的 `protocol` 语义应指实验/评测协议，
  但实现把它用作**数值单位**——`quantitative.py:94-105` 的 `_unit_near()` 只返回
  `"dB"` / `"percent"` / `None`（写入点 `:143`、`:192`）。因此它**不得**作为 L4
  「评测协议」的覆盖信号，见 §5。
- 方法名其实被抽到了，但在 `research/claims.py` 的 `subject`（`SELF_REFERENCE` +
  大写专有名词启发式），**没有与 `QuantitativeEvidence.method` 打通**。
- `research/lexicon.py` 的 `DATASETS`/`METRICS`/`TASKS` 全是图像复原词表。

## 3. 度量对象：4 层 × 2 领域

| 层 | 要抓什么 | 主要出处 |
|---|---|---|
| **L1 方法身份** | 方法名、缩写、别名（Voyager / STEVE / PEAM；Restormer / MPRNet） | 标题、摘要、intro 的命名句 |
| **L2 方法构成** | 架构、模块、组件、backbone、训练/推理流程 | 方法章节 |
| **L3 方法描述** | 方法在做什么、为何有效，每条带可定位出处 | 方法章节正文散文 |
| **L4 可复现设置** | baseline、超参、环境、评测协议、代码/仓库链接 | 实验章节、表格、脚注 |

拆成 4 层的理由：四者的信息出处与可抽取形态完全不同，合并度量得到的数字
无法指导后续在「补全字段」与「引入 LLM」之间做选择。

**样本**：复用已缓存的 40 篇 HTML，零下载成本、跨领域对照现成。

- 图像复原 20 篇：`docs/evaluation/holdout-ids-2026-11-12.txt`
- Agent in MC 20 篇：`docs/evaluation/holdout-ids-2026-11-14-agent-in-mc.txt`
- 不引入第三个领域，避免变量过多。

## 4. 标注协议

**单位**：`篇 × 层 = 40 × 4 = 160` 格。

每格三值之一：

| 值 | 判定标准 |
|---|---|
| `present` | 论文明确给出该层信息，且能定位到具体句 |
| `absent` | 全文未给出该层信息 |
| `ambiguous` | 只有暗示或泛泛而谈，无法定位到具体句 |

逐层的 `present` 判据，避免逐篇临场判断：

| 层 | `present` 当且仅当 |
|---|---|
| L1 | 出现方法名或缩写，且能看出它就是本文提出/评测的方法（不是纯引用前人） |
| L2 | 出现至少一个具体组件、模块、backbone 或流程步骤的描述 |
| L3 | 存在至少一句描述方法**机制或设计意图**的句子；只提到方法名不算 |
| L4 | 出现 baseline、超参、环境、评测协议、代码/仓库链接中的至少一项具体值 |

规则：

- 标 `present` 必须附**至少一处**可定位证据：`arxiv_id` + `section`（为 `None` 时
  以 `page_label` / `chunk_index` 替代） + 原句片段（≤40 字符）。
  `section` 取自 `load_html` / `chunk_pages` 产出的 chunk 章节字段，与系统侧同一套来源。
- **边界兜底**（审验 N4）：`html.py:66` 的 `_section` 初值为 `None`、仅由 heading 赋值，
  无标题 HTML 可能产出 `section is None` 的 chunk。此时按上一条替代定位，
  并在报告中标注「无标题」。「≤40 字符」指 **Unicode 字符**，
  片段须为该句内唯一可定位子串。
- `ambiguous` **不计入 present**，单独列数，不并入任何比率。把「暗示」当「给出」会抬高分母。
- 标注只回答「论文有没有给出」，**不回答「系统抽得对不对」**。
- 标注者：本会话 agent 逐篇读缓存 HTML；**owner-derived、非独立、非盲标**。
- **隔离防线**（审验 I3）：标注阶段**只读缓存 HTML 原文**，禁止查看或运行任何系统侧
  抽取产物（`claims`、`quantitative_evidence`、`identity_key`、`conditions`）及
  `scripts/method_acquisition_audit.py`。`labels.json` 定稿并冻结之后，才实现、运行
  审计脚本。`ANNOTATION.md` 首段须记录这一先后顺序，使复核者能验证 `C` 的分母
  未参照系统产出。仅有「非独立 / 非盲标 / 不算正确率」的声明不足以防止自证——
  `present` 正是 `C` 的分母，防线必须落在流程上。
- 产物：`tests/fixtures/method_acquisition/labels.json`（含 40 个 `arxiv_id`、
  每篇 4 层判定与证据片段，机器可读）与同目录 `ANNOTATION.md`（协议、逐条依据、
  诚实性声明）。脚本从 `labels.json` 的 id 列表读 `.holdout_cache/`，不需要额外 ids 参数。
- `ANNOTATION.md` 首段必须写明：这不是独立标注、不是盲标、不用于计算任何正确率或
  一致性指标；现有 `tests/fixtures/contradiction/ANNOTATION.md` 的 self-consistency
  教训同样适用。

**`labels.json` 最小 schema**（审验 N3；脚本与回归测试以此为契约）：

```json
{
  "labels": [
    {
      "arxiv_id": "2605.27762",
      "domain": "agent_in_mc",
      "layers": {
        "L1": {"label": "present",
               "evidence": [{"section": "Introduction", "page_label": null,
                             "chunk_index": null, "quote": "we introduce PEAM"}]},
        "L2": {"label": "absent", "evidence": []},
        "L3": {"label": "ambiguous", "evidence": []},
        "L4": {"label": "present", "evidence": [{"section": "Experiments",
               "page_label": null, "chunk_index": null, "quote": "lr = 3e-4"}]}
      }
    }
  ]
}
```

`label ∈ {present, absent, ambiguous}`；`label=present` 时 `evidence` 至少一条；
每条 evidence 的 `section` 为 `null` 时必须有 `page_label` 或 `chunk_index`；
`quote` ≤40 Unicode 字符。`labels` 是脚本的**唯一输入**，不另设 id 清单；
`domain` 取 `image_restoration` / `agent_in_mc` 二值；脚本须断言其中 `arxiv_id`
唯一且恰为 40 个，避免两份清单漂移。上例只示意结构，实为 40 个对象。

## 5. 系统侧覆盖的判定映射

避免在度量时临时拍脑袋，每层预先固定唯一认领对象：

| 层 | 系统侧认领对象 |
|---|---|
| L1 | 拆两个子项分开报：`structured` = `QuantitativeEvidence.method` 非 None 且不等于常量 `"proposed method"`；`proxy` = `identity_key` 第 1 段为 named method（非空、非 `self@`）。**proxy 不等于 §15 要求的结构化字段** |
| L2 | `Claim.conditions` 含 `backbone=` 或 `baseline=` |
| L3 | **无对应字段** → 系统侧恒 0，记为「结构性缺失」，与「抽错」分开描述 |
| L4 | **仅** `Claim.conditions` 含 `training=` 等具体设置值 |

**L4 不认领 `QuantitativeEvidence.protocol`**（审验 I1）：该字段存的是数值单位而非
评测协议，计入 `covered` 会把单位标记冒充为 L4 覆盖、系统性抬高 `C(L4)`，且与 §2
「evaluation protocol 无落点」自相矛盾。**该字段不参与本次度量。**

「覆盖」定义为：该篇存在至少一个可追溯到该篇、且属于上表认领对象的产出。
不使用关键词命中、章节标题猜测或任何近似信号来推断覆盖——那是用不可靠信号替代证据。

L1 的 `covered` **以 `structured` 为准**：`proxy`（claim subject）只单独列出数字，
不并入系统覆盖率，因为它不是 §15 要求的结构化 `method` 字段。把两者混为一谈
会高估当前能力。`proxy` 的呈现位置见 §6。

## 6. 三个数字（只量事实，不产出质量结论）

1. **可获取率** `A(l,d) = present(l,d) / 20`，分母恒为 20，可跨层、跨领域比较。
2. **系统覆盖率** `C(l,d) = covered(l,d) / present(l,d)`，分母是 present 篇数，不是 20。
3. **缺口分布**：按 `层 × 领域 × 成因` 的分类计数；成因只取三值
   `词表未覆盖` / `无结构化字段` / `无来源定位`。`ambiguous` **不套用三成因**，
   在缺口分布中单列计数。

口径纪律：

- `C` 的分母逐格不同，**不可跨层 / 跨领域直接比较**。报告须以
  `covered/present` 的**分数形式**呈现并同时列出 `present`、`covered` 绝对值，
  并列给出 `covered/20`（与 `A` 同分母、可直接比较）；`present < 5` 的格子
  不作趋势解读。只报裸百分比会把 `1/1=100%` 读成「覆盖充分」。
- 当 `present(l,d) = 0` 时，`C(l,d)` 记 `N/A`，**不写 0% 也不写 100%**。
- L1 额外单列 `proxy` 计数，不并入 `C`；`ambiguous` 单列，不并入任何比率。
- 本报告的「系统覆盖率 C」与项目既有的 `coverage` **不是同一指标、分母不同**，
  报告须显式声明两者无关，不重新解释既有口径。
- 报告禁止出现「准确率 / quality / agreement / 正确率」等词；本次不建 gold label，
  因此任何正确率都无从谈起。
- 既有 `coverage 100%` 的口径问题（把 scope skip 算进 `judged`）属于**另一个独立议题**，
  本次不修、不重新解释，只在评估报告的「待办登记」小节列出。

## 7. 明确不做

- 不扩 `lexicon.py` 词表、不引入 LLM 抽取器。
- 不改 `identity_key`、不改矛盾判定链、不改 `coverage` 口径、不改任何生产代码。
- 不新增第三个领域、不做第二轮独立标注（需独立标注者，不由 agent 扮演）。
- 不宣称方法抽取质量，不把 owner reference 当作评测基准。

**产物只有三项**：一个只读评估脚本 `scripts/method_acquisition_audit.py`（含其
`tests/unit/test_method_acquisition_audit.py` 回归测试）、
`tests/fixtures/method_acquisition/` 下的标注夹具（含 `labels.json` 与 `ANNOTATION.md`）、
一份评估报告 `docs/evaluation/2026-11-14-method-acquisition-audit.md`（含「待办登记」小节）。

## 8. 验收判据

- 160 格全部有 `label`；所有 `present` 格 `evidence` 非空且 `quote` 可定位；
  `ambiguous` 单独列数。
- `ANNOTATION.md` 首段声明齐全（非独立 / 非盲标 / 不用于正确率），并记录
  「先冻结 labels.json、后跑审计脚本」的隔离顺序。
- 脚本可复跑：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`，
  输出 `A` / `C` / 缺口分布、`proxy` 单列、`ambiguous` 单列；每条数字能追溯到具体 `arxiv_id`。
- 脚本对每个 `present=0` 的 (层, 领域) 必须输出 `N/A` 而非 0% / 100%，报告保留该标记。
- 报告逐层给出 `A` / `C` / 缺口分布，`C` 以 `covered/present` 分数形式并列出
  `present` / `covered` 绝对值与 `covered/20`；声明 `C` 分母逐格不同、不可跨层比较、
  `present < 5` 不作趋势解读；说明 L3 的 0 **来自结构性缺失而非抽取错误**；
  声明本报告 `C` 与既有 `coverage` 无关；设「待办登记」小节。
- **强断言**（审验 I5）：回归测试须断言 `A` / `C` / 缺口分布的具体数值，
  覆盖 `present=0 → N/A`、`ambiguous`、`proxy` 单列等分支，并断言逐 `arxiv_id`
  可追溯；删除计算逻辑后测试**必红**；禁止只查键存在或容器非空的空断言。
- **回归锁**：既有 `319 passed, 2 skipped` 保持不变；新增审计测试另计且全绿，
  最终总数 = `319 + 新增用例数`，`2 skipped` 不变。生产代码未改由
  `git diff --name-only` 核对，不把测试计数当作「生产代码未改」的证据。
- 实施按严格 TDD：先写会失败的测试、确认红灯、再写脚本；上一条的变异锚点
  是这一要求在最终产物中的可证伪形式。

## 9. 文档同步（实施阶段）

- `README.md` / `architect.md` / `human_decision.md` 同步本次新增的度量能力与诚实性口径；
  §0 的三条人类决策按 `human_decision.md` 的 HD 格式追加。
- §1 提到的「§2.5 未逐项登记 deviation ADR」与 §6 的「既有 coverage 口径」
  写入评估报告的「待办登记」小节，分别单独立项，不混进本次实施。
- 实施偏差写入本文末尾「实施偏差」表，不静默修改历史快照。
- `reports/*.md` 视为 run 产物，不手工维护。

## 10. 实施偏差

| # | 计划/设计 | 实际 | 性质与理由 |
|---|---|---|---|
| 1 | 标注一次冻结，160 格 | 首次 `424c976` 全判 present（160/0/0），经三轮独立审验修订为 `93c3174`(146/1/13)、`078dd91`(158/0/2)、`895196a`(159/0/1) | **偏差已修正并保留历史**：首次把表格标题/数据集名/竞赛名次当 L4 具体值；中间一轮误把「首条证据不合格」当成「论文没有」；最终按全文重新取证。四次提交均未改写历史（ANNOTATION.md 中的 160/160 为 present/total 二元组记法，与此处 160/0/0 同指首次判读。） |
| 2 | spec §4 未规定 `cause_for` 判定逻辑 | 实现为 `empty→无来源定位` / `L2→词表未覆盖` / 其余 `无结构化字段` | 实施细化，测试用三成因断言锁定 |
| 3 | spec §6 的 `A` 分母写死 20 | `summarise` 的 `domain_size` 默认 `None`，按 labels 逐域计数；合成夹具显式传 2 | 实施细化（真实语料两域各 20，结果一致） |
| 4 | 计划 Task 4 Step 2 未传 `require_full_corpus` | 真实入口 `load_labels(..., require_full_corpus=True)`，断言 40 篇且双域齐备 | 实施细化（spec §4 要求） |
| 5 | 计划脚本的 `CACHE` 为 CWD 相对路径 | 改为 `Path(__file__).resolve().parents[1] / ".holdout_cache"` | 审验后修正，恢复 CWD 无关，计划片段已由 d30e5ec 同步修正 |
| 6 | 计划 Task 3 写「预期 8 passed」、Task 2 gaps 写 `sum==3` | 实际 7 条测试、合成夹具 gaps 断言 4 项；真实语料缺口分布见评估报告 §3 八行（合计 105）；计划已分别提交 `4fbec17`、`749437b` 修正 | 计划算术/计数笔误，已修 |
| 7 | 计划 Task 4 生成脚本直接打印含 `\|` 的 gaps 键 | 改为 `k.replace('\|', '·')`，报告 §3 八行同步 | 审验发现 GFM 表格渲染错乱，已修，计划片段已由 03f0fca 同步修正 |
| 8 | spec §8 要求 `present=0 → N/A` 有验收覆盖 | 真实夹具最小 `present=19`，该分支**不在真实数据触发**，只由合成夹具验证 | **未完全满足，已如实写入 ANNOTATION 与评估报告 §4**，不做假验收 |
| 9 | spec §1 记 §2.5 为「7 项」、ADR-031 覆盖 1 项 | 其余语义判断场景的确定性实现未逐项登记 deviation ADR | 未偿，独立立项 |

任何后续偏差继续追加到本表，不静默修改本文已写定的口径与历史快照。
