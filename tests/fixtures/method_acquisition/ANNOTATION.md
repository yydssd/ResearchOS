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
- 后三次都是**对已冻结标签的重新判定**，不是新一轮独立标注，因此没有新的独立标注
  起止时间；历次判读沿用同一批 HTML 原文与同一批 owner 侧判读。

## 隔离顺序

1. 首次冻结（提交 `424c976`）：只读 HTML 原文、两个 ids 清单、`load_html` /
   `chunk_pages` 两个文档加载函数，逐篇读文产出 160 格，与本文同一提交写入夹具。
2. 第一次修订（提交 `93c3174`）：**坦白，方向错了**。它把「首次挑的那条 quote
   不合格」当成「论文没有该层信息」，把 13 格 L4 直接改判 `ambiguous`/`absent`，
   没有全文重新取证；复审判 Approved: NO。
3. 第二次修订（提交 `078dd91`）：按 §4 对 14 格**扫该篇全部 chunks 重新取证**
   （去掉 `chunks[:40]` 限制），找到 §4 五类具体值就换 `evidence`、保持/恢复
   `present`；全文确实找不到才保留非 present 并写出核查记录。
4. 本次修订：第三次复审指出 `2409.19479`/L1 的命名句在结论章；按同一条「全文
   找到就换证据、label 保持 `present`」纪律，回查该篇 ci=1137 `7 Conclusion`
   的 `This work presented LangProp`，把该格由 `ambiguous` 改回 `present`。以
   **新提交** 修订，保留 `424c976` / `93c3174` / `078dd91` 历史。冻结之后才
   实现 / 运行 `scripts/method_acquisition_audit.py`（本次修订期间该文件仍不存在，
   也未被读取或运行）。
5. 顺序可用 `git log --oneline -- tests/fixtures/method_acquisition/` 复核：该路径
   按时间先后应列出 `424c976`、`93c3174`、`078dd91` 与「本次修订的最新一条提交」；
   具体 SHA 以该命令实际输出为准，本文不写自引用的当前提交号。

隔离禁令在历次判读中一直有效：禁止读取或 import `src/research_os/research/claims.py`、
`quantitative.py`、`conditions.py`、`claim_builder.py`、`lexicon.py`；禁止运行任何会
产出 claims / quantitative_evidence / identity_key / conditions 的 pipeline；禁止读取
或运行 `scripts/method_acquisition_audit.py`。全程未触碰上述文件或产出，也未读取
`docs/evaluation/annotation-sheet-2026-11-14.*` 等任何现成标注表。

执行偏差与根因记录：计划 Step 2 脚本的 `from research_os.documents import
chunk_pages` 在本仓库不成立（`documents/__init__.py` 未 re-export），改用其定义模块
`from research_os.documents.chunks import chunk_pages`；函数与调用
`chunk_pages(load_html(...))` 完全一致，仍只读原文。**更关键的根因**：候选导出只取
`chunks[:40]`，而单篇最多 1555 个 chunk；第一次修订所谓「找不到具体值」其实是
「前 40 个 chunk 里没有」。本次改为扫全部 chunks（见「全文重新取证核查记录」）。
为逐篇判定，另在 gitignored 的 `.holdout_cache/` 下导出 `annotation_full.txt`、
`annotation_tail.txt`、`annotation_exp.txt` 三份只读原文摘录（同样只用 `load_html` +
`chunk_pages`），均不提交；本次修订改用内联执行重新生成夹具，不新增脚本文件。

## 逐层判据（§4，逐字）

下表是要求逐字执行的判据。**首次冻结并未真正逐字执行**：它系统性放宽了 L4 对
「具体值」的门槛（把数据集名、表格标题、表注泛泛句、图注、竞赛名次、`Keywords:`
区 URL 当成具体值），把 160 格全判 `present`。**第一次修订（93c3174）也走偏**：
它用证据质量替代事实判断，直接把 13 格改判，而没有按 §4 重新取证。本次才按
「论文有没有给出该层信息」逐格重判并重新取证；并且**不得**把「证据可定位性回查
`ALL OK`」当作判据已满足的佐证——那只是定位性，不是符合性。

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

