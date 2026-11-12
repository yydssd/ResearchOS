# P4 — Claim Synthesis · 设计规格

- **日期**：2026-11-12（W2 / Day 4）
- **对应计划**：§16（Phase 4 — Claim Synthesis），受 §2.2 可追溯、§25 失败模型约束
- **前置状态**：P0 ✅、P1 ✅、P2 ✅、P3 ✅（106 tests）
- **范围**：只做主张层。不做 P5 矛盾判定、P6 memo 结构重排、P7 反证搜索。

---

## 1. 目标

让「主张」成为**范围明确、可去重、可判支撑**的对象，而不是证据句的别名。

```text
Evidence（带精确位置 + 定量事实）
   → SectionContext（task / dataset 从标题与段首继承）
   → ClaimIdentity（subject · task · dataset · metric · direction · conditions · value_bucket）
   → Claim（identity_key + scope + conditions + status + confidence）
   → ClaimEvidenceRelation（SUPPORTS / 后续 CONTRADICTS）
```

计划的硬约束（§16）：**不得因为措辞相似就合并**；`A improves Rain100H PSNR` 与
`A improves SIDD PSNR` 必须保持两条，不得退化为 `A improves image restoration`。

## 2. 扩测发现（设计由这些实测数字驱动）

**样本**：6 篇 arXiv 摘要 + 4 篇 ar5iv 全文（BSRGAN / Restormer / NAFNet / SwinIR /
MIRNet / AutoDIR），合计 2150 块、1363 条证据、215 条非推测类主张。

| 漏斗层 | 数量 |
|---|---|
| 非推测类主张 | 215 |
| 有 subject | 93 |
| + 有 dataset | 12 |
| + 有 direction | 4 |
| + 有 metric（完整七维） | **0** |

跨源合并模拟：可凑齐门槛的键 9 个，**跨文档命中 0 组**。唯一一组"合并"是同一篇论文
abs 页与全文页的重复句，且主语被错抽为 `sota`。

| 观察 | 数字 | 对设计的含义 |
|---|---|---|
| 引用 / 图表标题 / LaTeX 重复占主张的比例 | 15%（5.2 / 6.2 / 3.3） | 噪声不是主因，无需先大改主张检测器 |
| 带 `dB`/`%`/`×` 的主张占比 | 12%（26/215） | 身份键是为少数句子服务的，不能拿 88% 的非定量句去凑 |
| 这 24 条全文数值句里 task 可从句子抽到 | 17% | task 必须来自章节标题 |
| 同上，继承标题后 | 50% | 继承有效，但不到一半 |
| 同上，task + dataset + metric 同时具备 | 12%（3/24） | 完整七维在真实语料上的天花板 |
| 带数值的证据中同时写了指标词 | 22%（11/50） | 78% 的数值句没有指标词，`value_bucket` 会大面积为空 |
| 数值主张落在名为 "Results/Experiments" 的章节 | 8%（2/24） | 章节名是**任务名**（`Classical image SR.`），不是 "Results" |

**结论**：把 identity 建在单句上不可行；必须允许从块级上下文继承。合并机制可以做，
但真实语料不会触发，其验收只能来自构造夹具。

## 3. 设计决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | identity 的 task / dataset 支持**块级继承**（章节标题 + 段首句），句子命中优先 | 扩测：句子级完整率 0%，继承后 task 覆盖 17%→50% |
| D2 | subject 用**谓词前缀**抽取，第三方标识存在时不默认 SELF | 全句搜索会把宾语当主语（`the gating mechanism enables the model` → 误判为方法本身） |
| D3 | dataset / metric 是**集合**而非单值 | 多指标并列（`PSNR by 0.42 dB and SSIM by 0.013`）是结果段最典型句式；"多个就置 None"会丢掉整个维度 |
| D4 | identity 增加 `value_bucket`；数值不一致**不合并** | 合并同键异值的主张会消灭 P5 需要的矛盾信号 |
| D5 | 合并门槛 = `subject` 非空 且 `dataset` 非空 且 `direction` 非空，再要求各维度逐一相等 | 计划 §16 "不得因措辞相似而合并"的可执行版本：只在范围完全确定时合并 |
| D6 | 定量抽取补 `delta` 与无指标词单位；ar5iv 数学重复在 loader 层净化 | 78% 的数值句无指标词；`96%96\%` 会让抽取读到错值 |
| D7 | "数值无法结构化"是**质量标记**，不是 unsupported | 证据在句子里，缺的是结构；判成 unsupported 等于说谎 |

