"""FAIR versus direct Muse Spark: frozen baseline prompt and scoring for the challenge set.

Offline only. This module makes no model calls and has no run command; a live comparison needs
separate authorization. The protocol is in docs/COMPARISON_PROTOCOL.md. Gold annotations are read
for scoring only, so they cannot reach a model through this code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.evidence import verify_quote
from app.meta_client import parse_json_object
from app.money import parse_money

CHALLENGE_DIR = Path(__file__).resolve().parent / "challenge"
INPUTS_PATH = CHALLENGE_DIR / "challenge_v1_inputs.json"
GOLD_PATH = CHALLENGE_DIR / "challenge_v1_gold_DRAFT.json"
MANIFEST_PATH = CHALLENGE_DIR / "challenge_v1_manifest.json"
VERDICTS = ("MATCH", "CONTRADICTION", "UNKNOWN")

# Frozen. Neutral on purpose: no FAIR rules about promises, silence or injection. It asks for the same
# fields the scorer reads, so both systems are judged on equivalent output.
BASELINE_PROMPT = """You will receive the terms of a subscription offer and something a person believes about it.
Say whether the terms support the belief, contradict it, or do not settle it. Quote the terms that decide your answer.
Report the prices and billing period, and the total cost over the first 12 months if it can be worked out.

Return only one JSON object:
{
  "verdict": "MATCH" | "CONTRADICTION" | "UNKNOWN",
  "quotes": ["..."],
  "explanation": "...",
  "recurring_price": "..." | null,
  "billing_period": "monthly" | "yearly" | "weekly" | "one_time" | "unknown",
  "intro_price": "..." | null,
  "one_time_fees": ["..."],
  "total_12_months": "..." | null
}"""


def baseline_input(terms: str, expectation: str) -> str:
    return f"TERMS:\n{terms}\n\nBELIEF:\n{expectation}"


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def prompt_sha256() -> str:
    return hashlib.sha256(BASELINE_PROMPT.encode("utf-8")).hexdigest()


def load_inputs(path: Path = INPUTS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def load_gold(path: Path = GOLD_PATH) -> dict[str, dict]:
    return {g["case_id"]: g for g in json.loads(path.read_text(encoding="utf-8"))["annotations"]}


@dataclass
class Normalized:
    """One system's answer to one case, in the shape the scorer reads."""

    status: str = "ok"  # "ok" | "error"
    verdict: str | None = None
    quotes: list[str] = field(default_factory=list)
    recurring_price: Any = None
    billing_period: str | None = None
    intro_price: Any = None
    one_time_fees: list[Any] = field(default_factory=list)
    total_12_months: Any = None
    latency_ms: int | None = None
    total_tokens: int | None = None
    error: str | None = None


def normalize_fair(response: dict) -> Normalized:
    """System A: the user-visible result of FAIR's full pipeline (an AnalyzeResponse as JSON)."""
    terms, keep = response["extracted_terms"], (response.get("decision") or {}).get("continue_path") or {}
    claims_summary = response.get("claims_summary") or {}
    decisive = [c["evidence"]["quote"] for c in response.get("claims", []) if c["verdict"] != "UNKNOWN" and (c.get("evidence") or {}).get("verified")]
    total = next((h.get("total") for h in keep.get("horizons", []) if h["months"] == 12 and h["status"] != "unavailable"), None)
    return Normalized(
        verdict=claims_summary.get("overall") or response["verdict"],
        quotes=decisive,
        recurring_price=terms.get("recurring_price"),
        billing_period=terms.get("billing_period"),
        intro_price=terms.get("intro_price"),
        one_time_fees=[f["amount"] for f in terms.get("one_time_fees", [])],
        total_12_months=total,
    )


def normalize_direct(text: str) -> Normalized:
    """System B: direct model text, exactly as received. Unusable output is an error, never repaired."""
    try:
        data = parse_json_object(text)
        verdict = str(data["verdict"]).strip().upper()
        if verdict not in VERDICTS:
            raise ValueError("invalid verdict")
    except Exception as exc:  # any unusable output counts against the system that produced it
        return Normalized(status="error", error=type(exc).__name__)
    quotes = data.get("quotes")
    fees = data.get("one_time_fees")
    return Normalized(
        verdict=verdict,
        quotes=[q for q in quotes if isinstance(q, str)] if isinstance(quotes, list) else [],
        recurring_price=data.get("recurring_price"),
        billing_period=data.get("billing_period"),
        intro_price=data.get("intro_price"),
        one_time_fees=fees if isinstance(fees, list) else [],
        total_12_months=data.get("total_12_months"),
    )


