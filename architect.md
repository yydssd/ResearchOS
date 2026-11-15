# ResearchOS — 架构说明（Architecture Snapshot）

> **用途**：当前架构的一目了然快照，随项目进展时刻维护。
> **权威计划**：`ResearchOS-Implementation-Plan.md`（v1.1，另有 HTML 版）。本文件只沉淀"当前事实 + 决策"，不复制计划全文。
> **维护规则**：架构或进度每次变化，必须同步更新本文，并在文末「维护记录」追加一行；人类方向性决策记入 `human_decision.md`。

---

## 当前状态（2026-11-13 · W3 / P5 完成）

- **阶段**：P0 ✅ · P1 ✅ · P2 ✅ · P3 ✅ · P4 ✅ · **P5 Contradiction ✅**
- **验收结果**：`pytest` 326 passed（+2 opt-in 真实网络）；主张带七维 `identity_key`，矛盾评估带 run 作用域、唯一约束与可定位证据
- **格式覆盖**：PDF · Markdown · README · HTML（含 ar5iv 全文；公式回声已净化）
- **实测口径**：留出集 20 篇 / 13871 块 / 4814 证据 / 1173 主张（1075 支撑）；P5 候选对 1049 → 判定 30（真矛盾 0，预期）；夹具 26 对全通过
- **下一步**：P6 Research Memo（结构化 memo 收口），再 P7 Falsification
- **P5 的诚实边界**：真矛盾在真实语料上不可观测；夹具标注与规则同源，100% 只能当回归锁；
  代码审查发现并修了白名单门控、run 作用域泄漏、可复现 harness 等 6 项，剩余 5 项待办见
  `docs/evaluation/2026-11-13-p5-review.md`

## 架构定位

> 可度量、可追溯的技术/科研研究系统：结论 → 主张 → 证据 → 权威来源，链断即标 unsupported。
> **reliability · measurability · traceability 优先于 autonomy**；不做聊天机器人，不做多智能体角色扮演。

## 核心不变量（6 条）

1. 证据 ≠ 主张：Source/Evidence/Claim/Hypothesis/Decision 永不合并（P2 新增第三种对象 **SourceCandidate**，同样不可冒充证据）
2. 主要结论必可追溯：finding→claim→relation→evidence→chunk→source version→位置；**证据无位置即拒收**（P3）
3. 状态显式持久化（17 类，含候选、分块、定量证据），聊天记录不是主状态
4. 数据库是唯一事实源，LLM 只收受控上下文视图
5. 确定性代码优先于 LLM（P2 规范化/聚类/核验、P3 分块/偏移/定量抽取全部零 LLM）
6. 评估从第一天开始：能力上线即带 fixtures + 可测测试

## 技术栈

Python 3.12+（conda `reOS` 环境）· FastAPI · Pydantic v2 · SQLAlchemy · SQLite · pytest · httpx · PyMuPDF
（避免：Neo4j / 向量库 / agent 框架 / 队列 / 复杂前端 —— 直到有可度量需求）

## 领域模型（8 个对象）

`ResearchQuestion` · `ResearchWork`（一作多版本）· `SourceVersion`（verified + `source_tier`）· **`SourceCandidate`（发现候选，独立表）** · `Evidence`（必带来源位置）· `Claim`（6 状态 + 4 置信标签）· `ClaimEvidenceRelation`（5 类关系）· `ContradictionAssessment`（5 类关系）

## 包结构（P2 `sources/` · P3 文档与证据层 · P4 主张层）

| 模块 | 职责 | LLM？ |
|---|---|---|
| `sources/normalize.py` | DOI / arXiv / 标题 / 作者纯函数规范化、相似度 | 否 |
| `sources/query.py` | 确定性关键词查询生成（+1 survey 变体） | 否 |
| `sources/providers.py` | `SearchProvider` 协议 + arXiv/Crossref/OpenAlex/Fixture；解析函数与传输分离 | 否 |
| `sources/resolver.py` | 候选聚类 → canonical work、版本合并、歧义拒绝合并 | 否 |
| `sources/verification.py` | verified 四条件 + `SourceTier` 标注 | 否 |
| `sources/discovery.py` | 纯发现循环：预算钩子、故障容错、候选去重 | 否 |
| `documents/loader.py` | PDF / Markdown / README 加载 + 后缀分派 | 否 |
| `documents/html.py` | HTML 加载（stdlib parser；优先 `<main>`/`<article>` 内容） | 否 |
| `documents/chunks.py` | 溯源分块（page/section/chunk_index/content_hash） | 否 |
| `research/evidence_extractor.py` | 原文区间切句 → 证据 + 精确 char 偏移 + `has_location` 校验 | 否 |
| `research/quantitative.py` | 定量证据抽取（指标/数值/数据集/对照/单位 + 无指标词 delta） | 否 |
| `research/scope.py` | 块级 task / dataset 继承（章节标题 + 节内首个点名句），带 provenance | 否 |
| `research/claims.py` | 主张 identity 七维、合并门槛、状态与质量 flag | 否 |
| `research/claim_builder.py` | identity → 分组 → 每条证据一条 SUPPORTS | 否 |
| `research/lexicon.py` | 数据集 / 指标 / 任务词表 + 第三方标识 | 否 |

