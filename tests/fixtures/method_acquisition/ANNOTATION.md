# Method-acquisition labels：所有权与隔离声明

本夹具中的 160 个判定（40 篇 × 4 层）是 **owner-derived**：由 owner 侧的实施 agent
逐篇阅读 `.holdout_cache/<arxiv_id>.html` 的原文后逐格给出，属于与被测系统同一侧
（owner 侧）产生的判读。它 **不是独立标注，不是盲标**：没有第二位标注者、没有独立
复标、没有与系统产出做任何对照，也没有跨日重标。因此这些标签 **不用于任何正确率、
一致率或质量结论**——既不能据此说系统抽得对，也不能据此说系统抽得好。`present`
计数只作 **可获取率与覆盖率 C 的分母**：它回答「论文原文里能否定位到这一层信息」，
不回答「系统是否抽到、抽得是否正确」。这一区分直接来自
`tests/fixtures/contradiction/ANNOTATION.md` 记下的 self-consistency 教训：那份夹具
用系统侧规则反推 `expected` 键，盲标复标（pass 2）从未进行，于是 26/26 的「一致」
证明的是标签与规则同源，而不是标签正确；本夹具因此把「分母必须在看到任何系统产出
之前冻结」作为硬约束，并拒绝把单侧判读包装成独立标注或一致率。

## 标注时间（UTC+8）

- 起：2026-11-14 23:03（UTC+8），对应 15:03 UTC。
- 止：2026-11-14 23:19（UTC+8），对应 15:19 UTC。
- 两个时刻均由 `date` 实取：本机 `date` 直接输出 `+0800`，并以 `TZ='UTC-8' date`
  （POSIX 东八区）与 `date -u` 交叉核对一致；`TZ='Asia/Shanghai'` 在本机无 tzdata、
  显示 `+0000`，故不采用。未做任何推算或编造。

## 隔离顺序

1. 先只读 HTML 原文（`.holdout_cache/*.html`）、两个 ids 清单、以及 `load_html` /
   `chunk_pages` 这两个文档加载函数，逐篇读文产出 160 格判定，写入 `labels.json`；
2. `labels.json` 与本文 `ANNOTATION.md` 在 **同一提交** 中冻结；
3. 冻结之后才实现 / 运行 `scripts/method_acquisition_audit.py`（本任务期间该文件
   不存在，也未被读取或运行）。

顺序可用 `git log --oneline -- tests/fixtures/method_acquisition/` 复核：该路径的提交
链只有「本次冻结提交」一条；ids 清单的提交 `86fa004` 在本路径之外、时间上在前。
冻结前禁止查看的系统侧产出：禁止读取或 import `src/research_os/research/claims.py`、
`quantitative.py`、`conditions.py`、`claim_builder.py`、`lexicon.py`；禁止运行任何会
产出 claims / quantitative_evidence / identity_key / conditions 的 pipeline；禁止读取
或运行 `scripts/method_acquisition_audit.py`。本夹具全程未触碰上述文件或产出，也
未读取 `docs/evaluation/annotation-sheet-2026-11-14.*` 等任何现成标注表。

执行偏差记录：计划 Step 2 脚本的 `from research_os.documents import chunk_pages` 在
本仓库不成立（`documents/__init__.py` 未 re-export），改用其定义模块
`from research_os.documents.chunks import chunk_pages`；函数与调用
`chunk_pages(load_html(...))` 完全一致，仍只读原文，候选集不变
（`annotation_candidates.txt` = 1600 行 = 40 篇 × 40 chunk）。为逐篇判定 L3 机制句
与 L4 具体值，另在 gitignored 的 `.holdout_cache/` 下导出了 `annotation_full.txt`、
`annotation_tail.txt`、`annotation_exp.txt` 三份只读原文摘录（同样只用 `load_html` +
`chunk_pages`），均不提交。

## 逐层判据（逐字执行）

