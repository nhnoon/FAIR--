"""FAIR versus direct Muse Spark, as defined in docs/COMPARISON_PROTOCOL.md.

  python -m evaluation.run_comparison plan
  python -m evaluation.run_comparison run --gold <frozen labels> --confirm-paid-calls

`plan` makes no calls. `run` makes paid calls: one FAIR and one direct request per case, in the same
order, sequentially, with no retries. It also needs MODEL_LIVE_CALLS_ENABLED=true for that process.

The labels must exist before the run. They are never sent to a model and are scored only after every
call has finished. Labels without a recorded independent review need --allow-draft-gold, and the result is
then marked as not independent. Every result is saved as it arrives, so a failure loses nothing already paid for.

The first failure ends the run: an API error, a timeout, a malformed or truncated response, missing token
counts, a token budget breach or an unexpected request count. No further request is sent, and the reason is saved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.analyzer import analyze
from app.config import get_settings, load_env_file
from app.meta_client import MetaClient, ModelError, ModelResponseError, ModelTruncatedError
from app.prompts import INSTRUCTIONS, PROMPT_VERSION, build_input
from app.schemas import AnalyzeRequest

from .challenge import (
    BASELINE_PROMPT,
    V2_GOLD_PATH,
    V2_INPUTS_PATH,
    V2_MANIFEST_PATH,
    Normalized,
    baseline_input,
    file_sha256,
    load_gold,
    load_inputs,
    normalize_direct,
    normalize_fair,
    prompt_sha256,
    score_case,
    summarize,
)

DEFAULT_OUT = Path(__file__).resolve().parent / "runs"
SYSTEMS = ("fair", "direct")
MAX_REQUESTS_PER_SYSTEM = 12
MAX_REQUESTS = MAX_REQUESTS_PER_SYSTEM * len(SYSTEMS)
MAX_OUTPUT_TOKENS = 8000  # sent with each request; the reported count is checked after it
MAX_INPUT_TOKENS = 5000  # the API enforces no input ceiling here, so this is checked after each request
MAX_INPUT_CHARS = 10000  # before any request: an estimate of the same limit at 2 characters per token, not a count
PIPELINE_ROOT = Path(__file__).resolve().parents[1]


def pipeline_sha256() -> str:
    """FAIR's code and this scorer. Record it before a run: changing either afterwards means a new comparison."""
    files = sorted((PIPELINE_ROOT / "app").glob("*.py")) + [PIPELINE_ROOT / "evaluation" / "challenge.py", Path(__file__).resolve()]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8") + path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def is_independent(gold_path: Path) -> bool:
    return bool(json.loads(gold_path.read_text(encoding="utf-8")).get("provenance", {}).get("independent_review"))


def frozen_problems() -> list[str]:
    """Anything that changed since the comparison was declared."""
    m = json.loads(V2_MANIFEST_PATH.read_text(encoding="utf-8"))
    checks = {
        "inputs": (m["inputs_sha256"], file_sha256(V2_INPUTS_PATH)),
        "baseline prompt": (m["baseline_prompt_sha256"], prompt_sha256()),
        "FAIR prompt": (m["fair_prompt_sha256"], hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()),
    }
    return [name for name, (want, have) in checks.items() if want != have]


def cmd_plan(_: argparse.Namespace) -> int:
    cases = load_inputs(V2_INPUTS_PATH)
    print(f"{len(cases)} cases, {len(cases) * len(SYSTEMS)} paid requests at most: {', '.join(SYSTEMS)} on each, in file order.")
    print(f"FAIR prompt {PROMPT_VERSION}; direct prompt hash {prompt_sha256()}.")
    print(f"Code hash {pipeline_sha256()}.")
    problems = frozen_problems()
    print(f"Changed since declared: {', '.join(problems)}" if problems else "Inputs and prompts match the manifest.")
    return 1 if problems else 0


def _fair(client: MetaClient, case: dict) -> tuple[Normalized, dict]:
    response = analyze(AnalyzeRequest(terms=case["terms"], expectation=case["expectation"], language="en"), client).model_dump(mode="json")
    return normalize_fair(response), {"status": "ok", "visible_response": response}


def _direct(client: MetaClient, case: dict) -> tuple[Normalized, dict]:
    answer = normalize_direct(client.generate(BASELINE_PROMPT, baseline_input(case["terms"], case["expectation"])))
    return answer, {"status": answer.status, "error": answer.error}


CALLS = {"fair": _fair, "direct": _direct}


def _saved(record: dict) -> str:
    return json.dumps({**record, "answer": vars(record["answer"])}, ensure_ascii=False, default=str) + "\n"