## 流水线（v4）

```
Question → 查询生成 → Provider[] → SourceCandidate → 规范化 → 去重/合并
        → canonical Work + SourceVersion[] → 核验
        → 加载（PDF/MD/HTML/README）→ 分块（落库）→ 证据（精确偏移 + 位置校验）
        → 定量证据 → 块级 scope → 主张 identity → 合并 → 状态/质量 flag
        → 关系 → 矛盾 → Memo（Scope / Conditions / Grounding / Kept Separate）
```

## 编排

9 种任务类型 · Run 状态机 `CREATED→…→COMPLETED`（含 FAILED/PAUSED）· 动态任务图，允许回退搜索
Supervisor 独占预算（`search_calls` / `sources_discovered`）与事件；provider 失败记 `FAILURE` 而不中断整轮。

## 架构决策（ADR）

| ID | 决策 | 状态 |
|----|------|------|
| ADR-001 | 以计划 v1.1 为权威基线 | ACTIVE |
| ADR-002 | 技术栈：Python 3.12+/FastAPI/Pydantic v2/SQLAlchemy/SQLite/pytest/httpx/PyMuPDF；不加重基建 | ACTIVE |
| ADR-003 | 数据库为唯一事实源（轻量 ResearchRun + 受控 ContextView） | ACTIVE |
| ADR-004 | 确定性代码优先；prompt 版本化 | ACTIVE |
| ADR-005 | 按 17 步开发顺序推进，不跳 Step 17 | ACTIVE |
| ADR-006 | 先垂直切片（本地论文），再接实时搜索 | ACTIVE（P1 已满足，P2 接续实时搜索） |
| ADR-007 | 评估前置，首要指标 unsupported claim rate | ACTIVE |
| ADR-008 | W1 实现细节：LLMProvider 协议 + 确定性启发式 extractor/claim builder；SourceVersion/Claim 加 run_id；句子切分保护小数点 | ACTIVE |
| ADR-009 | 源层独立为 `sources/` 包；候选落独立表 `source_candidates`，结构上杜绝摘要变证据 | ACTIVE |
| ADR-010 | 测试默认离线：录制真实报文 + `httpx.MockTransport` 回放；真实网络测试由 `RESEARCHOS_NETWORK_TESTS=1` 开启 | ACTIVE |
| ADR-011 | SQLite 用幂等加列迁移（`PRAGMA table_info` + `ALTER TABLE`），暂不引入 Alembic | ACTIVE |
| ADR-012 | 标题相似但作者冲突时**不合并**，标 `SOURCE_IDENTITY_AMBIGUOUS`（宁可多一个 work，不制造错误身份） | ACTIVE |
| ADR-013 | arXiv 查询不用整句短语（会零召回），改为逐词 AND，并取头部 2 + 尾部 3 词元（句中修饰词如 "help/ordinary" 会把交集打到 0）；实测三种问题 33/48/168 条且首条相关 | ACTIVE |
| ADR-014 | HTML 用标准库 `html.parser`（偏差于计划 §5 的 bs4），规则：跳过 script/style/nav/footer/header/aside/form，存在 `<main>`/`<article>` 时只收其内部块；真实 arXiv abs 页验证可用，若遇到 readability 级需求再引入 bs4 | ACTIVE |
| ADR-015 | 分块必须落 `chunks` 表：`Evidence.chunk_id` 若指向未持久化的块，追溯链在进程结束即断 | ACTIVE |
| ADR-016 | 定量证据独立成表（`evidence_id + seq` 复合标识），抽取用确定性正则；单位按数值**紧邻**判定，避免给 SSIM 误标 dB | ACTIVE |
| ADR-017 | 位置缺失的证据不入库，记 `CITATION_LOCATION_MISSING` 事件并写入 warnings（§2.2：链不完整必须显式标记，不得静默通过） | ACTIVE |
| ADR-018 | 证据必须是**完整句子**（结尾为 `.!?`，允许其后紧跟引号/括号）。网页里大段导航标签是"长而无句界"的文本，任何长度阈值都拦不住，只有句界判据能把它与散文分开；实测 arXiv abs 页 19→10 条证据，偏移仍逐字成立 | ACTIVE |
| ADR-019 | 追溯类输出（`claims`、`sources`、`inspect-claim`）一律按 `run_id` 作用域查询，禁止全库 `list_all()` 兜底；跨 run 聚合会让一个研究问题的结论混进另一个的审计链 | ACTIVE |
| ADR-020 | 主张的 task / dataset 从**块级上下文**继承（章节标题 + 节内首个点名句），不只从句子抽。实测：10 篇文档 215 条主张，单句完整 identity 命中 0 条；task 单句 17%、继承标题后 50% | ACTIVE |
| ADR-021 | `value_bucket` 进入 identity，数值不一致不合并。合并同键异值会让一条主张内部出现两个矛盾数值，P5 的"比较两条主张"输入模型就再也看不到这个分歧——去重成功、矛盾信号被消灭 | ACTIVE |
| ADR-022 | `UNSUPPORTED` 只表示"无支撑证据"（推测/未来工作）；"有证据但数值未结构化 / 范围不可判定 / 比较无对照"一律 SUPPORTED + LOW + 命名 flag。否则 unsupported 会退化成"低置信度"的同义词 | ACTIVE |
| ADR-023 | **参考文献章节整节剔除**（`References` / `Bibliography`，含罗马数字或阿拉伯数字编号变体）。20 篇留出集里 bibliography 贡献 1889/6703 条证据（28%），28 条还成了主张（`[13] Hadsell, R., …`）。参考文献条目是**别人的标题**，不是本文论断；附录不剔除（含真实实验） | ACTIVE |
| ADR-024 | task 增加**文档级兜底**：章节标题不含任务名时，取文档自身的 task，**优先从摘要读**（后续章节可能研究第二个任务，不能反过来定义论文）。dataset 不做文档级兜底——那是猜不是 scope。20 篇实测：task 有值 11% → 98% | ACTIVE |
| ADR-025 | 推断出的 `self` 主语标记 `subject_inferred`，但**不改变合并键**（flag 是 provenance 不是 identity）。留出集 459 条 self 中 409 条为推断（**P5 重测为 476 / 425**，见维护记录），抽样 12 条仅 2 条真是 `our method`；默认保留（绑文档 id，不会跨文档合并），但下游需能区分"本文声称"与"本文假设" | ACTIVE |
| ADR-026 | `direction` 改为四值，语义是**主张对质量的结论**而非数值移动：`UP`（声称变好）/`DOWN`（声称变差）/`LEVEL`（明确说没有改善）/`None`（只报数值）。`reduce`/`increase` 按**宾语极性**定性（`reduces error`→UP，`reduces PSNR`→DOWN）；否定式先判（`fails to improve`→LEVEL）。旧三值把 `achieves/reaches/reports` 归入 `LEVEL`，留出集 196 条 LEVEL **全部**是这种形式，导致「提高 PSNR」与「报告 30 dB」被判成相反方向。代价：合并门槛 111→73（direction 无值不再满足门槛） | ACTIVE |
| ADR-027 | 实验条件扩为四类（`backbone`/`degradation`/`baseline`/`training`），每类**最多一个值**、**不设默认**、值小写归一；并允许**块级继承**（heading → 节内首个提及），继承必须记 provenance。单句覆盖 2.6% → 四类 13.4% → 加继承 69.1%（heading 仅 5.1%）。继承是"本节有人这么说过"，不是"这条主张用了它" | ACTIVE |
| ADR-028 | 条件相等**分两级**（见 HD-014）：provenance 为 `sentence`/`heading` 时可支持 `TRUE_CONTRADICTION`；为 `section-first-mention` 时不可，降 `INSUFFICIENT_EVIDENCE`。错误是不对称的——继承条件**不相等**仍可否证相同，只有**相等**不可信。用"跳过对比句"的正则收窄只能从 69.1% 降到 62.9% 且会误跳正常设置段，故在判定层而非抽取层区分 | ACTIVE |
| ADR-029 | 配对键为 **subject + task**，不要求 dataset 相同：计划 §17 的 scope 差异范例两条主张 dataset 不同，要求 dataset 相交会让该范例不可配对。`self@` 只允许同一文档内配对（两篇论文的"our method"是两个方法），且需双方都有 dataset 与 metric（预过滤 6177→16）。`MAX_PAIRS=50_000`，截断必须报截断前总量与覆盖率 | ACTIVE |
| ADR-030 | 矛盾评估落库**按 run 作用域**（承接 ADR-019）：`(claim_a_id, claim_b_id)` 唯一索引、`list_by_run` 读取、`replace_for_run` 先删后写使重跑收敛；跨 run 主张对拒收（`cross_run_pair`）。行 id 原为 `con_<a[:10]>_<b[:10]>`，截断会让两对不同的主张撞主键；2026-11-14 起改为 `con_` + sha1 摘要前 16 位（ADR 见维护记录），唯一性仍声明在列上而不是靠主键 | ACTIVE |
| ADR-031 | P5 的矛盾判定用**确定性级联**，不走 LLM，尽管计划 §2.5 把 contradiction judgment 列在「LLM 适用场景」里。理由：判定输入是已落库的七维 identity，输出是五选一的关系，取值空间可枚举；确定性实现让同一输入必然得出同一结论，也让「这条为什么被判成矛盾」能在代码里逐行指出。换 LLM 的入口留在 `ContradictionAssessor` 协议上，P8 需要时替换实现，supervisor 不用改 | ACTIVE |
| ADR-032 | 评估工具放 `scripts/`（`holdout_claim_quality.py`、`holdout_contradiction_quality.py`、`evaluate_contradiction.py`、`compare_annotation_sheet.py`），不建计划 §6 里的 `evaluation/` 包。理由：四者都是离线一次性分析，不被 runtime 引用；建包会把它们变成公开 API，需要版本与稳定性承诺，而当前没有第二个消费者 | ACTIVE |