| 层 | 要抓什么 | `present` 当且仅当 |
|---|---|---|
| L1 方法身份 | 方法名、缩写、别名 | 出现方法名或缩写，且能看出它就是本文提出/评测的方法（不是纯引用前人） |
| L2 方法构成 | 架构、模块、组件、backbone、训练/推理流程 | 出现至少一个具体组件、模块、backbone 或流程步骤的描述 |
| L3 方法描述 | 方法在做什么、为何有效 | 存在至少一句描述方法**机制或设计意图**的句子；只提到方法名不算 |
| L4 可复现设置 | baseline、超参、环境、评测协议、代码/仓库链接 | 出现 baseline、超参、环境、评测协议、代码/仓库链接中的至少一项具体值 |

每格三值：`present` / `absent` / `ambiguous`（只有暗示或泛泛而谈、无法定位到具体句）。
`ambiguous` 不计入 present，单独列数。

`present` 必须附至少一处可定位证据：`section`（可为 null）、`page_label`、
`chunk_index`、`quote`（≤40 Unicode 字符，须为该句内可定位子串）。`section` 为 null
时必须有 `page_label` 或 `chunk_index`（`documents/html.py` 的 `_section` 初值为
None，无标题 HTML 会产出 `section is None` 的 chunk）。

## 统计

160 格 / 160 `present` / 0 `absent` / 0 `ambiguous`。按领域与层：

| 领域 | 层 | present | absent | ambiguous |
|---|---|---|---|---|
| image_restoration | L1 | 20 | 0 | 0 |
| image_restoration | L2 | 20 | 0 | 0 |
| image_restoration | L3 | 20 | 0 | 0 |
| image_restoration | L4 | 20 | 0 | 0 |
| image_restoration | 合计 | 80 | 0 | 0 |
| agent_in_mc | L1 | 20 | 0 | 0 |
| agent_in_mc | L2 | 20 | 0 | 0 |
| agent_in_mc | L3 | 20 | 0 | 0 |
| agent_in_mc | L4 | 20 | 0 | 0 |
| agent_in_mc | 合计 | 80 | 0 | 0 |
| 全部 | 合计 | 160 | 0 | 0 |

## 判读说明与边界样本

- 40 篇均为提出方法 / 系统 / 框架 / benchmark 的论文，四层信息在原文中均可定位到
  具体句，故 160 格全部 `present`。这是逐字执行判据、逐篇读原文的结果，不是关键词
  规则批量推断，也不是为了让分母「好看」；每一格的 section + quote 见下表。
- 每条 `present` 证据都经过机械回查：`quote` 必须是对应 `chunk_index` 归一化文本的
  真实连续子串（≤40 字符），`section` 必须等于该 chunk 的真实标题；回查结果
  `ALL OK`（脚本 `.holdout_cache/gen_labels.py`，gitignored，不提交）。
- `page_label` 恒为 `html`（`load_html` 对 HTML 页固定产出 `page_label="html"`），
  因此定位主要靠 `chunk_index` + `section`；`section` 为 null 的 chunk（如
  `2409.19479` 开头 3 个 LaTeX / glossaries chunk）一律未用作证据。
- 边界样本：`2404.12495` 是量子金刚石显微镜仪器 / 测量论文而非 ML 方法论文（落在
  图像复原 holdout 清单里属清单噪声），按字面判据其方法身份（all-in-one QDM）、构成
  （光路组件）、描述（光路切换的目的）、可复现设置（Table 1 测量模态）均可定位，故
  仍判 present；`2409.19479` 是博士论文，含 CALVIN / SOAP / LangProp / Voggite 多个
  本文方法名；`2406.11247` 是 65-chunk 短文；`2601.05215`、`2504.17950`、
  `2505.12321` 是 benchmark / 平台 / 模拟器论文——其「方法」是评测框架 / 平台本身，
  按判据同样四层可定位。
