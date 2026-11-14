# P5 contradiction analysis — measured results

Date: 2026-11-13 · Commit at time of run: `1e0895e` · Branch `p5-contradiction`

Numbers first, interpretation second. Every figure below is reproduced by the
commands at the end of this file; none are estimated.

---

## 1. What P5 is, and what this report can and cannot show

P5 answers one question: given two persisted claims, can we say they contradict,
differ in scope, are experimentally incompatible, complement each other, or that
the evidence is insufficient? It never reads the papers again — it judges from
`identity_key`, which P4 produced.

That design decision sets the ceiling for this report. `identity_key` is a
heuristic extraction (subject, task, dataset, metric, direction, conditions,
value bucket), so P5's ceiling is P4's recall. Everything below is measured
against that ceiling, not against the papers.

---

## 2. Fixture set — 26 labelled pairs

`tests/fixtures/contradiction/pairs.json`, 12 `real` (verbatim sentences from the
hold-out corpus) and 14 `constructed`.

| subset | n | judged | correct | skipped | accuracy |
|---|---|---|---|---|---|
| overall | 26 | 21 | 21 | 0 | 100.0% |
| real | 12 | 8 | 8 | 0 | 100.0% |
| constructed | 14 | 13 | 13 | 0 | 100.0% |

`TRUE_CONTRADICTION` precision = 100.0% (4/4), recall = 100.0% (4/4).

Confusion (rows = expected, columns = actual):

| expected \ actual | TRUE_CON | SCOPE | EXPERIM | COMPLEM | INSUFF | SKIPPED |
|---|---|---|---|---|---|---|
| TRUE_CONTRADICTION | 4 | 0 | 0 | 0 | 0 | 0 |
| SCOPE_DIFFERENCE | 0 | 4 | 0 | 0 | 0 | 0 |
| EXPERIMENTAL_INCOMPATIBILITY | 0 | 0 | 3 | 0 | 0 | 0 |
| COMPLEMENTARY | 0 | 0 | 0 | 4 | 0 | 0 |
| INSUFFICIENT_EVIDENCE | 0 | 0 | 0 | 0 | 6 | 0 |

Five fixtures expect no judgement (`null`) and all five produce none. Two of them
(p17, p18) never become candidates at all — pairing refuses a cross-document
`self@` and a different task — which is a different fact from the cascade
declining, and the evaluator records them separately.

### 2.1 This 100% is a regression lock, not evidence of quality

The labels were derived from the same rules the cascade implements. Agreement
therefore shows the rules still behave as written; it cannot show the rules are
right. The `85%` target in the original plan is met trivially and should not be
read as a quality result.

An expert review on 2026-11-14 (owner, all 26 entries) accepted 23 labels and
corrected 3. A separate audit compared every key's direction segment with what
`_direction` produces: **15 of 52 sides disagreed** — eleven because the rule was
missing `raises`/`lowers`/`unchanged`, four because the key was written from a
human reading rather than from rule output. Both are fixed and pinned by
`tests/unit/test_fixture_consistency.py`. The 100% above is therefore the first
version of this number that every entry actually earns through the rules; it is
still not an independent agreement rate, because no blind second pass exists.

What *was* independently verified: the 24 `real` sentences (12 pairs) appear
verbatim in the arXiv HTML named in their `from` field (checked by substring
search over `.holdout_cache/`, no edited or spliced sentences). The labels
themselves have **no independent provenance** — see
`tests/fixtures/contradiction/ANNOTATION.md`: pass 2 (the blind relabel) was
**not performed**. What exists is one agent pass plus an owner expert review on
2026-11-14, which is curation of machine output, not a second independent
annotation. No independent agreement rate can be reported.

---

## 3. Hold-out corpus — 20 unseen papers

### 3.1 Inputs

| quantity | value |
|---|---|
| papers | 20 |
| chunks | 13 871 |
| evidence | 4 814 |
| claims | 1 173 (1 075 supported) |
| claims with a dataset | 195 / 1 075 (18%) |
| claims with a metric | 153 / 1 075 (14%) |
| merge gate satisfied | 73 / 1 075 (7%) |
| cross-document merges | 0 |

