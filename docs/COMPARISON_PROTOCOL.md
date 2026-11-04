# Comparison protocol: FAIR versus direct Muse Spark

**Status: run once on 2026-11-02, scored against author-draft labels.** Direct Muse Spark did better than FAIR: verdicts 11/12 against 9/12. FAIR claims no advantage over direct Muse Spark. Results: [EVALUATION.md](EVALUATION.md#comparison-with-direct-muse-spark).

## Question

On the same new cases, does FAIR's full pipeline give a person more trustworthy results than Muse Spark with a simple, neutral prompt? Specifically: does it reassure wrongly less often, cite better evidence, and get money right more often? It may not. Report the result either way, including if direct Muse Spark does as well or better.

## Systems

| | A: FAIR | B: Direct Muse Spark |
|---|---|---|
| Model | `muse-spark-1.3` | `muse-spark-1.3` |
| Input | Same terms and belief | Same terms and belief |
| Prompt | Frozen Prompt v5 | Frozen neutral prompt, below |
| After the model | Evidence checks, guards, price checks, cost engine | Nothing; the answer is scored as received |
| Output budget | 8,000 tokens | 8,000 tokens |
| Scored answer | The verdict the user sees | The model's verdict |

**Prompt B, exactly** (also in `backend/evaluation/challenge.py`, with its hash frozen in the manifest):
```
You will receive the terms of a subscription offer and something a person believes about it.
Say whether the terms support the belief, contradict it, or do not settle it. Quote the terms that decide your answer.
Report the prices and billing period, and the total cost over the first 12 months if it can be worked out.

Return only one JSON object:
{
  "verdict": "MATCH" | "CONTRADICTION" | "UNKNOWN",
  "quotes": ["..."],
  "explanation": "...",
  "recurring_price": "..." | null,
  "billing_period": "monthly" | "yearly" | "weekly" | "one_time" | "unknown",
  "intro_price": "..." | null,
  "one_time_fees": ["..."],
  "total_12_months": "..." | null
}
```
The input to B is `TERMS:`, the terms, `BELIEF:` and the belief. It contains none of FAIR's rules about promises, silence or injected text. Asking for quotes and fields is generous to B: a plain chat answer would be harder to check.

## Cases

**Challenge set v2** in `backend/evaluation/challenge/`: 12 synthetic offers in a marketing style. 5 English, 4 Arabic, 3 mixed. The draft labels are 5 MATCH, 4 CONTRADICTION and 3 UNKNOWN, so over-caution can be measured. Tests confirm that none closely repeats the benchmark or challenge v1.

The inputs file holds only terms and beliefs. Each case's purpose is kept with the labels, so reviewers cannot see what a case is testing.

| Covers | Cases |
|---|---|
| Future guarantees, stated and unstated | CX-01, CX-02, CX-06, CX-08 |
| Cancellation traps | CX-03, CX-07, CX-11 |
| Multiple billing periods | CX-04, CX-10 |
| Recurring and optional add-on fees | CX-05, CX-09 |
| Ambiguous or self-contradicting terms | CX-08, CX-10 |
| False reassurance in marketing language | CX-02, CX-05, CX-08, CX-11 |
| Arabic and mixed language | CX-06 to CX-12 |

Challenge set v1 stays frozen and is not part of this comparison. Its hand-written answers still test FAIR's checks.

**Known limit: this set is not independent in origin.** The same AI-assisted process that built FAIR wrote it, with knowledge of Prompt v5. It is new in structure only. Real published offers chosen by someone else would be stronger evidence, and independent labels are the minimum needed to report a result as more than a draft.

## Independent review, before any run

1. Recruit at least two reviewers who did not build FAIR. At least one must read Arabic well.
2. Give them only the blind form from `python -m evaluation.review package --out <folder>`, not the draft labels or this project's prompts. It names neither FAIR nor any model.
3. Each labels every case alone: verdict, exact quote, reason, missing conditions, recurring and introductory price, billing period, one-time fees, the 12-month total or "not established", and any ambiguity.
4. **Rule for verdicts:** MATCH means the terms clearly support the whole belief. CONTRADICTION means a passage actually conflicts with part of it. UNKNOWN means the terms do not settle it. Use the words of the terms and do not add outside knowledge. Simple arithmetic on stated numbers is allowed.
5. **Rule for totals:** give a total only if the terms establish it without assuming an unstated quantity. Otherwise mark it "not established".
6. **Disagreements:** reviewers discuss and may change their labels, with reasons written down. If they still disagree, a third reviewer decides and the case is marked **contested**.
7. `python -m evaluation.review compare` keeps each original answer file with its hash and lists every agreement and disagreement. It decides nothing. People fill in the adjudication record, and `python -m evaluation.review finalize` writes the labels with their provenance and hashes, leaving the draft unchanged. Record the hash before any model run. Report agreement between reviewers.
8. Report every metric with and without contested cases.

Where the draft expects the most disagreement: CX-04, CX-05, CX-08 and CX-10. Reviewers see this only after labelling.

**If reviewers cannot be found in time,** the run may use the draft labels. Every result must then say "scored against author-draft labels, not independent", and the runner marks it so.

## Procedure, after separate authorization

```powershell
cd backend
.venv\Scripts\python.exe -m evaluation.run_comparison plan     # no calls
# Paid: set MODEL_LIVE_CALLS_ENABLED=true for this process only
.venv\Scripts\python.exe -m evaluation.run_comparison run --gold <frozen labels> --confirm-paid-calls
```

The runner:
- Refuses to start if the inputs or either prompt changed, if the labels file is missing, or if live calls are off.
- Runs A then B on each case, in file order and sequentially, with no retries. It makes at most 24 requests, and at most 12 for each system.
- Refuses a model other than the declared one, and labels with no recorded independent review unless the result is marked as a draft.
- Gives both systems the same timeout (45 s by default), output budget and no retries, and records them with a hash of FAIR's code and this scorer.
- Stops at the first timeout, connection error, HTTP error, rate limit, authentication failure, malformed or truncated response, missing token count, token budget breach or unexpected request count, and sends nothing after it. A wrong verdict is a result and never stops the run. Completed results and the reason for stopping are saved. Failed and unrun cases stay in the denominators and count as wrong, so read a stopped run on the cases both systems answered, which it lists.
- Token limits: the 8,000 output budget is sent with each request. The API enforces no input ceiling here, so before the run it only estimates input from its length, and 5,000 input tokens is checked after each request. A breach stops the run but that request has already been sent.
- Never sends labels to a model, and scores only after all calls finish.
- Saves each result as it arrives: raw output, FAIR's visible answer, tokens and latency, in a new git-ignored folder.

Do not change the prompts, the rules or the labels after seeing results. Any change means declaring a new comparison.

**Budget estimate:** about 5,000 tokens per FAIR request and fewer for direct requests, so about 100k tokens, with a worst case near 225k. This is an estimate, and input has no provider-enforced ceiling. Confirm credit coverage first.

## Metrics

Every metric is reported with its denominator, for both systems.

| Metric | Definition | How judged |
|---|---|---|
| Verdict accuracy | Correct verdicts / all cases | Scorer |
| **False reassurance rate** (primary) | MATCH shown / cases whose gold is not MATCH | Scorer |
| False contradiction, false unknown | Counts, to catch over-caution | Scorer |
| **Unsupported-certainty rate** | Cases with a decisive verdict where gold is UNKNOWN, a decisive verdict with no verbatim quote, or a total where none is established / all cases | Scorer |
| Invented quotes | Quotes not found verbatim / all quotes | Scorer |
| Evidence overlap | Decisive quotes overlapping accepted passages / decisive verdicts with accepted passages | Scorer |
| **Correct evidence support** | Decisive verdicts whose quote truly supports them / decisive verdicts | **Reviewers** |
| Price and billing accuracy | Correct recurring, introductory, fee and billing fields / all cases | Scorer |
| Arithmetic accuracy | Correct 12-month totals / all cases | Scorer |
| Wrongly withheld totals | No total where gold has one | Scorer |
| Latency, tokens | Median latency and total tokens per system | Recorded |

**Reading amounts fairly.** Both systems' amounts go through the same reader, however they are worded. An answer with several numbers, such as "USD 14 x 12 = USD 168", is listed for a person to decide and is not marked wrong automatically.

**Separating the prompt from the checks.** A difference between A and B could come from Prompt v5 rather than FAIR's checks. So A is also scored before its checks ran, and the verdicts and values the checks changed are counted. If the prompt explains the whole gap, say so.

**Invented quotes are not an even measure.** FAIR removes unverified quotes before the user sees them, so its displayed rate is zero by construction. Report it as a property of the pipeline, alongside how many quotes its model actually produced that failed.

**Prompt A had more tuning than Prompt B.** Prompt v5 was revised after errors on Development cases, and Prompt B was never tuned. Any gap must be reported with this caveat.

**Judging evidence support.** Reviewers see each verdict and its quote with the system identity hidden and the order shuffled. They mark it supports, partly supports or does not support, using the same disagreement steps as above.

**FAIR's costs are measured too.** It may withhold answers more often, and it uses a longer prompt. Wrongly withheld totals and false unknowns are where it can lose.

## What may be claimed afterwards

- 12 cases cannot establish statistical superiority. Report case-by-case differences and do not generalize.
- A claim such as "fewer false reassurances on these 12 cases" is allowed only if measured, with both numbers shown and the limits above stated.
- If direct Muse Spark does as well, say so. FAIR's remaining value would then rest on verified quotes and on arithmetic done by code, which these metrics also show.
- Results come from one run per system on synthetic cases, and they say nothing about user decisions.

**Offline checks are not model results.** Hand-written answers in the tests check the scorer and FAIR's code. Passing them says nothing about model accuracy.