| ADR-033 | `QuantitativeEvidence` 的**单位**从 `protocol` 拆出为 `unit`（见维护记录 2026-11-15）。计划 §15 给 `protocol` 的语义是**评测协议**，而实现把 `dB`/`percent` 存在该字段里：`value_bucket` 因此产出 `dB:0.44` 这类「伪协议」标签，`inspect_claim` 也把单位当协议报给调用方。拆分**不改变**任何渲染输出与 `value_bucket` 标签（ADR-021 的合并键稳定），`protocol` 在 S4 之前保持为空——空字段比如实标注的错字段更容易被发现 | ACTIVE |
| ADR-034 | 方法获取的 L1/L2/L4 走**确定性**模式（设计 §6），L3 描述留给 LLM（S3）。理由：名字/组件/设置是模式匹配，同一篇文档必须得出同一结果，否则 `MethodProfile` 无法作为 `QuantitativeEvidence.method` 的归因依据；而「这段在讲方法机理」是语义判断，正则必然做不好。为了让「没抽到」可观测，`MethodProfile.missing_layers` **落库**：空字段与未抽取在数据里必须不同形。审计脚本同步改为读 `MethodProfile`——否则新字段坏掉也能验收通过 | ACTIVE |
| ADR-035 | L3 走 LLM，但**只产要点、不产名字/设置**；模型输出先落 `MethodPointDraft`（宽松）、再过 `validate_description` 四道防线成 `MethodPoint`（严格）。理由：一是名字/设置已由确定性路径负责（ADR-034），让模型写名字等于把未经验证的字符串放进归因字段；二是把「宽松解析」与「严格校验」分开，才可能用 fake 输出把四条失败路径各测一遍。预算改为「先查后加」——`llm_calls` 此前全仓库无写入点，上限是装饰 | ACTIVE |
| ADR-036 | `conditions` 的内部表示改为 `dict[kind] -> value` + `dict[kind] -> tier`，`identity_key` 仍是 7 段、第 6 段仍排序拼接；矛盾判定只对**两侧共有**的 kind 要求 tier 确认。理由：S4 新增的 `scale=` / `protocol=` 是高频模式，整条覆盖会让一句 `5-shot` 抹掉继承来的 `training=`（覆盖率直接下降），并把 tier 升到 `sentence`，从而允许一个没有依据的 `TRUE_CONTRADICTION`。代价：旧库里的 `conditions_from=<tier>` 不再被读（按未确认处理），登记为已知限制 | ACTIVE |
| ADR-037 | L3 的 provider 走**一个** OpenAI 兼容客户端（`llm/openai_compat.py`），base_url/model/key 全走配置；JSON 模式、单次尝试、错误上抛 | 多 vendor 支持不该变成多客户端：同一份 JSON 契约下，换 vendor 只是换 base_url。不做重试，因为重试会花掉 supervisor 没计数的调用（设计 §7.3）；**不内置价格表**——价格是配置不是常量，`price_per_million` 未设时 `last_cost_usd` 保持 None，supervisor 就不回填成本，而不是按一个猜出来的单价收费 | ACTIVE |

