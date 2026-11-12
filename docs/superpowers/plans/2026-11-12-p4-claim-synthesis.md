# P4 Claim Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn evidence sentences into claims with an explicit scope identity, so claims can be de-duplicated across sources without merging claims that differ in dataset, task, metric, direction or reported value.

**Architecture:** A new `research/claims.py` holds the identity value object and its deterministic extractor; `research/scope.py` derives block-level context (task from section headings, dataset from the section's first naming sentence) because the 10-document probe showed sentence-level identity reaches 0/215. `claim_builder.py` becomes a thin grouper: extract identity per evidence, merge only when the identity gate passes, attach one SUPPORTS per evidence. Status/confidence flags move into `claims.py` so "unsupported" keeps meaning "no supporting evidence".

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0 + SQLite (idempotent ADD COLUMN migration), pytest.

**Spec:** `docs/superpowers/specs/2026-11-12-p4-claim-synthesis-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/research_os/documents/html.py` | + de-duplicate ar5iv's LaTeX echo (`96%96\%`, `10×10\times`) during block normalization |
| `src/research_os/research/lexicon.py` | + `TASKS` (heading phrase → canonical task), + `THIRD_PARTY` markers |
| `src/research_os/research/quantitative.py` | + delta/unit-only pass when no metric row exists |
| `src/research_os/domain/models.py` | `QuantitativeEvidence.delta`, `Claim.identity_key` |
| `src/research_os/storage/tables.py` | + 2 columns |
| `src/research_os/storage/database.py` | + 2 idempotent columns in `_ADDED_COLUMNS` |
| `src/research_os/research/scope.py` | **new** `BlockScope` + `build_section_scopes()` |
| `src/research_os/research/claims.py` | **new** `ClaimIdentity`, `extract_identity()`, `classify()`, `identity_gate()` |
| `src/research_os/research/claim_builder.py` | rewritten: group by identity, attach relations |
| `src/research_os/orchestration/supervisor.py` | pass quantitative facts + scopes |
| `src/research_os/reporting/memo.py` | Finding shows Scope/Conditions/Grounding; `# Claims Kept Separate` |
| `src/research_os/cli.py` | `claims` prints scope |

---

### Task 1: ar5iv LaTeX echo de-duplication

**Files:**
- Modify: `src/research_os/documents/html.py` (`_collapse`)
- Test: `tests/unit/test_html_loader.py`

- [x] **Step 1: Write the failing test**

```python
def test_latex_echo_is_deduplicated():
    """ar5iv renders ``96%96\\%`` and ``1×11\\times 1``; the echo would make the
    numeric extractor read two different values from one number."""
    html = (
        "<html><body><main><p>AutoDIR gathers more than 96%96\\% of the votes.</p>"
        "<p>We use 1×11\\times 1 convolution and a 10×10\\times patch.</p></main></body></html>"
    )
    path = tmp_path / "echo.html"
    path.write_text(html, encoding="utf-8")

    pages = load_html(path)

    body = " ".join(p.text for p in pages)
    assert "96%96\\%" not in body
    assert "96% of the votes" in body
    assert "1×1 convolution" in body
    assert "10×10 patch" in body


def test_deduplication_keeps_offsets_consistent():
    html = "<html><body><p>It gathers more than 96%96\\% of the votes in the user study.</p></body></html>"
    path = tmp_path / "echo2.html"
    path.write_text(html, encoding="utf-8")

    chunks = chunk_pages(load_html(path), "sv_echo")
    evidence = HeuristicEvidenceExtractor().extract(chunks)

    assert evidence
    assert all(c.text[e.char_start : e.char_end] == e.text for c in chunks for e in evidence)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_html_loader.py -q`
Expected: FAIL — `"96%96\%"` still present.

- [x] **Step 3: Implement in `_collapse`**

```python
# ar5iv keeps both the rendered form and the LaTeX source next to each other.
# Left in place, "96%96\%" reads as two numbers and "1×11\times 1" as three.
_ECHO_TIMES_LONG = re.compile(r"(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)\1\\(?:times)\s*\2")
_ECHO_TIMES_SHORT = re.compile(r"(\d+(?:\.\d+)?×\d+(?:\.\d+)?)\\(?:times)")
_ECHO_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\%(\d+(?:\.\d+)?)\\%")


def _collapse(text: str) -> str:
    """Normalize one block: undo ar5iv's LaTeX echo, then collapse whitespace."""
    text = _ECHO_TIMES_LONG.sub(r"\1×\2", text)   # 1×11\times 1 -> 1×1
    text = _ECHO_TIMES_SHORT.sub(r"\1", text)     # 10×10\times   -> 10×10
    text = _ECHO_PERCENT.sub(r"\1%", text)        # 96%96\%       -> 96%
    return re.sub(r"\s+", " ", text).strip()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_loader.py -q`
Expected: PASS (existing 5 + 2 new).

- [x] **Step 5: Commit**

```bash
git add src/research_os/documents/html.py tests/unit/test_html_loader.py
git commit -m "fix(documents): undo ar5iv LaTeX echo before chunking"
```

---

### Task 2: quantitative facts for values without a metric word

**Files:**
- Modify: `src/research_os/domain/models.py` (`QuantitativeEvidence.delta`)
- Modify: `src/research_os/storage/tables.py`, `src/research_os/storage/database.py`
- Modify: `src/research_os/research/quantitative.py`
- Test: `tests/unit/test_quantitative.py`

- [x] **Step 1: Write the failing test**

```python
def test_delta_value_without_metric_is_captured():
    """78% of value statements never name a metric; without this pass they carry
    no structured fact at all and cannot be compared or bucketed."""
    text = "The larger learning rate brings a gain of +0.44 dB (39.29 dB to 39.73 dB) on SIDD."

    rows = HeuristicQuantitativeExtractor().extract_from_text(text, evidence_id="e1")

    assert len(rows) == 1
    row = rows[0]
    assert row.metric is None
    assert row.delta == 0.44
    assert row.protocol == "dB"
    assert row.dataset == "SIDD"


def test_delta_pass_does_not_duplicate_metric_rows():
    text = "On Rain100H, our method improves PSNR by 0.42 dB."

    rows = HeuristicQuantitativeExtractor().extract_from_text(text, evidence_id="e1")

    assert len(rows) == 1
    assert rows[0].metric == "PSNR"
    assert rows[0].delta is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_quantitative.py -q`
Expected: FAIL — first test gets 0 rows (`metric` requirement blocks it).

- [x] **Step 3: Implement**

Add to `QuantitativeEvidence`:

```python
    delta: float | None = None  # "+0.44 dB" style gain when no metric is named
```

Add columns to `_ADDED_COLUMNS`:

```python
    "quantitative_evidence": {"delta": "FLOAT"},
    "claims": {"identity_key": "VARCHAR(256)"},
```

In `quantitative.py`, after the metric loop, when `not rows`:

```python
_DELTA = re.compile(r"(?P<sign>[+\-−])?\s*(?P<value>\d+(?:\.\d+)?)\s?(?P<unit>dB|%)\b", re.IGNORECASE)
_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s?dB\s*(?:to|→)\s*(\d+(?:\.\d+)?)\s?dB", re.IGNORECASE
)
_DELTA_WORDS = re.compile(r"(gain|improv|increas|reduc|higher|lower|margin|boost)", re.IGNORECASE)


def _delta_record(self, text: str) -> QuantitativeEvidence | None:
    """Record a gain stated as "+0.44 dB" / "a 0.11 dB improvement".

    Only called when the metric-based pass found nothing, otherwise the same
    number would be stored twice (once as PSNR, once as a delta).
    """
    if not _DELTA_WORDS.search(text):
        return None
    match = _DELTA.search(text)
    if match is None:
        return None
    value = float(match.group("value"))
    unit = match.group("unit").lower()
    lo = hi = None
    span = _RANGE.search(text)
    if span is not None:
        lo, hi = float(span.group(1)), float(span.group(2))
    return QuantitativeEvidence(
        evidence_id="",  # filled by caller
        metric=None,
        dataset=self._dataset(text),
        delta=value,
        value=hi,
        comparator_value=lo,
        protocol="dB" if unit == "db" else "percent",
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_quantitative.py -q`
Expected: PASS (5 existing + 2 new).

- [x] **Step 5: Commit**

```bash
git add src/research_os/domain/models.py src/research_os/storage src/research_os/research/quantitative.py tests/unit/test_quantitative.py
git commit -m "feat(evidence): capture delta values when no metric is named"
```

---

### Task 3: block-level scope inheritance

**Files:**
- Create: `src/research_os/research/scope.py`
- Modify: `src/research_os/research/lexicon.py` (+ `TASKS`)
- Test: `tests/unit/test_scope.py`

- [x] **Step 1: Write the failing test**

```python
def test_task_is_inherited_from_the_section_heading():
    chunks = [
        _chunk(0, "Classical image SR.", "The maximum PSNR gain reaches 0.26 dB on Manga109."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[0].id].task == "super-resolution"
    assert scopes[chunks[0].id].inherited_from["task"] == "heading"


def test_dataset_is_inherited_from_the_sections_first_naming_sentence():
    chunks = [
        _chunk(0, "Classical image SR.", "We evaluate on Set5 and Urban100 with scale factor 4."),
        _chunk(1, "Classical image SR.", "The method improves the score further on this dataset."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].datasets == frozenset({"Set5", "Urban100"})
    assert scopes[chunks[1].id].inherited_from["datasets"] == "section-first-mention"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scope.py -q`
Expected: FAIL — `ModuleNotFoundError: research_os.research.scope`.

- [x] **Step 3: Implement `scope.py`**

```python
"""Block-level scope context for claim identity (plan §16, P4 spec §4).

The 10-document probe behind P4 showed that identity taken from a single
sentence reaches a complete key 0 times in 215 claims: papers name the task in
the subsection heading ("Classical image SR.") and the dataset in the first
sentence of a subsection, then keep referring to "this dataset". So scope is
resolved at block level, with per-chunk provenance kept for inspection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from research_os.domain.models import DocumentChunk
from research_os.research.lexicon import DATASETS, TASKS


@dataclass(frozen=True)
class BlockScope:
    """Task/dataset context a claim inherits from its section."""

    task: str | None = None
    datasets: frozenset[str] = frozenset()
    inherited_from: dict[str, str] = field(default_factory=dict)


def _task_of(text: str) -> str | None:
    low = text.lower()
    for phrase, canonical in TASKS:
        if phrase in low:
            return canonical
    return None


def _datasets_of(text: str) -> frozenset[str]:
    low = text.lower()
    return frozenset(d for d in DATASETS if d.lower() in low)


def build_section_scopes(chunks: list[DocumentChunk]) -> dict[str, BlockScope]:
    """Map chunk id -> scope inherited from its section.

    Dataset inheritance is deliberately narrow: only the first sentence of the
    section that names a dataset is inherited. That covers "name it once, then
    say 'this dataset'", and nothing else - no pronoun resolution.
    """
    scopes: dict[str, BlockScope] = {}
    sections: dict[tuple[str, str | None], list[DocumentChunk]] = {}
    for chunk in chunks:
        sections.setdefault((chunk.source_version_id, chunk.section), []).append(chunk)

    for (_sv, section), group in sections.items():
        heading_task = _task_of(section or "")
        heading_datasets = _datasets_of(section or "")
        inherited: frozenset[str] = heading_datasets
        source = "heading" if heading_datasets else ""
        if not inherited:
            for chunk in group:
                found = _datasets_of(chunk.text)
                if found:
                    inherited, source = found, "section-first-mention"
                    break
        for chunk in group:
            provenance = {}
            if heading_task:
                provenance["task"] = "heading"
            if inherited:
                provenance["datasets"] = source
            scopes[chunk.id] = BlockScope(heading_task, inherited, provenance)
    return scopes
```

Add to `lexicon.py`:

```python
# Heading phrase -> canonical task. Papers name the task in subsection headings
# ("Classical image SR.", "RGB Image Denoising"), never in the sentences below.
TASKS: tuple[tuple[str, str], ...] = (
    ("super-resolution", "super-resolution"),
    ("super resolution", "super-resolution"),
    ("image sr", "super-resolution"),
    ("denoising", "denoising"),
    ("deblurring", "deblurring"),
    ("deraining", "deraining"),
    ("inpainting", "inpainting"),
    ("jpeg compression artifact reduction", "jpeg artifact reduction"),
    ("restoration", "image restoration"),
)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope.py -q`
Expected: PASS, 2 passed.

- [x] **Step 5: Commit**

```bash
git add src/research_os/research/scope.py src/research_os/research/lexicon.py tests/unit/test_scope.py
git commit -m "feat(claims): inherit task and dataset from block context"
```

---

### Task 4: claim identity

**Files:**
- Create: `src/research_os/research/claims.py`
- Modify: `src/research_os/domain/models.py` (`Claim.identity_key`), `tables.py`
- Test: `tests/unit/test_claim_identity.py`

- [x] **Step 1: Write the failing test**

```python
def test_dataset_makes_two_claims_different():
    """Plan §16 acceptance: Rain100H and SIDD must never collapse into one."""
    a = extract_identity(
        "On the Rain100H benchmark, our method improves PSNR by 0.42 dB.",
        source_version_id="sv_1", scope=None, quantitative=[],
    )
    b = extract_identity(
        "On the SIDD dataset, our method improves PSNR by 0.42 dB.",
        source_version_id="sv_1", scope=None, quantitative=[],
    )

    assert a.key() != b.key()
    assert a.dataset == frozenset({"Rain100H"})
    assert b.dataset == frozenset({"SIDD"})


def test_multiple_metrics_are_kept_as_a_set():
    identity = extract_identity(
        "On Rain100H, our method improves PSNR by 0.42 dB and SSIM by 0.013.",
        source_version_id="sv_1", scope=None, quantitative=[],
    )

    assert identity.metric == frozenset({"PSNR", "SSIM"})


def test_subject_comes_from_the_clause_before_the_predicate():
    """'the model' after the verb is the object, not the subject."""
    identity = extract_identity(
        "The gating mechanism enables the model to weight cues.",
        source_version_id="sv_1", scope=None, quantitative=[],
    )

    assert identity.subject is None  # a mechanism, not a named method


def test_self_subject_is_bound_to_its_source():
    a = extract_identity(
        "Our method improves PSNR by 0.42 dB on Rain100H.",
        source_version_id="sv_a", scope=None, quantitative=[],
    )
    b = extract_identity(
        "Our method improves PSNR by 0.42 dB on Rain100H.",
        source_version_id="sv_b", scope=None, quantitative=[],
    )

    assert a.subject == "self@sv_a"
    assert b.subject == "self@sv_b"
    assert a.key() != b.key()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_claim_identity.py -q`
Expected: FAIL — no module `claims`.

- [x] **Step 3: Implement `claims.py`** (identity part)

```python
"""Claim identity: what makes two claims "the same claim" (plan §16).

Deterministic only - no LLM. Identity is what the merge gate compares, so every
field must be either confidently extracted or None; None never equals None for
the merge gate (see `mergeable`), because "unknown" is not "identical".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from research_os.domain.models import QuantitativeEvidence
from research_os.research.lexicon import DATASETS, METRICS, THIRD_PARTY
from research_os.research.scope import BlockScope

# The verb that separates subject from object. Deliberately narrow: broad verb
# lists pick up "the blur is approximated by", which has no real subject.
PREDICATE = re.compile(
    r"\b(improves?|improved|outperforms?|outperformed|achieves?|achieved|gains?|gained|"
    r"reduces?|reduced|increases?|increased|surpass(?:es|ed)?|enables?|yields?|"
    r"reports?|reported|reaches?|demonstrates?)\b",
    re.IGNORECASE,
)
SELF_REFERENCE = re.compile(
    r"\b(?:our\s+(?:method|approach|model|framework|network|system|proposed)|"
    r"we\s+propose|this\s+paper\s+proposes|the\s+(?:proposed\s+)?(?:method|model|approach|network))\b",
    re.IGNORECASE,
)
COMMON_CAPS = frozenset({
    "the", "this", "that", "these", "those", "on", "in", "for", "with", "we", "our",
    "however", "specifically", "although", "to", "it", "both", "have", "link", "results",
    "result", "experiments", "experimental", "table", "figure", "abstract", "authors",
    "moreover", "therefore", "thus", "as", "at", "by", "from", "and", "but", "while",
    "recently", "since", "given", "compared", "unlike", "among", "notably", "finally",
})
DIRECTION_UP = re.compile(r"\b(improv\w*|gain\w*|outperform\w*|better|surpass\w*|exceed\w*|reduc\w*|increas\w*)", re.I)
DIRECTION_LEVEL = re.compile(r"\b(achiev\w*|reach\w*|report\w*)", re.I)
CONDITION_PATTERNS = (
    (re.compile(r"\b(cnn|transformer|convolutional)\b\s+backbone", re.I), "backbone"),
    (re.compile(r"\b(synthetic|real[- ]world)\b", re.I), "setting"),
    (re.compile(r"\b(video|single[- ]image)\b", re.I), "granularity"),
)
_BUCKET_DIGITS = {"PSNR": 1, "SSIM": 3, "LPIPS": 3, "FID": 1, "MAE": 2, "MSE": 2}


@dataclass(frozen=True)
class ClaimIdentity:
    subject: str | None
    task: str | None
    dataset: frozenset[str]
    metric: frozenset[str]
    direction: str | None
    conditions: tuple[str, ...]
    value_bucket: tuple[str, ...]

    def key(self) -> str:
        ds = ",".join(sorted(d.lower() for d in self.dataset))
        mt = ",".join(sorted(m.lower() for m in self.metric))
        conds = ";".join(self.conditions)
        return f"{self.subject}|{self.task}|{ds}|{mt}|{self.direction}|{conds}|{';'.join(self.value_bucket)}"

    def label(self) -> str:
        parts = [p for p in (self.task, ", ".join(sorted(self.dataset)),
                             ", ".join(sorted(self.metric)), self.direction) if p]
        return " · ".join(parts)


def _subject(text: str) -> str | None:
    match = PREDICATE.search(text)
    prefix = text[: match.start()] if match else text
    if SELF_REFERENCE.search(prefix):
        return "self"  # bound to the source version by the caller
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]*", prefix):
        low = token.lower()
        if low in COMMON_CAPS or low in {d.lower() for d in DATASETS} or low in {m.lower() for m in METRICS}:
            continue
        if (
            any(c.isupper() for c in token[1:])
            or (token.isupper() and len(token) >= 2)
            or any(c.isdigit() for c in token)
            or (token[0].isupper() and len(token) >= 6)
        ):
            return low
    return None


def _conditions(text: str) -> tuple[str, ...]:
    found = []
    for pattern, name in CONDITION_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(f"{name}={match.group(1).lower().replace(' ', '-')}")
    return tuple(sorted(found))


def _buckets(quantitative: list[QuantitativeEvidence]) -> tuple[str, ...]:
    buckets = []
    for row in quantitative:
        if row.metric and row.value is not None:
            digits = _BUCKET_DIGITS.get(row.metric.upper(), 1)
            buckets.append(f"{row.metric.lower()}={round(row.value, digits)}")
        elif row.delta is not None:
            buckets.append(f"{row.protocol or 'unit'}:{round(row.delta, 2)}")
    return tuple(sorted(set(buckets)))


def extract_identity(
    text: str,
    *,
    source_version_id: str,
    scope: BlockScope | None,
    quantitative: list[QuantitativeEvidence],
) -> ClaimIdentity:
    low = text.lower()
    datasets = {d for d in DATASETS if d.lower() in low}
    metrics = {m for m in METRICS if re.search(rf"\b{m}\b", text, re.I)}
    task = None
    if scope is not None:
        datasets = datasets or set(scope.datasets)
        task = scope.task
    subject = _subject(text)
    if subject is None and (task or datasets or metrics) and not THIRD_PARTY.search(text):
        # In the paper's own evaluation prose the implicit subject is its method.
        subject = "self"
    if subject == "self":
        subject = f"self@{source_version_id}"
    direction = "UP" if DIRECTION_UP.search(text) else ("LEVEL" if DIRECTION_LEVEL.search(text) else None)
    return ClaimIdentity(
        subject=subject,
        task=task,
        dataset=frozenset(datasets),
        metric=frozenset(metrics),
        direction=direction,
        conditions=_conditions(text),
        value_bucket=_buckets(quantitative),
    )


def mergeable(identity: ClaimIdentity) -> bool:
    """Plan §16: merge only when scope is fully determined."""
    return bool(identity.subject and identity.dataset and identity.direction)


def may_merge(a: ClaimIdentity, b: ClaimIdentity) -> bool:
    if not (mergeable(a) and mergeable(b)):
        return False
    if a.value_bucket != b.value_bucket:
        return False  # different reported values are P5's input, not a duplicate
    return a.key() == b.key()
```

Add `THIRD_PARTY` to `lexicon.py`:

```python
# Sentences about someone else's method must not get the implicit SELF subject.
THIRD_PARTY = re.compile(
    r"\b(previous|existing|prior|baseline|baselines|compared methods|state-of-the-art|sota|"
    r"competitors?|recent methods?|others?)\b",
    re.IGNORECASE,
)
```
(and `import re` in lexicon.py)

Add `identity_key` to `Claim`:

```python
    identity_key: str | None = None
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_claim_identity.py -q`
Expected: PASS, 4 passed.

- [x] **Step 5: Commit**

```bash
git add src/research_os/research/claims.py src/research_os/research/lexicon.py src/research_os/domain/models.py src/research_os/storage/tables.py src/research_os/storage/database.py tests/unit/test_claim_identity.py
git commit -m "feat(claims): deterministic claim identity with source-bound SELF subject"
```

---

### Task 5: merge claims by identity

**Files:**
- Modify: `src/research_os/research/claim_builder.py`
- Test: `tests/unit/test_claim_merge.py`, fixtures `tests/fixtures/claim_merge/paper_a.md`, `paper_b.md`, `paper_c.md`

- [x] **Step 1: Write the fixtures and the failing test**

`paper_a.md`: `# Results\n\nOn the Rain100H benchmark, Restormer improves PSNR by 0.42 dB.\n`
`paper_b.md`: `# Results\n\nOn the Rain100H benchmark, Restormer improves PSNR by 0.42 dB.\n`
`paper_c.md`: `# Results\n\nOn the Rain100H benchmark, Restormer improves PSNR by 0.51 dB.\n`

```python
def test_identical_identity_and_value_merges_into_one_claim():
    claims, relations = _build([PAPER_A, PAPER_B])

    assert len(claims) == 1
    assert len(relations) == 2
    assert {r.claim_id for r in relations} == {claims[0].id}


def test_same_identity_but_different_value_stays_separate():
    claims, _ = _build([PAPER_A, PAPER_C])

    assert len(claims) == 2, "different reported values are P5's input, not duplicates"


def test_our_method_from_two_papers_never_merges():
    claims, _ = _build([PAPER_SELF_A, PAPER_SELF_B])

    assert len(claims) == 2
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_claim_merge.py -q`
Expected: FAIL — 2 claims, because the builder still keys on text.

- [x] **Step 3: Rewrite `claim_builder.py`**

```python
"""Claim construction: identity, merge, relation (plan §16).

Grouping is by `ClaimIdentity`, never by wording similarity: two sentences that
read alike but differ in dataset, task, metric, direction, condition or reported
value stay two claims (plan §16 "do not merge claims simply because their wording
is similar").
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Protocol

from research_os.domain.models import (
    Claim,
    ClaimEvidenceRelation,
    DocumentChunk,
    Evidence,
    QuantitativeEvidence,
)
from research_os.research.claims import (
    ClaimIdentity,
    classify_claim,
    extract_identity,
    may_merge,
)
from research_os.research.scope import BlockScope, build_section_scopes


class ClaimBuilder(Protocol):
    def build(
        self,
        evidence: list[Evidence],
        quantitative: list[QuantitativeEvidence] | None = None,
        chunks: list[DocumentChunk] | None = None,
    ) -> tuple[list[Claim], list[ClaimEvidenceRelation]]: ...


class HeuristicClaimBuilder:
    """Deterministic builder: identity -> group -> one SUPPORTS per evidence."""

    def build(self, evidence, quantitative=None, chunks=None):
        quantitative = quantitative or []
        scopes: dict[str, BlockScope] = build_section_scopes(chunks or [])
        quant_by_evidence: dict[str, list[QuantitativeEvidence]] = defaultdict(list)
        for row in quantitative:
            quant_by_evidence[row.evidence_id].append(row)

        groups: list[dict] = []
        for ev in evidence:
            if not _is_claim_text(ev.text):
                continue
            identity = extract_identity(
                ev.text,
                source_version_id=ev.source_version_id,
                scope=scopes.get(ev.chunk_id or ""),
                quantitative=quant_by_evidence.get(ev.id, []),
            )
            for group in groups:
                if may_merge(group["identity"], identity):
                    group["evidence"].append(ev)
                    break
            else:
                groups.append({"identity": identity, "evidence": [ev], "text": ev.text})

        claims: list[Claim] = []
        relations: list[ClaimEvidenceRelation] = []
        for group in groups:
            identity: ClaimIdentity = group["identity"]
            evs: list[Evidence] = group["evidence"]
            status, confidence, flags = classify_claim(group["text"], identity, evs, quant_by_evidence)
            claim = Claim(
                text=group["text"],
                claim_type=_claim_type(group["text"]),
                scope=identity.label() or None,
                conditions=list(identity.conditions) + flags,
                status=status,
                confidence_label=confidence,
                identity_key=identity.key(),
            )
            claims.append(claim)
            rationale = (
                "merged by identity key: " + identity.key() if len(evs) > 1
                else "claim text derived from this evidence sentence"
            )
            for ev in evs:
                relations.append(
                    ClaimEvidenceRelation(
                        claim_id=claim.id, evidence_id=ev.id,
                        relation=EvidenceRelation.SUPPORTS, rationale=rationale,
                    )
                )
        return claims, relations
```

`_is_claim_text` keeps the existing mark/regex pair; `_claim_type` keeps the
existing comparative/factual split.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_claim_merge.py -q`
Expected: PASS, 3 passed.

- [x] **Step 5: Commit**

```bash
git add src/research_os/research/claim_builder.py tests/unit/test_claim_merge.py tests/fixtures/claim_merge
git commit -m "feat(claims): merge claims by identity instead of wording"
```

---

### Task 6: status and confidence flags

**Files:**
- Modify: `src/research_os/research/claims.py`
- Test: `tests/unit/test_claim_status.py`

- [x] **Step 1: Write the failing test**

```python
def test_speculation_is_unsupported_without_a_relation():
    status, confidence, flags = classify_claim(
        "We believe spatial cues may help on easier benchmarks.",
        _identity(), [], {},
    )
    assert status is ClaimStatus.UNSUPPORTED
    assert confidence is ConfidenceLabel.LOW


def test_value_without_structured_fact_stays_supported_but_low():
    """The sentence does support the claim; what is missing is structure."""
    status, confidence, flags = classify_claim(
        "The gain is 0.11 dB on the harder split.",
        _identity(), [object()], {},
    )
    assert status is ClaimStatus.SUPPORTED
    assert confidence is ConfidenceLabel.LOW
    assert "quantitative_unstructured" in flags


def test_comparative_without_control_is_flagged():
    status, confidence, flags = classify_claim(
        "Experimental results demonstrate that the method outperforms state-of-the-art methods.",
        _identity(), [object()], {},
    )
    assert status is ClaimStatus.SUPPORTED
    assert confidence is ConfidenceLabel.LOW
    assert "comparative_unsubstantiated" in flags
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_claim_status.py -q`
Expected: FAIL — `classify_claim` missing.

- [x] **Step 3: Implement `classify_claim` in `claims.py`**

```python
SPECULATION = re.compile(
    r"(we believe|believe that|suggest|hypothesiz|may |could |might |future work|"
    r"we expect|potentially|we hope|in principle|generalizes to other)",
    re.IGNORECASE,
)
UNIT_VALUE = re.compile(r"\d+(?:\.\d+)?\s?(dB|%|percent|×)\b", re.IGNORECASE)
COMPARATIVE = re.compile(r"\b(outperform\w*|better than|surpass\w*|state-of-the-art|sota)\b", re.I)
CONTROL = re.compile(r"\b(compared (?:with|to)|than|versus|vs\.?)\b", re.IGNORECASE)


def classify_claim(text, identity, evidence, quant_by_evidence):
    """(status, confidence, flags).

    UNSUPPORTED means "no supporting evidence", nothing else. A claim whose
    evidence exists but whose numbers are unstructured, out of scope, or
    unchecked stays SUPPORTED with LOW confidence plus a named flag - otherwise
    "unsupported" degrades into a synonym for "low confidence" (P4 spec §8).
    """
    if SPECULATION.search(text):
        return ClaimStatus.UNSUPPORTED, ConfidenceLabel.LOW, []
    flags: list[str] = []
    confidence = ConfidenceLabel.MEDIUM
    has_value = bool(UNIT_VALUE.search(text))
    grounded = any(quant_by_evidence.get(ev.id if hasattr(ev, "id") else "", []) for ev in evidence)
    if has_value and not grounded:
        flags.append("quantitative_unstructured")
    if has_value and not identity.dataset and not identity.metric:
        flags.append("scope_undetermined")
    if COMPARATIVE.search(text) and not CONTROL.search(text) and not grounded:
        flags.append("comparative_unsubstantiated")
    if flags:
        confidence = ConfidenceLabel.LOW
    return ClaimStatus.SUPPORTED, confidence, flags
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_claim_status.py -q`
Expected: PASS, 3 passed.

- [x] **Step 5: Commit**

```bash
git add src/research_os/research/claims.py tests/unit/test_claim_status.py
git commit -m "feat(claims): separate 'unsupported' from 'weak evidence'"
```

---

### Task 7: wiring, memo and CLI

**Files:**
- Modify: `src/research_os/orchestration/supervisor.py`
- Modify: `src/research_os/reporting/memo.py`
- Modify: `src/research_os/cli.py`
- Test: `tests/integration/test_claim_synthesis.py`

- [x] **Step 1: Write the failing test**

```python
def test_memo_shows_scope_and_keeps_differing_datasets_apart(db, tmp_path):
    run_id = _run_fixture_slice(tmp_path)

    memo = build_memo_from_run(session, run_id)

    assert "Scope:" in memo
    assert "Grounding:" in memo
    assert "# Claims Kept Separate" in memo
    assert "Rain100H" in memo and "SIDD" in memo
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_claim_synthesis.py -q`
Expected: FAIL — memo has no `Scope:` line.

- [x] **Step 3: Implement**

supervisor: pass `quantitative=quantitative_evidence, chunks=chunks` into `self._claim_builder.build(...)`.
memo: Finding block gains

```python
- Scope: {claim.scope or "undetermined"}
- Conditions: {", ".join(claim.conditions) or "none"}
- Grounding: {grounding}   # structured / unstructured / none, from flags
```

plus a new section listing groups sharing subject+metric but differing in dataset.
cli: `claims` prints `scope` between status and text.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest -q`
Expected: full suite green (≥ 120 passed).

- [x] **Step 5: Commit**

```bash
git add src/research_os/orchestration/supervisor.py src/research_os/reporting/memo.py src/research_os/cli.py tests/integration/test_claim_synthesis.py
git commit -m "feat(claims): surface scope, grounding and kept-separate groups"
```

---

### Task 8: documentation sync

**Files:** `README.md`, `architect.md`, `human_decision.md`, this plan's checkboxes

- [x] **Step 1** README: P4 status line, test count, limitations (real-corpus merge never fires; 78% metric-free values; tables not read).
- [x] **Step 2** architect: ADR-020 (block-level scope inheritance), ADR-021 (value in identity so merging cannot erase P5's signal), ADR-022 (`UNSUPPORTED` means no evidence), stage table P4 ✅, limitations.
- [x] **Step 3** human_decision: HD-010 (P4 scope = claim synthesis only; the probe-driven redesign is recorded as an ADR, not a human decision).
- [x] **Step 4** tick every checkbox above.
- [x] **Step 5** Commit + tag `w3-p4`.

---

## Self-Review

- **Spec coverage:** §4 → Task 3; §5 → Task 4; §6 → Task 5; §7 → Tasks 1–2; §8 → Task 6; §9 → Task 7; §11 → tests in Tasks 3–7; §12 → Task 8 limitations.
- **Placeholders:** none; every code step shows the code.
- **Type consistency:** `BlockScope(task, datasets, inherited_from)`; `ClaimIdentity.key()` / `.label()`; `extract_identity(text, *, source_version_id, scope, quantitative)`; `may_merge(a, b)`; `classify_claim(text, identity, evidence, quant_by_evidence)`; `Claim.identity_key`.
- **Known deviation:** the spec's acceptance #8 lists `Rain100L … 0.11 dB` as `quantitative_unstructured`, but Task 2's delta channel structures exactly that sentence. Task 2 wins: the flag example moves to `test_claim_status.py`, and the spec/acceptance must be updated in Task 8.