关键纪律（本次逐字执行）：**找到** §4 五类之一的真实具体值就换 `evidence`、
label 保持 `present`；**全文确实找不到**才判 `absent` 或 `ambiguous` 并写出核查记录。
不许为了保住 present 而拿表格标题/数据集名/性能宣称凑数；也不许为了凑出非 present
而回避重新取证。数据集名、表格标题、表注泛泛句、图注、竞赛名次、性能宣称、
`Keywords:` 区 URL 都**不等于** L4 的「具体值」。

## 判据符合性自查

必须明确区分两件事：

- **证据可定位性回查**（首次冻结已有，本次重跑仍 `ALL OK`）：只证明 `quote` 是对应
  `chunk_index` 归一化文本的真实连续子串、≤40 字符、`section` 与该 chunk 真实标题
  一致。它**不证明**判据符合性；把 `ALL OK` 当作「判据已满足」是错误的。
- **判据符合性**（本次新增）：逐格人工重读证据句，判断其是否真的给出该层要求的
  信息；对 14 格进一步扫该篇**全部 chunks** 重新取证，让 `label` 回答「论文有没有
  给出该层信息」，而不是「首次挑的那条 quote 合不合格」。本次第三次复审又对
  `2409.19479`/L1 沿用同一纪律：该篇 1555 chunks 已全扫，在 ci=1137
  `7 Conclusion` 找到 `This work presented LangProp`，据以把该格由 `ambiguous`
  改回 `present`。

审验独立回查给出的分布（按首次冻结证据判定）。**口径分别标明**：`N` = 明确不满足，
`B` = 边界（仅数据集/基准名），「含边界」= `N + B`。上次 `ANNOTATION.md` 的
「L4 = 13」用的是**含边界（N+B）口径**，「L1 = 1」用的是**只算 N 口径**，两者不
一致；本次统一分别标出：

| 层 | S（满足） | N（明确不满足） | B（边界） | 含边界 N+B |
|---|---|---|---|---|
| L4 | 27 | 4 | 9 | 13（32.5%，其中 12 格在 `image_restoration`） |
| L1（抽查 5 格） | 1 | 1 | 3 | 4 |
| L2 / L3 | 大体站得住 | — | — | — |

### 全文重新取证核查记录（14 格）

复审全文实扫 22292 chunks 找到至少 7 格被误判；本次对复审给出的 14 个 id 全部
重扫（每篇扫描全部 chunks，统计 `total` 与五类模式命中数 `hits`），逐格人工核定：

