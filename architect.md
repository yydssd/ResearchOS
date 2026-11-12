# ResearchOS — 架构说明（Architecture Snapshot）

> **用途**：当前架构的一目了然快照，随项目进展时刻维护。
> **权威计划**：`ResearchOS-Implementation-Plan.md`（v1.1，另有 HTML 版）。本文件只沉淀"当前事实 + 决策"，不复制计划全文。
> **维护规则**：架构或进度每次变化，必须同步更新本文，并在文末「维护记录」追加一行；人类方向性决策记入 `human_decision.md`。

---

## 当前状态（2026-10-18 · W1 完成）

- **阶段**：P0 Foundation ✅ · P1 First Vertical Slice ✅（Week 1 完成）
- **已有产物**：`src/research_os/` 完整包 · `tests/`（23 个测试全绿）· CLI · FastAPI · `reports/{run_id}.md` · `research_os.db`
- **环境**：conda `reOS`（Python 3.12，HD-005）
- **验收结果**：`pytest` 23 passed · `uvicorn research_os.main:app` 启动 + `/health` 200 · 垂直切片产出 6 主张（4 SUPPORTED / 2 UNSUPPORTED）且追溯链可查
- **下一步**：W2 —— P2 Source Discovery & Verification（实时搜索抽象、规范化、版本合并）

## 架构定位

> 可度量、可追溯的技术/科研研究系统：结论 → 主张 → 证据 → 权威来源，链断即标 unsupported。
> **reliability · measurability · traceability 优先于 autonomy**；不做聊天机器人，不做多智能体角色扮演。

## 核心不变量（6 条）

1. 证据 ≠ 主张：Source/Evidence/Claim/Hypothesis/Decision 永不合并
2. 主要结论必可追溯：finding→claim→relation→evidence→source version→位置
3. 状态显式持久化（14 类），聊天记录不是主状态
4. 数据库是唯一事实源，LLM 只收受控上下文视图
5. 确定性代码优先于 LLM（9 项确定性 vs 7 项语义判断）
6. 评估从第一天开始：能力上线即带 fixtures + 可测测试

## 技术栈

Python 3.12+（conda `reOS` 环境）· FastAPI · Pydantic v2 · SQLAlchemy · SQLite · pytest · httpx · PyMuPDF
（避免：Neo4j / 向量库 / agent 框架 / 队列 / 复杂前端 —— 直到有可度量需求）

## 领域模型（7 个对象）

`ResearchQuestion` · `ResearchWork`（一作多版本）· `SourceVersion`（verified 标记）· `Evidence`（必带来源位置）· `Claim`（6 状态 + 4 置信标签）· `ClaimEvidenceRelation`（5 类关系）· `ContradictionAssessment`（5 类关系）

## 流水线（v1）

`Question → Planning → Discovery → Verification → Reading → Evidence Extraction → Claim Construction → Relations → Contradiction → Memo`
（不执行实验 / 不跑外部代码 / 无前端）

## 编排

9 种任务类型 · Run 状态机 `CREATED→…→COMPLETED`（含 FAILED/PAUSED）· 动态任务图，允许回退搜索

## 架构决策（ADR）

| ID | 决策 | 状态 |
|----|------|------|
| ADR-001 | 以计划 v1.1 为权威基线 | ACTIVE |
| ADR-002 | 技术栈：Python 3.12+/FastAPI/Pydantic v2/SQLAlchemy/SQLite/pytest/httpx/PyMuPDF；不加重基建 | ACTIVE |
| ADR-003 | 数据库为唯一事实源（轻量 ResearchRun + 受控 ContextView） | ACTIVE |
| ADR-004 | 确定性代码优先；prompt 版本化 | ACTIVE |
| ADR-005 | 按 17 步开发顺序推进，不跳 Step 17 | ACTIVE |
| ADR-006 | 先垂直切片（本地论文），再接实时搜索 | ACTIVE |
| ADR-007 | 评估前置，首要指标 unsupported claim rate | ACTIVE |
| ADR-008 | W1 实现细节：LLMProvider 协议 + 确定性启发式 extractor/claim builder（无 LLM 也可端到端跑通）；SourceVersion/Claim 增加 run_id 归属列（存储层）；句子切分保护小数点 | ACTIVE |

## 阶段状态

| Phase | 周 | 内容 | 验收 | 状态 |
|-------|----|------|------|------|
| P0 Foundation | W1 | 脚手架·模型·SQLite·repository·LLMProvider·事件·health | pytest 23 passed + uvicorn /health 200 | ✅ DONE |
| P1 Vertical Slice | W1 | 本地论文→证据→主张→memo（关键里程碑） | 6 主张（4 SUPPORTED/2 UNSUPPORTED）·链可查 | ✅ DONE |
| P2 Source Discovery | W2 | 搜索抽象·规范化·版本合并·canonical work | ≥10 候选 | TO DO（当前） |
| P3 Evidence Quality | W2 | 多格式加载·溯源分块·定量证据 | 分块带溯源 | TO DO |
| P4 Claim Synthesis | W3 | 归一化·范围区分·unsupported 检测 | 不合并跨数据集主张 | TO DO |
| P5 Contradiction | W3 | 两两矛盾评估 | ≥20 fixtures·≥85% | TO DO |
| P6 Research Memo | W3 | 结构化 Markdown memo | 主要发现带引用 | TO DO |
| P7 Falsification | W4 | 反证搜索·负消融（证伪导向） | 对重要主张执行 | TO DO |
| P8 Evaluation | W4 | Baseline A/B vs ResearchOS 基准 | 5 项指标+成本 | TO DO |

## 接口

HTTP：`POST /research` · `GET /research/{run_id}` · `/report` · `/claims`
CLI（主接口）：`research-os run/status/claims/report/inspect-claim`

## 维护约定（代码注释规则）

1. 每个模块保留模块级 docstring：说明职责 + 关联计划条目（如 `plan §15`）。
2. 每个公共类 / 公共函数保留 docstring：做什么 + 关键约束（为什么这么做）。
3. 非显然的实现细节（如小数点的句子切分保护、SourceVersion/Claim 的 run_id 归属）必须用注释说明原因。
4. 修改代码时必须同步更新受影响的 docstring 与注释；新增文件必须带模块 docstring。
5. 注释与代码一致、不写废话；注释语言与代码一致（英文），文档（README/架构）用中文。

## 维护记录

| 日期 | 变更 |
|------|------|
| 2026-10-18 | 建档：按计划 v1.1 初始化快照与 ADR-001~007；确立时刻维护规则（本次重写为一目了然快照式） |
| 2026-10-18 | W1 完成：P0+P1 DONE（23 tests / uvicorn 200 / 垂直切片 6 主张）；新增 ADR-008；环境改用 conda reOS（HD-005） |
| 2026-10-18 | 补全公共接口 docstring（cli/main/chunks/tasks/loader）；确立代码注释维护规则（HD-006） |
