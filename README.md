# FAIR · تَبَيَّن — Know Before You Agree

FAIR checks what you *believe* about a subscription offer against what its terms *actually say*, in Arabic or English. It splits your belief into separate claims, shows the exact sentence behind each verdict, and calculates what each choice would cost using code rather than the model.

> **Status.** Muse Spark runs through the Meta Model API and has been evaluated live on a small synthetic benchmark: 15/15 on Development and 15/15 on Validation, with Prompt v5. Those cases share templates and were not independent of development, so **real-world accuracy is unmeasured**, and no user study shows that FAIR improves decisions. FAIR has not yet been compared with using Muse Spark directly. Details: [docs/EVALUATION.md](docs/EVALUATION.md).

## The problem

Free trials that convert to paid plans, introductory prices that end, cancellation deadlines and one-time fees all sit in fine print. People rarely misread everything. They hold one specific wrong belief, such as "I can cancel after the trial and avoid all fees". A summary of the terms does not test that belief.

## How Reveal the Gap works

You paste the terms and write what you believe, then press **Reveal the Gap**.

1. **Muse Spark reads and interprets.** It splits your belief into claims, judges each one as MATCH, CONTRADICTION or UNKNOWN, extracts prices and conditions with quotes, and writes the explanations in both languages.
2. **FAIR treats that output as untrusted.** Deterministic code checks it before anything is shown.
3. **Code does the math.** Costs use `Decimal` arithmetic on verified values only.

### Expectation Mirror: claim-level verdicts
Your belief appears as separate claims, each with its own verdict and evidence. A claim's MATCH or CONTRADICTION becomes UNKNOWN when its quote:
- is not found word for word in the terms, or is stitched together from separate passages;
- has a role that disagrees with the verdict;
- is not about the claim's topic;
- lacks a number the claim states (for MATCH);
- does not make an absolute or lasting promise the claim asserts, such as "never" or "guaranteed" (for MATCH).

These are necessary conditions, not proof. A real, on-topic quote can still fail to support a claim. That judgment remains the model's, and it is labelled **AI interpretation**.

### Decision Twin: Decision Reveal and Future Receipt
- **Decision Reveal** appears when a verified contradiction exists and at least two choices can be priced. It puts your belief beside the sentence that conflicts with it, then prices the choices: keep paying, cancel before the deadline, and, for a trial, miss the deadline then cancel. Each choice separates what is verified, assumed and not settled. It shows backend totals only, and it does not claim that the contradicted sentence caused them.
- **Future Receipt** compares keeping and cancelling over 1, 3 and 12 months, with amounts linked to their quotes. Each projection is based on stated terms, depends on listed assumptions, or is withheld with the missing information named.
- The cancel path is always conditional. FAIR assumes no refund and cannot confirm that cancelling is free. It appears only when the terms state automatic renewal and a cancellation rule FAIR can map to a deadline.
- FAIR labels the timing of a first payment as assumed, because it does not verify when a charge happens.

### What FAIR can and cannot total

Totals cover monthly and yearly billing over 1, 3 and 12 months, including introductory prices and one-time fees. Before showing one, FAIR checks that the verified prices account for what the terms say you would pay, because correct arithmetic on incomplete inputs is still misleading.

**FAIR shows no total, and keeps the stated price visible, when:**
- the price is per seat, user or device (FAIR does not multiply, even if a quantity is stated, and never assumes one);
- the terms state another required amount that no verified price or fee accounts for, including one the checks rejected;
- the terms both state and deny automatic renewal;
- the billing period or price is missing, or the billing cycle is unsupported.

**FAIR shows a total labelled as an assumption when:** an amount is presented as optional or as depending on a condition (the amount is named as not counted), an introductory period is not stated (assumed to be one billing period), renewal is not stated (billing is assumed to continue), or a first payment's timing is not verified.

Decision Reveal reads the same totals, so it shows no amounts when the receipt withholds them. A withheld total is never shown as zero.

### Price checks
A price counts only if its quote states it as money, in the same currency, as the right kind of price and for the same billing period. FAIR rejects a one-time fee taken as a recurring price, an annual price taken as monthly, a cancellation period taken as a price, and billing cycles it cannot calculate. `$` alone is not assumed to mean US dollars. Rejected values are shown with the reason.

### Arabic and English
The interface is fully translated with right-to-left layout. Evidence matching tolerates diacritics and Arabic-Indic digits (٥٩ = 59), but never different words. Terms can mix both languages. Arabic model quality has been measured only on the 10 Arabic Validation cases, and mixed-language model quality has not been measured.

## Why Muse Spark is in the workflow

Deciding whether a sentence supports, contradicts or simply does not address a belief written in someone's own words needs language understanding across Arabic and English. Rules cannot do that. FAIR gives this job to Muse Spark, and uses code for what code can do reliably: checking that quotes exist, validating amounts, and doing arithmetic.

## Architecture

```
Browser (React, Vite, Tailwind; English and Arabic)
  │  POST /api/analyze {terms, expectation, language}
  ▼
FastAPI (backend/app)        MODEL_API_KEY exists only here
  ├─ main.py         validation, CORS, rate limits, body-size limit, error codes
  ├─ meta_client.py  Meta Model API (OpenAI-compatible SDK, Responses API), no retries, output budget
  ├─ prompts.py      one versioned prompt (v5)
  ├─ analyzer.py     model JSON → schema check → evidence verification → verified terms
  ├─ evidence.py     verbatim quote matching with character offsets
  ├─ claims.py       claim-level guards and the overall result
  ├─ money.py        price, currency and billing-period checks
  ├─ cost.py         Decimal cost engine (1, 3 and 12 months)
  ├─ decision.py     Future Receipt paths from verified values
  └─ completeness.py withholds or labels totals the terms show are incomplete
backend/evaluation   FAIR-Bench runner, annotation overlay scoring, challenge-set scorer
```

