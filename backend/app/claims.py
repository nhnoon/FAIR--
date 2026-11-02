"""Expectation Mirror: per-claim verdicts with deterministic safety checks.

The model splits the user's expectation into atomic claims and judges each one
(semantic interpretation). FAIR then applies deterministic guards. A decisive verdict
(MATCH / CONTRADICTION) survives only if ALL of these hold; otherwise it becomes UNKNOWN:

  1. evidence_not_found          the quote exists verbatim in the terms
  2. inconsistent_evidence_role  the model's stated role agrees with its verdict
                                 (MATCH -> "supports", CONTRADICTION -> "contradicts")
  3. evidence_not_relevant       the quote is about the claim's topic (bilingual keywords;
                                 for topic "other": content-word overlap with the claim)
  4. numbers_not_in_evidence     for MATCH, every number in the claim appears in the quote
  5. absolute_claim_unsupported  for MATCH, a claim making an absolute or lasting promise needs a
                                 quote with promise or negation language of its own

These are NECESSARY conditions, not proof of entailment: a quote can pass all four and
still not logically support the claim. That residual judgement is the model's, and the
UI labels it "AI interpretation".

Known limits, pinned by test_known_limitation_* in tests/test_claims.py. Each is a semantic
judgement that word lists would only make brittle: quantities spelled as words are not seen
by guard 4, a belief the model omits is only detected when it contains a digit, and guard 5 only
sees explicit wording. A promise phrased another way passes, and a quote with such wording may
still not make that promise.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .evidence import normalize, numbers_in, verify_quote
from .money import states_money
from .schemas import Claim, ClaimsSummary, Evidence, Explanation, ModelExplanation

MAX_CLAIMS = 6
MAX_CLAIM_CHARS = 300

# Lower-case, diacritic-free stems (matched after evidence.normalize()).
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "trial": ("trial", "free", "تجرب", "تجربة", "مجان"),
    "renewal": ("renew", "automatic", "recurring", "continues", "until you cancel", "until cancel", "تجدد", "تجديد", "يتجدد", "تلقائ", "يستمر"),
    "cancellation": ("cancel", "terminat", "الغاء", "إلغاء", "تلغ", "يلغ", "إلغ"),
    "refund": ("refund", "reimburs", "money back", "non-refundable", "استرد", "استرجاع", "استرجع", "مسترد"),
    "fees": ("fee", "charge", "setup", "activation", "رسوم", "رسم"),
    "price": ("price", "cost", "usd", "sar", "eur", "$", "month", "year", "/mo", "سعر", "ريال", "دولار", "شهري", "سنوي", "مقابل"),
}

DOWNGRADE_TEXT: dict[str, Explanation] = {
    "evidence_not_found": Explanation(
        en="The quote the model cited was not found in the terms, so FAIR cannot confirm this claim.",
        ar="لم يُعثر على الاقتباس الذي استشهد به النموذج في الشروط، لذا لا يستطيع FAIR تأكيد هذا الادعاء.",
    ),
    "inconsistent_evidence_role": Explanation(
        en="The model's reasoning about this quote was inconsistent with its verdict, so FAIR treats the claim as not established.",
        ar="كان تفسير النموذج لهذا الاقتباس غير متسق مع حكمه، لذا يعدّ FAIR الادعاء غير ثابت.",
    ),
    "evidence_not_relevant": Explanation(
        en="The cited sentence exists in the terms but is not about this claim, so it does not prove it either way.",
        ar="الجملة المستشهد بها موجودة في الشروط لكنها لا تتعلق بهذا الادعاء، لذا لا تثبته ولا تنفيه.",
    ),
    "absolute_claim_unsupported": Explanation(
        en="This is an absolute or lasting promise, and the cited sentence does not make one. A current price or term does not guarantee the future.",
        ar="هذا وعد مطلق أو دائم، والجملة المستشهد بها لا تقدّم وعدًا كهذا. السعر أو الشرط الحالي لا يضمن المستقبل.",
    ),
    "no_claim_support": Explanation(
        en="The model gave an overall match but no claim-by-claim support for it, so FAIR does not present this as confirmed.",
        ar="أعطى النموذج تطابقًا عامًا دون دعم لكل ادعاء على حدة، لذا لا يعرضه FAIR على أنه مؤكد.",
    ),
    "numbers_not_in_evidence": Explanation(
        en="The amounts or durations in this claim do not appear in the cited sentence, so FAIR cannot confirm it.",
        ar="المبالغ أو المدد الواردة في هذا الادعاء غير موجودة في الجملة المستشهد بها، لذا لا يستطيع FAIR تأكيده.",
    ),
}

# Matched after evidence.normalize(), which removes Arabic diacritics.
_ABSOLUTE_CLAIM = re.compile(
    r"\b(?:never|always|forever|permanent(?:ly)?|guarantee[ds]?|lifetime|for life|locked in)\b"
    r"|\b(?:will not|won't|wont)\s+(?:change|increase|go up|rise)\b|\b(?:stays?|remains?)\s+the same\b|\bunchanged\b"
    r"|أبدا|ابدا|دائما|مضمون|يضمن|نضمن|ضمان|مدى الحياة|لن يتغير|لن يرتفع|لن تتغير|لن ترتفع|يبقى ثابت|تبقى ثابت"
)
_PROMISE_IN_QUOTE = re.compile(
    rf"{_ABSOLUTE_CLAIM.pattern}|\b(?:locked|fixed|any time|anytime|at all times|not|no)\b|n't\b"
    r"|ثابت|في أي وقت|في اي وقت|طوال|\bلا\b|\bلن\b|\bليس\b|\bلم\b"
)
# A claim that nothing at all is charged, as opposed to a claim about one named fee.
_NO_CHARGE_CLAIM = re.compile(
    r"\b(?:all|any|no)\s+(?:fees?|charges?|costs?|payments?)\b|\bavoids?\b.*\b(?:fees?|charges?|costs?)\b|\bfree of charge\b"
    r"|كل الرسوم|جميع الرسوم|أي رسوم|اي رسوم|بدون رسوم|دون رسوم|لا رسوم|تجنب.*(?:رسوم|الدفع)"
)

_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_STOP = {"that", "this", "with", "will", "have", "from", "they", "your", "when", "what", "which", "there", "their", "about", "would", "could"}


class _ModelClaim(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=MAX_CLAIM_CHARS)
    topic: str = "other"
    verdict: str
    evidence: str | None = None
    evidence_role: str | None = None
    explanation: ModelExplanation

    @field_validator("verdict")
    @classmethod
    def _verdict(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("MATCH", "CONTRADICTION", "UNKNOWN"):
            raise ValueError("invalid verdict")
        return v

    @field_validator("topic")
    @classmethod
    def _topic(cls, v: str) -> str:
        v = (v or "other").strip().lower()
        return v if v in (*TOPIC_KEYWORDS, "other") else "other"

    @field_validator("evidence_role")
    @classmethod
    def _role(cls, v: str | None) -> str | None:
        v = (v or "").strip().lower()
        return v if v in ("supports", "contradicts") else None


def is_relevant(topic: str, claim_text: str, quote: str) -> bool:
    q = normalize(quote)
    if topic == "price" and re.search(r"\d", q):
        return True
    if topic in TOPIC_KEYWORDS:
        return any(normalize(k) in q for k in TOPIC_KEYWORDS[topic])
    claim_words = {w for w in _WORD.findall(normalize(claim_text)) if w not in _STOP}
    quote_words = set(_WORD.findall(q))
    return len(claim_words & quote_words) >= 2


def _relevant_to_claim(raw: _ModelClaim, quote: str) -> bool:
    if is_relevant(raw.topic, raw.text, quote):
        return True
    # A stated amount can contradict "nothing is charged". It cannot prove or disprove a named fee.
    return raw.topic == "fees" and raw.verdict == "CONTRADICTION" and bool(_NO_CHARGE_CLAIM.search(normalize(raw.text))) and states_money(quote)


def _absolute_supported(claim_text: str, quote: str) -> bool:
    return not _ABSOLUTE_CLAIM.search(normalize(claim_text)) or bool(_PROMISE_IN_QUOTE.search(normalize(quote)))


def _numbers_supported(claim_text: str, quote: str) -> bool:
    quote_numbers = set(numbers_in(quote))
    return all(n in quote_numbers for n in numbers_in(claim_text))


def judge_claim(index: int, raw: _ModelClaim, terms: str) -> Claim:
    evidence: Evidence | None = None
    verified = False
    if raw.evidence:
        qc = verify_quote(raw.evidence, terms)
        if qc.verified:
            evidence = Evidence(quote=qc.quote, verified=True, start=qc.start, end=qc.end)
            verified = True

    reason = None
    if raw.verdict in ("MATCH", "CONTRADICTION"):
        expected_role = "supports" if raw.verdict == "MATCH" else "contradicts"
        if not verified:
            reason = "evidence_not_found"
        elif raw.evidence_role != expected_role:
            reason = "inconsistent_evidence_role"
        elif not _relevant_to_claim(raw, evidence.quote):
            reason = "evidence_not_relevant"
        elif raw.verdict == "MATCH" and not _numbers_supported(raw.text, evidence.quote):
            reason = "numbers_not_in_evidence"
        elif raw.verdict == "MATCH" and not _absolute_supported(raw.text, evidence.quote):
            reason = "absolute_claim_unsupported"

    verdict = "UNKNOWN" if reason else raw.verdict
    return Claim(
        id=f"claim-{index}",
        text=raw.text,
        topic=raw.topic,
        verdict=verdict,
        model_verdict=raw.verdict,
        downgraded=reason is not None,
        reason=reason,
        # A quote that failed relevance is not shown as this claim's evidence.
        evidence=None if reason == "evidence_not_relevant" else evidence,
        evidence_role=raw.evidence_role if verdict != "UNKNOWN" else None,
        explanation=DOWNGRADE_TEXT[reason] if reason else Explanation(en=raw.explanation.en, ar=raw.explanation.ar),
    )


def _omitted_amounts(expectation: str, claims: list[Claim]) -> int:
    covered = {n for c in claims for n in numbers_in(c.text)}
    return sum(n not in covered for n in set(numbers_in(expectation)))


def summarize(claims: list[Claim], dropped: int = 0, top_verdict: str = "MATCH", omitted_amounts: int = 0) -> ClaimsSummary:
    counts = {v: sum(c.verdict == v for c in claims) for v in ("MATCH", "CONTRADICTION", "UNKNOWN")}
    # MATCH is the reassuring headline, so it needs everything to agree: an unread claim, an
    # amount no claim checked, or a disagreeing overall verdict leaves the result unsettled.
    unsettled = counts["UNKNOWN"] or not claims or dropped or omitted_amounts or top_verdict != "MATCH"
    overall = "CONTRADICTION" if counts["CONTRADICTION"] else ("UNKNOWN" if unsettled else "MATCH")
    return ClaimsSummary(overall=overall, counts=counts, dropped=dropped, omitted_amounts=omitted_amounts)


def build_claims(
    raw_claims: list[Any],
    terms: str,
    expectation: str,
    fallback_verdict: str,
    fallback_evidence: Evidence | None,
    fallback_explanation: Explanation,
) -> tuple[list[Claim], ClaimsSummary]:
    claims: list[Claim] = []
    dropped = 0
    for item in raw_claims:
        if len(claims) >= MAX_CLAIMS:
            dropped += 1
            continue
        try:
            parsed = _ModelClaim.model_validate(item)
        except ValidationError:
            dropped += 1
            continue
        claims.append(judge_claim(len(claims) + 1, parsed, terms))

    if not claims:
        # Backward compatible: the already-verified overall verdict becomes a single claim.
        # An overall MATCH has passed no claim-level guard, so it is not shown as confirmed.
        unsupported = fallback_verdict == "MATCH"
        claims = [
            Claim(
                id="claim-1",
                text=expectation,
                topic="other",
                verdict="UNKNOWN" if unsupported else fallback_verdict,
                model_verdict=fallback_verdict,
                downgraded=unsupported,
                reason="no_claim_support" if unsupported else None,
                evidence=fallback_evidence if fallback_evidence and fallback_evidence.verified else None,
                explanation=DOWNGRADE_TEXT["no_claim_support"] if unsupported else fallback_explanation,
                from_overall=True,
            )
        ]
    return claims, summarize(claims, dropped, fallback_verdict, _omitted_amounts(expectation, claims))