- `ambiguous` 出口本次触发 0 格：所有层的证据句都能定位到具体句，未出现「只有暗示
  或泛泛而谈、无法定位到具体句」的情形；该出口保留在判据里供后续独立复标使用。
  `absent` 同样 0 格。

## 已知限制

- 标注由 owner 侧同一 agent 产生，非独立、非盲标；无第二位标注者、无独立复标、
  无跨日重标，因此不存在可报告的一致率 / 正确率。
- 判读存在主观性，尤其 L3（「机制或设计意图句」）与 L4（「具体值」是否属于列举的
  5 类）属边界判断；`ambiguous` 是主观边界的出口，本次未触发不代表他人判读会得出
  同样结果。
- 本夹具 **不回答「系统抽得对不对」**：它只固定覆盖率 C 的分母（论文里可获取的
  方法信息）；分子（系统实际抽取）由冻结之后实现的审计脚本给出，两者不得互相参照。
- 160/160 `present` 意味着分母取满；若后续独立复核认为某格应为 `absent` /
  `ambiguous`，须以新提交修订 `labels.json` 并重新计算覆盖率，不得静默改数。
- `labels.json` 顶层只有 `labels` 一个键；本夹具不另设 id 清单，`domain` 仅取
  `image_restoration` / `agent_in_mc`。

## 逐条依据（40 篇 × 4 层）

下列每格给出 label；`present` 附 `section` + `quote`（另附 `chunk_index` 便于定位）。
`absent` / `ambiguous` 本次各 0 格，故无理由行；`ambiguous` 单独列于下节。

### image_restoration（20 篇）

