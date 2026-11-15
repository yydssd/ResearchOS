# L3 provider 客户端 + 录制通路 实施计划（小阶段，无 key 也能完成 90%）

> **For agentic workers:** 逐任务执行，TDD，每任务一个提交。这是**独立立项**，不属于 S1–S4。

**Goal:** 让 L3 从「协议就绪、无 provider」变成「一条命令即可录制并测量」——缺的只剩一把 key。

**Architecture:** 一个 OpenAI 兼容的 chat-completions 客户端（`httpx.AsyncClient`，JSON 模式），包在现有的 `AsyncProviderDescriber` 里；工厂新增 `llm_provider="openai"` 分支；`record_method_descriptions.py` 从「拒绝桩」变成真正能录的脚本，按 `prompt_key` 命名、按 `prompt_index` 映射 chunk。全部用 `httpx.MockTransport` 测（ADR-010），所以**没有 key 也能把除「真实录制」以外的每一步验证完**。

**Tech Stack:** Python 3.12 / httpx（已装）/ pydantic v2 / pytest。解释器 `D:/Anaconda/envs/reOS/python.exe`。

**基线：** `418 passed, 2 skipped / 420 collected`。解释器与 `-o addopts=""`、`--basetemp` 换名的规矩同前几阶段。

**任务顺序（审验后调换）：** 客户端（Task 1）必须先于工厂分支（Task 2）落地。反过来时 `factory.py` 会 import 一个还不存在的模块，Task 1 的绿阶段实测 `1 failed, 4 passed`（`ModuleNotFoundError: research_os.llm.openai_compat`）——那不是绿。

**逐任务累计：** 418 → 423（+5）→ 425（+2）→ 428（+3 passed，2 skipped）→ 收集 420 → 425 → 427 → 430。

**已确认的边界（不要越界）：**
- 本阶段**不**录任何数据：没有 key，伪造录制会让「未测量」看起来像「已测量」（已知限制 17 的原话）。
- **不**改四道防线、不改 `MethodPoint`、不改 `identity_key`、不改矛盾级联。
- 不引入新依赖（httpx 已在依赖里）。

---

### Task 1: OpenAI 兼容客户端

**Files:**
- Create: `src/research_os/llm/openai_compat.py`
- Test: `tests/unit/test_openai_compat.py`（新建，5 条）

- [ ] **Step 1: 写测试（MockTransport，无网络）**

```python
"""The one place that speaks HTTP to a model (ADR-010: recorded transport)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from research_os.llm.base import Message, MethodDescriptionResponse
from research_os.llm.openai_compat import OpenAICompatibleProvider

MESSAGES = [Message(role="system", content="s"), Message(role="user", content="u")]


def _provider(handler) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        base_url="https://example.invalid/v1", api_key="k", model="m", client=client
    )


def test_a_json_answer_is_parsed_into_the_response_model():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer k"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"points": [
                    {"aspect": "goal", "statement": "s", "quote": "q", "chunk_id": "c"}
                ]})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    response = asyncio.run(_provider(handler).generate(MESSAGES))

    assert isinstance(response, MethodDescriptionResponse)
    assert response.points[0].chunk_id == "c"


def test_usage_becomes_a_cost_estimate():
    """`last_cost_usd` stays None when no price table applies; a made-up number
    would make the budget ceiling depend on a guess."""
    provider = _provider(
        lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "{\"points\": []}"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
        })
    )
    provider.price_per_million = (0.0, 0.0)

    asyncio.run(provider.generate(MESSAGES))

    assert provider.last_cost_usd == 0.0
    assert OpenAICompatibleProvider(base_url="x", api_key="k", model="m").last_cost_usd is None


def test_a_non_200_is_an_error_not_an_empty_answer():
    provider = _provider(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(RuntimeError, match="500"):
        asyncio.run(provider.generate(MESSAGES))


def test_content_that_is_not_json_is_an_error():
    provider = _provider(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json at all"}}]}
        )
    )

    with pytest.raises(RuntimeError, match="json"):
        asyncio.run(provider.generate(MESSAGES))


def test_a_timeout_is_an_error_with_the_timeout_in_the_message():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _provider(handler)

    with pytest.raises(RuntimeError, match="timeout|timed out"):
        asyncio.run(provider.generate(MESSAGES))
```

