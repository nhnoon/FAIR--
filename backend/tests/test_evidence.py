import csv
from decimal import Decimal
from pathlib import Path

import pytest

from app.evidence import numbers_in, value_in_quote, verify_quote

TERMS_EN = "Free for 7 days. Then USD 9.99 per month, automatically renewed unless cancelled before the trial ends."
TERMS_AR = "الاشتراك 59 SAR شهريًا ويتجدد تلقائيًا. يجب تقديم طلب الإلغاء قبل موعد التجديد القادم بـ48 ساعة على الأقل."

DATASET = Path(__file__).resolve().parents[2] / "data" / "fair_bench_v1.csv"


def test_exact_quote_verified_with_offsets():
    quote = "Then USD 9.99 per month"
    r = verify_quote(quote, TERMS_EN)
    assert r.verified
    assert TERMS_EN[r.start:r.end] == quote


def test_fabricated_quote_rejected():
    r = verify_quote("Cancel anytime with a full refund.", TERMS_EN)
    assert not r.verified
    assert r.reason == "quote_not_found_in_source"


def test_paraphrase_rejected():
    r = verify_quote("Then USD 9.99 each month", TERMS_EN)
    assert not r.verified


def test_changed_number_rejected():
    assert not verify_quote("Then USD 8.99 per month", TERMS_EN).verified


@pytest.mark.parametrize("quote", [None, "", "   ", "Free"])
def test_missing_or_too_short_quote_rejected(quote):
    r = verify_quote(quote, TERMS_EN)
    assert not r.verified
    assert r.reason == "quote_missing_or_too_short"


def test_whitespace_and_case_differences_tolerated():
    r = verify_quote("then  usd 9.99\nper month", TERMS_EN)
    assert r.verified
    assert TERMS_EN[r.start:r.end] == "Then USD 9.99 per month"


def test_arabic_quote_verified():
    quote = "يجب تقديم طلب الإلغاء قبل موعد التجديد القادم بـ48 ساعة على الأقل."
    r = verify_quote(quote, TERMS_AR)
    assert r.verified
    assert TERMS_AR[r.start:r.end] == quote


def test_arabic_without_diacritics_and_with_arabic_indic_digits():
    # Model drops tanween and writes ٥٩ instead of 59: same words, so still verified.
    r = verify_quote("الاشتراك ٥٩ SAR شهريا ويتجدد تلقائيا", TERMS_AR)
    assert r.verified
    assert TERMS_AR[r.start:r.end] == "الاشتراك 59 SAR شهريًا ويتجدد تلقائيًا"


def test_arabic_fabricated_quote_rejected():
    assert not verify_quote("يمكن استرداد المبلغ بالكامل عند الإلغاء.", TERMS_AR).verified


def test_quote_from_other_document_rejected():
    assert not verify_quote("Then USD 9.99 per month", TERMS_AR).verified


def test_numbers_in_handles_formats():
    assert numbers_in("USD 1,299.50 then ٥٩ and 7") == [Decimal("1299.50"), Decimal("59"), Decimal("7")]
    assert value_in_quote(Decimal("9.99"), "USD 9.99 per month")
    assert value_in_quote(59, "بمبلغ ٥٩ SAR")
    assert not value_in_quote(Decimal("9.99"), "USD 19.99 per month")


def test_all_gold_evidence_quotes_in_dataset_verify():
    """The verifier must accept every human-annotated gold quote (EN, AR, mixed)."""
    with DATASET.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 60
    failures = [r["Case ID"] for r in rows
                if not verify_quote(r["Evidence quote"], r["Offer / Terms (verbatim)"]).verified]
    assert failures == []