| arxiv_id | 层 | label | section | quote（原文子串，≤40 字符） | chunk_index |
|---|---|---|---|---|---|
| 2310.18293 | L1 | present | 1 Introduction | `UtilityIR is the first type and severity` | 15 |
| 2310.18293 | L2 | present | 1 Introduction | `Degradation Information Encoder (DIE)` | 24 |
| 2310.18293 | L3 | present | Abstract | `to guide weather severity and type` | 2 |
| 2310.18293 | L4 | present | 4.1 Implementation Details | `set the batch size to 2` | 67 |
| 2403.14614 | L1 | present | 1 Introduction | `our AdaIR algorithm` | 24 |
| 2403.14614 | L2 | present | 1 Introduction | `Adaptive Frequency Learning Block (AFLB)` | 22 |
| 2403.14614 | L3 | present | Abstract | `mine low- and high-frequency information` | 2 |
| 2403.14614 | L4 | present | 4 Experiments | `we adopt a batch size of 32` | 63 |
| 2404.12495 | L1 | present | II Instrument Overview | `The all-in-one QDM is configurable` | 6 |
| 2404.12495 | L2 | present | I Introduction | `An LED with linear polarization control` | 5 |
| 2404.12495 | L3 | present | I Introduction | `to create a transmission measurement` | 5 |
| 2404.12495 | L4 | present | II Instrument Overview | `confocal laser excitation` | 10 |
| 2407.11087 | L1 | present | 1 Introduction | `we propose Restore-RWKV` | 10 |
| 2407.11087 | L2 | present | 1 Introduction | `We present a recurrent WKV (Re-WKV)` | 16 |
| 2407.11087 | L3 | present | 1 Introduction | `by shifting tokens from all directions` | 11 |
| 2407.11087 | L4 | present | 4.1 Dataset | `The publicly available AAPM dataset` | 86 |
| 2503.17915 | L1 | present | 1 Introduction | `we present Cat-AIR` | 7 |
| 2503.17915 | L2 | present | 1 Introduction | `alternating spatial-channel attention` | 13 |
| 2503.17915 | L3 | present | 1 Introduction | `that enables our framework to extend` | 15 |
| 2503.17915 | L4 | present | 4.1 Implementation details | `We report PSNR on benchmark datasets` | 473 |
| 2504.09377 | L1 | present | 1. Introduction | `method called HOGformer` | 14 |
| 2504.09377 | L2 | present | 1. Introduction | `Dynamic HOG-aware Self-Attention` | 10 |
| 2504.09377 | L3 | present | 1. Introduction | `that incorporates gradient orientations` | 16 |
| 2504.09377 | L4 | present | 4.2. Implementation Details. | `on NVIDIA Tesla A100 GPUs` | 310 |
| 2504.14249 | L1 | present | 1. Introduction | `We propose AnyIR` | 17 |
| 2504.14249 | L2 | present | Image Restoration (IR) | `a convolutional patch embedding` | 22 |
| 2504.14249 | L3 | present | 1. Introduction | `optimally intertwines global context` | 15 |
| 2504.14249 | L4 | present | 3.2. Gated Degradation Adaption | `state-of-the-art on three degradations` | 46 |
| 2506.22736 | L1 | present | 1 Introduction | `framework, UniFuse` | 9 |
| 2506.22736 | L2 | present | 3.1 Overview | `four core modules: DAPL, OUFR` | 22 |
| 2506.22736 | L3 | present | 1 Introduction | `To simultaneously achieve feature` | 7 |
| 2506.22736 | L4 | present | 4.2 Implementation Details | `a batch size of 3 for 500 epochs` | 84 |
| 2507.22498 | L1 | present | 1 Introduction | `we propose SSGformer` | 10 |
| 2507.22498 | L2 | present | 1 Introduction | `Sobel operator and SVD` | 4 |
| 2507.22498 | L3 | present | 1 Introduction | `not only extracts essential features` | 10 |
| 2507.22498 | L4 | present | Abstract | `The code is available at github.com` | 3 |
| 2511.05873 | L1 | present | Introduction | `we introduce EndoIR` | 8 |
| 2511.05873 | L2 | present | Methodology | `Dual-Domain Prompter(DDP)` | 22 |
| 2511.05873 | L3 | present | Introduction | `for stable diffusion restoration` | 13 |
| 2511.05873 | L4 | present | Abstract | `on SegSTRONG-C and CEC datasets` | 2 |
| 2602.00749 | L1 | present | 1 Introduction | `we first propose HSI-VAR` | 8 |
| 2602.00749 | L2 | present | 2.1 Regression Methods for Restoration | `Structure of the multi-scale VQVAE` | 16 |
| 2602.00749 | L3 | present | 1 Introduction | `which progressively models the spectral` | 8 |
| 2602.00749 | L4 | present | 4.1 Experimental Setup | `We utilize two datasets, ICVL` | 572 |
| 2604.05629 | L1 | present | 1 Introduction | `this paper presents LLaRS` | 7 |
| 2604.05629 | L2 | present | 3.1 Band Semantic Matching | `using optimal transport (OT)` | 17 |
| 2604.05629 | L3 | present | 3.1 Band Semantic Matching | `so multi-sensor inputs are routed` | 17 |
| 2604.05629 | L4 | present | Abstract | `Repo: https://github.com/yc-cui/LLaRS` | 3 |
| 2605.06127 | L1 | present | 1 Introduction | `we propose Continuous Expert Assembly` | 7 |
| 2605.06127 | L2 | present | 1 Introduction | `Cross-Attention Hyper-Adapter` | 8 |
| 2605.06127 | L3 | present | 1 Introduction | `the adapter uses learnable queries` | 8 |
| 2605.06127 | L4 | present | Abstract | `Experiments on AIO-3, AIO-5, and CDD-11` | 2 |
| 2606.19097 | L1 | present | I Introduction | `this paper proposes DVANet` | 16 |
| 2606.19097 | L2 | present | Abstract | `a degradation representation module` | 2 |
| 2606.19097 | L3 | present | I Introduction | `a collaborative unfolding process` | 19 |
| 2606.19097 | L4 | present | IV-A2 Implementation Details | `a frozen DINOv3 ViT-L/16` | 127 |
| 2606.22801 | L1 | present | I Introduction | `We develop MLMIR` | 20 |
| 2606.22801 | L2 | present | I Introduction | `multi-timescale liquid discretization` | 18 |
| 2606.22801 | L3 | present | I Introduction | `the model can automatically adapt its` | 12 |
| 2606.22801 | L4 | present | IV-A1 Datasets | `randomly sample 2,500 image pairs` | 121 |
| 2607.28526 | L1 | present | 1. Introduction | `We propose DAR-Net for AIR` | 16 |
| 2607.28526 | L2 | present | 1. Introduction | `Spatial Ambiguity Rectification (SpAR)` | 13 |
| 2607.28526 | L3 | present | 1. Introduction | `DAR-Net reduces degradation-content` | 12 |
| 2607.28526 | L4 | present | 4.1. Experimental Settings | `we train on BSD400` | 594 |
| 2608.06832 | L1 | present | 1 Introduction | `We propose FIT` | 15 |
| 2608.06832 | L2 | present | 1 Introduction | `a lightweight Degradation Encoder` | 12 |
| 2608.06832 | L3 | present | 1 Introduction | `FIT bends patch grids` | 5 |
| 2608.06832 | L4 | present | Datasets. | `we train on DIV2K` | 69 |
| 2608.06939 | L1 | present | I Introduction | `we propose a Degradation-Aware` | 19 |
| 2608.06939 | L2 | present | I Introduction | `Cross-Modal Prompt Generator` | 25 |
| 2608.06939 | L3 | present | Abstract | `that disentangles degradation artifacts` | 3 |
| 2608.06939 | L4 | present | IV-A Datasets | `Snow100K [56], Outdoor-Rain [57]` | 134 |
| 2609.02839 | L1 | present | 1 Introduction | `we present FReSH-IR` | 8 |
| 2609.02839 | L2 | present | 3.2 Overall Framework | `Spectral Decomposition Block (SDB)` | 22 |
| 2609.02839 | L3 | present | 1 Introduction | `designed to bridge the gap` | 8 |
| 2609.02839 | L4 | present | 4.1 Implementation Details | `three datasets: RainDrop` | 59 |
| 2609.16578 | L1 | present | 1 Introduction | `we propose GraLoD` | 7 |
| 2609.16578 | L2 | present | Abstract | `minimal-sufficient footprint calibration` | 2 |
| 2609.16578 | L3 | present | 1 Introduction | `evaluates the local restoration utility` | 8 |
| 2609.16578 | L4 | present | 4 Experiments | `EfDeRain+ Guo et al. (2025a)` | 74 |