def _failure(exc: ModelError) -> tuple[str, str]:
    if isinstance(exc, ModelTruncatedError):
        return "model_truncated", exc.message
    if isinstance(exc, ModelResponseError):
        return "malformed_response", exc.message
    return exc.code, exc.message


def _anomaly(client: MetaClient, answer: Normalized, meta: dict, usage: dict, sent: int) -> tuple[str, str] | None:
    """Why a request that returned must still end the run. A wrong verdict is a result, never a reason."""
    if answer.status == "error":
        return "malformed_response", f"The answer could not be read ({answer.error})."
    dropped = ((meta.get("visible_response") or {}).get("claims_summary") or {}).get("dropped")
    if dropped:
        return "malformed_response", f"{dropped} model claim(s) could not be read."
    if sent != 1:
        return "unexpected_request_count", f"{sent} requests were counted for one call."
    if not all(isinstance(usage.get(k), int) for k in ("input_tokens", "output_tokens", "total_tokens")):
        return "token_usage_missing", "Token usage was not reported, so the budgets cannot be checked."
    if usage["output_tokens"] > client.settings.max_output_tokens:
        return "output_budget_exceeded", f"{usage['output_tokens']} output tokens."
    if usage["input_tokens"] > MAX_INPUT_TOKENS:
        return "input_budget_exceeded", f"{usage['input_tokens']} input tokens."
    if answer.latency_ms > client.settings.timeout_seconds * 1000:
        return "timeout_exceeded", f"The request took {answer.latency_ms} ms."
    return None


def run_all(client: MetaClient, cases: list[dict], out=None) -> tuple[list[dict], dict | None]:
    """One record per system per case. After the first failure nothing is sent, and the remaining cases stay in as errors."""
    records, stopped = [], None
    sent_by_system = dict.fromkeys(SYSTEMS, 0)

    def keep(record: dict) -> None:
        records.append(record)
        if out:
            out.write(_saved(record))
            out.flush()

    for case in cases:
        for system in SYSTEMS:
            if not stopped and sent_by_system[system] >= MAX_REQUESTS_PER_SYSTEM:
                stopped = {"reason": "system_request_limit", "detail": f"{system} reached {MAX_REQUESTS_PER_SYSTEM} requests.", "case_id": case["case_id"], "system": system}
            if stopped:
                keep({"case_id": case["case_id"], "system": system, "answer": Normalized(status="error", error="not_run"), "meta": {"status": "not_run"}, "requests_sent": 0})
                continue
            client.last_usage = client.last_call = None
            requests_before = client.usage_totals["requests"]
            failure = None
            started = time.perf_counter()
            try:
                answer, meta = CALLS[system](client, case)
            except ModelError as exc:
                failure = _failure(exc)
                answer, meta = Normalized(status="error", error=failure[0]), {"status": "error", "error": failure[0]}
            except Exception as exc:  # the failure stays in the results and counts as wrong
                failure = type(exc).__name__, "The call failed unexpectedly."
                answer, meta = Normalized(status="error", error=failure[0]), {"status": "error", "error": failure[0]}
            answer.latency_ms = round((time.perf_counter() - started) * 1000)
            usage = client.last_usage or {}
            answer.total_tokens = usage.get("total_tokens")
            call = client.last_call or {}
            sent = client.usage_totals["requests"] - requests_before
            sent_by_system[system] += sent
            failure = failure or _anomaly(client, answer, meta, usage, sent)
            if failure:
                stopped = {"reason": failure[0], "detail": failure[1], "case_id": case["case_id"], "system": system, "request_number": client.usage_totals["requests"]}
            keep({"case_id": case["case_id"], "system": system, "answer": answer, "meta": meta, "tokens": usage, "raw_output": call.get("raw_output"), "requests_sent": sent})
    return records, stopped


def score_all(records: list[dict], cases: list[dict], gold: dict[str, dict]) -> dict[str, dict]:
    by_id = {c["case_id"]: c for c in cases}
    return {
        system: summarize([score_case(by_id[r["case_id"]], gold[r["case_id"]], r["answer"]) for r in records if r["system"] == system and r["case_id"] in gold])
        for system in SYSTEMS
    }


def both_answered(records: list[dict]) -> list[str]:
    ok = [{r["case_id"] for r in records if r["system"] == s and r["answer"].status == "ok"} for s in SYSTEMS]
    return sorted(ok[0] & ok[1])


