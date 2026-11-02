"""FAIR-Bench v1: loading, dataset audit, metrics, and the run loop.

Principles
- Splits are never mixed. Test is for final reporting only (the CLI requires an
  explicit flag); prompt iteration uses Development.
- Metrics are computed only from real predictions. Failed calls are recorded as
  errors, excluded from model-quality metrics, and counted as wrong in the
  "strict" accuracy. A run with zero successful predictions writes nothing.
- Classification, evidence support and extraction/cost fields are scored separately.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable

from app.evidence import normalize, numbers_in, verify_quote
from app.meta_client import ModelError, ModelTruncatedError
from app.schemas import AnalyzeResponse

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "fair_bench_v1.csv"
DATASET_SHA256 = "b496051118b82f6e3c05d195fa4a29ed2024cfdfbc0044dca7a3950e9fe69d55"
# Scoring-only corrections. Read here and nowhere else, so it cannot reach the model's input.
OVERLAY_PATH = DATASET_PATH.with_name("fair_bench_v1_overlay.json")
LABELS = ("MATCH", "CONTRADICTION", "UNKNOWN")
SPLITS = {"development": "Development", "validation": "Validation", "test": "Test"}

# Documented in data/README.md. Labels and quotes are NOT modified.
ANNOTATION_FLAGS = {
    "FAIR-014": "Gold evidence quotes the setup-fee sentence; the 'renewal not stated' sentence is more relevant.",
    "FAIR-029": "Gold evidence quotes the setup-fee sentence; the 'renewal not stated' sentence is more relevant.",
    "FAIR-044": "Gold evidence quotes the setup-fee sentence; the 'renewal not stated' sentence is more relevant.",
    "FAIR-059": "Gold evidence quotes the setup-fee sentence; the 'renewal not stated' sentence is more relevant.",
}
# A model/auth/config failure affects every case: stop instead of burning calls.
FATAL_ERROR_CODES = {"model_not_configured", "live_calls_disabled", "model_auth_failed", "model_not_found", "request_limit_reached"}
MAX_CONSECUTIVE_ERRORS = 5

LIMITATIONS = [
    "All 60 cases are synthetic and generated from 5 scenario templates; review status is 'Author draft — review pending'.",
    "Test cases closely resemble Development cases (see template overlap). Scores likely overstate performance on real-world terms.",
    "Development is English-only; Test has no pure-English cases. Per-language results have small n (5–20).",
    "FAIR-014/029/044/059: gold evidence quotes a less relevant sentence; evidence-overlap is also reported without them.",
    "There is no gold introductory-price or billing-period column, so multi-month cost projections are not gold-scored; "
    "only cost-relevant extracted fields are compared.",
]


# ------------------------------------------------------------------ dataset


@dataclass(frozen=True)
class Case:
    case_id: str
    split: str
    language: str
    scenario: str
    terms: str
    expectation: str
    gold_label: str
    gold_evidence: str
    monthly_price: str
    currency: str
    trial_days: str
    auto_renewal: str
    additional_fee: str


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path = DATASET_PATH) -> list[Case]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    cases = [
        Case(
            case_id=r["Case ID"].strip(),
            split=r["Split"].strip(),
            language=r["Language"].strip(),
            scenario=r["Scenario"].strip(),
            # The API strips whitespace; offsets are relative to the stripped text.
            terms=r["Offer / Terms (verbatim)"].strip(),
            expectation=r["User expectation"].strip(),
            gold_label=r["Gold label"].strip(),
            gold_evidence=r["Evidence quote"].strip(),
            monthly_price=r["Monthly price"].strip(),
            currency=r["Currency"].strip(),
            trial_days=r["Trial days"].strip(),
            auto_renewal=r["Auto renewal"].strip(),
            additional_fee=r["Additional fee"].strip(),
        )
        for r in rows
    ]
    bad = [c.case_id for c in cases if c.gold_label not in LABELS]
    if bad:
        raise ValueError(f"Unknown gold labels in {bad}")
    return cases


def select_split(cases: Iterable[Case], split: str) -> list[Case]:
    name = SPLITS[split]
    return [c for c in cases if c.split == name]


def select_cases(cases: list[Case], ids: str) -> list[Case]:
    """Keep only the comma-separated case IDs. An ID that is not in `cases` is an error."""
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    if len(wanted) != len(set(wanted)):
        raise ValueError("duplicate case IDs")
    unknown = sorted(set(wanted) - {c.case_id for c in cases})
    if unknown:
        raise ValueError(", ".join(unknown))
    return [c for c in cases if c.case_id in wanted]


# ------------------------------------------------------------------ overlay


_OVERLAY_ENTRY_KEYS = {"case_id", "rationales", "evidence", "prices", "exclude_extraction"}
_OVERLAY_PRICE_KEYS = {"intro_price"}  # recurring and one-time prices stay in the base file
_OVERLAY_EXCLUDABLE = {"recurring_price"}


def load_overlay(cases: list[Case], path: Path = OVERLAY_PATH) -> dict[str, Any]:
    """Load and validate the annotation overlay. Any doubt is an error: scores must be reproducible."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["base_sha256"] != DATASET_SHA256:
        raise ValueError("Overlay was written for a different dataset.")
    by_case = {c.case_id: c for c in cases}
    entries: dict[str, dict] = {}
    for entry in data["corrections"]:
        cid = entry["case_id"]
        extra = set(entry) - _OVERLAY_ENTRY_KEYS
        if extra:  # in particular, an overlay can never carry a gold label
            raise ValueError(f"{cid}: unsupported overlay keys {sorted(extra)}")
        if cid not in by_case or cid in entries:
            raise ValueError(f"{cid}: unknown or duplicate case")
        if not entry["rationales"] or set(entry["rationales"]) - set(data["rationales"]):
            raise ValueError(f"{cid}: every correction needs a documented rationale")
        terms = by_case[cid].terms
        evidence = entry.get("evidence")
        if evidence:
            if evidence["mode"] not in ("all_parts", "any_of"):
                raise ValueError(f"{cid}: unknown evidence mode")
            if not evidence["passages"] or not all(verify_quote(q, terms).verified for q in evidence["passages"]):
                raise ValueError(f"{cid}: overlay passage is not verbatim in the terms")
        prices = entry.get("prices", {})
        if set(prices) - _OVERLAY_PRICE_KEYS or not all(_dec(v) in numbers_in(terms) for v in prices.values()):
            raise ValueError(f"{cid}: overlay price is unsupported or not in the terms")
        if set(entry.get("exclude_extraction", [])) - _OVERLAY_EXCLUDABLE:
            raise ValueError(f"{cid}: this field cannot be excluded")
        entries[cid] = entry
    return {"version": data["overlay_version"], "sha256": file_sha256(path), "entries": entries}


