# ResearchOS — 架构说明（Architecture Snapshot）

> **用途**：当前架构的一目了然快照，随项目进展时刻维护。
> **权威计划**：`ResearchOS-Implementation-Plan.md`（v1.1，另有 HTML 版）。本文件只沉淀"当前事实 + 决策"，不复制计划全文。
> **维护规则**：架构或进度每次变化，必须同步更新本文，并在文末「维护记录」追加一行；人类方向性决策记入 `human_decision.md`。

---

## 当前状态（2026-11-12 · W2 / P2 完成）

- **阶段**：P0 ✅ · P1 ✅ · **P2 Source Discovery & Verification ✅**
- **验收结果**：`pytest` 80 passed（+2 opt-in 真实网络）；真实跑一次问题 → **26 候选 / 23 works / 25 verified / 1 unverified**；同一作品的 arXiv 版与会议版合并为一个 work（AutoDIR、HAIR、Degradation-Aware Feature Perturbation）
- **下一步**：P3 Evidence Quality（多格式加载 HTML/README · 溯源分块增强 · 定量证据结构化）

## 架构定位

> 可度量、可追溯的技术/科研研究系统：结论 → 主张 → 证据 → 权威来源，链断即标 unsupported。
> **reliability · measurability · traceability 优先于 autonomy**；不做聊天机器人，不做多智能体角色扮演。

## 核心不变量（6 条）

1. 证据 ≠ 主张：Source/Evidence/Claim/Hypothesis/Decision 永不合并（P2 新增第三种对象 **SourceCandidate**，同样不可冒充证据）
2. 主要结论必可追溯：finding→claim→relation→evidence→source version→位置
3. 状态显式持久化（15 类，含候选），聊天记录不是主状态
4. 数据库是唯一事实源，LLM 只收受控上下文视图
5. 确定性代码优先于 LLM（P2 的规范化/聚类/核验全部零 LLM）
6. 评估从第一天开始：能力上线即带 fixtures + 可测测试

## 技术栈

Python 3.12+（conda `reOS` 环境）· FastAPI · Pydantic v2 · SQLAlchemy · SQLite · pytest · httpx · PyMuPDF
（避免：Neo4j / 向量库 / agent 框架 / 队列 / 复杂前端 —— 直到有可度量需求）

## 领域模型（8 个对象）

`ResearchQuestion` · `ResearchWork`（一作多版本）· `SourceVersion`（verified + `source_tier`）· **`SourceCandidate`（发现候选，独立表）** · `Evidence`（必带来源位置）· `Claim`（6 状态 + 4 置信标签）· `ClaimEvidenceRelation`（5 类关系）· `ContradictionAssessment`（5 类关系）

## 包结构（P2 新增 `sources/`）

| 模块 | 职责 | LLM？ |
|---|---|---|
| `sources/normalize.py` | DOI / arXiv / 标题 / 作者纯函数规范化、相似度 | 否 |
| `sources/query.py` | 确定性关键词查询生成（+1 survey 变体） | 否 |
| `sources/providers.py` | `SearchProvider` 协议 + arXiv/Crossref/OpenAlex/Fixture；解析函数与传输分离 | 否 |
| `sources/resolver.py` | 候选聚类 → canonical work、版本合并、歧义拒绝合并 | 否 |
| `sources/verification.py` | verified 四条件 + `SourceTier` 标注 | 否 |
| `sources/discovery.py` | 纯发现循环：预算钩子、故障容错、候选去重 | 否 |

## 流水线（v2）

```
Question → 查询生成 → Provider[] → SourceCandidate（候选，永不算证据）
        → 规范化 → 去重/版本合并 → canonical Work + SourceVersion[]
        → 核验（verified / 未核验 + 原因）→ 事件 + 预算
        → [P3+] 读取 → 证据抽取 → 主张 → 关系 → 矛盾 → Memo
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

## 阶段状态

| Phase | 周 | 内容 | 验收 | 状态 |
|-------|----|------|------|------|
| P0 Foundation | W1 | 脚手架·模型·SQLite·repository·LLMProvider·事件·health | pytest 全绿 + /health 200 | ✅ DONE |
| P1 Vertical Slice | W1 | 本地论文→证据→主张→memo | 6 主张（4 SUPPORTED/2 UNSUPPORTED）·链可查 | ✅ DONE |
| P2 Source Discovery | W2 | 搜索抽象·规范化·版本合并·canonical work·核验 | 真实跑 26 候选/23 works；arXiv+会议版合并；verified 可分 | ✅ DONE |
| P3 Evidence Quality | W2 | 多格式加载·溯源分块·定量证据 | 分块带溯源 | TO DO（当前） |
| P4 Claim Synthesis | W3 | 归一化·范围区分·unsupported 检测 | 不合并跨数据集主张 | TO DO |
| P5 Contradiction | W3 | 两两矛盾评估 | ≥20 fixtures·≥85% | TO DO |
| P6 Research Memo | W3 | 结构化 Markdown memo | 主要发现带引用 | TO DO |
| P7 Falsification | W4 | 反证搜索·负消融（证伪导向） | 对重要主张执行 | TO DO |
| P8 Evaluation | W4 | Baseline A/B vs ResearchOS 基准 | 5 项指标+成本 | TO DO |

## 接口

HTTP：`POST /research` · `GET /research/{run_id}` · `/report` · `/claims` · **`/sources`**
CLI（主接口）：`research-os run/status/claims/report/inspect-claim` · **`discover/sources`**

## 已知限制（P2）

1. 发现只保证身份可核验，不保证主题相关（查询为确定性关键词；相关性/改写属 P7）。
2. 作者元数据缺失时按标题合并，可能把同名不同作合并（当前 22 个 work 中暂无此例，但机制上可能）。
3. Crossref 会把 SSRN/Research Square 预印本挂到 `WEB` tier（有 DOI 无 venue），排序时低于正式发表。

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
