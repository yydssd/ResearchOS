# Contradiction fixture annotation protocol

Two independent passes, recorded here so the 85% target cannot be met by the
same reading twice.

1. First pass: label every pair from the two claim texts alone, before reading
   any `expected` value.
2. Second pass: at least one day later, relabel from scratch without looking at
   pass one.
3. Agreement is `agreements / 26`; every disagreement is written below with both
   labels and the reason one was chosen.
4. Constructed pairs are marked `"source": "constructed"` and never counted in
   the real-corpus subtotal.

The fixture is 26 pairs: 12 real, 14 constructed. `TRUE_CONTRADICTION` is
unreachable from the hold-out corpus (98.3% of its claims assert an improvement),
so every entry that lands on row 7b is constructed on purpose.

## Pass log

| date | pass | annotator | agreement with final |
|---|---|---|---|
| 2026-11-13 | 1 | agent (labels derived from the cascade table in spec §5) | 26/26 |
| — | 2 | **not performed** (blind relabel) | — |
| 2026-11-14 | expert review | owner | 23/26 unchanged, 3 corrected |

Pass 2 never happened and the blind-relabel gap is still open: the 26 labels were
produced with the rules in view, so agreement between them and the code proves
consistency, not correctness.

The 2026-11-14 review is a different thing and does not close that gap. The owner
reviewed the labels against the claim texts and found three that were wrong or
unsupported by the rules; 23 were accepted unchanged. That is expert curation of
machine output - it satisfies "manually curated" in the plan's §17 in the sense
that a human ruled on every entry, but it is **not** an independent blind
annotation, so no independent agreement rate can be reported.

## Disagreements (2026-11-14 review)

| id | was | now | ruling |
|---|---|---|---|
| p15.b | key `LEVEL`, rule produced `None` | key stays `LEVEL`, rule fixed | **Rule defect, not a label defect.** `NAFNet leaves PSNR unchanged` is the clearest possible no-gain statement; `_NO_GAIN` simply lacked `unchanged` / `no change` / `stays the same`. |
| p20.b | key `LEVEL` | key `None` | **Label defect.** "SSIM is the highest, PSNR second best" is a ranking, not a claim of no improvement. The verdict (`SCOPE_DIFFERENCE`) is unchanged because the dataset difference fires first. |
| p21.b | key `LEVEL`, `expected: TRUE_CONTRADICTION` | key `None`, `expected: INSUFFICIENT_EVIDENCE` | **Label defect that violated the spec.** §4.1 reads `reports 30.68 dB` as no direction, and §9 #5 says "improves PSNR" vs "reports 30 dB" must never be a `TRUE_CONTRADICTION`. The fixture was asserting the opposite of the rule it was testing. |
| p10.b | key `DOWN` | key `UP`, `expected: COMPLEMENTARY` | **Extraction defect, recorded rather than hidden.** A real sentence claims a gain on dehazing/deraining and a small loss on GoPro in one clause pair; the extractor keeps one claim and takes the first direction word. The key now records what the rule actually produces. |

## Key/rule consistency

An audit on 2026-11-14 compared every fixture key's direction segment with what
`_direction` produces for that text. **15 of 52 sides disagreed.** Eleven were the
rule missing `raises` / `lowers` / `unchanged`; four were keys written from a human
reading of the sentence (p12, p20, p21, p10).

That matters for how the 100% should be read: before this audit, a majority of the
fixture set was passing on hand-written keys rather than on rule output.
`tests/unit/test_fixture_consistency.py` now pins all 52 sides to the rule and
fails if a key drifts again. Four constructed texts were reworded from
`reaches X dB` to `improves PSNR to X dB` so the rows they exercise (8 and 9) are
reachable at all; a bare value report stops at row 6.

## Disagreements

(none recorded before 2026-11-14; see the table above)

## Label semantics

- **D13 is a whitelist.** Only `sentence` and `heading` prove that a claim used
  the setup it names, so only those tiers can support `TRUE_CONTRADICTION`.
  `section-first-mention` is an assumption, and an absent or unknown tier is
  silence - both yield `INSUFFICIENT_EVIDENCE`. A fixture expecting
  `TRUE_CONTRADICTION` MUST therefore set `a_conditions_from` and
  `b_conditions_from` explicitly (p04/p14/p15 use `sentence`, p26 uses
  `heading`). Earlier revisions treated a missing tag as "confirmed"; that was
  the exact "silence as evidence" error HD-014 exists to prevent.
- `expected: null` means "no judgement". Two causes, both recorded per entry:
  the pair is never produced by `pair_candidates` (different subject or task,
  cross-document `self@`), or `assess_pair` declines to judge it.

Two consequences worth stating, because the evaluation script depends on them:

- `null` in the fixture does not distinguish "not paired" from "skipped by the
  cascade". Task 10 must therefore run `pair_candidates` first and only call
  `assess_pair` on the pairs it returns, exactly as the validation snippet in
  the plan does. The `notes` field says which of the two causes applies.
- A non-null `a_conditions_from` / `b_conditions_from` is written into
  `Claim.conditions` as `conditions_from=<tier>` before the cascade runs. The
  conditions segment of `identity_key` still carries the condition values; the
  flag only records where they came from.

## Provenance of the real entries

Every `"source": "real"` entry names the arXiv id it was copied from. The texts
are verbatim sentences from `.holdout_cache/<id>.html`; none were edited,
shortened across a clause boundary, or assembled from two sentences.

`from` is the document both texts were copied from, except for p17, whose two
`self@` sides necessarily come from two documents; that entry carries a
`b_from` field for the second id. Every real text was checked as a literal
substring of its source file, so a plain `grep -F` finds it.

The real half is thinner than the constructed half on purpose, and what it can
cover is narrow: corpus sentences name benchmarks and directions but almost
never state a setup, so real entries reach rows 1, 2, 4 and 5 of the cascade
only. Rows 3, 6-9 and the D13 provenance tier (p25, p26) are exercised by
constructed pairs. Reporting one accuracy over the mixture would hide that, so
Task 10 must report the two subtotals separately.
