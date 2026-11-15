# L3 方法描述覆盖（2026-11-15，第一次真实测量）

> before：`docs/evaluation/2026-11-15-method-acquisition-s2.md` §1/§6（L3 `0/20`、原因 `LLM 未启用`）
> 语料：同一 40 篇（图像复原 20 / Agent in MC 20），`--labels tests/fixtures/method_acquisition/labels.json`
> 模型：`deepseek-flash`（OpenAI 兼容端点），每次 1 次调用，共 **42 次**（40 + 2 次重录），未超 80 预算

## 1. 三次测量，同一格

| 阶段 | 图像复原 L3 | Agent in MC L3 | 说明 |
|---|---|---|---|
| S3 收官（无 describer） | 0/20 | 0/20 | 原因 `LLM 未启用`，口径正确 |
| 录制完成（prompt v1） | **17/20** | **20/20** | 3 篇未覆盖，原因见 §3 |
| prompt 收紧后（prompt v2） | **19/20** | **20/20** | 两篇补回，剩 1 篇是模型空答复 |

`gaps` 合计：48 → **9**（L1 `词表未覆盖` 4+4、L3 `LLM 空答复` 1）。L3 图像复原那格的分母是 20，覆盖 19。

## 2. 四层全表（同一 40 篇、160 格）

| 层 | 图像复原 | Agent in MC |
|---|---|---|
| L1 方法身份 | 16/20 | 16/20 |
| L2 方法构成 | 20/20 | 20/20 |
| **L3 方法描述** | **19/20** | **20/20** |
| L4 可复现设置 | 19/19 | 20/20 |

**这是第一次四层全部有数字。** 但注意 `C` 的分母逐格不同（§21 的读法第一条）：L4 图像复原 `present` 只有 19，不要和 20 比。

## 3. 未覆盖的 3 篇（逐篇）

| 论文 | 首测 | 原因 | 处理 |
|---|---|---|---|
| `2504.14249` | 全篇拒绝 | 模型返回 3 条要点，**`chunk_id` 全为空** → schema 防线按设计整篇拒绝 | 收紧 prompt（`chunk_id` 必填、必须逐字取自 prompt 里的 id）后重录，通过 |
| `2609.16578` | 全篇拒绝 | 同上（9 条要点、无 `chunk_id`） | 同上，重录后通过 |
| `2506.22736` | 空答复 | 模型返回 `{"points": []}` | **未处理**：这是模型的判断，不是我们的缺陷；如实记为 `LLM 空答复` |

这两篇的失败**不是防线过严**：三条防线各自拦下的东西不同，`chunk_id` 为空时「引文真的在那一块里」根本无法验证，收下等于把未验证的陈述写进方法档案。

## 4. 一处标签修正（设计 §13 D32）

首测后这篇空答复被记成 `LLM 未启用`——**事实错误**：describer 装配了、也被调用了。
新增原因 `LLM 空答复`（模型被问过、什么都没答），与「没装配 describer」区分开。
这与 S4 的 D15（把「模式没覆盖」误记成「没有落点」）是同一类错误的另一头。

## 5. 这份数字能说明什么、不能说明什么

能说明：L3 的通路（协议 → 四道防线 → 落库 → 录制回放）在真实模型上跑通，40 篇里 39 篇产出了
**可定位**的要点；每条要点都能指回原文某一句，且陈述与引文共享至少两个实词。

**不能说明**：要点说得对不对。四道防线是形式判据（`quote` 能定位、`statement` 有词重叠），
不宣称描述正确率（已知限制 18）。§7 给了一个**盲评**的初步数字，但那是 LLM judge，不是人工标注。

## 6. 复现

```bash
RESEARCHOS_LLM_API_KEY=... RESEARCHOS_LLM_MODEL=deepseek-flash \
RESEARCHOS_LLM_BASE_URL=https://api.deepseek.com/v1 \
python scripts/record_method_descriptions.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt
python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json --describer recorded
```

40 份录制在 `tests/fixtures/method_descriptions/`（173 KB，已入库）。重放不调模型、不花预算，
所以上面的数字任何人可复核。录制键是「去掉 chunk id 的 prompt 摘要」，换一次运行仍能命中。

## 7. 陈述是否被引文支持（20 条盲评）

四道防线只保证「引文能定位」，不保证「陈述说得对」。这一节第一次给后者一个数字。

> ⚠️ 本节的 `15/5/0` **不能**当作描述质量的估计：§10 的人工锚点显示它与人工判断的一致率只有 50%（kappa 0.20）。

