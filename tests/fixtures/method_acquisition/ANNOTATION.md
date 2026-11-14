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

- 首次标注读文起：2026-11-14 23:03（UTC+8），对应 15:03 UTC。
- 首次标注读文止：2026-11-14 23:19（UTC+8），对应 15:19 UTC。
- 两个时刻均由 `date` 实取：本机 `date` 直接输出 `+0800`，并以 `TZ='UTC-8' date`
  （POSIX 东八区）与 `date -u` 交叉核对一致；`TZ='Asia/Shanghai'` 在本机无 tzdata、
  显示 `+0000`，故不采用。未做任何推算或编造。
- 本次是 **按 §4 判据对已冻结标签的重新判定**，不是新一轮独立标注，因此没有新的
  独立标注起止时间；重判沿用同一批 HTML 原文与同一批 owner 侧判读。

## 隔离顺序

1. 首次冻结（提交 `424c976`）：先只读 HTML 原文（`.holdout_cache/*.html`）、两个 ids
   清单、以及 `load_html` / `chunk_pages` 这两个文档加载函数，逐篇读文产出 160 格判定，
   与本文同一提交写入 `labels.json` / `ANNOTATION.md`。
2. **坦白**：首次冻结并未逐字执行 §4——它把数据集名、表格标题、表注泛泛句、图注、
   竞赛名次、`Keywords:` 区 URL 当成 L4 的「具体值」，从而把 160 格全部判成
   `present`。这是审验判为 NEEDS WORK（Critical I1）的根因，本夹具不为其辩护。
3. 本次修订：按 §4 从严重判 160 格（见「判据符合性自查」），以 **新提交** 修订夹具，
   保留 `424c976` 历史；冻结之后才实现 / 运行 `scripts/method_acquisition_audit.py`
   （本次修订期间该文件仍不存在，也未被读取或运行）。
4. 顺序可用 `git log --oneline -- tests/fixtures/method_acquisition/` 复核：该路径
   按时间先后应列出「首次冻结 `424c976`」与「本次修订的最新一条提交」；具体 SHA 以
   该命令的实际输出为准，本文不写自引用的当前提交号。

冻结前禁止查看的系统侧产出：禁止读取或 import `src/research_os/research/claims.py`、
`quantitative.py`、`conditions.py`、`claim_builder.py`、`lexicon.py`；禁止运行任何会
产出 claims / quantitative_evidence / identity_key / conditions 的 pipeline；禁止读取
或运行 `scripts/method_acquisition_audit.py`。首次冻结与本次修订全程未触碰上述文件或
产出，也未读取 `docs/evaluation/annotation-sheet-2026-11-14.*` 等任何现成标注表。

执行偏差记录：计划 Step 2 脚本的 `from research_os.documents import chunk_pages` 在
本仓库不成立（`documents/__init__.py` 未 re-export），改用其定义模块
`from research_os.documents.chunks import chunk_pages`；函数与调用
`chunk_pages(load_html(...))` 完全一致，仍只读原文，候选集不变
（`annotation_candidates.txt` = 1600 行 = 40 篇 × 40 chunk）。为逐篇判定，另在
gitignored 的 `.holdout_cache/` 下导出了 `annotation_full.txt`、`annotation_tail.txt`、
`annotation_exp.txt` 三份只读原文摘录（同样只用 `load_html` + `chunk_pages`），均不提交。

## 逐层判据（§4，逐字）

下表是审验要求逐字执行的判据。**首次冻结并未真正逐字执行**：它系统性放宽了 L4
对「具体值」的门槛（见上文第 2 点），本次修订才按此表从严重判；并且**不得**把
「证据可定位性回查 ALL OK」当作判据已满足的佐证——那只是定位性，不是符合性。

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

关键纪律（本次修订逐字执行）：找不到满足判据的句子就判 `absent` 或 `ambiguous` 并写
理由，**不许为了保住 present 而勉强找一条沾边的证据**。数据集名、表格标题、表注泛泛
句、图注、竞赛名次、性能宣称、`Keywords:` 区 URL 都**不等于** L4 的「具体值」。

## 判据符合性自查（本次新增）

审验的核心发现：`424c976` 的生成器把 160 格硬编码为全 `present`，其回查只验证
「quote 可定位 / ≤40 字符 / 有 section」，**完全不检查 evidence 是否满足 §4 该层判据**。
审验点名的缓存生成器 `.holdout_cache/gen_labels.py`（gitignored）保留原样不修改，作为
首次冻结的历史痕迹；本次修订改用内联执行重新生成 `labels.json` 与本文，不再依赖该
脚本的 ROWS，也不新增任何脚本文件。
因此必须明确区分两件事：

