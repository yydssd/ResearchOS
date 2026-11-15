# 方法获取能力 · 交接文档（2026-11-15）

> 面向：接手本分支的新会话。读完这一份应当知道「做到哪、为什么这么切、下一步敲什么命令」，
> 不需要回读前序对话。
>
> 权威文档：
> - 设计 `docs/superpowers/specs/2026-11-15-method-acquisition-design.md`（下称「设计」）
> - S1 计划 `docs/superpowers/plans/2026-11-15-s1-protocol-unit-split.md`（下称「S1 计划」）
> - 实测 `docs/evaluation/2026-11-14-method-acquisition-audit.md`
>
> 本文与上述不一致时，以**设计 + 实测输出**为准，并回来改本文。

---

## 0. 一句话状态

`method-acquisition-audit` 已**快进合并进 `master`**（本地，未推送），分支已删。
`master` 现在 `e248067` 之上 **47 个提交**：S1（`protocol` → `unit`）16 个、S2（确定性 L1/L2/L4）11 个，
其余是度量与文档。

**S1 五个任务全完成、验收 5/5；S2 十个任务全完成、验收 6/6**（判据见各自计划的验收表）。
**下一步是 S3 的计划（尚未开写）**：L3 的 LLM 接线。

本轮实测：**`374 passed, 2 skipped`**、**`376 tests collected`**、工作区干净。
（命令见 §6，跑法有坑见 §10。）

---

## 1. 接手第一步

```bash
cd /d/ResearchOS
git log --oneline master..HEAD | head -20    # 35 个提交
git status --short                            # 应为空
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_h1
```

仓库在 `D:\ResearchOS`（**不在**当前 workspace 目录内），解释器是 conda 环境 `reOS`。

---

## 2. 为什么做这件事（先看实测数字，不要看结论）

`docs/evaluation/2026-11-14-method-acquisition-audit.md` 在 40 篇留出集 × 4 层 = 160 格上实测：

| 层 | 图像复原 | Agent in MC | 系统侧为何是这个数 |
|---|---|---|---|
| L1 方法身份 | `0/20` | `0/20` | `method` 只在 `_PROPOSED_RE` 命中时写常量 `"proposed method"`，没有一行写出真名 |
| L2 方法构成 | `19/20` | `10/20` | 靠 `conditions` 的 `backbone=` / `baseline=` 蹭到，不是真组件 |
| L3 方法描述 | `0/20` | `0/20` | **全文任何模型都没有能存描述的位置** |
| L4 可复现设置 | `11/19` | `14/20` | 只靠 `training=` 一个槽 |

两句话必须说清，否则验收会被误读：

- L2 / L4 的分数是**蹭到的**，不是抽得好。
- L1 / L3 的 0 **不是抽错，是没地方存**。所以第一动作是**加落点**，不是调正则。

---

## 3. 四个已定决策（用户已拍板，不要重新讨论）

| 项 | 结论 |
|---|---|
| 抽取机制 | **分层混合**：L1 名字 / L2 组件 / L4 设置走确定性；**只有 L3 描述**走 LLM |
| 方法身份与 `identity_key` | **独立实体**，不进 identity；`subject` 仍为 `self@<source_version_id>` |
| P4 的 model scale / evaluation protocol | **接进 `conditions` 并进 `identity_key`**，接受合并行为改变，必须 before/after 双份登记 |
| L3 存储形态 | **结构化要点** `list[{aspect, statement, quote, chunk_id}]`，不是自由散文 |

出处与理由见设计 §0。要改这四条，先让用户改口，不要在实现里悄悄变通。

---

## 4. 为什么拆 S1–S4（不是拖延，是归因要求）

单次改动横跨数据模型、抽取、identity、迁移、编排、memo、审计脚本七个关注面且互相耦合，
before/after 差异无法归因到具体一项。按依赖排序拆四刀，**每刀单独出计划、单独提交、单独验收；
前一刀验收未过不进入下一刀**（设计 §3）。