## 4. 块级 scope 继承

`SectionContext` 由 `chunks` 序列推导，逐块给出 `(task, inherited_datasets)`：

- **task**：章节标题命中任务词表——`SR`/`super-resolution`、`denoising`、`deblurring`、
  `deraining`、`inpainting`、`restoration`、`JPEG compression artifact reduction`。
  句子自身命中优先于标题。
- **dataset**：句子命中优先；否则取**同 section 内首个命中 dataset 词表的句子**作为该节上下文。
  这是刻意做的最小回指，只覆盖"段首点名、后句省略"这一种最常见情况。
- **subject**：谓词前缀内先找 SELF 短语，再找专名（内部大写 / 全大写≥2 / 含数字 / 首字母大写且长度≥6，
  且不在停用词与 dataset/metric/task 词表内）。两者皆无时，**仅当**该块已继承到 task 或 dataset
  且句中不含第三方标识（`previous`、`existing`、`prior`、`baseline`、`compared methods`、
  `state-of-the-art`、`SOTA`）时，默认 `SELF@<source_version_id>`。
- SELF 永远带 `@sv_id`：两篇论文各自的 "our method" 是不同方法，不得合并。

## 5. identity 七维

| 维度 | 取值 | 缺失处置 |
|---|---|---|
| `subject` | 专名（小写归一）或 `self@sv_id` | None |
| `task` | 任务词表项 | None |
| `dataset` | dataset 词表项的集合 | None |
| `metric` | `PSNR/SSIM/LPIPS/FID/MAE/MSE` 集合 | None |
| `direction` | `UP`/`DOWN`/`LEVEL` | None |
| `conditions` | `backbone=…`、`setting=synthetic` 或 `setting=real`、`granularity=video` | `[]` |
| `value_bucket` | 每个指标一个桶：PSNR 1 位小数、SSIM 3 位、百分比取整；无指标词但有单位时记 `dB:<值>` / `%:<值>` | 无 |

`identity_key` = `subject|task|ds1,ds2|m1,m2|direction|cond;cond|bucket`，全小写。

## 6. 合并规则

两条同时满足才合并：

1. `subject`、`dataset`、`direction` 三者均非空；
2. 六个可比维度逐一相等——`subject`（SELF 须同一 `sv_id`）、`task`、`dataset` 集合、
   `metric` 集合、`direction`、`conditions`、`value_bucket`（按桶相等；一侧有另一侧无则**不合并**）。

合并结果保留首条 `text` 为代表，各来源证据以多条 `SUPPORTS` 挂在同一 claim 上，
`rationale` 记录"merged by identity key: …"以便审计。

不合并的组不进入任何"归一化"流程，仅在 memo 的 `# Claims Kept Separate` 段列出
（同 subject 同 metric、dataset 不同），作为"没有过度合并"的显式证据。

## 7. 定量抽取补全（D6）

- **无指标词的值**：`+0.44 dB` / `0.38 dB higher` → 新增 `delta` 字段（`QuantitativeEvidence.delta`），
  `metric=None`、`protocol="dB"`。
- **区间**：`39.29 dB to 39.73 dB` → `comparator_value=39.29`、`value=39.73`（现有规则），
  且不因句首 `+0.44 dB` 而错取。
- **ar5iv 数学重复净化**（`documents/html.py`）：`96%96\%` → `96%`、`10×10\times` → `10×10`、
  `1×11\times 1` → `1×1`。在 `_collapse()` 内做，属块文本归一化，因此偏移仍一致。
- 表格数值仍不抽取（`td` 只作文本收集），留待后续。

## 8. 状态与质量标记（D7）

**语义边界**：`UNSUPPORTED` 在本系统里只表示**没有支撑证据**；"有证据但证据薄弱"用
`confidence=LOW` + 具体 condition 表达。两者不得混用，否则 unsupported 会退化成"置信度"的同义词。