| arxiv_id | 原 label | 新 label | 全文 chunks / 命中 | 找到的 §4 具体值（位置） | 处置 |
|---|---|---|---|---|---|
| 2404.12495 | ambiguous | ambiguous | 120 / 2 | 无；ci=79 `GPUfit`/`pyGPUfit` 属拟合工具名、`>1 MHz`/`≈5 mm` 属仪器能力，ci=119 为致谢 | **保留 ambiguous**，写出核查记录 |
| 2503.17915 | ambiguous | present | 737 / 8 | ci=469 `120 epochs with a batch size of 16`（超参）；另 ci=0 项目 URL、ci=693 `Using PromptIR [37] as our baseline` | 换证据 |
| 2504.14249 | ambiguous | present | 802 / 9 | ci=717 `using a NVIDIA Tesla A100 (40G) GPU`（环境） | 换证据 |
| 2409.19479 | ambiguous | present | 1555 / 69 | ci=435 `https://github.com/shuishida/calvin`（代码仓库）；ci=298 `{20,40,60,80,100}` 超参集合 | 换证据 |
| 2407.11087 | ambiguous | present | 555 / 12 | ci=2 `github.com/Yaziwel/Restore-RWKV`（代码仓库）；ci=176 `a batch size of 4`、`learning rate 2e-4` | 换证据 |
| 2511.05873 | ambiguous | present | 510 / 7 | ci=285 `performed on NVIDIA A40 GPUs`（环境）、`100 epochs`、`learning rate 2×10⁻⁴` | 换证据 |
| 2602.00749 | ambiguous | present | 704 / 9 | ci=576 `8 NVIDIA GeForce RTX 4090 GPUs`（环境）；ci=570 `β1,β2 ... set as 2.0,0.5` | 换证据 |
| 2605.06127 | ambiguous | present | 969 / 12 | ci=210 `a total batch size of 64`（附录 B.3）、lr `5×10⁻⁴`、120 epochs；ci=139 `single local NVIDIA RTX 4090 GPU` | 换证据 |
| 2607.28526 | ambiguous | present | 676 / 6 | ci=595 `with a batch size of 32`（超参），同段还有 lr `2×10⁻⁴`、`β1=0.9`、`β2=0.99` | 换证据 |
| 2608.06832 | ambiguous | present | 614 / 14 | ci=70 `1 NVIDIA A100 GPU with batch size 64`（环境+超参）；ci=463 baseline 具体名 | 换证据 |
| 2608.06939 | ambiguous | present | 829 / 13 | ci=3 `github.com/fanamber831/DCMPC-Net`（代码仓库）；ci=383 `initial learning rate 3×10⁻⁴` | 换证据 |
| 2609.02839 | ambiguous | present | 270 / 10 | ci=170 `conducted on a 24GB RTX 4090 GPU`（环境）；ci=58 `first 10 epochs`（ar5iv 回声为 `1010`） | 换证据 |
| 2609.16578 | absent | present | 547 / 5 | ci=437 `the scale penalty is set to γ=0.05`（附录 A.2.2）、`τ=0.20`、`β=10` | 换证据；删除「设置明写在附录却说全文未给出」的自相矛盾理由 |
| 2405.17424 | present | present | 233 / 6 | ci=147 `using a single RTX4090 GPU`（环境）；原 `Keywords:` 区 URL 按纪律不算 | 复核并换成更明确的证据 |

其中 `2404.12495`/L4 是唯一「全文确实找不到 §4 具体值」的格：扫过 120 chunks，
按五类模式命中 2 行，人工核定均不构成 baseline / 超参 / 环境具体值 / 评测协议数值 /
代码仓库链接中的任何一项；故保留 `ambiguous`。`2609.16578`/L4 的附录 A.2.2 明确
给出超参数，故从 `absent` 改回 `present`，上轮「设置明写在 Appendix A.2/A.3」与
「全文未给出」自相矛盾的理由一并删除。

### 逐层重判结果

- **L1**：`2409.19479`/L1 按该篇全文 1555 chunks 复核，在 ci=1137 `7 Conclusion`
  找到 `This work presented LangProp`（ci=436 `6 Conclusion` 另有 CALVIN 的归属
  命名句），两句均满足 §4 L1「出现方法名且能看出是本文提出」，故由 `ambiguous`
  改回 `present` 并换证据；`2310.18293`/L1、`2404.12495`/L1 两格换含专名的命名句
  后保持 `present`；其余各格复核后保留 `present`。最终 **40/40 `present`**。
- **L2**：全量复核 40 格，证据均为具体组件、模块、backbone 或流程步骤的描述，
  40/40 `present`，未触发 `ambiguous`。
- **L3**：全量复核 40 格，证据均为机制或设计意图句，40/40 `present`，未触发
  `ambiguous`。这不等于 L2/L3 无主观性；若后续独立复标改判须以新提交修订。
- **L4**：14 格全文重取证后，12 格改回 `present`（含 1 格由 `absent` 改回）、
  1 格 `2405.17424` 复核后换证据保持 `present`、1 格 `2404.12495` 保留
  `ambiguous`。最终 **present 39 / ambiguous 1**（IR 19/1、MC 20/0）。