| 阶段 | 范围 | 独立理由 | 状态 |
|---|---|---|---|
| **S1** | `protocol`→`unit` 语义修正 | 修一个**既有缺陷**，与方法获取无关；可单独回滚 | **进行中（3/5）** |
| **S2** | 确定性 L1/L2/L4 + `MethodProfile`/`MethodSetup`/`MethodPoint` + 存储 + memo + **审计脚本扩展** | 不碰 identity，不改主张数，可独立度量 | 未开始 |
| **S3** | L3：同步 `MethodDescriber` + async 适配器 + provider 配置 + 预算计数 + 4 个事件 + 录制回放 | 依赖 S2 的表；async / 预算 / 配置是独立风险面 | 未开始 |
| **S4** | `conditions` 新增 `scale=`/`protocol=` + **按 kind 的 provenance** + 级联安全 + before/after 三份报告 | 只有它改变主张宇宙，必须独占一个度量周期 | 未开始 |

两条顺序约束，违反任一条都要推倒重来：

- **S1 必须最先**：否则 `MethodSetup.protocol`、`QuantitativeEvidence.protocol`、
  `conditions` 的 `protocol=` 三个同名概念并存，S2 一落地就冲突。
- **S4 必须最后且独占周期**：否则主张数的变化无法归因到「新条件」还是「新抽取」。

---

## 5. S1 逐任务状态

| 任务 | 内容 | 状态 | 提交 |
|---|---|---|---|
| — | 写 S1 计划 | 完成 | `bb9d0fa` |
| **T1** | 加 `unit` 字段与列（**不改变任何行为**） | 完成 + 1 轮修复 | `bab64ed` `5d94886` `f55945b` |
| **T2** | 按数据幂等的回填 | 完成 + 2 轮修复 | `3513677` `fb4186e` `239d21d` `558556d`（+ 计划修复 `801b5a0`） |
| **T3** | 翻转写入点 / 读取点 / 渲染点（**必须一起改**） | 完成 + 1 轮修复 | `29109c5` `132808f`（+ 计划补签名 `b20b55c`） |
| **T4** | `inspect_claim` 输出键 `"protocol"` → `"unit"` | 完成 | `05e8f3c` |
| **T5** | ADR-033 + 已知限制 + README 核对 + 计数对账 | 完成 | `d2f10f4` |
| — | 计划计数修正 / 注释漂移修正 | 完成 | `938c67a` `2b92bce` |

### T1–T3 实际落地的代码（七处 + 一处注释）

```
src/research_os/domain/models.py            +  unit: str | None = None
src/research_os/storage/tables.py           +  unit 列
src/research_os/storage/database.py         +  _ADDED_COLUMNS["quantitative_evidence"]["unit"]
                                            +  _IDEMPOTENT_BACKFILLS（三条守卫式 UPDATE）
src/research_os/storage/repositories.py     +  create_many / _to_domain 双向映射
src/research_os/research/quantitative.py    ~  两个写入点 protocol= → unit=
src/research_os/research/claims.py          ~  row.protocol → row.unit（:206）
src/research_os/reporting/memo.py           ~  :144 单位查表、:169 回退键
scripts/method_acquisition_audit.py         ~  docstring 依据更新（见 §8）
```

T1–T3 曾有意把 `memo.py:503` 的 `"protocol": fact.protocol` 留着不动（一次性改六处可观察面会让
回滚无法定位），T4 已把它翻成 `"unit": fact.unit`。该处的用例同时断言**旧键不存在**——
只断言新键在，会让「两个键都在」的错实现也通过。

---

## 5b. S2 逐任务状态（确定性 L1/L2/L4）

计划：`docs/superpowers/plans/2026-11-15-s2-deterministic-extraction.md`；报告：
`docs/evaluation/2026-11-15-method-acquisition-s2.md`。

