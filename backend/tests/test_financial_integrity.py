"""Totals must not look complete when the terms say more than the verified prices do.

Constructed outputs are hand-written correct answers, not model predictions. They test FAIR's
downstream checks only, and say nothing about model accuracy.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.analyzer import analyze
from app.config import Settings
from app.meta_client import MetaClient
from app.schemas import AnalyzeRequest
from evaluation.challenge import load_gold, load_inputs, normalize_fair, score_case
from tests.conftest import FakeSDK

D = Decimal
EXPL = {"en": "x", "ar": "س"}
CONSTRUCTED = json.loads((Path(__file__).parent / "fixtures" / "financial_constructed_outputs.json").read_text(encoding="utf-8"))["outputs"]
UI_FIXTURE = Path(__file__).parents[2] / "frontend" / "src" / "test" / "fixtures" / "financial_withheld.json"


def fact(value, evidence):
    return {"value": value, "evidence": evidence}


def run(terms, extraction, claims=None, verdict="UNKNOWN", quote=None):
    out = {"extraction": extraction, "verdict": verdict, "verdict_evidence": quote, "explanation": EXPL, "claims": claims or []}
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True), sdk_client=FakeSDK(output_text=json.dumps(out, ensure_ascii=False)))
    return analyze(AnalyzeRequest(terms=terms, expectation="A belief."), client)


def monthly(terms, price, quote=None, currency=None, **extra):
    q = quote or terms
    ex = {"recurring_price": fact(price, q), "billing_period": fact("monthly", q), "auto_renewal": fact("not_stated", None), **extra}
    if currency:
        ex["currency"] = fact(currency, q)
    return run(terms, ex)


def totals(r):
    return [h.total for h in r.decision.continue_path.horizons]


def codes(r):
    return [w.code for w in r.cost.withheld]


def assert_withheld(r, code):
    assert code in codes(r)
    assert totals(r) == [None, None, None]
    assert all(h.lines == [] for h in r.decision.continue_path.horizons)
    assert all(p.total is None and p.status == "unavailable" and code in p.missing for p in r.cost.projections)
    assert r.decision.continue_path.status == "unavailable" and r.decision.cancel_path.status == "unavailable"
    assert r.decision.difference == []
    # Withheld is never presented as zero, or as no charge.
    assert r.cost.due_at_signup is None and r.cost.first_paid_charge_amount is None


# ---------------------------------------------------------------- quantity


@pytest.mark.parametrize(
    "terms, price, currency",
    [
        ("Team plan: USD 20 per seat per month.", "USD 20", "USD"),
        ("Team plan: USD 20/user/month.", "USD 20", "USD"),
        ("USD 20 for each user, billed monthly.", "USD 20", "USD"),
        ("Per-seat price: USD 20 per month.", "USD 20", "USD"),
        ("خطة الفريق 20 SAR لكل مستخدم شهريًا.", "20 SAR", "SAR"),
        ("Team plan: 20 SAR per device شهريًا.", "20 SAR", "SAR"),
    ],
)
def test_unknown_quantity_never_becomes_a_quantity_of_one(terms, price, currency):
    r = monthly(terms, price, currency=currency)
    assert_withheld(r, "unit_quantity_unknown")
    assert r.extracted_terms.recurring_price == D(price.replace("USD", "").replace("SAR", "").strip())  # the fact is kept


def test_a_stated_seat_count_is_not_used_yet_so_the_total_stays_withheld():
    # No quantity field exists and Prompt v5 is frozen. Multiplying here would be a guess about what the count covers.
    r = monthly("5 seats at USD 20 per seat per month.", "USD 20", currency="USD")
    assert_withheld(r, "unit_quantity_unknown")


@pytest.mark.parametrize(
    "terms, price",
    [("Family plan: USD 20/month for up to 5 users.", "USD 20"), ("Includes 3 devices. USD 20/month.", "USD 20")],
)
def test_a_flat_price_that_merely_mentions_users_keeps_its_total(terms, price):
    r = monthly(terms, price, currency="USD")
    assert r.cost.withheld == [] and totals(r)[2] == D("240")


# ---------------------------------------------------------------- amounts the verified prices leave out


@pytest.mark.parametrize(
    "terms, price, currency, amount",
    [
        ("Stream for USD 10/month. A USD 4.50 monthly device fee applies to each TV app.", "USD 10", "USD", "4.50"),
        ("Plan is USD 10/month. A USD 2/month platform fee applies.", "USD 10", "USD", "2"),
        ("الخطة 10 SAR شهريًا. تُضاف رسوم منصة بقيمة 2 SAR شهريًا.", "10 SAR", "SAR", "2"),
        ("Plan is 10 SAR/month. تُضاف رسوم بقيمة 2 SAR لكل جهاز.", "10 SAR", "SAR", "2"),
        ("Plan is USD 10/month. An activation charge of USD 7 applies.", "USD 10", "USD", "7"),
    ],
)
def test_a_required_amount_is_never_silently_left_out(terms, price, currency, amount):
    r = monthly(terms, price, currency=currency)
    assert_withheld(r, "unaccounted_charge")
    assert r.cost.withheld[0].amount == D(amount)
    assert r.cost.withheld[0].quote in terms  # the original words, not normalized text
    assert r.extracted_terms.recurring_price is not None


def test_a_fee_the_checks_rejected_cannot_quietly_shrink_the_total():
    terms = "Plan is USD 10/month. A setup fee of USD 7 is charged."
    fee = {"label": "setup", "amount": "USD 8", "evidence": "A setup fee of USD 7 is charged."}
    r = monthly(terms, "USD 10", quote="Plan is USD 10/month.", currency="USD", one_time_fees=[fee])
    assert r.extracted_terms.one_time_fees == []
    assert_withheld(r, "unaccounted_charge")


@pytest.mark.parametrize(
    "terms, price, currency, amount",
    [
        ("Plan is USD 10/month. Optional cloud storage costs USD 2/month.", "USD 10", "USD", "2"),
        ("Plan is USD 10/month. A USD 5 late fee applies if a payment fails.", "USD 10", "USD", "5"),
        ("الخطة 10 SAR شهريًا. التخزين الإضافي اختياري بسعر 2 SAR شهريًا.", "10 SAR", "SAR", "2"),
        ("الخطة 10 SAR شهريًا. تُضاف 5 SAR إذا تأخر الدفع.", "10 SAR", "SAR", "5"),
    ],
)
def test_an_optional_or_conditional_amount_keeps_the_total_but_labels_and_names_it(terms, price, currency, amount):
    r = monthly(terms, price, currency=currency)
    assert r.cost.withheld == []
    assert [n.amount for n in r.cost.not_counted] == [D(amount)]
    assert totals(r)[2] == D("120")
    assert r.decision.continue_path.status == "conditional" and "amount_not_counted" in r.decision.continue_path.assumption_codes
    assert all(p.status == "conditional" and "amount_not_counted" in p.assumption_codes for p in r.cost.projections)


@pytest.mark.parametrize(
    "terms, price, billing, expected",
    [
        ("Pro is USD 8 per month, billed annually as one payment of USD 96.", "USD 96", "yearly", "96"),
        ("الباقة 39 SAR شهريًا، وتُدفع سنويًا بمبلغ 468 SAR.", "468 SAR", "yearly", "468"),
    ],
)
def test_a_yearly_price_restated_per_month_is_the_same_charge(terms, price, billing, expected):
    r = run(terms, {"recurring_price": fact(price, terms), "billing_period": fact(billing, terms)})
    assert r.cost.withheld == [] and totals(r)[2] == D(expected)


def test_a_restated_amount_that_does_not_reconcile_is_not_excused():
    terms = "Pro is USD 9 per month, billed annually as one payment of USD 96."
    r = run(terms, {"recurring_price": fact("USD 96", terms), "billing_period": fact("yearly", terms)})
    assert_withheld(r, "unaccounted_charge")


@pytest.mark.parametrize(
    "terms",
    [
        "Plan is USD 10/month. Cancel 48 hours before renewal.",
        "Plan is USD 10/month with a 12-month minimum term and 50% off accessories.",
        "Plan is USD 10/month. Support replies within 2 days.",
        "Plan is USD 10/month. Refunds within 14 days.",
    ],
)
def test_durations_and_percentages_are_not_treated_as_charges(terms):
    r = monthly(terms, "USD 10", currency="USD")
    assert r.cost.withheld == [] and r.cost.not_counted == [] and totals(r)[2] == D("120")


# ---------------------------------------------------------------- taxes and percentage charges


def currency_of(price):
    return "USD" if "USD" in price else "SAR"


@pytest.mark.parametrize(
    "terms, price, rate",
    [
        ("Plan is USD 10/month plus 15% VAT.", "USD 10", "15"),
        ("Plan is USD 10/month. 15% VAT will be added at checkout.", "USD 10", "15"),
        ("Plan is USD 10/month, excluding VAT at 15%.", "USD 10", "15"),
        ("Plan is USD 10/month. Sales tax of 8.25% applies.", "USD 10", "8.25"),
        ("Plan is USD 10/month + 5 percent GST.", "USD 10", "5"),
        ("Plan is USD 10/month. A 3% processing fee is charged on every payment.", "USD 10", "3"),
        ("Plan is USD 10/month plus 2%.", "USD 10", "2"),
        ("Plan is USD 10/month. The price increases by 10% each year.", "USD 10", "10"),
        ("Plan is USD 10/month. VAT of 15% may apply depending on your country.", "USD 10", "15"),
        ("الخطة 10 SAR شهريًا. تُضاف ضريبة القيمة المضافة بنسبة 15%.", "10 SAR", "15"),
        ("الخطة 10 SAR شهريًا غير شاملة ضريبة القيمة المضافة ١٥٪.", "10 SAR", "15"),
        ("الخطة 10 SAR شهريًا، بالإضافة إلى ضريبة %15.", "10 SAR", "15"),
        ("الخطة 10 SAR شهريًا. تُضاف رسوم معالجة بنسبة 3 بالمئة على كل دفعة.", "10 SAR", "3"),
        ("الخطة 10 SAR شهريًا. ترتفع الأسعار بنسبة 10% كل سنة.", "10 SAR", "10"),
    ],
)
def test_a_percentage_charge_never_disappears_from_a_total(terms, price, rate):
    r = monthly(terms, price, currency=currency_of(price))
    assert_withheld(r, "percentage_charge")
    reason = next(w for w in r.cost.withheld if w.code == "percentage_charge")
    assert reason.rate == D(rate) and reason.amount is None and reason.quote in terms
    assert r.extracted_terms.recurring_price == D("10")  # the stated price stays a fact; no tax is calculated


@pytest.mark.parametrize(
    "terms, price",
    [
        ("Plan is USD 10/month plus applicable taxes.", "USD 10"),
        ("Plan is USD 10/month, excluding VAT.", "USD 10"),
        ("Plan is USD 10/month. Prices do not include tax.", "USD 10"),
        ("Plan is USD 10/month. Taxes may apply.", "USD 10"),
        ("الخطة 10 SAR شهريًا غير شاملة الضريبة.", "10 SAR"),
        ("الخطة 10 SAR شهريًا. لا تشمل الأسعار ضريبة القيمة المضافة.", "10 SAR"),
        ("الخطة 10 SAR شهريًا. قد تُطبق ضريبة القيمة المضافة.", "10 SAR"),
    ],
)
def test_a_tax_with_no_stated_rate_withholds_and_is_never_estimated(terms, price):
    assert_withheld(monthly(terms, price, currency=currency_of(price)), "tax_not_included")


@pytest.mark.parametrize(
    "terms, price",
    [
        ("Plan is USD 10/month including 15% VAT.", "USD 10"),
        ("Plan is USD 10/month. Prices include VAT.", "USD 10"),
        ("Plan is USD 10/month, tax included.", "USD 10"),
        ("الخطة 10 SAR شهريًا شاملة ضريبة القيمة المضافة 15%.", "10 SAR"),
        ("الخطة 10 SAR شهريًا. الأسعار تشمل الضريبة.", "10 SAR"),
    ],
)
def test_a_tax_stated_as_included_is_already_in_the_total(terms, price):
    r = monthly(terms, price, currency=currency_of(price))
    assert r.cost.withheld == [] and r.cost.not_counted == [] and totals(r)[2] == D("120")
    assert r.decision.continue_path.status != "unavailable"


@pytest.mark.parametrize(
    "terms",
    [
        "Plan is USD 10/month with 99.9% uptime.",
        "Plan is USD 10/month. 100% refund within 14 days.",
        "Plan is USD 10/month. Save 20% with a referral.",
        "Plan is USD 10/month. Get a 20% discount on accessories.",
        "Plan is USD 10/month. Tax-free for students.",
        "Plan is USD 10/month. No tax is charged.",
        "Plan is USD 10/month. We email a tax invoice.",
        "Plan is USD 10/month. There is a 0% fee.",
        "الخطة 10 USD شهريًا مع خصم 20% على الملحقات.",
        "الخطة 10 USD شهريًا. استرداد 100% خلال 14 يومًا.",
    ],
)
def test_a_percentage_the_user_does_not_pay_keeps_the_total(terms):
    r = monthly(terms, "10 USD" if "الخطة" in terms else "USD 10", currency="USD")
    assert r.cost.withheld == [] and r.cost.not_counted == [] and totals(r)[2] == D("120")


@pytest.mark.parametrize(
    "terms, price, rate",
    [
        ("Plan is USD 10/month. Optional insurance adds a 5% fee.", "USD 10", "5"),
        ("Plan is USD 10/month. A 3% surcharge applies if you pay by card.", "USD 10", "3"),
        ("Plan is USD 10/month. A 5% late fee is charged on overdue invoices.", "USD 10", "5"),
        ("الخطة 10 SAR شهريًا. تُضاف رسوم 3% إذا دفعت ببطاقة ائتمان.", "10 SAR", "3"),
        ("الخطة 10 SAR شهريًا. تُفرض رسوم تأخير بنسبة 5%.", "10 SAR", "5"),
    ],
)
def test_a_conditional_percentage_fee_is_labelled_and_named_not_applied(terms, price, rate):
    r = monthly(terms, price, currency=currency_of(price))
    assert r.cost.withheld == [] and totals(r)[2] == D("120")
    assert [(n.amount, n.rate) for n in r.cost.not_counted] == [(None, D(rate))]
    assert r.decision.continue_path.status == "conditional" and "amount_not_counted" in r.decision.continue_path.assumption_codes


def test_a_tax_with_a_condition_still_withholds_because_applicability_is_not_guessed():
    assert_withheld(monthly("Plan is USD 10/month. 15% VAT applies if you live in the EU.", "USD 10", currency="USD"), "percentage_charge")


def test_an_included_tax_does_not_excuse_a_separate_fee():
    r = monthly("Plan is USD 10/month including VAT. A 3% processing fee is charged.", "USD 10", currency="USD")
    assert_withheld(r, "percentage_charge")
    assert [w.rate for w in r.cost.withheld] == [D("3")]


def test_a_signup_fee_is_not_shown_as_a_payment_when_tax_is_excluded_and_nothing_else_can_be_totalled():
    terms = "Free for 7 days. A one-time setup fee of USD 5 applies, plus 15% VAT."
    fee = {"label": "setup", "amount": "USD 5", "evidence": "A one-time setup fee of USD 5 applies"}
    r = run(terms, {"trial_days": fact(7, "Free for 7 days."), "one_time_fees": [fee]})
    assert r.cost.due_at_signup is None and [w.code for w in r.cost.withheld] == ["percentage_charge"]


# ---------------------------------------------------------------- conflicting renewal


@pytest.mark.parametrize(
    "terms, price",
    [
        ("Your plan renews automatically every month at USD 19. This plan does not renew without your consent.", "USD 19"),
        ("Your plan renews automatically every month at 19 SAR. لا يتجدد الاشتراك تلقائيًا إلا بموافقتك.", "19 SAR"),
        ("يتجدد الاشتراك تلقائيًا كل شهر بمبلغ 19 SAR. لن يتجدد الاشتراك دون موافقتك.", "19 SAR"),
    ],
)
def test_terms_that_both_state_and_deny_renewal_get_no_projection(terms, price):
    assert_withheld(monthly(terms, price), "conflicting_renewal")


@pytest.mark.parametrize(
    "terms",
    [
        "Plan is USD 10/month and renews automatically.",
        "Plan is USD 10/month. This plan does not renew.",
        "Plan is USD 10/month. Renewal terms are not stated.",
        "Plan is USD 10/month, automatically renewed unless cancelled.",
    ],
)
def test_one_clear_renewal_statement_is_not_a_conflict(terms):
    assert "conflicting_renewal" not in codes(monthly(terms, "USD 10", currency="USD"))


# ---------------------------------------------------------------- fully specified terms are untouched


def test_simple_monthly_subscription():
    terms = "Plan is USD 9.99/month and renews automatically."
    r = run(terms, {"currency": fact("USD", terms), "recurring_price": fact("USD 9.99", terms), "billing_period": fact("monthly", terms), "auto_renewal": fact("yes", terms)})
    assert totals(r) == [D("9.99"), D("29.97"), D("119.88")]
    assert r.decision.continue_path.status == "complete" and r.cost.withheld == [] and r.cost.not_counted == []


def test_introductory_pricing():
    terms = "First 2 months: USD 5/month. Then USD 20/month. The plan renews automatically."
    r = run(terms, {
        "currency": fact("USD", "Then USD 20/month."), "billing_period": fact("monthly", "Then USD 20/month."),
        "auto_renewal": fact("yes", "The plan renews automatically."), "intro_price": fact("USD 5", "First 2 months: USD 5/month."),
        "intro_periods": fact(2, "First 2 months: USD 5/month."), "recurring_price": fact("USD 20", "Then USD 20/month."),
    })
    assert totals(r) == [D("5"), D("30"), D("210")] and r.cost.withheld == []


def test_one_time_fee():
    terms = "Plan is USD 10/month. A one-time setup fee of USD 3 is charged at checkout."
    fee = {"label": "setup", "amount": "USD 3", "evidence": "A one-time setup fee of USD 3 is charged at checkout."}
    r = monthly(terms, "USD 10", quote="Plan is USD 10/month.", currency="USD", one_time_fees=[fee])
    assert totals(r) == [D("13"), D("33"), D("123")] and r.cost.withheld == []


def test_a_projection_already_unavailable_keeps_its_own_reason():
    terms = "Start using Premium for USD 9.99 today. See account settings. A USD 2 fee applies."
    r = run(terms, {"recurring_price": fact("USD 9.99", "Start using Premium for USD 9.99 today.")})
    assert r.decision.continue_path.status == "unavailable" and r.cost.withheld == []
    assert r.cost.projections[0].missing == ["billing_period"]


def test_verdicts_and_quotes_are_not_touched_by_withholding():
    terms = "Stream for USD 10/month. A USD 4.50 monthly device fee applies to each TV app."
    quote = "A USD 4.50 monthly device fee applies to each TV app."
    claim = {"text": "USD 10 is all I pay.", "topic": "fees", "verdict": "CONTRADICTION", "evidence": quote, "evidence_role": "contradicts", "explanation": EXPL}
    r = run(terms, {"recurring_price": fact("USD 10", "Stream for USD 10/month."), "billing_period": fact("monthly", "Stream for USD 10/month.")}, [claim], "CONTRADICTION", quote)
    assert r.verdict == r.claims_summary.overall == "CONTRADICTION"
    assert r.claims[0].evidence.quote == quote and r.cost.withheld


# ---------------------------------------------------------------- the challenge cases, constructed answers only

INPUTS = {c["case_id"]: c for c in load_inputs()}
GOLD = load_gold()


def constructed(case_id):
    case = INPUTS[case_id]
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True), sdk_client=FakeSDK(output_text=json.dumps(CONSTRUCTED[case_id], ensure_ascii=False)))
    return analyze(AnalyzeRequest(terms=case["terms"], expectation=case["expectation"]), client)


@pytest.mark.parametrize(
    "case_id, code", [("CH-04", "unit_quantity_unknown"), ("CH-05", "unaccounted_charge"), ("CH-11", "conflicting_renewal")]
)
def test_the_three_audit_findings_are_withheld(case_id, code):
    assert_withheld(constructed(case_id), code)


@pytest.mark.parametrize("case_id", sorted(CONSTRUCTED))
def test_constructed_answers_keep_their_verdicts_and_facts(case_id):
    r = constructed(case_id)
    s = score_case(INPUTS[case_id], GOLD[case_id], normalize_fair(r.model_dump(mode="json")))
    assert s["correct"] and s["recurring_price_correct"] and s["billing_correct"] and r.rejected_facts == []


def test_the_early_exit_percentage_in_ch07_is_named_on_a_labelled_total():
    r = constructed("CH-07")
    assert r.cost.withheld == [] and [n.rate for n in r.cost.not_counted] == [D("50")]
    assert totals(r)[2] == D("360") and r.decision.continue_path.status == "conditional"


def test_known_over_withholding_two_plans_in_one_offer():
    # CH-08 lists a monthly plan and a yearly plan. The draft gold totals the yearly plan. FAIR withholds, because
    # the monthly plan's price is another stated amount and nothing structured says which plan applies. Safe, but a miss.
    r = constructed("CH-08")
    assert_withheld(r, "unaccounted_charge")
    assert GOLD["CH-08"]["cost"]["total_12_months"] == 468


# ---------------------------------------------------------------- known limits, not desired outcomes


def test_known_limitation_a_percentage_in_words_or_without_a_charge_word_is_not_seen():
    r = monthly("Plan is USD 10/month. Your bill goes up by 15% each year.", "USD 10", currency="USD")
    assert r.cost.withheld == [] and totals(r)[2] == D("120")
    r = monthly("Plan is USD 10/month plus a fifteen percent levy.", "USD 10", currency="USD")
    assert r.cost.withheld == [] and totals(r)[2] == D("120")


def test_known_limitation_a_percentage_fee_with_a_stray_if_keeps_the_total():
    # Labelled and named, not withheld. Taxes do not get this treatment.
    r = monthly("Plan is USD 10/month. A 3% platform fee applies if you stay subscribed.", "USD 10", currency="USD")
    assert r.cost.withheld == [] and r.cost.not_counted[0].rate == D("3")


def test_known_limitation_a_unit_price_in_other_words_is_not_detected():
    r = monthly("USD 20 a month for every teammate.", "USD 20", currency="USD")
    assert r.cost.withheld == []


def test_known_limitation_an_amount_written_in_words_is_not_seen():
    r = monthly("Plan is USD 10/month plus a ten dollar monthly device fee.", "USD 10", currency="USD")
    assert r.cost.withheld == []


def test_known_limitation_a_required_amount_with_if_is_treated_as_conditional():
    # Labelled and named, but the total is shown.
    r = monthly("Plan is USD 10/month. If you use the TV app, USD 4.50 is added.", "USD 10", currency="USD")
    assert r.cost.withheld == [] and r.cost.not_counted[0].amount == D("4.50")


def test_ui_fixture_matches_the_pipeline():
    ui = json.loads(UI_FIXTURE.read_text(encoding="utf-8"))
    for case_id, entry in ui["cases"].items():
        assert entry["body"] == constructed(case_id).model_dump(mode="json")
    for entry in ui["percent_cases"].values():
        assert entry["body"] == run(entry["terms"], entry["extraction"], entry["claims"], entry["verdict"], entry["quote"]).model_dump(mode="json")
