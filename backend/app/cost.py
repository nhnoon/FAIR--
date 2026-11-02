"""Deterministic subscription cost engine.

Pure Python + Decimal. The model never does arithmetic: it only extracts values,
and only values whose evidence was verified reach this module.

Rules:
- Missing prices are never invented. A projection that needs a missing value is
  reported as "unavailable" with the missing field named.
- A projection that relies on filling a gap (e.g. renewal not stated) is
  "conditional" and states the assumption it made.
- "complete" projections use only stated terms, plus the universal assumption
  that the user does not cancel within the horizon.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .money import DOLLAR, currency_code

BillingPeriod = Literal["monthly", "yearly", "weekly", "one_time", "unknown"]
AutoRenewal = Literal["yes", "no", "not_stated"]
ProjectionStatus = Literal["complete", "conditional", "unavailable"]

HORIZONS = (1, 3, 12)

# Stable codes (for UI translation) -> English text. Texts may use {n} (horizon months).
ASSUMPTIONS: dict[str, str] = {
    "horizon": "Counts the first {n} month(s) of billing, starting when the free trial (if any) ends.",
    "no_cancel": "Assumes you do not cancel during this period.",
    "fees_at_signup": "One-time fees are counted once, at signup.",
    "intro_one_period": "The introductory price is assumed to last one billing period (its duration is not stated).",
    "renewal_unstated": "Automatic renewal is not stated; this figure assumes billing continues each period.",
    "trial_conversion_unstated": "Whether the trial converts to a paid plan is not stated; this figure assumes it does.",
    "no_auto_renewal": "The terms say it does not renew automatically; later periods assume no manual renewal.",
    "trial_no_auto_renewal": "The terms say it does not renew automatically, so the trial is assumed to end without a charge.",
    "weekly_not_projected": "Weekly billing is not projected onto months to avoid an inexact conversion.",
    "amount_not_counted": "The terms state an optional or conditional amount that this figure does not count.",
}
NOTES: dict[str, str] = {
    "currency_not_stated": "Currency is not stated.",
    "currency_symbol_ambiguous": "The terms show a dollar sign without naming the country, so FAIR does not assume US dollars.",
    "no_trial_stated": "No free trial is stated.",
    "due_at_signup_unknown": "The amount due at signup cannot be determined from the stated terms.",
}

A_NO_CANCEL = ASSUMPTIONS["no_cancel"]
A_HORIZON = ASSUMPTIONS["horizon"]
A_FEES = ASSUMPTIONS["fees_at_signup"]
A_INTRO_ONE = ASSUMPTIONS["intro_one_period"]
A_RENEW_UNSTATED = ASSUMPTIONS["renewal_unstated"]
A_TRIAL_UNSTATED = ASSUMPTIONS["trial_conversion_unstated"]
A_NO_RENEW = ASSUMPTIONS["no_auto_renewal"]
A_TRIAL_NO_RENEW = ASSUMPTIONS["trial_no_auto_renewal"]


class Fee(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(ge=0)


class CostInputs(BaseModel):
    currency: str | None = None
    trial_days: int | None = Field(default=None, ge=0)
    intro_price: Decimal | None = Field(default=None, ge=0)
    intro_periods: int | None = Field(default=None, ge=1)
    recurring_price: Decimal | None = Field(default=None, ge=0)
    billing_period: BillingPeriod = "unknown"
    auto_renewal: AutoRenewal = "not_stated"
    one_time_fees: list[Fee] = Field(default_factory=list)


class Projection(BaseModel):
    months: int
    status: ProjectionStatus
    total: Decimal | None = None
    assumptions: list[str] = Field(default_factory=list)
    assumption_codes: list[str] = Field(default_factory=list, description="Keys of ASSUMPTIONS, same order.")
    missing: list[str] = Field(default_factory=list)


class WithheldReason(BaseModel):
    code: Literal["unit_quantity_unknown", "unaccounted_charge", "conflicting_renewal", "percentage_charge", "tax_not_included"]
    amount: Decimal | None = None
    rate: Decimal | None = Field(default=None, description="A percentage as stated in the terms. FAIR never applies it.")
    quote: str = Field(description="The source text behind this reason.")


class NotCountedAmount(BaseModel):
    amount: Decimal | None = None
    rate: Decimal | None = Field(default=None, description="A percentage as stated in the terms. FAIR never applies it.")
    quote: str = Field(description="The source text stating this optional or conditional amount.")


class CostReport(BaseModel):
    currency: str | None
    trial_days: int
    due_at_signup: Decimal | None
    first_paid_charge_day: int | None = Field(
        description="Days after signup when the first subscription charge happens; null if unknown or none."
    )
    first_paid_charge_amount: Decimal | None
    one_time_fees_total: Decimal
    projections: list[Projection]
    notes: list[str] = Field(default_factory=list)
    note_codes: list[str] = Field(default_factory=list, description="Keys of NOTES, same order.")
    withheld: list[WithheldReason] = Field(default_factory=list, description="Why no totals are shown, though prices were verified.")
    not_counted: list[NotCountedAmount] = Field(default_factory=list, description="Stated amounts the totals leave out, labelled as an assumption.")


def _projection(n: int, status: ProjectionStatus, codes: list[str], **kw) -> Projection:
    return Projection(
        months=n,
        status=status,
        assumptions=[ASSUMPTIONS[c].format(n=n) for c in codes],
        assumption_codes=codes,
        **kw,
    )


def _charge_schedule(
    inp: CostInputs, n_months: int
) -> tuple[list[Decimal] | None, list[str], list[str], bool]:
    """Subscription charges inside an n-month horizon (fees excluded).

    Returns (charges or None, assumption codes, missing, conditional).
    """
    assumptions: list[str] = []
    missing: list[str] = []
    conditional = False

    period = inp.billing_period
    if period == "unknown":
        return None, assumptions, ["billing_period"], False
    if period == "weekly":
        return None, ["weekly_not_projected"], [], False

    if period == "one_time":
        price = inp.recurring_price if inp.recurring_price is not None else inp.intro_price
        if price is None:
            return None, assumptions, ["price"], False
        return [price], assumptions, missing, False

    # Number of charges in the horizon, assuming billing continues.
    n_charges = n_months if period == "monthly" else 1  # yearly: one charge covers 12 months

    intro_periods = inp.intro_periods
    if inp.intro_price is not None and intro_periods is None:
        intro_periods = 1
        assumptions.append("intro_one_period")
        conditional = True

    trial = inp.trial_days or 0
    if inp.auto_renewal == "no":
        if trial > 0:
            assumptions.append("trial_no_auto_renewal")
            return [], assumptions, missing, conditional
        if n_charges > 1:
            assumptions.append("no_auto_renewal")
        n_charges = 1
    elif inp.auto_renewal == "not_stated":
        if trial > 0:
            assumptions.append("trial_conversion_unstated")
            conditional = True
        elif n_charges > 1:
            assumptions.append("renewal_unstated")
            conditional = True

    charges: list[Decimal] = []
    for k in range(1, n_charges + 1):
        if inp.intro_price is not None and k <= (intro_periods or 0):
            charges.append(inp.intro_price)
        elif inp.recurring_price is not None:
            charges.append(inp.recurring_price)
        else:
            return None, assumptions, ["recurring_price"], conditional
    return charges, assumptions, missing, conditional


def calculate(inp: CostInputs) -> CostReport:
    fees_total = sum((f.amount for f in inp.one_time_fees), Decimal("0"))
    trial = inp.trial_days or 0
    note_codes: list[str] = []
    if inp.currency is None:
        note_codes.append("currency_not_stated")
    elif currency_code(inp.currency) == DOLLAR:
        note_codes.append("currency_symbol_ambiguous")
    if inp.trial_days is None:
        note_codes.append("no_trial_stated")

    projections: list[Projection] = []
    for n in HORIZONS:
        charges, assumptions, missing, conditional = _charge_schedule(inp, n)
        base = ["horizon", "no_cancel"]
        if inp.one_time_fees:
            base.append("fees_at_signup")
        if charges is None:
            projections.append(_projection(n, "unavailable", assumptions, missing=missing))
            continue
        projections.append(
            _projection(
                n,
                "conditional" if conditional else "complete",
                base + assumptions,
                total=sum(charges, Decimal("0")) + fees_total,
            )
        )

    # First subscription charge (independent of horizon).
    first_charges, _, _, _ = _charge_schedule(inp, 1)
    first_amount = first_charges[0] if first_charges else None
    converts = trial == 0 or inp.auto_renewal == "yes"
    first_day = trial if (first_amount is not None and converts) else None

    if trial > 0:
        due_at_signup: Decimal | None = fees_total
    elif first_charges is None:
        due_at_signup = None
        note_codes.append("due_at_signup_unknown")
    else:
        due_at_signup = (first_amount or Decimal("0")) + fees_total

    return CostReport(
        currency=inp.currency,
        trial_days=trial,
        due_at_signup=due_at_signup,
        first_paid_charge_day=first_day,
        first_paid_charge_amount=first_amount if converts else None,
        one_time_fees_total=fees_total,
        projections=projections,
        notes=[NOTES[c] for c in note_codes],
        note_codes=note_codes,
    )
