# ResearchOS — 架构说明（Architecture Snapshot）

> **用途**：当前架构的一目了然快照，随项目进展时刻维护。
> **权威计划**：`ResearchOS-Implementation-Plan.md`（v1.1，另有 HTML 版）。本文件只沉淀"当前事实 + 决策"，不复制计划全文。
> **维护规则**：架构或进度每次变化，必须同步更新本文，并在文末「维护记录」追加一行；人类方向性决策记入 `human_decision.md`。

---

## 当前状态（2026-11-12 · W3 / P4 完成）

- **阶段**：P0 ✅ · P1 ✅ · P2 ✅ · P3 ✅ · **P4 Claim Synthesis ✅**
- **验收结果**：`pytest` 147 passed（+2 opt-in 真实网络）；主张带 `identity_key`（七维）、按身份合并、memo 显示 Scope/Conditions/Grounding 与 `# Claims Kept Separate`
- **格式覆盖**：PDF · Markdown · README · HTML（含 ar5iv 全文；公式回声已净化）
- **实测口径**：单句 identity 完整率 0/215；引入块级继承后 fixture 6 条主张 = 4 SUPPORTED / 2 UNSUPPORTED
- **下一步**：P5 Contradiction（两两矛盾评估，≥20 fixtures / ≥85%）；前置条件是本层产出的"同 scope 异方向/异值"主张

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

## 阶段状态

| Phase | 周 | 内容 | 验收 | 状态 |
|-------|----|------|------|------|
| P0 Foundation | W1 | 脚手架·模型·SQLite·repository·LLMProvider·事件·health | pytest 全绿 + /health 200 | ✅ DONE |
| P1 Vertical Slice | W1 | 本地论文→证据→主张→memo | 6 主张（4 SUPPORTED/2 UNSUPPORTED）·链可查 | ✅ DONE |
| P2 Source Discovery | W2 | 搜索抽象·规范化·版本合并·canonical work·核验 | 真实跑 26 候选/23 works；arXiv+会议版合并；verified 可分 | ✅ DONE |
| P3 Evidence Quality | W2 | 多格式加载·分块落库·精确偏移·定量证据 | 分块带溯源；证据偏移逐字可验证；定量成表 | ✅ DONE |
| P4 Claim Synthesis | W3 | 块级 scope·identity 键·按身份合并·支撑性标记 | Rain100H/SIDD 不合并；跨源同值合并；4 SUPPORTED/2 UNSUPPORTED | ✅ DONE |
| P5 Contradiction | W3 | 两两矛盾评估 | ≥20 fixtures·≥85% | TO DO（当前） |
| P6 Research Memo | W3 | 结构化 Markdown memo | 主要发现带引用 | TO DO |
| P7 Falsification | W4 | 反证搜索·负消融（证伪导向） | 对重要主张执行 | TO DO |
| P8 Evaluation | W4 | Baseline A/B vs ResearchOS 基准 | 5 项指标+成本 | TO DO |

## 接口

HTTP：`POST /research` · `GET /research/{run_id}` · `/report` · `/claims` · **`/sources`**
CLI（主接口）：`research-os run/status/claims/report/inspect-claim` · **`discover/sources`**

## 已知限制（P2/P3）

1. 发现只保证身份可核验，不保证主题相关（查询为确定性关键词；相关性/改写属 P7）。
2. 作者元数据缺失时按标题合并，可能把同名不同作合并（当前 22 个 work 中暂无此例，但机制上可能）。
3. Crossref 会把 SSRN/Research Square 预印本挂到 `WEB` tier（有 DOI 无 venue），排序时低于正式发表。
4. PDF 章节标题未识别（section 为空），仅页级溯源；需字体启发式，误判风险高，留待后续。
5. 句子切分对 `et al. 2023` 这类缩写会误判句界；分块/分页处被截断的半句因无句界会被丢弃（宁可漏收，不可错收）。
6. 通用网页的**散文档**站点文案（如 arXivLabs 说明段，本身是完整句子）仍会入证据；标签碎片已由句界判据挡掉，剩下的是主题相关性问题，属 P7。
7. 定量抽取只认 ASCII 指标词与数字，表格结构不还原；无指标词的增益已由 `delta` 通道覆盖（P4），但表格与图注中的数值仍抽不到。
8. 跨源合并在真实语料上几乎不触发：需要同一方法在同一数据集上被他人复现。验收证据来自 `tests/fixtures/claim_merge/`，不来自真实论文。
9. `SELF` 默认依赖第三方标识黑名单（previous/baseline/SOTA…），漏判会把前人方法的结果算到本文方法头上；相关通道只会降置信，不会纠正归属。
10. 段落级回指只覆盖"段首点名"一种；代词与别名指代抽不到。

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