## 统计

总计 **159 `present` / 0 `absent` / 1 `ambiguous`**（160 格）。

| 领域 | 层 | present | absent | ambiguous |
|---|---|---|---|---|
| image_restoration | L1 | 20 | 0 | 0 |
| image_restoration | L2 | 20 | 0 | 0 |
| image_restoration | L3 | 20 | 0 | 0 |
| image_restoration | L4 | 19 | 0 | 1 |
| image_restoration | 合计 | 79 | 0 | 1 |
| agent_in_mc | L1 | 20 | 0 | 0 |
| agent_in_mc | L2 | 20 | 0 | 0 |
| agent_in_mc | L3 | 20 | 0 | 0 |
| agent_in_mc | L4 | 20 | 0 | 0 |
| agent_in_mc | 合计 | 80 | 0 | 0 |
| 全部 | 合计 | 159 | 0 | 1 |

## 判读说明与边界样本

- 首次冻结的 160/160 不是真实语料分布，问题在**证据挑得差**（数据集名、表格标题、
  表注泛句、图注、竞赛名次、`Keywords:` 区 URL），不在于 `present` 这个 label 本身。
  第一次修订误把「证据差」当成「事实缺失」，把 13 格直接改判；本次按 §4 全文重新
  取证后，L4 有 39/40 格的论文确实给出了具体值，而**证据已全部换成 §4 五类之一的
  真实具体值**（仓库 URL、GPU 型号、batch size / learning rate / epochs / 附录超参、
  baseline 具体名）。第三次复审进一步指出 `2409.19479`/L1 的命名句在结论章；按
  同一纪律回查 ci=1137 并改回 `present`，该篇四层现均为 `present`。
- 每条 `present` 证据的可定位性仍经机械回查（`ALL OK`），但如「判据符合性自查」
  所述，该回查只证明定位性；符合性由逐格人工重读给出，见下表逐条依据。
- `page_label` 恒为 `html`（`load_html` 对 HTML 页固定产出 `page_label="html"`），
  定位主要靠 `chunk_index` + `section`；`section` 为 null 的 chunk（如 `2409.19479`
  开头 3 个 LaTeX / glossaries chunk）一律未用作证据。
- 边界样本：`2404.12495` 是量子金刚石显微镜仪器 / 测量论文而非 ML 方法论文（落在
  图像复原 holdout 清单里属清单噪声），L1/L2/L3 按字面判据可定位，L4 全文 120
  chunks 无 §4 五类具体值，保留 `ambiguous`；`2409.19479` 是博士论文，含 CALVIN /
  SOAP / LangProp / Voggite 多个本文方法名，L4 已按 `https://github.com/shuishida/calvin`
  与 `{20,40,60,80,100}` 超参集合改回 `present`，L1 亦在 ci=1137 `7 Conclusion`
  找到 `This work presented LangProp`（ci=436 `6 Conclusion` 另有 CALVIN 归属句），
  该篇四层现均为 `present`；`2406.11247` 是 65-chunk 短文，
  L1 已换为 `Our STEVE Series agents`；`2601.05215`、`2504.17950`、
  `2505.12321` 是 benchmark / 平台 / 模拟器论文——其「方法」是评测框架 / 平台本身。
- `2405.17424`/L4 按关键纪律不再用 `Keywords:` 区 URL，全文取证改取 ci=147 的
  `using a single RTX4090 GPU`（环境具体值）。
- `2410.07484`/L1 两条 evidence 均列出（`1 Introduction` 的命名句与 `Abstract` 的
  `WALL-E achieves higher success rates`）。

## 已知限制

- 标注由 owner 侧同一 agent 产生，非独立、非盲标；无第二位标注者、无独立复标、
  无跨日重标，因此不存在可报告的一致率 / 正确率。