- [ ] **Step 2: 跑红**

预期：`ModuleNotFoundError: research_os.llm.openai_compat`。

- [ ] **Step 3: 实现**

`src/research_os/llm/openai_compat.py`：

```python
"""OpenAI-compatible chat completions (one client, many vendors).

Deliberately small: JSON mode, one attempt, errors raised. Retries belong to the
caller's budget, and a silent retry would spend calls the supervisor never counted
(design §7.3).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from research_os.llm.base import MethodDescriptionResponse, Message

DEFAULT_TIMEOUT = 60.0


class OpenAICompatibleProvider:
    """`generate()` posts to `{base_url}/chat/completions` in JSON mode."""

    # (input $/1M, output $/1M). None means "no price table": `last_cost_usd`
    # then stays None and the supervisor leaves the cost counter alone.
    price_per_million: tuple[float, float] | None = None

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model
        self._client = client
        self._timeout = timeout
        self.last_cost_usd: float | None = None

    async def generate(self, messages: list[Message], response_model: type | None = None) -> Any:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            # JSON mode is what makes the draft model parseable at all; without it
            # half the answers arrive wrapped in prose and the schema defence
            # rejects the paper for a formatting reason.
            "response_format": {"type": "json_object"},
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._key}"},
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"timeout talking to the model: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()
        if response.status_code != 200:
            raise RuntimeError(f"model returned {response.status_code}: {response.text[:200]}")
        content = response.json()["choices"][0]["message"]["content"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"model answer was not json: {content[:200]}") from exc
        self.last_cost_usd = self._cost(response.json().get("usage") or {})
        return MethodDescriptionResponse.model_validate(data)

    def _cost(self, usage: dict) -> float | None:
        if self.price_per_million is None:
            return None
        prompt, completion = self.price_per_million
        # Both defaults are 0: a missing usage field means "unknown", and charging
        # a full million tokens for it would inflate the supervisor's ceiling.
        return round(
            usage.get("prompt_tokens", 0) / 1e6 * prompt
            + usage.get("completion_tokens", 0) / 1e6 * completion,
            6,
        )
```

- [ ] **Step 4: 跑绿 + 全量**

`tests/unit/test_openai_compat.py` 5 passed；全量 `423 passed, 2 skipped`（收集 425）。

- [ ] **Step 5: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/llm/openai_compat.py tests/unit/test_openai_compat.py
git commit -m "feat(llm): add an OpenAI-compatible client, tested without a network

JSON mode, one attempt, errors raised: a silent retry would spend calls the
supervisor never counted. Cost stays None unless a price table is set, because a
made-up number makes the budget ceiling depend on a guess."
```

---

### Task 2: 配置 + 工厂分支

**Files:**
- Modify: `src/research_os/config.py`（加 `llm_base_url`）
- Modify: `src/research_os/llm/factory.py`（`openai` 分支）
- Test: `tests/unit/test_llm_config.py`（改 1 条、追加 2 条）

- [ ] **Step 1: 改测试**

`test_an_unknown_provider_name_is_a_configuration_error` 现在拿 `"openai"` 当未知名字——这个前提本阶段就失效了。改成 `"cohere"`。

文件顶部补 `import pytest`（现有文件没有导入它），并删掉新用例里那行局部 `from research_os.llm.describer import AsyncProviderDescriber`（模块顶部已有同名导入）。追加：

```python
def test_an_openai_compatible_provider_needs_a_key():
    settings = Settings(llm_provider="openai", llm_api_key=None)
    with pytest.raises(ValueError, match="llm_api_key"):
        build_describer(settings)


def test_an_openai_compatible_provider_builds_with_a_key():
    settings = Settings(
        llm_provider="openai",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_base_url="https://example.invalid/v1",
    )
    describer = build_describer(settings)

    assert isinstance(describer, AsyncProviderDescriber)
```

注意 `Settings` 是 `extra="ignore"`：字段不存在时 `llm_base_url=` 会被**静默丢掉**，不抛 `ValidationError`。所以第二条例外的红来自「`openai` 未实现」，不是「字段不存在」——别按后者写断言。

- [ ] **Step 2: 跑红**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_llm_config.py -q --basetemp=.pytest_tmp_p1_red
```