- **证据可定位性回查**（首次冻结已有，本次重跑仍 `ALL OK`）：只证明 `quote` 是对应
  `chunk_index` 归一化文本的真实连续子串、≤40 字符、`section` 与该 chunk 真实标题一致。
  它**不证明**判据符合性；首次冻结把 `ALL OK` 当作「判据已满足」是错误的。
- **判据符合性**（本次新增）：逐格人工重读证据句，判断其是否真的给出该层要求的信息。
  这是修订的依据，结果是 14 格改判（`absent`/`ambiguous`）、4 格换证据、1 格补依据。

审验独立回查给出的分布（按首次冻结证据判定）：

| 层 | S（满足） | B（边界） | N（不满足） | 从严不成立 |
|---|---|---|---|---|
| L4 | 27 | 9 | 4 | 13（32.5%），其中 12 格在 `image_restoration`（该域按首次证据仅 8/20 合格） |
| L1（抽查 5 格） | 1 | 3 | 1 | 1 |
| L2 / L3 | 大体站得住 | — | — | — |

逐层重判结果：

- **L1**：抽查 1 不满足格（`2409.19479`）改判 `ambiguous`；3 个边界格换证据后保留
  `present`（`2310.18293` 换含 `method` 的连续子串、`2406.11247` 换 Abstract 归属
  命名句替代图注、`2608.22055` 换 `We introduce GenCoord` 替代功能描述句）；其余 36
  格复核后证据均为「方法名 + 本文提出」的命名句，保留 `present`。另补
  `2410.07484`/L1 第 2 条 evidence 的依据。最终 **present 39 / ambiguous 1**。
- **L2**：全量复核 40 格，证据均为具体组件、模块、backbone 或流程步骤的描述，
  40/40 `present`，本次未触发 `ambiguous`；这不等于 L2 无主观性。
- **L3**：全量复核 40 格，证据均为机制或设计意图句（`to / by / which / so that /
  designed to / enables`），40/40 `present`，本次未触发 `ambiguous`。首次
  `ANNOTATION.md` 曾自认「L3/L4 是主观边界判断、`ambiguous` 是出口」却让两层 80 格
  0 次触发，属自相矛盾：本次 L4 触发 12 次 `ambiguous` + 1 次 `absent`，该矛盾已消除；
  L3 复核后确实未触发，若后续独立复标改判须以新提交修订。
- **L4**：4 个 N 格与 9 个 B 格**全部改判**（不事后另挑沾边证据保住 `present`），
  其中 `2609.16578` 因实验设置明写在附录、可见全文无具体值而判 `absent`，其余判
  `ambiguous`；另按关键纪律把 `2405.17424` 的 `Keywords:` 区 URL 换成 §4 合格的
  baseline 具体名句（label 不变）。最终 **present 27（IR 8 / MC 19）/ absent 1 /
  ambiguous 12**，与审验独立回查的 S=27、13 格不成立、IR 8/20、MC 19/20 一致。

## 统计

修订后不再是 160/160。总计 **146 `present` / 1 `absent` / 13 `ambiguous`**（160 格）。

| 领域 | 层 | present | absent | ambiguous |
|---|---|---|---|---|
| image_restoration | L1 | 20 | 0 | 0 |
| image_restoration | L2 | 20 | 0 | 0 |
| image_restoration | L3 | 20 | 0 | 0 |
| image_restoration | L4 | 8 | 1 | 11 |
| image_restoration | 合计 | 68 | 1 | 11 |
| agent_in_mc | L1 | 19 | 0 | 1 |
| agent_in_mc | L2 | 20 | 0 | 0 |
| agent_in_mc | L3 | 20 | 0 | 0 |
| agent_in_mc | L4 | 19 | 0 | 1 |
| agent_in_mc | 合计 | 78 | 0 | 2 |
| 全部 | 合计 | 146 | 1 | 13 |

## 判读说明与边界样本

- 首次冻结把 40 篇一律判成四层 `present`，不是真实语料分布：它把数据集名、表格
  标题、表注泛泛句、图注、竞赛名次、`Keywords:` 区 URL 当作 L4 的「具体值」，并为
  已定的 `present` 结论事后挑证据。本次按 §4 从严重判后，L4 只有 27/40 格合格，
  `image_restoration` 仅 8/20 合格；14 格改判为 `absent`/`ambiguous`。
