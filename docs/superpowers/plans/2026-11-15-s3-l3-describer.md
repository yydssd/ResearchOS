# S3：L3 方法描述的 LLM 接线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `MethodProfile.points` 有生产者——用一次 LLM 调用把「这篇的方法讲了什么」写成**带原文定位的结构化要点**，并对四个失败路径各自留下可查的事件。**任何一条要点都必须能指回原文的某一句话**，否则宁可不收。

**Architecture:** LLM 只在 S3 出现，且只出现在一个地方：`MethodDescriber`（同步协议）。实现 `AsyncProviderDescriber` 把 `LLMProvider.generate`（async）包成同步调用，**禁止在事件循环里静默嵌套**。模型输出先落成 `MethodPointDraft`（宽松），再由 `validate_description` 过四道防线变成 `MethodPoint`（严格）——防线与 LLM 解耦，所以能用 fake 输出把每条失败路径测到。预算在 supervisor 里「先查后加」，因为当前 `budget.llm_calls` 全仓库没有写入点。

**Tech Stack:** Python 3.12 / Pydantic v2 / SQLAlchemy 2 / SQLite / pytest。解释器 `D:/Anaconda/envs/reOS/python.exe`。

**设计依据：** `docs/superpowers/specs/2026-11-15-method-acquisition-design.md` §7（全节）、§10.1（原因枚举）、§10.4（L3 用录制回放重跑）。
**回归基线：** `374 passed, 2 skipped / 376 collected`（S2 收官实测）。本计划只允许新增用例，不允许既有用例消失；每任务末尾的期望数字都以此递推。

**前置约束（写给执行者）：**
- 跑测试**必须** `-o addopts=""`，`--basetemp` 每次换新目录名。
- **不碰** `claims.py`、`contradiction.py`、`scope.py`、`conditions.py`；S3 不改 `identity_key`、不改主张数。
- **不改**审计脚本的 L3 判据语义（`bool(profile.points)`），只加「为什么是 0」的原因。
- 不引入新依赖：`asyncio` 是标准库；`httpx` 已装（provider 用）。
- S3 显式**不做**：真实 provider 实现（OpenAI/Anthropic 客户端）、`conditions` 新维度（S4）、域名词表。

---

## 文件结构

| 文件 | 责任 | 本计划改动 |
|---|---|---|
| `src/research_os/llm/base.py` | provider 协议 | 新增 `MethodPointDraft` / `MethodDescriptionResponse` / `DescriptionAttempt` / `LLMInEventLoopError` |
| `src/research_os/llm/describer.py` | **新建**：`MethodDescriber` 协议 + `AsyncProviderDescriber` + prompt 构造 | 新建 |
| `src/research_os/research/method_description.py` | **新建**：四道防线 `validate_description` | 新建 |
| `src/research_os/config.py` | 配置 | `llm_provider` / `llm_model` / `llm_api_key` |
| `src/research_os/orchestration/supervisor.py` | 编排 | 注入 describer；预算「先查后加」；调用 + 事件 + points 落库 |
| `src/research_os/domain/enums.py` | 枚举 | `FailureType` 加四项 |
| `src/research_os/cli.py` / `main.py` | 装配 | 按 `llm_provider` 构造 describer |
| `src/research_os/llm/recorded.py` | **新建**：录制回放 provider | 新建 |
| `scripts/record_method_descriptions.py` | **新建**：把真实响应录成夹具 | 新建 |
| `scripts/method_acquisition_audit.py` | 只读审计 | `--describer` 选项 + L3 原因 |
| `architect.md` / `docs/` | 文档 | ADR-035、已知限制、§13 偏差、报告、交接 |

---

### Task 1: 描述响应模型 + async 适配器

**Files:**
- Modify: `src/research_os/llm/base.py`
- Create: `src/research_os/llm/describer.py`
- Test: `tests/unit/test_method_describer.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_describer.py`：

```python
"""The sync face of an async provider (design §7.1).

The two things that matter: a call from inside a running event loop must raise a
typed error instead of nesting `asyncio.run` (which corrupts the loop or hangs),
and the response is parsed into the draft model so a bad aspect does not kill the
whole run - it becomes a rejected point with an event, one layer up.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from research_os.domain.models import DocumentChunk
from research_os.llm.base import LLMInEventLoopError, MethodDescriptionResponse, Message
from research_os.llm.describer import SYSTEM_PROMPT, AsyncProviderDescriber, build_prompt


def _chunk(text: str, *, section: str = "Method", index: int = 0) -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{index}", source_version_id="sv_1", section=section,
        chunk_index=index, text=text,
    )


class FakeProvider:
    """Async provider that records the messages it was given."""

    def __init__(self, response: BaseModel | None = None) -> None:
        self.calls = 0
        self.messages: list[Message] = []
        self._response = response or MethodDescriptionResponse(points=[])

    async def generate(self, messages, response_model=None):
        self.calls += 1
        self.messages = list(messages)
        return self._response


def test_describe_runs_the_async_provider_synchronously():
    provider = FakeProvider()
    describer = AsyncProviderDescriber(provider)

    attempt = describer.describe([_chunk("We propose LangProp.")])

    assert provider.calls == 1
    assert attempt.response is not None
    assert attempt.response.points == []
    assert attempt.error is None


def test_a_running_event_loop_is_refused_instead_of_nested():
    provider = FakeProvider()
    describer = AsyncProviderDescriber(provider)

    async def call_inside_loop():
        describer.describe([_chunk("We propose LangProp.")])

    with pytest.raises(LLMInEventLoopError):
        asyncio.run(call_inside_loop())
    assert provider.calls == 0


def test_the_prompt_carries_chunk_ids_and_their_text():
    """The model must answer with a `chunk_id` we can resolve; a prompt without
    ids produces quotes that cannot be located (design §7.4)."""
    chunks = [_chunk("We propose LangProp.", index=0), _chunk("It stores code.", index=1)]
    prompt = build_prompt(chunks)

    assert "chunk_0" in prompt
    assert "chunk_1" in prompt
    assert "We propose LangProp." in prompt
    # The enum lives in the system message; without it the model invents aspects
    # and every answer is rejected one layer up.
    assert "aspect" in SYSTEM_PROMPT


def test_the_prompt_is_bounded_even_on_a_long_paper():
    """A 40-page paper must not become a 200k-token request: the prompt keeps a
    fixed character budget and says so when it truncates."""
    chunks = [_chunk("x" * 5000, index=i) for i in range(30)]
    prompt = build_prompt(chunks)

    assert len(prompt) < 12000
    assert "truncated" in prompt.lower()


def test_a_provider_error_becomes_an_attempt_not_an_exception():
    """The supervisor must be able to log a typed event and carry on; an
    exception escaping here would kill the run at the first flaky response."""

    class BoomProvider:
        async def generate(self, messages, response_model=None):
            raise RuntimeError("upstream 500")

    attempt = AsyncProviderDescriber(BoomProvider()).describe([_chunk("We propose X.")])

    assert attempt.response is None
    assert attempt.error is not None
    assert "500" in attempt.error
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_describer.py -q --basetemp=.pytest_tmp_s3_t1_red
```

