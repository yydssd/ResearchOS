# 方法获取能力度量（2026-11-14）

> 复现：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`
> 标注：`tests/fixtures/method_acquisition/ANNOTATION.md`（owner-derived，非独立、非盲标）
> 本报告的 `C` 与项目既有 `coverage`（judged/total_before_cap）**不是同一指标、分母不同，两者无关**。

## 1. 语料与口径

40 篇（图像复原 20 / Agent in MC 20），4 层 × 2 领域 = 8 组。
`A = present/20`；`C = covered/present`，分母逐格不同，**不可跨层 / 跨领域比较**；
`present < 5` 的格子不作趋势解读；`present=0` 记 `N/A`。
标注夹具：159 present / 0 absent / 1 ambiguous（`2404.12495`/L4）。

## 2. 结果

| 领域 | 层 | present | A | covered | C | covered/20 |
|---|---|---|---|---|---|---|
| agent_in_mc | L1 | 20 | 20/20 | 0 | 0/20 | 0/20 |
| agent_in_mc | L2 | 20 | 20/20 | 10 | 10/20 | 10/20 |
| agent_in_mc | L3 | 20 | 20/20 | 0 | 0/20 | 0/20 |
| agent_in_mc | L4 | 20 | 20/20 | 14 | 14/20 | 14/20 |
| image_restoration | L1 | 20 | 20/20 | 0 | 0/20 | 0/20 |
| image_restoration | L2 | 20 | 20/20 | 19 | 19/20 | 19/20 |
| image_restoration | L3 | 20 | 20/20 | 0 | 0/20 | 0/20 |
| image_restoration | L4 | 19 | 19/20 | 11 | 11/19 | 11/20 |

## 3. 缺口分布

| 缺口成因 | 计数 |
|---|---|
| agent_in_mc|L1|无结构化字段 | 20 |
| agent_in_mc|L2|词表未覆盖 | 10 |
| agent_in_mc|L3|无结构化字段 | 20 |
| agent_in_mc|L4|无结构化字段 | 6 |
| image_restoration|L1|无结构化字段 | 20 |
| image_restoration|L2|词表未覆盖 | 1 |
| image_restoration|L3|无结构化字段 | 20 |
| image_restoration|L4|无结构化字段 | 8 |

proxy（claim subject，不等于 §15 的 method）：{'agent_in_mc': 669, 'image_restoration': 566, 'total': 1235}
ambiguous（不计入任何比率）：{'image_restoration|L4': 1, 'total': 1}

## 4. 读法边界

- L3 的 0 来自**结构性缺失**（无对应字段），不是抽取错误。
- 本报告只量可获取性与覆盖率，不建 gold label，不报任何质量结论。
- `proxy`（claim subject）单列，不等于 §15 要求的 `QuantitativeEvidence.method`。
- `ambiguous` 单列，不计入任何比率。
- 真实夹具中不存在 `present=0` 的格子，因此 `present=0 → N/A` 分支**只由合成夹具验证**，
  不在本次真实语料中触发。
- `A` 是否恒 100%、`C` 分母是否恒 20，以 §2 表格为准，不得另行概括。

## 5. 待办登记

- 既有 `coverage 100%` 的口径问题（scope skip 计入 `judged`）：独立立项。
- §2.5 未逐项登记 deviation ADR：独立立项。
- 第二轮独立标注：需独立标注者。
- `load_labels` 缺 HTML 容错、非 present 格 evidence 未校验：非阻塞健壮性项。
- 真实入口调用 `load_labels(..., require_full_corpus=True)` 是脚本实施细化（计划片段未传该参数）。