预期：**`2 failed, 3 passed`** —— 只有两条新用例红。`test_an_unknown_provider_name...` 改成 `"cohere"` 后仍然是绿的（`cohere` 本来就不认识），这一条是把守卫钉在别处，不是红点。

- [ ] **Step 3: 实现**

`config.py` 在 `llm_api_key` 之后加：

```python
    # Base URL for the OpenAI-compatible endpoint (design: one client, many
    # vendors). Kept as configuration rather than a constant so the same code
    # can point at a gateway, a proxy, or a local server.
    llm_base_url: str = "https://api.openai.com/v1"
```

`factory.py` 在 `recorded` 分支之后加：

```python
    if name in ("openai", "openai_compatible"):
        if not settings.llm_api_key:
            raise ValueError("llm_provider=openai requires llm_api_key")
        from research_os.llm.openai_compat import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4o-mini",
        )
        return AsyncProviderDescriber(provider, model=settings.llm_model)
```

并把末尾 `raise ValueError(...)` 的提示改成 `use 'none', 'recorded' or 'openai'`；模块 docstring 里「Only `recorded` is implemented」这句同时改掉（否则注释与代码互相打脸）：

```python
"""Assemble one describer from settings (design §7.2).

`recorded` replays fixtures; `openai` talks to any OpenAI-compatible endpoint.
Naming a provider without a key is a configuration error rather than a silent
fallback, because "I configured a model and got heuristics" is the quiet failure
this project keeps paying for.
"""
```

- [ ] **Step 4: 跑绿 + 全量**

`tests/unit/test_llm_config.py` 应 5 passed；全量 `425 passed, 2 skipped`（收集 427）。

- [ ] **Step 5: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/config.py src/research_os/llm/factory.py tests/unit/test_llm_config.py
git commit -m "feat(llm): build an OpenAI-compatible describer from configuration

Naming a provider without a key is a configuration error, not a silent fallback:
'I configured a model and got heuristics' is the failure this project keeps
paying for."
```

---

### Task 3: 录制脚本真正可用

**Files:**
- Modify: `scripts/record_method_descriptions.py`
- Modify: `src/research_os/llm/recorded.py`（把 id 解析提成 `prompt_ids()`，录制与回放共用同一个正则；否则两处各写一套，「哪一行算 id」会在录制侧悄悄漂移）
- Test: `tests/unit/test_record_script.py`（新建，3 条）

- [ ] **Step 1: 写测试**

```python
"""Recording is a command, not a manual step (design §7.6)."""

from __future__ import annotations

import json

from scripts.record_method_descriptions import plan_jobs, write_recording


def test_jobs_are_keyed_by_the_prompt_without_ids():
    from research_os.domain.models import DocumentChunk

    chunks = [DocumentChunk(id="chunk_x", source_version_id="sv", section="Method",
                            chunk_index=0, text="We store the policy as code.")]
    jobs = plan_jobs([chunks])

    assert len(jobs) == 1
    key, prompt = jobs[0]
    assert "chunk_x" not in key          # the key must survive a new run
    assert "[chunk_x]" in prompt          # the prompt still carries the real id


def test_an_existing_recording_is_not_overwritten(tmp_path):
    key = "abc123"
    out = tmp_path / f"{key}.json"
    out.write_text(json.dumps({"points": [{"quote": "kept"}]}), encoding="utf-8")

    write_recording(tmp_path, key, {"points": [{"quote": "new"}]})

    assert json.loads(out.read_text(encoding="utf-8"))["points"][0]["quote"] == "kept"


def test_no_key_means_exit_2_and_no_files(tmp_path, monkeypatch):
    from scripts import record_method_descriptions as script

    # Explicit: a developer shell with a real key exported must not turn the
    # "refuse to fabricate" contract into a 40-paper recording run.
    monkeypatch.delenv("RESEARCHOS_LLM_API_KEY", raising=False)
    code = script.main(["--provider", "openai", "--out", str(tmp_path), "--cache", str(tmp_path)])

    assert code == 2
    assert list(tmp_path.glob("*.json")) == []
