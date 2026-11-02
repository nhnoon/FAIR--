"""Decision Twin: two paths computed from verified terms only.

Path "continue": keep the subscription. Totals are exactly cost.calculate()'s
projections; this module adds receipt lines (quantity x unit price per verified
source field) that sum to the same totals.

Path "cancel": cancel before the documented deadline. Built ONLY when the verified
terms state automatic renewal, a cancellation rule FAIR can map to a deadline, and a
supported billing period. It is never presented as certain: it is always
"conditional", because FAIR cannot confirm that cancelling is free or that refunds
apply. Amounts already charged are counted as paid (no refund is assumed).

No AI arithmetic: every amount here is Decimal math on verified values.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .cost import HORIZONS, CostInputs, _charge_schedule, calculate

CancelBy = Literal["trial_end", "renewal", "anytime", "not_stated"]
ScenarioStatus = Literal["complete", "conditional", "unavailable"]

CANCEL_ASSUMPTIONS = ["cancel_before_deadline", "cancellation_fee_not_stated", "no_refund_assumed"]


class CancelNotice(BaseModel):
    amount: int = Field(ge=1)
    unit: Literal["hours", "days"]


class ReceiptLine(BaseModel):
    kind: Literal["one_time_fee", "intro_charge", "recurring_charge"]
    label: str | None = None
    quantity: int
    unit_amount: Decimal
    amount: Decimal
    source_field: str = Field(description="Verified fact behind this amount: intro_price, recurring_price or fee:<index>.")


class ScenarioHorizon(BaseModel):
    months: int
    status: ScenarioStatus
    total: Decimal | None = None
    lines: list[ReceiptLine] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class CancelDeadline(BaseModel):
    kind: Literal["trial_end", "first_renewal"]
    day: int | None = Field(default=None, description="Days after signup (trial end); null when not stated.")
    notice: CancelNotice | None = None
    last_safe_hour: int | None = Field(
        default=None,
        description="Latest safe cancellation in hours after signup: trial end minus the stated notice. Null unless both are stated.",
    )


class Scenario(BaseModel):
    key: Literal["continue", "cancel"]
    status: ScenarioStatus
    reason: str | None = Field(default=None, description="Why the scenario is unavailable.")
    horizons: list[ScenarioHorizon] = Field(default_factory=list)
    assumption_codes: list[str] = Field(default_factory=list)
    deadline: CancelDeadline | None = None


class Difference(BaseModel):
    months: int
    amount: Decimal = Field(description="continue total - cancel total; both from verified terms.")


class DecisionTwin(BaseModel):
    continue_path: Scenario
    cancel_path: Scenario
    difference: list[Difference] = Field(default_factory=list)


def _lines(inp: CostInputs, charges: list[Decimal], intro_periods: int | None) -> list[ReceiptLine]:
    lines: list[ReceiptLine] = []
    for i, fee in enumerate(inp.one_time_fees):
        lines.append(
            ReceiptLine(kind="one_time_fee", label=fee.label, quantity=1, unit_amount=fee.amount, amount=fee.amount, source_field=f"fee:{i}")
        )
    if not charges:
        return lines
    if inp.billing_period == "one_time":  # a single purchase, not a subscription charge series
        field = "recurring_price" if inp.recurring_price is not None else "intro_price"
        lines.append(ReceiptLine(kind="recurring_charge", quantity=1, unit_amount=charges[0], amount=charges[0], source_field=field))
        return lines
    n_intro = min(len(charges), intro_periods or 1) if inp.intro_price is not None else 0
    if n_intro:
        lines.append(
            ReceiptLine(kind="intro_charge", quantity=n_intro, unit_amount=inp.intro_price, amount=inp.intro_price * n_intro, source_field="intro_price")
        )
    rest = charges[n_intro:]
    if rest:
        lines.append(
            ReceiptLine(kind="recurring_charge", quantity=len(rest), unit_amount=rest[0], amount=sum(rest, Decimal("0")), source_field="recurring_price")
        )
    return lines


def _continue_path(inp: CostInputs) -> Scenario:
    report = calculate(inp)
    horizons = []
    codes: list[str] = []
    for p in report.projections:
        charges, _, _, _ = _charge_schedule(inp, p.months)
        lines = _lines(inp, charges, inp.intro_periods) if charges is not None else []
        # Receipt lines must reproduce the engine's total exactly; never show a receipt that disagrees.
        if p.total is not None and sum((ln.amount for ln in lines), Decimal("0")) != p.total:
            raise RuntimeError("receipt lines diverged from the cost engine")
        horizons.append(ScenarioHorizon(months=p.months, status=p.status, total=p.total, lines=lines, missing=p.missing))
        for c in p.assumption_codes:
            if c not in codes:
                codes.append(c)
    statuses = {h.status for h in horizons}
    status = "unavailable" if statuses == {"unavailable"} else ("complete" if statuses == {"complete"} else "conditional")
    return Scenario(key="continue", status=status, horizons=horizons, assumption_codes=codes)


def _unavailable(reason: str) -> Scenario:
    return Scenario(key="cancel", status="unavailable", reason=reason)


def _cancel_path(inp: CostInputs, cancel_by: CancelBy, notice: CancelNotice | None) -> Scenario:
    if inp.auto_renewal == "no":
        return _unavailable("no_automatic_renewal")
    if inp.auto_renewal != "yes":
        return _unavailable("renewal_not_stated")
    if cancel_by == "not_stated":
        return _unavailable("cancellation_terms_not_stated")
    if inp.billing_period not in ("monthly", "yearly"):
        return _unavailable("billing_period_unsupported")

    trial = inp.trial_days or 0
    codes = list(CANCEL_ASSUMPTIONS)
    if trial > 0:
        if cancel_by not in ("trial_end", "anytime"):
            # e.g. "cancel before renewal" with a trial: whether trial end counts is ambiguous.
            return _unavailable("cancellation_deadline_ambiguous")
        last_safe_hour = None
        if notice is not None:
            last_safe_hour = trial * 24 - notice.amount * (24 if notice.unit == "days" else 1)
            if last_safe_hour <= 0:  # the notice is as long as the trial: no safe moment can be derived
                return _unavailable("cancellation_deadline_ambiguous")
        charges: list[Decimal] = []
        deadline = CancelDeadline(kind="trial_end", day=trial, notice=notice, last_safe_hour=last_safe_hour)
    else:
        if cancel_by not in ("renewal", "anytime"):
            return _unavailable("cancellation_deadline_ambiguous")
        first, first_codes, missing, _ = _charge_schedule(inp, 1)
        if not first:
            return _unavailable("price_not_stated" if missing else "cancellation_deadline_ambiguous")
        charges = first[:1]
        codes += [c for c in first_codes if c not in codes]
        deadline = CancelDeadline(kind="first_renewal", day=None, notice=notice)

    fees = sum((f.amount for f in inp.one_time_fees), Decimal("0"))
    lines = _lines(inp, charges, 1)
    total = fees + sum(charges, Decimal("0"))
    horizons = [ScenarioHorizon(months=n, status="conditional", total=total, lines=lines) for n in HORIZONS]
    return Scenario(key="cancel", status="conditional", horizons=horizons, assumption_codes=codes, deadline=deadline)


def build_decision(inp: CostInputs, cancel_by: CancelBy = "not_stated", notice: CancelNotice | None = None) -> DecisionTwin:
    cont = _continue_path(inp)
    canc = _cancel_path(inp, cancel_by, notice)
    diff = []
    if canc.status != "unavailable":
        by_month = {h.months: h for h in canc.horizons}
        for h in cont.horizons:
            other = by_month.get(h.months)
            if h.total is not None and other is not None and other.total is not None:
                diff.append(Difference(months=h.months, amount=h.total - other.total))
    return DecisionTwin(continue_path=cont, cancel_path=canc, difference=diff)
