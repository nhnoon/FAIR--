"""Pipeline tests with a mocked model. Inputs are written here, not taken from the benchmark."""

import json
from decimal import Decimal

import pytest

from app.analyzer import DOWNGRADED_EXPLANATION, analyze
from app.meta_client import MetaClient, ModelResponseError
from app.schemas import AnalyzeRequest
from tests.conftest import FakeSDK

TERMS = ("Free for 10 days. Then USD 12.50 per month, renews automatically until cancelled. "
         "A one-time activation fee of USD 4 applies at checkout.")
EXPLAIN = {"en": "It becomes paid after the trial.", "ar": "يصبح مدفوعًا بعد التجربة."}


def model_output(**overrides):
    out = {
        "extraction": {
            "currency": {"value": "USD", "evidence": "Then USD 12.50 per month"},
            "trial_days": {"value": 10, "evidence": "Free for 10 days."},
            "intro_price": {"value": None, "evidence": None},
            "intro_periods": {"value": None, "evidence": None},
            "recurring_price": {"value": "12.50", "evidence": "Then USD 12.50 per month"},
            "billing_period": {"value": "monthly", "evidence": "Then USD 12.50 per month"},
            "auto_renewal": {"value": "yes", "evidence": "renews automatically until cancelled"},
            "cancellation_requirement": {"value": None, "evidence": None},
            "one_time_fees": [{"label": "activation fee", "amount": "4",
                               "evidence": "A one-time activation fee of USD 4 applies at checkout."}],
        },
        "verdict": "CONTRADICTION",
        "verdict_evidence": "Then USD 12.50 per month, renews automatically until cancelled.",
        "explanation": EXPLAIN,
    }
    out.update(overrides)
    return out


def run(output, terms=TERMS, expectation="It is free forever.", settings=None):
    from app.config import Settings
    settings = settings or Settings(api_key="k", live_calls_enabled=True)
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    client = MetaClient(settings, sdk_client=FakeSDK(output_text=text))
    return analyze(AnalyzeRequest(terms=terms, expectation=expectation), client)


def test_verified_contradiction_with_costs():
    r = run(model_output())
    assert r.verdict == "CONTRADICTION" and not r.verdict_downgraded
    assert r.verdict_evidence.verified
    assert TERMS[r.verdict_evidence.start:r.verdict_evidence.end].startswith("Then USD 12.50")
    assert r.extracted_terms.recurring_price == Decimal("12.50")
    assert r.rejected_facts == []
    assert r.cost.due_at_signup == Decimal("4")
    assert r.cost.first_paid_charge_day == 10
    assert {p.months: p.total for p in r.cost.projections} == {
        1: Decimal("16.50"), 3: Decimal("41.50"), 12: Decimal("154.00")}
    assert r.explanation.en == EXPLAIN["en"]


def test_fabricated_verdict_evidence_downgrades_to_unknown():
    r = run(model_output(verdict="MATCH", verdict_evidence="Cancel anytime for a full refund."))
    assert r.verdict == "UNKNOWN"
    assert r.model_verdict == "MATCH"
    assert r.verdict_downgraded
    assert r.verdict_evidence.verified is False
    assert r.explanation == DOWNGRADED_EXPLANATION  # model's unsupported reasoning is not shown
    assert any("not found" in w for w in r.warnings)


def test_missing_verdict_evidence_downgrades():
    r = run(model_output(verdict_evidence=None))
    assert r.verdict == "UNKNOWN" and r.verdict_downgraded


def test_unknown_verdict_needs_no_evidence():
    r = run(model_output(verdict="UNKNOWN", verdict_evidence=None))
    assert r.verdict == "UNKNOWN" and not r.verdict_downgraded


def test_invented_price_with_real_quote_is_rejected_and_not_costed():
    out = model_output()
    out["extraction"]["recurring_price"] = {"value": "9.99", "evidence": "Then USD 12.50 per month"}
    r = run(out)
    assert r.extracted_terms.recurring_price is None
    assert any(f.field == "recurring_price" and f.evidence.reason == "value_not_in_quote" for f in r.rejected_facts)
    assert all(p.status == "unavailable" for p in r.cost.projections)


