"""Decision Twin: deterministic scenarios from verified terms (pure Decimal, no AI)."""

from decimal import Decimal
from itertools import product

import pytest

from app.cost import CostInputs, Fee, calculate
from app.decision import CANCEL_ASSUMPTIONS, CancelNotice, build_decision

D = Decimal


def totals(scenario):
    return {h.months: h.total for h in scenario.horizons}


def test_free_trial_conversion_continue_vs_cancel():
    inp = CostInputs(currency="USD", trial_days=14, recurring_price=D("11.99"), billing_period="monthly",
                     auto_renewal="yes", one_time_fees=[Fee(label="activation", amount=D("2.50"))])
    d = build_decision(inp, "trial_end", CancelNotice(amount=24, unit="hours"))
    assert totals(d.continue_path) == {1: D("14.49"), 3: D("38.47"), 12: D("146.38")}
    assert d.continue_path.status == "complete"
    # Cancelling before the trial ends: only the signup fee is known to be paid.
    assert totals(d.cancel_path) == {1: D("2.50"), 3: D("2.50"), 12: D("2.50")}
    assert d.cancel_path.status == "conditional"
    assert d.cancel_path.assumption_codes[:3] == CANCEL_ASSUMPTIONS  # never assumed free / refundable
    assert (d.cancel_path.deadline.kind, d.cancel_path.deadline.day, d.cancel_path.deadline.notice.amount) == ("trial_end", 14, 24)
    assert {x.months: x.amount for x in d.difference} == {1: D("11.99"), 3: D("35.97"), 12: D("143.88")}


@pytest.mark.parametrize(
    "trial, amount, unit, expected",
    [(7, 48, "hours", 120), (14, 24, "hours", 312), (7, 36, "hours", 132), (30, 3, "days", 648)],
)
def test_last_safe_moment_is_trial_end_minus_the_stated_notice(trial, amount, unit, expected):
    inp = CostInputs(trial_days=trial, recurring_price=D("10"), billing_period="monthly", auto_renewal="yes")
    deadline = build_decision(inp, "trial_end", CancelNotice(amount=amount, unit=unit)).cancel_path.deadline
    assert (deadline.day, deadline.last_safe_hour) == (trial, expected)


def test_no_last_safe_moment_is_invented_without_a_stated_notice():
    inp = CostInputs(trial_days=7, recurring_price=D("10"), billing_period="monthly", auto_renewal="yes")
    assert build_decision(inp, "trial_end").cancel_path.deadline.last_safe_hour is None


def test_no_date_is_derived_for_a_renewal_deadline():
    inp = CostInputs(recurring_price=D("10"), billing_period="monthly", auto_renewal="yes")
    deadline = build_decision(inp, "renewal", CancelNotice(amount=48, unit="hours")).cancel_path.deadline
    assert (deadline.kind, deadline.day, deadline.last_safe_hour) == ("first_renewal", None, None)


@pytest.mark.parametrize("amount, unit", [(24, "hours"), (1, "days"), (48, "hours")])
def test_notice_as_long_as_the_trial_makes_the_cancel_path_unavailable(amount, unit):
    inp = CostInputs(trial_days=1, recurring_price=D("10"), billing_period="monthly", auto_renewal="yes")
    d = build_decision(inp, "trial_end", CancelNotice(amount=amount, unit=unit))
    assert (d.cancel_path.status, d.cancel_path.reason) == ("unavailable", "cancellation_deadline_ambiguous")
    assert d.difference == []


def test_promotional_price_receipt_lines():
    inp = CostInputs(intro_price=D("15"), intro_periods=1, recurring_price=D("45"), billing_period="monthly", auto_renewal="yes")
    d = build_decision(inp, "anytime")
    h12 = d.continue_path.horizons[2]
    assert [(ln.kind, ln.quantity, ln.unit_amount, ln.amount, ln.source_field) for ln in h12.lines] == [
        ("intro_charge", 1, D("15"), D("15"), "intro_price"),
        ("recurring_charge", 11, D("45"), D("495"), "recurring_price"),
    ]
    assert h12.total == D("510")
    # Cancel before the first renewal: the first (introductory) month is paid.
    assert totals(d.cancel_path) == {1: D("15"), 3: D("15"), 12: D("15")}
    assert d.cancel_path.deadline.kind == "first_renewal" and d.cancel_path.deadline.day is None


