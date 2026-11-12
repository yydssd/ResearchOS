# P2 — Source Discovery and Verification · 设计规格

- **日期**：2026-11-12（W2 / Day 2）
- **对应计划**：`ResearchOS-Implementation-Plan.md` v1.1 §14（Phase 2），并受 §2 不变量、§8 来源权威、§25 失败模型、§26 预算控制约束
- **前置状态**：P0 Foundation ✅、P1 Vertical Slice ✅（23 tests 全绿）
- **范围**：只做 P2 源层。不接 P3（多格式加载 / 定量证据）、不做 P4+ 语义推理。

---

## 1. 目标

把"研究问题"变成"一批已核验的 canonical work + 其版本"，为后续 deep read 提供可信输入。

```text
ResearchQuestion
   → 查询生成（确定性）
   → SearchProvider[]（arXiv / Crossref / OpenAlex / Fixture）
   → SourceCandidate（发现候选：永不算证据）
   → 确定性规范化（DOI / arXiv / 标题 / 作者）
   → 去重与版本合并
   → ResearchWork（canonical work）+ SourceVersion[]
   → 核验（verified / unverified + 原因）
   → 事件 + 预算计数
```

## 2. 验收标准（对齐计划 §14）

1. 单个研究问题产出 **≥ 10 个 SourceCandidate**。
2. 同一逻辑作品的多个版本**合并为一个 work**（fixture 内已有真实重复对：AutoDIR 的 arXiv `2310.10123v5` 与 ECCV 2024 版 `10.1007/978-3-031-73661-2_19`）。
3. canonical work 身份**落库**（`works` 表 + 版本指向同一 `work_id`）。
4. verified 与 unverified 版本**可区分且带原因**（`verification_notes`）。
5. 搜索片段（snippet / abstract）**绝不进入证据表**。
6. `pytest` 全绿；真实网络只用于 opt-in 冒烟测试与人工验收。

## 3. 核心设计决策

| 决策 | 内容 | 理由 |
|---|---|---|
| D1 | 新增 `sources/` 包（normalize / providers / resolver / verification），不塞进 `research/` | 源层与语义层职责分离；`research/` 只做需要语义判断的事（§2.5） |
| D2 | `SourceCandidate` 是独立领域对象 + 独立表 | §2.1 证据与主张分离；候选是第三种对象，绝不可冒充证据 |
| D3 | 规范化全部为纯函数，零 I/O | §2.5 确定性优先；可被单测穷举 |
| D4 | provider 使用同步 `httpx.Client`，并允许注入 transport | 现有代码库全同步；注入 `MockTransport` 使测试完全离线 |
| D5 | 测试默认离线，真实网络用 `RESEARCHOS_NETWORK_TESTS=1` 才跑 | 评估可重复；CI 不因网络抖动红 |
| D6 | 标题相似但作者冲突时**不合并**，标 `SOURCE_IDENTITY_AMBIGUOUS` | 宁可多一个 work，也不制造错误身份（可追溯性优先于整洁） |
| D7 | `source_tier` 只作发现元数据，不参与真假判定 | §8：来源权威依赖被评估的主张，不能做全局排序 |
| D8 | 预算计数只在 supervisor 侧递增 | §26 supervisor 独占预算，组件不得覆盖 |

## 4. 领域模型新增

### 4.1 SourceCandidate

```python
class SourceCandidate(BaseModel):
    id: str
    provider: str                 # 'arxiv' | 'crossref' | 'openalex' | 'fixture'
    provider_rank: int = 0        # 0-based rank inside that provider's result list
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None        # normalized (lowercase, no URL prefix)
    arxiv_id: str | None = None   # normalized base id, no version suffix
    arxiv_version: str | None = None
    url: str | None = None
    abstract: str | None = None   # discovery-only; never becomes Evidence
    source_type: SourceType = SourceType.WEB
    raw: dict = {}
```

`abstract` 与 `raw` 只用于审计与后续 deep read 的线索，明确禁止写入 `evidence` 表。