**抽样**：`random.seed(20261115)`，从 290 条可定位要点里抽 20 条，**每篇最多 1 条**、两域各 10 条
（避免集中在少数论文上）。样本与原始响应：`docs/evaluation/2026-11-15-l3-sample.json`。

**判断者**：一个独立子代理，规则是「只看 `quote`，不读论文、不看产出模型、不评价文笔」，
判据四档：`supported`（陈述里每个具体内容都能在引文里找到依据）/ `partial`（主干成立但补入了
引文没有的具体信息，或把弱表述强化）/ `unsupported` / `unclear`。判定：`2026-11-15-l3-judgement.json`。

| verdict | 条数 | 比例 |
|---|---|---|
| `supported` | 15 | 75% |
| `partial` | 5 | 25% |
| `unsupported` | 0 | 0% |
| `unclear` | 0 | 0% |

**5 条 `partial` 的失败方式高度同质——都是「复述主干 + 补全」**：

| id | 补了什么 | 引文实际说的 |
|---|---|---|
| p01 | 补「spectral/spatial 依赖」「非全局重建」 | 只说「把 HSI 复原重新表述为自回归生成问题」 |
| p03 | 把 `deformable patch embedding` 泛化成 `patch embedding` | 限定 deformable，陈述把特例说成通例 |
| p04 | 补主语「a loss」 | 引文是无主语半句 |
| p15 | 补主语「the critic」 | 同上 |
| p16 | 补结论「making the system simpler to operate」 | 只有「By distilling capabilities into a single model」 |

我自己复核了 p01 / p03 / p16 / p09：前三条与判断一致；p09 判 `supported` 略宽（`Singular Value
Decomposition` 被写成 `matrix decomposition`，是上位词降级），可接受但不该当成毫无损失。

**这个数字是什么、不是什么**：

- 是：这 20 条里 75% 的陈述**逐字可核对**，25% 需要读者回去看原文才能确认补全部分。
- **不是**「描述准确率」：判断者与被评对象都是模型，这是 LLM-as-judge，有已知的宽容倾向
  （本轮 p09 就是一例），**不能替代人工标注**，也没有做标注者间一致性。
- 是：一个**可行动的缺陷**——失败不在「引文不可定位」，而在「改写时补全」。下一轮可以试的
  最小改动：prompt 里禁止引入引文之外的主语/结论，或加一条自动检查（陈述的实词必须都能在
  引文里找到），后者能测、能回滚。

## 8. 自动检查的负结果（试过，不采用）

上一节说「加一条自动检查：陈述的实词必须都能在引文里找到」，听起来划算。先按规矩在 20 条已判样本上
标定，再决定是否上全量。**结论：不采用。**

规则：把陈述与引文都取实词集合（长度 > 2、去停用词），取 `陈述实词 - 引文实词` 的个数。

| 阈值 | 能抓到几条 `partial` | 误伤几条 `supported` | 误伤率 |
|---|---|---|---|
| ≥1 | 4 / 5 | 13 / 15 | 87% |
| ≥2 | 4 / 5 | 12 / 15 | 80% |
| ≥3 | 3 / 5 | 5 / 15 | **33%** |

我给自己定的门槛是「误伤超过一成就不做」，最严的一档也差了三倍。

**为什么必然失败**：忠实改写会换词。p02 被判 `supported`，但它的陈述里有 7 个引文没有的实词
（`approach` / `single` / `region` / …）——那是同义改写，不是补全。而 p03 被判 `partial`
的理由是**丢掉了** `deformable` 这个限定词，规则数「多出来的词」，结构上就看不见「少掉的词」。
换词、缩合、泛化三种情况在词面上同形，任何词面规则都分不开。

**因此这一步只能靠语义判断**，也就是 §7 那种盲评。要让它可重复，唯一的路是把判断放进流水线：

| 方案 | 成本 | 代价 |
|---|---|---|
| 每篇多一次判别调用（把 3–5 条要点一次判完） | 40 篇 +40 次调用（预算 80，仍够，但普通 run 会翻倍） | 判官也是模型，存在宽容倾向；需要与 §7 同样声明「非人工」 |
| 只在审计时判（不进竖切） | 只在度量时花 40 次 | 日常 run 不产出这个数字；改动不即时可见 |

我倾向第二种：**这是度量指标，不是产品行为**，放进日常 run 会为每篇论文多花一次调用，而用户看不到
收益。要落地需要单独一轮（判别器 + 与人工一致性估计），本轮不做。

## 9. 人工一致性（表已备好，待填）