### 3.2 Pairing

| quantity | value |
|---|---|
| pairs that passed pairing | 1 049 |
| evaluated | 1 049 |
| coverage of paired candidates | 100.0% |
| dropped by the `self@` prefilter | 6 601 |
| skipped: no dataset | 917 |
| skipped: no metric | 102 |
| skipped: identical value (P4 defect tripwire) | 0 |
| dropped by `MAX_PAIRS` | 0 |

**Coverage of 100% does not mean everything was compared.** It means every pair
that became a candidate was judged. The 6 601 pairs the `self@` prefilter dropped
are reported on their own line precisely so this cannot be misread; they are
within-document pairs where at least one side lacks a dataset or a metric.

### 3.3 Result distribution

| relation | count |
|---|---|
| `TRUE_CONTRADICTION` | **0** |
| `EXPERIMENTAL_INCOMPATIBILITY` | 2 |
| `SCOPE_DIFFERENCE` | 18 |
| `COMPLEMENTARY` | 5 |
| `INSUFFICIENT_EVIDENCE` | 5 |
| **total assessments** | **30** |

Of 1 049 comparable pairs, 30 produced a judgement. 1 019 were skipped for a
missing scope field. This is what a comparability filter looks like on a corpus
of independent papers: the dominant output is "these two numbers are not
comparable", not "these two papers disagree".

---

## 4. Why `TRUE_CONTRADICTION` is zero

`TRUE_CONTRADICTION` recall cannot be measured on this corpus: 98.3% of the 1075
supported claims assert an improvement or merely report a value, leaving 2 LEVEL
and 16 DOWN claims and zero opposite-direction pairs. The type is verified by
constructed fixtures only.

Direction distribution, re-measured on the post-fix corpus (n = 1075):

| direction | count | share |
|---|---|---|
| `UP` (claims improvement) | 372 | 34.6% |
| `None` (reports a value, asserts no direction) | 685 | 63.7% |
| `DOWN` (claims degradation) | 16 | 1.5% |
| `LEVEL` (explicit no-gain) | 2 | 0.2% |

`UP + None = 1057 / 1075 = 98.3%`. Note what the 98.3% means: it is "not a
negative or flat claim", not "asserts an improvement". The design spec's §2 used
1063 claims (`UP 369 / None 676`) measured before the prerequisite fixes; the
conclusion is unchanged, but the report of record uses the re-measured numbers.

Two further measurements pin the same conclusion from different sides:

1. **Direction.** After the four-valued fix, `achieves/reports/reaches` assert no
   direction at all. A claim reporting 39.18 dB can no longer be read as the
   opposite of a claim reporting an improvement — the failure that would have
   produced false contradictions.
2. **Conditions.** All 25 assessments that passed the conditions gate rested on
   conditions inherited from a section's first mention; **zero pairs had
   sentence-level conditions on both sides.** Had the weak tier been trusted as
   proof of a shared setup, every one of those 25 would have been a candidate for
   a contradiction verdict on evidence that does not support it.

That second number is the reason for HD-014. `section-first-mention` conditions
are now allowed to *disprove* a shared setup but never to *prove* one, so the
`TRUE_CONTRADICTION` gate is effectively "both sides state their setup in the
sentence or in the heading". Measured effect on this corpus today: 0 pairs
downgraded, because there were no opposite-direction pairs to downgrade. The rule
is insurance, and its cost is currently zero.

---

## 5. End-to-end behaviour

One real paper (`2606.22801`, 1 105 chunks, 151 claims) through the full
supervisor path produces:

```text
# Contradictions and Open Questions

Assessed 192 of 192 candidate pairs (coverage 100%).
Skipped: 152 without a dataset, 36 without a metric, 1176 self pairs without a dataset or metric.

## True contradictions (0)
## Experimental incompatibilities (0)
## Scope differences (1)
- dataset differs: sidd vs urban100
  - A: `c_839eae74460a` — sv_2d9f24ecfb53 · IV-D1 Zero-shot generalization ... · chars 0-114
  - B: `c_d789e8db6b7e` — sv_2d9f24ecfb53 · IV-D3 Generalization to unknown ... · chars 701-865
## Complementary findings (2)
## Insufficient evidence (1)
```