预期：`ImportError: cannot import name 'LLMInEventLoopError'`（模块与名字都还不存在）。

- [ ] **Step 3: 加模型与异常**

`src/research_os/llm/base.py`：在 `class LLMProvider(Protocol):` 之后追加：

```python
class LLMInEventLoopError(RuntimeError):
    """Raised when a sync describer is called from inside a running event loop.

    `asyncio.run` cannot be nested: it would either raise a confusing
    "loop already running" from deep inside the provider, or - worse - the caller
    would wrap it in its own loop and get a hang that looks like a slow model.
    A typed error at the boundary is the only version of this that can be logged.
    """


class MethodPointDraft(BaseModel):
    """One point as the model claims it, before any check.

    Deliberately loose: `aspect` is a plain string and the lengths are unchecked,
    so a malformed answer is *rejected with a reason* one layer up instead of
    raising inside the provider and losing the whole paper (design §7.4).
    """

    aspect: str = ""
    statement: str = ""
    quote: str = ""
    chunk_id: str = ""
    section: str | None = None


class MethodDescriptionResponse(BaseModel):
    """What a describer returns: points only, never a name or a setup.

    L1/L2/L4 are deterministic (S2); letting the model write a name here would
    put an unverified string into the field that attributes every quantitative
    row (ADR-034).
    """

    points: list[MethodPointDraft] = []


@dataclass(frozen=True)
class DescriptionAttempt:
    """One call's outcome, including the two facts the budget needs.

    `response is None` plus `error` means "the call happened and failed";
    `skipped` is not represented here - the supervisor decides that before
    calling, because only it owns the budget (design §7.3).
    """

    response: MethodDescriptionResponse | None
    cost_usd: float | None = None
    error: str | None = None
```

（`from dataclasses import dataclass` 加到文件顶部导入。）

- [ ] **Step 4: 写 `describer.py`**

`src/research_os/llm/describer.py`：

```python
"""Sync face for the L3 describer (design §7.1).

`LLMProvider.generate` is async; the vertical slice is sync. One adapter, one
rule: never nest an event loop. Everything else here is prompt construction,
which is deterministic on purpose - a prompt that changes between runs makes the
recorded fixtures (Task 6) unusable.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from research_os.domain.models import DocumentChunk
from research_os.llm.base import (
    DescriptionAttempt,
    LLMInEventLoopError,
    MethodDescriptionResponse,
    Message,
)

# Chunk text is the only evidence the model is allowed to quote, so the prompt
# budget is in characters of chunk text, not tokens: a token estimate would need
# a tokenizer that differs per provider.
_MAX_CHUNK_CHARS = 9000
_MAX_CHUNKS = 12
_ASPECTS = ("goal", "mechanism", "why_it_works", "io")

SYSTEM_PROMPT = """You extract what a paper says about its own method.

Answer with JSON only: {"points": [{"aspect": ..., "statement": ..., "quote": ...,
"chunk_id": ..., "section": ...}]}.

Rules, all mandatory:
- `quote` must be copied verbatim from the chunk named by `chunk_id`, at least 4
  words, and must appear exactly once in that chunk.
- `statement` must be a paraphrase of that quote in at most 200 characters, and
  it must reuse at least two content words from it.
- `aspect` is one of: goal, mechanism, why_it_works, io.
- Never write a method name, a dataset, a metric or a number here.
- If the chunks do not describe the method, answer {"points": []}.
"""


def _payload(chunks: list[DocumentChunk]) -> tuple[str, bool]:
    """(text, truncated) - method sections first, then everything else."""
    ordered = sorted(
        chunks,
        key=lambda chunk: (0 if "method" in (chunk.section or "").lower() else 1, chunk.chunk_index),
    )
    parts: list[str] = []
    used = 0
    truncated = False
    kept = 0
    for chunk in ordered:
        if kept >= _MAX_CHUNKS or used + len(chunk.text) > _MAX_CHUNK_CHARS:
            truncated = True
            break
        parts.append(f"[{chunk.id}] section={chunk.section or '-'}\n{chunk.text}")
        used += len(chunk.text)
        kept += 1
    if kept < len(ordered):
        truncated = True
    return "\n\n".join(parts), truncated


def build_prompt(chunks: list[DocumentChunk]) -> str:
    """The user message: every chunk line starts with its id.

    Ids are in the prompt because the response must name one; a quote without a
    resolvable id cannot be located and will be dropped as unlocatable.
    """
    body, truncated = _payload(chunks)
    notice = "\n\n[truncated: only the first chunks are shown]" if truncated else ""
    return f"{body}{notice}"


def _refuse_inside_loop() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise LLMInEventLoopError(
        "MethodDescriber.describe() was called from inside a running event loop; "
        "await the provider directly or run this pipeline in a worker thread."
    )


class MethodDescriber(Protocol):
    def describe(self, chunks: list[DocumentChunk]) -> DescriptionAttempt: ...


class AsyncProviderDescriber:
    """Adapts an async `LLMProvider` to the synchronous describer contract."""

    def __init__(self, provider, *, model: str | None = None) -> None:
        self._provider = provider
        self._model = model
        # Fail at construction too: a describer built inside a loop is a wiring
        # defect, and finding it at run start beats finding it mid-paper.
        _refuse_inside_loop()

    def describe(self, chunks: list[DocumentChunk]) -> DescriptionAttempt:
        _refuse_inside_loop()
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=build_prompt(chunks)),
        ]
        try:
            response = asyncio.run(
                self._provider.generate(messages, response_model=MethodDescriptionResponse)
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as an event, never swallowed
            return DescriptionAttempt(response=None, error=f"{type(exc).__name__}: {exc}")
        if not isinstance(response, MethodDescriptionResponse):
            # A provider that ignores `response_model` must not smuggle a dict in.
            try:
                response = MethodDescriptionResponse.model_validate(response)
            except Exception as exc:  # noqa: BLE001
                return DescriptionAttempt(response=None, error=f"schema: {exc}")
        cost = getattr(self._provider, "last_cost_usd", None)
        return DescriptionAttempt(response=response, cost_usd=cost)
```

- [ ] **Step 5: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_describer.py -v --basetemp=.pytest_tmp_s3_t1_green
```

预期：5 passed。

- [ ] **Step 6: 全量**

预期：`379 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/llm/base.py src/research_os/llm/describer.py \
        tests/unit/test_method_describer.py
git commit -m "feat(llm): adapt the async provider to a sync method describer