- 每条 `present` 证据的可定位性仍经机械回查（`ALL OK`），但如「判据符合性自查」节
  所述，该回查只证明定位性；符合性由逐格人工重读给出，见下表逐条依据。
- `page_label` 恒为 `html`（`load_html` 对 HTML 页固定产出 `page_label="html"`），
  定位主要靠 `chunk_index` + `section`；`section` 为 null 的 chunk（如 `2409.19479`
  开头 3 个 LaTeX / glossaries chunk）一律未用作证据。
- 边界样本：`2404.12495` 是量子金刚石显微镜仪器 / 测量论文而非 ML 方法论文（落在
  图像复原 holdout 清单里属清单噪声），L1/L2/L3 按字面判据可定位，但 L4 无 §4 具体
  值，本次改判 `ambiguous`；`2409.19479` 是博士论文，含 CALVIN / SOAP / LangProp /
  Voggite 多个本文方法名，L1 的 `Thirdly, LangProp` 孤立看无法定位到「本文提出」，
  L4 的竞赛名次不构成具体值，两格均改判；`2406.11247` 是 65-chunk 短文，L1 原证据
  为图注、已换为 `Our STEVE Series agents`；`2601.05215`、`2504.17950`、
  `2505.12321` 是 benchmark / 平台 / 模拟器论文——其「方法」是评测框架 / 平台本身。
- `2405.17424`/L4 原证据是 `Keywords:` 区 URL，按关键纪律不算具体值，已换成
  `5.2 Main Results` 里 `The methods compared on MineDojo include MineAgent ...
  Plan4MC` 的 baseline 具体名句子（label 仍 `present`）。
- `2410.07484`/L1 保留两条 evidence：`1 Introduction` 的
  `World Alignment by ruLe LEarning`（命名句）与 `Abstract` 的
  `WALL-E achieves higher success rates`（表明它是本文评测的方法）；首次
  `ANNOTATION.md` 的逐条依据表只列了第一条，本次两条都列出。

## 已知限制

- 标注由 owner 侧同一 agent 产生，非独立、非盲标；无第二位标注者、无独立复标、
  无跨日重标，因此不存在可报告的一致率 / 正确率。
- 判读存在主观性，尤其 L3（「机制或设计意图句」）与 L4（「具体值」是否属于列举的
  5 类）；`ambiguous` 是主观边界的出口，本次在 L1（1 格）与 L4（12 格）触发，
  L2/L3 复核后未触发。这不代表他人判读会得出同样结果。
- 本夹具 **不回答「系统抽得对不对」**：它只固定覆盖率 C 的分母（论文里可获取的
  方法信息）；分子（系统实际抽取）由冻结之后实现的审计脚本给出，两者不得互相参照。
- **`A` 不再恒 100%**：`image_restoration`/L4 仅 8 格 `present`，`agent_in_mc`/L1 与
  `/L4` 各 19 格 `present`，因此 `C` 的分母不再恒为 20，任何按「每层 20 篇全 present」
  写的公式或断言都必须按本表重算。
- **本次没有任何（领域, 层）组合 `present=0`**（最低为 `image_restoration`/L4 的 8）。
  因此 `present=0 → N/A` 分支在真实夹具上不触发，只由合成夹具验证；不能据此声称该
  分支已被真实语料覆盖。
- **不得静默改数**：本次修订是 **新提交**，完整保留首次冻结 `424c976` 的历史；不
  amend、不 force push、不删旧提交。`160/160` 与 `146/1/13` 两个版本都在
  `git log --oneline -- tests/fixtures/method_acquisition/` 中可见，纠正以可见的方式
  完成。若后续独立复核再改判某格，须同样以新提交修订 `labels.json` 并重算覆盖率。
- `labels.json` 顶层只有 `labels` 一个键；本夹具不另设 id 清单，`domain` 仅取
  `image_restoration` / `agent_in_mc`。

## 逐条依据（40 篇 × 4 层）

下列每格给出 label；`present` 附全部 evidence 的 `section` + `quote`（另附
`chunk_index` 便于定位），多条 evidence 以 `；` 分隔；`absent` / `ambiguous` 各给一句
理由。`ambiguous` 单独列于下节。

### image_restoration（20 篇）

