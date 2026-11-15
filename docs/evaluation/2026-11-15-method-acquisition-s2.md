# 方法获取能力 · S2 实测（2026-11-15）

> 命令：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`
> 语料：`docs/evaluation/holdout-ids-2026-11-12.txt` + `holdout-ids-2026-11-14-agent-in-mc.txt`，
> 共 40 篇（图像复原 20 / Agent in MC 20），160 格。
> 判据：设计 §10.1 守恒式 + §10.2 L1 零容忍 + §10.4 逐篇向量。**不预设阈值。**
>
> 本报告的数字来自实现完成后的**一次实跑**（本机 `.holdout_cache`，47 个 html，40 篇有标签）。
> before 一列是 `docs/evaluation/2026-11-14-method-acquisition-audit.md` 的原数字，未改动。

## 1. before / after（同一 40 篇、同一 160 格）

| 层 | 图像复原 before | 图像复原 after | Agent in MC before | Agent in MC after |
|---|---|---|---|---|
| L1 方法身份 | 0/20 | **16/20** | 0/20 | **16/20** |
| L2 方法构成 | 19/20 | **20/20** | 10/20 | **20/20** |
| L3 方法描述 | 0/20 | 0/20 | 0/20 | 0/20 |
| L4 可复现设置 | 11/19 | **19/19** | 14/20 | **20/20** |

`gaps` 合计 **105 → 48**（L1 8 + L3 40，L2/L4 归零）。

两句话必须与这张表一起读：

- **L1/L4 的上升是真的落点**，不是蹭 `conditions`：判据已改成读 `MethodProfile`（设计 §6.7），
  旧判据只认 `backbone=`/`baseline=`/`training=`，那三个字符串与「方法身份」无关。
- **L3 仍是 0，且是结构性的**：S2 没有 L3 生产者，`missing_layers` 已逐篇落库为事实，
  不再是「空字段看起来像没抽」。

## 2. 守恒式（设计 §10.1）

对每个 `(领域, 层)`：`covered + explained_uncovered == present`，`unexplained_uncovered == 0`。

| 格子 | present | covered | explained | 原因分布 | unexplained |
|---|---|---|---|---|---|
| 图像复原 / L1 | 20 | 16 | 4 | 词表未覆盖 4 | **0** |
| 图像复原 / L2 | 20 | 20 | 0 | — | **0** |
| 图像复原 / L3 | 20 | 0 | 20 | 无结构化字段 20 | **0** |
| 图像复原 / L4 | 19 | 19 | 0 | — | **0** |
| Agent in MC / L1 | 20 | 16 | 4 | 词表未覆盖 4 | **0** |
| Agent in MC / L2 | 20 | 20 | 0 | — | **0** |
| Agent in MC / L3 | 20 | 0 | 20 | 无结构化字段 20 | **0** |
| Agent in MC / L4 | 20 | 20 | 0 | — | **0** |

原因取值的含义按设计 §10.1 收紧过一次：「无结构化字段」**只**用于该层还没有落点（S2 的 L3）；
L1/L2/L4 都有字段，它们的缺口一律记「词表未覆盖」——把 L1 的缺口写成「无字段」会夸大缺陷，
因为字段在、模式没匹配到。这次修正在 `1ee2af4`。

**8 篇 L1 未覆盖的原因逐篇成立**：这 8 篇的命名句不在设计 §6.1 的四条构式里
（典型是名字只出现在图注，如 `2310.18293` 的真名 `UtilityIR` 只出现在 "Overview of proposed UtilityIR"）。
它们不是被误判成「没有方法」，`missing_layers` 逐篇记 `L1`。

## 3. 逐篇向量（L2/L4，设计 §10.4）

`before` = 旧判据（`conditions` 的 `backbone=`/`baseline=` 判 L2，`training=` 判 L4）；
`after` = 新判据（`MethodProfile.components` / `setup` 任一子项）。逐篇比，不只比总数。

| domain | paper | L2 before | L2 after | L4 before | L4 after |
|---|---|---|---|---|---|
| image_restoration | 2310.18293 | True | True | True | True |
| image_restoration | 2403.14614 | True | True | True | True |
| image_restoration | 2404.12495 | False | True | False | True |
| image_restoration | 2407.11087 | True | True | False | True |
| image_restoration | 2503.17915 | True | True | True | True |
| image_restoration | 2504.09377 | True | True | False | True |
| image_restoration | 2504.14249 | True | True | False | True |
| image_restoration | 2506.22736 | True | True | False | True |
| image_restoration | 2507.22498 | True | True | False | True |
| image_restoration | 2511.05873 | True | True | True | True |
| image_restoration | 2602.00749 | True | True | True | True |
| image_restoration | 2604.05629 | True | True | True | True |
| image_restoration | 2605.06127 | True | True | True | True |
| image_restoration | 2606.19097 | True | True | True | True |
| image_restoration | 2606.22801 | True | True | True | True |
| image_restoration | 2607.28526 | True | True | False | True |
| image_restoration | 2608.06832 | True | True | False | True |
| image_restoration | 2608.06939 | True | True | True | True |
| image_restoration | 2609.02839 | True | True | True | True |
| image_restoration | 2609.16578 | True | True | False | True |
| agent_in_mc | 2605.27762 | True | True | True | True |
| agent_in_mc | 2406.11247 | True | True | True | True |
| agent_in_mc | 2504.17950 | False | True | True | True |
| agent_in_mc | 2311.15209 | False | True | True | True |
| agent_in_mc | 2505.12321 | False | True | False | True |
| agent_in_mc | 2508.18722 | False | True | True | True |
| agent_in_mc | 2505.24157 | True | True | True | True |
| agent_in_mc | 2606.12852 | True | True | True | True |
| agent_in_mc | 2409.19479 | True | True | True | True |
| agent_in_mc | 2405.15414 | False | True | False | True |
| agent_in_mc | 2507.03293 | False | True | False | True |
| agent_in_mc | 2601.05215 | False | True | False | True |
| agent_in_mc | 2305.16291 | False | True | True | True |
| agent_in_mc | 2403.08282 | False | True | True | True |
| agent_in_mc | 2608.22055 | True | True | False | True |
| agent_in_mc | 2411.12977 | True | True | True | True |
| agent_in_mc | 2410.07484 | False | True | True | True |
| agent_in_mc | 2411.06736 | True | True | True | True |
| agent_in_mc | 2501.19318 | True | True | False | True |
| agent_in_mc | 2405.17424 | True | True | True | True |

**没有任何一篇下降**（`L2 regressions: []`、`L4 regressions: []`）。这一点在实现期间抓到过一次：
`2507.22498` 首次实跑时 L4 由 True 掉成 False，原因是该文只写 `github.com/foo/bar` 而不带 `https://`，
而它的标注证据正是那句 "The code is available at github.com"。按 §10.4「每处下降给理由，否则回滚」，
这里选择修而不是解释：仓库正则改为 scheme 可选并归一化补 `https://`（提交 `1fdf95b`，附一条回归用例）。
修后该篇回到 True，L4 图像复原 19/19。

