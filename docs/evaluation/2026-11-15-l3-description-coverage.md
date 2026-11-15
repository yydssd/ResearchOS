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