def _amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return parse_money(value).amount
    except (ValueError, InvalidOperation, ArithmeticError):
        return None


def _same_amount(found: Any, gold: Any) -> bool:
    if gold is None:
        return found is None
    return _amount(found) == Decimal(str(gold))


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def score_case(case: dict, gold: dict, answer: Normalized) -> dict[str, Any]:
    """Deterministic checks. Whether a quote logically supports the verdict is judged by reviewers."""
    terms = case["terms"]
    verified = [verify_quote(q, terms) for q in answer.quotes]
    verbatim = [q for q in verified if q.verified]
    accepted = [verify_quote(q, terms) for q in gold["accepted_evidence"]]
    decisive = answer.verdict in ("MATCH", "CONTRADICTION")
    cost, money = gold["cost"], [_amount(f) for f in answer.one_time_fees]
    return {
        "case_id": case["case_id"],
        "language": case["language"],
        "status": answer.status,
        "gold": gold["verdict"],
        "verdict": answer.verdict,
        "correct": answer.verdict == gold["verdict"],
        "false_reassurance": answer.verdict == "MATCH" and gold["verdict"] != "MATCH",
        "false_contradiction": answer.verdict == "CONTRADICTION" and gold["verdict"] != "CONTRADICTION",
        "false_unknown": answer.verdict == "UNKNOWN" and gold["verdict"] != "UNKNOWN",
        "decisive": decisive,
        "decisive_without_verbatim_quote": decisive and not verbatim,
        "invented_quotes": len(verified) - len(verbatim),
        "quotes_total": len(verified),
        "quote_hits_accepted": any(_overlaps((q.start, q.end), (g.start, g.end)) for q in verbatim for g in accepted) if accepted else None,
        "recurring_price_correct": _same_amount(answer.recurring_price, cost["recurring_price"]),
        "billing_correct": answer.billing_period == cost["billing_period"],
        "intro_price_correct": _same_amount(answer.intro_price, cost["intro_price"]),
        "fees_correct": sorted(m for m in money if m is not None) == sorted(Decimal(str(f)) for f in cost["one_time_fees"]) and None not in money,
        "total_correct": _same_amount(answer.total_12_months, cost["total_12_months"]) if answer.status == "ok" else False,
        "total_unsupported": cost["total_12_months"] is None and answer.total_12_months is not None,
        "total_withheld_wrongly": cost["total_12_months"] is not None and answer.total_12_months is None,
        "latency_ms": answer.latency_ms,
        "total_tokens": answer.total_tokens,
    }


def _rate(hits: int, total: int) -> dict[str, Any]:
    return {"hits": hits, "of": total, "rate": hits / total if total else None}


def summarize(scores: list[dict]) -> dict[str, Any]:
    """Every metric keeps its denominator. Errors stay in the denominators and count as wrong."""
    n = len(scores)
    count = lambda key: sum(bool(s[key]) for s in scores)  # noqa: E731
    not_match = sum(s["gold"] != "MATCH" for s in scores)
    decisive = sum(s["decisive"] for s in scores)
    hits = [s["quote_hits_accepted"] for s in scores if s["decisive"] and s["quote_hits_accepted"] is not None]
    withheld_gold = sum(not s["total_correct"] and s["total_unsupported"] for s in scores)
    return {
        "cases": n,
        "errors": sum(s["status"] != "ok" for s in scores),
        "verdict_accuracy": _rate(count("correct"), n),
        "false_reassurance": _rate(count("false_reassurance"), not_match),
        "false_contradiction": count("false_contradiction"),
        "false_unknown": count("false_unknown"),
        "decisive_without_verbatim_quote": _rate(count("decisive_without_verbatim_quote"), decisive),
        "invented_quotes": _rate(sum(s["invented_quotes"] for s in scores), sum(s["quotes_total"] for s in scores)),
        "decisive_quote_hits_accepted_evidence": _rate(sum(bool(h) for h in hits), len(hits)),
        "recurring_price": _rate(count("recurring_price_correct"), n),
        "billing_period": _rate(count("billing_correct"), n),
        "intro_price": _rate(count("intro_price_correct"), n),
        "one_time_fees": _rate(count("fees_correct"), n),
        "total_12_months": _rate(count("total_correct"), n),
        "unsupported_totals": withheld_gold,
        "totals_withheld_wrongly": count("total_withheld_wrongly"),
        "median_latency_ms": _median([s["latency_ms"] for s in scores]),
        "total_tokens": sum(s["total_tokens"] or 0 for s in scores),
    }


def _median(values: list[int | None]) -> int | None:
    known = sorted(v for v in values if v is not None)
    return known[len(known) // 2] if known else None
