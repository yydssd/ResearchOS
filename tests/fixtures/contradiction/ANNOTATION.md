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
| — | 2 | **not performed** | — |

The second pass did not happen. The protocol asks for a blind relabel at least a
day later, and the work was done in one session: pass 1 was produced while the
rules were in view, so agreement between pass 1 and the fixture is not evidence
that the labels are right. It is evidence that the fixture and the code agree.

Consequence, stated plainly because the evaluation report depends on it:
`docs/evaluation/2026-11-13-p5-contradiction.md` reports 100% fixture accuracy and
that number must be read as a regression lock only. An independent annotator who
labels the 26 pairs from the claim texts alone, without reading `spec §5` or
`contradiction.py`, is the missing step; until then `TRUE_CONTRADICTION` precision
and recall on this fixture measure self-consistency, not correctness.

## Disagreements

(none recorded yet)

## Label semantics

- `conditions_from` absent (null): the conditions are treated as stated by the
  sentence itself. The cascade only distinguishes a confirmed setup from one
  inherited from a section's first mention; a fixture that omits the field is
  asserting the confirmed tier.
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