One adapter, one rule: never nest an event loop. A call from inside a loop raises
a typed error at the boundary, because the alternative is a hang that looks like
a slow model. Provider failures become attempts so the supervisor can log them."
```

---

### Task 2: 四道防线

**Files:**
- Create: `src/research_os/research/method_description.py`
- Test: `tests/unit/test_method_description.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_method_description.py`：

```python
"""The four defences (design §7.4).

Every path below is a way a plausible-looking model answer must be refused. The
distinction that matters: a *bad point* is dropped and the rest survives, a
*broken schema* rejects the whole answer - half a description is still useful,
half a quote is not.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.llm.base import MethodDescriptionResponse, MethodPointDraft
from research_os.research.method_description import validate_description

CHUNK_TEXT = (
    "LangProp turns a language model's proposals into executable policies. "
    "Our method stores each policy as code and scores it by execution feedback. "
    "The gating mechanism decides which programs are reused."
)
CHUNKS = [
    DocumentChunk(id="chunk_0", source_version_id="sv_1", section="Method", chunk_index=0, text=CHUNK_TEXT)
]
GOOD_QUOTE = "Our method stores each policy as code"


def _draft(**overrides) -> MethodPointDraft:
    data = dict(
        aspect="mechanism",
        statement="Stores each policy as code for later reuse.",
        quote=GOOD_QUOTE,
        chunk_id="chunk_0",
        section="Method",
    )
    data.update(overrides)
    return MethodPointDraft(**data)


def _validate(*drafts: MethodPointDraft):
    return validate_description(MethodDescriptionResponse(points=list(drafts)), CHUNKS)


def test_a_locating_point_is_kept():
    outcome = _validate(_draft())

    assert outcome.reason is None
    assert len(outcome.points) == 1
    assert outcome.points[0].aspect == "mechanism"
    assert outcome.points[0].chunk_id == "chunk_0"


def test_a_quote_not_in_its_chunk_is_dropped():
    """The whole point of the layer: a statement without a source location is a
    summary, and plan §7.4 forbids storing those."""
    outcome = _validate(_draft(quote="Policies are compiled into a graph of skills"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_a_short_quote_is_dropped():
    """`quote="attention"` would "locate" itself everywhere; four words is the
    smallest quote that still identifies one sentence."""
    outcome = _validate(_draft(quote="Our method"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_a_quote_that_appears_twice_is_dropped():
    """Non-unique quotes do not locate: the reader cannot tell which occurrence
    the statement came from."""
    repeated = [
        DocumentChunk(
            id="chunk_0", source_version_id="sv_1", section="Method", chunk_index=0,
            text="The gating mechanism is reused. The gating mechanism is reused again.",
        )
    ]
    outcome = validate_description(
        MethodDescriptionResponse(points=[_draft(quote="The gating mechanism is reused")]), repeated
    )

    assert outcome.points == []
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_a_statement_with_no_word_from_its_quote_is_dropped():
    """Formally fine, substantively invented: a real quote with a statement
    about something else is the failure `METHOD_STATEMENT_UNSUPPORTED` names."""
    outcome = _validate(
        _draft(
            quote=GOOD_QUOTE,
            statement="The model is trained with a contrastive objective on video.",
        )
    )

    assert outcome.points == []
    assert outcome.reason == "METHOD_STATEMENT_UNSUPPORTED"


def test_a_broken_schema_rejects_every_point():
    """An out-of-enum aspect means the model did not follow the contract; keeping
    its other points would be trusting an answer we know is malformed."""
    outcome = _validate(_draft(), _draft(aspect="vibes"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_DESCRIPTION_REJECTED"


def test_a_chunk_id_outside_the_input_is_a_rejection():
    outcome = _validate(_draft(chunk_id="chunk_999"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_DESCRIPTION_REJECTED"


def test_one_bad_point_does_not_discard_the_good_one():
    outcome = _validate(_draft(), _draft(quote="This sentence is not in the chunk at all"))

    assert len(outcome.points) == 1
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_description.py -q --basetemp=.pytest_tmp_s3_t2_red
```

预期：`ModuleNotFoundError: No module named 'research_os.research.method_description'`。

- [ ] **Step 3: 实现**

`src/research_os/research/method_description.py`：

```python
"""Validate what the describer wrote (design §7.4).

Four defences, in this order, because they have different blast radii:

1. schema (aspect / lengths / chunk id)  -> reject the whole answer
2. quote locates (verbatim, >=4 words, unique in its chunk) -> drop the point
3. statement is supported by the quote (>=2 content words shared) -> drop the point
4. no describer / over budget is decided by the caller (it owns the budget)

The split exists so that one bad point costs one point, while a malformed answer
costs the paper: keeping points from a response we know broke its contract would
be trusting the part we cannot check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from research_os.domain.models import DocumentChunk, MethodPoint
from research_os.llm.base import MethodDescriptionResponse

_ASPECTS = frozenset({"goal", "mechanism", "why_it_works", "io"})
_MAX_STATEMENT = 200
_MIN_QUOTE_WORDS = 4
_MIN_SHARED_WORDS = 2

# Words that carry no claim; a statement "supported" only by these is supported
# by grammar, not by the quote.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
        "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
        "these", "those", "we", "our", "as", "at", "from", "which", "each", "than",
        "then", "not", "no", "can", "may", "uses", "use", "using", "via",
    }
)
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class DescriptionOutcome:
    """Validated points plus the one reason worth logging when none survived."""

    points: list[MethodPoint]
    reason: str | None = None


