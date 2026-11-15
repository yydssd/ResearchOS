# S4 实测：方法获取四层（2026-11-15）

> before：`docs/evaluation/2026-11-14-method-acquisition-audit.md` 与
> `docs/evaluation/2026-11-15-method-acquisition-s2.md` §1（原数字未改）
> after：`python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json`

## 1. before / after（同一 40 篇、同一 160 格）

| 层 | 原始基线 (2026-11-14) | S2 after | S4 after | 解释 |
|---|---|---|---|---|
| L1 图像 / MC | 0/20 · 0/20 | 16/20 · 16/20 | 16/20 · 16/20 | S4 不碰 L1 |
| L2 图像 / MC | 19/20 · 10/20 | 20/20 · 20/20 | 20/20 · 20/20 | S4 不碰 L2 |
| L3 图像 / MC | 0/20 · 0/20 | 0/20 · 0/20 | 0/20 · 0/20 | S3 无 provider，原因 `LLM 未启用` |
| L4 图像 / MC | 11/19 · 14/20 | 19/19 · 20/20 | 19/19 · 20/20 | S4 不碰 L4 |
| `gaps` 合计 | 105 | 48 | **48** | 无变化 |

## 2. 变化归因

S4 只改 `conditions` 的单句身份维度与 provenance，**不产方法名、组件、设置或描述**，
审计脚本的 `system_side` 仍只读 `MethodProfile`。四层八格逐格一致，
`gaps` 仍为 48（L1 词表未覆盖 4+4、L3 `LLM 未启用` 20+20）。

## 3. 验收

设计 §10.4 的「逐篇布尔向量」在本阶段无下降：S4 没有改变任何一层的生产者。

## 4. 已知未解决

- L3 仍未测量（无 provider 客户端，录制夹具目录为空），见已知限制 17。