## 4. L1 精度（零容忍，设计 §10.2）

32 个名字，三条判据逐条核。**任一条不满足即判该篇失败**：

1. `name` 是 `name_quote` 的逐字子串，且该 quote 逐字出现在它指向的 chunk 里；
2. `name` 命中下面这套**独立构式**（手写自设计 §6.1，不复用 `patterns.py`）；
3. `name` 不是更长名字的片段（quote 里名字后面紧跟大写词或 `and + 大写词` 即失败）。

独立构式（本报告内定义，与抽取器实现无关）：

```text
\b(?i:we|this paper|this work)\s+(?i:propose|introduce|present|call)(?:s|d|es)?\s+(?:it\s+)?(?P<a>[A-Z][^\s,.;]{2,})
\b(?i:our)\s+(?i:method|approach|model|framework|system)[,]?\s+(?i:called|named|dubbed)?\s*(?P<b>[A-Z][^\s,.;]{2,})
(?P<c>[A-Z][^\s,.;]{2,})\s*,\s*(?i:our|the)\s+(?i:proposed\s+)?(?i:method|approach|model|framework)\s*,
```

实跑结果：**32 个名字，① 0 失败、② 0 失败、③ 0 失败**。

| paper | name | quote (truncated) | ① verbatim | ② independent | ③ not a fragment |
|---|---|---|---|---|---|
| 2403.14614 | AdaIR | This paper introduces AdaIR, an all-in-one image restoration model cap | True | True | True |
| 2407.11087 | Restore-RWKV | To leverage its advanced design, we propose Restore-RWKV, the first RW | True | True | True |
| 2503.17915 | Cat-AIR | We present Cat-AIR, a novel Content And Task-aware framework for All-i | True | True | True |
| 2504.09377 | HOGformer | In this paper, we present HOGformer, an all-in-one image restoration m | True | True | True |
| 2504.14249 | AnyIR | ∙\bullet We propose AnyIR , a unified and efficient model capable of h | True | True | True |
| 2506.22736 | UniFuse | To address this, we propose UniFuse, a general fusion framework. | True | True | True |
| 2507.22498 | SSGformer | We propose SSGformer, an All-in-One adverse weather removal model with | True | True | True |
| 2511.05873 | EndoIR | We propose EndoIR, an all-in-one, degradation-agnostic diffusion-based | True | True | True |
| 2602.00749 | HSI-VAR | We propose HSI-VAR, first rethinking the HSI restoration as an visual  | True | True | True |
| 2604.05629 | LLaRS | To this end, this paper presents LLaRS (see Fig. | True | True | True |
| 2606.19097 | DVANet | To address these issues, this paper proposes DVANet, a deep unfolding  | True | True | True |
| 2607.28526 | DAR-Net | To mitigate this issue, we propose DAR-Net, a Dual-Ambiguity Rectifica | True | True | True |
| 2608.06832 | FIT | We propose FIT, a unified image restoration architecture that makes th | True | True | True |
| 2608.06939 | DCMPC-Net | To this end, we propose DCMPC-Net, a Degradation-Aware Cross-Modal Pro | True | True | True |
| 2609.02839 | FReSH-IR | (Bottom row) Restored real-world and synthetic images using our method | True | True | True |
| 2609.16578 | GraLoD | Inspired by level-of-detail (LOD) rendering in computer graphics, we p | True | True | True |
| 2605.27762 | PEAM | We present PEAM, a Parametric Embodied Agent Memory framework in Minec | True | True | True |
| 2504.17950 | MineCollab | We introduce MineCollab, an example of a benchmark that can be built i | True | True | True |
| 2311.15209 | STEVE | This paper proposes STEVE, a comprehensive and visionary embodied agen | True | True | True |
| 2505.12321 | BeliefNest | In this paper, we propose BeliefNest, an open-source simulator designe | True | True | True |
| 2508.18722 | VistaWise | This paper introduces VistaWise, a cost-effective agent framework that | True | True | True |
| 2505.24157 | REPOA | In this section, we introduce REPOA, which consists of three main comp | True | True | True |
| 2606.12852 | WISE | To address this, we propose WISE (Which-Why Informed Semantic Explorer | True | True | True |
| 2405.15414 | Luban | In this work, we propose Luban, an agent capable of open-ended creativ | True | True | True |
| 2507.03293 | LTLCrit | We propose LTLCrit, a novel Linear Temporal Logic-based Critic, which  | True | True | True |
| 2601.05215 | MineNPC-Task | We present MineNPC-Task, a user-authored benchmark and evaluation harn | True | True | True |
| 2305.16291 | Voyager | We introduce Voyager, the first LLM-powered embodied lifelong learning | True | True | True |
| 2403.08282 | HAS | ∙\bullet We introduce HAS, a hierarchical structure for multi-agent na | True | True | True |
| 2608.22055 | GenCoord | We introduce GenCoord, which turns the task consequence of such privat | True | True | True |
| 2411.12977 | MindForge | We propose MindForge, a generative-agent framework for cultural lifelo | True | True | True |
| 2411.06736 | MrSteve | To address this, we introduce MrSteve (Memory Recall Steve), a novel l | True | True | True |
| 2501.19318 | MINDSTORES | We introduce MINDSTORES, an experience-augmented planning framework th | True | True | True |

> 32 个名字逐条看过，全部是该篇自己的方法/系统名（`AdaIR`、`SSGformer`、`LLaRS`、`DAR-Net`、
> `Voyager`、`WISE`、`MINDSTORES` 一类）。`MineCollab`（"an example of a benchmark"）边界模糊——
> 它是该文的产物，但严格说是 benchmark 不是 method；按 §4.1 的「一篇一个 name」收下，
> 已进已知限制第 15 条的口径。

## 4b. 行级 L1 覆盖（设计 §10.3，与按篇分开报）

分母 = 该篇全部定量行中，句子点名 self（`SELF_REFERENCE`）或点名具名第三方方法的行；
分子 = 其中 `method` 非空且等于该篇解析名字的行。**不宣称精度**（`architect.md:144`：
476 条 self 里 425 条是推断）。

实跑：`quantitative rows=170 method_filled=100 equals_resolved_name=36 placeholder=8 third_party=56`

即 170 行里 100 行有 `method`；其中 36 行等于该篇解析名字、8 行仍是占位 `proposed method`
（该篇没有解析出名字）、56 行是第三方方法名（`Restormer` 一类，也含 `Liquid-Mamba`、
`CEA-IR-S` 这种片段）。行级数字低于按篇覆盖，是因为按篇只要有一处命名句就记 covered——
**这两个口径必须并列报，不能只报按篇**。

## 5. 已知未解决

- **L3 仍为 0**：S3 未实施。`missing_layers` 已逐篇落库，S3 落地后这一格才会动。
- **L1 召回受命名句式限制**：名字只写在图注/标题的论文抽不到（`2310.18293` 的 `UtilityIR`）。
- **L1/L2 在 agent_in_mc 上的残差**：`lexicon.py` 仍只有图像复原词表，S2 只铺了 `patterns.py`
  的领域组结构（`DOMAINS` 为空）；扩 MC 词表是独立立项（设计 §12.1）。
- **`method` 会收到第三方名片段**（`Liquid-Mamba`）：它是「谓词前最近的具名 token」，
  不做名字完整性判断。§4b 已声明不宣称精度。
- **一篇多方法**：只收一个 `name`，其余进 `aliases` 并记 `METHOD_MULTI_NAME`；
  同 tier 同 chunk 并列时 `name` 留空并记 `METHOD_NAME_AMBIGUOUS`。归属问题没有解决。
- **本报告的数字依赖本机 `.holdout_cache`**：缓存是 gitignored，换机器需先重下
  （`docs/evaluation/holdout-ids-*.txt` 两份清单），否则复现不出这些数字。