- 判读存在主观性，尤其 L3（「机制或设计意图句」）与 L4（「具体值」是否属于列举的
  5 类）；`ambiguous` 是主观边界的出口，本次仅在 L4（1 格）触发（L1 已回到
  40/40 `present`），L2/L3 复核后未触发。这不代表他人判读会得出同样结果。
- 本夹具 **不回答「系统抽得对不对」**：它只固定覆盖率 C 的分母（论文里可获取的
  方法信息）；分子（系统实际抽取）由冻结之后实现的审计脚本给出，两者不得互相参照。
- **`A` 不再恒 100%**：现仅由 `image_restoration`/L4 的 19 格 `present` 单独
  支撑（`agent_in_mc` 四层均已回到 20 格 `present`），该层小于 20，因此 `C` 的
  分母不再恒为 20；任何按「每层 20 篇全 present」写的公式或断言都必须按本表重算。
- **本次没有任何（领域, 层）组合 `present=0`**（最低为 19）。因此
  `present=0 → N/A` 分支在真实夹具上不触发，只由合成夹具验证；不能据此声称该
  分支已被真实语料覆盖。
- **不得静默改数**：四次判读分别是首次冻结 `424c976`、第一次修订 `93c3174`
  （方向错误）、第二次修订 `078dd91`（全文重新取证）与本次修订（新提交），历史
  全部保留；不 amend、不 force push、不删旧提交。`160/160`、`146/1/13`、
  `158/0/2`、`159/0/1` 四个版本都在
  `git log --oneline -- tests/fixtures/method_acquisition/` 中可见，纠正以可见的
  方式完成。若后续独立复核再改判某格，须同样以新提交修订 `labels.json` 并重算覆盖率。
- `labels.json` 顶层只有 `labels` 一个键；本夹具不另设 id 清单，`domain` 仅取
  `image_restoration` / `agent_in_mc`。

## 逐条依据（40 篇 × 4 层）

下列每格给出 label；`present` 附全部 evidence 的 `section` + `quote`（另附
`chunk_index` 便于定位），多条 evidence 以 `；` 分隔；`absent` / `ambiguous` 各给一句
理由。`ambiguous` 单独列于下节。

### image_restoration（20 篇）