| arxiv_id | 层 | label | section | quote（原文子串，≤40 字符） | chunk_index | 依据 / 理由 |
|---|---|---|---|---|---|---|
| 2310.18293 | L1 | present | 1 Introduction | `all-in-one image restoration method` | 15 | 换证据：原 quote 截断为「...first type and severity」产生歧义，改取含 method 的连续子串。 |
| 2310.18293 | L2 | present | 1 Introduction | `Degradation Information Encoder (DIE)` | 24 | — |
| 2310.18293 | L3 | present | Abstract | `to guide weather severity and type` | 2 | — |
| 2310.18293 | L4 | present | 4.1 Implementation Details | `set the batch size to 2` | 67 | — |
| 2403.14614 | L1 | present | 1 Introduction | `our AdaIR algorithm` | 24 | — |
| 2403.14614 | L2 | present | 1 Introduction | `Adaptive Frequency Learning Block (AFLB)` | 22 | — |
| 2403.14614 | L3 | present | Abstract | `mine low- and high-frequency information` | 2 | — |
| 2403.14614 | L4 | present | 4 Experiments | `we adopt a batch size of 32` | 63 | — |
| 2404.12495 | L1 | present | II Instrument Overview | `The all-in-one QDM is configurable` | 6 | — |
| 2404.12495 | L2 | present | I Introduction | `An LED with linear polarization control` | 5 | — |
| 2404.12495 | L3 | present | I Introduction | `to create a transmission measurement` | 5 | — |
| 2404.12495 | L4 | ambiguous | — | — | — | 首次证据 confocal laser excitation 是 Table 1 测量模态缩写；全文可定位的 >1 MHz、≈5 mm 属仪器能力描述，不构成 baseline/超参/环境/评测协议/代码链接的具体值。 |
| 2407.11087 | L1 | present | 1 Introduction | `we propose Restore-RWKV` | 10 | — |
| 2407.11087 | L2 | present | 1 Introduction | `We present a recurrent WKV (Re-WKV)` | 16 | — |
| 2407.11087 | L3 | present | 1 Introduction | `by shifting tokens from all directions` | 11 | — |
| 2407.11087 | L4 | ambiguous | — | — | — | 首次证据 The publicly available AAPM dataset 仅为数据集名；实验段可定位的 DRF=4、674/5000 pairs 属数据规模，非 §4 五类的具体值。 |
| 2503.17915 | L1 | present | 1 Introduction | `we present Cat-AIR` | 7 | — |
| 2503.17915 | L2 | present | 1 Introduction | `alternating spatial-channel attention` | 13 | — |
| 2503.17915 | L3 | present | 1 Introduction | `that enables our framework to extend` | 15 | — |
| 2503.17915 | L4 | ambiguous | — | — | — | 首次证据 We report PSNR on benchmark datasets 是表注泛泛句；按关键纪律表注不算具体值，本次不另挑沾边证据。 |
| 2504.09377 | L1 | present | 1. Introduction | `method called HOGformer` | 14 | — |
| 2504.09377 | L2 | present | 1. Introduction | `Dynamic HOG-aware Self-Attention` | 10 | — |
| 2504.09377 | L3 | present | 1. Introduction | `that incorporates gradient orientations` | 16 | — |
| 2504.09377 | L4 | present | 4.2. Implementation Details. | `on NVIDIA Tesla A100 GPUs` | 310 | — |
| 2504.14249 | L1 | present | 1. Introduction | `We propose AnyIR` | 17 | — |
| 2504.14249 | L2 | present | Image Restoration (IR) | `a convolutional patch embedding` | 22 | — |
| 2504.14249 | L3 | present | 1. Introduction | `optimally intertwines global context` | 15 | — |
| 2504.14249 | L4 | ambiguous | — | — | — | 首次证据 state-of-the-art on three degradations 是表格标题；按关键纪律表格标题不算具体值。 |
| 2506.22736 | L1 | present | 1 Introduction | `framework, UniFuse` | 9 | — |
| 2506.22736 | L2 | present | 3.1 Overview | `four core modules: DAPL, OUFR` | 22 | — |
| 2506.22736 | L3 | present | 1 Introduction | `To simultaneously achieve feature` | 7 | — |
| 2506.22736 | L4 | present | 4.2 Implementation Details | `a batch size of 3 for 500 epochs` | 84 | — |
| 2507.22498 | L1 | present | 1 Introduction | `we propose SSGformer` | 10 | — |
| 2507.22498 | L2 | present | 1 Introduction | `Sobel operator and SVD` | 4 | — |
| 2507.22498 | L3 | present | 1 Introduction | `not only extracts essential features` | 10 | — |
| 2507.22498 | L4 | present | Abstract | `The code is available at github.com` | 3 | — |
| 2511.05873 | L1 | present | Introduction | `we introduce EndoIR` | 8 | — |
| 2511.05873 | L2 | present | Methodology | `Dual-Domain Prompter(DDP)` | 22 | — |
| 2511.05873 | L3 | present | Introduction | `for stable diffusion restoration` | 13 | — |
| 2511.05873 | L4 | ambiguous | — | — | — | 首次证据 on SegSTRONG-C and CEC datasets 仅为数据集名；γ=0.5/1 只出现在图注，按纪律图注不算。 |
| 2602.00749 | L1 | present | 1 Introduction | `we first propose HSI-VAR` | 8 | — |
| 2602.00749 | L2 | present | 2.1 Regression Methods for Restoration | `Structure of the multi-scale VQVAE` | 16 | — |
| 2602.00749 | L3 | present | 1 Introduction | `which progressively models the spectral` | 8 | — |
| 2602.00749 | L4 | ambiguous | — | — | — | 首次证据 We utilize two datasets, ICVL 仅为数据集名；AIO-3/AIO-5 基准名与 ICVL 规模数值不构成 §4 具体值。 |
| 2604.05629 | L1 | present | 1 Introduction | `this paper presents LLaRS` | 7 | — |
| 2604.05629 | L2 | present | 3.1 Band Semantic Matching | `using optimal transport (OT)` | 17 | — |
| 2604.05629 | L3 | present | 3.1 Band Semantic Matching | `so multi-sensor inputs are routed` | 17 | — |
| 2604.05629 | L4 | present | Abstract | `Repo: https://github.com/yc-cui/LLaRS` | 3 | — |
| 2605.06127 | L1 | present | 1 Introduction | `we propose Continuous Expert Assembly` | 7 | — |
| 2605.06127 | L2 | present | 1 Introduction | `Cross-Attention Hyper-Adapter` | 8 | — |
| 2605.06127 | L3 | present | 1 Introduction | `the adapter uses learnable queries` | 8 | — |
| 2605.06127 | L4 | ambiguous | — | — | — | 首次证据 Experiments on AIO-3, AIO-5, and CDD-11 仅为基准名；按关键纪律数据集/基准名不算。 |
| 2606.19097 | L1 | present | I Introduction | `this paper proposes DVANet` | 16 | — |
| 2606.19097 | L2 | present | Abstract | `a degradation representation module` | 2 | — |
| 2606.19097 | L3 | present | I Introduction | `a collaborative unfolding process` | 19 | — |
| 2606.19097 | L4 | present | IV-A2 Implementation Details | `a frozen DINOv3 ViT-L/16` | 127 | — |
| 2606.22801 | L1 | present | I Introduction | `We develop MLMIR` | 20 | — |
| 2606.22801 | L2 | present | I Introduction | `multi-timescale liquid discretization` | 18 | — |
| 2606.22801 | L3 | present | I Introduction | `the model can automatically adapt its` | 12 | — |
| 2606.22801 | L4 | present | IV-A1 Datasets | `randomly sample 2,500 image pairs` | 121 | — |
| 2607.28526 | L1 | present | 1. Introduction | `We propose DAR-Net for AIR` | 16 | — |
| 2607.28526 | L2 | present | 1. Introduction | `Spatial Ambiguity Rectification (SpAR)` | 13 | — |
| 2607.28526 | L3 | present | 1. Introduction | `DAR-Net reduces degradation-content` | 12 | — |
| 2607.28526 | L4 | ambiguous | — | — | — | 首次证据 we train on BSD400 仅为数据集名；3D/5D 设置名不是具体值。 |
| 2608.06832 | L1 | present | 1 Introduction | `We propose FIT` | 15 | — |
| 2608.06832 | L2 | present | 1 Introduction | `a lightweight Degradation Encoder` | 12 | — |
| 2608.06832 | L3 | present | 1 Introduction | `FIT bends patch grids` | 5 | — |
| 2608.06832 | L4 | ambiguous | — | — | — | 首次证据 we train on DIV2K 仅为数据集名；30.72 dB 等属性能宣称，按纪律不算。 |
| 2608.06939 | L1 | present | I Introduction | `we propose a Degradation-Aware` | 19 | — |
| 2608.06939 | L2 | present | I Introduction | `Cross-Modal Prompt Generator` | 25 | — |
| 2608.06939 | L3 | present | Abstract | `that disentangles degradation artifacts` | 3 | — |
| 2608.06939 | L4 | ambiguous | — | — | — | 首次证据 Snow100K [56], Outdoor-Rain [57] 仅为数据集名；表格 PSNR/SSIM 数值属结果值，非可复现设置。 |
| 2609.02839 | L1 | present | 1 Introduction | `we present FReSH-IR` | 8 | — |
| 2609.02839 | L2 | present | 3.2 Overall Framework | `Spectral Decomposition Block (SDB)` | 22 | — |
| 2609.02839 | L3 | present | 1 Introduction | `designed to bridge the gap` | 8 | — |
| 2609.02839 | L4 | ambiguous | — | — | — | 首次证据 three datasets: RainDrop 仅为数据集名；80% fewer parameters 属性能宣称，不算。 |
| 2609.16578 | L1 | present | 1 Introduction | `we propose GraLoD` | 7 | — |
| 2609.16578 | L2 | present | Abstract | `minimal-sufficient footprint calibration` | 2 | — |
| 2609.16578 | L3 | present | 1 Introduction | `evaluates the local restoration utility` | 8 | — |
| 2609.16578 | L4 | absent | — | — | — | 实验章节明写 experimental setup ... provided in Appendix A.2 and A.3；缓存 HTML 可见全文未给出 §4 五类的具体值，故判 absent。 |

