"""Strict API schemas and the schema the model's JSON output must satisfy."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .cost import AutoRenewal, BillingPeriod, CostReport
from .decision import CancelBy, CancelNotice, DecisionTwin
from .evidence import normalize_digits

Verdict = Literal["MATCH", "CONTRADICTION", "UNKNOWN"]
UILanguage = Literal["en", "ar"]

MAX_TERMS_CHARS = 20_000
MAX_EXPECTATION_CHARS = 2_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- request


class AnalyzeRequest(_Strict):
    terms: str = Field(min_length=1, max_length=MAX_TERMS_CHARS, description="Offer / terms text, verbatim.")
    expectation: str = Field(min_length=1, max_length=MAX_EXPECTATION_CHARS, description="What the user believes.")
    language: UILanguage = "en"


# ------------------------------------------------- model output (untrusted)


def _to_decimal(value: Any) -> Any:
    """Accept '9.99', 9.99, '٥٩', '1,299.00'. Leave None/other for pydantic to judge."""
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = normalize_digits(value).replace(",", "").strip()
        if cleaned == "":
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"not a numeric amount: {value!r}") from exc
    return value


class ModelFact(BaseModel):
    """An extracted value plus the verbatim quote that supports it."""

    model_config = ConfigDict(extra="ignore")
    value: Any = None
    evidence: str | None = None


class ModelFee(BaseModel):
    """Amount stays untyped here; the analyzer coerces it and rejects bad values
    individually, so one malformed fee does not discard the whole analysis."""

    model_config = ConfigDict(extra="ignore")
    label: str = Field(default="fee", max_length=200)
    amount: Any = None
    evidence: str | None = None


class ModelExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    currency: ModelFact = Field(default_factory=ModelFact)
    trial_days: ModelFact = Field(default_factory=ModelFact)
    intro_price: ModelFact = Field(default_factory=ModelFact)
    intro_periods: ModelFact = Field(default_factory=ModelFact)
    recurring_price: ModelFact = Field(default_factory=ModelFact)
    billing_period: ModelFact = Field(default_factory=ModelFact)
    auto_renewal: ModelFact = Field(default_factory=ModelFact)
    cancellation_requirement: ModelFact = Field(default_factory=ModelFact)
    # Structured cancellation rule (Decision Twin). value: trial_end | renewal | anytime | not_stated
    cancel_by: ModelFact = Field(default_factory=ModelFact)
    # value: {"amount": int, "unit": "hours" | "days"}, as written in the terms
    cancel_notice: ModelFact = Field(default_factory=ModelFact)
    one_time_fees: list[ModelFee] = Field(default_factory=list)


class ModelExplanation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    en: str = Field(min_length=1, max_length=2000)
    ar: str = Field(min_length=1, max_length=2000)


class ModelAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    extraction: ModelExtraction = Field(default_factory=ModelExtraction)
    verdict: Verdict
    verdict_evidence: str | None = None
    explanation: ModelExplanation
    # Atomic claims (Expectation Mirror). Untyped here: each item is validated on its own
    # in claims.py, so one malformed claim never discards the whole analysis.
    claims: list[Any] = Field(default_factory=list)

    @field_validator("claims", mode="before")
    @classmethod
    def _claims_list(cls, v: Any) -> Any:
        # A non-list "claims" is ignored (falls back to the overall verdict) rather than failing the analysis.
        return v if isinstance(v, list) else []

    @field_validator("verdict", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        return v.strip().upper() if isinstance(v, str) else v


# --------------------------------------------------------------- response


class Evidence(BaseModel):
    quote: str
    verified: bool
    start: int | None = None
    end: int | None = None
    reason: str | None = None


class VerifiedFact(BaseModel):
    field: str
    value: Any
    evidence: Evidence


class FeeOut(BaseModel):
    label: str
    amount: Decimal
    evidence: Evidence


class ExtractedTerms(BaseModel):
    """Only values whose evidence was verified are populated; others are null."""

    currency: str | None = None
    trial_days: int | None = None
    intro_price: Decimal | None = None
    intro_periods: int | None = None
    recurring_price: Decimal | None = None
    billing_period: BillingPeriod = "unknown"
    auto_renewal: AutoRenewal = "not_stated"
    cancellation_requirement: str | None = None
    cancel_by: CancelBy = "not_stated"
    cancel_notice: CancelNotice | None = None
    one_time_fees: list[FeeOut] = Field(default_factory=list)


class Explanation(BaseModel):
    en: str
    ar: str


ClaimTopic = Literal["price", "trial", "renewal", "cancellation", "refund", "fees", "other"]
ClaimReason = Literal[
    "evidence_not_found",
    "inconsistent_evidence_role",
    "evidence_not_relevant",
    "numbers_not_in_evidence",
    "no_claim_support",
    "absolute_claim_unsupported",
]


class Claim(BaseModel):
    """One atomic belief from the user's expectation, judged against the terms."""

    id: str
    text: str
    topic: ClaimTopic
    verdict: Verdict
    model_verdict: Verdict
    downgraded: bool = Field(description="True if FAIR replaced the model's verdict with UNKNOWN.")
    reason: ClaimReason | None = Field(default=None, description="Why the verdict was downgraded.")
    evidence: Evidence | None = Field(
        default=None, description="Verified quote only. A quote is evidence of presence, not proof of support."
    )
    evidence_role: Literal["supports", "contradicts"] | None = None
    explanation: Explanation
    from_overall: bool = Field(
        default=False, description="True when the model returned no claims and the overall verdict is used."
    )


class ClaimsSummary(BaseModel):
    overall: Verdict = Field(description="CONTRADICTION if any claim contradicts; else UNKNOWN if any is unknown; else MATCH.")
    counts: dict[str, int]
    dropped: int = Field(default=0, description="Model claims rejected as malformed or beyond the limit.")
    omitted_amounts: int = Field(default=0, description="Numbers in the expectation that no claim mentions.")


class AnalyzeResponse(BaseModel):
    verdict: Verdict
    verdict_downgraded: bool = Field(
        description="True if the model's verdict was replaced by UNKNOWN because its evidence failed verification."
    )
    model_verdict: Verdict
    verdict_evidence: Evidence | None
    explanation: Explanation
    extracted_terms: ExtractedTerms
    facts: list[VerifiedFact]
    rejected_facts: list[VerifiedFact] = Field(
        description="Model claims whose evidence failed verification. Not used for verdict or cost."
    )
    cost: CostReport
    warnings: list[str] = Field(default_factory=list)
    model: str
    # Decision Twin (additive; older consumers can ignore these fields).
    claims: list[Claim] = Field(default_factory=list)
    claims_summary: ClaimsSummary | None = None
    decision: DecisionTwin | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model: str
    base_url: str
    model_configured: bool
    live_calls_enabled: bool
