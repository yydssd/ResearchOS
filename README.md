# ResearchOS

可度量、可追溯的技术/科研研究系统：每个重要结论都能追溯到
`结论 → 主张 → 证据 → 权威来源位置`。

> **reliability · measurability · traceability 优先于 autonomy**

## 状态

- Week 1 ✅ P0 Foundation + P1 First Vertical Slice
- Week 2 ✅ P2 Source Discovery & Verification（候选 → 规范化 → 版本合并 → canonical work → 核验）
- 测试：`pytest` 80 passed（另有 2 个 opt-in 真实网络测试）
- 权威计划：`ResearchOS-Implementation-Plan.md`（v1.1）
- 架构快照：`architect.md` · 人类决策：`human_decision.md` · 设计与计划：`docs/superpowers/`

## 环境

conda 环境 `reOS`（Python 3.12）：

```powershell
conda activate reOS
python -m pip install -e .   # 已安装 research-os 0.1.0
```

## 快速开始

### 源发现（P2，实时数据）

```powershell
python -m research_os.cli discover --question "你的研究问题" --limit 10
python -m research_os.cli sources RUN_ID
```

默认并发使用 arXiv / Crossref / OpenAlex；`RESEARCHOS_SEARCH_PROVIDERS` 可改顺序或只开部分。
`--fixture tests/fixtures/source_candidates` 用录制候选离线复现。

### 垂直切片（P1，本地论文）

```powershell
python -m research_os.cli run --question "你的研究问题" --source 本地论文.pdf
python -m research_os.cli status RUN_ID
python -m research_os.cli claims RUN_ID
python -m research_os.cli report RUN_ID
python -m research_os.cli inspect-claim RUN_ID CLAIM_ID
```

API：`uvicorn research_os.main:app` → `GET /health` · `POST /research` ·
`GET /research/{run_id}(/report|/claims|/sources)`

## 测试

```powershell
python -m pytest                                            # 全离线
$env:RESEARCHOS_NETWORK_TESTS=1; python -m pytest tests/integration/test_live_providers.py
```

## 目录

```
src/research_os/   domain · storage · sources · llm · documents · research · orchestration · reporting
tests/             unit / integration / fixtures（含录制的 arXiv/Crossref/OpenAlex 报文）
docs/superpowers/  specs（设计规格）· plans（实施计划）
reports/           生成的 Markdown memo
```

## 已知限制（P2）

- 发现层只保证**身份可核验**，不保证**主题相关**：查询由确定性关键词生成，相关性判断留给后续阶段。
- 预印本与正式版按 DOI / arXiv id / 标题+作者合并；作者元数据缺失时不判为冲突（宁可合并）。
- 仅支持 PDF / Markdown 本地读取（多格式与定量证据属 P3）。