Every verdict names its dimension and both values, and every claim carries the
source version, section and character offsets of its supporting evidence. A
reader can open the paper at `chars 0-114` and check the claim. Verdicts that
cannot be located say `no locatable evidence` instead of printing placeholder
coordinates.

---

## 6. Known limits, restated with the numbers behind them

1. **`TRUE_CONTRADICTION` is unobservable on real text** (§4). The type exists,
   is tested by fixtures, and cannot be trusted to fire correctly on a corpus
   where it never fires.
2. **Fixture accuracy is circular** (§2.1). Independent labelling remains open.
3. **18% of claims carry a dataset** (§3.1), so 87% of comparable pairs are
   skipped before judgement. Improving this is a P4 extraction problem, not a P5
   rule problem, and lowering the gate would be exactly the "missing means the
   same" error this phase exists to avoid.
4. **Conditions are mostly inherited** (§4). A shared setup is asserted with a
   provenance tag at best, never from the sentence itself on both sides.

---

## Reproducing

```bash
# §3.1 inputs and §4 direction distribution
D:/Anaconda/envs/reOS/python.exe scripts/holdout_claim_quality.py \
    --papers 20 --ids-file docs/evaluation/holdout-ids-2026-11-12.txt

# §3.2 pairing, §3.3 result distribution, §4 condition provenance
D:/Anaconda/envs/reOS/python.exe scripts/holdout_contradiction_quality.py \
    --ids-file docs/evaluation/holdout-ids-2026-11-12.txt

# §2 fixture set
D:/Anaconda/envs/reOS/python.exe scripts/evaluate_contradiction.py

D:/Anaconda/envs/reOS/python.exe -m pytest
```

Every number in §3–§4 is printed by one of the two hold-out scripts;
`holdout_contradiction_quality.py` rebuilds the claims from the cached pages and
runs the same `HeuristicContradictionAssessor` the supervisor uses. Neither
script needs network access. The first version of this report transcribed
§3.2–3.3 from an uncommitted ad-hoc probe, which a code review correctly flagged
as unverifiable; the harness above is that probe, committed.

---

## Post-review note (2026-11-13 evening)

An independent code review (`docs/evaluation/2026-11-13-p5-review.md`) found that
this report's §3.2–3.3 numbers had no committed harness. That is fixed: the
second command under **Reproducing** now prints every figure transcribed here.
The review also closed a provenance-gate defect (a missing `conditions_from` tag
could produce `TRUE_CONTRADICTION`) and a run-scope leak. Re-running the harness
after those fixes reproduced §3 unchanged — in particular `TRUE_CONTRADICTION`
was already 0, so the whitelist gate changed no real-corpus verdict.

Several §9 acceptance items remain open (direction word-list blind spots,
`FAILURE` events, three separate confusion matrices, the second blind annotation
pass). They are listed in the review record; this report does not claim they are met.

The items listed as open in the post-review note above are addressed in the
final section below.

---

## Failure events and per-subset matrices (2026-11-14)

P5 now persists four kinds of failure instead of swallowing them (plan §25):
`CROSS_RUN_PAIR` when storage holds a pair spanning two runs (the run continues,
the batch is dropped and the count is recorded), `CONTRADICTION_UNRESOLVED` for a
pair that raised and for an identical-value pair that P4 should have merged, and
`CITATION_LOCATION_MISSING` for an assessed claim with no supporting evidence.
Each also appends to `run.warnings`, so `research-os status` shows it.

`coverage` now uses `judged = evaluated - failed_pairs` as its numerator. Before
this change a run whose only pair raised reported "Assessed 1 of 1 candidate
pairs (coverage 100%)" and then "All 1 evaluated pairs were skipped" - two
statements that were both false.

The confusion matrix is printed three times - overall, real, constructed. The
split makes visible what the combined table hid: every `TRUE_CONTRADICTION` hit
comes from the constructed subset; the real row is zero across the board. That is
the same fact the recall note in §4 states in words, now visible in the numbers.
