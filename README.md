# ResearchOS

可度量、可追溯的技术/科研研究系统：每个重要结论都能追溯到
`结论 → 主张 → 证据 → 权威来源位置`。

> **reliability · measurability · traceability 优先于 autonomy**

## 状态

- Week 1 ✅ P0 Foundation + P1 First Vertical Slice
- Week 2 ✅ P2 Source Discovery & Verification（候选 → 规范化 → 版本合并 → canonical work → 核验）
- Week 2 ✅ P3 Evidence Quality（PDF/Markdown/README/HTML → 分块落库 → 精确偏移证据 → 定量证据）
- Week 3 ✅ P4 Claim Synthesis（块级 scope 继承 → identity 键 → 按身份合并 → 支撑性标记）
- Week 3 ✅ P5 Contradiction（四值方向 → 四类条件与章节继承 → 候选配对 → 级联判定 → run 作用域落库）
- 测试：`pytest` 239 passed（另有 2 个 opt-in 真实网络测试）
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

- `documents/html.py` — HTML 结构抽取（标准库 `html.parser`）+ ar5iv 公式回声净化
- `research/evidence_extractor.py` — 句子切分与字符偏移
- `research/quantitative.py` — 数值 / 单位 / 数据集启发式抽取（含无指标词的 delta）
- `research/scope.py` — 块级 task / dataset / conditions 继承（带 provenance）
- `research/conditions.py` — 四类实验条件抽取（backbone / degradation / baseline / training）
- `research/claims.py` — 主张 identity、四值方向与支撑性判定
- `research/contradiction.py` — 候选配对、级联判定、评估器协议
- `research/claim_builder.py` — 证据 → 主张，并把 provenance 写进质量 flags
- `sources/resolver.py` — 候选 → canonical work 的合并与消歧
- `scripts/holdout_claim_quality.py` — 留出集评估（联网）
- `scripts/evaluate_contradiction.py` — 夹具集分层评估（混淆矩阵、按子集准确率）

## 文档口径

阶段收尾时要同步的文档分成两类，**别把历史快照当状态表改**：

| 类别 | 文件 | 规则 |
| --- | --- | --- |
| **当前状态**（每次收尾必须更新） | `README.md`、`architect.md`、`human_decision.md`、`docs/evaluation/*.md` | 数字用**本阶段重测值**；旧值只作为对比出现，并注明是哪个口径 |
| **历史快照**（不追改正文） | `docs/superpowers/specs/*`、`docs/superpowers/plans/*` | 记录的是**设计当时**的测量与决策。实现有偏差时，在 spec 末尾的「实施偏差」表补一行，不静默改正文 |

其余：

- `ResearchOS-Implementation-Plan.md` 是权威计划 v1.1（17 步规格），**不是进度表**；
  `research-os-implementation-plan.html` 是它的同源渲染，改 md 就要同步 HTML。
- `reports/*.md` 是 run 生成物，不手工维护。
- 阶段状态以 git tag 为准：当前 `w3-p5`，上一阶段 `w3-p4.1`。
- 每次收尾的同步清单：阶段状态与限制 → ADR / 维护记录 → 人类决策 → spec 实施偏差表
  → 评估报告 → 全量测试 → 打 tag。

**当前数字口径**（P5 前置修正后重测，20 篇留出集）：1075 条支持主张、
合并门槛 73（7%）、候选对 1049、判定 30、真矛盾 0。
设计文档里出现的 1063 条 / 111 门槛 / 64.3% 覆盖都是**修正前**的快照。

## 主张层（P4）

```powershell
python -m research_os.cli claims RUN_ID                    # 每条主张带 scope 与置信度
python -m research_os.cli inspect-claim RUN_ID CLAIM_ID    # 含 identity_key / grounding
```

每条主张有一个 `identity_key`：
`subject · task · dataset · metric · direction · conditions · value_bucket`。

合并只在**范围完全确定**时发生——subject、dataset、direction 三者齐全，且各维度逐一相等。
所以 `A improves Rain100H PSNR` 与 `A improves SIDD PSNR` 永远是两条，不会退化成一句
`A improves image restoration`。memo 的 `# Claims Kept Separate` 段把这类"看起来像重复、
但被刻意分开"的主张列出来，供人工核对。