§7 是模型判模型。要说明它离真相多远，必须有一个独立锚点，哪怕只有 10 条。

- **表**：`docs/evaluation/2026-11-16-l3-annotation.json`，10 条，
  **分层抽样**：5 条模型判 `partial` + 5 条随机 `supported`（`seed 20261116`，顺序打乱）。
  分层是必要的：若按 base rate 随机抽 10，`partial` 只会有 2–3 条，一致率会被「全判 supported」虚高。
- **盲**：表里只有 `statement` / `quote` / `aspect` / 一个回连用的 `source_id`，**没有模型判定**；
  表头写明不要去看 `2026-11-15-l3-judgement.json`。
- **评分**：`python scripts/score_l3_annotation.py`
  - 报**分层**原始一致率（模型判 `partial` 的那 5 条、判 `supported` 的那 5 条分开），
    不报池化数字——样本是设计出来的，池化没有意义；
  - 另报二值 Cohen's kappa（`supported` vs 其余），并注明 **n=10 时 kappa 不稳，只能当下限检查**；
  - 未填或填了四个词之外的值直接报错并列出 id，**不把空行算成不同意**。

评分脚本有 5 条用例（完美一致、一条不一致、未填、未知 source_id、机遇一致时 kappa=0）。

**填完之前，本报告不给出任何「LLM judge 与人类一致」的结论。** 现在的 `15/5/0` 只是模型的自评，
而 p09 那一条已经显示出宽容倾向。

## 10. 人工锚点结果：一致率 50%，分歧集中在两条规则上

10 条分层盲评已填（`2026-11-16-l3-annotation.json`），`scripts/score_l3_annotation.py` 的输出：

```
n = 10   raw agreement = 50.0%   kappa(binary) = 0.200
by stratum:  model=partial 2/5 = 40%   model=supported 3/5 = 60%
```

| id | 人工 | 模型 | 一致 | 分歧点 |
|---|---|---|---|---|
| a01 | partial | supported | ✗ | 模型放过了 `Singular Value Decomposition` → `matrix decomposition` 的上位词替换 |
| a02 | supported | supported | ✓ | |
| a03 | supported | partial | ✗ | 引文是无主语片段，陈述补了 `The critic` |
| a04 | supported | partial | ✗ | 同上，补了 `A loss` |
| a05 | supported | supported | ✓ | |
| a06 | partial | partial | ✓ | `deformable` 被丢掉 |
| a07 | partial | partial | ✓ | |
| a08 | unsupported | partial | ✗ | 陈述补了「spectral/spatial 依赖」「非全局重建」 |
| a09 | supported | supported | ✓ | |
| a10 | partial | supported | ✗ | `omnidirectional token shift mechanism` 被压成 `shift mechanism` |

### 这不是「模型不可靠」，是两条规则没定死

把 5 条分歧逐条看，它们**不是随机分布的**，全部落在两个问题上：

1. **片段补主语算不算「添加内容」？** a03 的引文 `analyze failed or suboptimal trajectories and generate new
   temporal logic rules…` 没有主语，陈述写成「The critic inspects…」。模型判「补了主语 → partial」，
   人工判「主语是片段自带的 → supported」。a04 完全同形。**两条分歧全部来自这条规则未定义。**
2. **换成上位词算不算失真？** a01（SVD → matrix decomposition）、a10（omnidirectional token shift →
   shift）都是把具体术语换成更宽的说法。模型放过，人工判 partial。

方向也是双向的：模型在 a01/a10 更宽，在 a03/a04 更严，在 a08 更宽。所以**「LLM judge 偏宽容」这个假设不成立**——§7 里我根据 p09 一条推断出的倾向，在 10 条上没有得到支持。

### 结论（写给自己和下一个人的）

- **`15/5/0` 不是质量估计**，是两个模型之间的一致性水平；与一个人类读者的一致率是 50%、kappa 0.20（n=10，置信区间很宽，但 0.2 已经低到不能当代理指标）。
- **不要因为 kappa 低就下「模型判不了」的结论**：5 条分歧全部可由两条规则解释，说明问题在rubric，不在能力。n=10 也分不清这两种解释——这一点必须承认，不能假装分清了。
- **下一步最小改动**：把 rubric 钉成两条明文规则（片段补主语**不算**添加；上位词替换**算**丢失），
  二值化（`supported` / `needs-review`），再抽 20 条、两个标注者各自独立填——那时才谈得上一致率。
  在此之前，L3 的可报告指标只有**覆盖率**（`19/20` / `20/20`），不是支持率。