### 4.2 SourceTier

```python
class SourceTier(StrEnum):
    OFFICIAL_PUBLICATION = "OFFICIAL_PUBLICATION"
    PREPRINT = "PREPRINT"
    REPOSITORY = "REPOSITORY"
    WEB = "WEB"
    UNKNOWN = "UNKNOWN"
```

`SourceVersion` 增加 `source_tier: SourceTier | None`，仅作发现元数据。

## 5. 规范化规则（`sources/normalize.py`）

| 函数 | 规则 |
|---|---|
| `normalize_doi(raw)` | 去 `https?://(dx.)?doi.org/`、`doi:` 前缀与首尾标点，小写；必须匹配 `^10\.\d{4,9}/\S+$`，否则返回 `None` |
| `parse_arxiv(raw)` | 支持 `arXiv:2104.12345v3`、`2104.12345`、`https://arxiv.org/abs/2104.12345v2`、`/pdf/...pdf`、旧式 `cs/0601001`；返回 `(base_id, version)` |
| `normalize_title(raw)` | NFKC、去 LaTeX 花括号与命令残余、小写、去标点、折叠空白；剥离尾部的 `(supplementary material)` / `(extended version)` 类片段 |
| `title_similarity(a, b)` | 归一化标题的 token Jaccard 与 `difflib.SequenceMatcher` 取最大值，返回 `[0,1]` |
| `normalize_author(raw)` | 处理 `"Zamir, Syed Waqas"` 与 `"Syed Waqas Zamir"` 两种形态，输出 `"last|f"` 键 |
| `author_overlap(a, b)` | 归一化作者键（姓 + 名首字母）的交集 / 较小集合大小 |

阈值（常量，集中在 `resolver.py`）：

- `TITLE_SIMILARITY_THRESHOLD = 0.92`
- `AUTHOR_OVERLAP_THRESHOLD = 0.5`
- `YEAR_TOLERANCE = 1`

## 6. Provider（`sources/providers.py`）

```python
class SearchProvider(Protocol):
    name: str
    def search(self, query: str, limit: int) -> list[SourceCandidate]: ...
```

| 实现 | 端点 | 关键解析 |
|---|---|---|
| `ArxivProvider` | `export.arxiv.org/api/query` | `search_query` 用 `all:` 逐词 AND（**不用整句引号短语**），超长时取头部 2 + 尾部 3 词元；Atom XML：`id`（含版本）→ arxiv_id/version，`title` 折叠空白，`arxiv:doi`，`published` → year |
| `CrossrefProvider` | `api.crossref.org/works` | `query.bibliographic`；`DOI` / `title[0]` / `author[].given,family` / `issued.date-parts[0][0]` / `container-title[0]` |
| `OpenAlexProvider` | `api.openalex.org/works` | `display_name` / `doi` / `publication_year` / `authorships[].author.display_name` / `primary_location.source.display_name` |
| `FixtureProvider` | 本地 JSON | 读取已录制的候选列表，用于离线端到端与演示 |

约定：

- 任何 HTTP 失败或报文不可解析 → 抛 `ProviderError(FailureType.NETWORK_ERROR | SOURCE_UNAVAILABLE)`，由 supervisor 记 `FAILURE` 事件，不吞异常。
- provider 不做跨源去重、不做核验、不做排序以外的语义判断。
- 每个 provider 结果按 provider rank 记录原始名次，便于后续评估 source coverage。

## 7. 查询生成（`sources/query.py`）

确定性、无 LLM：

- `extract_keyterms(question)`：小写化 → 去标点 → 去停用词 → 保序去重。
- `build_queries(question, max_queries=2)`：`[keyterms]`，以及 `keyterms + " survey"`（当问题本身不含 survey/review 时）。上限由 `max_queries` 控制。

这一层刻意保持简单：查询改写属于语义判断，等 P7 反证搜索阶段再用 LLM。

## 8. 聚类与合并（`sources/resolver.py`）

