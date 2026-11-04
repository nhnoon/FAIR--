# FAIR evaluation record

All figures come from saved runs on FAIR-Bench v1. Run folders are kept locally and are not in the repository; their hashes are below.

## Read this first

- **The dataset is synthetic:** 60 short cases built from a few templates.
- **Development and Validation share templates.** The English Validation cases repeat Development scenarios with different amounts, and the Arabic cases closely parallel them.
- **Gold labels are author drafts** pending review.
- **Validation was not fully independent of development.** The author read Validation rows before writing the annotation overlay and the promise check.
- **Real-world accuracy is unmeasured.** Perfect scores here must not be read as 100% accuracy on real terms.
- **No user study** shows that FAIR improves decisions.
- **Direct Muse Spark did better than FAIR** in the one comparison run so far, on 12 new synthetic cases scored against author-draft labels. See [the comparison below](#comparison-with-direct-muse-spark).

## Results

Model `muse-spark-1.3`. "Shown" is the verdict the user sees, and it is the number that matters.

| Run | Prompt | Cases | Top-level | Shown | Tokens | Avg latency |
|---|---|---|---|---|---|---|
| Smoke test | v4 | 3 Development | 3/3 | 3/3 | 13,335 | 9.9 s |
| Development | v4 | 15 | 14/15 | 13/15 | 73,889 | 11.9 s |
| Development | v5 | 15 | 15/15 | 15/15 | 81,396 | 12.0 s |
| **Validation** | **v5, frozen** | **15** | **15/15** | **15/15** | **74,507** | **10.8 s** |

**Validation by language**

| Language | Cases | Shown | Note |
|---|---|---|---|
| English | 5 | 5/5 | No gold-MATCH case in this group |
| Arabic | 10 | 10/10 | All 5 gold-MATCH cases; only 1 CONTRADICTION |
| Mixed | 0 | Not tested | Only the Test split has mixed cases, and it has not been run |

**Validation detail**
- False MATCH: 0 of 10 cases whose gold label is not MATCH.
- Cost horizon totals: 36/36 match totals computed independently from gold prices, across 12 priced cases. The other 3 cases correctly show no projection.
- Prices, using the annotation overlay: recurring 12/12, introductory 3/3. One-time fees 3/3.
- Decisive verdicts with a verified quote: 10/10.
- Without FAIR-016 and FAIR-027, whose wording overlaps the promise check: 13/13. The promise check did not change any Validation result.
- Peak output: 4,797 of the 8,000-token budget. No truncation, schema failures or errors.

## What happened along the way

- **Smoke test, v4:** verdicts were correct, but extraction failed. The model returned `USD 9.99`, which the parser rejected, so no receipt totals appeared. The parser was fixed afterwards. That run remains a failed extraction result.
- **Development, v4:** 13/15 shown. FAIR-012 was a false reassurance: a stated price was accepted as proof that it would "never change". FAIR-011 was a correct contradiction wrongly downgraded by a topic check.
- **Development, v5:** Prompt v5, a promise check and a narrow topic fix were written after those errors, so this 15/15 is not independent.

## Against a simple baseline

A naive keyword script, written after seeing the labels, scored 11/15 on Development and 11/15 on Validation. On Validation, FAIR was right on 4 cases where it was wrong and lost none (exact McNemar p = 0.125). This does not establish statistical superiority.

## Comparison with direct Muse Spark

Run once on 2026-11-02 under [COMPARISON_PROTOCOL.md](COMPARISON_PROTOCOL.md): challenge set v2, 12 cases (5 English, 4 Arabic, 3 mixed), one request per case per system, both on `muse-spark-1.3`. **Scored against author-draft labels, not independent.** Both systems answered all 12 cases with no errors.

| Measure | FAIR (Prompt v5) | Direct Muse Spark |
|---|---|---|
| Verdict shown to the user | 9/12 | **11/12** |
| FAIR's model verdict before its checks | 10/12 | — |
| False reassurance | 0/7 | 0/7 |
| Unsupported certainty | **2/12** | 3/12 |
| Invented quotes | 0 | 0 |
| Recurring price | 5/12 | **10/12** |
| 12-month total | 7/12 | **10/12** |
| Total withheld when the label has one | 4 | 0 |
| Total given when the label has none | 1 | 2 |
| Median latency | 14.3 s | **7.2 s** |
| Tokens | 69,001 | **26,608** |

**Result: this run does not show that FAIR is better than using Muse Spark directly. Direct Muse Spark did better on verdicts, prices and totals.** Where FAIR lost:
- **CX-01:** a check downgraded the model's correct MATCH to UNKNOWN.
- **CX-04:** two billing options in one offer; FAIR answered UNKNOWN and withheld the price.
- **CX-05:** a required add-on; FAIR's verdict was right, but it withheld the 12-month total.
- **CX-06, CX-07, CX-09 (Arabic):** verdicts right, but the checks rejected the riyal price, so no total was shown.
- **CX-10 (mixed):** the terms state both monthly and yearly billing. FAIR answered CONTRADICTION; the label is UNKNOWN.
- **CX-12 (mixed):** FAIR showed a 12-month total of 0 where the label gives none.

Twelve synthetic cases and one run per system are too few to generalise in either direction. Run folder `20261102T184538Z_comparison_v2_muse-spark-1.3`, `outputs.jsonl` SHA-256 `2797193b2d008cd51e9efe154c8b0cd1d4808c9d624e925c398ec48cc86b5a71`, code SHA-256 `c8d285cb15c13ca3922d776ac59e42051949c6e6c603c2a61b50f93dcf3d5726`. FAIR's code has not changed since.

## Not yet done

- The Test split, including all its mixed-language cases.
- Any real published offer, or long terms.
- A comparison against independently reviewed labels.
- Claim-level gold labels; claim quality was reviewed manually by the author.
- Repeat runs to measure how much answers vary.
- Native-speaker review of Arabic output.

## What FAIR's checks changed in saved outputs

All 48 saved model outputs (18 on Prompt v4, 30 on Prompt v5) were replayed through FAIR's current code. No model request was made.

| Measure | Result |
|---|---|
| Overall verdict changed by a check | **1 of 48:** FAIR-012 on Prompt v4, where the model answered MATCH on "the price will never change". FAIR shows UNKNOWN. **0 of 30 on Prompt v5.** |
| Claim quotes that failed verification | **0 of 44.** The model invented no quote in these runs. |
| Extracted values rejected | 10 of 48 outputs, all the same field (`intro_periods`). This looks like strictness, not caught mistakes. |

**On these short synthetic cases, FAIR's checks have rarely been tested by a real error.** This does not show that they add value beyond the model. In the [comparison with direct Muse Spark](#comparison-with-direct-muse-spark), the checks changed one verdict, and that change was wrong.

## Later change to cost totals

After these runs, FAIR gained a completeness check that can withhold a total (see the README). It changes no verdict, quote or price. Replaying all 30 saved Prompt v5 outputs gives identical results, with 72/72 horizon totals unchanged across Development and Validation. The recorded runs were not altered. This check has not been run with new live outputs.

## Run identifiers

| Run folder | `predictions.jsonl` SHA-256 |
|---|---|
| `20261031T131540Z_development_muse-spark-1.3` | `6a9da3f1ad3108ade1349816fc12d89a3ffab473990a2fbd1d18f42232433430` |
| `20261031T173455Z_development_muse-spark-1.3` | `7d1e17615d53fecf3fb0db997727aae40bf721374d73ae8a2c1b4a907f95e2ad` |
| `20261031T181531Z_development_muse-spark-1.3` | `ce1b6f7a9c0e3479cc298bb7d3b356ec5f42d72e6dcdd8a915bbd15e9023e53b` |
| `20261031T184322Z_validation_muse-spark-1.3` | `be0e2d65fff3c29adf9f7a8378f9162b01584518a772882a0df7fc4f592cccbf` |

Prompt v5 SHA-256: `b1f3ccab20e26cd4d071b4555839bc3c5fa64c5aaa06ebd507b720b5db55053f`