| 任务 | 内容 | 提交 |
|---|---|---|
| T1 | `research/patterns.py`：命名构式 / 组件词表 / L4 正则 | `be828ad` |
| T2 | `MethodPoint` / `MethodSetup` / `MethodProfile` | `184f12a` |
| T3 | L1 名字（层级排序、歧义、可定位） | `0746bf8` |
| T4 | L2 组件 + L4 设置 + `missing_layers` | `e7ba4db` |
| T5 | `method_profiles` / `method_points` 两表与仓储 | `e586687` |
| T6 | 竖切第 3 步：抽取 + 落库 + 两个普通事件 | `bf4cbad` |
| T7 | 行级 `method` 填充（self 名字 / 第三方名 / 占位） | `c3ddfe8` |
| T8 | memo `# Methods` 段 + 两个归因计数 | `cd13667` |
| T9 | 审计脚本改读 `MethodProfile` | `9be9374` |
| — | 修正：scheme-less 仓库 URL（L4 逐篇下降） | `1fdf95b` |
| — | 修正：L1/L4 缺口原因改记「词表未覆盖」 | `1ee2af4` |

实测（160 格）：L1 `0/20 → 16/20`（两域）、L2 `19/20 → 20/20` 与 `10/20 → 20/20`、
L4 `11/19 → 19/19` 与 `14/20 → 20/20`、L3 仍 `0/20`（S3 未做）；`gaps` **105 → 48**。
L1 产出 32 个名字，三条判据（逐字子串 / 独立构式 / 非片段）**0 失败**。

---

## 6. 当前基线证据（本轮实测，非推算）

```
$ cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s2_final
374 passed, 2 skipped, 1 warning in 24.46s

$ ... --collect-only -q --basetemp=.pytest_tmp_s2_collect
376 tests collected
```

基线演进：`326 → 327 → 330 → 331 → 332 → 333 passed`（收集 `328 → 334 → 335`）。S1 内的净增 7 条用例，
全部对应真实缺陷或真实可观察面，没有为凑数写的断言。T4 的 1 条是 S1 的第 7 条（`333 - 332`），
T5 只出文档，不改计数——这一点是判据：**T5 之后收集数不是 335 就说明有用例被静默删除**。

**S1 没有扰动已有度量**，证据是重跑审计脚本（只读、`summarise` 为纯函数）：

```
$ "D:/Anaconda/envs/reOS/python.exe" scripts/method_acquisition_audit.py \
    --labels tests/fixtures/method_acquisition/labels.json
agent_in_mc|L1   A=20/20 C=0/20    image_restoration|L1 A=20/20 C=0/20
agent_in_mc|L2   A=20/20 C=10/20   image_restoration|L2 A=20/20 C=19/20
agent_in_mc|L3   A=20/20 C=0/20    image_restoration|L3 A=20/20 C=0/20
agent_in_mc|L4   A=20/20 C=14/20   image_restoration|L4 A=19/20 C=11/19
gaps 合计 105
```

与 `docs/evaluation/2026-11-14-method-acquisition-audit.md` **逐格一致**（T4/T5 之后又重跑一次，
仍逐格一致；`gaps` 八格合计仍为 105）。

---

## 7. S1 期间修掉的四个真缺陷（都是审验抓出来的，不是风格问题）

记在这里是因为**每一个都会以「测试全绿」的形态活下来**：

1. **回填挂在 `ALTER` 事件上 = 永久跳过。** 设计初稿写「列刚添加时一次性执行」。但只要有任意
   一次 `init_db()` 发生在「加列」与「填数据」两个提交之间，该分支就再也不会进入，回填永久跳过，
   **而全量测试全绿**——只有真实库静默失去单位。改为语句自带数据守卫，可重复执行。
   实现见 `database.py` 的 `_IDEMPOTENT_BACKFILLS`。