# -------------------------------------------------------------------- audit


def _template(text: str) -> str:
    return re.sub(r"\d+(?:[.,]\d+)?", "#", normalize(text))


def audit_dataset(cases: list[Case]) -> dict[str, Any]:
    """Measured facts about the benchmark itself (no model involved)."""
    by_split: dict[str, list[Case]] = defaultdict(list)
    for c in cases:
        by_split[c.split].append(c)

    def templates(cs, with_expectation=False):
        return {(_template(c.terms), _template(c.expectation)) if with_expectation else _template(c.terms) for c in cs}

    dev, val, test = by_split["Development"], by_split["Validation"], by_split["Test"]
    dev_val_terms = templates(dev + val)
    dev_val_pairs = templates(dev + val, with_expectation=True)
    test_terms_seen = sum(_template(c.terms) in dev_val_terms for c in test)
    test_pairs_seen = sum((_template(c.terms), _template(c.expectation)) in dev_val_pairs for c in test)
    val_pairs_seen = sum((_template(c.terms), _template(c.expectation)) in templates(dev, True) for c in val)

    return {
        "n_cases": len(cases),
        "split_sizes": {s: len(v) for s, v in by_split.items()},
        "split_x_language": {s: dict(Counter(c.language for c in v)) for s, v in by_split.items()},
        "split_x_label": {s: dict(Counter(c.gold_label for c in v)) for s, v in by_split.items()},
        "distinct_terms_templates": len(templates(cases)),
        "distinct_terms_expectation_templates": len(templates(cases, True)),
        "test_terms_template_seen_in_dev_or_val": f"{test_terms_seen}/{len(test)}",
        "test_terms_and_expectation_template_seen_in_dev_or_val": f"{test_pairs_seen}/{len(test)}",
        "val_terms_and_expectation_template_seen_in_dev": f"{val_pairs_seen}/{len(val)}",
        "gold_evidence_verbatim": f"{sum(verify_quote(c.gold_evidence, c.terms).verified for c in cases)}/{len(cases)}",
        "annotation_flags": ANNOTATION_FLAGS,
        "note": "Templates replace every number with '#' after normalisation; equal templates differ only in amounts.",
    }