## 阶段状态

| Phase | 周 | 内容 | 验收 | 状态 |
|-------|----|------|------|------|
| P0 Foundation | W1 | 脚手架·模型·SQLite·repository·LLMProvider·事件·health | pytest 全绿 + /health 200 | ✅ DONE |
| P1 Vertical Slice | W1 | 本地论文→证据→主张→memo | 6 主张（4 SUPPORTED/2 UNSUPPORTED）·链可查 | ✅ DONE |
| P2 Source Discovery | W2 | 搜索抽象·规范化·版本合并·canonical work·核验 | 真实跑 26 候选/23 works；arXiv+会议版合并；verified 可分 | ✅ DONE |
| P3 Evidence Quality | W2 | 多格式加载·分块落库·精确偏移·定量证据 | 分块带溯源；证据偏移逐字可验证；定量成表 | ✅ DONE |
| P4 Claim Synthesis | W3 | 块级 scope·identity 键·按身份合并·支撑性标记 | Rain100H/SIDD 不合并；跨源同值合并；4 SUPPORTED/2 UNSUPPORTED | ✅ DONE |
| P5 Contradiction | W3 | 四值方向·四类条件与继承·候选配对·级联判定·run 作用域落库 | 26 fixtures 全通过（回归锁，非独立验证）；留出集 1049 候选对 → 30 判定，真矛盾 0（预期） | ✅ DONE |
| P6 Research Memo | W3 | 结构化 Markdown memo | 主要发现带引用 | TO DO |
| P7 Falsification | W4 | 反证搜索·负消融（证伪导向） | 对重要主张执行 | TO DO |
| P8 Evaluation | W4 | Baseline A/B vs ResearchOS 基准 | 5 项指标+成本 | TO DO |