def cmd_run(args: argparse.Namespace, client: MetaClient | None = None) -> int:
    if not args.confirm_paid_calls:
        print("This makes paid Meta API calls. Re-run with --confirm-paid-calls.", file=sys.stderr)
        return 2
    gold_path = Path(args.gold)
    if not gold_path.is_file():
        print("The labels must be frozen before the run: --gold must name an existing file. No calls were made.", file=sys.stderr)
        return 2
    is_draft = not is_independent(gold_path)
    if is_draft and not args.allow_draft_gold:
        print("These labels record no independent review. Re-run with --allow-draft-gold to accept a result marked as not independent. No calls were made.", file=sys.stderr)
        return 2
    problems = frozen_problems()
    if problems:
        print(f"Changed since declared: {', '.join(problems)}. No calls were made.", file=sys.stderr)
        return 2
    if client is None:
        load_env_file()
        client = MetaClient(get_settings())
    declared = json.loads(V2_MANIFEST_PATH.read_text(encoding="utf-8"))["model"]
    if client.model != declared:
        print(f"The comparison was declared for {declared}, not {client.model}. No calls were made.", file=sys.stderr)
        return 2
    try:
        client.check_ready()
    except ModelError as exc:
        print(f"Not configured for live calls: {exc.message}", file=sys.stderr)
        return 2

    cases = load_inputs(V2_INPUTS_PATH)
    gold = load_gold(gold_path)
    missing = sorted({c["case_id"] for c in cases} - set(gold))
    if missing:
        print(f"Labels are missing for {', '.join(missing)}. No calls were made.", file=sys.stderr)
        return 2
    if len(cases) > MAX_REQUESTS_PER_SYSTEM:
        print(f"{len(cases)} cases would pass the limit of {MAX_REQUESTS_PER_SYSTEM} requests per system. No calls were made.", file=sys.stderr)
        return 2
    if client.settings.max_output_tokens > MAX_OUTPUT_TOKENS:
        print(f"The output budget is above {MAX_OUTPUT_TOKENS} tokens. No calls were made.", file=sys.stderr)
        return 2
    too_long = [c["case_id"] for c in cases if max(len(INSTRUCTIONS) + len(build_input(c["terms"], c["expectation"])), len(BASELINE_PROMPT) + len(baseline_input(c["terms"], c["expectation"]))) > MAX_INPUT_CHARS]
    if too_long:
        print(f"Input is too long for {', '.join(too_long)}. No calls were made.", file=sys.stderr)
        return 2
    gold_sha = file_sha256(gold_path)
    client.max_requests = MAX_REQUESTS

    folder = Path(args.out) / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_comparison_v2_{client.model}"
    folder.mkdir(parents=True)
    with (folder / "outputs.jsonl").open("w", encoding="utf-8") as out:
        records, stopped = run_all(client, cases, out)
    uncontested = {k: v for k, v in gold.items() if not v.get("contested")}
    report = {
        "labels": "AUTHOR DRAFT, NOT INDEPENDENT" if is_draft else "independently reviewed before the run",
        "gold_sha256": gold_sha,
        "model": client.model,
        "fair_prompt_version": PROMPT_VERSION,
        "baseline_prompt_sha256": prompt_sha256(),
        "code_sha256": pipeline_sha256(),
        "max_output_tokens": client.settings.max_output_tokens,
        "timeout_seconds": client.settings.timeout_seconds,
        "sdk_retries": 0,
        "stopped_on": stopped["reason"] if stopped else None,
        "stop_detail": stopped,
        "requests_by_system": {s: sum(r["requests_sent"] for r in records if r["system"] == s) for s in SYSTEMS},
        "cases_not_run": sorted({r["case_id"] for r in records if r["meta"]["status"] == "not_run"}),
        "cases_answered_by_both": both_answered(records),
        "contested_cases": sorted(set(gold) - set(uncontested)),
        "token_usage": client.usage_totals,
        "results": score_all(records, cases, gold),
        "results_without_contested": score_all(records, cases, uncontested),
    }
    (folder / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {folder}. Requests: {client.usage_totals['requests']}. Stopped on: {report['stopped_on']}.")
    return 1 if stopped else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evaluation.run_comparison", description="FAIR versus direct Muse Spark")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="show the plan; makes no calls")
    r = sub.add_parser("run", help="paid: run both systems on every case")
    r.add_argument("--gold", required=True, help="labels frozen before the run")
    r.add_argument("--allow-draft-gold", action="store_true")
    r.add_argument("--out", default=str(DEFAULT_OUT))
    r.add_argument("--confirm-paid-calls", action="store_true")
    return p


def main(argv: list[str] | None = None, client: MetaClient | None = None) -> int:
    args = build_parser().parse_args(argv)
    return cmd_plan(args) if args.command == "plan" else cmd_run(args, client)


if __name__ == "__main__":
    sys.exit(main())
