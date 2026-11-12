# ResearchOS

可度量、可追溯的技术/科研研究系统：每个重要结论都能追溯到
`结论 → 主张 → 证据 → 权威来源位置`。

> **reliability · measurability · traceability 优先于 autonomy**

## 状态

- Week 1 ✅ P0 Foundation + P1 First Vertical Slice
- Week 2 ✅ P2 Source Discovery & Verification（候选 → 规范化 → 版本合并 → canonical work → 核验）
- Week 2 ✅ P3 Evidence Quality（PDF/Markdown/README/HTML → 分块落库 → 精确偏移证据 → 定量证据）
- 测试：`pytest` 106 passed（另有 2 个 opt-in 真实网络测试）
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

### 垂直切片（P1/P3，本地文档）

```powershell
python -m research_os.cli run --question "你的研究问题" --source 本地论文.pdf
python -m research_os.cli status RUN_ID
python -m research_os.cli claims RUN_ID
python -m research_os.cli report RUN_ID
python -m research_os.cli inspect-claim RUN_ID CLAIM_ID
```

`--source` 支持 `.pdf` / `.md` / `.markdown` / `.txt` / `.html` / `.htm` 与 `README*`。
HTML 走结构抽取（跳过 script/style/nav/footer/header/aside/form，优先 `<main>`/`<article>`），
所以抓下来的论文页不会把站内导航文案当成证据。

`inspect-claim` 会打印每条证据的精确位置（`page · section · chars a-b`）与 `content_hash`，
可以拿 `chunk.text[char_start:char_end]` 逐字核对——这是"可追溯"的验收动作。

API：`uvicorn research_os.main:app` → `GET /health` · `POST /research` ·
`GET /research/{run_id}(/report|/claims|/sources)`

## 测试

```powershell
python -m pytest                                            # 全离线（录制报文回放）
$env:RESEARCHOS_NETWORK_TESTS=1; python -m pytest tests/integration/test_live_providers.py
```

离线测试用 `httpx.MockTransport` 回放 `tests/fixtures/sources/` 下录制的 arXiv / Crossref / OpenAlex
真实报文，所以 provider 解析逻辑的回归不依赖网络。

## 目录

```
src/research_os/   domain · storage · sources · llm · documents · research · orchestration · reporting
tests/             unit / integration / fixtures（含录制的 arXiv/Crossref/OpenAlex 报文）
docs/superpowers/  specs（设计规格）· plans（实施计划）
reports/           生成的 Markdown memo
```

几个值得知道位置的模块：

- `documents/html.py` — HTML 结构抽取（标准库 `html.parser`）
- `research/evidence_extractor.py` — 句子切分与字符偏移
- `research/quantitative.py` — 数值 / 单位 / 数据集启发式抽取
- `sources/resolver.py` — 候选 → canonical work 的合并与消歧

## 已知限制（截至 P3）

- 发现层只保证**身份可核验**，不保证**主题相关**：查询由确定性关键词生成，相关性判断留给后续阶段。
- 预印本与正式版按 DOI / arXiv id / 标题+作者合并；作者元数据缺失时不判为冲突（宁可合并）。
- 证据**位置缺失即拒收**（记 `CITATION_LOCATION_MISSING` 事件），不做降级保留。
- 证据必须是**完整句子**（以 `.`/`?`/`!` 结尾）：网页里成串的导航标签因此不会混进证据；
  代价是分页/分块处被截断的半句会丢弃（宁可漏收，不可错收）。
- 仍是完整句子的站点说明文案（如 arXivLabs 段落）会入证据；区分它需要主题相关性，属 P7。
- 定量抽取是启发式：只覆盖 lexicon 内的数据集与指标（PSNR/SSIM/LPIPS/FID/MAE/MSE），
  单位只看数值紧邻 6 字符；跨句、表格、图注中的数值抽不到。
- 句子切分按 `[.!?]` + 空白，缩写（`et al.`）会造成过切，目前不影响偏移正确性（宁可切碎不可错位）。
- 只处理文本层，未做 OCR；扫描版 PDF 无文本则无证据。
