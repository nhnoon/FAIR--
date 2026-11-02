# Comparison protocol: FAIR versus direct Muse Spark

**Status: prepared, never run.** No model has seen these cases. FAIR claims no advantage over direct Muse Spark until this comparison has been measured.

## Question

On the same new cases, does FAIR's full pipeline give a person more trustworthy results than Muse Spark with a simple, neutral prompt? Specifically: does it reassure wrongly less often, cite better evidence, and get money right more often? It may not. Report the result either way, including if direct Muse Spark does as well or better.

## Systems

| | A: FAIR | B: Direct Muse Spark |
|---|---|---|
| Model | `muse-spark-1.3` | `muse-spark-1.3` |
| Input | Same terms and belief | Same terms and belief |
| Prompt | Frozen Prompt v5 | Frozen neutral prompt in `backend/evaluation/challenge.py` |
| After the model | Evidence checks, guards, price checks, cost engine | Nothing; the answer is scored as received |
| Output budget | 8,000 tokens | 8,000 tokens |
| Scored answer | The verdict the user sees | The model's verdict |

Prompt B asks for the same fields so that both can be scored the same way. It contains none of FAIR's rules about promises, silence or injected text. Its hash and the data hashes are frozen in `challenge_v1_manifest.json`. Changing any of them after a run means declaring a new comparison.

## Cases

12 synthetic cases in `backend/evaluation/challenge/`: 8 English, 2 Arabic, 2 mixed. A test confirms that none closely repeats a benchmark case.

| Case | Tests |
|---|---|
| CH-01 | Monthly price shown, annual payment charged |
| CH-02 | A real lasting promise, which FAIR must not reject |
| CH-03 | A reserved right to change prices |
| CH-04 | Unstated refund; per-seat price with no seat count |
| CH-05 | "No hidden fees!" with a footnote |
| CH-06 | Text addressed to an AI reviewer |
| CH-07 | Minimum term, pauses and exit cost |
| CH-08 | Arabic: monthly equivalent of an annual payment |
| CH-09 | Arabic: a condition that does not reach the future case |
| CH-10 | Mixed: a price step-up inside a promise |
| CH-11 | Mixed: terms that contradict themselves |
| CH-12 | A "starts at" price that varies by region |

**Known limit.** These cases were written by the same AI-assisted process that built FAIR, with knowledge of Prompt v5. They are new in structure but not independent in origin. Real published offers chosen by someone else would be stronger evidence.

## Open questions in the draft annotations

These are the author's own doubts, recorded for reviewers to settle after they have labelled the cases. Nothing was changed to fit FAIR.

| Case | Question |
|---|---|
| CH-01 | The belief has two parts. Does annual billing decide the whole belief? |
| CH-02 | The belief does not say the user is a founding member. Is MATCH right, or UNKNOWN? |
| CH-04 | Is "no total" right, or is a per-seat total of 240 acceptable if labelled? |
| CH-05 | Is "no total" right, or is 174 right for the one TV app the belief names? |
| CH-08 | Draft gold totals the yearly plan at 468. **FAIR withholds it**, because the offer also lists a monthly plan. Which is right? |
| CH-09 | Does the enrolment condition imply the student price ends, making this closer to CONTRADICTION? |
| CH-10 | Is 435 established, given that cancelling anytime is also stated? |
| CH-11 | Is this UNKNOWN, or CONTRADICTION on the Arabic sentence? |

**Label balance.** The draft has 7 CONTRADICTION, 4 UNKNOWN and 1 MATCH, so over-caution is hard to measure. Add explicitly supported MATCH cases before freezing, which changes the manifest hashes.

**Offline checks are not model results.** Hand-written correct answers run through FAIR's checks in `backend/tests/test_financial_integrity.py` test the checks only. Passing them says nothing about model accuracy.

## Separating inputs from gold

- `challenge_v1_inputs.json` holds model inputs only. A test confirms it contains no verdicts or annotations.
- `challenge_v1_gold_DRAFT.json` is an **author draft, not independent**. It exists to test the scorer and to give the adjudicator something to compare with.
- Only terms and belief are sent to a model.

## Independent review, before any run

1. Recruit at least two reviewers who did not build FAIR. At least one must read Arabic well.
2. Give them the inputs only, not the draft gold and not this project's prompts.
3. Each labels every case alone: verdict, deciding passages, recurring and introductory price, billing period, one-time fees, and the 12-month total or "not established".
4. **Rule for verdicts:** MATCH means the terms explicitly support the whole belief. CONTRADICTION means a passage actually conflicts with part of it. UNKNOWN means the terms do not settle it. Use the words of the terms and do not add outside knowledge.
5. **Rule for totals:** give a total only if the terms establish it without assuming an unstated quantity. Otherwise mark it "not established".
6. **Disagreements:** reviewers discuss and may change their labels, with reasons written down. If they still disagree, a third reviewer decides and the case is marked **contested**.
7. Freeze the final labels and record their hash before any model run. Report inter-reviewer agreement.
8. Report every metric with and without contested cases.

## Procedure, after separate authorization

1. Confirm all hashes and that reviewer gold is frozen.
2. Run A and B once per case, in the same order, sequentially, with no retries. Maximum 24 requests.
3. Stop on authentication failure, rate limiting or a budget anomaly. Failed cases stay in the denominators and count as wrong.
4. Save raw outputs, tokens and latency in a new folder.
5. Score with `evaluation/challenge.py`. Do not change the prompts, the rules or the labels after seeing results.

**Budget estimate:** about 5,000 tokens per FAIR request and fewer for direct requests, so about 100k tokens, with a worst case near 225k. This is an estimate, and input has no provider-enforced ceiling. Credit coverage must be confirmed separately.

## Metrics

Every metric is reported with its denominator, for both systems.

| Metric | Definition | How judged |
|---|---|---|
| Verdict accuracy | Correct verdicts / all cases | Scorer |
| **False reassurance rate** (primary) | MATCH shown / cases whose gold is not MATCH | Scorer |
| False contradiction, false unknown | Counts, to catch over-caution | Scorer |
| Unsupported claim rate | Decisive verdicts with no verbatim quote / decisive verdicts | Scorer |
| Invented quotes | Quotes not found verbatim / all quotes | Scorer |
| Evidence overlap | Decisive quotes overlapping accepted passages / decisive verdicts with accepted passages | Scorer |
| **Correct evidence support** | Decisive verdicts whose quote truly supports them / decisive verdicts | **Reviewers** |
| Price and billing accuracy | Correct recurring, introductory, fee and billing fields / all cases | Scorer |
| Arithmetic accuracy | Correct 12-month totals / all cases | Scorer |
| Unsupported totals | Totals given where gold says none is established | Scorer |
| Wrongly withheld totals | No total where gold has one | Scorer |
| Latency, tokens | Median latency and total tokens per system | Recorded |

**Judging evidence support.** Reviewers see each verdict and its quote with the system identity hidden and the order shuffled. They mark it supports, partly supports or does not support, using the same disagreement steps as above. FAIR's cost is real too: it may withhold answers more often, and it uses a longer prompt.

## What may be claimed afterwards

- 12 cases cannot establish statistical superiority. Report case-by-case differences and do not generalize.
- A claim such as "fewer false reassurances on these 12 cases" is allowed only if measured, with both numbers shown and the limits above stated.
- If direct Muse Spark does as well, say so. FAIR's remaining value would then rest on verified quotes and on arithmetic done by code, which should also be shown by these metrics.
- Results come from one run per system on synthetic cases, and they say nothing about user decisions.
