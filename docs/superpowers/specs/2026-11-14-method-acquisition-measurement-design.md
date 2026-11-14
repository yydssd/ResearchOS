# 方法获取能力度量设计（2026-11-14）

> 背景：以 `Agent in MC`（Minecraft 智能体）为主题的 20 篇全新留出集跑完后，
> 定量通道整体归零（`quantitative` 170 → 0）、`task` 标题继承 98.2% → 23.4%、
> P5 判定 30 → 0。复审权威计划 `ResearchOS-Implementation-Plan.md` v1.1 后确认：
> 计划把「方法」列为**独立于数值**的结构化能力，而当前实现从未真正建成。
> 本文只设计**一次只读度量**，不实现任何抽取能力。

## 0. 决策记录

| 项 | 结论 | 来源 |
|---|---|---|
| 「方法获取」的范围 | **(b) 广义**：方法身份 + 方法描述 + 实现细节 + 可复现实验设置，不止可比较的结构化身份 | 用户 2026-11-14 确认 |
| 路径 | **C 先度量**：先量现状，再决定「最小补全」还是「按 §2.5 引入 LLM」 | 用户 2026-11-14 确认 |
| 标注基准 | **选项 1**：owner-derived reference，显式声明非独立、非盲标；只算可获取率与覆盖率，**不算正确率** | 用户 2026-11-14 确认 |

## 1. 计划依据

| 位置 | 要求 |
|---|---|
| §15 Phase 3（`md:841-856`） | `QuantitativeEvidence` 必须有 `method: str \| None`，与 dataset/metric/value/comparator/protocol 并列，理由是 "avoid invalid cross-paper comparisons" |
| §16 Phase 4（`md:871-881`） | 主张不得因措辞相近合并，须按 7 个维度区分：dataset · task · metric · **architecture** · **training setup** · **model scale** · **evaluation protocol** |
| §2.5（`md:184-192`） | `evidence extraction`、`claim normalization`、`scope comparison`、`contradiction judgment` 均列为需要语义判断、应使用 LLM 的场景 |
| §2.6 / §21 | 每个能力引入时须有 fixtures 与 measurable tests；但 §21 现有指标清单里**没有方法抽取指标** |
| §19（`md:955-981`） | Falsification 要 "inspect source code when relevant"、检查参数量与消融——属于可复现设置层 |
| §30 | `evidence extraction` 排第 4、`claim synthesis` 排第 11：方法获取是地基，不是后续加分项 |

**已登记的偏差**：`ADR-031` 只覆盖 `contradiction judgment` 一项，而 §2.5 列了四项。
`evidence extraction`、`claim normalization`、`scope comparison` 同样是确定性正则，偏差未登记。
本次**不修**，只在报告里记为待登记项，实施阶段另行处理。

## 2. 当前实现差距（度量的起点，不是结论）

- `method` 字段存在：`domain/models.py:150`、`storage/tables.py:107`，repo 读写齐全；
  但 `research/quantitative.py:157` 只赋 `method = "proposed method" if _PROPOSED_RE.search(text) else None`
  ——**常量占位符，从不写真实方法名**。
- 7 个 scope 维度只落了部分：`identity_key` 是
  `subject|task|dataset|metric|direction|conditions|value_bucket`；
  `research/conditions.py` 只有 `backbone=`、`training=`、`degradation=`、`baseline=`。
  **model scale、evaluation protocol 无落点**，architecture 被压成 backbone 一个词。
- 方法名其实被抽到了，但在 `research/claims.py` 的 `subject`（`SELF_REFERENCE` + 大写专有名词
  启发式），**没有与 `QuantitativeEvidence.method` 打通**。
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

- 标 `present` 必须附**至少一处**可定位证据：`arxiv_id` + `section` + 原句片段（≤40 字符）。
  `section` 取自 `load_html` / `chunk_pages` 产出的 chunk 章节字段，与系统侧同一套来源。
- `ambiguous` **不计入 present**，单独列数，不并入任何比率。把「暗示」当「给出」会抬高分母。
- 标注只回答「论文有没有给出」，**不回答「系统抽得对不对」**。
- 标注者：本会话 agent 逐篇读缓存 HTML；**owner-derived、非独立、非盲标**。
- 产物：`tests/fixtures/method_acquisition/labels.json`（含 40 个 `arxiv_id`、
  每篇 4 层判定与证据片段，机器可读）与同目录 `ANNOTATION.md`（协议、逐条依据、
  诚实性声明）。脚本从 `labels.json` 的 id 列表读 `.holdout_cache/`，不需要额外的 ids 参数。