**Meta integration.** Endpoint `https://api.meta.ai/v1`, model `muse-spark-1.3`, one request per analysis.

## Privacy, API key and limits

- Your text goes to the FAIR server and, when live analysis is enabled, to the Meta Model API. Meta's own terms govern what happens there. The FAIR server does not store it, and its logs contain metadata such as verdicts, latency and token counts.
- The key is read from `MODEL_API_KEY` on the server. It is never sent to the browser, logged or returned.
- Paid calls are off unless `MODEL_LIVE_CALLS_ENABLED=true`. Each request makes no automatic retries, carries an 8,000 output-token budget, and times out at 45 seconds. The API enforces no input ceiling here; request bodies are size-limited, and terms are capped at 20,000 characters.
- Defaults allow 10 analyses per minute per IP and 300 per day per server. Limits are in memory, so run one instance.

## Run locally

Requirements: Python 3.11 and Node 20 or newer. Commands use PowerShell.

```powershell
# Backend (from backend/)
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend (from frontend/, in a second terminal)
npm ci
npm run dev        # http://localhost:5173, forwards /api to port 8000
```

With no key the app still runs: the status shows that live AI is not configured, and analysis returns a setup message, never a result. To use live analysis, add your key to `backend/.env` and set `MODEL_LIVE_CALLS_ENABLED=true`. **Each analysis is then a billable request.**

### Try it without a key: replay mode

Replay mode runs the real checks and calculations on saved Muse Spark outputs for three synthetic cases. It makes no model request, and it labels every result as a replay.

```powershell
cd frontend; npm run build
cd ..\backend; .venv\Scripts\python.exe -m scripts.demo_replay    # http://127.0.0.1:8010
```

The inputs are in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). Any other input returns an error.

`?lang=ar` opens Arabic. In development builds only, `?sample=<id>` opens a hand-written sample labelled as not AI-generated.

## Tests

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest
cd frontend; npm test
cd frontend; npm run build
backend\.venv\Scripts\python.exe tools\check_release.py     # from the repository root
```

Model interactions in tests are mocked, and the backend test suite blocks external network access.

## Evaluation

| Run (Prompt v5, frozen for Validation) | Verdicts shown to the user | Notes |
|---|---|---|
| Development | 15/15 | The prompt was revised after errors on these cases |
| Validation | 15/15 | Arabic 10/10. No false MATCH on these 15. 36/36 cost horizon totals correct |

**What these numbers do not show.** The 60-case dataset is synthetic. Development and Validation share templates. Gold labels are author drafts pending review. Validation was not fully independent of development decisions. A naive keyword script scored 11/15 on each of these splits, and differences this small are not statistically conclusive. The Test split, which holds the only mixed-language cases, has not been run.

Full results and run identifiers: [docs/EVALUATION.md](docs/EVALUATION.md). A planned comparison with direct Muse Spark, not yet run: [docs/COMPARISON_PROTOCOL.md](docs/COMPARISON_PROTOCOL.md).

```powershell
cd backend
.venv\Scripts\python.exe -m evaluation.run_eval audit     # no model calls
# Paid: set MODEL_LIVE_CALLS_ENABLED=true for this process only
.venv\Scripts\python.exe -m evaluation.run_eval run --split development --max-requests 15 --stop-on-anomaly --confirm-paid-calls
```

## Limitations

- **Real-world accuracy and user benefit are unmeasured.** Offers in the benchmark are a couple of sentences long; long real terms are untested.
- **Semantic gaps remain.** A quote can be real and on topic without supporting the claim. A promise phrased in unusual words can pass the promise check. A dropped belief is detected only if it contains a digit. An unstated condition is not detected.
- **Prompt injection.** Offer text is treated as data by instruction, but if the model obeys on-topic injected text, the checks can still pass.
- **FAIR needs your belief in writing,** and it reads pasted text only.
- **Cost totals can still be incomplete or over-cautious.** The checks read wording. FAIR never calculates tax or a percentage fee: a tax not stated as included, or a required percentage fee, withholds the total, and an optional or conditional percentage fee is named beside a labelled total. A percentage in words or without a charge word ("your bill goes up by 15%"), an amount written in words, and a per-unit price phrased unusually ("for every teammate") are not detected, so a total can be too low. A required charge or fee phrased with "if" is shown as conditional, not withheld. An offer listing two plans has its total withheld, because nothing says which plan applies, and a stated seat count is not used.
- **Billing support.** Weekly billing is not converted, and quarterly or daily cycles are rejected. Taxes are detected from wording, never calculated.
- **Model output varies between runs.** Each benchmark case ran once per prompt version.
- **Quotes must be verbatim.** A correct paraphrase is rejected on purpose.
- FAIR gives information, not legal or financial advice.

## Repository layout

```
backend/   FastAPI app, tests, evaluation, replay mode (scripts/demo_replay.py)
frontend/  React app and tests
data/      fair_bench_v1.csv, annotation overlay, data card
docs/      evaluation, comparison protocol, demo script, project description, deployment, checklist
tools/     check_release.py (pre-publication safety scan)
```

## Third-party assets

Fonts are bundled from npm: Inter and IBM Plex Sans Arabic (both SIL Open Font License 1.1). Icons and the favicon are original inline SVG.

## License

No license has been chosen yet.
