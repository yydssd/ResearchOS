# S4 实测：矛盾质量（2026-11-15）

> before：`docs/evaluation/2026-11-13-p5-contradiction.md` §3/§5（原数字未改）
> + S3 快照工作树同口径实跑（`PYTHONPATH=<tmp>/s3/src`）
> after：`python scripts/holdout_contradiction_quality.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt`

## 1. before / after

| 指标 | S3 真 before | S4 after | 差值 | 解释 |
|---|---|---|---|---|
| 判定数 assessments | 30 | 30 | 0 | 候选对 1049 不变 |
| `SCOPE_DIFFERENCE` | 18 | 18 | 0 | — |
| `COMPLEMENTARY` | 5 | 5 | 0 | — |
| `INSUFFICIENT_EVIDENCE` | 5 | 5 | 0 | 按 kind 的门没有把任何一对降级 |
| `EXPERIMENTAL_INCOMPATIBILITY` | 2 | 2 | 0 | — |
| **`TRUE_CONTRADICTION`** | **0** | **0** | **0** | **设计 §8.4 的硬判据：未因新维度增加** |
| condition provenance（三分类） | 25 / 0 / 5 | 27 / 2 / 1 | +2 / +2 / −4 | 口径变了，见下 |

**provenance 口径必须并列读**：before 是「整条一个 tier」，after 是「每 kind 一个 tier 的并集」
（`either_side_first_mention` / `heading_involved` / `sentence_or_unspecified`）。
一条 claim 现在可以同时贡献多个 tier，所以 25/0/5 → 27/2/1 **不是行为变化**，主要是统计口径变化；
旧脚本在只改源码未改脚本时曾报 `sentence_or_unspecified 30`（25 条继承全部丢失），
Task 6 把统计改成按 kind 聚合后才恢复可比。两口径的归一规则未定义，不换算。

## 2. 逐对归因

30 条判定逐格不变；新门只对「OPPOSITE 且两侧共有 kind 的 tier 全部确认」放行，
本语料里没有任何一对满足额外放行或额外降级条件，因此分布逐格相同。

夹具 `tests/fixtures/contradiction/pairs.json` 的 26 对：
脚本按第 6 段 kind 把全局 tier 展开成每 kind 一个 flag 后，`acc=100.0%`、
`TRUE_CONTRADICTION` precision/recall 100%，`test_evaluate_contradiction.py` 8 passed。
展开前（源码已改、脚本未改）是 `acc=81.0%`、4 对误判——那 4 对是**脚本没跟上**，不是判定退化。

## 3. 已知未解决

- 40 篇口径（含 Agent in MC）的矛盾判定本轮未跑；设计 §8.4 的
  「`TRUE_CONTRADICTION` 不增加」只在图像复原 20 篇上验证。
- 存量库旧 `conditions_from=` 标记不迁移，旧 run 的矛盾数不能与新 run 直接比
  （已知限制 19）。
