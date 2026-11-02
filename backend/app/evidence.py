"""Evidence verification: a quote counts as evidence only if it exists in the source.

Matching is tolerant of formatting noise only (Unicode width forms, letter case,
whitespace runs, Arabic diacritics/tatweel, Arabic-Indic digits, curly quotes).
It never tolerates different words. Matches are mapped back to character offsets
in the original text so the UI can highlight exactly what was quoted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MIN_QUOTE_CHARS = 5

_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬",
    "01234567890123456789.,",
)
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"'})
# Arabic harakat, superscript alef, tatweel; also bidi/zero-width marks.
_DROP = re.compile(r"[ً-ٰٟـ​-‏‪-‮⁦-⁩﻿]")
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Return normalized text plus, for each output char, its index in `text`."""
    out: list[str] = []
    index_map: list[int] = []
    prev_space = True  # trims leading whitespace
    for i, ch in enumerate(text):
        if _DROP.match(ch):
            continue
        piece = unicodedata.normalize("NFKC", ch).translate(_DIGITS).translate(_QUOTES).casefold()
        for c in piece:
            if c.isspace():
                if prev_space:
                    continue
                c = " "
                prev_space = True
            else:
                prev_space = False
            out.append(c)
            index_map.append(i)
    if out and out[-1] == " ":
        out.pop()
        index_map.pop()
    return "".join(out), index_map


def normalize(text: str) -> str:
    return _normalize_with_map(text)[0]


@dataclass(frozen=True)
class QuoteCheck:
    quote: str
    verified: bool
    start: int | None = None  # offsets into the original source text
    end: int | None = None
    reason: str | None = None


def verify_quote(quote: str | None, source: str) -> QuoteCheck:
    quote = quote or ""
    norm_quote = normalize(quote)
    if len(norm_quote) < MIN_QUOTE_CHARS:
        return QuoteCheck(quote, False, reason="quote_missing_or_too_short")
    norm_source, index_map = _normalize_with_map(source)
    pos = norm_source.find(norm_quote)
    if pos < 0:
        return QuoteCheck(quote, False, reason="quote_not_found_in_source")
    start = index_map[pos]
    end = index_map[pos + len(norm_quote) - 1] + 1
    return QuoteCheck(quote, True, start=start, end=end)


def numbers_in(text: str) -> list[Decimal]:
    found = []
    for raw in _NUMBER.findall(normalize_digits(text)):
        try:
            found.append(Decimal(raw.replace(",", "")))
        except InvalidOperation:  # pragma: no cover - regex only yields numerics
            continue
    return found


def value_in_quote(value: Decimal | int, quote: str) -> bool:
    """True if the numeric value literally appears in the quote (e.g. 9.99, ٥٩)."""
    target = Decimal(value)
    return any(n == target for n in numbers_in(quote))