```

- [ ] **Step 2: 跑红**（`scripts.record_method_descriptions` 里没有 `plan_jobs` / `write_recording`，`main()` 也不收 argv → 导入即 `ImportError`，3 条全红）

- [ ] **Step 3: 实现**

`src/research_os/llm/recorded.py` 把 id 解析提成公开函数，`RecordedProvider.generate` 改为调用它（行为不变，既有测试覆盖）：

```python
def prompt_ids(prompt: str) -> list[str]:
    """Chunk ids in prompt order. Recording and replay must agree on this."""
    return _ID_LINE.findall(prompt)
```

```python
        ids = prompt_ids(prompt)
```

`scripts/record_method_descriptions.py` 重写为：

```python
"""Record L3 answers for the hold-out corpus (design §7.6).

Without `RESEARCHOS_LLM_API_KEY` this exits 2 and writes nothing: fabricated L3
data would be indistinguishable from measured data in the audit (known limit 17).

Recordings are keyed by `prompt_key` (the prompt without its per-run chunk ids)
and each point carries `prompt_index`, so a replay on a later run maps onto that
run's real chunk ids.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.llm.describer import SYSTEM_PROMPT, build_prompt
from research_os.llm.openai_compat import OpenAICompatibleProvider
from research_os.llm.recorded import prompt_ids, prompt_key
from research_os.llm.base import Message

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / ".holdout_cache"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/method_descriptions"


def plan_jobs(per_paper_chunks: list[list]) -> list[tuple[str, str]]:
    """(key, prompt) per paper. The key drops ids so it survives a new run."""
    return [(prompt_key(build_prompt(chunks)), build_prompt(chunks)) for chunks in per_paper_chunks]


def write_recording(out_dir: Path, key: str, payload: dict) -> Path:
    """Write once: a recording is a measurement, not a cache."""
    path = out_dir / f"{key}.json"
    if path.exists():
        return path
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def _record(provider, prompt: str) -> dict:
    response = await provider.generate(
        [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=prompt)]
    )
    # Same parser as the replay side: a chunk body line that happens to start
    # with "[chunk_" would otherwise shift every index by one and attach each
    # quote to the wrong chunk on the next run.
    ids = prompt_ids(prompt)
    points = []
    for point in response.points:
        index = ids.index(point.chunk_id) if point.chunk_id in ids else 0
        points.append(
            {
                "aspect": point.aspect,
                "statement": point.statement,
                "quote": point.quote,
                "prompt_index": index,
                "section": point.section,
            }
        )
    return {"points": points}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ids-file", type=Path, default=None)
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    if args.provider not in ("openai", "openai_compatible"):
        print(f"provider {args.provider!r} is not implemented; use 'openai'", file=sys.stderr)
        return 2
    api_key = os.environ.get("RESEARCHOS_LLM_API_KEY")
    if not api_key:
        print("RESEARCHOS_LLM_API_KEY is not set; refusing to fabricate recordings.", file=sys.stderr)
        return 2

    ids = [
        line.strip()
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if args.ids_file else sorted(path.stem for path in args.cache.glob("*.html"))
    if args.limit:
        ids = ids[: args.limit]

    provider = OpenAICompatibleProvider(
        base_url=os.environ.get("RESEARCHOS_LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=api_key,
        model=os.environ.get("RESEARCHOS_LLM_MODEL", "gpt-4o-mini"),
    )
    recorded = 0
    for arxiv_id in ids:
        path = args.cache / f"{arxiv_id}.html"
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            continue
        chunks = chunk_pages(load_html(path), f"sv_{arxiv_id}")
        key, prompt = plan_jobs([chunks])[0]
        if (args.out / f"{key}.json").exists():
            continue
        write_recording(args.out, key, asyncio.run(_record(provider, prompt)))
        recorded += 1
    print(f"recorded {recorded} of {len(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑绿 + 全量**

`tests/unit/test_record_script.py` 3 passed；全量 `428 passed, 2 skipped`。

- [ ] **Step 5: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/llm/recorded.py scripts/record_method_descriptions.py tests/unit/test_record_script.py
git commit -m "feat(scripts): make the L3 recorder usable, and still refuse to invent

Recordings are keyed by the id-free prompt and each point names its prompt
position, so a replay maps onto the next run's chunk ids. Without a key it exits
2 and writes nothing."
```

---

### Task 4: 文档与收尾

**Files:** `architect.md`（ADR-037、已知限制 17 改写、维护记录）、`README.md`（provider 一行）、`docs/handover/2026-11-15-method-acquisition-handover.md`（§0/§6/§9）、`docs/superpowers/plans/2026-11-15-l3-provider-client.md`（本计划本身，未跟踪；不提交它就做不到「工作区干净」）。

- [ ] **Step 1: ADR-037**

```markdown
| ADR-037 | L3 的 provider 走**一个** OpenAI 兼容客户端（`llm/openai_compat.py`），base_url/model/key 全走配置；JSON 模式、单次尝试、错误上抛 | 多 vendor 支持不该变成多客户端：同一份 JSON 契约下，换 vendor 只是换 base_url。不做重试，因为重试会花掉 supervisor 没计数的调用（设计 §7.3）；**不内置价格表**——价格是配置不是常量，`price_per_million` 未设时 `last_cost_usd` 保持 None，supervisor 就不回填成本，而不是按一个猜出来的单价收费 | ACTIVE |
```

- [ ] **Step 2: 已知限制 17 改写**

原文说「没有 provider 客户端」——现在有了，缺的是 key 与录制。改成：

```markdown
17. **L3 的覆盖在本仓库里仍是未测量状态**：客户端、录制脚本、回放与四道防线都已就绪，但 `tests/fixtures/method_descriptions/` 里一个录制文件都没有（目录本身也还不存在，第一次录制时才创建）——要动这一格，需要 `RESEARCHOS_LLM_API_KEY` 并跑一次 `scripts/record_method_descriptions.py`。在此之前审计报 `LLM 未启用`，不报一个没测过的数字；录制脚本无 key 时退出 2，拒绝伪造。
```

- [ ] **Step 3: README 一行**

在方法获取度量那段之后加：

```markdown
要测 L3 需先录制：`RESEARCHOS_LLM_API_KEY=... python scripts/record_method_descriptions.py --ids-file docs/evaluation/holdout-ids-2026-11-12.txt`，
然后 `python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json --describer recorded`。没有 key 时审计报 `LLM 未启用`。
```

（`--labels` 处不要留 `...`：README 里的命令要能整行复制。）

- [ ] **Step 4: 交接**

§0 提交数 `68 → 72` 与测试数 `418/420 → 428/430`、§6 基线证据块换成本轮实测、§9「后续待办」里 L3 那一条改成「只差 key + 一次录制」。

- [ ] **Step 5: 收尾**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_p4_final
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" --collect-only -q --basetemp=.pytest_tmp_p4_collect | tail -2
git status --short
```

预期：`2 skipped` + `428 passed`、`430 tests collected`；`git status --short` 只剩本计划文件一行 `??`（Task 4 的提交把它一起收进去，之后复查应为空）。

- [ ] **Step 6: 提交（不推送）**

```bash
cd /d/ResearchOS && git add architect.md README.md \
  docs/handover/2026-11-15-method-acquisition-handover.md \
  docs/superpowers/plans/2026-11-15-l3-provider-client.md
git commit -m "docs(arch): record the L3 provider client

ADR-037: one OpenAI-compatible client, JSON mode, no retries (they spend calls the
supervisor never counted), no cost estimate without a price table. Known limit 17
now says what is actually missing: a key and one recording run."
```

`git push` 由 owner 自己做，本计划不做推送。

---

## 验收

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | 无 key 时工厂明确报错 | `test_an_openai_compatible_provider_needs_a_key` |
| 2 | 客户端能解析 JSON 答案 | `test_a_json_answer_is_parsed_into_the_response_model`（MockTransport） |
| 3 | 失败不伪装成空答案 | 500 / 非 JSON / 超时三条都抛错 |
| 4 | 录制键与新 run 兼容 | `test_jobs_are_keyed_by_the_prompt_without_ids` |
| 5 | 无 key 不落任何文件 | `test_no_key_means_exit_2_and_no_files` |
| 6 | 既有用例一条不少 | 收集数 `430` |

## 明确不做

- 不录任何数据（没有 key）。
- 不改四道防线、`MethodPoint`、`identity_key`、矛盾级联。
- 不做重试/退避（属于预算语义，要单独设计）。
