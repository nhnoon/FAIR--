# FAIR-Bench v1 (60 cases)

`fair_bench_v1.csv` is an unmodified copy of the author's original file
(SHA-256 `b496051118b82f6e3c05d195fa4a29ed2024cfdfbc0044dca7a3950e9fe69d55`).
Read it with `utf-8-sig` (the file has a BOM).

- Splits: Development 15 (EN), Validation 15 (5 EN, 10 AR), Test 30 (10 AR, 20 Mixed).
- Labels: 20 MATCH / 20 CONTRADICTION / 20 UNKNOWN, balanced in every split.
- All rows are synthetic, with review status "Author draft — review pending".

## Usage rules
- Prompt iteration: **Development split only**. Validation for checking; Test is run once for reporting.
- Labels and evidence annotations are not edited in place. Any correction goes in a
  separate, documented overlay file.

## Measured audit
`cd backend; .venv\Scripts\python.exe -m evaluation.run_eval audit` (no model calls) reports:
15 distinct offer templates (5 scenarios × EN/AR/Mixed). 10/30 Test offers share an exact
number-masked template with Development/Validation, and 5/30 also share the expectation template.
All 60 gold quotes appear verbatim in their terms.

## Claim-level evaluation gap (Decision Twin)
FAIR-Bench v1 labels one expectation per case. It has **no claim-level gold labels**, so it cannot measure
how well the model splits a composite expectation into atomic claims or judges each one.
`backend/tests/test_claims.py` contains hand-written **development fixtures** that test FAIR's own
deterministic guards (missing, fabricated, irrelevant or inconsistent evidence; numbers; Arabic/mixed).
They use mocked model outputs, so they are **not** model evaluations and are not reported as accuracy.
A claim-labelled split would be needed to measure claim-level performance.

## Annotation overlay
`fair_bench_v1_overlay.json` holds versioned scoring corrections, each with a documented rationale.
The CSV and its gold labels are unchanged, and the overlay cannot carry a label (the loader rejects it).
Only `evaluation/fair_bench.py` reads it, so it never reaches the model. Runs report base metrics exactly
as before, plus a separate `overlay` block, and the manifest records its version and SHA-256.

| Rationale | Rows | Effect |
|---|---|---|
| `two_part_evidence` | FAIR-007, 022, 037, 052 | Both price passages are gold; either counts as overlap, both needed for "complete" |
| `intro_price_annotation` | All 12 Promotional Price rows | Introductory price is scored separately from recurring and one-time prices |
| `renewal_gap_evidence` | FAIR-014, 029, 044, 059 | The "renewal not stated" sentence is accepted as well |
| `ambiguous_recurring_price` | All 12 Missing Details rows | `recurring_price` is excluded from scoring, neither right nor wrong |

Corrections came from an author audit before any FAIR-Bench model run and were not independently reviewed.

## What the deterministic guards cannot catch
Pinned by the `test_known_limitation_*` tests in `backend/tests/test_claims.py`. These are semantic judgements,
left to the model and labelled "AI interpretation" in the UI, because word lists would only make them brittle:
- A quantity written in words is not seen by the number check. Prompt v4 asks for digits, but this is not enforced.
- A real, on-topic quote can still fail to logically support the claim.
- An omitted belief is only detected when it contains a digit.
- An overall CONTRADICTION with no claims needs a real quote, but passes no relevance or role check.
- Text injected into an offer that uses on-topic words can pass every guard if the model obeys it. Only the prompt rule defends here.
- One claim holds one quote. A claim needing two separate passages must be split; otherwise it cannot be a MATCH.
- The absolute-promise check only sees explicit wording. A promise phrased another way passes, a quote containing
  promise or negation wording may still not make that promise, and an unstated condition is not detected.
  Its wording overlaps Validation and Test expectations such as "guaranteed" and "never", which the author had
  read before writing it, so those rows are not independent evidence for this check.

## Challenge set
A separate 12-case challenge set, not part of FAIR-Bench, is in `backend/evaluation/challenge/`. See `docs/COMPARISON_PROTOCOL.md`. Version 2 was run once against FAIR and direct Muse Spark (results in `docs/EVALUATION.md`). Its gold file is an author draft awaiting independent review.

## Known annotation notes (not changed)
- FAIR-014, 029, 044, 059 (gold UNKNOWN: renewal not stated): the gold evidence quotes the
  setup-fee sentence. The more directly relevant sentence is the "renewal not stated" one.
  Exact evidence-match scoring would penalise a correct quote on these rows.
- Cases are generated from 5 templates. Test cases closely resemble Development cases, so
  scores will overstate performance on real-world terms.
- There is no intro-price column; promotional cases encode it only in the terms text.
- FAIR-031: "7 يومًا" (grammatically "7 أيام"). Text kept verbatim.
- FAIR-007, 022, 037, 052 (gold MATCH, two prices): the gold quote covers only the later price, so
  it does not prove the whole expectation. A correct quote of the introductory price counts as no overlap.
- Missing Details rows (FAIR-005, 010, 015, 020, 025, 030, 035, 040, 045, 050, 055, 060): the terms
  state a price but the gold Monthly price is blank, so extracting that price scores as wrong in the
  base metrics. Whether it is a recurring price is ambiguous, so the overlay excludes it.