# ------------------------------------------------------------------ results


@dataclass
class CaseResult:
    case_id: str
    split: str
    language: str
    scenario: str
    gold_label: str
    status: str  # "ok" | "error"
    error_code: str | None = None
    predicted: str | None = None  # top-level verdict
    displayed_verdict: str | None = None  # what the UI headline shows: claims_summary.overall
    claims: list | None = None
    model_verdict: str | None = None
    downgraded: bool | None = None
    verdict_evidence: dict | None = None
    extracted: dict | None = None
    facts_verified: int = 0
    facts_rejected: int = 0
    latency_ms: int = 0
    error_message: str | None = None
    truncated: bool = False
    tokens: dict | None = None
    explanation: dict | None = None
    dropped_claims: int = 0
    response_status: str | None = None
    incomplete_reason: str | None = None
    raw_output: str | None = None  # the model's text exactly as received, before any parsing
    started_at: str | None = None
    rejected_facts: list | None = None
    warnings: list | None = None
    cost: dict | None = None
    decision: dict | None = None


def to_result(case: Case, response: AnalyzeResponse, latency_ms: int) -> CaseResult:
    data = response.model_dump(mode="json")
    return CaseResult(
        case_id=case.case_id,
        split=case.split,
        language=case.language,
        scenario=case.scenario,
        gold_label=case.gold_label,
        status="ok",
        predicted=data["verdict"],
        displayed_verdict=(data.get("claims_summary") or {}).get("overall") or data["verdict"],
        claims=data.get("claims", []),  # full records with quotes: reviewing them must not need a paid re-run
        explanation=data["explanation"],
        dropped_claims=(data.get("claims_summary") or {}).get("dropped", 0),
        rejected_facts=data["rejected_facts"],
        warnings=data["warnings"],
        cost=data["cost"],
        decision=data.get("decision"),
        model_verdict=data["model_verdict"],
        downgraded=data["verdict_downgraded"],
        verdict_evidence=data["verdict_evidence"],
        extracted=data["extracted_terms"],
        facts_verified=len(data["facts"]) + sum(1 for f in data["extracted_terms"]["one_time_fees"]),
        facts_rejected=len(data["rejected_facts"]),
        latency_ms=latency_ms,
    )


def run_cases(
    cases: list[Case],
    predict: Callable[[Case], AnalyzeResponse],
    on_progress: Callable[[CaseResult], None] | None = None,
    get_usage: Callable[[], dict | None] | None = None,
    get_call: Callable[[], dict | None] | None = None,
    stop_check: Callable[[CaseResult], str | None] | None = None,
) -> tuple[list[CaseResult], str | None]:
    """Run predict() over cases. Returns (results, abort_reason or None).

    A crash on one case is recorded as an error, so it cannot lose the calls already paid for.
    stop_check may end the run after any result by returning a reason.
    """
    results: list[CaseResult] = []
    consecutive = 0
    usage = lambda: dict(get_usage() or {}) or None if get_usage else None  # noqa: E731

    def record_call(r: CaseResult) -> None:
        call = (get_call() if get_call else None) or {}
        r.response_status, r.incomplete_reason, r.raw_output = call.get("status"), call.get("incomplete_reason"), call.get("raw_output")

    for case in cases:
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        started = time.perf_counter()
        try:
            response = predict(case)
        except Exception as exc:
            model_error = isinstance(exc, ModelError)
            r = CaseResult(
                case.case_id, case.split, case.language, case.scenario, case.gold_label, "error",
                exc.code if model_error else "pipeline_error",
                error_message=exc.message if model_error else type(exc).__name__,
                truncated=isinstance(exc, ModelTruncatedError),
                tokens=usage(),
                latency_ms=int((time.perf_counter() - started) * 1000),
                started_at=started_at,
            )
            record_call(r)
            results.append(r)
            if on_progress:
                on_progress(r)
            reason = stop_check(r) if stop_check else None
            if reason:
                return results, reason
            consecutive += 1
            if model_error and exc.code in FATAL_ERROR_CODES:
                return results, f"fatal error '{exc.code}': {exc.message}"
            if consecutive >= MAX_CONSECUTIVE_ERRORS:
                return results, f"{consecutive} consecutive errors (last: {r.error_code})"
            continue
        consecutive = 0
        r = to_result(case, response, int((time.perf_counter() - started) * 1000))
        r.tokens = usage()
        r.started_at = started_at
        record_call(r)
        results.append(r)
        if on_progress:
            on_progress(r)
        reason = stop_check(r) if stop_check else None
        if reason:
            return results, reason
    return results, None


