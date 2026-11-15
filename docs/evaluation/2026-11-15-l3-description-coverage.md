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
不宣称描述正确率（已知限制 18）。也没有做人工抽查——本轮没有第二人复核，标注仍是 owner-derived。

## 6. 复现

```bash
RESEARCHOS_LLM_API_KEY=... RESEARCHOS_LLM_MODEL=deepseek-flash \
RESEARCHOS_LLM_BASE_URL=https://api.deepseek.com/v1 \
python scripts/record_method_descriptions.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt
python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json --describer recorded
```

40 份录制在 `tests/fixtures/method_descriptions/`（173 KB，已入库）。重放不调模型、不花预算，
所以上面的数字任何人可复核。录制键是「去掉 chunk id 的 prompt 摘要」，换一次运行仍能命中。
