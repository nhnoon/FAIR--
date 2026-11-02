"""Monetary values from model output: strict parsing and checks against the quoted source.

The model may write an amount with its currency ("USD 9.99", "٥٩ ر.س"). Only unambiguous forms
parse; anything else is rejected, never guessed. A parsed amount then counts only if the quote
states it as money, in the same currency, as the kind of price it was extracted as, and for the
same billing period. Every failure excludes the value and names why; none guesses a correction.

The rules read the words around each number. They catch explicit conflicts, not meaning: a
sentence that describes a price without these words is accepted or rejected on what it does say.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Literal, NamedTuple

from .evidence import _NUMBER, normalize

PriceKind = Literal["recurring", "intro", "one_time"]

# "$" and "dollar" alone do not identify a currency (USD, CAD, AUD...), so they keep their own code.
DOLLAR = "$"
_ALIASES = {
    "USD": ("usd", "us$", "us dollars", "us dollar", "دولار أمريكي", "دولار امريكي"),
    DOLLAR: ("$", "dollars", "dollar", "دولار"),
    "SAR": ("sar", "ر.س", "﷼", "ريال"),
    "EUR": ("eur", "€", "euros", "euro", "يورو"),
    "GBP": ("gbp", "£"),
    "AED": ("aed", "د.إ", "درهم"),
}


def _alias_pattern(alias: str) -> str:
    text = re.escape(normalize(alias))
    if alias == "$":
        return rf"(?<![a-z]){text}"  # A$ and C$ are other currencies
    return rf"(?<![a-z]){text}(?![a-z])" if alias.isascii() and alias[0].isalpha() else text


_BY_ALIAS = {normalize(a): code for code, aliases in _ALIASES.items() for a in aliases}
_CURRENCY = "|".join(_alias_pattern(a) for a in sorted((a for v in _ALIASES.values() for a in v), key=len, reverse=True))
_AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

_PERIOD_NOUN = r"month|mo|year|yr|week|wk|شهر|سنة|عام|اسبوع|أسبوع"
_PERIOD_ADVERB = r"monthly|yearly|annually|annual|weekly|شهريا|سنويا|اسبوعيا|أسبوعيا"
_PER_PERIOD = rf"\s*(?:/\s*|\b(?:per|a|an|each|every)\s+|كل\s+|في\s+(?:ال)?)(?:{_PERIOD_NOUN})\b|\s*(?:{_PERIOD_ADVERB})\b"
_PERIOD_WORD = re.compile(r"(?P<monthly>month|\bmo\b|شهر)|(?P<yearly>year|annual|\byr\b|سنو|سنة|كل عام)|(?P<weekly>week|\bwk\b|اسبوع|أسبوع)")

_MONEY = re.compile(rf"^(?:(?P<before>{_CURRENCY})\s*)?(?P<amount>{_AMOUNT})(?:\s*(?P<after>{_CURRENCY}))?(?P<rest>.*)$")
_PER_PERIOD_ONLY = re.compile(rf"^(?:{_PER_PERIOD})$")
_PER_PERIOD_AFTER = re.compile(rf"^\s*(?:{_CURRENCY})?(?:{_PER_PERIOD})")
_CURRENCY_AT_END = re.compile(rf"(?:{_CURRENCY})\s*$")
_CURRENCY_AT_START = re.compile(rf"^\s*(?:{_CURRENCY})")
_CURRENCY_ANYWHERE = re.compile(_CURRENCY)

_COUNTED_AFTER = re.compile(r"^[\s-]*(?:%|hours?\b|hrs?\b|days?\b|weeks?\b|months?\b|years?\b|minutes?\b|ساع|يوم|ايام|أيام|اسبوع|أسبوع|شهر(?!ي)|سنة|سنوات)")
_COUNTED_BEFORE = re.compile(r"(?:\b(?:day|week|month|year)|يوم|اسبوع|أسبوع|شهر|سنة)\s*$")
_DURATION = re.compile(r"\d+(?:\.\d+)?[\s-]*(?:hours?|days?|weeks?|months?|years?|ساعة|ساعات|يوم|أيام|ايام|أسابيع|اسابيع|شهر|أشهر|اشهر|سنة|سنوات)")
_CLAUSE_BREAK = re.compile(r",|;|،|\bthen\b|\bplus\b|\band\b|ثم")
_SENTENCE_END = re.compile(r"[.!?؟](?:\s|$)")

_ONE_TIME = re.compile(
    r"one[\s-]?time|\bonce\b|\bsingle payment\b|\blifetime\b|set[\s-]?up|activation|sign[\s-]?up fee|registration|joining fee|enrol+ment fee|installation"
    r"|لمرة واحدة|لمره واحده|دفعة واحدة|رسوم (?:تأسيس|تاسيس|إعداد|اعداد|تفعيل|تسجيل)"
)
_PAY_NOW = re.compile(r"\btoday\b|\bcheckout\b|\bup[\s-]?front\b|\bnow\b|اليوم|عند الدفع")
_UNSUPPORTED_PERIOD = re.compile(
    r"quarter|bi[\s-]?weekly|bi[\s-]?monthly|fortnight|semi[\s-]?annual|half[\s-]year|\bdaily\b|(?:/|\bper |\ba )\s*day\b"
    r"|\bevery\s+(?:\d|two\b|three\b|four\b|six\b|other\b)|ربع سنوي|فصلي|يوميا|كل\s+(?:\d|شهرين|سنتين|ثلاث|أربع|اربع|ست)"
)


_PERIODIC = ("monthly", "yearly", "weekly")


class Money(NamedTuple):
    amount: Decimal
    currency: str | None
    period: str | None = None  # stated with the amount, as in "USD 10/month"


def parse_money(value: Any) -> Money:
    """Parse an amount, optionally with one supported currency and one period. Raises ValueError otherwise."""
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError("not a non-negative amount")
        return Money(amount, None)
    if not isinstance(value, str):
        raise ValueError("not an amount")
    match = _MONEY.match(normalize(value))
    if not match or (match["rest"] and not _PER_PERIOD_ONLY.match(match["rest"])):
        raise ValueError("not an unambiguous amount in a supported currency")
    codes = {_BY_ALIAS[c] for c in (match["before"], match["after"]) if c}
    if len(codes) > 1:
        raise ValueError("two different currencies")
    return Money(Decimal(match["amount"].replace(",", "")), codes.pop() if codes else None, _last_period(match["rest"]))


def currency_code(text: str | None) -> str | None:
    """The one supported currency named in `text`, or None if there is none or several."""
    codes = {_BY_ALIAS[m] for m in _CURRENCY_ANYWHERE.findall(normalize(text or ""))}
    return codes.pop() if len(codes) == 1 else None


_MONEY_IN_TEXT = re.compile(rf"(?:{_CURRENCY})\s*(?:{_AMOUNT})|(?:{_AMOUNT})\s*(?:{_CURRENCY})")


def states_money(text: str) -> bool:
    """True if the text gives an amount next to a supported currency."""
    return bool(_MONEY_IN_TEXT.search(normalize(text)))


def _last_period(text: str) -> str | None:
    found = list(_PERIOD_WORD.finditer(text))
    return found[-1].lastgroup if found else None


def _satisfies(claimed: str, source: str | None) -> bool:
    """A value may say "$" where the source says USD. It may not say USD where the source only says "$"."""
    return claimed == source or (claimed == DOLLAR and source == "USD")


def _sentence_around(text: str, position: int) -> str:
    start = 0
    for end in _SENTENCE_END.finditer(text):
        if end.end() > position:
            return text[start : end.end()]
        start = end.end()
    return text[start:]


def _words_before(text: str, number_start: int) -> str:
    """The clause leading up to the number: other amounts and durations do not describe it."""
    sentence_start = text.rfind(_sentence_around(text, number_start), 0, number_start + 1)
    lead = _DURATION.sub(" ", text[max(sentence_start, 0) : number_start])
    numbers = list(_NUMBER.finditer(lead))
    if numbers:
        lead = lead[numbers[-1].end() :]
    return _CLAUSE_BREAK.split(lead)[-1]


def _words_after(after: str) -> str:
    number = _NUMBER.search(after)
    return _CLAUSE_BREAK.split(_SENTENCE_END.split(after[: number.start()] if number else after)[0])[0]


def money_problem(money: Money, quote: str, kind: PriceKind, stated_currency: str | None = None, billing: str | None = None) -> str | None:
    """Why `quote` does not support this price, or None if it does. Returns an evidence reason code."""
    if money.currency and stated_currency and not _satisfies(money.currency, currency_code(stated_currency)):
        return "currency_mismatch"
    q = normalize(quote)
    found = [m for m in _NUMBER.finditer(q) if Decimal(m[0].replace(",", "")) == money.amount]
    if not found:
        return "value_not_in_quote"

    problem = "not_a_price"
    for number in found:
        before, after = q[: number.start()], q[number.end() :]
        if _COUNTED_AFTER.match(after) or _COUNTED_BEFORE.search(before):
            continue  # a duration or a percentage, not an amount of money
        nearby = _CURRENCY_AT_END.search(before) or _CURRENCY_AT_START.match(after)
        if money.currency:
            sources = {_BY_ALIAS[nearby[0].strip()]} if nearby else {_BY_ALIAS[c] for c in _CURRENCY_ANYWHERE.findall(q)}
            if not any(_satisfies(money.currency, s) for s in sources):
                problem = "currency_mismatch"
                continue
        reason = _price_type_problem(money, q, number.start(), after, kind, billing)
        if reason:
            problem = reason
            continue
        return None
    return problem


def _price_type_problem(money: Money, q: str, start: int, after: str, kind: PriceKind, billing: str | None) -> str | None:
    lead, trail = _words_before(q, start), _words_after(after)
    suffix = _PER_PERIOD_AFTER.match(after)
    marked_one_time = bool(_ONE_TIME.search(lead) or _ONE_TIME.search(trail))
    if kind == "one_time":
        if suffix or (not marked_one_time and _last_period(lead)):
            return "recurring_not_one_time"
        return None
    if not suffix:
        if marked_one_time:
            return "one_time_not_recurring"
        # With no billing period this stays a plain price; it only must not enter a recurring calculation.
        if kind == "recurring" and billing in _PERIODIC and (_PAY_NOW.search(lead) or _PAY_NOW.search(trail)):
            return "price_type_not_stated"
        if _UNSUPPORTED_PERIOD.search(_sentence_around(q, start)):
            return "billing_period_unsupported"

    source = _last_period(suffix[0]) if suffix else _last_period(lead)
    periodic = billing if billing in _PERIODIC else None
    if billing == "one_time" and (suffix or money.period):
        return "billing_period_mismatch"
    stated = {p for p in (source, money.period, periodic) if p}
    return "billing_period_mismatch" if len(stated) > 1 else None


def billing_problem(billing: str, quote: str) -> str | None:
    """A billing period counts only if the quote names it. Stated durations ("12 months") do not."""
    raw = normalize(quote)
    text = _DURATION.sub(" ", raw)
    if billing == "one_time":
        return None if _ONE_TIME.search(text) else "billing_period_not_in_quote"
    if _UNSUPPORTED_PERIOD.search(raw) and not re.search(_PER_PERIOD, text):
        return "billing_period_unsupported"
    return None if any(m.lastgroup == billing for m in _PERIOD_WORD.finditer(text)) else "billing_period_not_in_quote"