| 通道 | 触发 | 结果 |
|---|---|---|
| (a) 推测 / 未来工作 | `we believe`、`may`、`future work` 等 | `UNSUPPORTED` + `LOW`，无 SUPPORTS 关系 |
| (b) 数值无法结构化 | 句中有 `dB`/`%`/`×` 值但该证据无定量行 | 保持 `SUPPORTED`，confidence `LOW`，condition `quantitative_unstructured` |
| (c) 范围不可判定 | 有数值但 dataset 与 metric 双缺 | 保持 `SUPPORTED`，confidence `LOW`，condition `scope_undetermined` |
| (d) 比较无对照 | 出现 `outperform`/`better than`/`surpass`/`SOTA`，但同句既无定量事实也无 `compared with/to X` | 保持 `SUPPORTED`，confidence `LOW`，condition `comparative_unsubstantiated` |
| — 纯定性主张 | 无数值、无比较 | 不降级 |

(d) 针对的是摘要里最常见的过度断言：`Experimental results demonstrate that SwinIR outperforms
state-of-the-art methods`——这一句里没有任何对照数据，把它记为 MEDIUM 等于替作者背书。

## 9. 编排与呈现

- `HeuristicClaimBuilder.build(evidence, quantitative, chunk_scope)`：先算 `SectionContext`，
  再逐条抽 identity，最后按 `identity_key` 聚组合并。
- supervisor 传入定量事实与 `evidence → chunk/section` 映射。
- memo 的 Finding 增列 `Scope:`、`Conditions:`、`Grounding:`（`structured` / `unstructured` / `none`）；
  新增 `# Claims Kept Separate` 段。
- `inspect-claim` 增 `identity_key`、`grounding`、`scope_context`（哪些字段来自标题继承）。

## 10. 明确不做

- 跨句共指解析（除"段首点名、后句省略"这一种最小回指）。
- LLM 参与归一化或合并判定。
- 指标换算（dB 与 % 不互转）、跨数据集数值比较。
- 用真实语料验收"跨源合并"——它在真实语料上不触发，不拿它当验收证据。

## 11. 验收

1. **不合并**：`A improves Rain100H PSNR` 与 `A improves SIDD PSNR` → 两条 claim，`identity_key` 不同。
2. **合并**：两篇夹具论文同 identity 同值 → 一条 claim、两条 SUPPORTS；同 identity 异值 → 两条。
3. **SELF 绑定**：两篇论文各自的 "our method improves PSNR by 0.42 dB on Rain100H" → 不合并。
4. **块级继承**：`Classical image SR.` 标题下的数值句 → `task=super-resolution`；
   段首点名 `SIDD` 的后继句 → `dataset={SIDD}`。
5. **多指标**：`PSNR by 0.42 dB and SSIM by 0.013` → `metric={PSNR, SSIM}`，不是 None。
6. **无指标词数值**：`+0.44 dB … on SIDD` → `delta=0.44`、`dataset=SIDD`、`metric=None`。
7. **数学重复净化**：`96%96\%` → `96%`，且净化后偏移仍 `chunk.text[a:b] == evidence.text`。
8. **状态标记**：fixture 6 条主张 → **4 SUPPORTED / 2 UNSUPPORTED**：
   `The gating mechanism enables…`（定性，MEDIUM）、Rain100H 与 SIDD（structured，MEDIUM）、
   `Rain100L … 0.11 dB`（SUPPORTED 但 LOW + `quantitative_unstructured`）、
   `We believe…` 与 `Future work…`（UNSUPPORTED）。即：只有真正的推测句才降为 unsupported。
   另加一例 `SwinIR outperforms state-of-the-art methods`（无对照数据）→ SUPPORTED / LOW /
   `comparative_unsubstantiated`。
9. **真实语料回归**：4 篇 ar5iv 全文跑通不报错；identity 完整率从 0% 提升到 ≥10%；
   跨文档合并触发 0 次（记录为已知限制，不作为失败）。
10. `pytest` 全绿，现有 106 条测试不回归。

## 12. 已知限制

1. 真实语料上跨源合并几乎不触发，机制的价值需要同方法同数据集被他人复现才显现。
2. 78% 的数值句没有指标词，只能靠 `delta` + 单位记录，无法与有指标词的记录直接比较。
3. 表格与图注中的数值不抽取，结论段的汇总表因此进不了定量事实。
4. `SELF` 默认依赖第三方标识黑名单，漏判会把前人方法的结果算到本文方法头上（(b)/(c) 通道会降置信，但不会纠正归属）。
5. 段落级回指只覆盖"段首点名"这一种，代词与别名指代仍然抽不到。
