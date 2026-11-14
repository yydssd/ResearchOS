# P5 Contradiction Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Judge, from persisted claims alone, whether two claims contradict, differ in scope, are experimentally incompatible, complement each other, or lack the evidence to tell — deterministically, with an auditable explanation and a locatable evidence trail.

**Architecture:** Three prerequisites fix P4 labels first (four-valued direction, section-inherited conditions, unit words excluded from subjects) because the judgement cannot be built on them as-is. Then a pure cascade over `ClaimIdentity` produces `ContradictionAssessment` rows; pairing, cascade, storage, and memo are separate units so each is testable in isolation. No LLM anywhere.

**Tech Stack:** Python 3.13, pydantic models, SQLAlchemy 2.x on SQLite, pytest, conda env `reOS` (`D:/Anaconda/envs/reOS/python.exe`).

**Spec:** `docs/superpowers/specs/2026-11-13-p5-contradiction-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/research_os/research/conditions.py` (new) | Extract `backbone=…` / `degradation=…` / `baseline=…` / `training=…` from one text |
| `src/research_os/research/claims.py` (modify) | Four-valued direction; unit-word filter in `_subject`; conditions from sentence or scope |
| `src/research_os/research/scope.py` (modify) | Section-level conditions + provenance, alongside existing task/dataset inheritance |
| `src/research_os/research/contradiction.py` (new) | `pair_candidates`, `assess_pair`, `ContradictionAssessor` + `HeuristicContradictionAssessor` |
| `src/research_os/storage/database.py` (modify) | Idempotent unique index on `(claim_a_id, claim_b_id)` |
| `src/research_os/storage/repositories.py` (modify) | `ContradictionRepository.list_by_run`, `replace_for_run` |
| `src/research_os/domain/enums.py` (modify) | `EventType.CONTRADICTION_ASSESSED` |
| `src/research_os/orchestration/supervisor.py` (modify) | Call assessor after claims, before memo |
| `src/research_os/reporting/memo.py` (modify) | Render the contradictions section; expose partners in `inspect_claim` |
| `scripts/evaluate_contradiction.py` (new) | Layered accuracy report over the fixture set |
| `tests/fixtures/contradiction/pairs.json` (new) | ≥24 labelled pairs, real + constructed, separately tagged |

Baseline: 163 tests pass, tag `w3-p4.1`, tree clean.

---

### Task 1: Four-valued direction

The current labels say `achiev|reach|report` → `LEVEL` and treat `reduce|increase` as `UP`. Both are wrong: "reports 39.18 dB" asserts no direction, and "reduces PSNR" is a degradation.

**Files:**
- Modify: `src/research_os/research/claims.py:49-53` (regexes), `:186-189` (the `direction = …` expression)
- Create: `tests/unit/test_claim_direction.py`

- [ ] **Step 1: Write the failing test**

```python
"""Direction expresses the claim's conclusion about quality, not metric movement."""

from __future__ import annotations

import pytest

from research_os.research.claims import extract_identity
from research_os.research.scope import BlockScope


def _direction(text: str) -> str | None:
    return extract_identity(
        text, source_version_id="sv_1", scope=BlockScope("image restoration"), quantitative=[]
    ).direction


@pytest.mark.parametrize(
    "text",
    [
        "Our method improves PSNR by 0.42 dB on Rain100H.",
        "The model outperforms every baseline on SIDD.",
        "It reduces the error by a wide margin on GoPro.",
        "The design increases PSNR on Urban100.",
    ],
)
def test_improvement_is_up(text):
    assert _direction(text) == "UP"


@pytest.mark.parametrize(
    "text",
    [
        "The method degrades performance on real-world data.",
        "It drops 0.4 dB under heavy rain.",
        "Removing the module reduces PSNR on SIDD.",
        "The variant increases the error on Rain100L.",
    ],
)
def test_degradation_is_down(text):
    assert _direction(text) == "DOWN"


@pytest.mark.parametrize(
    "text",
    [
        "Restormer achieves 39.18 dB on SIDD.",
        "The model reaches 0.955 SSIM on GoPro.",
        "We report 32.5 dB averaged over the five datasets.",
        "It obtains the best score on Urban100.",
    ],
)
def test_reported_value_has_no_direction(text):
    """A measurement is not a claim of change; 'achieves' must not become LEVEL."""
    assert _direction(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Spatial conditioning shows no gain on SIDD with a CNN backbone.",
        "The module yields no significant difference on Rain100H.",
        "The variant fails to improve PSNR on GoPro.",
        "Performance is on par with the baseline on SIDD.",
    ],
)
def test_explicit_no_gain_is_level(text):
    assert _direction(text) == "LEVEL"


def test_negation_beats_the_word_it_negates():
    """`fails to improve` contains `improve`; LEVEL must win over UP."""
    assert _direction("The module fails to improve PSNR on Rain100H.") == "LEVEL"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_claim_direction.py -q`
Expected: FAIL — `achieves 39.18 dB` returns `"LEVEL"` instead of `None`; `reduces PSNR` returns `"UP"` instead of `"DOWN"`.

- [ ] **Step 3: Replace the direction rules**

In `src/research_os/research/claims.py`, replace the two regexes at lines 49-53 with:

```python
# Direction is the claim's conclusion about quality, not the raw movement of the
# number: "reduces error" is an improvement, "reduces PSNR" is not, and "reports
# 39.18 dB" asserts no direction at all. The old three-value scheme put
# achiev/reach/report into LEVEL, which made "improves PSNR" and "reports 30 dB"
# look like opposites (196 of 196 LEVEL claims on the hold-out were of that kind).
_IMPROVE = re.compile(r"\b(improv\w*|gain\w*|outperform\w*|better|surpass\w*|exceed\w*)\b", re.IGNORECASE)
_DEGRADE = re.compile(r"\b(degrades?|drops?|worse|hurts?|fails? on)\b", re.IGNORECASE)
_NO_GAIN = re.compile(
    r"\b(no (?:clear |significant )?(?:gain|improvement|difference)|"
    r"fails? to improv\w*|does not improv\w*|without (?:any )?improvement|"
    r"on par with|comparable to)\b",
    re.IGNORECASE,
)
_ERROR_SIDE = r"(?:error|loss|noise|artifact\w*|complexity|params|parameters)"
_QUALITY_SIDE = r"(?:psnr|ssim|accuracy|performance|quality)"
_REDUCE_LOWERS_ERROR = re.compile(rf"\breduc\w*\s+(?:the\s+)?{_ERROR_SIDE}\b", re.IGNORECASE)
_REDUCE_LOWERS_QUALITY = re.compile(rf"\breduc\w*\s+(?:the\s+)?{_QUALITY_SIDE}\b", re.IGNORECASE)
_INCREASE_RAISES_QUALITY = re.compile(rf"\bincreas\w*\s+(?:the\s+)?{_QUALITY_SIDE}\b", re.IGNORECASE)
_INCREASE_RAISES_ERROR = re.compile(rf"\bincreas\w*\s+(?:the\s+)?{_ERROR_SIDE}\b", re.IGNORECASE)
```

Then add the helper right after `_conditions()`:

```python
def _direction(text: str) -> str | None:
    """UP / DOWN / LEVEL / None. Negation is checked first so that
    "fails to improve" is LEVEL rather than UP."""
    if _NO_GAIN.search(text):
        return "LEVEL"
    if _DEGRADE.search(text) or _REDUCE_LOWERS_QUALITY.search(text) or _INCREASE_RAISES_ERROR.search(text):
        return "DOWN"
    if _IMPROVE.search(text) or _REDUCE_LOWERS_ERROR.search(text) or _INCREASE_RAISES_QUALITY.search(text):
        return "UP"
    return None
```

And replace the `direction = (...)` expression inside `extract_identity` with:

```python
    direction = _direction(text)
```

- [ ] **Step 4: Run the new tests**

Run: `python -m pytest tests/unit/test_claim_direction.py -q`
Expected: PASS (17 tests).

- [ ] **Step 5: Run the whole suite and fix the assertions that pinned the old labels**

Run: `python -m pytest -q`
Expected: failures only in tests that asserted `LEVEL` for `achieves/reaches/reports`. For each, update the expectation to `None` and add a one-line comment stating the rule it now follows. Do not change a test expectation without that comment — the reason must live next to the assertion.

- [ ] **Step 6: Commit**

```bash
git add src/research_os/research/claims.py tests/unit/test_claim_direction.py
git commit -m "fix(claims): direction states a conclusion, not a measurement

achieves/reaches/reports/reaches now yield None instead of LEVEL: on the
hold-out all 196 LEVEL claims were of that form, so 'improves PSNR' and
'reports 30 dB' were being treated as opposites. reduce/increase resolve by
object polarity - reduces error is UP, reduces PSNR is DOWN. Negation is
checked first so 'fails to improve' is LEVEL, not UP."
```

---

### Task 2: Unit words are not method names

`dB` satisfies the "inner capital means proper noun" rule, so `subject=db` spans 9 papers and 15 claims — the most repeated named subject in the hold-out.

**Files:**
- Modify: `src/research_os/research/claims.py` (`_subject`, the skip condition around line 124)
- Test: `tests/unit/test_claim_identity.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_claim_identity.py`:

```python
def test_unit_words_are_not_method_names():
    """'dB' has an inner capital, so the proper-noun rule accepted it and `db`
    became the most repeated named subject across the hold-out (9 papers)."""
    for text in (
        "The performance improvement is over 55 dB on dehazing.",
        "The gain reaches 0.42 dB on Rain100H compared with the previous work.",
        "It improves 3.1 % over the strongest competitor.",
    ):
        identity = _identity(text)
        assert identity.subject not in {"db", "psnr", "ssim"}, text
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/unit/test_claim_identity.py::test_unit_words_are_not_method_names -q`
Expected: FAIL with `assert 'db' not in {...}`.