2. **守卫写成 `unit IS NULL` 会静默丢单位。** 一行 `unit=''` 会被判「已填」，于是 `protocol`
   被清空、单位既不复制也不保留。本仓库其它地方（`memo.py` 的 `fact.protocol or ""`、
   `claims.py` 的 `or 'unit'`）一律把空串当「没有值」，所以判据必须是 `COALESCE(unit,'') = ''`。
   词表比对同样要 `lower(trim(...))`，否则 `'DB'` / `'dB '` 会留在 `protocol` 里，
   等读取点翻到 `unit` 之后这些行的 `value_bucket` 从 `dB:0.44` 塌成 `unit:0.44`。

3. **`value_bucket` 标签是大写 `B`，不是 `db:0.44`。** `_buckets()` 不做 `.lower()`。
   计划里写错了，会让 T3 的红测试因错误原因失败，而「顺手修」的方向（给 `_buckets` 加
   `.lower()`）会**静默改写 identity 第 7 段**（ADR-021）。已改正为断言 `("dB:0.44",)`，
   并在设计 §5.4 明文禁止加 `.lower()`。

4. **`assert "39.18 dB" in memo` 没有鉴别力。** memo 里嵌了证据原文，原文本身含 `39.18 dB`，
   渲染器回退成 `protocol` 照样绿。改为断言 `"[quant: PSNR 39.18 dB on SIDD]" in memo`，
   并已独立验证：把 `memo.py:144` 改回 `fact.protocol`，该用例失败；改回来，3 passed。

---

## 8. 本轮顺手修的两处注释漂移（不在 S1 原计划内）

- `scripts/method_acquisition_audit.py::system_side` 的 docstring 原写「`protocol` 存的是单位」。
  S1 之后这句成了**事实错误**，但结论（不把 `protocol` 观测为覆盖）仍成立，只是依据换了。
  按 HD-006 同批改为新依据：`protocol` 现在**处处为空**，观测它只会观察到空，直到 S4 填它。
  不改任何行为，审计数字已复跑核对（§6）。
- 设计 §14 的 B2 / M5 两行交叉引用指向的是**改版前**的 §5.3 / §5.2 措辞（「一次性执行」「四步」），
  与现行正文矛盾，已改成数据守卫式与六个消费点。

两处都记在设计 §13「实施偏差」的 D1 行。

---

## 9. 下一步：S3 的计划（S1 / S2 已收官）

### S1 收官记录（实测，可复核）

| 判据 | 结果 | 证据 |
|---|---|---|
| 1 `value_bucket` 逐字不变 | 通过 | `test_delta_bucket_label_survives_the_unit_split` 断言 `("dB:0.44",)` |
| 2 memo 仍显示单位 | 通过 | `"[quant: PSNR 39.18 dB on SIDD]" in memo`（`test_evidence_quality.py`） |
| 3 `init_db()` 两次幂等 | 通过 | `test_second_init_db_does_not_destroy_the_backfilled_unit` |
| 4 既有用例一条不少 | 通过 | `333 passed / 335 collected`（预期值即此） |
| 5 `protocol` 不再当单位用 | 通过 | `grep -rn "fact.protocol\|row.protocol" src/` 只剩 `repositories.py:394/412` 两行映射 |

T4 落地：`memo.py:503` 键改 `"unit"`，用例断言 `any(fact["unit"] == "dB")` +
`all("protocol" not in fact)`；红→绿过程已核（红因 `KeyError: 'unit'`，即旧键名仍在）。
T5 落地：`architect.md` 加 ADR-033 与已知限制第 13 条、维护记录加一行；README **无需改**——
`grep "protocol|定量|QuantitativeEvidence" README.md` 命中的三处（:12 阶段表、:154 定量计数、
:249「单位只看数值紧邻 6 字符」）都不描述该字段，且第 249 行拆分后依然成立。
另按 HD-006 补了 `models.py:154` 的注释（设计 §13 D2），只改注释不改行为。

### S2 收官记录（实测，可复核）

