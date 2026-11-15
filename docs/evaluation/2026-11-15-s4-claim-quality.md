# S4 实测：主张质量（2026-11-15）

> before 来源 A：`docs/evaluation/2026-11-13-p5-contradiction.md` §3（历史快照，原数字未改）
> before 来源 B：**S3 快照工作树**（`git worktree add <tmp>/s3 827a110`，`PYTHONPATH=<tmp>/s3/src`
> 强制使用快照源码，`.holdout_cache` 复制自本机）——这是与 S4 同口径的真 before
> after 命令：`python scripts/holdout_claim_quality.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt`
> 与 `python scripts/holdout_contradiction_quality.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt`

## 1. before / after

| 指标 | 历史报告（2026-11-13） | S3 快照（真 before） | S4 after | 差值（对真 before） |
|---|---|---|---|---|
| 论文 / 块 / 证据 | 20 / 13871 / 4814 | 20 / 13871 / 4814 | 20 / 13871 / 4814 | 0 |
| 主张 / SUPPORTED | 1173 / 1075 | 1173 / 1075 | 1173 / 1075 | **0 / 0** |
| 有 dataset / 有 metric | 195 / 153 | 195 / 153 | 195 / 153 | 0 |
| 满足合并门槛 | 73（7%） | 73 | 73 | 0 |
| 方向 UP / None / DOWN / LEVEL | 372 / 685 / 16 / 2 | 371 / 684 / 17 / 3 | 371 / 684 / 17 / 3 | **0** |
| 候选对 / 判定数 | 1049 / 30 | 1049 / 30 | 1049 / 30 | 0 |
| `TRUE_CONTRADICTION` | 0 | 0 | 0 | **0** |

**关于方向分布**：历史报告写 `372/685/16/2`，S3 快照已经是 `371/684/17/3`。
这 1–2 条的漂移**发生在 S4 之前**，不是本阶段造成的；两组数字都保留，不覆盖旧报告。

## 2. 变化归因（设计 §8.4）

S4 同时做了两件方向相反的事，逐项分开记：

1. **新增 `scale=` / `protocol=`**：40 篇留出集里 146 句命中（scale 89 / protocol 57），
   20 篇留出集里有 **455 条 claim 的第 6 段带上新 kind**（before 为 0）。
   `identity_key` 第 6 段因此变化，但这些句子本来就没有可合并的同键对象——
   **主张总数 1173 → 1173、合并门槛 73 → 73、候选对 1049 → 1049，全部未变**。
2. **provenance 改为按 kind**：此前被整条覆盖的 `training=` / `backbone=` 按类补齐，
   继承值回到第 6 段。实测同样是 **key 内容变了、主张数没变**：没有新的合并，也没有拆开旧合并。

`identity_key` 唯一数与合并组数：**既有报告没有这两个指标，本轮未新增采集脚本，因此不编造 before**；
本节用「主张总数 / 门槛 / 候选对」三格并列代替，并在已知限制里登记这个缺口。

## 3. 验收

- `identity_key` 仍 7 段：`len(key.split("|")) == 7` 的既有断言全绿。
- `TRUE_CONTRADICTION` 未因新维度增加（0 → 0）。
- 全量测试 `418 passed, 2 skipped / 420 collected`。

## 4. 已知未解决

- 第 6 段变化造成的「按 kind provenance 补回继承值」这一路，**没有单独计数**，只以
  「主张数不变」间接证明。若要逐句归因，需新增采集脚本（独立立项）。
- 历史报告的方向分布与 S3 快照不一致，原因未查（不属四阶段范围），旧数字未改。