- `ANNOTATION.md` 首段必须写明：这不是独立标注、不是盲标、不用于计算任何正确率或
  一致性指标；现有 `tests/fixtures/contradiction/ANNOTATION.md` 的 self-consistency
  教训同样适用。

## 5. 系统侧覆盖的判定映射

避免在度量时临时拍脑袋，每层预先固定唯一认领对象：

| 层 | 系统侧认领对象 |
|---|---|
| L1 | 拆两个子项分开报：`structured` = `QuantitativeEvidence.method` 非 None 且不等于常量 `"proposed method"`；`proxy` = `identity_key` 第 1 段为 named method（非空、非 `self@`）。**proxy 不等于 §15 要求的结构化字段** |
| L2 | `Claim.conditions` 含 `backbone=` 或 `baseline=` |
| L3 | **无对应字段** → 系统侧恒 0，记为「结构性缺失」，与「抽错」分开描述 |
| L4 | `Claim.conditions` 含 `training=`，或 `QuantitativeEvidence.protocol` 非 None |

「覆盖」定义为：该篇存在至少一个可追溯到该篇、且属于上表认领对象的产出。
不使用关键词命中、章节标题猜测或任何近似信号来推断覆盖——那是用不可靠信号替代证据。

L1 的 `covered` **以 `structured` 为准**：`proxy`（claim subject）只单独列出数字，
不并入系统覆盖率，因为它不是 §15 要求的结构化 `method` 字段。把两者混为一谈
会高估当前能力。

## 6. 三个数字（只量事实，不产出质量结论）

1. **可获取率** `A(l,d) = present(l,d) / 20`
2. **系统覆盖率** `C(l,d) = covered(l,d) / present(l,d)`，分母是 present 篇数，不是 20
3. **缺口分布**：按 `层 × 领域 × 成因` 的分类计数；成因只取三值
   `词表未覆盖` / `无结构化字段` / `无来源定位`

口径纪律：

- 当 `present(l,d) = 0` 时，`C(l,d)` 记 `N/A`，**不写 0% 也不写 100%**。
- 报告禁止出现「准确率 / quality / agreement / 正确率」等词；本次不建 gold label，
  因此任何正确率都无从谈起。
- `coverage 100%` 的既有口径问题（把 scope skip 算进 `judged`）属于**另一个独立议题**，
  本次不修、不在本报告中重新解释，只在「待办」里登记。

## 7. 明确不做

- 不扩 `lexicon.py` 词表、不引入 LLM 抽取器。
- 不改 `identity_key`、不改矛盾判定链、不改 `coverage` 口径、不改任何生产代码。
- 不新增第三个领域、不做第二轮独立标注（需独立标注者，不由 agent 扮演）。
- 不宣称方法抽取质量，不把 owner reference 当作评测基准。

**产物只有三项**：一个只读评估脚本 `scripts/method_acquisition_audit.py`（含其
`tests/unit/test_method_acquisition_audit.py` 回归测试）、
`tests/fixtures/method_acquisition/` 下的标注夹具、
一份评估报告 `docs/evaluation/2026-11-14-method-acquisition-audit.md`。

## 8. 验收判据

- 160 格全部有判定；所有 `present` 格都有定位证据片段；`ambiguous` 单独列数。
- `ANNOTATION.md` 首段的诚实性声明齐全（非独立 / 非盲标 / 不用于正确率）。
- 脚本可复跑：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`，
  输出三层数字，且每条数字能追溯到具体 `arxiv_id`。
- 报告逐层给出 `A` / `C` / 缺口分布，并区分 L3 的「结构性缺失」与「抽错」。
- 不改生产代码，因此全量 `pytest` 仍是回归锁：319 passed, 2 skipped。
- 实施按严格 TDD：先写会失败的测试，确认红灯，再写脚本。

## 9. 文档同步（实施阶段）

- `README.md` / `architect.md` / `human_decision.md` 同步本次新增的度量能力与诚实性口径。
- §1 提到的「ADR-031 覆盖面不足」单独立项登记，不混进本次。
- 实施偏差写入本文末尾「实施偏差」表，不静默修改历史快照。
- `reports/*.md` 视为 run 产物，不手工维护。

## 10. 实施偏差

本文目前只包含设计，尚无实施。任何与本文的偏差在实施阶段追加到本节的表中，
不静默修改本文已写定的口径与历史快照。
