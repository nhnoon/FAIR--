from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.cost import A_INTRO_ONE, A_NO_RENEW, A_RENEW_UNSTATED, CostInputs, Fee, calculate

D = Decimal


def totals(report):
    return {p.months: p.total for p in report.projections}


def statuses(report):
    return {p.months: p.status for p in report.projections}


def test_free_trial_then_monthly():
    r = calculate(CostInputs(currency="USD", trial_days=7, recurring_price=D("9.99"),
                             billing_period="monthly", auto_renewal="yes"))
    assert r.due_at_signup == D("0")
    assert r.first_paid_charge_day == 7
    assert r.first_paid_charge_amount == D("9.99")
    assert totals(r) == {1: D("9.99"), 3: D("29.97"), 12: D("119.88")}
    assert set(statuses(r).values()) == {"complete"}


def test_promotional_intro_price_with_stated_duration():
    r = calculate(CostInputs(currency="USD", intro_price=D("5.00"), intro_periods=1,
                             recurring_price=D("9.99"), billing_period="monthly", auto_renewal="yes"))
    assert r.due_at_signup == D("5.00")
    assert totals(r) == {1: D("5.00"), 3: D("24.98"), 12: D("114.89")}
    assert set(statuses(r).values()) == {"complete"}


def test_promotional_multi_period_intro():
    r = calculate(CostInputs(intro_price=D("1"), intro_periods=3, recurring_price=D("10"),
                             billing_period="monthly", auto_renewal="yes"))
    assert totals(r) == {1: D("1"), 3: D("3"), 12: D("93")}


def test_promotional_intro_duration_unstated_is_conditional():
    r = calculate(CostInputs(intro_price=D("7.5"), recurring_price=D("14.99"),
                             billing_period="monthly", auto_renewal="yes"))
    assert totals(r) == {1: D("7.5"), 3: D("37.48"), 12: D("172.39")}
    assert set(statuses(r).values()) == {"conditional"}
    assert all(A_INTRO_ONE in p.assumptions for p in r.projections)


def test_one_time_fee_with_renewal_not_stated():
    r = calculate(CostInputs(currency="USD", recurring_price=D("9.99"), billing_period="monthly",
                             auto_renewal="not_stated", one_time_fees=[Fee(label="setup", amount=D("3"))]))
    assert r.one_time_fees_total == D("3")
    assert r.due_at_signup == D("12.99")
    assert totals(r) == {1: D("12.99"), 3: D("32.97"), 12: D("122.88")}
    assert statuses(r) == {1: "complete", 3: "conditional", 12: "conditional"}
    assert A_RENEW_UNSTATED in r.projections[1].assumptions


def test_missing_everything_is_unavailable_not_invented():
    r = calculate(CostInputs())
    assert set(statuses(r).values()) == {"unavailable"}
    assert all(p.total is None for p in r.projections)
    assert all("billing_period" in p.missing for p in r.projections)
    assert r.due_at_signup is None
    assert r.first_paid_charge_amount is None
    assert "Currency is not stated." in r.notes


def test_missing_recurring_price_is_unavailable():
    r = calculate(CostInputs(billing_period="monthly", auto_renewal="yes"))
    assert set(statuses(r).values()) == {"unavailable"}
    assert all(p.missing == ["recurring_price"] for p in r.projections)
    assert r.due_at_signup is None


def test_price_known_but_billing_period_unknown():
    # "Start Premium for USD 9.99 today" - no period: we must not assume monthly.
    r = calculate(CostInputs(currency="USD", recurring_price=D("9.99")))
    assert set(statuses(r).values()) == {"unavailable"}
    assert r.due_at_signup is None


def test_intro_known_recurring_missing():
    r = calculate(CostInputs(intro_price=D("5"), intro_periods=1, billing_period="monthly", auto_renewal="yes"))
    assert statuses(r) == {1: "complete", 3: "unavailable", 12: "unavailable"}
    assert r.projections[0].total == D("5")
    assert r.projections[1].missing == ["recurring_price"]


def test_no_auto_renewal_charges_once():
    r = calculate(CostInputs(recurring_price=D("10"), billing_period="monthly", auto_renewal="no"))
    assert totals(r) == {1: D("10"), 3: D("10"), 12: D("10")}
    assert A_NO_RENEW in r.projections[2].assumptions


def test_trial_without_auto_renewal_costs_only_fees():
    r = calculate(CostInputs(trial_days=14, recurring_price=D("10"), billing_period="monthly", auto_renewal="no",
                             one_time_fees=[Fee(label="activation", amount=D("2"))]))
    assert totals(r) == {1: D("2"), 3: D("2"), 12: D("2")}
    assert r.first_paid_charge_day is None
    assert r.due_at_signup == D("2")


def test_trial_with_renewal_not_stated_is_conditional_and_no_charge_day():
    r = calculate(CostInputs(trial_days=7, recurring_price=D("9.99"), billing_period="monthly",
                             auto_renewal="not_stated"))
    assert set(statuses(r).values()) == {"conditional"}
    assert r.first_paid_charge_day is None
    assert r.first_paid_charge_amount is None


def test_yearly_billing_single_charge_within_12_months():
    r = calculate(CostInputs(recurring_price=D("99"), billing_period="yearly", auto_renewal="yes"))
    assert totals(r) == {1: D("99"), 3: D("99"), 12: D("99")}


def test_weekly_billing_not_projected():
    r = calculate(CostInputs(recurring_price=D("2.99"), billing_period="weekly", auto_renewal="yes"))
    assert set(statuses(r).values()) == {"unavailable"}


def test_one_time_purchase():
    r = calculate(CostInputs(recurring_price=D("49"), billing_period="one_time"))
    assert totals(r) == {1: D("49"), 3: D("49"), 12: D("49")}


def test_decimal_exactness():
    r = calculate(CostInputs(recurring_price=D("0.10"), billing_period="monthly", auto_renewal="yes"))
    assert totals(r)[3] == D("0.30")
    assert str(totals(r)[12]) == "1.20"


@pytest.mark.parametrize("field", ["recurring_price", "intro_price"])
def test_negative_prices_rejected(field):
    with pytest.raises(ValidationError):
        CostInputs(**{field: D("-1")})


def test_negative_fee_rejected():
    with pytest.raises(ValidationError):
        Fee(label="x", amount=D("-0.01"))


def test_assumption_and_note_codes_align_with_texts():
    from app.cost import ASSUMPTIONS, NOTES
    r = calculate(CostInputs(intro_price=D("1"), recurring_price=D("2"), billing_period="monthly",
                             one_time_fees=[Fee(label="x", amount=D("1"))]))
    for p in r.projections:
        assert p.assumptions == [ASSUMPTIONS[c].format(n=p.months) for c in p.assumption_codes]
    assert r.notes == [NOTES[c] for c in r.note_codes]
    assert r.note_codes == ["currency_not_stated", "no_trial_stated"]


def test_every_projection_states_its_assumptions():
    r = calculate(CostInputs(recurring_price=D("5"), billing_period="monthly", auto_renewal="yes"))
    for p in r.projections:
        assert any("do not cancel" in a for a in p.assumptions)
        assert any(f"first {p.months} month" in a for a in p.assumptions)