**匹配优先级（并查集式增量聚类）**

1. DOI 相同 → 同 work。
2. arXiv base id 相同 → 同 work。
3. 归一化标题相似度 ≥ 0.92 **且** 作者重合 ≥ 0.5 **且** 年份差 ≤ 1 → 同 work。
4. 标题相似但作者重合 < 0.5 → **不合并**，标记 `ambiguous=True`，原因写 `SOURCE_IDENTITY_AMBIGUOUS`。

**版本合并**：同一 work 内，按 `doi` / `arxiv_id` / `normalized_title+year` 识别同一版本；重复候选合并为一条版本，缺失字段互补（DOI 补 DOI、venue 补 venue），并记录 `merged from <provider>`。

**canonical 选择**：`OFFICIAL_PUBLICATION > PREPRINT > REPOSITORY > WEB > UNKNOWN`；同 tier 取年份较新、版本号较高者。`ResearchWork.canonical_title` 取该版本标题。

## 9. 核验（`sources/verification.py`）

一个版本 `verified=True` 当且仅当：

1. 具备可解析标识符（DOI 或 arXiv id），且
2. 标题非空，且
3. 作者列表非空，且
4. 未命中身份歧义。

否则 `verified=False` 并在 `verification_notes` 写明原因（`no resolvable identifier` / `no authors` / `identity ambiguous` / `no venue for published claim`）。

## 10. 持久化

- 新表 `source_candidates`：含 `run_id`、provider 元信息、规范化后的标识符、`abstract`、`raw`（JSON）、`resolved_work_id`、`resolved_source_version_id`。
- `source_versions` 增列 `source_tier`：SQLite `create_all` 不会给既有库加列，故 `init_db` 增加幂等轻量迁移（`PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN`），只加列不改数据。
- 新增 `SqlSourceCandidateRepository`：`create_many` / `list_by_run` / `list_all`。

## 11. 编排与接口

- `Supervisor.run_source_discovery(run_id, limit=15, providers=None)`：
  - 生成查询 → 逐 provider 搜索（每次 +1 `search_calls`，超预算即停并记事件）→ 落候选 → 聚类 → 落 work/version → 核验 → 记 `SOURCE_DISCOVERED` / `SOURCE_VERIFIED` / `FAILURE` 事件 → 返回摘要 dict。
  - provider 默认由 `settings` 决定：`RESEARCHOS_SEARCH_PROVIDERS`（逗号分隔，默认 `arxiv,crossref,openalex`）。
- CLI：`research-os discover --question ... [--limit 15] [--fixture DIR]`、`research-os sources RUN_ID`。
- API：`GET /research/{run_id}/sources` 返回 works + versions + verified 标记。

## 12. 测试计划（TDD 顺序）

1. `tests/unit/test_normalize.py` — DOI 六种形态、arXiv 五种形态、标题归一化、作者两种形态、相似度边界。
2. `tests/unit/test_query.py` — 停用词、保序去重、变体数量上限。
3. `tests/unit/test_providers.py` — 用录制报文 + `MockTransport` 解析三个 provider；HTTP 500 → `ProviderError`。
4. `tests/unit/test_resolver.py` — DOI 合并、arXiv 版本合并、AutoDIR 双源合并、作者冲突不合并、canonical 选择。
5. `tests/unit/test_verification.py` — verified 四条规则与 tier 判定。
6. `tests/integration/test_source_discovery.py` — 离线端到端：≥10 候选、候选落库、work 合并、verified 区分、snippet 未入证据、预算与事件。
7. `tests/integration/test_live_providers.py` — 仅 `RESEARCHOS_NETWORK_TESTS=1` 时跑，验证真实端点仍可解析。

## 13. 明确不做

- 不做 HTML / README 加载（P3）。
- 不做摘要级定量证据抽取（P3）。
- 不做语义查询改写、反证搜索（P7）。
- 不引入向量库、图数据库、agent 框架、异步队列。
- 不把候选摘要写进证据表。
