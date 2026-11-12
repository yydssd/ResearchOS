# ResearchOS — 人类决策记录（Human Decision Log）

> **目的**：记录项目所有者（人类）做出的、影响项目方向 / 范围 / 约束的决策，使人类决策与 Agent 技术决策边界清晰、可审计。
> **分工**：由实现派生的技术决策（ADR）登记在 `architect.md` §7；本文件只记录人类明确做出的决定。
> **权威参考**：`ResearchOS-Implementation-Plan.md`（v1.1，下称"计划"）；`architect.md` 为本项目架构的单一事实来源。

---

## 记录格式

每条决策包含：日期 · 决策内容 · 上下文/理由 · 状态（`ACTIVE` / `SUPERSEDED`）· 影响。被替代的决策标记 `SUPERSEDED` 并保留，不删除。

## 决策日志

### HD-001 项目落地目录与权威计划基线
- **日期**：2026-10-18
- **决策**：ResearchOS 项目落地于 `D:\ResearchOS`；以 `ResearchOS-Implementation-Plan.md`（v1.1，含同版 HTML）为权威计划文件，项目所有工作（阶段、验收、开发顺序）均参照该计划执行。
- **理由**：项目所有者明确指定存放位置并要求参照 plan 文件，避免工作方向漂移。
- **状态**：ACTIVE
- **影响**：所有实现以计划 §1–§37 为验收依据；计划更新须同步（见 architect.md 维护约定）。

### HD-002 维护架构说明与人类决策日志
- **日期**：2026-10-18
- **决策**：维护 `architect.md`（架构单一事实来源）与 `human_decision.md`（人类决策日志）两份活文档，随项目演进持续更新。
- **理由**：项目所有者明确要求，保证架构与人类决策全程可追溯。
- **状态**：ACTIVE
- **影响**：新增方向性决定先登记于此；架构变更登记于 architect.md §7。

### HD-003 当前目标为 MVP-1（Evidence Research System）
- **日期**：2026-10-18
- **决策**：以计划 §4 的 MVP-1（证据研究系统：Question → Search → Verification → Evidence → Claims → Claim–Evidence Graph → Contradictions → Memo）为当前交付目标；遵循计划 §30 的 17 步开发顺序与 §31 的四周路线，不跳跃到 Step 17（Coding Agent 集成）。
- **理由**：计划既定目标与路线；项目所有者选择按计划推进。
- **状态**：ACTIVE
- **影响**：Phase 0–8 按计划逐阶段推进，先完成第一垂直切片（P1）再接实时搜索。

### HD-004 architect.md 必须一目了然并时刻反映进展
- **日期**：2026-10-18
- **决策**：`architect.md` 用于记载项目**当前**的架构：格式必须一目了然（快照式，非计划复述），内容必须与项目实际进展一致，且每次架构/进度变化都必须时刻维护更新（并在文末维护记录追加一行）。
- **理由**：项目所有者明确要求，避免文档与实现脱节、成为不可读的冗余长文。
- **状态**：ACTIVE
- **影响**：architect.md 已重写为精简快照式；后续任何阶段推进、ADR 变更、技术栈调整都必须同步更新该文件。

### HD-005 使用 conda 环境 reOS 运行项目
- **日期**：2026-10-18
- **决策**：项目运行环境改用 conda 新建的 `reOS` 环境（Python 3.12，位于 `D:\Anaconda\envs\reOS`），不使用 venv。
- **理由**：项目所有者明确要求使用 conda 环境。
- **状态**：ACTIVE
- **影响**：所有命令以 `D:\Anaconda\envs\reOS\python.exe` 执行；已弃用的 `.venv` 已删除；包以 editable 模式安装（`research-os` 0.1.0）。

### HD-006 为项目时刻维护好注释
- **日期**：2026-10-18
- **决策**：代码注释必须随项目时刻维护——模块 docstring、公共类/函数 docstring、非显然实现细节的原因注释都要齐全，并在每次代码改动时同步更新。
- **理由**：项目所有者明确要求。
- **状态**：ACTIVE
- **影响**：已补全 cli/main/chunks/tasks/loader 等公共接口注释；规则写入 architect.md「维护约定」，后续新增/修改代码按此执行。

---

_后续人类决策按上述格式追加。_