| arxiv_id | 层 | label | section | quote（原文子串，≤40 字符） | chunk_index | 依据 / 理由 |
|---|---|---|---|---|---|---|
| 2310.18293 | L1 | present | 1 Introduction | `Overview of proposed UtilityIR` | 24 | Minor 处置（换证据）：原 `all-in-one image restoration method` 是通用类名、不含专名，改取 `Overview of proposed UtilityIR`（含专名与 `proposed` 的命名句）。 |
| 2310.18293 | L2 | present | 1 Introduction | `Degradation Information Encoder (DIE)` | 24 | — |
| 2310.18293 | L3 | present | Abstract | `to guide weather severity and type` | 2 | — |
| 2310.18293 | L4 | present | 4.1 Implementation Details | `set the batch size to 2` | 67 | — |
| 2403.14614 | L1 | present | 1 Introduction | `our AdaIR algorithm` | 24 | — |
| 2403.14614 | L2 | present | 1 Introduction | `Adaptive Frequency Learning Block (AFLB)` | 22 | — |
| 2403.14614 | L3 | present | Abstract | `mine low- and high-frequency information` | 2 | — |
| 2403.14614 | L4 | present | 4 Experiments | `we adopt a batch size of 32` | 63 | — |
| 2404.12495 | L1 | present | Abstract | `a quantum diamond microscope (QDM)` | 1 | Minor 处置（换证据、保留 present）：原 `The all-in-one QDM is configurable` 是功能描述句；改取 Abstract 归属命名句内的 `a quantum diamond microscope (QDM)`，整句 `This work demonstrates a quantum diamond microscope (QDM)...` 明确本文演示的装置；`all-in-one QDM` 亦见标题与 Table 1。 |
| 2404.12495 | L2 | present | I Introduction | `An LED with linear polarization control` | 5 | — |
| 2404.12495 | L3 | present | I Introduction | `to create a transmission measurement` | 5 | — |
| 2404.12495 | L4 | ambiguous | — | — | — | 全文 120 chunks 按五类模式命中 2 行（ci=79 GPU 拟合软件/数据规模、ci=119 致谢），人工核定均非 §4 五类具体值；`>1 MHz`/`≈5 mm` 属仪器能力描述、`GPUfit`/`pyGPUfit` 属数据处理工具名，不构成 baseline/超参/环境/评测协议/代码链接的具体值。 |
| 2407.11087 | L1 | present | 1 Introduction | `we propose Restore-RWKV` | 10 | — |
| 2407.11087 | L2 | present | 1 Introduction | `We present a recurrent WKV (Re-WKV)` | 16 | — |
| 2407.11087 | L3 | present | 1 Introduction | `by shifting tokens from all directions` | 11 | — |
| 2407.11087 | L4 | present | Abstract | `github.com/Yaziwel/Restore-RWKV` | 2 | 全文重取证：ci=2 `github.com/Yaziwel/Restore-RWKV`（代码仓库）；原仅数据集名。 |
| 2503.17915 | L1 | present | 1 Introduction | `we present Cat-AIR` | 7 | — |
| 2503.17915 | L2 | present | 1 Introduction | `alternating spatial-channel attention` | 13 | — |
| 2503.17915 | L3 | present | 1 Introduction | `that enables our framework to extend` | 15 | — |
| 2503.17915 | L4 | present | 4.1 Implementation details | `120 epochs with a batch size of 16` | 469 | 全文重取证：ci=469 `120 epochs with a batch size of 16`（超参）；原仅表注泛句。 |
| 2504.09377 | L1 | present | 1. Introduction | `method called HOGformer` | 14 | — |
| 2504.09377 | L2 | present | 1. Introduction | `Dynamic HOG-aware Self-Attention` | 10 | — |
| 2504.09377 | L3 | present | 1. Introduction | `that incorporates gradient orientations` | 16 | — |
| 2504.09377 | L4 | present | 4.2. Implementation Details. | `on NVIDIA Tesla A100 GPUs` | 310 | — |
| 2504.14249 | L1 | present | 1. Introduction | `We propose AnyIR` | 17 | — |
| 2504.14249 | L2 | present | Image Restoration (IR) | `a convolutional patch embedding` | 22 | — |
| 2504.14249 | L3 | present | 1. Introduction | `optimally intertwines global context` | 15 | — |
| 2504.14249 | L4 | present | 4.1. State of the Art Comparison | `using a NVIDIA Tesla A100 (40G) GPU` | 717 | 全文重取证：ci=717 `using a NVIDIA Tesla A100 (40G) GPU`（环境）；原仅表格标题。 |
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
| 2511.05873 | L4 | present | Experiment Settings | `performed on NVIDIA A40 GPUs` | 285 | 全文重取证：ci=285 `performed on NVIDIA A40 GPUs`（环境）；原仅数据集名。 |
| 2602.00749 | L1 | present | 1 Introduction | `we first propose HSI-VAR` | 8 | — |
| 2602.00749 | L2 | present | 2.1 Regression Methods for Restoration | `Structure of the multi-scale VQVAE` | 16 | — |
| 2602.00749 | L3 | present | 1 Introduction | `which progressively models the spectral` | 8 | — |
| 2602.00749 | L4 | present | 4.1 Experimental Setup | `8 NVIDIA GeForce RTX 4090 GPUs` | 576 | 全文重取证：ci=576 `8 NVIDIA GeForce RTX 4090 GPUs`（环境）；原仅数据集名。 |
| 2604.05629 | L1 | present | 1 Introduction | `this paper presents LLaRS` | 7 | — |
| 2604.05629 | L2 | present | 3.1 Band Semantic Matching | `using optimal transport (OT)` | 17 | — |
| 2604.05629 | L3 | present | 3.1 Band Semantic Matching | `so multi-sensor inputs are routed` | 17 | — |
| 2604.05629 | L4 | present | Abstract | `Repo: https://github.com/yc-cui/LLaRS` | 3 | — |
| 2605.06127 | L1 | present | 1 Introduction | `we propose Continuous Expert Assembly` | 7 | — |
| 2605.06127 | L2 | present | 1 Introduction | `Cross-Attention Hyper-Adapter` | 8 | — |
| 2605.06127 | L3 | present | 1 Introduction | `the adapter uses learnable queries` | 8 | — |
| 2605.06127 | L4 | present | B.3 Optimization and Training Objective | `a total batch size of 64` | 210 | 全文重取证：ci=210 `a total batch size of 64`（附录 B.3 超参）；原仅基准名。 |
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
| 2607.28526 | L4 | present | 4.1. Experimental Settings | `with a batch size of 32` | 595 | 全文重取证：ci=595 `with a batch size of 32`（超参）；原仅数据集名。 |
| 2608.06832 | L1 | present | 1 Introduction | `We propose FIT` | 15 | — |
| 2608.06832 | L2 | present | 1 Introduction | `a lightweight Degradation Encoder` | 12 | — |
| 2608.06832 | L3 | present | 1 Introduction | `FIT bends patch grids` | 5 | — |
| 2608.06832 | L4 | present | Implementation Details. | `1 NVIDIA A100 GPU with batch size 64` | 70 | 全文重取证：ci=70 `1 NVIDIA A100 GPU with batch size 64`（环境+超参）；原仅数据集名。 |
| 2608.06939 | L1 | present | I Introduction | `we propose a Degradation-Aware` | 19 | — |
| 2608.06939 | L2 | present | I Introduction | `Cross-Modal Prompt Generator` | 25 | — |
| 2608.06939 | L3 | present | Abstract | `that disentangles degradation artifacts` | 3 | — |
| 2608.06939 | L4 | present | Abstract | `github.com/fanamber831/DCMPC-Net` | 3 | 全文重取证：ci=3 `github.com/fanamber831/DCMPC-Net`（代码仓库）；原仅数据集名。 |
| 2609.02839 | L1 | present | 1 Introduction | `we present FReSH-IR` | 8 | — |
| 2609.02839 | L2 | present | 3.2 Overall Framework | `Spectral Decomposition Block (SDB)` | 22 | — |
| 2609.02839 | L3 | present | 1 Introduction | `designed to bridge the gap` | 8 | — |
| 2609.02839 | L4 | present | Appendix C Additional efficiency results. | `conducted on a 24GB RTX 4090 GPU` | 170 | 全文重取证：ci=170 `conducted on a 24GB RTX 4090 GPU`（环境）；原仅数据集名。 |
| 2609.16578 | L1 | present | 1 Introduction | `we propose GraLoD` | 7 | — |
| 2609.16578 | L2 | present | Abstract | `minimal-sufficient footprint calibration` | 2 | — |
| 2609.16578 | L3 | present | 1 Introduction | `evaluates the local restoration utility` | 8 | — |
| 2609.16578 | L4 | present | A.2.2 Default Hyperparameters | `the scale penalty is set to γ=0.05` | 437 | 全文重取证：ci=437 `the scale penalty is set to γ=0.05`（附录 A.2.2 超参）；原判 absent 的理由自相矛盾，已删除。 |