def test_intro_duration_unstated_propagates_assumption_to_cancel_path():
    inp = CostInputs(intro_price=D("15"), recurring_price=D("45"), billing_period="monthly", auto_renewal="yes")
    d = build_decision(inp, "renewal")
    assert d.continue_path.status == "conditional"
    assert "intro_one_period" in d.cancel_path.assumption_codes


@pytest.mark.parametrize(
    "inp, cancel_by, reason",
    [
        (dict(recurring_price=D("10"), billing_period="monthly", auto_renewal="not_stated"), "renewal", "renewal_not_stated"),
        (dict(recurring_price=D("10"), billing_period="monthly", auto_renewal="no"), "renewal", "no_automatic_renewal"),
        (dict(recurring_price=D("10"), billing_period="monthly", auto_renewal="yes"), "not_stated", "cancellation_terms_not_stated"),
        (dict(recurring_price=D("3"), billing_period="weekly", auto_renewal="yes"), "renewal", "billing_period_unsupported"),
        (dict(recurring_price=D("10"), billing_period="unknown", auto_renewal="yes"), "renewal", "billing_period_unsupported"),
        # Ambiguous: a trial, but the rule only says "before renewal".
        (dict(trial_days=7, recurring_price=D("10"), billing_period="monthly", auto_renewal="yes"), "renewal", "cancellation_deadline_ambiguous"),
        # No trial, but the rule mentions the trial end.
        (dict(recurring_price=D("10"), billing_period="monthly", auto_renewal="yes"), "trial_end", "cancellation_deadline_ambiguous"),
        (dict(billing_period="monthly", auto_renewal="yes"), "renewal", "price_not_stated"),
    ],
)
def test_unsupported_cancel_scenarios_stay_unavailable(inp, cancel_by, reason):
    d = build_decision(CostInputs(**inp), cancel_by)
    assert d.cancel_path.status == "unavailable"
    assert d.cancel_path.reason == reason
    assert d.cancel_path.horizons == []
    assert d.difference == []


def test_missing_price_makes_continue_unavailable_without_invented_numbers():
    d = build_decision(CostInputs(currency="USD", recurring_price=D("6.99")), "not_stated")
    assert d.continue_path.status == "unavailable"
    assert all(h.total is None and h.lines == [] for h in d.continue_path.horizons)


def test_yearly_plan_cancel_before_first_renewal():
    d = build_decision(CostInputs(recurring_price=D("99"), billing_period="yearly", auto_renewal="yes"), "renewal")
    assert totals(d.continue_path) == {1: D("99"), 3: D("99"), 12: D("99")}
    assert totals(d.cancel_path) == {1: D("99"), 3: D("99"), 12: D("99")}
    assert all(x.amount == 0 for x in d.difference)


def test_each_scenario_offers_all_three_horizons():
    d = build_decision(CostInputs(recurring_price=D("5"), billing_period="monthly", auto_renewal="yes"), "anytime")
    assert [h.months for h in d.continue_path.horizons] == [1, 3, 12]
    assert [h.months for h in d.cancel_path.horizons] == [1, 3, 12]


@pytest.mark.parametrize(
    "trial, intro, periods, recurring, period, renewal, fees",
    list(product(
        [None, 0, 7],
        [None, D("1.10")],
        [None, 2],
        [None, D("9.99")],
        ["monthly", "yearly", "one_time", "weekly", "unknown"],
        ["yes", "no", "not_stated"],
        [[], [D("2.50"), D("0.75")]],
    )),
)
def test_receipt_lines_always_sum_to_the_cost_engine_total(trial, intro, periods, recurring, period, renewal, fees):
    inp = CostInputs(trial_days=trial, intro_price=intro, intro_periods=periods if intro else None, recurring_price=recurring,
                     billing_period=period, auto_renewal=renewal, one_time_fees=[Fee(label=f"f{i}", amount=a) for i, a in enumerate(fees)])
    engine = {p.months: p.total for p in calculate(inp).projections}
    d = build_decision(inp, "anytime")
    for h in d.continue_path.horizons:
        assert h.total == engine[h.months]
        if h.total is not None:
            assert sum((ln.amount for ln in h.lines), D("0")) == h.total
    for h in d.cancel_path.horizons:
        assert sum((ln.amount for ln in h.lines), D("0")) == h.total