### agent_in_mc（20 篇）

| arxiv_id | 层 | label | section | quote（原文子串，≤40 字符） | chunk_index |
|---|---|---|---|---|---|
| 2605.27762 | L1 | present | Abstract | `We present PEAM` | 1 |
| 2605.27762 | L2 | present | 1 Introduction | `A slow deliberative LLM handles` | 8 |
| 2605.27762 | L3 | present | 1 Introduction | `PEAM consolidates experience into` | 7 |
| 2605.27762 | L4 | present | 4.1 Setup | `We instantiate PEAM in Minecraft 1.19` | 111 |
| 2406.11247 | L1 | present | Abstract | `STEVE Series` | 2 |
| 2406.11247 | L2 | present | 4 Hierarchical Multi-Agent System | `our Hierarchical Multi-Agent System` | 6 |
| 2406.11247 | L3 | present | 5 Distill Embodied Agent into a Single Model | `that refines the alignment of tasks` | 7 |
| 2406.11247 | L4 | present | 2 Data and Environment | `20,000 Question-Answering pairs` | 4 |
| 2504.17950 | L1 | present | 1 Introduction | `we introduce mindcraft` | 6 |
| 2504.17950 | L2 | present | 3.2 Agent Architecture | `a server for launching` | 54 |
| 2504.17950 | L3 | present | 3.3 Multi-agent Collaboration | `is enabled by a conversation manager` | 56 |
| 2504.17950 | L4 | present | 3.4 Additional Features | `github.com/kolbytn/mindcraft` | 57 |
| 2311.15209 | L1 | present | Abstract | `This paper proposes STEVE` | 1 |
| 2311.15209 | L2 | present | 1 Introduction | `Vision Perception, Language Instruction` | 5 |
| 2311.15209 | L3 | present | 3.1 Overview | `integrates Visual Perception` | 24 |
| 2311.15209 | L4 | present | 1 Introduction | `STEVE-21K dataset, including 600+` | 14 |
| 2505.12321 | L1 | present | Abstract | `simulator, BeliefNest` | 1 |
| 2505.12321 | L2 | present | Abstract | `multiple physical simulators` | 2 |
| 2505.12321 | L3 | present | Abstract | `by leveraging Theory of Mind` | 1 |
| 2505.12321 | L4 | present | 1 Introduction | `source code is available at https` | 11 |
| 2508.18722 | L1 | present | 1 Introduction | `we propose VistaWise` | 7 |
| 2508.18722 | L2 | present | 1 Introduction | `a cross-modal knowledge graph` | 7 |
| 2508.18722 | L3 | present | 1 Introduction | `to directly predict actions` | 8 |
| 2508.18722 | L4 | present | 4.1 Dataset and Implementation | `on an L4 GPU with 24G VRAM` | 159 |
| 2505.24157 | L1 | present | 1 Introduction | `we propose Robust and Efficient Planning` | 7 |
| 2505.24157 | L2 | present | 1 Introduction | `Adaptive Dependency Learning (ADL)` | 7 |
| 2505.24157 | L3 | present | Abstract | `to enhance robustness to knowledge` | 2 |
| 2505.24157 | L4 | present | Implementation details | `we use Qwen2.5-VL-7B` | 45 |
| 2606.12852 | L1 | present | 1 Introduction | `we introduce WISE` | 9 |
| 2606.12852 | L2 | present | 1 Introduction | `a Causal Event Graph` | 16 |
| 2606.12852 | L3 | present | 1 Introduction | `the scheduler adapts to newly observed` | 10 |
| 2606.12852 | L4 | present | 4.1 Experiment Setups | `four NVIDIA RTX 4080 GPUs` | 85 |
| 2409.19479 | L1 | present | Abstract | `Thirdly, LangProp` | 7 |
| 2409.19479 | L2 | present | Abstract | `a vision-to-action transformer backend` | 8 |
| 2409.19479 | L3 | present | Abstract | `by treating code as learnable policies` | 7 |
| 2409.19479 | L4 | present | Abstract | `third place in the MineRL BASALT` | 8 |
| 2405.15414 | L1 | present | 4 Method | `we introduce the Luban agent` | 15 |
| 2405.15414 | L2 | present | 4 Method | `3D structural speculation stage` | 16 |
| 2405.15414 | L3 | present | 1 Introduction | `aimed at empowering open-ended agents` | 7 |
| 2405.15414 | L4 | present | 5.1 Exprimental Settings | `with gpt-4-vision-preview` | 28 |
| 2507.03293 | L1 | present | 1.2 Contributions | `We propose LTLCrit` | 12 |
| 2507.03293 | L2 | present | 1.2 Contributions | `a two-timescale architecture` | 15 |
| 2507.03293 | L3 | present | 1.2 Contributions | `by protecting the planners against` | 12 |
| 2507.03293 | L4 | present | 4.1 Experimental Setup | `Temperatures are set to 0.1` | 81 |
| 2601.05215 | L1 | present | Abstract. | `We present MineNPC-Task` | 2 |
| 2601.05215 | L2 | present | 1. Introduction | `Intent routing parses chat` | 15 |
| 2601.05215 | L3 | present | 1. Introduction | `To execute tasks reproducibly` | 6 |
| 2601.05215 | L4 | present | Abstract. | `instantiate the framework with GPT-4o` | 3 |
| 2305.16291 | L1 | present | Abstract | `We introduce Voyager` | 1 |
| 2305.16291 | L2 | present | 1 Introduction | `an automatic curriculum` | 6 |
| 2305.16291 | L3 | present | Abstract | `that continuously explores the world` | 1 |
| 2305.16291 | L4 | present | 3.1 Experimental Setup | `We set all temperatures to 0` | 47 |
| 2403.08282 | L1 | present | 1 Introduction | `We introduce HAS` | 11 |
| 2403.08282 | L2 | present | 3 HAS: A Multi-agent Navigation Framework | `M-MLM and A-MLM` | 21 |
| 2403.08282 | L3 | present | 1 Introduction | `It utilizes centralized planning` | 11 |
| 2403.08282 | L4 | present | 4.1 Experimental Setups | `gpt-4-1106-vision-preview` | 54 |
| 2608.22055 | L1 | present | 1. Introduction | `GenCoord represents sender and peer` | 17 |
| 2608.22055 | L2 | present | 1. Introduction | `parse, schema check, canonical` | 11 |
| 2608.22055 | L3 | present | 1. Introduction | `to compose goals, capabilities, objects` | 8 |
| 2608.22055 | L4 | present | 5.2. Data and Training | `Training uses two epochs` | 83 |
| 2411.12977 | L1 | present | 1 Introduction | `we introduce the MindForge framework` | 8 |
| 2411.12977 | L2 | present | 1 Introduction | `perspective-taking through a causal ToM` | 9 |
| 2411.12977 | L3 | present | 1 Introduction | `using Theory of Mind (ToM)` | 8 |
| 2411.12977 | L4 | present | 5.2 Voyager With Open-Weight LLMs | `Mistral-7B [25], Mixtral-8x7B` | 34 |
| 2410.07484 | L1 | present | 1 Introduction | `World Alignment by ruLe LEarning` | 9 |
| 2410.07484 | L2 | present | 1 Introduction | `the neurosymbolic world model` | 9 |
| 2410.07484 | L3 | present | 1 Introduction | `by learning complementary rules with` | 9 |
| 2410.07484 | L4 | present | 4 Experiments | `134 testing tasks from the ALFWorld` | 64 |
| 2411.06736 | L1 | present | 1 Introduction | `MrSteve (Memory Recall Steve)` | 8 |
| 2411.06736 | L2 | present | 3 Method | `consists of Memory Module and Solver` | 19 |
| 2411.06736 | L3 | present | 1 Introduction | `this framework enables the agent to` | 9 |
| 2411.06736 | L4 | present | Abstract | `project page: https://sites.google.com` | 2 |
| 2501.19318 | L1 | present | 1 Introduction | `we propose MINDSTORES` | 12 |
| 2501.19318 | L2 | present | 1 Introduction | `an experience database storing natural` | 13 |
| 2501.19318 | L3 | present | 1 Introduction | `operates cyclically: observe, retrieve` | 13 |
| 2501.19318 | L4 | present | 4.1 Experimental Setup | `Sentence-BERT embeddings (768-dim)` | 48 |
| 2405.17424 | L1 | present | 1 Introduction | `we first propose Large Auto-Regressive` | 7 |
| 2405.17424 | L2 | present | 4.1 Referee Reinforcement Learning | `we introduce referee RL` | 43 |
| 2405.17424 | L3 | present | 4.1 Referee Reinforcement Learning | `to provide an auxiliary reward feedback` | 43 |
| 2405.17424 | L4 | present | Keywords: | `lizhuoling.github.io/LARM_webpage/` | 3 |

## ambiguous 单独列出

本次 `ambiguous` 共 **0 格**（`absent` 亦 0 格）。原因是 40 篇都是方法 / 系统类论文，
四层信息在原文中均能定位到具体句，没有出现「只有暗示或泛泛而谈、无法定位到具体句」
的格子。该出口保留在判据中，供后续独立复标或扩充语料时使用。