### agent_in_mc（20 篇）

| arxiv_id | 层 | label | section | quote（原文子串，≤40 字符） | chunk_index | 依据 / 理由 |
|---|---|---|---|---|---|---|
| 2605.27762 | L1 | present | Abstract | `We present PEAM` | 1 | — |
| 2605.27762 | L2 | present | 1 Introduction | `A slow deliberative LLM handles` | 8 | — |
| 2605.27762 | L3 | present | 1 Introduction | `PEAM consolidates experience into` | 7 | — |
| 2605.27762 | L4 | present | 4.1 Setup | `We instantiate PEAM in Minecraft 1.19` | 111 | — |
| 2406.11247 | L1 | present | Abstract | `Our STEVE Series agents` | 1 | — |
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
| 2409.19479 | L1 | present | 7 Conclusion | `This work presented LangProp` | 1137 | 全文复核：ci=1137 `7 Conclusion` 的 `This work presented LangProp`（ci=436 `6 Conclusion` 另有 CALVIN 归属句），明确本文提出的方法，故由 `ambiguous` 改回 `present`。 |
| 2409.19479 | L2 | present | Abstract | `a vision-to-action transformer backend` | 8 | — |
| 2409.19479 | L3 | present | Abstract | `by treating code as learnable policies` | 7 | — |
| 2409.19479 | L4 | present | 6 Implementation | `https://github.com/shuishida/calvin` | 435 | 全文重取证：ci=435 `https://github.com/shuishida/calvin`（代码仓库）；原仅竞赛名次。 |
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
| 2608.22055 | L1 | present | Abstract. | `We introduce GenCoord` | 1 | — |
| 2608.22055 | L2 | present | 1. Introduction | `parse, schema check, canonical` | 11 | — |
| 2608.22055 | L3 | present | 1. Introduction | `to compose goals, capabilities, objects` | 8 | — |
| 2608.22055 | L4 | present | 5.2. Data and Training | `Training uses two epochs` | 83 | — |
| 2411.12977 | L1 | present | 1 Introduction | `we introduce the MindForge framework` | 8 | — |
| 2411.12977 | L2 | present | 1 Introduction | `perspective-taking through a causal ToM` | 9 | — |
| 2411.12977 | L3 | present | 1 Introduction | `using Theory of Mind (ToM)` | 8 | — |
| 2411.12977 | L4 | present | 5.2 Voyager With Open-Weight LLMs | `Mistral-7B [25], Mixtral-8x7B` | 34 | — |
| 2410.07484 | L1 | present | 1 Introduction；Abstract | `World Alignment by ruLe LEarning`；`WALL-E achieves higher success rates` | 9；2 | 两条 evidence 均列出：第 2 条 `WALL-E achieves higher success rates`（Abstract, ci=2）首次逐条依据表漏列，已补。 |
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
| 2405.17424 | L4 | present | 4.2 Large Auto-Regressive Model | `using a single RTX4090 GPU` | 147 | 全文复核：按关键纪律不再用 `Keywords:` 区 URL；改取 ci=147 `using a single RTX4090 GPU`（环境具体值），label 仍 present。 |

## ambiguous 单独列出

本次 `ambiguous` 共 **1 格**（`absent` **0 格**），按重判后的真实统计为
**`image_restoration` 1 格 / `agent_in_mc` 0 格**：唯一剩余的是 `2404.12495`/L4。
上一版「IR 1 / MC 1」中的 MC 1 格为 `2409.19479`/L1，本次已在其
`7 Conclusion`（ci=1137）找到 `This work presented LangProp` 并改回 `present`，
MC 四层现均为 20 格 `present`。

| arxiv_id | 层 | label | 领域 | 核查记录 |
|---|---|---|---|---|
| 2404.12495 | L4 | ambiguous | image_restoration | 扫过 120 chunks，按五类模式命中 2 行（ci=79 GPU 拟合工具 / 数据规模、ci=119 致谢），人工核定无 §4 五类具体值 |

`absent` 本次 0 格：上轮唯一的 `2609.16578`/L4 已在附录 A.2.2 找到
`γ=0.05 / τ=0.20 / β=10` 等超参，改回 `present`。`ambiguous` 出口仍真实触发
（1 格），不再出现「声明是出口却 0 次使用」的状态。
