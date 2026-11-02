"""Expectation Gap Detection pipeline.

model JSON (untrusted) -> schema validation -> evidence verification
-> verified terms only -> deterministic cost engine -> response.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any, Callable

from pydantic import ValidationError

from .claims import build_claims, is_relevant
from .completeness import apply_assessment, assess
from .cost import CostInputs, Fee, calculate
from .decision import CancelNotice, build_decision
from .evidence import QuoteCheck, normalize, value_in_quote, verify_quote
from .meta_client import MetaClient, ModelResponseError
from .money import PriceKind, billing_problem, money_problem, parse_money
from .prompts import INSTRUCTIONS, build_input
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Evidence,
    Explanation,
    ExtractedTerms,
    FeeOut,
    ModelAnalysis,
    ModelFact,
    VerifiedFact,
    _to_decimal,
)

DOWNGRADED_EXPLANATION = Explanation(
    en=(
        "We could not confirm this from the offer text: the quoted evidence was not found in the terms, "
        "so FAIR marks it as unknown. Please read the terms directly."
    ),
    ar=(
        "تعذّر التحقق من ذلك من نص العرض: لم يُعثر على الاقتباس المستشهد به في الشروط، "
        "لذلك يصنّفه FAIR على أنه غير معروف. يُرجى قراءة الشروط مباشرة."
    ),
)

_BILLING = {"monthly", "yearly", "weekly", "one_time", "unknown"}
_RENEWAL = {"yes", "no", "not_stated"}
_CANCEL_BY = {"trial_end", "renewal", "anytime", "not_stated"}
_FACT_ORDER = ("currency", "trial_days", "intro_price", "intro_periods", "recurring_price", "billing_period", "auto_renewal",
               "cancellation_requirement", "cancel_by", "cancel_notice")
_BILLING_REASONS = {"billing_period_mismatch", "billing_period_unsupported", "billing_period_not_in_quote", "price_type_not_stated", "one_time_not_recurring"}
_NOTICE_UNIT_WORDS = {"hours": ("hour", "hr", "ساع"), "days": ("day", "يوم", "ايام", "أيام")}
# Every group must appear in the quote. "Continues until cancelled" states no deadline at all.
_DEADLINE_WORDS = ("before", "prior to", "no later than", "by the end", "قبل")
_CANCEL_BY_WORDS = {
    "trial_end": (("trial", "تجرب"), _DEADLINE_WORDS),
    "renewal": (("renew", "تجدد", "تجديد"), _DEADLINE_WORDS),
    "anytime": (("any time", "anytime", "at any point", "أي وقت", "اي وقت"),),
}


def _notice(v: Any) -> CancelNotice:
    if not isinstance(v, dict):
        raise ValueError("notice must be an object")
    return CancelNotice(amount=_count(v.get("amount")), unit=str(v.get("unit", "")).strip().lower())


def _about_cancelling(_value: Any, quote: str) -> str | None:
    return None if is_relevant("cancellation", "", quote) else "quote_not_about_cancellation"


def _cancel_by_stated(value: str, quote: str) -> str | None:
    problem = _about_cancelling(value, quote)
    if problem:
        return problem
    q = normalize(quote)
    if not all(any(normalize(word) in q for word in group) for group in _CANCEL_BY_WORDS[value]):
        return "quote_does_not_state_deadline"
    return None


def _notice_in_quote(value: CancelNotice, quote: str) -> str | None:
    if not value_in_quote(value.amount, quote):
        return "value_not_in_quote"
    # Dates are calculated from this notice, so its unit must be verified too (48 hours is not 48 days).
    if not any(normalize(word) in normalize(quote) for word in _NOTICE_UNIT_WORDS[value.unit]):
        return "value_not_in_quote"
    return _about_cancelling(value, quote)


def _amount(v: Any) -> Decimal:
    return parse_money(v).amount


def _count(v: Any) -> int:
    if isinstance(v, bool):
        raise ValueError("boolean is not a count")
    d = _to_decimal(v)
    if not isinstance(d, Decimal) or d != d.to_integral_value() or d < 0:
        raise ValueError("not a non-negative integer")
    return int(d)


def _text(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError("not text")
    return v.strip()


def _enum(allowed: set[str]) -> Callable[[Any], str]:
    def coerce(v: Any) -> str:
        s = _text(v).lower().replace("-", "_").replace(" ", "_")
        if s not in allowed:
            raise ValueError(f"not one of {sorted(allowed)}")
        return s

    return coerce


def _evidence(qc: QuoteCheck) -> Evidence:
    return Evidence(**asdict(qc))


class _Verifier:
    def __init__(self, terms: str):
        self.terms = terms
        self.facts: list[VerifiedFact] = []
        self.rejected: list[VerifiedFact] = []

    def _reject(self, field: str, value: Any, quote: str | None, reason: str) -> None:
        self.rejected.append(
            VerifiedFact(
                field=field,
                value=value if isinstance(value, (str, int, float)) or value is None else str(value),
                evidence=Evidence(quote=quote or "", verified=False, reason=reason),
            )
        )

    def check(
        self,
        field: str,
        fact: ModelFact,
        coerce: Callable[[Any], Any],
        *,
        numeric: bool = False,
        literal: bool = False,
        no_evidence_ok: Any = None,
        extra: Callable[[Any, str], str | None] | None = None,
    ) -> Any:
        """Return the value if (and only if) its evidence is verified, else None.

        numeric: the number must literally appear in the quote.
        literal: the text value must literally appear in the quote (e.g. currency).
        no_evidence_ok: a "not stated" value that is accepted without a quote.
        extra: further deterministic check (value, quote) -> rejection reason or None.
        """
        if fact.value is None:
            return None
        try:
            value = coerce(fact.value)
        except (ValueError, TypeError):
            self._reject(field, fact.value, fact.evidence, "invalid_value")
            return None
        if no_evidence_ok is not None and value == no_evidence_ok:
            return value
        qc = verify_quote(fact.evidence, self.terms)
        if qc.verified and numeric and not value_in_quote(value, fact.evidence or ""):
            qc = QuoteCheck(qc.quote, False, reason="value_not_in_quote")
        if qc.verified and literal and normalize(str(value)) not in normalize(fact.evidence or ""):
            qc = QuoteCheck(qc.quote, False, reason="value_not_in_quote")
        if qc.verified and extra is not None:
            problem = extra(value, fact.evidence or "")
            if problem:
                qc = QuoteCheck(qc.quote, False, reason=problem)
        if not qc.verified:
            self.rejected.append(VerifiedFact(field=field, value=_jsonable(value), evidence=_evidence(qc)))
            return None
        self.facts.append(VerifiedFact(field=field, value=_jsonable(value), evidence=_evidence(qc)))
        return value


def _jsonable(v: Any) -> Any:
    return str(v) if isinstance(v, Decimal) else v


def analyze(request: AnalyzeRequest, client: MetaClient) -> AnalyzeResponse:
    raw = client.generate_json(INSTRUCTIONS, build_input(request.terms, request.expectation))
    try:
        parsed = ModelAnalysis.model_validate(raw)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise ModelResponseError(f"The model response did not match the expected schema (fields: {', '.join(fields)}).") from exc

    ex = parsed.extraction
    v = _Verifier(request.terms)
    currency = v.check("currency", ex.currency, _text, literal=True)
    trial_days = v.check("trial_days", ex.trial_days, _count, numeric=True)
    # Before the prices: a price must agree with the verified billing period.
    billing = v.check("billing_period", ex.billing_period, _enum(_BILLING), no_evidence_ok="unknown", extra=billing_problem) or "unknown"

    def price(field: str, fact: ModelFact, kind: PriceKind) -> Decimal | None:
        return v.check(field, fact, _amount, extra=lambda _, quote: money_problem(parse_money(fact.value), quote, kind, currency, billing))

    intro_price = price("intro_price", ex.intro_price, "intro")
    intro_periods = v.check("intro_periods", ex.intro_periods, _count, numeric=True)
    recurring = price("recurring_price", ex.recurring_price, "recurring")
    renewal = v.check("auto_renewal", ex.auto_renewal, _enum(_RENEWAL), no_evidence_ok="not_stated") or "not_stated"
    cancellation = v.check("cancellation_requirement", ex.cancellation_requirement, _text)
    cancel_by = (
        v.check("cancel_by", ex.cancel_by, _enum(_CANCEL_BY), no_evidence_ok="not_stated", extra=_cancel_by_stated)
        or "not_stated"
    )
    cancel_notice = v.check("cancel_notice", ex.cancel_notice, _notice, extra=_notice_in_quote)

    # Billing is checked first but reported in the usual order.
    for found in (v.facts, v.rejected):
        found.sort(key=lambda f: _FACT_ORDER.index(f.field) if f.field in _FACT_ORDER else len(_FACT_ORDER))

    fees: list[FeeOut] = []
    for fee in ex.one_time_fees:
        label = fee.label.strip() or "fee"
        try:
            amount = _amount(fee.amount)
        except (ValueError, TypeError):
            v._reject(f"one_time_fee:{label}", fee.amount, fee.evidence, "invalid_value")
            continue
        qc = verify_quote(fee.evidence, request.terms)
        problem = money_problem(parse_money(fee.amount), fee.evidence or "", "one_time", currency) if qc.verified else None
        if problem:
            qc = QuoteCheck(qc.quote, False, reason=problem)
        out = FeeOut(label=label, amount=amount, evidence=_evidence(qc))
        if qc.verified:
            fees.append(out)
        else:
            v.rejected.append(VerifiedFact(field=f"one_time_fee:{label}", value=str(amount), evidence=out.evidence))

    warnings: list[str] = []
    if any(f.evidence.reason in _BILLING_REASONS for f in v.rejected):
        warnings.append("A price or billing period was excluded because the terms do not state it clearly enough to calculate from it.")

    # Verdict: MATCH / CONTRADICTION must rest on a verified quote.
    verdict_evidence: Evidence | None = None
    if parsed.verdict_evidence:
        verdict_evidence = _evidence(verify_quote(parsed.verdict_evidence, request.terms))
    verdict = parsed.verdict
    explanation = Explanation(en=parsed.explanation.en, ar=parsed.explanation.ar)
    downgraded = False
    if verdict != "UNKNOWN" and not (verdict_evidence and verdict_evidence.verified):
        verdict, downgraded, explanation = "UNKNOWN", True, DOWNGRADED_EXPLANATION
        warnings.append(
            f"The model answered {parsed.verdict}, but its evidence was not found in the terms; shown as UNKNOWN."
        )
    if v.rejected:
        warnings.append(
            f"{len(v.rejected)} extracted value(s) could not be verified against the terms and were excluded."
        )

    inputs = CostInputs(
        currency=currency,
        trial_days=trial_days,
        intro_price=intro_price,
        intro_periods=intro_periods if intro_periods and intro_periods >= 1 else None,
        recurring_price=recurring,
        billing_period=billing,
        auto_renewal=renewal,
        one_time_fees=[Fee(label=f.label, amount=f.amount) for f in fees],
    )
    cost = calculate(inputs)
    decision = build_decision(inputs, cancel_by, cancel_notice)
    # Every consumer reads the totals from here, so the receipt and the reveal cannot disagree.
    cost, decision = apply_assessment(cost, decision, assess(request.terms, inputs))
    if cost.withheld:
        warnings.append("Cost totals were withheld because the verified prices do not account for what the terms say you would pay.")

    claims, claims_summary = build_claims(
        parsed.claims,
        request.terms,
        request.expectation,
        fallback_verdict=verdict,
        fallback_evidence=verdict_evidence,
        fallback_explanation=explanation,
    )
    downgraded_claims = sum(c.downgraded for c in claims)
    if downgraded_claims:
        warnings.append(f"{downgraded_claims} claim verdict(s) were not supported by relevant evidence; shown as UNKNOWN.")

    if claims_summary.dropped:
        warnings.append(f"{claims_summary.dropped} model claim(s) could not be read, so the result cannot be a full match.")

    if claims_summary.omitted_amounts:
        warnings.append(f"{claims_summary.omitted_amounts} amount(s) in the expectation were not checked by any claim.")

    return AnalyzeResponse(
        verdict=verdict,
        verdict_downgraded=downgraded,
        model_verdict=parsed.verdict,
        verdict_evidence=verdict_evidence,
        explanation=explanation,
        extracted_terms=ExtractedTerms(
            currency=currency,
            trial_days=trial_days,
            intro_price=intro_price,
            intro_periods=intro_periods,
            recurring_price=recurring,
            billing_period=billing,
            auto_renewal=renewal,
            cancellation_requirement=cancellation,
            cancel_by=cancel_by,
            cancel_notice=cancel_notice,
            one_time_fees=fees,
        ),
        facts=v.facts,
        rejected_facts=v.rejected,
        cost=cost,
        warnings=warnings,
        model=client.model,
        claims=claims,
        claims_summary=claims_summary,
        decision=decision,
    )