`Scope` 的 task 来自章节标题；标题不写任务名时（`1 Introduction`、`8 Further Ablation Study`）
回退到**文档自身的 task**，优先从摘要读。dataset 支持"段首点名、后句省略"的继承，
但**只在节内**继承——把它扩到全文就是猜。

这不是设计偏好，是实测结果：只看单句时完整 identity 命中率为 0/215。

### 留出集实测（20 篇未见论文，2026-11-12）

`python scripts/holdout_claim_quality.py --papers 20`，论文清单见
`docs/evaluation/holdout-ids-2026-11-12.txt`（缓存页面不入库，可重下）。

| 指标 | 值 |
| --- | --- |
| 文档 / 块 / 证据 | 20 / 13871 / 4814 |
| 定量证据（其中 delta 行） | 170（47） |
| 主张（SUPPORTED / UNSUPPORTED） | 1173（1075 / 98） |
| subject 有值：named / self / 无 | 535 / 476 / 64 |
| 其中 `subject_inferred` | 425 |
| task 有值 | 1056 / 1075（98%） |
| dataset 有值 | 195 / 1075（18%） |
| metric 有值 | 153 / 1075（14%） |
| **满足合并门槛** | **73 / 1075（7%）** |
| grounding：structured / unstructured / 无值 | 137 / 18 / 920 |
| 跨文档合并组数 | **0** |

> **这组数字在 P5 前置修正后重测过。** 合并门槛从 111（10%）降到 73（7%），主张数从
> 1160 升到 1173：`direction` 改成四值后，只报告数值的句子（`achieves 39.18 dB`）不再
> 声明方向，而合并门槛要求 `direction` 有值，于是那些句子不再互相合并。这是刻意的代价——
> 宁可少合并，也不要靠一个被污染的标签合并。

这轮评估推翻了三处实现（都不是调参问题）：

1. **参考文献被当成证据**：1889/6703 条证据（28%）来自 bibliography，28 条还变成主张
   （`[13] Hadsell, R., ...`）。现在 loader 直接丢弃 section 标题为 References/Bibliography 的块，
   附录保留。
2. **task 继承率是假象**：`key()` 曾把 `None` 渲染成字面量 `"None"`，harness 因此报"task 100% 继承"。
   改成空字段后真实值只有 11%——因为任务名写在摘要里、不在标题里。加文档级兜底后到 98%。
3. **subject 精度**：`Motivated` / `Extensive` / `Proposed` 曾因句首大写被当成方法名。

并且暴露一个尚未解决的事实：**瓶颈已经从 task 转移到 dataset**。论文在实验节用
"Table 2"、"this dataset" 指代，不重复点名，所以 82% 的主张拿不到 dataset，合并门槛因此卡在 7%。
这是 P5 的输入条件，不是 P4 的 bug。


## 矛盾与可比性（P5）

```powershell
python -m research_os.cli memo RUN_ID                     # 含 # Contradictions and Open Questions 段
python -m research_os.cli inspect-claim RUN_ID CLAIM_ID   # 含 contradictions（对端主张、关系、理由）
```

P5 只用落库的 `identity_key` 判断，**不再读原文**。五种关系，按顺序首个命中即定论：

| 关系 | 含义 | 置信度 |
| --- | --- | --- |
| `TRUE_CONTRADICTION` | 同 subject、同 dataset、metric 有交集、条件被证实相同、方向对立 | `DISPUTED` |
| `EXPERIMENTAL_INCOMPATIBILITY` | 同向但数值不同，或 metric 无交集 | `MEDIUM` |
| `SCOPE_DIFFERENCE` | dataset 或条件不同，方向也不同 | `MEDIUM` |
| `COMPLEMENTARY` | 范围不同但方向相同（不同基准上各自成立） | `MEDIUM` |
| `INSUFFICIENT_EVIDENCE` | 缺条件、缺方向、或条件只是继承来的 | `LOW` |

三条判定原则值得单独说：

1. **`reports 39.18 dB` 不是方向。** `direction` 四值：`UP`（声称变好）、`DOWN`（声称变差）、
   `LEVEL`（明确说没有改善）、`None`（只报数值）。旧的三值实现把 `achieves/reaches/reports`
   归入 `LEVEL`，于是「提高 PSNR」和「报告 30 dB」被判成相反方向。
