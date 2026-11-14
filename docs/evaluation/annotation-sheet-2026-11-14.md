# 人工标注表说明（P5 fixtures，2026-11-14）

计划 §17 要求 **at least 20 manually curated contradiction fixtures**。现有 26 条
fixtures 的标签是 agent 按 spec 规则推导的，不构成「人工整理」。这张表就是为了补上那一环。

## 怎么做

1. 用 Excel / WPS 打开 `annotation-sheet-2026-11-14.csv`（UTF-8 BOM，中文不会乱码）。
2. 逐行读 `a_text` 与 `b_text`（两条主张原文），结合 `a_key` / `b_key` 里的范围信息，
   在 `your_label` 填一个标签，在 `your_reason` 写一句理由（为什么不是相邻的那一档）。
3. 26 行全部填完后把文件放回原位，告诉我，我来算一致率。

**不要看** `tests/fixtures/contradiction/pairs.json` 和 `ANNOTATION.md`——那里面有机器标签，
看了就不再是独立标注。

## 六个合法标签（只给定义，不给判定顺序）

| 标签 | 含义 |
|---|---|
| `TRUE_CONTRADICTION` | 两条主张针对**同一对象、同一范围**得出**相反**结论（一条说变好，一条说没改善或变差） |
| `SCOPE_DIFFERENCE` | 结论不同，但范围**确实不同**（数据集、实验条件等），差异可以由此解释 |
| `EXPERIMENTAL_INCOMPATIBILITY` | 方向一致但两次实验**不能直接对照**（指标不可比，或同向却给出不同数值） |
| `COMPLEMENTARY` | 范围不同但方向一致：各自在自己的条件下成立，互相补充 |
| `INSUFFICIENT_EVIDENCE` | 信息不足以做出以上任一判断（缺方向、缺范围、或设置是否相同无从确认） |
| `SKIP` | 这一对**根本不该进入比较**（不是同一对象，或缺必要字段导致无法配对） |

判定顺序、条件来源的处理方式都不在表里——按你自己的判断选最贴切的一档。

## 表格字段

| 列 | 含义 |
|---|---|
| `id` | p01–p26 |
| `source` | `real` = 原文逐字取自 `.holdout_cache/` 里的论文；`constructed` = 为覆盖某类而构造 |
| `from` | 真实条目的 arXiv id，可据此回查原文（`b_from` 存在时 p17 的 B 侧来自另一篇） |
| `a_text` / `b_text` | 两条主张原文 |
| `a_key` / `b_key` | `subject｜task｜dataset｜metric｜direction｜conditions｜value_bucket`，空段表示该字段没抽到 |
| `a_conditions_from` / `b_conditions_from` | 实验条件是从哪里来的：`sentence` 句内明写 / `heading` 节标题 / `section-first-mention` 本节首次提及 / 空 未记录 |
| `your_label` | 你填的标签（见上表六个值） |
| `your_reason` | 你的理由，一句话 |

`direction` 的四个取值：`UP` 声称变好、`DOWN` 声称变差、`LEVEL` 明确说没有改善、空 只报了数值没声称方向。

## 填完之后

我会做三件事，都不会改你已经填的内容：

1. 逐条比对 `your_label` 与机器标签，报一致率（这才是计划 §17 要的 accuracy）。
2. 分歧逐条列出来，标为「机器错」或「标注错」或「规则未定义」，由你裁决后写进
   `ANNOTATION.md` 的 Disagreements 段。
3. 把人工标签作为 ground truth 写回 `pairs.json` 的 `expected`，并把 `ANNOTATION.md` 的
   pass log 从 `not performed` 改成有真实标注者的记录——同时保留原有机器标签，
   方便以后看规则漂移。

没有这张表，`TRUE_CONTRADICTION` 的 precision/recall 只能叫自洽性；有了它，才叫准确率。