# ------------------------------------------------------------------ metrics


def classification_metrics(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """pairs: (gold, predicted). Macro-F1 over the 3 labels; 0/0 counts as 0."""
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    confusion = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p in pairs:
        confusion[g][p] += 1
    per_label = {}
    for lab in LABELS:
        tp = confusion[lab][lab]
        fp = sum(confusion[g][lab] for g in LABELS if g != lab)
        fn = sum(confusion[lab][p] for p in LABELS if p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_label[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return {
        "n": n,
        "accuracy": sum(g == p for g, p in pairs) / n,
        "macro_f1": sum(v["f1"] for v in per_label.values()) / len(LABELS),
        "per_label": per_label,
        "confusion": confusion,
    }


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _gold_renewal(v: str) -> str:
    return {"yes": "yes", "no": "no"}.get(v.strip().lower(), "not_stated")


def extraction_checks(case: Case, extracted: dict, annotation: dict | None = None) -> dict[str, bool]:
    """Cost-relevant field agreement with gold annotations (independent of the verdict).

    With an overlay annotation, introductory prices are scored and excluded fields are dropped.
    """
    fees = sum((_dec(f["amount"]) or Decimal(0) for f in extracted.get("one_time_fees", [])), Decimal(0))
    checks = {
        "recurring_price": _dec(case.monthly_price) == _dec(extracted.get("recurring_price")),
        # Gold 0 / blank = no trial stated; predicted null = not stated. Treated as equal.
        "trial_days": (_dec(case.trial_days) or 0) == (_dec(extracted.get("trial_days")) or 0),
        "auto_renewal": _gold_renewal(case.auto_renewal) == extracted.get("auto_renewal"),
        "one_time_fee_total": (_dec(case.additional_fee) or Decimal(0)) == fees,
        "currency": (case.currency or "").upper() == (extracted.get("currency") or "").upper(),
    }
    if annotation:
        for name in annotation.get("exclude_extraction", []):
            del checks[name]
        if "intro_price" in annotation.get("prices", {}):
            checks["intro_price"] = _dec(annotation["prices"]["intro_price"]) == _dec(extracted.get("intro_price"))
    return checks


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _quoted_spans(r: CaseResult) -> list[tuple[int, int]]:
    """Verified quotes the result rests on: the overall quote plus those of decisive claims."""
    quotes = [r.verdict_evidence] + [c.get("evidence") for c in (r.claims or []) if c.get("verdict") != "UNKNOWN"]
    return [(q["start"], q["end"]) for q in quotes if q and q.get("verified")]


def overlay_metrics(ok: list[CaseResult], cases: list[Case], overlay: dict[str, Any]) -> dict[str, Any]:
    """The same results scored with the overlay. The base metrics stay as they were."""
    by_id = {c.case_id: c for c in cases}
    rate = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    field_hits: dict[str, list[bool]] = defaultdict(list)
    all_ok, overlap, overlap_decisive, complete = [], [], [], []
    for r in ok:
        case = by_id[r.case_id]
        annotation = overlay["entries"].get(r.case_id)
        checks = extraction_checks(case, r.extracted or {}, annotation)
        for k, v in checks.items():
            field_hits[k].append(v)
        all_ok.append(all(checks.values()))

        spec = (annotation or {}).get("evidence") or {"mode": "any_of", "passages": [case.gold_evidence]}
        gold = [verify_quote(q, case.terms) for q in spec["passages"]]
        ev = r.verdict_evidence
        if ev and ev.get("verified"):
            hit = any(_overlap((ev["start"], ev["end"]), (g.start, g.end)) for g in gold)
            overlap.append(hit)
            if case.gold_label != "UNKNOWN":
                overlap_decisive.append(hit)
        if case.gold_label != "UNKNOWN":
            spans = _quoted_spans(r)
            found = [any(_overlap(s, (g.start, g.end)) for s in spans) for g in gold]
            complete.append(all(found) if spec["mode"] == "all_parts" else any(found))
    return {
        "version": overlay["version"],
        "sha256": overlay["sha256"],
        "cases_corrected": sum(r.case_id in overlay["entries"] for r in ok),
        "extraction": {"field_accuracy": {k: rate(v) for k, v in field_hits.items()}, "all_cost_fields_correct_rate": rate(all_ok)},
        "evidence": {
            "verified_quote_overlaps_accepted_rate": rate(overlap),
            "verified_quote_overlaps_accepted_rate_decisive_gold_only": rate(overlap_decisive),
            "decisive_gold_evidence_complete_rate": rate(complete),
        },
    }


def compute_metrics(results: list[CaseResult], cases: list[Case], overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    by_id = {c.case_id: c for c in cases}
    ok = [r for r in results if r.status == "ok"]
    errors = [r for r in results if r.status == "error"]

    def cls(rs):
        return classification_metrics([(r.gold_label, r.predicted) for r in rs])

    groups = lambda key: {k: cls([r for r in ok if getattr(r, key) == k]) for k in sorted({getattr(r, key) for r in ok})}  # noqa: E731

    decisive = [r for r in ok if r.model_verdict in ("MATCH", "CONTRADICTION")]
    supported = [r for r in decisive if r.verdict_evidence and r.verdict_evidence.get("verified")]

    overlap_all, overlap_unflagged, overlap_decisive_gold = [], [], []
    for r in ok:
        ev = r.verdict_evidence
        if not (ev and ev.get("verified")):
            continue
        case = by_id[r.case_id]
        gold = verify_quote(case.gold_evidence, case.terms)
        hit = bool(gold.verified and _overlap((ev["start"], ev["end"]), (gold.start, gold.end)))
        overlap_all.append(hit)
        if r.case_id not in ANNOTATION_FLAGS:
            overlap_unflagged.append(hit)
        if case.gold_label != "UNKNOWN":  # a gold quote for UNKNOWN only points near the gap
            overlap_decisive_gold.append(hit)

    field_hits: dict[str, list[bool]] = defaultdict(list)
    all_fields_ok = []
    for r in ok:
        checks = extraction_checks(by_id[r.case_id], r.extracted or {})
        for k, v in checks.items():
            field_hits[k].append(v)
        all_fields_ok.append(all(checks.values()))

    total_claims = sum(r.facts_verified + r.facts_rejected for r in ok)
    token_rows = [r.tokens for r in results if r.tokens]
    peak = lambda name: max((t[name] for t in token_rows if isinstance(t.get(name), int)), default=None)  # noqa: E731
    rate = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    metrics = {
        "coverage": {
            "n_cases": len(results),
            "n_predictions": len(ok),
            "n_errors": len(errors),
            "error_codes": dict(Counter(r.error_code for r in errors)),
        },
        "classification": cls(ok),
        # The UI headline uses the claim-by-claim result, so it is scored separately.
        "classification_displayed": classification_metrics([(r.gold_label, r.displayed_verdict or r.predicted) for r in ok]),
        "displayed_differs_from_verdict": sum((r.displayed_verdict or r.predicted) != r.predicted for r in ok),
        "strict_displayed_accuracy_errors_count_as_wrong": (
            sum((r.displayed_verdict or r.predicted) == r.gold_label for r in ok) / len(results)
        ) if results else None,
        "truncated_responses": sum(r.truncated for r in results),
        "tokens": {"cases_recorded": len(token_rows), "peak_output": peak("output_tokens"),
                   "peak_reasoning": peak("reasoning_tokens"), "peak_total": peak("total_tokens")},
        "strict_accuracy_errors_count_as_wrong": (sum(r.predicted == r.gold_label for r in ok) / len(results)) if results else None,
        "per_language": groups("language"),
        "per_scenario": groups("scenario"),
        "evidence": {
            "model_decisive_verdicts": len(decisive),
            "decisive_with_verified_quote_rate": rate([r in supported for r in decisive]),
            "downgraded_to_unknown_rate": rate([bool(r.downgraded) for r in ok]),
            "verified_quote_overlaps_gold_rate": rate(overlap_all),
            "verified_quote_overlaps_gold_rate_excluding_flagged": rate(overlap_unflagged),
            "verified_quote_overlaps_gold_rate_decisive_gold_only": rate(overlap_decisive_gold),
            "rejected_claims_rate": (sum(r.facts_rejected for r in ok) / total_claims) if total_claims else None,
        },
        "extraction": {
            "field_accuracy": {k: rate(v) for k, v in field_hits.items()},
            "all_cost_fields_correct_rate": rate(all_fields_ok),
            "note": "Compared with gold Monthly price, Trial days, Auto renewal, Additional fee, Currency. "
            "Projections are not gold-scored (no gold intro-price/billing-period columns).",
        },
        "latency_ms_median": sorted(r.latency_ms for r in ok)[len(ok) // 2] if ok else None,
    }
    if overlay is not None:
        metrics["overlay"] = overlay_metrics(ok, cases, overlay)
    return metrics


# ------------------------------------------------------------------- saving


class NoPredictionsError(RuntimeError):
    pass


def save_run(out_root: Path, manifest: dict, results: list[CaseResult], metrics: dict) -> Path:
    if not any(r.status == "ok" for r in results):
        raise NoPredictionsError("No successful predictions: nothing was saved.")
    stamp = manifest["started_at"].replace(":", "").replace("-", "")
    run_dir = out_root / f"{stamp}_{manifest['split']}_{re.sub(r'[^A-Za-z0-9.]+', '-', manifest['model'])}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with (run_dir / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(render_report(manifest, metrics), encoding="utf-8")
    return run_dir


def save_failed_attempt(out_root: Path, manifest: dict, results: list[CaseResult]) -> Path:
    """Record a run with no successful prediction. It holds no metrics, but its requests may have been billed."""
    out_root.mkdir(parents=True, exist_ok=True)
    stamp = manifest["started_at"].replace(":", "").replace("-", "")
    path = out_root / f"{stamp}_{manifest['split']}_failed_attempt.json"
    path.write_text(json.dumps({"manifest": manifest, "results": [asdict(r) for r in results]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _overlay_report(m: dict) -> list[str]:
    o = m.get("overlay")
    if not o:
        return []
    return [
        f"## With annotation overlay {o['version']} ({o['cases_corrected']} corrected case(s); gold labels unchanged)",
        *[f"- {k}: {_pct(v)}" for k, v in o["extraction"]["field_accuracy"].items()],
        f"- All fields correct: {_pct(o['extraction']['all_cost_fields_correct_rate'])}",
        *[f"- {k.replace('_', ' ')}: {_pct(v)}" for k, v in o["evidence"].items()],
        "",
    ]


def render_report(manifest: dict, m: dict) -> str:
    c = m["classification"]
    lines = [
        f"# FAIR-Bench run: {manifest['split']} split",
        "",
        f"- Model: `{manifest['model']}` · prompt `{manifest['prompt_version']}` · dataset sha256 `{manifest['dataset_sha256'][:12]}…`",
        f"- Started {manifest['started_at']} · finished {manifest['finished_at']}",
        f"- Coverage: {m['coverage']['n_predictions']}/{m['coverage']['n_cases']} predictions, "
        f"{m['coverage']['n_errors']} errors {m['coverage']['error_codes'] or ''}",
    ]
    if manifest.get("aborted"):
        lines.append(f"- **Run aborted:** {manifest['aborted']}")
    lines += [
        "",
        "## Classification (successful predictions only)",
        f"- Accuracy: {_pct(c.get('accuracy'))} · Macro-F1: {_pct(c.get('macro_f1'))} (n={c.get('n', 0)})",
        f"- Strict accuracy (errors counted wrong): {_pct(m['strict_accuracy_errors_count_as_wrong'])}",
        f"- Displayed verdict (UI headline) accuracy: {_pct(m['classification_displayed'].get('accuracy'))} · "
        f"Macro-F1: {_pct(m['classification_displayed'].get('macro_f1'))} · differs from top-level verdict in "
        f"{m['displayed_differs_from_verdict']} case(s)",
        f"- Tokens: {manifest.get('token_usage', 'not recorded')} · per-case peaks: {m['tokens']} · "
        f"truncated responses: {m['truncated_responses']}",
        "",
        "| Language | n | Accuracy | Macro-F1 |",
        "|---|---|---|---|",
        *[f"| {k} | {v['n']} | {_pct(v.get('accuracy'))} | {_pct(v.get('macro_f1'))} |" for k, v in m["per_language"].items()],
        "",
        "## Evidence",
        *[f"- {k.replace('_', ' ')}: {_pct(v) if isinstance(v, float) else v}" for k, v in m["evidence"].items()],
        "",
        "## Extraction (cost-relevant fields)",
        *[f"- {k}: {_pct(v)}" for k, v in m["extraction"]["field_accuracy"].items()],
        f"- All fields correct: {_pct(m['extraction']['all_cost_fields_correct_rate'])}",
        "",
        *_overlay_report(m),
        "## Limitations",
        *[f"- {x}" for x in LIMITATIONS],
        "",
    ]
    return "\n".join(lines)