### agent_in_mc（20 篇）

| arxiv_id | 层 | label | section | quote（原文子串，≤40 字符） | chunk_index | 依据 / 理由 |
|---|---|---|---|---|---|---|
| 2605.27762 | L1 | present | Abstract | `We present PEAM` | 1 | — |
| 2605.27762 | L2 | present | 1 Introduction | `A slow deliberative LLM handles` | 8 | — |
| 2605.27762 | L3 | present | 1 Introduction | `PEAM consolidates experience into` | 7 | — |
| 2605.27762 | L4 | present | 4.1 Setup | `We instantiate PEAM in Minecraft 1.19` | 111 | — |
| 2406.11247 | L1 | present | Abstract | `Our STEVE Series agents` | 1 | 换证据：原证据为图注「Figure 1: STEVE Series overview.」（非命名句），改取 Abstract 的归属命名句。 |
| 2406.11247 | L2 | present | 4 Hierarchical Multi-Agent System | `our Hierarchical Multi-Agent System` | 6 | — |
| 2406.11247 | L3 | present | 5 Distill Embodied Agent into a Single Model | `that refines the alignment of tasks` | 7 | — |
| 2406.11247 | L4 | present | 2 Data and Environment | `20,000 Question-Answering pairs` | 4 | — |
| 2504.17950 | L1 | present | 1 Introduction | `we introduce mindcraft` | 6 | — |
| 2504.17950 | L2 | present | 3.2 Agent Architecture | `a server for launching` | 54 | — |
| 2504.17950 | L3 | present | 3.3 Multi-agent Collaboration | `is enabled by a conversation manager` | 56 | — |
| 2504.17950 | L4 | present | 3.4 Additional Features | `github.com/kolbytn/mindcraft` | 57 | — |
| 2311.15209 | L1 | present | Abstract | `This paper proposes STEVE` | 1 | — |
| 2311.15209 | L2 | present | 1 Introduction | `Vision Perception, Language Instruction` | 5 | — |
| 2311.15209 | L3 | present | 3.1 Overview | `integrates Visual Perception` | 24 | — |
| 2311.15209 | L4 | present | 1 Introduction | `STEVE-21K dataset, including 600+` | 14 | — |
| 2505.12321 | L1 | present | Abstract | `simulator, BeliefNest` | 1 | — |
| 2505.12321 | L2 | present | Abstract | `multiple physical simulators` | 2 | — |
| 2505.12321 | L3 | present | Abstract | `by leveraging Theory of Mind` | 1 | — |
| 2505.12321 | L4 | present | 1 Introduction | `source code is available at https` | 11 | — |
| 2508.18722 | L1 | present | 1 Introduction | `we propose VistaWise` | 7 | — |
| 2508.18722 | L2 | present | 1 Introduction | `a cross-modal knowledge graph` | 7 | — |
| 2508.18722 | L3 | present | 1 Introduction | `to directly predict actions` | 8 | — |
| 2508.18722 | L4 | present | 4.1 Dataset and Implementation | `on an L4 GPU with 24G VRAM` | 159 | — |
| 2505.24157 | L1 | present | 1 Introduction | `we propose Robust and Efficient Planning` | 7 | — |
| 2505.24157 | L2 | present | 1 Introduction | `Adaptive Dependency Learning (ADL)` | 7 | — |
| 2505.24157 | L3 | present | Abstract | `to enhance robustness to knowledge` | 2 | — |
| 2505.24157 | L4 | present | Implementation details | `we use Qwen2.5-VL-7B` | 45 | — |
| 2606.12852 | L1 | present | 1 Introduction | `we introduce WISE` | 9 | — |
| 2606.12852 | L2 | present | 1 Introduction | `a Causal Event Graph` | 16 | — |
| 2606.12852 | L3 | present | 1 Introduction | `the scheduler adapts to newly observed` | 10 | — |
| 2606.12852 | L4 | present | 4.1 Experiment Setups | `four NVIDIA RTX 4080 GPUs` | 85 | — |
| 2409.19479 | L1 | ambiguous | — | — | — | 首次证据 Thirdly, LangProp 孤立看是贡献列表中的一项、像引用前人，无法定位到「本文提出方法」的命名句。 |
| 2409.19479 | L2 | present | Abstract | `a vision-to-action transformer backend` | 8 | — |
| 2409.19479 | L3 | present | Abstract | `by treating code as learnable policies` | 7 | — |
| 2409.19479 | L4 | ambiguous | — | — | — | 首次证据 third place in the MineRL BASALT 是竞赛名次/性能宣称；按关键纪律不算具体值。 |
| 2405.15414 | L1 | present | 4 Method | `we introduce the Luban agent` | 15 | — |
| 2405.15414 | L2 | present | 4 Method | `3D structural speculation stage` | 16 | — |
| 2405.15414 | L3 | present | 1 Introduction | `aimed at empowering open-ended agents` | 7 | — |
| 2405.15414 | L4 | present | 5.1 Exprimental Settings | `with gpt-4-vision-preview` | 28 | — |
| 2507.03293 | L1 | present | 1.2 Contributions | `We propose LTLCrit` | 12 | — |
| 2507.03293 | L2 | present | 1.2 Contributions | `a two-timescale architecture` | 15 | — |
| 2507.03293 | L3 | present | 1.2 Contributions | `by protecting the planners against` | 12 | — |
| 2507.03293 | L4 | present | 4.1 Experimental Setup | `Temperatures are set to 0.1` | 81 | — |
| 2601.05215 | L1 | present | Abstract. | `We present MineNPC-Task` | 2 | — |
| 2601.05215 | L2 | present | 1. Introduction | `Intent routing parses chat` | 15 | — |
| 2601.05215 | L3 | present | 1. Introduction | `To execute tasks reproducibly` | 6 | — |
| 2601.05215 | L4 | present | Abstract. | `instantiate the framework with GPT-4o` | 3 | — |
| 2305.16291 | L1 | present | Abstract | `We introduce Voyager` | 1 | — |
| 2305.16291 | L2 | present | 1 Introduction | `an automatic curriculum` | 6 | — |
| 2305.16291 | L3 | present | Abstract | `that continuously explores the world` | 1 | — |
| 2305.16291 | L4 | present | 3.1 Experimental Setup | `We set all temperatures to 0` | 47 | — |
| 2403.08282 | L1 | present | 1 Introduction | `We introduce HAS` | 11 | — |
| 2403.08282 | L2 | present | 3 HAS: A Multi-agent Navigation Framework | `M-MLM and A-MLM` | 21 | — |
| 2403.08282 | L3 | present | 1 Introduction | `It utilizes centralized planning` | 11 | — |
| 2403.08282 | L4 | present | 4.1 Experimental Setups | `gpt-4-1106-vision-preview` | 54 | — |
| 2608.22055 | L1 | present | Abstract. | `We introduce GenCoord` | 1 | 换证据：原证据「GenCoord represents sender and peer」是功能描述（更接近 L3），改取 Abstract 的命名句。 |
| 2608.22055 | L2 | present | 1. Introduction | `parse, schema check, canonical` | 11 | — |
| 2608.22055 | L3 | present | 1. Introduction | `to compose goals, capabilities, objects` | 8 | — |
| 2608.22055 | L4 | present | 5.2. Data and Training | `Training uses two epochs` | 83 | — |
| 2411.12977 | L1 | present | 1 Introduction | `we introduce the MindForge framework` | 8 | — |
| 2411.12977 | L2 | present | 1 Introduction | `perspective-taking through a causal ToM` | 9 | — |
| 2411.12977 | L3 | present | 1 Introduction | `using Theory of Mind (ToM)` | 8 | — |
| 2411.12977 | L4 | present | 5.2 Voyager With Open-Weight LLMs | `Mistral-7B [25], Mixtral-8x7B` | 34 | — |
| 2410.07484 | L1 | present | 1 Introduction；Abstract | `World Alignment by ruLe LEarning`；`WALL-E achieves higher success rates` | 9；2 | 两条 evidence 均列出：第 2 条「WALL-E achieves higher success rates」首次 ANNOTATION.md 漏了依据，此处补上。 |
| 2410.07484 | L2 | present | 1 Introduction | `the neurosymbolic world model` | 9 | — |
| 2410.07484 | L3 | present | 1 Introduction | `by learning complementary rules with` | 9 | — |
| 2410.07484 | L4 | present | 4 Experiments | `134 testing tasks from the ALFWorld` | 64 | — |
| 2411.06736 | L1 | present | 1 Introduction | `MrSteve (Memory Recall Steve)` | 8 | — |
| 2411.06736 | L2 | present | 3 Method | `consists of Memory Module and Solver` | 19 | — |
| 2411.06736 | L3 | present | 1 Introduction | `this framework enables the agent to` | 9 | — |
| 2411.06736 | L4 | present | Abstract | `project page: https://sites.google.com` | 2 | — |
| 2501.19318 | L1 | present | 1 Introduction | `we propose MINDSTORES` | 12 | — |
| 2501.19318 | L2 | present | 1 Introduction | `an experience database storing natural` | 13 | — |
| 2501.19318 | L3 | present | 1 Introduction | `operates cyclically: observe, retrieve` | 13 | — |
| 2501.19318 | L4 | present | 4.1 Experimental Setup | `Sentence-BERT embeddings (768-dim)` | 48 | — |
| 2405.17424 | L1 | present | 1 Introduction | `we first propose Large Auto-Regressive` | 7 | — |
| 2405.17424 | L2 | present | 4.1 Referee Reinforcement Learning | `we introduce referee RL` | 43 | — |
| 2405.17424 | L3 | present | 4.1 Referee Reinforcement Learning | `to provide an auxiliary reward feedback` | 43 | — |
| 2405.17424 | L4 | present | 5.2 Main Results | `MineAgent (Fan et al. 2022), Plan4MC` | 178 | 换证据：原证据为 Keywords: 区 URL（关键纪律明确不算），改取 baseline 具体名句子。 |