def _content_words(text: str) -> set[str]:
    return {
        word
        for word in _WORD.findall(text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    }


def _locates(quote: str, chunk_text: str) -> bool:
    """Verbatim, at least four words, and unique inside the chunk."""
    collapsed = " ".join(quote.split())
    if len(collapsed.split()) < _MIN_QUOTE_WORDS:
        return False
    if collapsed not in " ".join(chunk_text.split()):
        return False
    return chunk_text.count(collapsed) == 1


def validate_description(
    response: MethodDescriptionResponse, chunks: list[DocumentChunk]
) -> DescriptionOutcome:
    by_id = {chunk.id: chunk for chunk in chunks}
    sections = {chunk.id: chunk.section for chunk in chunks}

    # Defence 1: the contract itself. One violation rejects the answer.
    for draft in response.points:
        if draft.aspect not in _ASPECTS:
            return DescriptionOutcome([], "METHOD_DESCRIPTION_REJECTED")
        if not draft.statement.strip() or len(draft.statement) > _MAX_STATEMENT:
            return DescriptionOutcome([], "METHOD_DESCRIPTION_REJECTED")
        if draft.chunk_id not in by_id:
            return DescriptionOutcome([], "METHOD_DESCRIPTION_REJECTED")

    points: list[MethodPoint] = []
    reason: str | None = None
    for draft in response.points:
        chunk = by_id[draft.chunk_id]
        # Defence 2: it has to be findable again.
        if not _locates(draft.quote, chunk.text):
            reason = reason or "METHOD_POINT_UNLOCATABLE"
            continue
        # Defence 3: the statement has to be about the quote, not merely
        # accompanied by it.
        shared = _content_words(draft.statement) & _content_words(draft.quote)
        if len(shared) < _MIN_SHARED_WORDS:
            reason = reason or "METHOD_STATEMENT_UNSUPPORTED"
            continue
        points.append(
            MethodPoint(
                aspect=draft.aspect,
                statement=" ".join(draft.statement.split()),
                quote=" ".join(draft.quote.split()),
                chunk_id=draft.chunk_id,
                section=draft.section or sections.get(draft.chunk_id),
            )
        )
    return DescriptionOutcome(points, reason if not points else reason)
```

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_description.py -v --basetemp=.pytest_tmp_s3_t2_green
```

预期：8 passed。若 `test_a_quote_that_appears_twice_is_dropped` 红：确认 `chunk_text.count(collapsed)` 用的是**原始文本**而不是折叠后的（重复句在折叠后仍重复，两者都该判 2）。

- [ ] **Step 5: 全量**

预期：`387 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/research/method_description.py tests/unit/test_method_description.py
git commit -m "feat(methods): validate the model's points before they are stored

A quote must locate itself (verbatim, four words, unique) and the statement must
share two content words with it - otherwise the row is a summary with no source,
which plan §7.4 forbids. A malformed answer rejects the paper; a bad point costs
one point."
```

---

### Task 3: 配置与装配

**Files:**
- Modify: `src/research_os/config.py`
- Create: `src/research_os/llm/factory.py`
- Modify: `src/research_os/cli.py` / `src/research_os/main.py`
- Test: `tests/unit/test_llm_config.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_llm_config.py`：

```python
"""Wiring by configuration, not by import side effects (design §7.2).

`UnavailableProvider` was never instantiated anywhere; the honest default is "no
describer at all", so a run with no key does zero calls and says so.
"""

from __future__ import annotations

from research_os.config import Settings
from research_os.llm.describer import AsyncProviderDescriber
from research_os.llm.factory import build_describer


def test_no_provider_means_no_describer():
    settings = Settings(llm_provider="none")
    assert build_describer(settings) is None


def test_an_unknown_provider_name_is_a_configuration_error():
    settings = Settings(llm_provider="openai")
    try:
        build_describer(settings)
    except ValueError as exc:
        assert "llm_provider" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("an unimplemented provider name must not build silently")


def test_the_recorded_provider_builds_a_describer():
    settings = Settings(llm_provider="recorded", llm_fixture_dir="tests/fixtures/method_descriptions")
    describer = build_describer(settings)
    assert isinstance(describer, AsyncProviderDescriber)
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_llm_config.py -q --basetemp=.pytest_tmp_s3_t3_red
```

预期：`ImportError: cannot import name 'build_describer'`。

- [ ] **Step 3: 加配置**

`src/research_os/config.py`，在 `search_providers` 之后加：

```python
    # L3 describer (design §7.2). `none` means no describer is assembled at all -
    # not "assembled but broken" - so a run without a key does zero LLM calls and
    # reports L3 as "LLM 未启用" instead of an extraction failure.
    llm_provider: str = "none"  # none | recorded | <provider name>
    llm_model: str | None = None
    llm_api_key: str | None = None
    # Replay directory for `llm_provider="recorded"` (design §7.6).
    llm_fixture_dir: str = "tests/fixtures/method_descriptions"
```

- [ ] **Step 4: 加工厂**

`src/research_os/llm/factory.py`：

```python
"""Assemble one describer from settings (design §7.2).

Only `recorded` is implemented: a real provider needs a client library and a key,
and neither is in scope for S3. Naming an unimplemented provider is a
configuration error rather than a silent fallback, because "I configured OpenAI
and got heuristics" is the kind of quiet failure this project keeps paying for.
"""

from __future__ import annotations

from research_os.config import Settings
from research_os.llm.describer import AsyncProviderDescriber, MethodDescriber
from research_os.llm.recorded import RecordedProvider


def build_describer(settings: Settings) -> MethodDescriber | None:
    name = (settings.llm_provider or "none").strip().lower()
    if name in ("", "none"):
        return None
    if name == "recorded":
        provider = RecordedProvider(settings.llm_fixture_dir)
        return AsyncProviderDescriber(provider, model=settings.llm_model)
    raise ValueError(
        f"llm_provider={settings.llm_provider!r} is not implemented; "
        "use 'none' or 'recorded'"
    )
```

- [ ] **Step 5: 装配点**

`src/research_os/cli.py` 的 `_cmd_run`：`supervisor = Supervisor(session)` 改成

```python
        supervisor = Supervisor(session, method_describer=build_describer(settings))
```

并在导入块加 `from research_os.config import settings` 与 `from research_os.llm.factory import build_describer`。

`src/research_os/main.py` 同样改（该方法内已有 session）：

```python
        supervisor = Supervisor(session, method_describer=build_describer(settings))
```

导入同上。

> 说明：Task 3 先让 `build_describer` 能返回 `None` 或 recorded，`Supervisor` 的 `method_describer` 参数在 Task 5 才加。测试只覆盖工厂，所以本任务全量仍是绿的；`cli/main` 的改动在 Task 5 之后才真正生效——**顺序不要调**，否则 `_cmd_run` 会在导入期就引用不存在的参数。

- [ ] **Step 6: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_llm_config.py -v --basetemp=.pytest_tmp_s3_t3_green
```

预期：3 passed。若 `test_the_recorded_provider_builds_a_describer` 红：`recorded.py` 在 Task 6 才建，先建一个空的 `RecordedProvider` 骨架（构造函数收目录、`generate` 返回空 `MethodDescriptionResponse`），Task 6 再补回放逻辑。

- [ ] **Step 7: 全量**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  -q --basetemp=.pytest_tmp_s3_t3_all
```

预期：`390 passed, 2 skipped`。

- [ ] **Step 8: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/config.py src/research_os/llm/factory.py \
        src/research_os/llm/recorded.py tests/unit/test_llm_config.py
git commit -m "feat(llm): assemble the describer from configuration

'none' means no describer at all, so a keyless run does zero calls and reports L3
as not-enabled instead of as an extraction failure. An unimplemented provider name
raises instead of falling back to heuristics."
```

---

### Task 4: 预算「先查后加」

**Files:**
- Modify: `src/research_os/orchestration/supervisor.py`
- Modify: `src/research_os/domain/enums.py`（`FailureType` 四项）
- Test: `tests/unit/test_llm_budget.py`（新建）

- [ ] **Step 1: 写会失败的测试**

新建 `tests/unit/test_llm_budget.py`：

```python
"""Budget accounting for L3 (design §7.3).

`budget.llm_calls` had no writer anywhere in the repo, so `exceeded()` could never
be true for LLM calls: the 80-call ceiling was decoration. These tests pin the
counter and the "check before, add after" order that avoids the 80/81 off-by-one.
"""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import EventType, FailureType
from research_os.domain.models import MethodDescriptionResponse
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlEventRepository,
    SqlMethodProfileRepository,
    SqlRunRepository,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class CountingDescriber:
    """Sync describer that answers with one well-formed point and counts calls."""

    def __init__(self, quote: str) -> None:
        self.calls = 0
        self._quote = quote

    def describe(self, chunks):
        from research_os.llm.base import DescriptionAttempt, MethodPointDraft

        self.calls += 1
        return DescriptionAttempt(
            response=MethodDescriptionResponse(
                points=[
                    MethodPointDraft(
                        aspect="mechanism",
                        statement="Stores each policy as code.",
                        quote=self._quote,
                        chunk_id=chunks[0].id,
                        section=chunks[0].section,
                    )
                ]
            )
        )


def _run(tmp_path, describer, max_llm_calls: int, papers: int = 1) -> tuple[str, int]:
    sources = [(str(FIXTURES / "named_paper.md"), f"p{i}", "markdown") for i in range(papers)]
    with session_scope() as session:
        supervisor = Supervisor(session, method_describer=describer)
        run = supervisor.create_run(question_text="Does reuse help?", domain=None)
        run.budget.max_llm_calls = max_llm_calls
        SqlRunRepository(session).update(run)
        supervisor.run_vertical_slice(run_id=run.id, sources=sources, reports_dir=tmp_path)
        stored = SqlRunRepository(session).get(run.id)
        return run.id, stored.budget.llm_calls


def test_a_zero_budget_makes_no_call_and_says_why(db, tmp_path):
    describer = CountingDescriber("LangProp, our proposed method, stores each policy as code")

    run_id, calls = _run(tmp_path, describer, max_llm_calls=0)

    assert calls == 0
    assert describer.calls == 0
    with session_scope() as session:
        events = [
            event
            for event in SqlEventRepository(session).list_by_run(run_id)
            if event.event_type == EventType.FAILURE
            and event.failure_type == FailureType.METHOD_DESCRIPTION_SKIPPED
        ]
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert len(events) == 1
    assert "L3" in profile.missing_layers


def test_the_call_is_counted_after_it_happens(db, tmp_path):
    describer = CountingDescriber("LangProp, our proposed method, stores each policy as code")

    _run_id, calls = _run(tmp_path, describer, max_llm_calls=5)

    assert describer.calls == 1
    assert calls == 1


def test_exactly_two_calls_for_three_papers_and_the_third_is_logged(db, tmp_path):
    describer = CountingDescriber("LangProp, our proposed method, stores each policy as code")

    run_id, calls = _run(tmp_path, describer, max_llm_calls=2, papers=3)

    assert describer.calls == 2
    assert calls == 2
    with session_scope() as session:
        skipped = [
            event
            for event in SqlEventRepository(session).list_by_run(run_id)
            if event.failure_type == FailureType.METHOD_DESCRIPTION_SKIPPED
        ]
    assert len(skipped) == 1


def test_a_cost_bearing_provider_accumulates_the_cost(db, tmp_path):
    """A provider that reports usage must move `cost_usd`; one that does not must
    leave it alone rather than invent a number."""

    class Costly(CountingDescriber):
        def describe(self, chunks):
            from research_os.llm.base import DescriptionAttempt

            attempt = super().describe(chunks)
            return DescriptionAttempt(response=attempt.response, cost_usd=0.25)

    describer = Costly("LangProp, our proposed method, stores each policy as code")
    _run_id, _calls = _run(tmp_path, describer, max_llm_calls=5)

    with session_scope() as session:
        stored = SqlRunRepository(session).get(_run_id)
    assert stored.budget.cost_usd == 0.25
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_llm_budget.py -q --basetemp=.pytest_tmp_s3_t4_red
```

预期：`TypeError: Supervisor.__init__() got an unexpected keyword argument 'method_describer'`。

- [ ] **Step 3: 加 `FailureType`**

`src/research_os/domain/enums.py` 的 `FailureType` 末尾加：

```python
    # L3 (design §7.5). All four are failures in the sense that a paper that
    # should have a description did not get one; the message and payload say
    # which step refused it.
    METHOD_POINT_UNLOCATABLE = "METHOD_POINT_UNLOCATABLE"
    METHOD_STATEMENT_UNSUPPORTED = "METHOD_STATEMENT_UNSUPPORTED"
    METHOD_DESCRIPTION_REJECTED = "METHOD_DESCRIPTION_REJECTED"
    METHOD_DESCRIPTION_SKIPPED = "METHOD_DESCRIPTION_SKIPPED"
```

- [ ] **Step 4: 加预算与调用**

`src/research_os/orchestration/supervisor.py`：

构造函数加参数（放在 `method_extractor` 之后）：

```python
        method_describer: "MethodDescriber | None" = None,
```

并保存：

```python
        self._describer = method_describer
```

加两个私有方法（放在 `_check_budget` 之后）：

```python
    def _llm_budget_exhausted(self, run: ResearchRun) -> bool:
        """Check only: the caller adds after the call returns (design §7.3).

        `>=` rather than `>` so a budget of 0 means zero calls, and so 80 means 80.
        Adding first and checking after is how 81-call runs happen.
        """
        budget = self._budget(run)
        return budget.llm_calls >= budget.max_llm_calls or budget.cost_usd >= budget.max_cost_usd

    def _spend_llm(self, run: ResearchRun, cost_usd: float | None) -> None:
        """Count the call, and the cost when the provider reported one.

        A missing cost stays missing: inventing a number would make the ceiling
        depend on a guess.
        """
        run.budget.llm_calls += 1
        if cost_usd is not None:
            run.budget.cost_usd = round(run.budget.cost_usd + cost_usd, 6)
        SqlRunRepository(self._session).update(run)
```

在 3) 方法档案那一步之后（`complete_task(method_task, ...)` 之后）插入 3c：

```python
        # 3c) L3: one description call per paper, through the four defences
        # (design §7.4). The budget is checked before the call and counted after,
        # so a ceiling of N means N calls.
        if self._describer is not None:
            profiles = SqlMethodProfileRepository(self._session).list_by_run(run.id)
            by_source: dict[str, list] = {}
            for chunk in all_chunks:
                by_source.setdefault(chunk.source_version_id, []).append(chunk)
            for profile in profiles:
                if self._llm_budget_exhausted(run):
                    self._log(
                        run.id,
                        EventType.FAILURE,
                        "L3 description skipped: LLM budget exhausted",
                        {"source_version_id": profile.source_version_id,
                         "llm_calls": run.budget.llm_calls,
                         "max_llm_calls": run.budget.max_llm_calls},
                        failure_type=FailureType.METHOD_DESCRIPTION_SKIPPED,
                    )
                    continue
                attempt = self._describer.describe(by_source.get(profile.source_version_id, []))
                self._spend_llm(run, attempt.cost_usd)
                if attempt.response is None:
                    self._log(
                        run.id,
                        EventType.FAILURE,
                        f"L3 description failed: {attempt.error}",
                        {"source_version_id": profile.source_version_id},
                        failure_type=FailureType.METHOD_DESCRIPTION_REJECTED,
                    )
                    continue
                outcome = validate_description(attempt.response, by_source.get(profile.source_version_id, []))
                if outcome.reason:
                    self._log(
                        run.id,
                        EventType.FAILURE,
                        f"L3 description partially refused: {outcome.reason}",
                        {"source_version_id": profile.source_version_id,
                         "kept": len(outcome.points),
                         "reason": outcome.reason},
                        failure_type=FailureType(outcome.reason),
                    )
                if outcome.points:
                    profile.points = outcome.points
                    SqlMethodProfileRepository(self._session).upsert(profile, run.id)
```

导入：`from research_os.research.method_description import validate_description`，以及 `from research_os.llm.describer import MethodDescriber`（放进既有 llm 导入或新增一行）。

> `FailureType(outcome.reason)` 依赖 `reason` 与枚举名一致（`METHOD_POINT_UNLOCATABLE` / `METHOD_STATEMENT_UNSUPPORTED` / `METHOD_DESCRIPTION_REJECTED`），这是 Task 2 的字符串契约，改一边必须改另一边。

- [ ] **Step 5: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_llm_budget.py -v --basetemp=.pytest_tmp_s3_t4_green
```

预期：4 passed。

- [ ] **Step 6: 全量**

预期：`394 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/domain/enums.py src/research_os/orchestration/supervisor.py \
        tests/unit/test_llm_budget.py
git commit -m "feat(run): count LLM calls and stop at the ceiling

budget.llm_calls had no writer, so the 80-call ceiling could never be reached.
The check runs before the call and the increment after it, which is what keeps
'budget 2' meaning two calls instead of three."
```

---

### Task 5: 接线完成（描述 → 落库 → memo）

**Files:**
- Modify: `src/research_os/orchestration/supervisor.py`（若 Task 4 已含则跳过）
- Test: `tests/integration/test_method_description_run.py`（新建）

- [ ] **Step 1: 写会失败的测试**

```python
"""L3 end to end (design §7.4/§6.6): points land in the database and the memo
shows them with their section."""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import EventType, FailureType
from research_os.llm.base import DescriptionAttempt, MethodDescriptionResponse, MethodPointDraft
from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlEventRepository, SqlMethodProfileRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
QUOTE = "LangProp, our proposed method, stores each policy as code"


class QuoteDescriber:
    def __init__(self, quote: str = QUOTE, aspect: str = "mechanism") -> None:
        self._quote = quote
        self._aspect = aspect

    def describe(self, chunks):
        return DescriptionAttempt(
            response=MethodDescriptionResponse(
                points=[
                    MethodPointDraft(
                        aspect=self._aspect,
                        statement="Each policy is stored as code and scored.",
                        quote=self._quote,
                        chunk_id=chunks[0].id,
                        section=chunks[0].section,
                    )
                ]
            )
        )


def _run(tmp_path, describer):
    with session_scope() as session:
        supervisor = Supervisor(session, method_describer=describer)
        run = supervisor.create_run(question_text="Does reuse help?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "named_paper.md"), "named", "markdown")],
            reports_dir=tmp_path,
        )
        return run.id


def test_points_are_persisted_and_leave_missing_layers(db, tmp_path):
    run_id = _run(tmp_path, QuoteDescriber())

    with session_scope() as session:
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert [point.aspect for point in profile.points] == ["mechanism"]
    assert profile.points[0].chunk_id
    assert "L3" not in profile.missing_layers


def test_the_memo_prints_the_point_with_its_section(db, tmp_path):
    run_id = _run(tmp_path, QuoteDescriber())

    with session_scope() as session:
        memo = build_memo_from_run(session, run_id) or ""

    section = memo.split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "mechanism" in section
    assert "Each policy is stored as code" in section


def test_an_unlocatable_quote_is_logged_and_nothing_is_stored(db, tmp_path):
    run_id = _run(tmp_path, QuoteDescriber(quote="This sentence is nowhere in the paper"))

    with session_scope() as session:
        events = [
            event for event in SqlEventRepository(session).list_by_run(run_id)
            if event.failure_type == FailureType.METHOD_POINT_UNLOCATABLE
        ]
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert len(events) == 1
    assert events[0].payload["kept"] == 0
    assert profile.points == []
    assert "L3" in profile.missing_layers


def test_no_describer_leaves_l3_missing_without_any_event(db, tmp_path):
    """A run with no key must not pretend a call was attempted."""
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Does reuse help?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "named_paper.md"), "named", "markdown")],
            reports_dir=tmp_path,
        )
        events = [
            event for event in SqlEventRepository(session).list_by_run(run.id)
            if event.failure_type in {
                FailureType.METHOD_DESCRIPTION_SKIPPED,
                FailureType.METHOD_DESCRIPTION_REJECTED,
                FailureType.METHOD_POINT_UNLOCATABLE,
                FailureType.METHOD_STATEMENT_UNSUPPORTED,
            }
        ]
        profile = SqlMethodProfileRepository(session).list_by_run(run.id)[0]

    assert events == []
    assert "L3" in profile.missing_layers
```

- [ ] **Step 2: 运行，确认失败**

预期：4 条中至少 3 条红（`points == []`、`L3` 仍在）；若 Task 4 已把 3c 写完，则红在 memo 断言与 missing_layers 断言。

- [ ] **Step 3: 补齐**

- 若 Task 4 的 3c 已写入，本任务只需确认 `profile.missing_layers` 在 points 落地后去掉 `L3`：在 3c 的 `profile.points = outcome.points` 之后加

```python
                    profile.missing_layers = [layer for layer in profile.missing_layers if layer != "L3"]
```

- `reporting/memo.py` 的 `_render_methods_section` 已支持 `profile.points`（S2 写的），无需改；只确认 `point.aspect` 与 `point.section` 都被打印（`- {aspect}: {statement} _[{section}]_`）。

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/integration/test_method_description_run.py -v --basetemp=.pytest_tmp_s3_t5_green
```

预期：4 passed。

- [ ] **Step 5: 全量**

预期：`398 passed, 2 skipped`。

- [ ] **Step 6: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/orchestration/supervisor.py \
        tests/integration/test_method_description_run.py
git commit -m "feat(run): store validated L3 points and clear them from missing_layers

A point that passes the four defences is a locatable statement, so L3 stops being
'missing' for that paper; a refused point leaves the layer missing and says why."
```

---

### Task 6: 录制回放 provider + 录制脚本

**Files:**
- Modify: `src/research_os/llm/recorded.py`
- Create: `scripts/record_method_descriptions.py`
- Test: `tests/unit/test_recorded_provider.py`（新建）

- [ ] **Step 1: 写会失败的测试**

```python
"""Replay recorded L3 answers (design §7.6, ADR-010's pattern).

The point is reproducibility, not convenience: the same fixtures must give the
same audit numbers on a machine with no key and no network.
"""

from __future__ import annotations

import asyncio
import json

from research_os.llm.base import MethodDescriptionResponse
from research_os.llm.recorded import RecordedProvider


def _messages(text: str):
    from research_os.llm.base import Message

    return [Message(role="system", content="s"), Message(role="user", content=text)]


def test_a_recorded_answer_is_replayed_for_its_chunk_id(tmp_path):
    (tmp_path / "chunk_0.json").write_text(
        json.dumps(
            {
                "points": [
                    {
                        "aspect": "goal",
                        "statement": "Restore all degradations with one model.",
                        "quote": "All-in-one image restoration aims to handle multiple degradations",
                        "chunk_id": "chunk_0",
                        "section": "Abstract",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages("[chunk_0] section=Abstract\nAll-in-one ...")))

    assert isinstance(response, MethodDescriptionResponse)
    assert response.points[0].chunk_id == "chunk_0"


def test_a_missing_recording_is_an_empty_answer_not_a_crash(tmp_path):
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages("[chunk_9] section=Method\nnope")))

    assert response.points == []


def test_the_recording_is_keyed_by_the_first_chunk_id_in_the_prompt(tmp_path):
    """The key has to come from the prompt itself: the provider sees messages, not
    a source id, and inventing one would make the fixtures unreadable."""
    (tmp_path / "chunk_a.json").write_text(json.dumps({"points": []}), encoding="utf-8")
    provider = RecordedProvider(tmp_path)

    response = asyncio.run(provider.generate(_messages("[chunk_a] section=Method\nx")))

    assert response.points == []
```

- [ ] **Step 2: 运行，确认失败**

预期：`ImportError`（`recorded.py` 还没有回放逻辑）。

- [ ] **Step 3: 实现回放**

`src/research_os/llm/recorded.py`：

```python
"""Replay recorded L3 answers from disk (design §7.6).

The key is the first `[chunk_id]` in the user message: the provider only sees
messages, and the chunk id is already in the prompt for the model's benefit, so
using it again costs nothing and invents no identifier.

A missing recording answers `points: []`. That is the honest reading: the model
was not asked, so it described nothing. The audit turns an all-empty replay into
"no recording" (Task 7) instead of reporting a coverage number it did not measure.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_os.llm.base import MethodDescriptionResponse, Message

_CHUNK_MARK = "[chunk"


class RecordedProvider:
    """Reads `{chunk_id}.json` from a fixture directory; never touches the network."""

    def __init__(self, fixture_dir: str | Path) -> None:
        self._dir = Path(fixture_dir)
        self.last_cost_usd: float | None = None

    async def generate(self, messages: list[Message], response_model=None):
        prompt = messages[-1].content if messages else ""
        key = self._key(prompt)
        if key is None:
            return MethodDescriptionResponse(points=[])
        path = self._dir / f"{key}.json"
        if not path.exists():
            return MethodDescriptionResponse(points=[])
        return MethodDescriptionResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def _key(self, prompt: str) -> str | None:
        start = prompt.find(_CHUNK_MARK)
        if start < 0:
            return None
        end = prompt.find("]", start)
        if end < 0:
            return None
        return prompt[start + 1 : end]
```

- [ ] **Step 4: 录制脚本**

`scripts/record_method_descriptions.py`：

```python
"""Record L3 answers for the hold-out corpus (design §7.6).

Requires a real provider, which S3 does not ship: this script exists so the
recording is a repeatable command rather than a manual step, and so the replay
path has an obvious place to get its data. Without a key it exits 2 and records
nothing - it must never fabricate answers, since fabricated L3 data would look
exactly like measured L3 data in the audit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.llm.describer import build_prompt
from research_os.research.patterns import EVAL_PROTOCOL  # noqa: F401  (import cost check)

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / ".holdout_cache"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/method_descriptions"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--provider", required=True, help="provider name to record with")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    print(
        "No provider client is shipped in S3; implement one and pass it here. "
        "Refusing to fabricate recordings.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_recorded_provider.py -v --basetemp=.pytest_tmp_s3_t6_green
```

预期：3 passed。

- [ ] **Step 6: 全量**

预期：`401 passed, 2 skipped`。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add src/research_os/llm/recorded.py scripts/record_method_descriptions.py \
        tests/unit/test_recorded_provider.py
git commit -m "feat(llm): replay recorded L3 answers, and refuse to invent them

The replay key is the chunk id already in the prompt, so no new identifier is
invented. The record script exits non-zero without a provider: fabricated L3 data
would be indistinguishable from measured L3 data in the audit."
```

---

### Task 7: 审计 —— L3 的原因与重跑

**Files:**
- Modify: `scripts/method_acquisition_audit.py`
- Test: `tests/unit/test_method_acquisition_audit.py`（追加 2 条）

- [ ] **Step 1: 写会失败的测试**

在 `tests/unit/test_method_acquisition_audit.py` 末尾追加：

```python
def test_l3_cause_says_whether_a_describer_was_configured():
    """0/20 for L3 has two very different meanings: "nothing can fill this layer"
    and "nobody asked". After S3 the field exists, so the audit must say which."""
    side = {**SIDES["a1"], "L3_cause": "LLM 未启用"}

    assert cause_for("L3", side) == "LLM 未启用"
    # No hint at all keeps the S2 behaviour for the synthetic fixtures above.
    assert cause_for("L3", SIDES["a1"]) == "无结构化字段"


def test_system_side_reports_an_l3_cause_without_a_describer():
    from scripts.method_acquisition_audit import system_side

    side = system_side("2311.15209")  # cached, has a method section

    assert side["L3"] is False
    assert side["L3_cause"] == "LLM 未启用"
```

- [ ] **Step 2: 运行，确认失败**

预期：`KeyError: 'L3_cause'` 或断言失败。

- [ ] **Step 3: 改审计**

`scripts/method_acquisition_audit.py`：

`cause_for` 的 L3 分支改为：

```python
    if layer == "L3":
        # A hint from the observation wins: after S3 "no field" and "no describer"
        # are different causes, and only the run knows which one it is.
        return side.get("L3_cause") or "无结构化字段"
```

`system_side` 加一个参数与一个键：

```python
def system_side(arxiv_id: str, cache: Path = CACHE, describer=None) -> dict:
```

返回字典里加：

```python
        "L3_cause": (
            None
            if (profile and profile.points)
            else ("LLM 未启用" if describer is None else "无结构化字段")
        ),
```

并在 `main()` 里加：

```python
    parser.add_argument(
        "--describer",
        choices=("none", "recorded"),
        default="none",
        help="recorded replays tests/fixtures/method_descriptions (design §7.6)",
    )
```

`main()` 构造 describer：

```python
    describer = None
    if args.describer == "recorded":
        from research_os.config import Settings
        from research_os.llm.factory import build_describer

        describer = build_describer(
            Settings(llm_provider="recorded", llm_fixture_dir="tests/fixtures/method_descriptions")
        )
    sides = {row["arxiv_id"]: system_side(row["arxiv_id"], args.cache, describer) for row in labels}
```

- [ ] **Step 4: 运行，确认通过**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" \
  tests/unit/test_method_acquisition_audit.py -v --basetemp=.pytest_tmp_s3_t7_green
```

预期：9 passed。

- [ ] **Step 5: 全量**

预期：`403 passed, 2 skipped`。

- [ ] **Step 6: 实跑（关键判据）**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" scripts/method_acquisition_audit.py \
  --labels tests/fixtures/method_acquisition/labels.json
"D:/Anaconda/envs/reOS/python.exe" scripts/method_acquisition_audit.py \
  --labels tests/fixtures/method_acquisition/labels.json --describer recorded
```

预期：两次都是 **L3 `C=0/20`、`gaps` 48**，且原因行从
`无结构化字段 20` 变成 **`LLM 未启用` 40**（两个领域各 20）。

**如果 `--describer recorded` 出现 L3 覆盖 > 0，说明夹具目录里有别人的录制数据，停下来查清楚来源再继续。**

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add scripts/method_acquisition_audit.py tests/unit/test_method_acquisition_audit.py
git commit -m "feat(audit): say whether L3 is empty because nobody asked

After S3 the layer has a field, so 'no structured field' would be a lie. The cause
now distinguishes a run with no describer from a describer that produced nothing,
and --describer recorded replays fixtures without touching the network."
```

---

### Task 8: 文档与交接

**Files:**
- Modify: `architect.md`（ADR-035、已知限制 17–18、维护记录）
- Modify: `docs/superpowers/specs/2026-11-15-method-acquisition-design.md`（§13 D16–D19）
- Modify: `docs/evaluation/2026-11-15-method-acquisition-s2.md`（追加「S3 之后」一节）
- Modify: `docs/handover/2026-11-15-method-acquisition-handover.md`

- [ ] **Step 1: ADR-035**

`architect.md` 的 ADR 表末尾（ADR-034 之后）加：

```markdown
| ADR-035 | L3 走 LLM，但**只产要点、不产名字/设置**；模型输出先落 `MethodPointDraft`（宽松）、再过 `validate_description` 四道防线成 `MethodPoint`（严格）。理由：一是名字/设置已由确定性路径负责（ADR-034），让模型写名字等于把未经验证的字符串放进归因字段；二是把「宽松解析」与「严格校验」分开，才可能用 fake 输出把四条失败路径各测一遍。预算改为「先查后加」——`llm_calls` 此前全仓库无写入点，上限是装饰 | ACTIVE |
```

- [ ] **Step 2: 已知限制**

「已知限制」末尾（第 16 条之后）加：

```markdown
17. **L3 的覆盖在本仓库里仍是未测量状态**：S3 落地了协议、四道防线、预算与录制回放，但**没有 provider 客户端**，`tests/fixtures/method_descriptions/` 是空的。审计在 `--describer recorded` 下报 `LLM 未启用`，不报一个没测过的数字。要动这一格，必须先实现 provider 并用 `scripts/record_method_descriptions.py` 录 40 篇。
18. 四道防线是**形式判据**：`quote` 能定位、`statement` 与它有词重叠，不等于 `statement` 说得对。这一层不宣称描述正确率，只保证「每条要点都能指回原文的一句」。
```

- [ ] **Step 3: 设计 §13 偏差**

`docs/superpowers/specs/2026-11-15-method-acquisition-design.md` 的 §13 表末尾追加：

```markdown
| D16 | §7.1 协议是 `describe(...) -> MethodDescriptionResponse \| None` | 返回 `DescriptionAttempt`（response / cost_usd / error） | §7.3 要求「provider 返回用量则回填 cost_usd」，而原签名没有位置放成本与错误。三者同为一次调用的结果，分成三个返回值只会让调用方拼装状态 |
| D17 | §4.1 的 `MethodPoint` 直接作为模型输出模型 | 新增 `MethodPointDraft`（宽松）作输出模型，`MethodPoint` 只由校验器产出 | 若直接让 pydantic 校验模型输出，一个越界 aspect 会抛 `ValidationError`，整篇描述连带丢失，且事件只能记成「schema 坏」；而 §7.4 要求「不合 → 丢弃该点」与「schema 坏 → 整篇拒绝」分开 |
| D18 | §7.2 未给配置项命名 | `llm_provider` / `llm_model` / `llm_api_key` / `llm_fixture_dir`；`none` 表示不装配 describer | `UnavailableProvider` 从未被实例化，与其假装默认是它，不如让默认是「没有 describer」：零调用、零成本、事件明确 |
| D19 | §7.6 「把 40 篇的 L3 响应录成夹具」 | 只实现录制与回放两条通路，夹具目录留空，审计报「LLM 未启用」 | 本仓库没有 provider 客户端、没有 key；伪造 40 份响应会让「未测量」看起来像「已测量」，正是本项目反复在修的同一类错误。TRADE-OFF 已写进已知限制 17 |
```

- [ ] **Step 4: 报告追加一节**

在 `docs/evaluation/2026-11-15-method-acquisition-s2.md` 末尾加：

```markdown
## 6. S3 之后（2026-11-15，协议与防线落地）

S3 把 L3 的通路建好了，**但没有 provider**，因此本报告第 1 节的 L3 一格**没有变化**，
而且以后不该再读成「抽取失败」：

```
$ python scripts/method_acquisition_audit.py --labels tests/fixtures/method_acquisition/labels.json
  image_restoration|L3   A=20/20  C=0/20
  agent_in_mc|L3         A=20/20  C=0/20
  image_restoration|L3|LLM 未启用   20
  agent_in_mc|L3|LLM 未启用         20
```

要让这一格动起来需要两步，都不在本轮范围内：①实现一个 provider 客户端；
②`python scripts/record_method_descriptions.py --provider <name>` 录 40 篇，
然后 `--describer recorded` 重跑。那时才第一次有 L3 的 covered 数字，且必须与 before 并列写。
```

- [ ] **Step 5: 交接**

`docs/handover/2026-11-15-method-acquisition-handover.md`：§0 改成 S3 已收官、下一步 S4；
§9 的「S3 起手要做的事」改成「S3 收官记录」+「S4 起手要做的事」（设计 §8：`conditions` 新增
`scale=`/`protocol=`、按 kind 的 provenance、级联安全、三份 before/after 报告）；
§6 数字改成实测值；待办 #10 与 #17 的关系写清（指标登记仍欠，且现在多了一条「L3 未测量」）。

- [ ] **Step 6: 收尾核对**

```bash
cd /d/ResearchOS && "D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" -q --basetemp=.pytest_tmp_s3_final
"D:/Anaconda/envs/reOS/python.exe" -m pytest -o addopts="" --collect-only -q --basetemp=.pytest_tmp_s3_collect | tail -3
git status --short
```

预期：`403 passed, 2 skipped`、`405 tests collected`、工作区干净。

- [ ] **Step 7: 提交**

```bash
cd /d/ResearchOS && git add architect.md docs/
git commit -m "docs(arch): record S3, the L3 wiring

ADR-035 pins the two-model split (loose draft, strict point) and the budget
order. The report adds the L3 section that says, in numbers, that the layer is
still unmeasured - which is different from reporting zero coverage as a defect."
```

---

## 验收（S3 完成判据）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | 同步协议 + async 适配器可用 | `test_describe_runs_the_async_provider_synchronously` |
| 2 | 事件循环里不嵌套 | `test_a_running_event_loop_is_refused_instead_of_nested`（构造期与调用期各一次） |
| 3 | 四道防线各有一条路径 | `test_method_description.py` 的 7 条，含「一个坏点不连坐」 |
| 4 | 预算先查后加 | `max_llm_calls=0` → 0 次调用 + 1 条 SKIPPED；`=2` + 3 篇 → 恰好 2 次 |
| 5 | 落库 + memo 显示 | `test_points_are_persisted_and_leave_missing_layers`、`test_the_memo_prints_the_point_with_its_section` |
| 6 | 无 provider 不伪装成调过 | `test_no_describer_leaves_l3_missing_without_any_event` |
| 7 | 审计不谎报 L3 | 两次实跑都是 `L3 C=0/20`，原因行 `LLM 未启用 20+20` |
| 8 | 既有用例一条不少 | 收集数 `405`（376 + 29） |

## 明确不做（S3 边界）

- 不实现真实 provider 客户端（OpenAI/Anthropic 等）；只实现录制回放与工厂分支。
- 不让模型产出 name / components / setup（那是 S2 的确定性路径）。
- 不改 `identity_key`、不改 `conditions`、不改主张数。
- 不宣称 L3 的描述正确率；只保证可定位。
- 不伪造录制夹具。