| 判据 | 结果 | 证据 |
|---|---|---|
| 1 三层各有落点 | 通过 | `test_method_run.py` 从库里读回 name + `name_chunk_id`、components、scale/protocol |
| 2 「没抽到」与「抽到为空」可区分 | 通过 | `missing_layers` 落库；`sample_paper` 逐篇记 `L1` |
| 3 L1 精度零容忍 | 通过 | 32 个名字，逐字子串 / 独立构式 / 非片段三条判据 **0 失败**（报告 §4） |
| 4 审计脚本能观测新能力 | 通过 | `system_side` 改读 `MethodProfile`；L3 判据读 `points` 不再是常量 |
| 5 不扰动 identity 与主张数 | 通过 | `claims.py`、`contradiction.py`、`scope.py` 零改动；claim 用例一条未改 |
| 6 既有用例一条不少 | 通过 | `374 passed / 376 collected`（333 + 41） |

### S3 起手要做的事

1. **先写计划**：`docs/superpowers/plans/2026-11-16-s3-l3-describer.md`，依据设计 §7：
   同步 `MethodDescriber` 协议 + `AsyncProviderDescriber`（`asyncio.run` + 事件循环探测）、
   `config.py` 三个配置项、`Supervisor` 注入、**预算计数点（先查后加）+ 4 个 `FailureType`**、
   四道防线、`recorded fixture provider`。
2. S3 的三条现成接口不必重新设计：`MethodProfile.points`（`MethodPoint` 已有校验：aspect 枚举 /
   statement ≤200）、`MethodExtraction`、`SqlMethodProfileRepository.upsert` 的 points 替换语义
   （已测 `test_points_are_replaced_not_appended`）。S3 只需把 points 填进去。
3. 现成可复用的坑位记录：`budget.llm_calls` 全仓库仍无写入点（设计 §7.3），
   `_check_budget()` 只读 `exceeded()`——S3 必须补「先查后加」，否则 80/81 off-by-one。
4. 审计脚本的 L3 判据已经就绪（`side["L3"] = bool(profile.points)`），S3 落地后
   **不要改判据**，只重跑；改判据等于把「能力生效」和「度量口径变了」混在一起。

### 仍未偿的小事

- `memo.py` 的回退键 `fact.metric or fact.unit or "unspecified"` 语义正确，但**仍没有专门用例**，
  现有覆盖来自间接路径。S3 动 memo 时一并定。
- 待办 #10：§21（`ResearchOS-Implementation-Plan.md`）仍无方法抽取指标；S2 已经把四层度量跑成
  报告（`docs/evaluation/2026-11-15-method-acquisition-s2.md`），**登记进 §21 的动作还没做**，
  与 S3 的指标一起登记更省一次改动。
- 设计 §13 现在有 D1–D15：D14（scheme-less 仓库 URL）与 D15（L1/L4 缺口原因改记「词表未覆盖」）
  是实现期实测抓出来的，不在原计划里。

---

## 10. 环境坑（都踩过，别再踩）

1. **`pytest -q` 会吞掉汇总行**：`pyproject.toml:36` 是 `addopts = "-q --basetemp=.pytest_tmp"`，
   命令行再给一个 `-q` 就变成 `-qq`，**汇总行整行消失**，看起来像「跑完了但没结果」。
   一律用 `-o addopts=""` 连带清掉 addopts：
   `"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q`。
2. **`--basetemp` 目录被沙箱拒绝删除**。`addopts` 里硬编码的 `.pytest_tmp` 会一直复用同一个目录；
   清掉 addopts 后自己给，**每次换一个新目录名**（`.pytest_tmp_h1`、`_h2`…），不要复用。
3. **没有装 `ruff`**。不要用 `ruff check` 当验收，用测试 + `grep`。
4. **`init_db(url=...)` 会永久替换全局 engine / session factory**，后续测试会指向已删除的临时文件。
   `tests/unit/test_database.py` 已有 `file_database` fixture 在 teardown 里
   `init_db(url="sqlite:///:memory:")` 复位——新写文件库用例必须复用它。
5. **陈旧 DDL 会和模型漂移**。`_old_database_without_unit` 已改为从 `Base.metadata.create_all`
   派生再 `DROP COLUMN`，不要再手写建表语句。

