# ResearchOS

可度量、可追溯的技术/科研研究系统：每个重要结论都能追溯到
`结论 → 主张 → 证据 → 权威来源位置`。

> **reliability · measurability · traceability 优先于 autonomy**

## 状态

- Week 1 完成：P0 Foundation + P1 First Vertical Slice（`pytest` 23 passed，`/health` 200，垂直切片端到端跑通）
- 权威计划：`ResearchOS-Implementation-Plan.md`（v1.1）
- 架构快照：`architect.md` · 人类决策：`human_decision.md`

## 环境

conda 环境 `reOS`（Python 3.12）：

```powershell
conda activate reOS
python -m pip install -e .   # 已安装 research-os 0.1.0
```

## 快速开始（垂直切片）

```powershell
python -m research_os.cli run --question "你的研究问题" --source 本地论文.pdf
python -m research_os.cli status RUN_ID
python -m research_os.cli claims RUN_ID
python -m research_os.cli report RUN_ID
python -m research_os.cli inspect-claim RUN_ID CLAIM_ID
```

API：`uvicorn research_os.main:app` → `GET /health` · `POST /research` · `GET /research/{run_id}(/report|/claims)`

## 测试

```powershell
python -m pytest
```

## 目录

```
src/research_os/   domain · storage · llm · documents · research · orchestration · reporting
tests/             unit / integration / fixtures
reports/           生成的 Markdown memo
```
