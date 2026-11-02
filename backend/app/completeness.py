"""Is a cost total trustworthy? Arithmetic can be right while the projection is incomplete.

The cost engine only sees the prices it is given. This module compares those verified prices with
the source terms and answers one question: do they account for what the terms say the user pays?

Withheld (no numeric projection):
  unit_quantity_unknown  the verified price is per seat, user or device, and no quantity is modelled
  unaccounted_charge     the terms state another amount that no verified price or fee accounts for
  conflicting_renewal    the terms both state and deny automatic renewal
  percentage_charge      the terms state a tax or fee as a percentage, not included in the price
  tax_not_included       the terms mention a tax, with no rate, and do not say the price includes it

FAIR never calculates a percentage: the base and whether it applies to this person are not verified.
A tax not stated as included always withholds, even when the terms hedge ("VAT may apply").

Counted as an assumption (total shown, labelled conditional, the amount or rate named):
  an unaccounted amount or percentage fee that the terms present as optional or as depending on a condition

An amount per period that reconciles with a verified yearly price (USD 8/month, billed as USD 96/year)
is the same charge restated, so it is accounted for.

These read wording, so they catch explicit signals rather than meaning. See README limitations.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from .cost import ASSUMPTIONS, NOTES, CostInputs, CostReport, NotCountedAmount, WithheldReason
from .decision import DecisionTwin, Scenario, ScenarioHorizon
from .evidence import _NUMBER, _normalize_with_map
from .money import (
    _COUNTED_AFTER,
    _COUNTED_BEFORE,
    _CURRENCY_AT_END,
    _CURRENCY_AT_START,
    _PER_PERIOD_AFTER,
    _SENTENCE_END,
    _words_after,
    _words_before,
)

_UNITS = r"seat|seats|user|users|member|members|device|devices|license|licence|licenses|licences|person|employee|employees|screen|screens"
_UNIT_PRICE = re.compile(
    rf"\bper[\s-](?:{_UNITS})\b|/\s*(?:{_UNITS})\b|\beach\s+(?:{_UNITS})\b"
    r"|لكل\s+(?:مستخدم|مقعد|جهاز|عضو|موظف|شخص|ترخيص|شاشة)|للمستخدم الواحد|للمقعد الواحد|للجهاز الواحد"
)
_NOT_REQUIRED = re.compile(r"\boptional(?:ly)?\b|\bif\b|\byou may add\b|\bif you (?:add|choose)\b|اختياري|اختيارية|إذا|اذا")
_RENEWS = re.compile(r"\brenews?\s+automatically\b|\bautomatically\s+renew|\bauto[\s-]?renew|(?:يتجدد|تتجدد).*تلقائ|تلقائ.*(?:يتجدد|تتجدد)")
_DOES_NOT_RENEW = re.compile(
    r"\b(?:does not|do not|doesn't|don't|will not|won't|not)\s+(?:auto(?:matically)?[\s-]?)?renew|\bno\s+auto(?:matic)?[\s-]?renewal\b"
    r"|(?:لا|لن)\s+(?:يتجدد|تتجدد)|لا\s+يتم\s+التجديد|بدون\s+تجديد\s+تلقائي"
)
YEARLY_EQUIVALENT_PERIODS = 12

_PERCENT_SIGN = r"[%٪]|\bpercent\b|\bper cent\b|\bpct\b|بالمئة|بالمائة|في المئة|في المائة"
_PERCENT = re.compile(rf"(?P<rate>{_NUMBER.pattern})\s*(?:{_PERCENT_SIGN})|[%٪]\s*(?P<rate_after>{_NUMBER.pattern})")
_TAX = re.compile(r"\bvat\b|\btax(?:es)?\b|\bgst\b|\bhst\b|ضريب|القيمة المضافة")
_NOT_A_TAX_CHARGE = re.compile(
    r"\btax[\s-]?free\b|\bno\s+(?:additional\s+|extra\s+)?(?:tax|taxes|vat)\b|\b(?:tax|vat)\s+(?:invoice|receipt|number|id|registration)"
    r"|الرقم الضريبي|فاتورة ضريبية|معف[ىاي]"
)
_TAX_EXCLUDED = re.compile(
    r"\bexcl|\b(?:not|does not|do not|doesn't|don't)\s+incl|\bwithout\b|\bbefore\b|\bpre[\s-]?tax|\bplus\b|\+|\bextra\b|\badded\b|\bon top\b"
    r"|غير\s+(?:شامل|متضمن)|لا\s+(?:يشمل|تشمل|يتضمن|تتضمن)|بدون|باستثناء|قبل|تضاف|يضاف|بالإضافة"
)
_TAX_INCLUDED = re.compile(r"\bincl|شامل|يشمل|تشمل|يتضمن|تتضمن|متضمن")
_CHARGE_WORD = re.compile(
    r"\bfees?\b|\bcharg|\bsurcharge|\bcommission|\blevy\b|\bduty\b|\bgratuity\b|\binterest\b|\bcosts?\b|\bmark[\s-]?up\b"
    r"|\bincreas|\braises?\b|\brises?\b|\badded\b|رسوم|رسم\b|عمولة|فائدة|زيادة|ترتفع|يرتفع|تضاف|يضاف"
)
_PLUS_BEFORE = re.compile(r"(?:\bplus\b|\+|بالإضافة إلى|زائد)\s*(?:(?:an?|additional|another)\s+)*$")
_SAVING_AFTER = re.compile(r"^\s*(?:off\b|discount|cash[\s-]?back|back\b|refund|savings?\b|خصم|تخفيض)")
_SAVING_BEFORE = re.compile(r"(?:\bsave\b|\bsaving\b|\bdiscount(?: of)?\b|\brefund(?: of)?\b|خصم|تخفيض|استرداد|توفير|وفر)(?:\s+(?:up to|بنسبة|قدره|قدرها))?\s*$")
_RATE_CONDITIONAL = re.compile(rf"{_NOT_REQUIRED.pattern}|\bearly\b|\blate\b|\boverdue\b|مبكر|تأخ")


class Assessment(BaseModel):
    withheld: list[WithheldReason] = []
    not_counted: list[NotCountedAmount] = []


def _sentences(norm: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for end in _SENTENCE_END.finditer(norm):
        spans.append((start, end.end()))
        start = end.end()
    if start < len(norm):
        spans.append((start, len(norm)))
    return spans


def _original(terms: str, index_map: list[int], start: int, end: int) -> str:
    return terms[index_map[start] : index_map[end - 1] + 1].strip()


def _assess_percentages_and_tax(terms: str, norm: str, index_map: list[int], sentences: list[tuple[int, int]], result: Assessment) -> None:
    seen: set[Decimal] = set()
    for start, end in sentences:
        sentence = norm[start:end]
        taxed = bool(_TAX.search(_NOT_A_TAX_CHARGE.sub(" ", sentence)))
        included = taxed and bool(_TAX_INCLUDED.search(sentence)) and not _TAX_EXCLUDED.search(sentence)
        quote = _original(terms, index_map, start, end)
        tax_rate_found = False
        for found in _PERCENT.finditer(sentence):
            rate = Decimal((found["rate"] or found["rate_after"]).replace(",", ""))
            before, after = sentence[: found.start()], sentence[found.end() :]
            if rate == 0 or _SAVING_AFTER.match(after) or _SAVING_BEFORE.search(before):
                continue
            words = _words_before(sentence, found.start()) + " " + _words_after(after)
            is_tax = bool(_TAX.search(words))
            if not (is_tax or _CHARGE_WORD.search(words) or _PLUS_BEFORE.search(before)):
                continue  # uptime, satisfaction, a share of users: not stated as something the user pays
            tax_rate_found = tax_rate_found or is_tax
            if (is_tax and included) or rate in seen:
                continue
            seen.add(rate)
            if not is_tax and _RATE_CONDITIONAL.search(sentence):
                result.not_counted.append(NotCountedAmount(rate=rate, quote=quote))
            else:
                result.withheld.append(WithheldReason(code="percentage_charge", rate=rate, quote=quote))
        if taxed and not included and not tax_rate_found:
            result.withheld.append(WithheldReason(code="tax_not_included", quote=quote))


def assess(terms: str, inputs: CostInputs) -> Assessment:
    norm, index_map = _normalize_with_map(terms)
    sentences = _sentences(norm)
    around = lambda pos: next(((s, e) for s, e in sentences if s <= pos < e), (0, len(norm)))  # noqa: E731
    known = {p for p in (inputs.recurring_price, inputs.intro_price) if p is not None} | {f.amount for f in inputs.one_time_fees}
    result = Assessment()
    seen: set[Decimal] = set()

    for number in _NUMBER.finditer(norm):
        try:
            amount = Decimal(number[0].replace(",", ""))
        except InvalidOperation:  # pragma: no cover - the regex only yields numerics
            continue
        before, after = norm[: number.start()], norm[number.end() :]
        if _COUNTED_AFTER.match(after) or _COUNTED_BEFORE.search(before):
            continue  # a duration or a percentage
        per_period = bool(_PER_PERIOD_AFTER.match(after))
        if not (per_period or _CURRENCY_AT_END.search(before) or _CURRENCY_AT_START.match(after)):
            continue  # not stated as money
        start, end = around(number.start())
        quote = _original(terms, index_map, start, end)

        if amount in (inputs.recurring_price, inputs.intro_price):
            words = _words_before(norm, number.start()) + " " + _words_after(after)
            if _UNIT_PRICE.search(words) and not any(w.code == "unit_quantity_unknown" for w in result.withheld):
                result.withheld.append(WithheldReason(code="unit_quantity_unknown", amount=amount, quote=quote))
            continue
        if amount in known or amount in seen:
            continue
        if inputs.billing_period == "yearly" and per_period and amount * YEARLY_EQUIVALENT_PERIODS == inputs.recurring_price:
            continue  # the same yearly charge, restated per period
        seen.add(amount)
        if _NOT_REQUIRED.search(norm[start:end]):
            result.not_counted.append(NotCountedAmount(amount=amount, quote=quote))
        else:
            result.withheld.append(WithheldReason(code="unaccounted_charge", amount=amount, quote=quote))

    _assess_percentages_and_tax(terms, norm, index_map, sentences, result)

    says_renews = next(((s, e) for s, e in sentences if _RENEWS.search(norm[s:e]) and not _DOES_NOT_RENEW.search(norm[s:e])), None)
    says_not = next(((s, e) for s, e in sentences if _DOES_NOT_RENEW.search(norm[s:e])), None)
    if says_renews and says_not:
        quote = f"{_original(terms, index_map, *says_renews)} {_original(terms, index_map, *says_not)}"
        result.withheld.append(WithheldReason(code="conflicting_renewal", quote=quote))
    return result


def _has_total(cost: CostReport) -> bool:
    return any(p.total is not None for p in cost.projections) or bool(cost.due_at_signup)


def apply_assessment(cost: CostReport, decision: DecisionTwin, assessment: Assessment) -> tuple[CostReport, DecisionTwin]:
    """Facts stay in extracted_terms. Only totals built on them are withheld or relabelled."""
    if not _has_total(cost):  # nothing to protect: no amount is shown, for its own reason
        return cost, decision
    if assessment.withheld:
        return _withhold(cost, decision, assessment)
    if assessment.not_counted:
        return _label_not_counted(cost, decision, assessment)
    return cost, decision


def _withhold(cost: CostReport, decision: DecisionTwin, assessment: Assessment) -> tuple[CostReport, DecisionTwin]:
    codes = list(dict.fromkeys(w.code for w in assessment.withheld))
    projections = [p.model_copy(update={"status": "unavailable", "total": None, "assumptions": [], "assumption_codes": [], "missing": codes}) for p in cost.projections]
    note_codes = list(cost.note_codes)
    notes = list(cost.notes)
    if "due_at_signup_unknown" not in note_codes:
        note_codes.append("due_at_signup_unknown")
        notes.append(NOTES["due_at_signup_unknown"])
    report = cost.model_copy(
        update={
            "projections": projections,
            "due_at_signup": None,
            "first_paid_charge_day": None,
            "first_paid_charge_amount": None,
            "note_codes": note_codes,
            "notes": notes,
            "withheld": assessment.withheld,
            "not_counted": assessment.not_counted,
        }
    )
    horizons = [ScenarioHorizon(months=h.months, status="unavailable", missing=codes) for h in decision.continue_path.horizons]
    twin = DecisionTwin(
        continue_path=Scenario(key="continue", status="unavailable", reason=codes[0], horizons=horizons),
        cancel_path=Scenario(key="cancel", status="unavailable", reason=codes[0]),
        difference=[],
    )
    return report, twin


def _with_assumption(codes: list[str]) -> list[str]:
    return codes if "amount_not_counted" in codes else [*codes, "amount_not_counted"]


def _label_not_counted(cost: CostReport, decision: DecisionTwin, assessment: Assessment) -> tuple[CostReport, DecisionTwin]:
    text = ASSUMPTIONS["amount_not_counted"]
    projections = [
        p.model_copy(update={"status": "conditional", "assumption_codes": _with_assumption(p.assumption_codes), "assumptions": [*p.assumptions, text]}) if p.total is not None else p
        for p in cost.projections
    ]
    report = cost.model_copy(update={"projections": projections, "not_counted": assessment.not_counted})

    def relabel(path: Scenario) -> Scenario:
        if path.status == "unavailable":
            return path
        horizons = [h.model_copy(update={"status": "conditional"}) if h.total is not None else h for h in path.horizons]
        return path.model_copy(update={"status": "conditional", "horizons": horizons, "assumption_codes": _with_assumption(path.assumption_codes)})

    return report, decision.model_copy(update={"continue_path": relabel(decision.continue_path), "cancel_path": relabel(decision.cancel_path)})