## 接口

HTTP：`POST /research` · `GET /research/{run_id}` · `/report` · `/claims` · **`/sources`**
CLI（主接口）：`research-os run/status/claims/report/inspect-claim` · **`discover/sources`**

## 已知限制（P2/P3，数字已按 P5 重测口径更新）

1. 发现只保证身份可核验，不保证主题相关（查询为确定性关键词；相关性/改写属 P7）。
2. 作者元数据缺失时按标题合并，可能把同名不同作合并（当前 22 个 work 中暂无此例，但机制上可能）。
3. Crossref 会把 SSRN/Research Square 预印本挂到 `WEB` tier（有 DOI 无 venue），排序时低于正式发表。
4. PDF 章节标题未识别（section 为空），仅页级溯源；需字体启发式，误判风险高，留待后续。
5. 句子切分对 `et al. 2023` 这类缩写会误判句界；分块/分页处被截断的半句因无句界会被丢弃（宁可漏收，不可错收）。
6. 通用网页的**散文档**站点文案（如 arXivLabs 说明段，本身是完整句子）仍会入证据；标签碎片已由句界判据挡掉，剩下的是主题相关性问题，属 P7。
7. 定量抽取只认 ASCII 指标词与数字，表格结构不还原；无指标词的增益已由 `delta` 通道覆盖（P4），但表格与图注中的数值仍抽不到。
8. 跨源合并在真实语料上几乎不触发：需要同一方法在同一数据集上被他人复现。验收证据来自 `tests/fixtures/claim_merge/`，不来自真实论文。
9. `SELF` 默认依赖第三方标识黑名单（previous/baseline/SOTA…），漏判会把前人方法的结果算到本文方法头上；相关通道只会降置信，不会纠正归属。20 篇实测 476 条 self 中 425 条是**推断**而来（标 `subject_inferred`），抽样 12 条仅 2 条为真自指，其余是机理描述与图注。
10. 段落级回指只覆盖"段首点名"一种；代词与别名指代抽不到。
11. **dataset 是主张层的瓶颈**：82% 的主张拿不到 dataset（论文用 "this dataset" / "Table 2" 指代），合并门槛满足率 7%（P5 前置修正后重测；原为 83% / 10%）。补齐需要表格解析或代词消解，不属 P4/P5。
12. 跨源合并实测不触发：20 篇里 73 个可合并键，跨文档命中 0 组。验收靠构造夹具，不靠真实论文。
13. `QuantitativeEvidence.protocol` 自 2026-11-15 起为空：单位已迁到 `unit`（ADR-033），评测协议要等 S4。读到空的 `protocol` 是**已知**状态，不是抽取失败。
14. 方法 L1/L2 在 agent_in_mc 上仍有残差：`lexicon.py` 只有图像复原词表，S2 只铺了 `patterns.py` 的领域组结构（`DOMAINS` 为空）。扩 MC 词表是独立立项，不在四阶段内。
15. 一篇多方法只收一个 `name`，其余进 `aliases` 并记 `METHOD_MULTI_NAME`；同层同 chunk 并列时 `name` 留空并记 `METHOD_NAME_AMBIGUOUS`。**归属没有解决**，只是不再假装解决了。`MineCollab` 这类「是产物但严格说是 benchmark」的边界项按同一规则收下。
16. L1 只认命名句式：名字只写在图注/标题里的论文（留出集 `2310.18293`，真名 `UtilityIR` 只出现在 "Overview of proposed UtilityIR"）抽不到，`missing_layers` 记为 `["L1"]`。`QuantitativeEvidence.method` 的第三方名可能是片段（`Liquid-Mamba`、`CEA-IR-S`），按设计 §10.3 只报行级覆盖率，**不宣称精度**。行级实跑：170 行里 100 行有 `method`，其中 36 行等于解析名字。
17. **L3 现已测量，但是单一模型单次录制**：40 篇录制在 `tests/fixtures/method_descriptions/`（`deepseek-flash`，42 次调用，173 KB），覆盖 `19/20` 与 `20/20`。三点限制写清：① 换模型或改 prompt 就是另一份数据——录制键是 prompt 摘要，改 prompt 会让旧录制全部 miss；② 一次录制不等于稳定（`2506.22736` 空答复、两篇首测漏 `chunk_id`）；③ 没有人工抽查，四道防线只保证可定位，不保证说得对。
18. 四道防线是**形式判据**：`quote` 能定位、`statement` 与它有词重叠，不等于 `statement` 说得对。2026-11-15 做了一次 20 条盲评（`docs/evaluation/2026-11-15-l3-description-coverage.md` §7）：`supported` 15 / `partial` 5 / `unsupported` 0。**这是 LLM-as-judge，不是人工标注**——判断者与被评对象都是模型，有宽容倾向，不能替代人；75% 只代表这 20 条的支持率，不是准确率。失败集中在「补全引文没有的主语或结论」，这是可行动的缺陷，不是统计噪声。
18b. **「陈述实词必须出现在引文里」这条自动检查试过、不采用**：20 条标定里最严一档仍误伤 33%（忠实改写会换词，而泛化是「少词」、规则只看「多词」）。要可重复地测「说得对不对」，只能把盲评放进流水线，那是一次额外的模型调用/篇——是度量，不是产品行为。记录在 `2026-11-15-l3-description-coverage.md` §8。
19. 存量数据库里的 `conditions_from=<tier>` 标记**不迁移**：S4 起读 `condition_tier=<kind>:<tier>`，旧行按「没有已确认 kind」处理。这是安全方向（不会凭空产生矛盾），但意味着**旧 run 的评估结果不能与新 run 直接比矛盾数**。
20. provenance 按 kind 之后，`identity_key` 第 6 段仍可能出现「同一句在不同 section 下 key 不同」的情况——继承是按 kind 补齐的，但 section 不同则继承值不同。这不是缺陷，是 ADR-027 的「继承即 section 上下文」原样延续。
21. S4 报告里 `identity_key` 唯一数 / 合并组数**没有 before**：既有报告没有这两个指标，本轮未新增采集脚本，因此只以「主张数 / 合并门槛 / 候选对」三格并列代替，不虚构 before。

