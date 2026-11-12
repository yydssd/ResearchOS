# P3 — Evidence Quality · 设计规格

- **日期**：2026-11-12（W2 / Day 3）
- **对应计划**：§15（Phase 3 — Evidence Quality），受 §2.2 可追溯、§25 失败模型约束
- **前置状态**：P0 ✅、P1 ✅、P2 ✅（83 tests）
- **范围**：只做证据质量层。不做 P4 主张归一化/范围区分，不做 P5 矛盾判定。

---

## 1. 目标

让「证据」本身经得起检查：**多格式可读、分块可查、位置可定位、数值可比**。

```text
SourceVersion(本地文件)
   → Loader（PDF / Markdown / HTML / README）
   → PageText（page_index / page_label / section）
   → DocumentChunk（持久化 + content_hash + chunk_index）
   → Evidence（chunk_id 可解析 + 精确 char_start/char_end + 位置必填）
   → QuantitativeEvidence（dataset / metric / value / comparator / protocol）
```

## 2. 当前缺陷（P3 要修的）

| 缺陷 | 现状 | 后果 |
|---|---|---|
| D1 分块不落库 | `DocumentChunk` 只在内存中传递 | `Evidence.chunk_id` 是悬空引用，事后无法回查原文 |
| D2 字符偏移失真 | 句子切分在「换行替换为空格」的文本上做，再回原文 `find()` | `char_start/char_end` 常为 `None` 或错位 |
| D3 无位置校验 | 证据缺 page/section 也能入库 | 违反 §2.2「链不完整必须标 unsupported」 |
| D4 只支持 PDF/Markdown | HTML/README 无法读取 | 大量技术来源（项目页、文档站）不可用 |
| D5 定量证据未用 | `QuantitativeEvidence` 模型存在但无抽取、无表 | 无法阻止跨论文错配比较（如不同数据集 PSNR 直接比） |

## 3. 设计决策

| 决策 | 内容 | 理由 |
|---|---|---|
| D6 | HTML 解析用 **标准库 `html.parser`**，不引入 bs4/selectolax | 计划 §5 推荐 bs4，但当前只需「标题→section、p/li/pre→正文、跳过 script/style/nav」，标准库足够且零新依赖（ADR-002 约束）；真实页面若解析失败再引入 bs4（记 ADR-014 偏差） |
| D7 | 新增 `chunks` 表，分块持久化 | 让 chunk_id 可解析是「可追溯」的前提 |
| D8 | 句子切分改为**在原文上取区间**（`_sentence_spans`），不再替换换行再 `find` | 偏移必须与原文逐字一致，否则引用无法定位 |
| D9 | 证据缺位置 → 不落库，记 `CITATION_LOCATION_MISSING` 事件 | §2.2 明确「链不完整必须标记」，静默入库是最坏情况 |
| D10 | 定量抽取**纯确定性正则**，覆盖 PSNR/SSIM/LPIPS/FID/MAE/MSE + dB + 数据集名 | §2.5 确定性优先；LLM 版留给后续替换同一接口 |
| D11 | 定量证据单独成表并回链 evidence_id | §15「避免无效跨论文比较」：比较前必须能按 dataset/metric 分组 |

## 4. 多格式加载

| 格式 | 入口 | page_index / page_label | section 来源 |
|---|---|---|---|
| PDF | `load_pdf` | 真实页号 / `p.N` | 暂为空（限制，见 §8） |
| Markdown | `load_markdown` | 0 / `md` | `#` 标题层级 |
| HTML | `load_html`（新） | 0 / `html` | `h1`–`h6` 标题 |
| README | `load_markdown` + `source_type=README` | 0 / `md` | 同 Markdown |

`load_document` 按后缀分派 `.pdf/.md/.markdown/.txt/.html/.htm`；`source_type_for` 识别 `README*` → `SourceType.README`，`.html/.htm` → `SourceType.HTML`。

HTML 解析规则：跳过 `script/style/nav/footer/header/aside/form`；`h1..h6` 结束上一节并开新节；`p/li/blockquote/pre/td` 收集文本；实体（`&amp;` 等）反转义；连续空白折叠。

## 5. 分块与偏移

- `chunk_pages()` 逻辑不变，但 `DocumentChunk` 落 `chunks` 表（含 `source_version_id`、`page_index`、`page_label`、`section`、`chunk_index`、`text`、`content_hash`）。
- `_sentence_spans(text)`：用 `(?<=[.!?])\s+` 在**原文**上找边界（小数点后无空白，天然不被切开），返回 `(start, end, sentence)`；证据 `char_start/char_end` 直接取区间，保证 `text[start:end] == evidence.text`。
- 已知限制：`et al. 2023` 这类缩写会被误判为句界（记录在案，不修）。

## 6. 定量证据

`QuantitativeEvidence` 抽取规则（确定性）：

| 字段 | 规则 |
|---|---|
| metric | 命中 `PSNR / SSIM / LPIPS / FID / MAE / MSE` |
| value | 指标后（≤12 字符内）出现的数字 |
| dataset | 命中内置数据集词表（Rain100H/SIDD/GoPro/…）或 `on <Capitalized>` |
| comparator | `compared with/than/over/baseline <X>` 捕获 |
| comparator_value | `compared with <num>` 或 `from <num> to <num>` |
| protocol | 句子含 `dB` → `dB`；含 `%` → `percent`；否则 `None` |

无 metric 或无数值的句子不产出定量记录（宁缺勿错）。

## 7. 编排与呈现

- `run_vertical_slice`：登记 work/version → **持久化 chunks** → 抽取证据（带偏移）→ 位置校验（缺失即拒收 + 事件）→ 抽取定量证据并落库 → 主张/关系 → memo。
- memo 每条证据追加位置 `(p.N / section / chunk_index)`；新增 `# Quantitative Evidence` 段，按 `dataset + metric` 分组列出，明确标注「跨数据集不可直接比较」。
- `inspect-claim` 输出增加 `chunk_id`、`section`、`page_label`、`char_range`。

## 8. 明确不做

- PDF 章节标题识别（需字体启发式，误判风险高，留给后续）。
- 表格结构还原（`td` 仅作为文本收集）。
- 远程 HTML/README 抓取（属网络获取，且外部文档为不可信数据，见 §27）。
- 指标归一化/换算（dB 与 % 不做互转）。
- 任何 LLM 参与抽取。

## 9. 验收

1. `pytest` 全绿，新增测试覆盖：HTML 加载、分块落库、字符偏移精确性、位置缺失拒收、定量抽取、端到端 memo。
2. 对 `tests/fixtures/sample_paper.md`：每条证据 `chunk_id` 可在 `chunks` 表查到，且 `chunk.text[char_start:char_end] == evidence.text`。
3. 同一文档产出 ≥3 条 QuantitativeEvidence（Rain100H 0.42 dB、SIDD 39.18 dB、Rain100L 0.11 dB）。
4. 构造一条无位置证据 → 不入库，产生 `CITATION_LOCATION_MISSING` 事件。