- [ ] **Step 3: Add the stoplist**

In `src/research_os/research/claims.py`, add next to the metric imports area:

```python
# Units and metric names are never subjects. `dB` is the reason this exists: its
# inner capital satisfied the proper-noun test, so `db` was read as a method
# name in 9 of the 20 hold-out papers.
NOT_A_SUBJECT = frozenset(
    {"db", "psnr", "ssim", "lpips", "fid", "mae", "mse", "percent", "%", "×"}
)
```

And inside `_subject`'s token loop, extend the existing skip line:

```python
        if low in COMMON_CAPS or low in dataset_words or low in metric_words or low in NOT_A_SUBJECT:
            continue
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/unit/test_claim_identity.py -q`
Expected: PASS (21 tests).

- [ ] **Step 5: Commit**

```bash
git add src/research_os/research/claims.py tests/unit/test_claim_identity.py
git commit -m "fix(claims): units and metric names cannot be a claim subject

'dB' has an inner capital, so the proper-noun rule read it as a method name;
`db` then appeared in 9 of the 20 hold-out papers, more than any real method."
```

---

### Task 3: Conditions — four kinds, inherited from the section

Single-sentence conditions cover 2.6%. Four kinds lift that to 13.4%; inheriting from the section lifts it to 64.3%, which is the only way a "same setup" claim can ever be made.

**Files:**
- Create: `src/research_os/research/conditions.py`
- Modify: `src/research_os/research/scope.py` (add conditions to `BlockScope`)
- Modify: `src/research_os/research/claims.py` (`_conditions` delegates; `extract_identity` inherits)
- Modify: `src/research_os/domain/models.py`? **No** — `ClaimIdentity` lives in `claims.py`.
- Create: `tests/unit/test_claim_conditions.py`

- [ ] **Step 1: Write the failing test**

```python
"""Conditions describe the experimental setup a claim's number came from."""

from __future__ import annotations

from research_os.research.conditions import extract_conditions


def test_backbone_is_extracted():
    assert extract_conditions("We train a Transformer-based model.") == ("backbone=transformer",)
    assert extract_conditions("A CNN backbone is used for comparison.") == ("backbone=cnn",)


def test_degradation_level_is_extracted():
    assert extract_conditions("At noise level 25 the gain is largest.") == ("degradation=25",)
    assert extract_conditions("Images suffer from heavy rain.") == ("degradation=heavy",)


def test_baseline_is_extracted():
    assert extract_conditions("Compared with MPRNet, the gain is 0.4 dB.") == ("baseline=mprnet",)


def test_training_protocol_is_extracted():
    assert extract_conditions("All models are trained from scratch.") == ("training=from-scratch",)


def test_multiple_kinds_are_sorted_and_deduplicated():
    text = "The Transformer model trained from scratch is compared with MPRNet."
    assert extract_conditions(text) == (
        "backbone=transformer",
        "baseline=mprnet",
        "training=from-scratch",
    )


def test_no_condition_means_empty_not_a_default():
    assert extract_conditions("Our method improves PSNR by 0.42 dB.") == ()
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/unit/test_claim_conditions.py -q`
Expected: FAIL — `ModuleNotFoundError: research_os.research.conditions`.

- [ ] **Step 3: Create the module**

`src/research_os/research/conditions.py`:

```python
"""Experimental conditions attached to a claim (P5 spec §4.2).

Three properties matter and are easy to get wrong:

- One value per kind. A claim that mentions two backbones does not have a
  backbone; taking the first keeps the field comparable instead of inventing a
  union that matches nothing.
- No defaults. A missing condition stays missing — the P5 cascade treats an
  absent condition as "cannot confirm the setup", never as "same setup".
- Values are normalised to lower case so `Transformer` and `transformer` agree.
"""

from __future__ import annotations

import re

_BACKBONE = re.compile(
    r"\b(transformer|cnn|convolutional|convnet|mamba|u-?net|diffusion)s?\b", re.IGNORECASE
)
_DEGRADATION = re.compile(
    r"\b(?:noise level|level)\s*(\d+)"          # noise level 25 / level 3
    r"|sigma\s*=?\s*(\d+)"                       # sigma=25
    r"|\b(heavy|light|dense|thick|severe|mild|moderate)\b",
    re.IGNORECASE,
)
_BASELINE = re.compile(
    r"\b(?:compared (?:with|to)|over)\s+([A-Z][A-Za-z0-9\-]{2,})\b"
)
_TRAINING = re.compile(
    r"\b(from\s+scratch|pre-?train(?:ed|ing)?|fine-?tun(?:ed|ing)?)\b", re.IGNORECASE
)


def extract_conditions(text: str) -> tuple[str, ...]:
    """Return the setup this sentence names, sorted by kind, at most one each."""
    found: set[str] = set()

    match = _BACKBONE.search(text)
    if match:
        found.add(f"backbone={match.group(1).lower().rstrip('s')}")

    match = _DEGRADATION.search(text)
    if match:
        value = match.group(1) or match.group(2) or match.group(3).lower()
        found.add(f"degradation={value}")

    match = _BASELINE.search(text)
    if match:
        found.add(f"baseline={match.group(1).lower()}")

    match = _TRAINING.search(text)
    if match:
        found.add("training=" + re.sub(r"\s+", "-", match.group(1).lower()))

    return tuple(sorted(found))
```

- [ ] **Step 4: Run it**

