# FAIR evaluation record

All figures come from saved runs on FAIR-Bench v1. Run folders are kept locally and are not in the repository; their hashes are below.

## Read this first

- **The dataset is synthetic:** 60 short cases built from a few templates.
- **Development and Validation share templates.** The English Validation cases repeat Development scenarios with different amounts, and the Arabic cases closely parallel them.
- **Gold labels are author drafts** pending review.
- **Validation was not fully independent of development.** The author read Validation rows before writing the annotation overlay and the promise check.
- **Real-world accuracy is unmeasured.** Perfect scores here must not be read as 100% accuracy on real terms.
- **No user study** shows that FAIR improves decisions.
- **FAIR has not been compared with using Muse Spark directly.** See [COMPARISON_PROTOCOL.md](COMPARISON_PROTOCOL.md).

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

## Not yet done

- The Test split, including all mixed-language cases.
- Any real published offer, or long terms.
- Comparison with direct Muse Spark.
- Claim-level gold labels; claim quality was reviewed manually by the author.
- Repeat runs to measure how much answers vary.
- Native-speaker review of Arabic output.

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