## ambiguous 单独列出

本次 `ambiguous` 共 **13 格**（另有 `absent` **1 格**），全部由本次按 §4 从严重判产生；
首次冻结为 0 格。逐格如下（理由见上表）：

| arxiv_id | 层 | label | 领域 |
|---|---|---|---|
| 2404.12495 | L4 | ambiguous | image_restoration |
| 2503.17915 | L4 | ambiguous | image_restoration |
| 2504.14249 | L4 | ambiguous | image_restoration |
| 2407.11087 | L4 | ambiguous | image_restoration |
| 2511.05873 | L4 | ambiguous | image_restoration |
| 2602.00749 | L4 | ambiguous | image_restoration |
| 2605.06127 | L4 | ambiguous | image_restoration |
| 2607.28526 | L4 | ambiguous | image_restoration |
| 2608.06832 | L4 | ambiguous | image_restoration |
| 2608.06939 | L4 | ambiguous | image_restoration |
| 2609.02839 | L4 | ambiguous | image_restoration |
| 2409.19479 | L1 | ambiguous | agent_in_mc |
| 2409.19479 | L4 | ambiguous | agent_in_mc |

其中 12 格集中在 `image_restoration`（该域 L4 只有 8/20 `present`），1 格在
`agent_in_mc`（L4 竞赛名次）。`2409.19479` 的 L1 与 L4 两格均改判。`ambiguous` 出口
本次真实触发，不再是首次冻结那种「声明是出口却 0 次使用」的状态。

另有 1 格 `absent`：`2609.16578`/L4（`image_restoration`）——实验设置明写在
Appendix A.2/A.3，缓存 HTML 可见全文未给出 §4 五类的具体值；理由见逐条依据表。