## 维护约定（代码注释规则）

1. 每个模块保留模块级 docstring：说明职责 + 关联计划条目（如 `plan §15`）。
2. 每个公共类 / 公共函数保留 docstring：做什么 + 关键约束（为什么这么做）。
3. 非显然的实现细节必须用注释说明原因（如小数点句子切分保护、run_id 归属、幂等加列迁移、歧义不合并）。
4. 修改代码时必须同步更新受影响的 docstring 与注释；新增文件必须带模块 docstring。
5. 注释与代码一致、不写废话；注释语言与代码一致（英文），文档（README/架构）用中文。

## 维护记录

| 日期 | 变更 |
|------|------|
| 2026-10-18 | 建档：按计划 v1.1 初始化快照与 ADR-001~007；确立时刻维护规则（本次重写为一目了然快照式） |
| 2026-10-18 | W1 完成：P0+P1 DONE（23 tests / uvicorn 200 / 垂直切片 6 主张）；新增 ADR-008；环境改用 conda reOS（HD-005） |
| 2026-10-18 | 补全公共接口 docstring（cli/main/chunks/tasks/loader）；确立代码注释维护规则（HD-006） |
| 2026-11-12 | W2/P2 完成：新增 `sources/` 包（normalize/query/providers/resolver/verification/discovery）、`SourceCandidate` 对象与表、`source_tier` 幂等迁移、supervisor 发现编排、CLI `discover/sources`、API `/sources`；测试 23→80；ADR-009~012 |
| 2026-11-12 | 小测发现并修复 arXiv 零召回缺陷（整句短语搜索 → 逐词 AND + 头2尾3 词元，ADR-013）；测试 80→83；真实小规模复测 15 候选/12 works/2 合并 |
| 2026-11-12 | W2/P3 完成：HTML 加载（stdlib + `<main>` 过滤）、`chunks` 表、证据精确字符偏移、位置缺失拒收、定量证据表与抽取；测试 83→101；ADR-014~017 |
| 2026-11-12 | P3 收尾修两个真实缺陷：① `claims` 曾全库列主张（跨 run 污染），改为按 run 作用域（ADR-019）；② 真实 arXiv abs 页 19 条证据中 10 条是站点导航标签，加"完整句子"判据后降为 10 条（ADR-018）。真实复跑 38 块 / 10 证据 / 1 主张 / 偏移逐字成立；测试 101→106 |
| 2026-11-12 | W3/P4 完成：`research/scope.py`（块级继承）、`research/claims.py`（identity 七维 / 合并门槛 / 状态 flag）、claim_builder 改为按身份分组、memo 增 Scope/Conditions/Grounding 与 `# Claims Kept Separate`、定量抽取补 `delta`（无指标词）、ar5iv 公式回声净化；测试 106→147；ADR-020~022 |
| 2026-11-12 | P4 留出集（20 篇未见论文，清单 `docs/evaluation/holdout-ids-2026-11-12.txt`）跑通：20 文档 / 13871 块 / 4814 证据 / 1160 主张（1063 SUPPORTED）；合并门槛 111/1063（10%）；跨文档合并 **0** 组。暴露并修复三处实现缺陷：参考文献进证据（ADR-023）、task 继承率被 `key()` 的 `"None"` 字面量伪装成 100%（ADR-024）、`Motivated/Extensive/Proposed` 被当方法名 + 推断主语不可区分（ADR-025）；测试 147→163 |
| 2026-11-13 | W3/P5 完成：`research/conditions.py`（四类条件）、`research/contradiction.py`（候选配对 + 级联 + 评估器协议）、`scope.py` 条件继承、`claims.py` 四值方向与单位词过滤、`storage` 唯一索引与 run 作用域、memo 矛盾段与 `inspect-claim` 对端、`scripts/evaluate_contradiction.py`；测试 163→239；ADR-026~030；HD-014 |
| 2026-11-13 | P5 前置修正改写了 P4 的部分数字：留出集重测为 1173 主张（1075 支撑）、合并门槛 **73（7%）**、跨文档合并仍 0。合并率下降是四值方向的代价（只报数值的句子不再声明方向），不是回退 |
| 2026-11-13 | P5 实测：候选对 1049 → 判定 30（真矛盾 0 / 实验不可比 2 / 范围不同 18 / 互补 5 / 证据不足 5），跳过 917 缺 dataset + 102 缺 metric，`self@` 预过滤丢弃 6601。30 条判定里 25 条的条件来自 `section-first-mention`，**没有一对是双方句子明写**——这是 HD-014 的直接依据 |
| 2026-11-13 | P5 存储决策落地：`(claim_a_id, claim_b_id)` 唯一索引（不靠 `con_<a[:10]>_<b[:10]>` 主键，截断会撞）、`list_by_run` run 作用域、`replace_for_run` 先删后写使重跑收敛、跨 run 对拒收 |
| 2026-11-13 | P5 独立代码审查（3 个只读子代理 + 实跑验证）：修 HD-014 门控改白名单、`list_by_run`/`replace_for_run` 双侧 run 约束、COMPLEMENTARY 证据位置、旧库去重迁移、夹具引文回归锁、留出集 P5 harness 入库；测试 239→249。剩余方向词表盲区、FAILURE 事件等 5 项列入审查记录 |
| 2026-11-14 | P5 补齐（subagent-driven，10 任务）：失败事件四类（`CROSS_RUN_PAIR` / `CONTRADICTION_UNRESOLVED` ×2 / `CITATION_LOCATION_MISSING`）、三组混淆矩阵并拒绝未知 source、幂等内容断言、主张对主键改摘要、评估路径脱离 CWD、四处空断言改值断言、补三个覆盖缺口；测试 249→319。新增 ADR-031/032 |
| 2026-11-15 | 方法获取能力度量（subagent-driven，6 任务）：新增只读审计脚本、标注夹具（160 格，owner-derived 且先冻结）、回归测试 7 条与评估报告；测试 319→326。标注经三轮独立审验修订（160/0/0 → 146/1/13 → 158/0/2 → 159/0/1）。HD-016。§2.5 未逐项登记 deviation ADR 列为待办 |
| 2026-11-15 | S1 `protocol`→`unit` 语义拆分（5 任务）：`unit` 字段与列、数据守卫式幂等回填、写入/读取/渲染三侧同步翻转、`inspect-claim` 输出键改名、ADR-033；测试 326→333（收集 328→335），`value_bucket` 与 memo 渲染逐字未变。审计脚本只改了一处 docstring（依据换成「`protocol` 处处为空」），四层数字逐格与 2026-11-14 报告一致 |
| 2026-11-15 | S2 方法获取（确定性 L1/L2/L4，10 任务）：`research/patterns.py` + `research/methods.py`（名字/组件/设置 + `missing_layers`）、`MethodProfile`/`MethodSetup`/`MethodPoint` 三模型、`method_profiles`/`method_points` 两表与仓储、竖切第 3 步、行级 `method` 填充、memo `# Methods` 段 + 两个归因计数、审计脚本改读 `MethodProfile`；测试 333→374（收集 335→376）。实测 160 格：L1 0→16/20（两域）、L2 19→20 与 10→20、L4 11→19（19 格）与 14→20，L3 仍 0（S3 未做）；`gaps` 105→48。新增 ADR-034 |
| 2026-11-15 | S3 L3 接线（8 任务）：`MethodDescriber` 同步协议 + `AsyncProviderDescriber`（事件循环探测）、`MethodPointDraft`/`MethodDescriptionResponse`/`DescriptionAttempt`、四道防线 `validate_description`、预算「先查后加」与 4 个 `METHOD_*` 失败类型、录制回放 provider（键 = 去 id 的 prompt 摘要）+ 拒绝伪造的录制脚本、`llm_provider`/`llm_model`/`llm_api_key`/`llm_fixture_dir`、审计 `--describer` 与 L3 原因；测试 374→408（收集 376→410）。**L3 覆盖仍为 0/20 且报「LLM 未启用」**（无 provider，见已知限制 17）。新增 ADR-035 |
| 2026-11-15 | S4 方法获取收官（7 任务）：`conditions` 六类（`scale=`/`protocol=`）、按 kind 的 provenance 与继承、`condition_tier=` 落库、矛盾门按共有 kind 确认、两个离线脚本跟随、三份 before/after 报告；测试 408→418（收集 410→420）。实测：主张 1173→1173、门槛 73→73、`TRUE_CONTRADICTION` 0→0、方法四层与 `gaps` 48 逐格不变；455 条 claim 第 6 段带新 kind 但主张数不变。新增 ADR-036 |
| 2026-11-15 | L3 第一次真实测量：录制 40 篇（`deepseek-flash`，42 次调用，173 KB 夹具入库），收紧 prompt 让 `chunk_id` 必填，L3 从 `0/20`+`0/20` 到 **`19/20`+`20/20`**，`gaps` 48→**9**；新增原因 `LLM 空答复`（D32）与录制侧「无法解析的 chunk_id 记 -1」；测试 428→430（收集 430→432） |
| 2026-11-15 | L3 provider 客户端（4 任务，独立立项）：`llm/openai_compat.py`（OpenAI 兼容、JSON 模式、单次尝试、错误上抛、无内置价格表）、工厂 `openai` 分支与 `llm_base_url`、录制脚本从拒绝桩变成可用命令（键 = 去 id 的 prompt，点带 `prompt_index`；`prompt_ids` 与回放共用同一解析）；测试 418→428（收集 420→430），全部经 `httpx.MockTransport` 离线验证。**未录任何数据**，夹具目录仍不存在，审计照旧报「LLM 未启用」（已知限制 17 已改写）。新增 ADR-037 |

`ADR-031` 只覆盖 §2.5 的 `contradiction judgment` 一项，其余语义判断场景的确定性实现未逐项登记 deviation ADR，单独立项处理。

本批次标注于 2026-11-14 深夜冻结，最终修订与文档同步发生在 2026-11-15 上午；维护记录取提交日，报告/spec 文件名沿用决策日 11-14。
