"""Monetary values: strict parsing, source checks, and replay of real Phase 11 model outputs.

The replay fixture holds exact model text from the live smoke test. Replays are offline and
post-hoc: they test today's validation code, and they do not change that run's recorded result.
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.analyzer import analyze
from app.config import Settings
from app.meta_client import MetaClient
from app.money import billing_problem, currency_code, money_problem, parse_money
from app.schemas import AnalyzeRequest
from evaluation.fair_bench import load_cases, load_overlay
from tests.conftest import FakeSDK

D = Decimal
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "phase11_raw_outputs.json").read_text(encoding="utf-8"))
UI_FIXTURE = Path(__file__).parents[2] / "frontend" / "src" / "test" / "fixtures" / "phase11_replay.json"
EXPL = {"en": "x", "ar": "س"}


def analyze_with(extraction, terms):
    out = {"extraction": extraction, "verdict": "UNKNOWN", "verdict_evidence": None, "explanation": EXPL}
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True), sdk_client=FakeSDK(output_text=json.dumps(out, ensure_ascii=False)))
    return analyze(AnalyzeRequest(terms=terms, expectation="A belief."), client)


def fact(value, evidence):
    return {"value": value, "evidence": evidence}


def rejected(r, field):
    return next((f.evidence.reason for f in r.rejected_facts if f.field.startswith(field)), None)


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "value, amount, currency",
    [
        ("9.99", "9.99", None), (9.99, "9.99", None), (59, "59", None),
        ("USD 9.99", "9.99", "USD"), ("9.99 USD", "9.99", "USD"), ("usd9.99", "9.99", "USD"),
        ("$9.99", "9.99", "$"), ("9.99$", "9.99", "$"), ("US$ 9.99", "9.99", "USD"), ("9.99 US dollars", "9.99", "USD"),
        ("SAR 59", "59", "SAR"), ("59 SAR", "59", "SAR"), ("ر.س 59", "59", "SAR"), ("٥٩ ر.س", "59", "SAR"),
        ("59 ريال", "59", "SAR"), ("٩٫٩٩ دولار", "9.99", "$"), ("٩٫٩٩ دولار أمريكي", "9.99", "USD"), ("٢٩٫٥ SAR", "29.5", "SAR"),
        ("€12.50", "12.50", "EUR"), ("£12", "12", "GBP"), ("AED 30", "30", "AED"),
        ("1,299.00", "1299.00", None), ("USD 1,299", "1299", "USD"), ("USD USD 9", None, None),
        ("USD 14.99/month", "14.99", "USD"), ("39 SAR/month", "39", "SAR"), ("USD 9.99 per month", "9.99", "USD"),
        ("59 SAR شهريًا", "59", "SAR"),
    ],
)
def test_supported_formats_parse(value, amount, currency):
    if amount is None:
        with pytest.raises(ValueError):
            parse_money(value)
    else:
        assert parse_money(value)[:2] == (D(amount), currency)


@pytest.mark.parametrize(
    "value",
    ["", "   ", "free", "four", "about 10", "~10", "10-20", "10 or 12", "9.99 USD SAR", "USD 9.99 SAR", "$9.99 SAR",
     "9,99", "1.299,00", "1,29", ".99", "9.", "-5", "USD -5", "CAD 10", "10 JPY", "¥10", "10 BTC", "10 USD extra",
     "9.99 month", "1e3", "NaN", "Infinity", True, False, None, [], {}, float("nan"), float("inf"), -1],
)
def test_malformed_ambiguous_or_unsupported_values_are_rejected(value):
    with pytest.raises((ValueError, ArithmeticError)):
        parse_money(value)


@pytest.mark.parametrize(
    "text, code",
    [("USD", "USD"), ("$", "$"), ("دولار", "$"), ("ر.س", "SAR"), ("SAR", "SAR"), ("Pesos", None), ("", None), (None, None), ("USD and SAR", None)],
)
def test_currency_code(text, code):
    assert currency_code(text) == code


# ---------------------------------------------------------------- the source must support the price


@pytest.mark.parametrize(
    "value, quote, kind, stated, reason",
    [
        # Supported
        ("USD 9.99", "Plan is USD 9.99/month.", "recurring", "USD", None),
        ("9.99 USD", "Plan is USD 9.99/month.", "recurring", "USD", None),
        ("$9.99", "Plan is USD 9.99/month.", "recurring", "USD", None),
        ("٥٩ ر.س", "السعر 59 SAR شهريًا.", "recurring", "SAR", None),
        ("59", "السعر ٥٩ ريال شهريًا.", "recurring", None, None),
        ("USD 9.99", "USD plan: 9.99 each month.", "recurring", "USD", None),
        # Absent or wrong amount
        ("USD 9.98", "Plan is USD 9.99/month.", "recurring", "USD", "value_not_in_quote"),
        ("USD 99", "Plan is USD 9.99/month.", "recurring", "USD", "value_not_in_quote"),
        ("USD 9.99", "See your account for prices.", "recurring", "USD", "value_not_in_quote"),
        # Currency mismatch
        ("SAR 9.99", "Plan is USD 9.99/month.", "recurring", None, "currency_mismatch"),
        ("USD 9", "Plan is 9 SAR/month.", "recurring", None, "currency_mismatch"),
        ("USD 9", "Plan is 9/month.", "recurring", None, "currency_mismatch"),
        ("USD 9.99", "Plan is USD 9.99/month.", "recurring", "SAR", "currency_mismatch"),
        ("USD 9.99", "Plan is USD 9.99/month.", "recurring", "CAD", "currency_mismatch"),
        # A number that is not an amount of money
        ("48", "Cancel at least 48 hours before renewal.", "recurring", None, "not_a_price"),
        ("USD 48", "Plan is USD 10. Cancel 48 hours before renewal.", "recurring", "USD", "not_a_price"),
        ("7", "Start with a 7-day free trial.", "intro", None, "not_a_price"),
        ("٤٨", "يجب الإلغاء قبل التجديد بـ٤٨ ساعة.", "recurring", None, "not_a_price"),
        ("3", "يجب الإلغاء قبل 3 أيام من التجديد.", "one_time", None, "not_a_price"),
        ("12", "Commit for 12 months.", "recurring", None, "not_a_price"),
        ("2", "From month 2 the plan costs more.", "recurring", None, "not_a_price"),
        ("20", "Save 20% today.", "intro", None, "not_a_price"),
        # One-time and recurring prices are not interchangeable
        ("USD 3", "A one-time setup fee of USD 3 is charged at checkout.", "recurring", "USD", "one_time_not_recurring"),
        ("6", "تُضاف رسوم تأسيس لمرة واحدة بقيمة 6 SAR عند الدفع.", "recurring", None, "one_time_not_recurring"),
        ("USD 3", "A one-time setup fee of USD 3 is charged at checkout.", "intro", "USD", "one_time_not_recurring"),
        ("USD 3", "A one-time setup fee of USD 3 is charged at checkout.", "one_time", "USD", None),
        ("USD 14.99", "From month two: USD 14.99/month.", "one_time", "USD", "recurring_not_one_time"),
        ("39", "السعر بعد الشهر الأول 39 SAR/month.", "one_time", None, "recurring_not_one_time"),
        # The sentence holding the number decides, not the rest of the quote
        ("USD 10", "Plan is USD 10/month. A one-time fee of USD 3 applies.", "recurring", "USD", None),
        ("USD 3", "Plan is USD 10/month. A one-time fee of USD 3 applies.", "recurring", "USD", "one_time_not_recurring"),
    ],
)
def test_money_is_checked_against_the_quote(value, quote, kind, stated, reason):
    assert money_problem(parse_money(value), quote, kind, stated) == reason


def test_every_benchmark_price_format_is_accepted_without_hardcoding():
    checked = 0
    for case in load_cases():
        if not case.monthly_price:
            continue
        for value in (case.monthly_price, f"{case.currency} {case.monthly_price}", f"{case.monthly_price} {case.currency}"):
            assert money_problem(parse_money(value), case.terms, "recurring", case.currency, "monthly") is None, (case.case_id, value)
        checked += 1
    assert checked == 48


# ---------------------------------------------------------------- through the pipeline


TERMS = ("Introductory month: USD 7.5. From month two: USD 14.99/month. A one-time setup fee of USD 3 is charged at checkout. "
         "The plan renews automatically. Cancel at least 48 hours before the next renewal.")
INTRO, REC, FEE, RENEW, CANCEL = ("Introductory month: USD 7.5.", "From month two: USD 14.99/month.", "A one-time setup fee of USD 3 is charged at checkout.",
                                  "The plan renews automatically.", "Cancel at least 48 hours before the next renewal.")
BASE = {
    "currency": fact("USD", REC),
    "billing_period": fact("monthly", REC),
    "auto_renewal": fact("yes", RENEW),
    "cancel_by": fact("renewal", CANCEL),
    "cancel_notice": fact({"amount": 48, "unit": "hours"}, CANCEL),
}


def test_multiple_prices_stay_separate_and_reach_the_calculation_layer():
    r = analyze_with({
        **BASE,
        "intro_price": fact("USD 7.5", INTRO),
        "intro_periods": fact(None, None),
        "recurring_price": fact("USD 14.99", REC),
        "one_time_fees": [{"label": "setup fee", "amount": "USD 3", "evidence": FEE}],
    }, TERMS)
    t = r.extracted_terms
    assert (t.intro_price, t.recurring_price, t.one_time_fees[0].amount, r.rejected_facts) == (D("7.5"), D("14.99"), D("3"), [])
    lines = r.decision.continue_path.horizons[2].lines
    assert [(ln.kind, ln.quantity, ln.unit_amount, ln.amount, ln.source_field) for ln in lines] == [
        ("one_time_fee", 1, D("3"), D("3"), "fee:0"),
        ("intro_charge", 1, D("7.5"), D("7.5"), "intro_price"),
        ("recurring_charge", 11, D("14.99"), D("164.89"), "recurring_price"),
    ]
    assert r.decision.continue_path.horizons[2].total == D("175.39")
    assert "intro_one_period" in r.decision.continue_path.assumption_codes  # duration not stated: labelled, not assumed silently
    assert r.decision.continue_path.status == "conditional"


def test_introductory_price_applies_only_for_its_stated_periods():
    terms = "First 2 months: USD 5/month. Then USD 20/month. The plan renews automatically."
    r = analyze_with({
        "currency": fact("USD", "Then USD 20/month."),
        "billing_period": fact("monthly", "Then USD 20/month."),
        "auto_renewal": fact("yes", "The plan renews automatically."),
        "intro_price": fact("USD 5", "First 2 months: USD 5/month."),
        "intro_periods": fact(2, "First 2 months: USD 5/month."),
        "recurring_price": fact("USD 20", "Then USD 20/month."),
    }, terms)
    assert [h.total for h in r.decision.continue_path.horizons] == [D("5"), D("30"), D("210")]


@pytest.mark.parametrize(
    "field, value, quote, reason",
    [
        ("recurring_price", "USD 8.99", REC, "value_not_in_quote"),
        ("recurring_price", "SAR 14.99", REC, "currency_mismatch"),
        ("recurring_price", "48", CANCEL, "not_a_price"),
        ("recurring_price", "USD 3", FEE, "one_time_not_recurring"),
        ("recurring_price", "CAD 14.99", REC, "invalid_value"),
        ("recurring_price", "14,99", REC, "invalid_value"),
        ("intro_price", "USD 3", FEE, "one_time_not_recurring"),
        ("recurring_price", "USD 14.99", "This sentence is not in the terms: USD 14.99.", "quote_not_found_in_source"),
    ],
)
def test_unsupported_price_never_reaches_a_projection(field, value, quote, reason):
    r = analyze_with({**BASE, field: fact(value, quote)}, TERMS)
    assert getattr(r.extracted_terms, field) is None
    assert rejected(r, field) == reason
    assert all(h.total is None for h in r.decision.continue_path.horizons) or field == "intro_price"
    assert r.decision.cancel_path.status == "unavailable"


@pytest.mark.parametrize(
    "amount, quote, reason",
    [("USD 14.99", REC, "recurring_not_one_time"), ("USD 5", FEE, "value_not_in_quote"), ("48", CANCEL, "not_a_price"), ("three", FEE, "invalid_value")],
)
def test_unsupported_one_time_charge_is_excluded(amount, quote, reason):
    r = analyze_with({**BASE, "recurring_price": fact("USD 14.99", REC), "one_time_fees": [{"label": "fee", "amount": amount, "evidence": quote}]}, TERMS)
    assert r.extracted_terms.one_time_fees == [] and rejected(r, "one_time_fee") == reason
    assert r.cost.one_time_fees_total == D("0")


def test_no_price_in_the_terms_leaves_projections_unavailable():
    terms = "Plan renews automatically. See your account for prices."
    r = analyze_with({"auto_renewal": fact("yes", "Plan renews automatically."), "billing_period": fact("monthly", "Plan renews automatically."),
                      "recurring_price": fact("USD 9.99", "See your account for prices.")}, terms)
    assert r.extracted_terms.recurring_price is None and rejected(r, "recurring_price") == "value_not_in_quote"
    assert r.decision.continue_path.status == "unavailable"
    assert all(h.total is None and h.lines == [] for h in r.decision.continue_path.horizons)


def test_arabic_prices_through_the_pipeline():
    terms = "الشهر الأول بسعر ترويجي ١٤٫٥ ر.س. ابتداءً من الشهر الثاني يكون السعر ٢٩ ر.س شهريًا. يتجدد الاشتراك تلقائيًا."
    first, later = "الشهر الأول بسعر ترويجي ١٤٫٥ ر.س.", "ابتداءً من الشهر الثاني يكون السعر ٢٩ ر.س شهريًا."
    r = analyze_with({
        "currency": fact("ر.س", later), "billing_period": fact("monthly", later), "auto_renewal": fact("yes", "يتجدد الاشتراك تلقائيًا."),
        "intro_price": fact("١٤٫٥ ر.س", first), "recurring_price": fact("٢٩ ر.س", later),
    }, terms)
    assert (r.extracted_terms.intro_price, r.extracted_terms.recurring_price) == (D("14.5"), D("29"))
    assert r.decision.continue_path.horizons[2].total == D("333.5")


# ---------------------------------------------------------------- replay of the real Phase 11 outputs


CASES = {c.case_id: c for c in load_cases()}
OUTPUTS = {o["case_id"]: o for o in FIXTURE["outputs"]}


def replay(case_id):
    case, raw = CASES[case_id], OUTPUTS[case_id]["raw_output"]
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True, model=FIXTURE["model"]), sdk_client=FakeSDK(output_text=raw))
    return analyze(AnalyzeRequest(terms=case.terms, expectation=case.expectation), client)


def test_fixture_is_the_recorded_output_for_the_current_prompt():
    assert sorted(OUTPUTS) == ["FAIR-003", "FAIR-005", "FAIR-007"]
    for o in FIXTURE["outputs"]:
        assert hashlib.sha256(o["raw_output"].encode("utf-8")).hexdigest() == o["raw_output_sha256"]
    assert FIXTURE["prompt_version"] == "v4"  # these outputs came from v4; they say nothing about later prompts
    assert FIXTURE["prompt_sha256"] == "ceb4811ea6c93d63e383994be8e5e092b2406818d9fa0e43249053724f0b898c"


@pytest.mark.parametrize("case_id", sorted(OUTPUTS))
def test_replay_keeps_the_verdicts_and_quotes(case_id):
    r = replay(case_id)
    assert r.verdict == r.claims_summary.overall == OUTPUTS[case_id]["gold_label"]
    assert not r.verdict_downgraded and not any(c.downgraded for c in r.claims)
    for c in r.claims:
        if c.evidence:
            assert CASES[case_id].terms[c.evidence.start : c.evidence.end] == c.evidence.quote


def test_replay_fair_003_future_receipt():
    r = replay("FAIR-003")
    t = r.extracted_terms
    assert (t.currency, t.recurring_price, t.billing_period, t.auto_renewal, t.cancel_by) == ("USD", D("9.99"), "monthly", "yes", "renewal")
    assert t.cancel_notice.amount == 48 and t.intro_price is None and t.one_time_fees == [] and r.rejected_facts == []
    keep = r.decision.continue_path
    assert keep.status == "complete" and [h.total for h in keep.horizons] == [D("9.99"), D("29.97"), D("119.88")]
    cancel = r.decision.cancel_path
    assert cancel.status == "conditional" and [h.total for h in cancel.horizons] == [D("9.99")] * 3
    assert cancel.deadline.kind == "first_renewal" and cancel.deadline.last_safe_hour is None
    assert {"cancellation_fee_not_stated", "no_refund_assumed"} <= set(cancel.assumption_codes)
    assert [d.amount for d in r.decision.difference] == [D("0.00"), D("19.98"), D("109.89")]
    quoted = next(f for f in r.facts if f.field == "recurring_price").evidence
    assert "9.99" in quoted.quote and quoted.verified  # the amount is grounded in the quote


def test_replay_fair_007_future_receipt():
    r = replay("FAIR-007")
    t = r.extracted_terms
    assert (t.currency, t.intro_price, t.recurring_price, t.billing_period) == ("USD", D("7.5"), D("14.99"), "monthly")
    assert t.cancel_by == "not_stated"  # "until cancelled" states no deadline
    assert [(f.field, f.evidence.reason) for f in r.rejected_facts] == [("intro_periods", "value_not_in_quote")]  # no digit in the quote
    keep = r.decision.continue_path
    assert keep.status == "conditional" and "intro_one_period" in keep.assumption_codes
    assert [h.total for h in keep.horizons] == [D("7.5"), D("37.48"), D("172.39")]
    assert r.decision.cancel_path.status == "unavailable" and r.decision.cancel_path.reason == "cancellation_terms_not_stated"
    assert r.decision.difference == []


def test_replay_fair_005_stays_without_a_price_or_projection():
    r = replay("FAIR-005")
    assert r.extracted_terms.recurring_price is None and r.rejected_facts == []
    assert r.decision.continue_path.status == "unavailable" and r.decision.cancel_path.status == "unavailable"


def test_ui_replay_fixture_matches_the_pipeline():
    ui = json.loads(UI_FIXTURE.read_text(encoding="utf-8"))
    for case_id in OUTPUTS:
        assert ui["cases"][case_id]["body"] == replay(case_id).model_dump(mode="json")


# ---------------------------------------------------------------- Phase 11.2: price type in one sentence


@pytest.mark.parametrize(
    "value, quote, kind, reason",
    [
        # English
        ("USD 3", "Plan is USD 10/month plus a one-time setup fee of USD 3.", "recurring", "one_time_not_recurring"),
        ("USD 10", "Plan is USD 10/month plus a one-time setup fee of USD 3.", "recurring", None),
        ("USD 3", "Plan is USD 10/month plus a one-time setup fee of USD 3.", "one_time", None),
        ("USD 10", "Plan is USD 10/month plus a one-time setup fee of USD 3.", "one_time", "recurring_not_one_time"),
        ("USD 3", "A one-time setup fee of USD 3 and USD 10/month apply.", "recurring", "one_time_not_recurring"),
        ("USD 10", "A one-time setup fee of USD 3 and USD 10/month apply.", "recurring", None),
        ("USD 3", "Setup fee: USD 3, then USD 10 per month.", "recurring", "one_time_not_recurring"),
        ("USD 5", "A monthly fee of USD 5 applies.", "one_time", "recurring_not_one_time"),
        ("USD 5", "A monthly fee of USD 5 applies.", "recurring", None),
        ("USD 3", "USD 3 once, then USD 10/month.", "recurring", "one_time_not_recurring"),
        # Arabic
        ("3 SAR", "الاشتراك 10 SAR شهريًا مع رسوم تأسيس لمرة واحدة بقيمة 3 SAR.", "recurring", "one_time_not_recurring"),
        ("10 SAR", "الاشتراك 10 SAR شهريًا مع رسوم تأسيس لمرة واحدة بقيمة 3 SAR.", "recurring", None),
        ("٣ ر.س", "الاشتراك ١٠ ر.س شهريًا ورسوم تفعيل ٣ ر.س.", "recurring", "one_time_not_recurring"),
        ("٣ ر.س", "الاشتراك ١٠ ر.س شهريًا ورسوم تفعيل ٣ ر.س.", "one_time", None),
        # Mixed
        ("3 SAR", "Monthly plan 10 SAR/month، توجد رسوم إعداد لمرة واحدة بقيمة 3 SAR.", "recurring", "one_time_not_recurring"),
        ("10 SAR", "Monthly plan 10 SAR/month، توجد رسوم إعداد لمرة واحدة بقيمة 3 SAR.", "recurring", None),
    ],
)
def test_price_type_comes_from_the_words_around_the_amount(value, quote, kind, reason):
    assert money_problem(parse_money(value), quote, kind) == reason


@pytest.mark.parametrize(
    "value, quote, kind, billing, reason",
    [
        ("USD 9.99", "Start using Premium for USD 9.99 today.", "recurring", "monthly", "price_type_not_stated"),
        ("59 SAR", "ابدأ استخدام Premium اليوم مقابل 59 SAR.", "recurring", "monthly", "price_type_not_stated"),
        ("39 SAR", "Premium today for 39 SAR.", "recurring", "monthly", "price_type_not_stated"),
        ("USD 9.99", "Start using Premium for USD 9.99 today.", "recurring", None, None),  # a plain price, not calculated
        ("USD 9.99", "Start using Premium for USD 9.99 today.", "intro", "monthly", None),
        ("USD 9.99", "USD 9.99/month starting today.", "recurring", "monthly", None),
    ],
)
def test_a_payment_due_now_does_not_enter_a_recurring_calculation(value, quote, kind, billing, reason):
    assert money_problem(parse_money(value), quote, kind, None, billing) == reason


# ---------------------------------------------------------------- Phase 11.2: billing periods


@pytest.mark.parametrize(
    "value, quote, billing, reason",
    [
        ("USD 120", "Annual plan: USD 120/year.", "monthly", "billing_period_mismatch"),
        ("USD 120", "Annual plan: USD 120/year.", "yearly", None),
        ("USD 120", "Annual plan: USD 120.", "monthly", "billing_period_mismatch"),
        ("USD 120/year", "Plan is USD 120.", "monthly", "billing_period_mismatch"),
        ("USD 10/year", "Plan is USD 10/month.", None, "billing_period_mismatch"),
        ("USD 10", "Plan is USD 10/month.", "yearly", "billing_period_mismatch"),
        ("USD 10", "USD 10/month or USD 100/year.", "monthly", None),
        ("USD 100", "USD 10/month or USD 100/year.", "monthly", "billing_period_mismatch"),
        ("USD 100", "USD 10/month or USD 100/year.", "yearly", None),
        ("USD 120", "USD 120 billed annually.", "yearly", None),
        ("USD 120", "USD 120 per year.", "one_time", "billing_period_mismatch"),
        ("USD 120", "Pay USD 120 for life.", "one_time", None),
        ("1200 SAR", "الخطة السنوية 1200 SAR سنويًا.", "monthly", "billing_period_mismatch"),
        ("1200 SAR", "الخطة السنوية 1200 SAR سنويًا.", "yearly", None),
        ("100 SAR", "السعر 100 SAR كل سنة.", "monthly", "billing_period_mismatch"),
        ("100 SAR", "السعر 100 SAR شهريًا.", "yearly", "billing_period_mismatch"),
        ("100 SAR", "Plan costs 100 SAR سنويًا.", "monthly", "billing_period_mismatch"),
        ("USD 30", "USD 30 every 3 months.", "monthly", "billing_period_unsupported"),
        ("USD 30", "USD 30 per quarter.", "monthly", "billing_period_unsupported"),
        ("USD 30", "Quarterly plan: USD 30.", "monthly", "billing_period_unsupported"),
        ("USD 2", "Only USD 2 per day.", "monthly", "billing_period_unsupported"),
        ("USD 10", "USD 10/month or USD 25 every 3 months.", "monthly", None),
        ("60 SAR", "60 SAR كل 3 أشهر.", "monthly", "billing_period_unsupported"),
        ("60 SAR", "اشتراك ربع سنوي بسعر 60 SAR.", "monthly", "billing_period_unsupported"),
        ("USD 5", "First 12 months: USD 5/month.", "monthly", None),
    ],
)
def test_a_price_must_agree_with_its_billing_period(value, quote, billing, reason):
    assert money_problem(parse_money(value), quote, "recurring", None, billing) == reason


@pytest.mark.parametrize(
    "billing, quote, reason",
    [
        ("monthly", "Plan is USD 9.99/month.", None),
        ("monthly", "Subscription continues monthly until cancelled.", None),
        ("monthly", "السعر 59 SAR شهريًا.", None),
        ("monthly", "Monthly membership 39 SAR.", None),
        ("yearly", "Billed annually.", None),
        ("yearly", "يتم الدفع سنويًا.", None),
        ("weekly", "USD 3/week.", None),
        ("one_time", "A single payment of USD 49.", None),
        ("one_time", "دفعة واحدة بقيمة 49 SAR.", None),
        ("monthly", "Start using Premium for USD 9.99 today.", "billing_period_not_in_quote"),
        ("monthly", "Annual plan: USD 120.", "billing_period_not_in_quote"),
        ("yearly", "Plan is USD 9.99/month.", "billing_period_not_in_quote"),
        ("monthly", "A 12-month contract costs USD 100.", "billing_period_not_in_quote"),
        ("one_time", "Plan is USD 9.99/month.", "billing_period_not_in_quote"),
        ("monthly", "Billed every 3 months.", "billing_period_unsupported"),
    ],
)
def test_billing_period_must_be_named_by_its_quote(billing, quote, reason):
    assert billing_problem(billing, quote) == reason


def _priced(terms, price, price_quote, billing, billing_quote, currency=None):
    extraction = {"recurring_price": fact(price, price_quote), "billing_period": fact(billing, billing_quote), "auto_renewal": fact("yes", billing_quote)}
    if currency:
        extraction["currency"] = fact(currency, price_quote)
    return analyze_with(extraction, terms)


@pytest.mark.parametrize(
    "terms, price, billing, currency, field, reason",
    [
        ("Plan is USD 10/month plus a one-time setup fee of USD 3.", "USD 3", "monthly", "USD", "recurring_price", "one_time_not_recurring"),
        ("Annual plan: USD 120/year.", "USD 120", "monthly", "USD", "billing_period", "billing_period_not_in_quote"),
        ("Annual plan: USD 120/year. Billed monthly.", "USD 120", "monthly", "USD", "recurring_price", "billing_period_mismatch"),
        ("USD 30 every 3 months.", "USD 30", "monthly", "USD", "billing_period", "billing_period_unsupported"),
        ("Start using Premium for USD 9.99 today.", "USD 9.99", "monthly", "USD", "billing_period", "billing_period_not_in_quote"),
        ("الخطة السنوية 1200 SAR سنويًا.", "1200 SAR", "monthly", "SAR", "billing_period", "billing_period_not_in_quote"),
    ],
)
def test_unsafe_prices_fail_with_a_warning_and_no_total(terms, price, billing, currency, field, reason):
    r = _priced(terms, price, terms, billing, terms, currency)
    assert rejected(r, field) == reason
    assert all(h.total is None for h in r.decision.continue_path.horizons)
    assert r.decision.continue_path.status == "unavailable" and r.decision.cancel_path.status == "unavailable"
    assert any("not state it clearly enough" in w for w in r.warnings) or field == "billing_period"
    assert any("could not be verified" in w for w in r.warnings)


def test_stricter_rules_do_not_reject_any_benchmark_price_in_any_language():
    cases = load_cases()
    overlay = load_overlay(cases)["entries"]
    counts = {"intro": 0, "one_time": 0}
    for case in cases:
        intro = overlay.get(case.case_id, {}).get("prices", {}).get("intro_price")
        if intro:
            for value in (intro, f"{case.currency} {intro}", f"{intro} {case.currency}"):
                assert money_problem(parse_money(value), case.terms, "intro", case.currency, "monthly") is None, (case.case_id, value)
            counts["intro"] += 1
        if case.additional_fee not in ("", "0"):
            for value in (case.additional_fee, f"{case.currency} {case.additional_fee}"):
                assert money_problem(parse_money(value), case.terms, "one_time", case.currency) is None, (case.case_id, value)
                assert money_problem(parse_money(value), case.terms, "recurring", case.currency, "monthly") == "one_time_not_recurring", (case.case_id, value)
            counts["one_time"] += 1
    assert counts == {"intro": 12, "one_time": 12}


def test_facts_keep_their_usual_order_although_billing_is_checked_first():
    terms = "Plan is USD 10/month, renews automatically."
    r = _priced(terms, "USD 10", terms, "monthly", terms, "USD")
    assert [f.field for f in r.facts] == ["currency", "recurring_price", "billing_period", "auto_renewal"]


def test_annual_price_is_calculated_as_one_annual_charge():
    terms = "Annual plan: USD 120/year, renews automatically."
    r = _priced(terms, "USD 120", terms, "yearly", terms, "USD")
    assert r.extracted_terms.recurring_price == D("120") and r.rejected_facts == []
    assert [h.total for h in r.decision.continue_path.horizons] == [D("120"), D("120"), D("120")]  # never 1,440


def test_arabic_annual_price_is_calculated_as_one_annual_charge():
    terms = "الخطة السنوية 1200 SAR سنويًا وتتجدد تلقائيًا."
    r = _priced(terms, "1200 SAR", terms, "yearly", terms, "SAR")
    assert r.decision.continue_path.horizons[2].total == D("1200")


# ---------------------------------------------------------------- Phase 11.2: explicit currency assumptions


@pytest.mark.parametrize(
    "value, quote, stated, reason",
    [
        ("$10", "Plan is $10/month.", "$", None),
        ("$10", "Plan is USD 10/month.", "USD", None),
        ("USD 10", "Plan is $10/month.", None, "currency_mismatch"),  # "$" does not establish US dollars
        ("USD 10", "Plan is $10/month.", "$", "currency_mismatch"),
        ("$10", "Plan is 10 SAR/month.", None, "currency_mismatch"),
        ("$10", "Plan is A$10/month.", None, "currency_mismatch"),
        ("USD 10", "Plan is C$10/month.", None, "currency_mismatch"),
        ("10", "Plan is $10/month.", "$", None),
        ("10", "Plan is 10/month.", None, None),
        ("10 دولار", "الاشتراك 10 دولار شهريًا.", None, None),
        ("USD 10", "الاشتراك 10 دولار شهريًا.", None, "currency_mismatch"),
        ("USD 10", "الاشتراك 10 دولار أمريكي شهريًا.", None, None),
    ],
)
def test_currency_is_never_assumed_from_a_symbol(value, quote, stated, reason):
    assert money_problem(parse_money(value), quote, "recurring", stated) == reason


@pytest.mark.parametrize("value", ["A$10", "C$10", "CA$ 10", "AU$10", "10 CAD", "NZ$10"])
def test_other_dollar_currencies_do_not_parse(value):
    with pytest.raises(ValueError):
        parse_money(value)


def test_dollar_sign_reaches_the_receipt_as_written_with_a_note():
    terms = "Plan is $10/month, renews automatically."
    r = _priced(terms, "$10", terms, "monthly", terms, "$")
    assert r.cost.currency == "$" and "currency_symbol_ambiguous" in r.cost.note_codes
    assert r.decision.continue_path.horizons[2].total == D("120")


def test_model_cannot_upgrade_a_dollar_sign_to_usd():
    terms = "Plan is $10/month, renews automatically."
    r = _priced(terms, "USD 10", terms, "monthly", terms, "USD")
    assert r.extracted_terms.currency is None and r.cost.currency is None  # "USD" is not in the quote
    assert "currency_not_stated" in r.cost.note_codes


def test_bare_amount_is_calculated_with_an_explicit_note():
    terms = "Plan is 10/month, renews automatically."
    r = _priced(terms, "10", terms, "monthly", terms)
    assert r.cost.currency is None and "currency_not_stated" in r.cost.note_codes
    assert r.decision.continue_path.horizons[2].total == D("120")


# ---------------------------------------------------------------- Phase 11.2: known limits, not desired outcomes


def test_known_limitation_price_without_period_words_trusts_a_verified_billing_period():
    terms = "The price is USD 10. Billed monthly."
    r = analyze_with({"recurring_price": fact("USD 10", "The price is USD 10."), "billing_period": fact("monthly", "Billed monthly."),
                      "auto_renewal": fact("yes", "Billed monthly.")}, terms)
    assert r.decision.continue_path.horizons[2].total == D("120")


def test_known_limitation_period_word_in_unrelated_prose_can_mislead():
    # "month" here describes a guarantee, not billing. Words cannot establish that distinction.
    assert billing_problem("monthly", "Money-back guarantee for a month on the USD 120 plan.") is None


def test_known_limitation_swapped_intro_and_recurring_are_not_detected():
    assert money_problem(parse_money("USD 7.5"), "Introductory month: USD 7.5.", "recurring", "USD", "monthly") is None
