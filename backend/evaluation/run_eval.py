"""FAIR-Bench CLI (run from backend/).

  python -m evaluation.run_eval audit
      Dataset audit only. No model calls.

  python -m evaluation.run_eval run --split development --confirm-paid-calls [--limit N]
      Live run through the real pipeline (Meta API + evidence validator + cost engine).
      Requires MODEL_API_KEY in backend/.env and MODEL_LIVE_CALLS_ENABLED=true (set it for
      this one process; a real environment variable overrides backend/.env).
      --cases FAIR-003,FAIR-007 runs only those cases of the chosen split.
      --max-requests N refuses to attempt more than N requests. --stop-on-anomaly ends the run
      at the first error, truncation, unreadable claim, missing usage or budget anomaly.
      The Test split additionally requires --confirm-test-split (final reporting only).

Results are written to evaluation/runs/<timestamp>_<split>_<model>/ only when at
least one real prediction succeeded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.analyzer import analyze
from app.config import get_settings, load_env_file
from app.meta_client import MetaClient, ModelError
from app.prompts import INSTRUCTIONS, PROMPT_VERSION
from app.schemas import AnalyzeRequest

from .fair_bench import (
    DATASET_PATH,
    DATASET_SHA256,
    LIMITATIONS,
    NoPredictionsError,
    SPLITS,
    audit_dataset,
    compute_metrics,
    file_sha256,
    load_cases,
    load_overlay,
    run_cases,
    save_failed_attempt,
    save_run,
    select_cases,
    select_split,
)

DEFAULT_OUT = Path(__file__).resolve().parent / "runs"
MAX_EXPECTED_INPUT_TOKENS = 5000  # far above short benchmark cases; the API enforces no input ceiling here


def anomaly(r, budget: int, timeout_seconds: float) -> str | None:
    """Why a run must stop after this result. A wrong verdict is a result, never a reason."""
    if r.status == "error":
        return f"stopped on {r.error_code} at {r.case_id}: {r.error_message}"
    if r.dropped_claims:
        return f"stopped at {r.case_id}: {r.dropped_claims} malformed claim(s)"
    tokens = r.tokens or {}
    if not all(isinstance(tokens.get(k), int) for k in ("input_tokens", "output_tokens", "total_tokens")):
        return f"stopped at {r.case_id}: token usage was not reported"
    if tokens["output_tokens"] > budget:
        return f"stopped at {r.case_id}: output tokens exceeded the budget"
    if tokens["input_tokens"] > MAX_EXPECTED_INPUT_TOKENS:
        return f"stopped at {r.case_id}: input tokens were unexpectedly high"
    if r.latency_ms > timeout_seconds * 1000:
        return f"stopped at {r.case_id}: the request exceeded the application timeout"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_audit(_: argparse.Namespace) -> int:
    sha = file_sha256(DATASET_PATH)
    report = audit_dataset(load_cases())
    report["dataset_sha256"] = sha
    report["dataset_sha256_matches_expected"] = sha == DATASET_SHA256
    report["limitations"] = LIMITATIONS
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace, client: MetaClient | None = None) -> int:
    if args.split == "test" and not args.confirm_test_split:
        print("Refusing to run the Test split without --confirm-test-split. "
              "Use Development for prompt iteration; Test is for final reporting only.", file=sys.stderr)
        return 2
    if not args.confirm_paid_calls:
        print("Live evaluation makes paid Meta API calls. Re-run with --confirm-paid-calls.", file=sys.stderr)
        return 2

    sha = file_sha256(DATASET_PATH)
    if sha != DATASET_SHA256:
        print(f"Dataset hash mismatch ({sha}); labels may have changed. Aborting.", file=sys.stderr)
        return 2

    if client is None:
        load_env_file()
        client = MetaClient(get_settings())
    try:
        client.check_ready()
    except ModelError as exc:
        print(f"Not configured for live calls: {exc.message}", file=sys.stderr)
        return 2

    all_cases = load_cases()
    overlay = load_overlay(all_cases)
    cases = select_split(all_cases, args.split)
    if args.cases:
        try:
            cases = select_cases(cases, args.cases)
        except ValueError as exc:
            print(f"Invalid --cases for the {args.split} split: {exc}. No calls were made.", file=sys.stderr)
            return 2
    if args.limit:
        cases = cases[: args.limit]
    if args.max_requests and len(cases) > args.max_requests:
        print(f"{len(cases)} case(s) exceed --max-requests {args.max_requests}. No calls were made.", file=sys.stderr)
        return 2
    client.max_requests = args.max_requests or None
    budget = client.settings.max_output_tokens
    print(f"Running {len(cases)} {args.split} case(s) against {client.model}: {len(cases)} paid call(s), "
          f"at most {budget} output tokens each.", file=sys.stderr)

    started = _now()

    def predict(case):
        return analyze(AnalyzeRequest(terms=case.terms, expectation=case.expectation, language="en"), client)

    def progress(r):
        mark = r.predicted if r.status == "ok" else f"ERROR {r.error_code}"
        t, total = r.tokens or {}, client.usage_totals
        print(f"  {r.case_id} gold={r.gold_label} -> {mark} | {r.latency_ms} ms | input={t.get('input_tokens')} output={t.get('output_tokens')} "
              f"reasoning={t.get('reasoning_tokens')} total={t.get('total_tokens')} | cumulative requests={total['requests']} "
              f"total_tokens={total['total_tokens']}", file=sys.stderr, flush=True)

    stop_check = (lambda r: anomaly(r, budget, client.settings.timeout_seconds)) if args.stop_on_anomaly else None
    results, aborted = run_cases(cases, predict, on_progress=progress, get_usage=lambda: client.last_usage,
                                 get_call=lambda: client.last_call, stop_check=stop_check)
    metrics = compute_metrics(results, cases, overlay)
    print(f"Token usage: {json.dumps(client.usage_totals)}", file=sys.stderr)
    manifest = {
        "split": args.split,
        "limit": args.limit,
        "cases": args.cases,
        "max_output_tokens": budget,
        "max_requests": args.max_requests,
        "stop_on_anomaly": args.stop_on_anomaly,
        "timeout_seconds": client.settings.timeout_seconds,
        "token_usage": client.usage_totals,
        "model": client.model,
        "base_url": client.settings.base_url,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest(),
        "dataset": str(DATASET_PATH.name),
        "dataset_sha256": sha,
        "overlay_version": overlay["version"],
        "overlay_sha256": overlay["sha256"],
        "started_at": started,
        "finished_at": _now(),
        "aborted": aborted,
        "python": platform.python_version(),
        "test_split_confirmed": bool(args.confirm_test_split),
    }
    try:
        run_dir = save_run(Path(args.out), manifest, results, metrics)
    except NoPredictionsError as exc:
        print(f"{exc} Errors: {metrics['coverage']['error_codes']}", file=sys.stderr)
        if results:
            print(f"Attempt recorded in {save_failed_attempt(Path(args.out), manifest, results)}", file=sys.stderr)
        if aborted:
            print(f"Aborted: {aborted}", file=sys.stderr)
        return 1
    print(f"Saved run to {run_dir}", file=sys.stderr)
    if aborted:
        print(f"Run aborted early: {aborted}", file=sys.stderr)
    print(json.dumps({"coverage": metrics["coverage"], "classification": {
        k: metrics["classification"].get(k) for k in ("n", "accuracy", "macro_f1")}}, indent=2))
    return 0 if not aborted else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evaluation.run_eval", description="FAIR-Bench evaluation")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("audit", help="dataset audit (no model calls)")
    r = sub.add_parser("run", help="live evaluation through the real pipeline")
    r.add_argument("--split", choices=list(SPLITS), required=True)
    r.add_argument("--limit", type=int, default=0, help="only the first N cases of the split")
    r.add_argument("--cases", default="", help="comma-separated case IDs within the split")
    r.add_argument("--max-requests", type=int, default=0, help="refuse to attempt more than N requests")
    r.add_argument("--stop-on-anomaly", action="store_true", help="end the run at the first error or budget anomaly")
    r.add_argument("--out", default=str(DEFAULT_OUT))
    r.add_argument("--confirm-paid-calls", action="store_true")
    r.add_argument("--confirm-test-split", action="store_true")
    return p


def main(argv: list[str] | None = None, client: MetaClient | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Arabic text on Windows consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        return cmd_audit(args)
    return cmd_run(args, client=client)


if __name__ == "__main__":
    sys.exit(main())