def test_invented_fee_is_excluded_from_costs():
    out = model_output()
    out["extraction"]["one_time_fees"].append(
        {"label": "service fee", "amount": "2", "evidence": "A service fee of USD 2 applies."})
    r = run(out)
    assert [f.label for f in r.extracted_terms.one_time_fees] == ["activation fee"]
    assert r.cost.one_time_fees_total == Decimal("4")
    assert any(f.field == "one_time_fee:service fee" for f in r.rejected_facts)


def test_malformed_fee_amount_rejected_individually():
    out = model_output()
    out["extraction"]["one_time_fees"][0]["amount"] = "four"
    r = run(out)
    assert r.extracted_terms.one_time_fees == []
    assert r.rejected_facts[0].evidence.reason == "invalid_value"


def test_unverified_auto_renewal_falls_back_to_not_stated():
    out = model_output()
    out["extraction"]["auto_renewal"] = {"value": "yes", "evidence": "It auto-renews forever."}
    r = run(out)
    assert r.extracted_terms.auto_renewal == "not_stated"
    assert r.cost.first_paid_charge_day is None  # trial conversion no longer assumed as fact


def test_not_stated_values_accepted_without_evidence():
    terms = "Start using Premium for USD 9.99 today. See account settings for renewal details."
    out = {
        "extraction": {
            "currency": {"value": "USD", "evidence": "Start using Premium for USD 9.99 today."},
            "recurring_price": {"value": "9.99", "evidence": "Start using Premium for USD 9.99 today."},
            "billing_period": {"value": "unknown", "evidence": None},
            "auto_renewal": {"value": "not_stated", "evidence": None},
        },
        "verdict": "UNKNOWN",
        "verdict_evidence": "See account settings for renewal details.",
        "explanation": EXPLAIN,
    }
    r = run(out, terms=terms, expectation="It never renews.")
    assert r.verdict == "UNKNOWN" and r.verdict_evidence.verified
    assert r.extracted_terms.billing_period == "unknown"
    assert r.cost.due_at_signup is None  # no period stated: nothing invented
    assert r.rejected_facts == []


def test_arabic_terms_pipeline():
    terms = "التجربة مجانية لمدة 5 أيام. بعدها يتجدد الاشتراك تلقائيًا بمبلغ 25 SAR شهريًا."
    out = {
        "extraction": {
            "currency": {"value": "SAR", "evidence": "بعدها يتجدد الاشتراك تلقائيًا بمبلغ 25 SAR شهريًا."},
            "trial_days": {"value": "٥", "evidence": "التجربة مجانية لمدة 5 أيام."},
            "recurring_price": {"value": "٢٥", "evidence": "بمبلغ 25 SAR شهريًا"},
            "billing_period": {"value": "monthly", "evidence": "بمبلغ 25 SAR شهريًا"},
            "auto_renewal": {"value": "yes", "evidence": "بعدها يتجدد الاشتراك تلقائيا"},
        },
        "verdict": "MATCH",
        "verdict_evidence": "بعدها يتجدد الاشتراك تلقائيًا بمبلغ 25 SAR شهريًا.",
        "explanation": {"en": "Matches.", "ar": "يطابق."},
    }
    r = run(out, terms=terms, expectation="يتحول إلى اشتراك مدفوع بعد التجربة")
    assert r.verdict == "MATCH" and r.verdict_evidence.verified
    assert r.extracted_terms.trial_days == 5
    assert r.extracted_terms.recurring_price == Decimal("25")
    assert r.cost.projections[2].total == Decimal("300")


def test_lowercase_verdict_normalized():
    assert run(model_output(verdict="contradiction")).verdict == "CONTRADICTION"


@pytest.mark.parametrize(
    "bad",
    [
        "I think it is a contradiction.",
        {"verdict": "MAYBE", "explanation": EXPLAIN},
        {"verdict": "MATCH"},
        {"verdict": "MATCH", "explanation": {"en": "", "ar": ""}},
    ],
)
def test_bad_model_output_raises_response_error(bad):
    with pytest.raises(ModelResponseError):
        run(bad)