---

## 11. 判定逻辑上的已知雷（**不要顺手改**）

这些是用户逐条否决过的点，改了会连带改写全部实测数字：

- **方向词表盲区**：裸名词 `gain` 命中 `_IMPROVE`，否定式词表是封闭的。
  `gain disappears` / `does not outperform` / `The gain is 0.5 dB` 都会被误判成 `UP`。
  修它要连带重测所有方向分布，**必须独立开一个度量周期**，不要在修别的东西时顺手改。
- **`_buckets` 不许加 `.lower()`**（ADR-021，见 §7.3）。
- **`claims.py:180` 的 `if own: return own, "sentence"`** 是整体覆盖 + tier 升级；
  与 `contradiction.py:146` 的 `_CONFIRMED_TIERS = {"sentence","heading"}` 叠加后，
  一句「success rate」就能产出 `TRUE_CONTRADICTION`。已登记未修。
- **82% 的主张拿不到 dataset**（论文用 "this dataset" / "Table 2" 指代），卡住 P5 候选规模。
  需要表格解析或代词消解，**不要靠放宽判定门槛绕过**。
- **P5 夹具第二轮独立盲标未做**。26 对 100% 通过只能当回归锁（HD-015），
  `ANNOTATION.md` 的 pass log 记为 not performed。

当前方向分布（P5 前置修正后、20 篇留出集）：`UP 372 / None 685 / DOWN 16 / LEVEL 2`，
支持主张 1075 条，合并门槛 73（7%），候选对 1049，真矛盾 0。
**设计 spec / 早期 HD 里的 1063 条、111 门槛、64.3% 覆盖是修正前快照，不要引用。**

---

## 12. 待办登记（设计 §12，共 10 条）

不属于本轮四阶段，但会反复被问到，先分清归属：

| # | 事项 | 归属 |
|---|---|---|
| 1 | 领域词表可移植（`lexicon.py` 只有图像复原，是 MC 归零的直接原因） | S2 前置 |
| 2 | architecture 维只有 `backbone=` 一词 | 需单独设计「架构身份」 |
| 3 | §8 来源权威层级（`repository` 与论文描述冲突时取谁没有规则） | 未立项 |
| 4 | §19 Falsification 的源码检查 | 未立项 |
| 5 | 一篇多方法（`2409.19479` 一类只取一个 `name`） | S2 之后 |
| 6 | L3 第二轮独立盲标（`covered` 分母仍是 owner-derived） | S3 之后 |
| 7 | `SqlEventRepository.list_by_run` 缺 `ORDER BY`，memo 取 `events[-1]` 靠 SQLite rowid | 技术债 |
| 8 | `replaced` payload 值断言、`inspect_claim` partner 成员断言 | 技术债 |
| 9 | §2.5 其余 6 项确定性实现的 deviation ADR 逐项登记 | 文档债 |
| 10 | §21 指标清单无方法抽取指标，需登记进 §21 / `README.md` | **仍未做**；度量已在 2026-11-15 报告里，等 S3 一起登记 |

---

## 13. 不要做的事

- **不要**为让测试变绿改 `_buckets`、放宽容差、或把断言改成存在性断言。
- **不要**在 S1 未验收前开始 S2。S1 的验收判据是「`value_bucket` 逐字不变 + `init_db()` 两次幂等 +
  既有用例一条不少」，见 S1 计划末尾表。
- **不要**重写 `docs/superpowers/plans/2026-11-14-*.md` 这类历史快照——它们记录的是当时的样子，
  偏差一律记进设计的 §13 表。
- **不要**相信子代理的「已完成」报告。上一轮一个子代理被中断，实际已经提交（`132808f`）；
  反过来也有报告成功但没落盘的情况。**以 `git log` / `git diff` / 实测输出为准。**
- **不要**在没有失败测试的情况下写生产代码（TDD），这条在本项目是刚性的。