2. **`reduces error` 与 `reduces PSNR` 方向相反。** 方向看宾语极性，不看动词。
3. **条件相等分两级。** 句子明写（`sentence`）或节标题点名（`heading`）才算证实；
   从「本节首个提到条件的句子」继承来的（`section-first-mention`）只能用来**否证**相同，
   不能用来**证明**相同。留出集上 25/30 条判定都建立在这种继承条件上。

### 留出集实测（同一批 20 篇）

`docs/evaluation/2026-11-13-p5-contradiction.md` 有完整数字。

| 指标 | 值 |
| --- | --- |
| 进入级联的候选对 | 1049 |
| 产出判定 | 30 |
| 真矛盾 / 实验不可比 / 范围不同 / 互补 / 证据不足 | **0** / 2 / 18 / 5 / 5 |
| 因缺 dataset / 缺 metric 跳过 | 917 / 102 |
| `self@` 预过滤丢弃 | 6601 |

**真矛盾为 0 是预期结果，不是失败。** 留出集 1075 条支撑主张里，只有 16 条 `DOWN`
+ 2 条 `LEVEL`（1.7%）构成负向或持平信号；其余 98.3% 是 `UP`（声称提升）或 `None`
（只报数值、不声称方向），方向对立对结构性不存在。这个类型只在构造夹具上验证
（`tests/fixtures/contradiction/`，26 对，12 对取自真实论文原句）。

## 已知限制（截至 P5）

- **真矛盾在真实语料上不可观测**：它是 P5 唯一不能靠真实论文验收的类型。夹具的标注又是
  照规则推的，所以那个 100% 准确率只能证明"实现和规则一致"，不能证明"规则是对的"。
  独立标注仍未做（`tests/fixtures/contradiction/ANNOTATION.md` 的 pass 2 缺）。
- **条件大多是继承来的**：留出集里没有一对主张在两边都于句子里明写设置，
  所以「设置相同」永远带着 provenance 标签，最多只能是 `heading` 级。
- **18% 的主张有 dataset**，导致可比对的候选对里 87% 在判定前就被跳过。
  补这块是 P4 抽取问题，不是放宽 P5 门槛的理由。
- **P5 的天花板是 P4 的召回**：它只读 `identity_key`，不读原文，`identity_key` 抽错的字段
  它会原样继承。


- 发现层只保证**身份可核验**，不保证**主题相关**：查询由确定性关键词生成，相关性判断留给后续阶段。
- 预印本与正式版按 DOI / arXiv id / 标题+作者合并；作者元数据缺失时不判为冲突（宁可合并）。
- 证据**位置缺失即拒收**（记 `CITATION_LOCATION_MISSING` 事件），不做降级保留。
- 证据必须是**完整句子**（以 `.`/`?`/`!` 结尾）：网页里成串的导航标签因此不会混进证据；
  代价是分页/分块处被截断的半句会丢弃（宁可漏收，不可错收）。
- 仍是完整句子的站点说明文案（如 arXivLabs 段落）会入证据；区分它需要主题相关性，属 P7。
- 参考文献章节已整节剔除（否则占 28% 证据），但**正文里提到的他人工作**仍会入证据
  （这类句子靠 `THIRD_PARTY` 词表排除推断主语，不保证全拦）。
- 定量抽取是启发式：只覆盖 lexicon 内的数据集与指标（PSNR/SSIM/LPIPS/FID/MAE/MSE），
  单位只看数值紧邻 6 字符；表格、图注中的数值抽不到。
- 78% 的数值句不写指标词，只能记成 `delta` + 单位；这类行无法与有指标词的行直接比较。
- **dataset 是当前最大瓶颈**：82% 的主张拿不到 dataset（论文用"this dataset"/"Table 2"指代），
  合并门槛满足率 7%。补这一块需要表格解析或代词消解，不属 P4。
- 44% 的主张主语是 `self`，其中 89% 是推断（`subject_inferred`）；抽样 12 条里只有 2 条
  真的是 `our method`，其余是机理描述和图注。flag 让下游能区分，但没减少误判本身。
- 跨源合并在真实语料上**不触发**：20 篇里 73 个可合并键，跨文档命中 0 组。
  它的验收证据来自构造夹具（`tests/fixtures/claim_merge/`），不是真实论文。
- 句子切分按 `[.!?]` + 空白，缩写（`et al.`）会造成过切，目前不影响偏移正确性（宁可切碎不可错位）。
- 只处理文本层，未做 OCR；扫描版 PDF 无文本则无证据。