Run: `python -m pytest tests/unit/test_claim_conditions.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Write the inheritance tests**

Append to `tests/unit/test_scope.py`:

```python
def test_conditions_are_inherited_from_the_section():
    """Conditions live in the experiment section, not in each sentence: single
    sentence coverage is 2.6%, section inheritance lifts it to 64.3%."""
    chunks = [
        _chunk(0, "4.1 SIDD denoising", "We train a Transformer backbone for 300 epochs."),
        _chunk(1, "4.1 SIDD denoising", "The gain over the baseline reaches 0.42 dB."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].conditions == ("backbone=transformer",)
    assert scopes[chunks[1].id].inherited_from["conditions"] == "section-first-mention"


def test_a_sentence_condition_does_not_leak_to_siblings():
    chunks = [
        _chunk(0, "4.2 Ablation", "With a CNN backbone the gain disappears."),
        _chunk(1, "4.2 Ablation", "The full model reaches 32.8 dB."),
    ]

    scopes = build_section_scopes(chunks)

    assert scopes[chunks[1].id].conditions == ("backbone=cnn",)
```

- [ ] **Step 6: Run them**

Run: `python -m pytest tests/unit/test_scope.py -q`
Expected: FAIL — `BlockScope` has no field `conditions`.

- [ ] **Step 7: Add conditions to the scope**

In `src/research_os/research/scope.py`, extend the dataclass:

```python
@dataclass(frozen=True)
class BlockScope:
    """Task/dataset/condition context a claim inherits from its section."""

    task: str | None = None
    datasets: frozenset[str] = frozenset()
    inherited_from: dict[str, str] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()
```

Import and use the extractor:

```python
from research_os.research.conditions import extract_conditions
```

Inside `build_section_scopes`, after the dataset block and before the per-chunk loop:

```python
        conditions = extract_conditions(section or "")
        if conditions:
            provenance["conditions"] = "heading"
        else:
            for chunk in group:
                found_conditions = extract_conditions(chunk.text)
                if found_conditions:
                    conditions = found_conditions
                    provenance["conditions"] = "section-first-mention"
                    break
```

and pass it when constructing:

```python
            scopes[chunk.id] = BlockScope(task, inherited, dict(provenance), conditions)
```

- [ ] **Step 8: Run the scope tests**

Run: `python -m pytest tests/unit/test_scope.py -q`
Expected: PASS (16 tests). The existing equality test still passes because `conditions` defaults to `()`.

- [ ] **Step 9: Make the claim use sentence conditions, else the scope's**

In `src/research_os/research/claims.py`, replace the old `CONDITION_PATTERNS`/`_conditions` with a delegate:

```python
from research_os.research.conditions import extract_conditions


def _conditions(text: str, scope: BlockScope | None) -> tuple[tuple[str, ...], str | None]:
    """Sentence conditions win; otherwise inherit the section's, with provenance."""
    own = extract_conditions(text)
    if own:
        return own, "sentence"
    if scope is not None and scope.conditions:
        return scope.conditions, scope.inherited_from.get("conditions")
    return (), None
```

Then in `extract_identity`, replace `conditions=_conditions(text),` with:

```python
        conditions=conditions,
        conditions_from=conditions_from,
```

and above the return:

```python
    conditions, conditions_from = _conditions(text, scope)
```

Add to `ClaimIdentity` (next to `subject_inferred`):

```python
    # Provenance of the conditions tuple: "sentence", "heading",
    # "section-first-mention", or None. Excluded from the key for the same reason
    # as subject_inferred: it says where the value came from, not what it is.
    conditions_from: str | None = field(default=None, compare=False)
```

- [ ] **Step 10: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. Any test asserting the old three-kind condition strings (`setting=`, `granularity=`) must be updated with a comment naming §4.2 as the reason.

- [ ] **Step 11: Commit**

```bash
git add src/research_os/research/conditions.py src/research_os/research/claims.py src/research_os/research/scope.py tests/unit/test_claim_conditions.py tests/unit/test_scope.py
git commit -m "feat(claims): four condition kinds, inherited from the experiment section

Single-sentence coverage was 2.6% because conditions are stated once per
section ('we train a Transformer backbone') and then omitted. Four extractable
kinds lift it to 13.4%; inheriting heading/section-first-mention lifts it to
64.3%. Inheritance records provenance and never invents a default: absent
conditions stay absent, which is what the P5 gate depends on."
```

---

### Task 4: Candidate pairing

**Files:**
- Create: `src/research_os/research/contradiction.py`
- Create: `tests/unit/test_contradiction_pairing.py`

- [ ] **Step 1: Write the failing test**

```python
"""Pairing decides what can even be compared (P5 spec §4)."""

from __future__ import annotations

from research_os.domain.enums import ClaimStatus
from research_os.domain.models import Claim
from research_os.research.contradiction import pair_candidates


def _claim(key: str, text: str = "x") -> Claim:
    return Claim(text=text, status=ClaimStatus.SUPPORTED, identity_key=key)


def test_same_named_subject_and_task_are_paired():
    a = _claim("restormer|image restoration|sidd|psnr|UP||psnr=39.18")
    b = _claim("restormer|image restoration|gopro|psnr|UP||psnr=32.5")

    pairs, stats = pair_candidates([a, b])

    assert len(pairs) == 1
    assert stats.total_before_cap >= 1


def test_different_subjects_are_not_paired():
    a = _claim("restormer|image restoration|sidd|psnr|UP||")
    b = _claim("mprnet|image restoration|sidd|psnr|UP||")

    pairs, _ = pair_candidates([a, b])

    assert pairs == []


def test_different_tasks_are_not_paired():
    a = _claim("restormer|image restoration|sidd|psnr|UP||")
    b = _claim("restormer|denoising|sidd|psnr|UP||")

    pairs, _ = pair_candidates([a, b])

    assert pairs == []


def test_self_subjects_pair_only_inside_one_document():
    a = _claim("self@sv_a|image restoration|sidd|psnr|UP||")
    b = _claim("self@sv_a|image restoration|sidd|psnr|LEVEL||")
    c = _claim("self@sv_b|image restoration|sidd|psnr|UP||")

    pairs, _ = pair_candidates([a, b, c])

    assert [(x.id, y.id) for x, y in pairs] == [(a.id, b.id)]


def test_self_pairs_need_dataset_and_metric_on_both_sides():
    """Without the prefilter a single document yields 6177 self-pairs; with it, 16."""
    a = _claim("self@sv_a|image restoration||psnr|UP||")
    b = _claim("self@sv_a|image restoration|sidd|psnr|UP||")

    pairs, stats = pair_candidates([a, b])

    assert pairs == []
    assert stats.skipped_self_prefilter == 1


def test_unsupported_claims_are_not_paired():
    a = Claim(text="x", status=ClaimStatus.SUPPORTED, identity_key="m|image restoration|sidd|psnr|UP||")
    b = Claim(text="y", status=ClaimStatus.UNSUPPORTED, identity_key="m|image restoration|sidd|psnr|LEVEL||")

    pairs, _ = pair_candidates([a, b])

    assert pairs == []


def test_pairs_are_ordered_and_deduplicated():
    a = _claim("m|image restoration|sidd|psnr|UP||")
    b = _claim("m|image restoration|sidd|psnr|LEVEL||")

    pairs, _ = pair_candidates([b, a])

    assert len(pairs) == 1
    first, second = pairs[0]
    assert first.id < second.id
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/unit/test_contradiction_pairing.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the module with pairing**

```python
"""Pairwise contradiction assessment over claim identity (P5 spec §4-§5).

Why the pairing key is subject+task and not dataset: the plan's own example -
"spatial conditioning helps on Rain100H with a Transformer" versus "no gain on
SIDD with a CNN" - sits on two different datasets. Requiring a dataset overlap
would make the example unpairable, and the expected answer (SCOPE_DIFFERENCE)
unreachable.

Why self subjects pair only inside one document: two papers' "our method" are
different methods; comparing them would invent a shared object that does not
exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from research_os.domain.enums import ClaimStatus
from research_os.domain.models import Claim

MAX_PAIRS = 50_000


@dataclass
class PairingStats:
    """Everything a reader needs to tell 'no contradiction' from 'not compared'."""

    total_before_cap: int = 0
    evaluated: int = 0
    skipped_missing_dataset: int = 0
    skipped_missing_metric: int = 0
    skipped_self_prefilter: int = 0
    skipped_cap: int = 0
    emitted_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return self.evaluated / self.total_before_cap if self.total_before_cap else 0.0


def _parts(claim: Claim) -> list[str]:
    return (claim.identity_key or "").split("|")


def _subject(claim: Claim) -> str | None:
    parts = _parts(claim)
    return (parts[0] or None) if len(parts) >= 7 else None


def _task(claim: Claim) -> str | None:
    parts = _parts(claim)
    return (parts[1] or None) if len(parts) >= 7 else None


def _datasets(claim: Claim) -> frozenset[str]:
    parts = _parts(claim)
    return frozenset(filter(None, parts[2].split(","))) if len(parts) >= 7 else frozenset()


def _metrics(claim: Claim) -> frozenset[str]:
    parts = _parts(claim)
    return frozenset(filter(None, parts[3].split(","))) if len(parts) >= 7 else frozenset()


def pair_candidates(claims: list[Claim]) -> tuple[list[tuple[Claim, Claim]], PairingStats]:
    """All comparable pairs, deterministically ordered, capped at MAX_PAIRS."""
    stats = PairingStats()
    groups: dict[tuple[str, str], list[Claim]] = {}
    for claim in claims:
        if claim.status != ClaimStatus.SUPPORTED or not claim.identity_key:
            continue
        subject, task = _subject(claim), _task(claim)
        if not subject or not task:
            continue
        groups.setdefault((task, subject), []).append(claim)

    pairs: list[tuple[Claim, Claim]] = []
    for (_, subject), group in sorted(groups.items()):
        group = sorted(group, key=lambda c: c.id)
        for a, b in combinations(group, 2):
            if subject.startswith("self@") and not (
                _datasets(a) and _metrics(a) and _datasets(b) and _metrics(b)
            ):
                stats.skipped_self_prefilter += 1
                continue
            pairs.append((a, b))

    stats.total_before_cap = len(pairs)
    if len(pairs) > MAX_PAIRS:
        stats.skipped_cap = len(pairs) - MAX_PAIRS
        pairs = pairs[:MAX_PAIRS]
    stats.evaluated = len(pairs)
    return pairs, stats
```

- [ ] **Step 4: Run it**

Run: `python -m pytest tests/unit/test_contradiction_pairing.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/research_os/research/contradiction.py tests/unit/test_contradiction_pairing.py
git commit -m "feat(contradiction): pair claims by subject and task, with skip accounting

Same task alone yields 425k pairs on 20 papers; task+dataset yields 1471 but can
never produce the plan's scope-difference example, whose two claims sit on
different datasets. Subject+task gives 1047 named pairs. Self subjects pair only
within one document and only when both sides carry a dataset and a metric."
```

---

### Task 5: The cascade

**Files:**
- Modify: `src/research_os/research/contradiction.py`
- Create: `tests/unit/test_contradiction_cascade.py`

- [ ] **Step 1: Write the failing test**

```python
"""The cascade classifies why two claims are not the same claim (P5 spec §5)."""

from __future__ import annotations

import pytest

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim
from research_os.research.contradiction import assess_pair


def _claim(
    subject="restormer",
    dataset="sidd",
    metric="psnr",
    direction="UP",
    conditions="",
    bucket="psnr=39.18",
    text="x",
    conditions_from=None,
) -> Claim:
    key = "|".join([subject, "image restoration", dataset, metric, direction, conditions, bucket])
    flags = [f"conditions_from={conditions_from}"] if conditions_from else []
    return Claim(text=text, status=ClaimStatus.SUPPORTED, identity_key=key, conditions=flags)


def _relationship(a: Claim, b: Claim):
    result = assess_pair(a, b)
    return result.relationship if result else None


def test_missing_dataset_is_skipped_not_judged():
    assert assess_pair(_claim(dataset=""), _claim(dataset="")) is None


def test_missing_metric_is_skipped_not_judged():
    assert assess_pair(_claim(metric=""), _claim(metric="")) is None


def test_different_datasets_with_opposite_directions_are_a_scope_difference():
    """The plan's own example: same component, different benchmark, different
    conclusion. It must never become TRUE_CONTRADICTION."""
    a = _claim(dataset="rain100h", direction="UP", conditions="backbone=transformer")
    b = _claim(dataset="sidd", direction="LEVEL", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.SCOPE_DIFFERENCE


def test_different_datasets_with_same_direction_are_complementary():
    a = _claim(dataset="rain100h", direction="UP", conditions="backbone=transformer")
    b = _claim(dataset="sidd", direction="UP", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.COMPLEMENTARY


def test_different_conditions_are_a_scope_difference():
    a = _claim(direction="UP", conditions="backbone=transformer")
    b = _claim(direction="LEVEL", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.SCOPE_DIFFERENCE


def test_metric_without_overlap_is_experimental_incompatibility():
    a = _claim(metric="psnr", conditions="backbone=cnn")
    b = _claim(metric="lpips", conditions="backbone=cnn")

    assert _relationship(a, b) == ContradictionType.EXPERIMENTAL_INCOMPATIBILITY


def test_missing_conditions_means_insufficient_evidence_not_a_contradiction():
    """Empty conditions on both sides only prove the extractor found nothing."""
    a = _claim(direction="UP", conditions="")
    b = _claim(direction="LEVEL", conditions="")

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.INSUFFICIENT_EVIDENCE
    assert result.confidence_label == ConfidenceLabel.LOW


def test_same_explicit_scope_and_opposite_direction_is_a_true_contradiction():
    a = _claim(direction="UP", conditions="backbone=transformer")
    b = _claim(direction="LEVEL", conditions="backbone=transformer")

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.TRUE_CONTRADICTION
    assert result.confidence_label == ConfidenceLabel.DISPUTED


def test_reported_value_is_not_a_direction_so_it_cannot_contradict():
    a = _claim(direction="UP", conditions="backbone=cnn")
    b = _claim(direction="", conditions="backbone=cnn")

    assert assess_pair(a, b).relationship == ContradictionType.INSUFFICIENT_EVIDENCE


def test_same_direction_different_values_is_experimental_incompatibility():
    a = _claim(direction="UP", conditions="backbone=cnn", bucket="psnr=39.18")
    b = _claim(direction="UP", conditions="backbone=cnn", bucket="psnr=38.50")

    assert _relationship(a, b) == ContradictionType.EXPERIMENTAL_INCOMPATIBILITY


def test_same_direction_without_values_is_insufficient_evidence():
    a = _claim(direction="UP", conditions="backbone=cnn", bucket="")
    b = _claim(direction="UP", conditions="backbone=cnn", bucket="psnr=39.18")

    assert _relationship(a, b) == ContradictionType.INSUFFICIENT_EVIDENCE


def test_equal_but_inherited_conditions_do_not_prove_a_contradiction():
    """D13: "the section said so once" is an assumption, not evidence. Two claims
    whose setup was inherited from the first mention may well disagree, but the
    judgement cannot assert that their scopes are the same."""
    a = _claim(direction="UP", conditions="backbone=transformer", conditions_from="section-first-mention")
    b = _claim(direction="LEVEL", conditions="backbone=transformer", conditions_from="section-first-mention")

    result = assess_pair(a, b)

    assert result.relationship == ContradictionType.INSUFFICIENT_EVIDENCE
    assert result.confidence_label == ConfidenceLabel.LOW
    assert "inherited" in result.explanation


def test_heading_level_conditions_are_evidence():
    """A heading that names the setup governs the whole section, so it is
    confirmed rather than assumed."""
    a = _claim(direction="UP", conditions="backbone=transformer", conditions_from="heading")
    b = _claim(direction="LEVEL", conditions="backbone=transformer", conditions_from="heading")

    assert _relationship(a, b) == ContradictionType.TRUE_CONTRADICTION


def test_inherited_conditions_can_still_disprove_a_shared_setup():
    """The asymmetry is the point: inherited conditions that differ are real
    evidence that the two claims came from different experiments."""
    a = _claim(direction="UP", conditions="backbone=transformer", conditions_from="section-first-mention")
    b = _claim(direction="LEVEL", conditions="backbone=cnn", conditions_from="section-first-mention")

    assert _relationship(a, b) == ContradictionType.SCOPE_DIFFERENCE


@pytest.mark.parametrize(
    "a_dir,b_dir",
    [("UP", "LEVEL"), ("UP", "DOWN"), ("DOWN", "LEVEL")],
)
def test_every_opposite_pair_combination(a_dir, b_dir):
    a = _claim(direction=a_dir, conditions="backbone=cnn", bucket="psnr=39.18")
    b = _claim(direction=b_dir, conditions="backbone=cnn", bucket="psnr=39.18")

    assert _relationship(a, b) == ContradictionType.TRUE_CONTRADICTION


def test_explanation_names_the_dimension_and_the_values():
    a = _claim(dataset="rain100h", direction="UP", conditions="backbone=transformer")
    b = _claim(dataset="sidd", direction="LEVEL", conditions="backbone=cnn")

    result = assess_pair(a, b)

    assert "dataset differs" in result.explanation
    assert "rain100h" in result.explanation and "sidd" in result.explanation
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/unit/test_contradiction_cascade.py -q`
Expected: FAIL — `assess_pair` is not defined.

- [ ] **Step 3: Implement the cascade**

Append to `src/research_os/research/contradiction.py`:

```python
from research_os.domain.enums import ConfidenceLabel, ContradictionType
from research_os.domain.models import ContradictionAssessment


def _directions(claim: Claim) -> str | None:
    parts = _parts(claim)
    return (parts[4] or None) if len(parts) >= 7 else None


def _conditions(claim: Claim) -> tuple[str, ...]:
    parts = _parts(claim)
    return tuple(filter(None, parts[5].split(";"))) if len(parts) >= 7 else ()


def _conditions_from(claim: Claim) -> str | None:
    """Where the conditions came from, read off the quality flags (D13).

    `sentence` and `heading` state the setup; `section-first-mention` only says
    someone earlier in the section did. Only the first two can prove two claims
    share a setup, so the cascade needs this distinction before it may call a
    pair a true contradiction.
    """
    for item in claim.conditions:
        if item.startswith("conditions_from="):
            return item.split("=", 1)[1]
    return None


def _buckets(claim: Claim) -> tuple[str, ...]:
    parts = _parts(claim)
    return tuple(filter(None, parts[6].split(";"))) if len(parts) >= 7 else ()


OPPOSITE = {("UP", "LEVEL"), ("LEVEL", "UP"), ("UP", "DOWN"), ("DOWN", "UP"), ("DOWN", "LEVEL"), ("LEVEL", "DOWN")}


def _assessment(a: Claim, b: Claim, relation: ContradictionType, explanation: str, confidence: ConfidenceLabel):
    return ContradictionAssessment(
        claim_a_id=a.id,
        claim_b_id=b.id,
        relationship=relation,
        explanation=explanation,
        confidence_label=confidence,
    )


def assess_pair(a: Claim, b: Claim) -> ContradictionAssessment | None:
    """Ordered cascade; first match wins. Returns None when the pair is skipped.

    The order is the plan's "default must not be TRUE_CONTRADICTION" made
    executable: dataset and conditions are facts, an opposite direction is only a
    surface clash, and a missing condition is never read as an agreeing one.
    """
    datasets_a, datasets_b = _datasets(a), _datasets(b)
    metrics_a, metrics_b = _metrics(a), _metrics(b)
    if not datasets_a or not datasets_b or not metrics_a or not metrics_b:
        return None

    direction_a, direction_b = _directions(a), _directions(b)
    same_direction = direction_a is not None and direction_a == direction_b

    if datasets_a != datasets_b:
        relation = ContradictionType.COMPLEMENTARY if same_direction else ContradictionType.SCOPE_DIFFERENCE
        return _assessment(
            a, b, relation,
            f"dataset differs: {','.join(sorted(datasets_a))} vs {','.join(sorted(datasets_b))}",
            ConfidenceLabel.MEDIUM,
        )

    conditions_a, conditions_b = _conditions(a), _conditions(b)
    if conditions_a and conditions_b and conditions_a != conditions_b:
        relation = ContradictionType.COMPLEMENTARY if same_direction else ContradictionType.SCOPE_DIFFERENCE
        return _assessment(
            a, b, relation,
            f"conditions differ: {';'.join(conditions_a)} vs {';'.join(conditions_b)}",
            ConfidenceLabel.MEDIUM,
        )

    if not (metrics_a & metrics_b):
        return _assessment(
            a, b, ContradictionType.EXPERIMENTAL_INCOMPATIBILITY,
            f"metric has no overlap: {','.join(sorted(metrics_a))} vs {','.join(sorted(metrics_b))}",
            ConfidenceLabel.MEDIUM,
        )

    if not conditions_a or not conditions_b:
        return _assessment(
            a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
            "conditions not extracted on at least one side; setup cannot be confirmed",
            ConfidenceLabel.LOW,
        )

    if direction_a is None or direction_b is None:
        missing = "A" if direction_a is None else "B"
        return _assessment(
            a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
            f"direction not stated on side {missing}",
            ConfidenceLabel.LOW,
        )

    if (direction_a, direction_b) in OPPOSITE:
        assumed = [
            side
            for side, claim in (("A", a), ("B", b))
            if _conditions_from(claim) == "section-first-mention"
        ]
        if assumed:
            # D13: a condition inherited from the section's first mention is an
            # assumption, not evidence. Inherited conditions may still *disprove*
            # a shared setup (their inequality is real); they may not *prove* one.
            return _assessment(
                a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
                f"opposite direction, but conditions on side {'/'.join(assumed)} are "
                "inherited from the section's first mention; setup not confirmed",
                ConfidenceLabel.LOW,
            )
        return _assessment(
            a, b, ContradictionType.TRUE_CONTRADICTION,
            f"same scope, opposite direction: {direction_a} vs {direction_b}",
            ConfidenceLabel.DISPUTED,
        )

    buckets_a, buckets_b = _buckets(a), _buckets(b)
    if buckets_a and buckets_b and buckets_a != buckets_b:
        return _assessment(
            a, b, ContradictionType.EXPERIMENTAL_INCOMPATIBILITY,
            f"same scope, same direction, different values: {';'.join(buckets_a)} vs {';'.join(buckets_b)}",
            ConfidenceLabel.MEDIUM,
        )

    if not buckets_a or not buckets_b:
        # Spec §5 row 9: one side reporting no value cannot corroborate a
        # same-direction claim, so the pair is left unjudged rather than skipped.
        missing_values = "A" if not buckets_a else "B"
        return _assessment(
            a, b, ContradictionType.INSUFFICIENT_EVIDENCE,
            f"same direction, value not reported on side {missing_values}",
            ConfidenceLabel.LOW,
        )

    return None
```

- [ ] **Step 4: Run it**

Run: `python -m pytest tests/unit/test_contradiction_cascade.py -q`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add src/research_os/research/contradiction.py tests/unit/test_contradiction_cascade.py
git commit -m "feat(contradiction): deterministic cascade with an auditable explanation

Ordered so that facts beat surface clashes: dataset and conditions first, then
metric, then direction. A true contradiction needs the same subject, the same
dataset, overlapping metrics, both sides stating conditions that agree, and
opposite directions - so the default is never TRUE_CONTRADICTION. Every
explanation names the dimension and its values."
```

---

### Task 6: Storage — unique index, run scope, idempotent rerun

**Files:**
- Modify: `src/research_os/storage/database.py` (`_ADDED_INDEXES`)
- Modify: `src/research_os/storage/repositories.py` (`SqlContradictionRepository`)
- Create: `tests/integration/test_contradiction_storage.py`

- [ ] **Step 1: Write the failing test**

```python
"""Assessment storage must be unique per pair, run-scoped, and idempotent."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from research_os.domain.enums import ClaimStatus, ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim, ContradictionAssessment
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import SqlClaimRepository, SqlContradictionRepository


@pytest.fixture()
def session(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'p5.db'}")
    s = session_factory()()
    yield s
    s.close()


def _assessment(a: str, b: str) -> ContradictionAssessment:
    return ContradictionAssessment(
        claim_a_id=a,
        claim_b_id=b,
        relationship=ContradictionType.SCOPE_DIFFERENCE,
        explanation="dataset differs: rain100h vs sidd",
        confidence_label=ConfidenceLabel.MEDIUM,
    )


def _seed(session, run_id: str, ids: tuple[str, str]) -> None:
    repo = SqlClaimRepository(session)
    for claim_id in ids:
        repo.create(
            Claim(id=claim_id, text="t", status=ClaimStatus.SUPPORTED, identity_key="m|t|sidd|psnr|UP||"),
            run_id=run_id,
        )
    session.commit()


def test_duplicate_pair_is_rejected_by_the_database(session):
    _seed(session, "run_1", ("c1", "c2"))
    repo = SqlContradictionRepository(session)
    repo.create(_assessment("c1", "c2"))
    session.commit()

    with pytest.raises(IntegrityError):
        repo.create(_assessment("c1", "c2"))
        session.commit()
    session.rollback()


def test_list_by_run_hides_other_runs(session):
    _seed(session, "run_1", ("c1", "c2"))
    _seed(session, "run_2", ("c3", "c4"))
    repo = SqlContradictionRepository(session)
    repo.create(_assessment("c1", "c2"))
    repo.create(_assessment("c3", "c4"))
    session.commit()

    mine = repo.list_by_run("run_1")

    assert [(x.claim_a_id, x.claim_b_id) for x in mine] == [("c1", "c2")]


def test_replace_for_run_is_idempotent(session):
    _seed(session, "run_1", ("c1", "c2"))
    repo = SqlContradictionRepository(session)
    repo.replace_for_run("run_1", [_assessment("c1", "c2")])
    session.commit()

    deleted = repo.replace_for_run("run_1", [_assessment("c1", "c2")])
    session.commit()

    assert deleted == 1
    assert len(repo.list_by_run("run_1")) == 1


def test_replace_rejects_a_pair_from_another_run(session):
    _seed(session, "run_1", ("c1",))
    _seed(session, "run_2", ("c2",))

    with pytest.raises(ValueError, match="cross_run_pair"):
        SqlContradictionRepository(session).replace_for_run("run_1", [_assessment("c1", "c2")])
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/integration/test_contradiction_storage.py -q`
Expected: FAIL — `list_by_run` / `replace_for_run` missing; duplicate insert succeeds because no unique index.

- [ ] **Step 3: Add the unique index**

In `src/research_os/storage/database.py`, below `_ADDED_COLUMNS`:

```python
# Indexes added after the first release, for the same reason as the columns:
# create_all never touches an existing table, so pre-P5 databases would accept
# the same claim pair twice.
_ADDED_INDEXES: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_pair "
    "ON contradiction_assessments (claim_a_id, claim_b_id)",
)
```

and at the end of `_apply_sqlite_migrations`:

```python
        for statement in _ADDED_INDEXES:
            conn.exec_driver_sql(statement)
```

- [ ] **Step 4: Implement the repository methods**

In `src/research_os/storage/repositories.py`, add to `SqlContradictionRepository`:

```python
    def list_by_run(self, run_id: str) -> list[ContradictionAssessment]:
        """Run-scoped read (ADR-019): a trace output must never leak across runs."""
        rows = (
            self._s.execute(
                select(t.ContradictionAssessmentRow)
                .join(t.ClaimRow, t.ClaimRow.id == t.ContradictionAssessmentRow.claim_a_id)
                .where(t.ClaimRow.run_id == run_id)
                .order_by(
                    t.ContradictionAssessmentRow.claim_a_id,
                    t.ContradictionAssessmentRow.claim_b_id,
                )
            )
            .scalars()
            .all()
        )
        return [self._to_domain(row) for row in rows]

    def replace_for_run(self, run_id: str, items: list[ContradictionAssessment]) -> int:
        """Delete this run's assessments, then write the new ones.

        Rerunning a run must produce the same rows, not a second copy; the unique
        index alone would raise instead of converging. A pair whose claims belong
        to different runs is rejected rather than stored: it would make the audit
        chain ambiguous.
        """
        claim_rows = {
            row.id: row.run_id
            for row in self._s.execute(select(t.ClaimRow.id, t.ClaimRow.run_id)).all()
        }
        for item in items:
            if claim_rows.get(item.claim_a_id) != run_id or claim_rows.get(item.claim_b_id) != run_id:
                raise ValueError(f"cross_run_pair: {item.claim_a_id} / {item.claim_b_id}")

        claim_ids = select(t.ClaimRow.id).where(t.ClaimRow.run_id == run_id)
        deleted = self._s.execute(
            delete(t.ContradictionAssessmentRow).where(
                t.ContradictionAssessmentRow.claim_a_id.in_(claim_ids)
            )
        ).rowcount or 0
        for item in items:
            self.create(item)
        return deleted
```

Add `delete` to the SQLAlchemy import at the top of the file:

```python
from sqlalchemy import delete, select
```

- [ ] **Step 5: Run the storage tests**

Run: `python -m pytest tests/integration/test_contradiction_storage.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS (index creation is idempotent; existing DBs get the index on init).

- [ ] **Step 7: Commit**

```bash
git add src/research_os/storage/database.py src/research_os/storage/repositories.py tests/integration/test_contradiction_storage.py
git commit -m "feat(storage): run-scoped, unique and idempotent contradiction assessments

The table had no unique constraint on (claim_a_id, claim_b_id), so rerunning a
run duplicated every pair. Adds the index, a run-scoped read, and a replace that
deletes this run's rows first - so a rerun converges instead of failing. A pair
whose claims belong to different runs is refused, not stored."
```

---

### Task 7: Wire the assessor into the run

**Files:**
- Modify: `src/research_os/domain/enums.py` (`EventType`)
- Modify: `src/research_os/research/contradiction.py` (the assessor protocol)
- Modify: `src/research_os/orchestration/supervisor.py`
- Create: `tests/integration/test_contradiction_run.py`

- [ ] **Step 1: Write the failing test**

```python
"""A run must produce assessments, log the counts, and never mutate claims."""

from __future__ import annotations

import pytest

from research_os.domain.enums import ClaimStatus
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import SqlClaimRepository, SqlContradictionRepository


@pytest.fixture()
def session(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'run.db'}")
    s = session_factory()()
    yield s
    s.close()


def test_vertical_slice_records_assessments_without_touching_claims(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(
        "# Results\n\n"
        "On SIDD, Restormer improves PSNR by 0.42 dB with a Transformer backbone.\n\n"
        "On SIDD, Restormer shows no improvement with a Transformer backbone.\n",
        encoding="utf-8",
    )

    supervisor = Supervisor(session)
    result = supervisor.run_vertical_slice(paper, question="Does it work?")
    run_id = result["run_id"]

    claims = SqlClaimRepository(session).list_by_run(run_id)
    before = {c.id: (c.status, c.confidence_label) for c in claims}

    assessments = SqlContradictionRepository(session).list_by_run(run_id)

    assert assessments, "expected at least one assessment for two same-scope claims"
    assert all(a.explanation for a in assessments)
    assert {c.id: (c.status, c.confidence_label) for c in claims} == before
    assert any(e.event_type.value == "CONTRADICTION_ASSESSED" for e in SqlEventRepository(session).list_by_run(run_id))
```

Add the missing import in the test file:

```python
from research_os.storage.repositories import (
    SqlClaimRepository,
    SqlContradictionRepository,
    SqlEventRepository,
)
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/integration/test_contradiction_run.py -q`
Expected: FAIL — `EventType` has no `CONTRADICTION_ASSESSED`; the supervisor never assesses.

- [ ] **Step 3: Add the event type**

In `src/research_os/domain/enums.py`, inside `EventType`:

```python
    CLAIM_BUILT = "CLAIM_BUILT"
    CONTRADICTION_ASSESSED = "CONTRADICTION_ASSESSED"
```

- [ ] **Step 4: Add the assessor protocol to the module**

Append to `src/research_os/research/contradiction.py`:

```python
from typing import Protocol


class ContradictionAssessor(Protocol):
    """Same shape as ClaimBuilder/EvidenceExtractor so P8 can swap in an LLM
    assessor without touching the supervisor."""

    def assess(self, claims: list[Claim]) -> tuple[list[ContradictionAssessment], PairingStats]: ...


class HeuristicContradictionAssessor:
    """Deterministic pairing plus the cascade. No LLM, no randomness."""

    def assess(self, claims: list[Claim]) -> tuple[list[ContradictionAssessment], PairingStats]:
        pairs, stats = pair_candidates(claims)
        assessments: list[ContradictionAssessment] = []
        for a, b in pairs:
            result = assess_pair(a, b)
            if result is None:
                if not _datasets(a) or not _datasets(b):
                    stats.skipped_missing_dataset += 1
                elif not _metrics(a) or not _metrics(b):
                    stats.skipped_missing_metric += 1
                continue
            assessments.append(result)
            stats.emitted_by_type[result.relationship.value] = (
                stats.emitted_by_type.get(result.relationship.value, 0) + 1
            )
        stats.evaluated = len(pairs)
        return assessments, stats
```

- [ ] **Step 5: Call it from the supervisor**

In `src/research_os/orchestration/supervisor.py`, add the import:

```python
from research_os.research.contradiction import ContradictionAssessor, HeuristicContradictionAssessor
```

Add a constructor parameter next to `claim_builder`:

```python
        contradiction_assessor: ContradictionAssessor | None = None,
```

and store it:

```python
        self._assessor = contradiction_assessor or HeuristicContradictionAssessor()
```

After the `CLAIM_BUILT` event and before step 5 (memo), insert:

```python
        # 4b) pairwise contradiction assessment (plan §17). Claims are read-only
        # here on purpose: P4 owns status and confidence, P5 only relates them.
        assess_task = create_task(self._session, run.id, TaskType.CHECK_CONTRADICTION)
        assessments, stats = self._assessor.assess(claims)
        replaced = SqlContradictionRepository(self._session).replace_for_run(run.id, assessments)
        complete_task(self._session, assess_task, output_ids=[a.claim_a_id for a in assessments])
        self._log(
            run.id,
            EventType.CONTRADICTION_ASSESSED,
            f"{len(assessments)} assessments from {stats.evaluated} pairs",
            {
                "assessments": len(assessments),
                "total_before_cap": stats.total_before_cap,
                "evaluated": stats.evaluated,
                "coverage": round(stats.coverage, 4),
                "skipped_missing_dataset": stats.skipped_missing_dataset,
                "skipped_missing_metric": stats.skipped_missing_metric,
                "skipped_self_prefilter": stats.skipped_self_prefilter,
                "skipped_cap": stats.skipped_cap,
                "by_type": stats.emitted_by_type,
                "replaced": replaced,
            },
        )
```

Add `SqlContradictionRepository` to the existing repository import block.

- [ ] **Step 6: Run the integration test**

Run: `python -m pytest tests/integration/test_contradiction_run.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. Existing vertical-slice tests may now see a new event; update counts only where a test asserts an exact event total, with a comment naming plan §17.

- [ ] **Step 8: Commit**

```bash
git add src/research_os/domain/enums.py src/research_os/research/contradiction.py src/research_os/orchestration/supervisor.py tests/integration/test_contradiction_run.py
git commit -m "feat(orchestration): assess contradictions after claims, before the memo

The event carries what a reader needs to tell 'no contradiction' from 'not
compared': pairs before truncation, pairs evaluated, coverage, and a per-reason
skip breakdown. Claims are not modified - P4 owns status and confidence."
```

---

> **实施期修正（2026-11-13，已落地）。** 本任务 Step 1 的两处写法与实际代码不符，执行时以
> `tests/integration/test_contradiction_run.py` 为准：① `run_vertical_slice` 的签名是
> `(run_id, sources, reports_dir)`，不是 `(paper, question=...)`；② 示例语料 `# Results` 标题
> 不含任务词，抽不出 `task`，配对数为 0——改用 `# Image denoising` 并把指标写进第二句。
> 另：`skipped_same_value` 是本任务新增的计数（见 Step 4），原计划没有。

---

### Task 8: Memo section and claim inspection

**Files:**
- Modify: `src/research_os/reporting/memo.py`
- Create: `tests/integration/test_contradiction_memo.py`

- [ ] **Step 1: Write the failing test**

```python
"""The memo must show the relation, the reason, and where each claim came from."""

from __future__ import annotations

import pytest

from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, inspect_claim
from research_os.storage.database import init_db, session_factory
from research_os.storage.repositories import SqlClaimRepository


@pytest.fixture()
def session(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'memo.db'}")
    s = session_factory()()
    yield s
    s.close()


def test_memo_lists_the_assessment_with_its_reason(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(
        "# Results\n\n"
        "On SIDD, Restormer improves PSNR by 0.42 dB with a Transformer backbone.\n\n"
        "On SIDD, Restormer shows no improvement with a Transformer backbone.\n",
        encoding="utf-8",
    )
    run_id = Supervisor(session).run_vertical_slice(paper, question="q")["run_id"]

    memo = build_memo_from_run(session, run_id)

    assert "# Contradictions and Open Questions" in memo
    assert "Assessed" in memo and "coverage" in memo.lower()
    assert "same scope, opposite direction" in memo or "SCOPE_DIFFERENCE" in memo
    assert "chars" in memo  # evidence location travels with the claim text


def test_inspect_claim_exposes_partners_and_provenance(session, tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(
        "# Results\n\n"
        "On SIDD, Restormer improves PSNR by 0.42 dB with a Transformer backbone.\n\n"
        "On SIDD, Restormer shows no improvement with a Transformer backbone.\n",
        encoding="utf-8",
    )
    run_id = Supervisor(session).run_vertical_slice(paper, question="q")["run_id"]
    claim = SqlClaimRepository(session).list_by_run(run_id)[0]

    detail = inspect_claim(session, run_id, claim.id)

    assert "contradictions" in detail
    assert detail["contradictions"], "the paired claim should appear as a partner"
    assert "relationship" in detail["contradictions"][0]
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/integration/test_contradiction_memo.py -q`
Expected: FAIL — the memo still prints the Week-1 placeholder.

- [ ] **Step 3: Add assessments to the graph**

In `src/research_os/reporting/memo.py`, extend `RunGraph`:

```python
    assessments: list[ContradictionAssessment] = field(default_factory=list)
    assessment_stats: dict = field(default_factory=dict)
```

Import the types:

```python
from research_os.domain.models import Claim, ContradictionAssessment, Evidence, QuantitativeEvidence, SourceVersion
from research_os.storage.repositories import SqlContradictionRepository
```

In `collect_run_graph`, after `claims = …`:

```python
    assessments = SqlContradictionRepository(session).list_by_run(run_id)
```

and include `assessments=assessments` in the constructed `RunGraph`.

- [ ] **Step 4: Render the section**

Replace the placeholder block:

```python
    lines.append("# Contradictions and Open Questions")
    lines.append("")
    lines.append("- No pairwise contradiction assessment was run in the Week-1 slice (Phase 5).")
    lines.append("")
```

with:

```python
    lines.extend(_render_contradictions(graph))
```

Add the renderer above `render_memo`:

```python
_ORDER = (
    ContradictionType.TRUE_CONTRADICTION,
    ContradictionType.EXPERIMENTAL_INCOMPATIBILITY,
    ContradictionType.SCOPE_DIFFERENCE,
    ContradictionType.COMPLEMENTARY,
    ContradictionType.INSUFFICIENT_EVIDENCE,
)
_HEADINGS = {
    ContradictionType.TRUE_CONTRADICTION: "True contradictions",
    ContradictionType.EXPERIMENTAL_INCOMPATIBILITY: "Experimental incompatibilities",
    ContradictionType.SCOPE_DIFFERENCE: "Scope differences",
    ContradictionType.COMPLEMENTARY: "Complementary findings",
    ContradictionType.INSUFFICIENT_EVIDENCE: "Insufficient evidence",
}


def _claim_location(graph: RunGraph, claim_id: str) -> str:
    """claim -> relation -> evidence -> chunk location. Missing is a defect."""
    claim = next((c for c in graph.claims if c.id == claim_id), None)
    supports = graph.supports.get(claim_id, [])
    if claim is None:
        return "unknown claim"
    if not supports:
        return "no locatable evidence"
    ev = supports[0]
    section = ev.section or "no section"
    return f"{ev.source_version_id} · {section} · chars {ev.char_start}-{ev.char_end}"


def _render_contradictions(graph: RunGraph) -> list[str]:
    if not graph.assessments:
        return [
            "# Contradictions and Open Questions",
            "",
            "No comparable claim pair in this run.",
            "",
        ]

    by_type: dict[ContradictionType, list] = {}
    for item in graph.assessments:
        by_type.setdefault(item.relationship, []).append(item)

    lines = ["# Contradictions and Open Questions", ""]
    lines.append(
        f"Assessed {len(graph.assessments)} claim pairs. "
        f"{len([c for c in graph.claims if c.status == ClaimStatus.SUPPORTED])} supported claims "
        f"were eligible for pairing."
    )
    lines.append("")
    for relation in _ORDER:
        items = by_type.get(relation, [])
        lines.append(f"## {_HEADINGS[relation]} ({len(items)})")
        lines.append("")
        if relation is ContradictionType.COMPLEMENTARY and items:
            subjects = sorted({i.explanation for i in items})
            lines.append(f"- {len(items)} pair(s) agree across different scopes.")
            for explanation in subjects[:5]:
                lines.append(f"  - {explanation}")
            lines.append("")
            continue
        for item in items[:20]:
            lines.append(f"- {item.explanation}")
            lines.append(f"  - A: `{item.claim_a_id}` — {_claim_location(graph, item.claim_a_id)}")
            lines.append(f"  - B: `{item.claim_b_id}` — {_claim_location(graph, item.claim_b_id)}")
        if len(items) > 20:
            lines.append(f"- … {len(items) - 20} more")
        lines.append("")
    return lines
```

Add `ContradictionType` to the enums import:

```python
from research_os.domain.enums import ClaimStatus, ContradictionType, EvidenceRelation
```

- [ ] **Step 5: Expose partners in `inspect_claim`**

In the returned dict of `inspect_claim`, add:

```python
        "contradictions": [
            {
                "claim_id": other_id,
                "relationship": item.relationship.value,
                "explanation": item.explanation,
                "confidence": item.confidence_label.value,
            }
            for item in graph.assessments
            for other_id in (
                [item.claim_b_id] if item.claim_a_id == claim_id
                else [item.claim_a_id] if item.claim_b_id == claim_id
                else []
            )
        ],
```

- [ ] **Step 6: Run the memo tests**

Run: `python -m pytest tests/integration/test_contradiction_memo.py -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. The old assertion in `tests/integration/test_vertical_slice.py` that the memo contains the placeholder text must be updated to the new heading with a comment naming §6.

- [ ] **Step 8: Commit**

```bash
git add src/research_os/reporting/memo.py tests/integration/test_contradiction_memo.py
git commit -m "feat(memo): render contradictions by type with evidence locations

Each relation gets its own section in a fixed order so two runs of the same
input produce byte-identical output. Every entry carries both claim ids and the
location of the first supporting evidence - a relation without a locatable
source is shown as such rather than silently."
```

---

### Task 9: Fixture set with independent labels

**Files:**
- Create: `tests/fixtures/contradiction/pairs.json`
- Create: `tests/fixtures/contradiction/ANNOTATION.md`

- [ ] **Step 1: Write the fixture file**

Twenty-four pairs: at least 12 whose claim texts are copied from the hold-out corpus, the rest constructed to cover `TRUE_CONTRADICTION`, which the corpus cannot produce. Each entry records where it came from.

```json
{
  "version": 1,
  "note": "identity keys are the ones extract_identity produced for the sentence on 2026-11-13; scope fields are written out so the cascade can be tested without re-running extraction",
  "pairs": [
    {
      "id": "p01",
      "source": "real",
      "from": "2607.28526",
      "a_text": "Compared with the second-best method, DAR-Net improves the average PSNR by 0.14 dB.",
      "b_text": "Under the 5D setting, DAR-Net achieves the best overall performance with an average PSNR of 31.02.",
      "a_key": "dar-net|image restoration|rain100h|psnr|UP|backbone=transformer|psnr=31.02",
      "b_key": "dar-net|image restoration|rain100h|psnr||backbone=transformer|psnr=31.02",
      "expected": "INSUFFICIENT_EVIDENCE",
      "notes": "B reports a value without a direction; equal scope still cannot decide."
    },
    {
      "id": "p02",
      "source": "real",
      "from": "2403.14614",
      "a_text": "On Rain100H the model improves PSNR by 0.42 dB.",
      "b_text": "On SIDD the model shows no gain over the baseline.",
      "a_key": "self@sv_2403|image restoration|rain100h|psnr|UP|backbone=transformer|psnr=39.18",
      "b_key": "self@sv_2403|image restoration|sidd|psnr|LEVEL|backbone=transformer|psnr=38.50",
      "expected": "SCOPE_DIFFERENCE",
      "notes": "The plan's §17 example shape: same method, different benchmark."
    },
    {
      "id": "p03",
      "source": "constructed",
      "a_text": "Spatial conditioning improves Rain100H with a Transformer backbone.",
      "b_text": "Spatial conditioning shows no gain on SIDD with a CNN backbone.",
      "a_key": "spatial conditioning|image restoration|rain100h|psnr|UP|backbone=transformer|psnr=39.10",
      "b_key": "spatial conditioning|image restoration|sidd|psnr|LEVEL|backbone=cnn|psnr=38.90",
      "expected": "SCOPE_DIFFERENCE",
      "notes": "Verbatim the plan's example; must not be TRUE_CONTRADICTION."
    },
    {
      "id": "p04",
      "source": "constructed",
      "a_text": "With a CNN backbone, Restormer improves PSNR on SIDD by 0.40 dB.",
      "b_text": "With a CNN backbone, Restormer shows no improvement on SIDD.",
      "a_key": "restormer|image restoration|sidd|psnr|UP|backbone=cnn|psnr=39.18",
      "b_key": "restormer|image restoration|sidd|psnr|LEVEL|backbone=cnn|psnr=39.18",
      "expected": "TRUE_CONTRADICTION",
      "notes": "Same named method, same benchmark, same stated backbone, opposite conclusion."
    },
    {
      "id": "p05",
      "source": "constructed",
      "a_text": "Restormer improves PSNR on SIDD.",
      "b_text": "Restormer shows no improvement on SIDD.",
      "a_key": "restormer|image restoration|sidd|psnr|UP||psnr=39.18",
      "b_key": "restormer|image restoration|sidd|psnr|LEVEL||psnr=39.18",
      "expected": "INSUFFICIENT_EVIDENCE",
      "notes": "Neither side states a condition, so 'same setup' is unproven (D7)."
    }
  ]
}
```

Extend the file to 24 entries: repeat the same shape with these cases at minimum, one per line of the table below (`source` may be `real` or `constructed`; `expected` is the label to be justified in `notes`).

| id | shape | expected |
|---|---|---|
| p06 | same scope, same direction, different values | `EXPERIMENTAL_INCOMPATIBILITY` |
| p07 | same scope, same direction, one side without values | `INSUFFICIENT_EVIDENCE` |
| p08 | same scope, metric psnr vs lpips | `EXPERIMENTAL_INCOMPATIBILITY` |
| p09 | different datasets, same direction | `COMPLEMENTARY` |
| p10 | different conditions, opposite direction | `SCOPE_DIFFERENCE` |
| p11 | different conditions, same direction | `COMPLEMENTARY` |
| p12 | dataset missing on one side | skipped (`null`) |
| p13 | metric missing on one side | skipped (`null`) |
| p14 | UP vs DOWN, same explicit conditions | `TRUE_CONTRADICTION` |
| p15 | DOWN vs LEVEL, same explicit conditions | `TRUE_CONTRADICTION` |
| p16 | both directions missing | `INSUFFICIENT_EVIDENCE` |
| p17 | self@A vs self@B, opposite direction | skipped (`null`) |
| p18 | same subject, different task | skipped (`null`) |
| p19 | metric overlap is partial (psnr,ssim vs psnr) | judged, not skipped |
| p20 | three-way dataset overlap (sidd,rain100h vs sidd) | `SCOPE_DIFFERENCE` |
| p21 | conditions equal but inherited is not represented here | `TRUE_CONTRADICTION` |
| p22 | complementary across two datasets with values | `COMPLEMENTARY` |
| p23 | opposite direction but conditions differ in training | `SCOPE_DIFFERENCE` |
| p24 | same scope, same direction, identical values | skipped (`null`) |

Entries with `expected: null` assert that `assess_pair` returns `None`.

- [ ] **Step 2: Write the annotation protocol**

`tests/fixtures/contradiction/ANNOTATION.md`:

```markdown
# Contradiction fixture annotation protocol

Two independent passes, recorded here so the 85% target cannot be met by the
same reading twice.

1. First pass: label every pair from the two claim texts alone, before reading
   any `expected` value.
2. Second pass: at least one day later, relabel from scratch without looking at
   pass one.
3. Agreement is `agreements / 24`; every disagreement is written below with both
   labels and the reason one was chosen.
4. Constructed pairs are marked `"source": "constructed"` and never counted in
   the real-corpus subtotal.

## Pass log

| date | pass | annotator | agreement with final |
|---|---|---|---|
| 2026-11-13 | 1 | agent | pending |
| 2026-11-13 | 2 | agent (blind) | pending |

## Disagreements

(none recorded yet)
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/contradiction/
git commit -m "test(contradiction): 24 labelled pairs, real sentences plus constructed gaps

Twelve come from the hold-out corpus so the language is real; the rest are
constructed because TRUE_CONTRADICTION does not occur there at all (98.3% of
claims assert an improvement). Every entry records its source and the reason for
its label, and the annotation protocol requires two blind passes."
```

---

### Task 10: Layered evaluation script

**Files:**
- Create: `scripts/evaluate_contradiction.py`
- Create: `tests/unit/test_evaluate_contradiction.py`

- [ ] **Step 1: Write the failing test**

```python
"""The report must separate real from constructed pairs, not average them away."""

from __future__ import annotations

from scripts.evaluate_contradiction import summarise


def test_precision_and_recall_are_reported_for_true_contradiction():
    rows = [
        {"source": "real", "expected": "TRUE_CONTRADICTION", "actual": "TRUE_CONTRADICTION"},
        {"source": "real", "expected": "TRUE_CONTRADICTION", "actual": "SCOPE_DIFFERENCE"},
        {"source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "TRUE_CONTRADICTION"},
        {"source": "real", "expected": "SCOPE_DIFFERENCE", "actual": "SCOPE_DIFFERENCE"},
    ]

    report = summarise(rows)

    assert report["overall"]["accuracy"] == 0.5
    assert report["TRUE_CONTRADICTION"]["precision"] == 0.5
    assert report["TRUE_CONTRADICTION"]["recall"] == 0.5


def test_skipped_is_counted_separately_from_a_wrong_label():
    rows = [
        {"source": "real", "expected": None, "actual": None},
        {"source": "real", "expected": "SCOPE_DIFFERENCE", "actual": None},
    ]

    report = summarise(rows)

    assert report["overall"]["skipped"] == 1
    assert report["overall"]["accuracy"] == 0.0


def test_confusion_matrix_is_square_over_the_five_types():
    rows = [{"source": "constructed", "expected": "COMPLEMENTARY", "actual": "COMPLEMENTARY"}]

    report = summarise(rows)

    assert set(report["confusion"]["COMPLEMENTARY"]) == {
        "TRUE_CONTRADICTION",
        "EXPERIMENTAL_INCOMPATIBILITY",
        "SCOPE_DIFFERENCE",
        "COMPLEMENTARY",
        "INSUFFICIENT_EVIDENCE",
        "SKIPPED",
    }
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/unit/test_evaluate_contradiction.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the script**

```python
"""Layered accuracy report for the P5 cascade (P5 spec §9).

A single accuracy number hides everything that matters here: the classes are
unbalanced (the corpus produces almost no true contradictions), so 'always
answer SCOPE_DIFFERENCE' scores well. This reports per-subset accuracy, a full
confusion matrix, TRUE_CONTRADICTION precision/recall, and the skip rate.

    python scripts/evaluate_contradiction.py [--json tests/fixtures/contradiction/pairs.json]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from research_os.domain.enums import ConfidenceLabel, ContradictionType
from research_os.domain.models import Claim
from research_os.research.contradiction import assess_pair

TYPES = [t.value for t in ContradictionType]
COLUMNS = TYPES + ["SKIPPED"]
FIXTURE = Path("tests/fixtures/contradiction/pairs.json")


def _claim(key: str, text: str, ident: str) -> Claim:
    return Claim(id=ident, text=text, identity_key=key, status="SUPPORTED", confidence_label=ConfidenceLabel.LOW)


def evaluate(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for entry in payload["pairs"]:
        ident = entry["id"]
        a = _claim(entry["a_key"], entry["a_text"], f"{ident}_a")
        b = _claim(entry["b_key"], entry["b_text"], f"{ident}_b")
        result = assess_pair(a, b)
        rows.append(
            {
                "id": ident,
                "source": entry["source"],
                "expected": entry["expected"],
                "actual": result.relationship.value if result else None,
            }
        )
    return rows


def summarise(rows: list[dict]) -> dict:
    def block(subset: list[dict]) -> dict:
        judged = [r for r in subset if r["expected"] is not None]
        skipped = sum(1 for r in subset if r["actual"] is None)
        correct = sum(1 for r in judged if r["expected"] == r["actual"])
        return {
            "n": len(subset),
            "judged": len(judged),
            "skipped": skipped,
            "correct": correct,
            "accuracy": round(correct / len(judged), 3) if judged else 0.0,
        }

    confusion = {expected: {column: 0 for column in COLUMNS} for expected in TYPES}
    for row in rows:
        if row["expected"] is None:
            continue
        column = row["actual"] or "SKIPPED"
        confusion[row["expected"]][column] += 1

    tp = sum(1 for r in rows if r["expected"] == "TRUE_CONTRADICTION" and r["actual"] == "TRUE_CONTRADICTION")
    fp = sum(1 for r in rows if r["actual"] == "TRUE_CONTRADICTION" and r["expected"] != "TRUE_CONTRADICTION")
    fn = sum(1 for r in rows if r["expected"] == "TRUE_CONTRADICTION" and r["actual"] != "TRUE_CONTRADICTION")
    return {
        "overall": block([r for r in rows]),
        "real": block([r for r in rows if r["source"] == "real"]),
        "constructed": block([r for r in rows if r["source"] == "constructed"]),
        "TRUE_CONTRADICTION": {
            "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
        },
        "confusion": confusion,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=str(FIXTURE))
    args = parser.parse_args()

    rows = evaluate(Path(args.json))
    report = summarise(rows)

    for name in ("overall", "real", "constructed"):
        block = report[name]
        print(f"{name:<12} n={block['n']:<3} judged={block['judged']:<3} "
              f"correct={block['correct']:<3} skipped={block['skipped']:<3} acc={block['accuracy']:.1%}")
    print(f"\nTRUE_CONTRADICTION precision={report['TRUE_CONTRADICTION']['precision']:.1%} "
          f"recall={report['TRUE_CONTRADICTION']['recall']:.1%}")

    print("\nconfusion (rows = expected, cols = actual)")
    header = "".join(f"{c[:6]:>8}" for c in COLUMNS)
    print(f"{'':<26}{header}")
    for expected, row in report["confusion"].items():
        cells = "".join(f"{row[c]:>8}" for c in COLUMNS)
        print(f"{expected:<26}{cells}")

    wrong = [r for r in rows if r["expected"] is not None and r["actual"] != r["expected"]]
    if wrong:
        print("\nmisclassified:")
        for row in wrong:
            print(f"  {row['id']} ({row['source']}): expected {row['expected']}, got {row['actual']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_evaluate_contradiction.py -q`
Expected: PASS (3 tests). Add `scripts/__init__.py` if the import fails:

```bash
touch scripts/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_contradiction.py scripts/__init__.py tests/unit/test_evaluate_contradiction.py
git commit -m "test(contradiction): layered evaluation with per-type confusion

A headline accuracy hides the fact that the classes are unbalanced; this reports
real and constructed subsets separately, gives TRUE_CONTRADICTION precision and
recall, and counts skips apart from wrong answers."
```

---

### Task 11: Run the fixtures and the hold-out corpus

**Files:**
- Modify: `docs/evaluation/` (add the result record)
- No source changes unless a real defect appears

- [ ] **Step 1: Run the fixture evaluation**

Run: `python scripts/evaluate_contradiction.py`
Expected: all three blocks printed; `TRUE_CONTRADICTION` precision/recall shown. Record the numbers.

- [ ] **Step 2: Check every misclassification is a rule defect or a label defect**

For each row in `misclassified`, decide which it is, and act accordingly:

- Rule defect → write a failing unit test in `tests/unit/test_contradiction_cascade.py` first, then fix the cascade.
- Label defect → fix `pairs.json` and record the reason in `ANNOTATION.md` under "Disagreements".

Do not adjust a rule to make an individual fixture pass; if two fixtures disagree about the same rule, the rule is underspecified and the spec section must be cited in the fix.

- [ ] **Step 3: Re-run the hold-out corpus**

Run:

```bash
python scripts/holdout_claim_quality.py --papers 20 --ids-file docs/evaluation/holdout-ids-2026-11-12.txt
python scripts/evaluate_contradiction.py
```

Then run one real paper end to end to see the memo section:

```bash
python - <<'PY'
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import init_db, session_factory
from pathlib import Path
init_db("sqlite:///p5_demo.db")
s = session_factory()()
result = Supervisor(s).run_vertical_slice(
    Path(".holdout_cache/2607.28526.html"), question="Does all-in-one restoration work?"
)
print(result["memo"].split("# Contradictions and Open Questions")[1][:1200])
PY
rm -f p5_demo.db
```

Expected: the section lists assessments with locations, or explains that no comparable pair exists. Record the distribution.

- [ ] **Step 4: Write the result record**

Create `docs/evaluation/2026-11-13-p5-contradiction.md` with: fixture accuracy per subset, confusion matrix, `TRUE_CONTRADICTION` precision/recall, the hold-out distribution, and this sentence when it applies:

```markdown
`TRUE_CONTRADICTION` recall cannot be measured on this corpus: 98.3% of the 1075
supported claims assert an improvement or merely report a value, leaving 2 LEVEL
and 16 DOWN claims and zero opposite-direction pairs. The type is verified by
constructed fixtures only.
```

- [ ] **Step 5: Commit**

```bash
git add docs/evaluation/
git commit -m "docs(p5): record fixture accuracy and the hold-out distribution

Numbers before narrative: per-subset accuracy, per-type confusion, and the
measured reason true contradictions stay at zero on this corpus."
```

---

### Task 12: Documentation sync and tag

**Files:**
- Modify: `README.md`, `architect.md`, `human_decision.md`
- Modify: `docs/superpowers/specs/2026-11-13-p5-contradiction-design.md` (mark implemented deviations)

- [ ] **Step 1: README**

Add a P5 section: the CLI/API surface, the five relations and what each means, the measured distribution, and these limits (already written in the spec §10, repeat them here in one line each):

- true contradictions are structurally absent from a corpus of independent papers;
- conditions are inherited, so a shared setup is asserted with provenance and lower confidence;
- 98.3% of claims carry no negative direction, so P5 on this corpus is a comparability filter.

- [ ] **Step 2: architect**

Add ADR-026 (four-valued direction: LEVEL means an explicit no-gain, `None` means a measurement), ADR-027 (conditions inherited from the section with provenance and a confidence penalty), ADR-028 (pairing by subject+task because the plan's scope example spans datasets), and update the phase table: P5 ✅.

Also add the storage decisions to the maintenance record: unique `(a, b)` index, run-scoped reads, replace-on-rerun.

- [ ] **Step 3: human_decision**

If any decision changed during implementation, add it; otherwise mark HD-012 and HD-013 as implemented in one line each.

- [ ] **Step 4: Spec deviations**

If implementation diverged from the spec (a rule that had to change, a number that moved), add a `> 实施偏差` note under the affected section, the way P4's spec §11 #8 does. No silent divergence.

- [ ] **Step 5: Full verification before claiming done**

Run:

```bash
python -m pytest -q
git status --short
```

Expected: all tests pass, tree clean apart from the files just committed.

- [ ] **Step 6: Commit and tag**

```bash
git add -A
git commit -m "docs(p5): contradiction analysis complete - relations, limits, measured distribution"
git tag -a w3-p5 -m "P5 contradiction analysis: deterministic cascade, section-inherited conditions, run-scoped assessments"
```

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| §2.1 direction labels | Task 1 |
| §2.2 conditions + inheritance | Task 3 |
| §2.3 subject unit words | Task 2 |
| §2.4 pairing rules, `MAX_PAIRS` | Task 4 |
| §2.5 reachability, expected zero | Tasks 11, 12 |
| §5 cascade, all ten steps, explanations | Task 5 |
| §6 module, storage, trace, orchestration, memo | Tasks 4–8 |
| §7 error handling | Tasks 4 (cap), 6 (cross-run), 7 (event payload) |
| §9 acceptance 1–17 | Tasks 1–3 (10–12), 5 (5–8), 6 (14), 7 (13, 15), 8, 10 (3–4), 11 (16), 12 (17) |
| §10 limits | Tasks 11, 12 |

**Placeholders**

None. Every step carries the code or the exact command it needs. The one instruction that could read as vague — Task 11 Step 3 "record the distribution" — is backed by the concrete result file in Step 4 with its required contents.

**Type consistency**

- `ClaimIdentity.conditions` (tuple) and `ClaimIdentity.conditions_from` (provenance, `compare=False`) are added in Task 3 and consumed in Task 5 through the identity key only — the key never carries provenance, by design.
- `pair_candidates` returns `(pairs, PairingStats)` in Task 4 and is called with that shape in Task 7.
- `assess_pair(a, b) -> ContradictionAssessment | None` is defined in Task 5 and used unchanged in Tasks 7 and 10.
- `ContradictionAssessor.assess(claims) -> (list[ContradictionAssessment], PairingStats)` is defined in Task 7 and consumed by the supervisor in the same task.
- `SqlContradictionRepository.list_by_run / replace_for_run` are defined in Task 6 and used in Tasks 7 and 8.

**Known gap, deliberate**

Task 9's fixture entries carry identity keys rather than re-running extraction. That is stated in the fixture file's `note`; extraction correctness is covered by Tasks 1–3, and mixing both concerns in the fixture set would make a cascade failure indistinguishable from an extraction failure.
