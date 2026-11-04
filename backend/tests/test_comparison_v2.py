"""Challenge set v2 and the comparison runner. Offline: a fake SDK, never a model."""

import json
import re
import time
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import Settings
from app.evidence import normalize, verify_quote
from app.meta_client import MetaClient
from evaluation import run_comparison
from evaluation.challenge import (
    BASELINE_PROMPT,
    INPUTS_PATH,
    V2_GOLD_PATH,
    V2_INPUTS_PATH,
    V2_MANIFEST_PATH,
    Normalized,
    file_sha256,
    load_gold,
    load_inputs,
    prompt_sha256,
    score_case,
    summarize,
)
from evaluation.fair_bench import load_cases
from tests.conftest import FakeSDK

INPUTS = load_inputs(V2_INPUTS_PATH)
GOLD = load_gold(V2_GOLD_PATH)
WORD = re.compile(r"[^\W\d_]+")
# A well-formed answer for both systems, so a fake run stops only where a test makes it fail.
DIRECT = json.dumps({"verdict": "UNKNOWN", "quotes": [], "recurring_price": None, "billing_period": "unknown", "intro_price": None, "one_time_fees": [], "total_12_months": None,
                     "verdict_evidence": None, "explanation": {"en": "x", "ar": "س"}, "extraction": {}, "claims": []})


def words(text):
    return set(WORD.findall(normalize(text)))


def test_set_covers_every_language_and_outcome_with_more_than_one_match():
    assert 8 <= len(INPUTS) <= 12
    assert {c["language"] for c in INPUTS} == {"English", "Arabic", "Mixed"}
    assert [c["case_id"] for c in INPUTS] == sorted(GOLD)
    labels = [g["verdict"] for g in GOLD.values()]
    assert all(labels.count(v) >= 3 for v in ("MATCH", "CONTRADICTION", "UNKNOWN"))


def test_inputs_hold_no_gold_material_or_case_purpose():
    raw = V2_INPUTS_PATH.read_text(encoding="utf-8")
    for key in ('"verdict"', '"accepted_evidence"', '"rationale"', '"cost"', '"focus"', "MATCH", "CONTRADICTION", "UNKNOWN"):
        assert key not in raw
    for case in INPUTS:
        assert set(case) == {"case_id", "language", "terms", "expectation"}


def test_gold_is_marked_as_a_draft_and_its_passages_come_from_the_terms():
    assert "NOT INDEPENDENT" in json.loads(V2_GOLD_PATH.read_text(encoding="utf-8"))["status"]
    for case in INPUTS:
        gold = GOLD[case["case_id"]]
        assert all(verify_quote(q, case["terms"]).verified for q in gold["accepted_evidence"]), case["case_id"]
        assert bool(gold["accepted_evidence"]) == (gold["verdict"] != "UNKNOWN"), case["case_id"]


def test_cases_differ_from_the_benchmark_and_from_challenge_v1():
    others = [(b.case_id, b.terms, b.expectation) for b in load_cases()]
    others += [(c["case_id"], c["terms"], c["expectation"]) for c in load_inputs(INPUTS_PATH)]
    for case in INPUTS:
        for other_id, terms, expectation in others:
            for mine, theirs in ((case["terms"], terms), (case["expectation"], expectation)):
                a, c = words(mine), words(theirs)
                assert len(a & c) / max(len(a | c), 1) < 0.5, (case["case_id"], other_id)


def test_manifest_freezes_this_set():
    m = json.loads(V2_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert m["inputs_sha256"] == file_sha256(V2_INPUTS_PATH) and m["gold_draft_sha256"] == file_sha256(V2_GOLD_PATH)
    assert m["baseline_prompt_sha256"] == prompt_sha256()
    assert run_comparison.frozen_problems() == []


@pytest.mark.parametrize("case_id", sorted(GOLD))
def test_a_perfect_answer_built_from_gold_scores_fully(case_id):
    case, gold = next(c for c in INPUTS if c["case_id"] == case_id), GOLD[case_id]
    cost = gold["cost"]
    s = score_case(case, gold, Normalized(verdict=gold["verdict"], quotes=gold["accepted_evidence"], recurring_price=cost["recurring_price"], billing_period=cost["billing_period"],
                                          intro_price=cost["intro_price"], one_time_fees=cost["one_time_fees"], total_12_months=cost["total_12_months"]))
    assert s["correct"] and s["total_correct"] and not s["unsupported_certainty"]


def by_id(case_id):
    return next(c for c in INPUTS if c["case_id"] == case_id), GOLD[case_id]


@pytest.mark.parametrize(
    "answer",
    [
        Normalized(verdict="MATCH", quotes=["No contracts."]),  # certain where the terms do not settle it
        Normalized(verdict="UNKNOWN", total_12_months="396"),  # a total where none is established: tested on CX-10 below
    ],
)
def test_unsupported_certainty_is_counted(answer):
    case, gold = by_id("CX-02") if answer.verdict == "MATCH" else by_id("CX-10")
    assert score_case(case, gold, answer)["unsupported_certainty"]


def test_a_decisive_verdict_with_an_invented_quote_is_unsupported_certainty():
    case, gold = by_id("CX-03")
    assert score_case(case, gold, Normalized(verdict="CONTRADICTION", quotes=["This sentence is not in the offer."], total_12_months="120"))["unsupported_certainty"]


def test_summary_reports_unsupported_certainty_with_its_denominator():
    case, gold = by_id("CX-02")
    m = summarize([score_case(case, gold, Normalized(verdict="MATCH", quotes=["No contracts."]))])
    assert m["unsupported_certainty"] == {"hits": 1, "of": 1, "rate": 1.0}


# ---------------------------------------------------------------- the runner never needs a model to be tested


USAGE = SimpleNamespace(input_tokens=100, output_tokens=100, total_tokens=200, output_tokens_details=None)


def reply(text=DIRECT, usage=USAGE, status="completed", reason=None):
    return SimpleNamespace(output_text=text, usage=usage, status=status, incomplete_details=SimpleNamespace(reason=reason))


class ScriptedSDK:
    """Answers well, except for one bad result at one request."""

    def __init__(self, output=DIRECT, bad=None, at=None):
        self.calls = []
        self.output, self.bad, self.at = output, bad, at
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) != self.at:
            return reply(self.output)
        if isinstance(self.bad, Exception):
            raise self.bad
        return self.bad


def fake_client(output=DIRECT, **settings):
    return MetaClient(Settings(api_key="k", live_calls_enabled=True, **settings), sdk_client=ScriptedSDK(output))


def args(tmp_path, *extra):
    return ["run", "--out", str(tmp_path), *extra]


def test_plan_makes_no_calls_and_needs_no_key(capsys):
    assert run_comparison.main(["plan"]) == 0
    assert "24 paid requests" in capsys.readouterr().out


def test_run_refuses_without_the_paid_flag(tmp_path):
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold"), client) == 2
    assert client.usage_totals["requests"] == 0


def test_run_refuses_missing_labels_and_unacknowledged_draft_labels(tmp_path):
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(tmp_path / "none.json"), "--confirm-paid-calls"), client) == 2
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--confirm-paid-calls"), client) == 2
    assert client.usage_totals["requests"] == 0


def test_run_refuses_when_live_calls_are_off(tmp_path):
    client = MetaClient(Settings(api_key="k", live_calls_enabled=False), sdk_client=FakeSDK(output_text=DIRECT))
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 2


def test_run_refuses_when_anything_frozen_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(run_comparison, "prompt_sha256", lambda: "changed")
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 2
    assert client.usage_totals["requests"] == 0


def test_a_correct_amount_is_not_marked_wrong_for_how_it_is_worded():
    case, gold = by_id("CX-01")
    for worded in ("USD 168", "168 USD total", "$168.00", "١٦٨", 168):
        assert score_case(case, gold, Normalized(verdict="MATCH", quotes=gold["accepted_evidence"], total_12_months=worded))["total_correct"], worded


def test_an_amount_with_several_numbers_goes_to_a_person_not_automatically_wrong():
    case, gold = by_id("CX-01")
    s = score_case(case, gold, Normalized(verdict="MATCH", total_12_months="USD 14 x 12 = USD 168"))
    assert s["money_needs_review"] and not s["total_correct"] and not s["total_withheld_wrongly"]
    assert summarize([s])["money_answers_for_human_review"] == 1


@pytest.mark.parametrize("words", ["not established", "cannot be determined", "لا يمكن تحديده"])
def test_saying_no_total_in_words_is_no_total(words):
    case, gold = by_id("CX-10")
    s = score_case(case, gold, Normalized(verdict="UNKNOWN", total_12_months=words))
    assert s["total_correct"] and not s["total_unsupported"] and not s["money_needs_review"]


def test_billing_and_fees_read_the_same_for_both_systems():
    case, gold = by_id("CX-01")
    s = score_case(case, gold, Normalized(verdict="MATCH", billing_period=" Monthly ", one_time_fees=["none"]))
    assert s["billing_correct"] and s["fees_correct"]
    assert not score_case(case, gold, Normalized(status="error"))["billing_correct"]


def test_the_checks_are_measured_apart_from_the_prompt():
    from evaluation.challenge import normalize_fair
    case, gold = by_id("CX-02")
    response = {
        "verdict": "MATCH", "model_verdict": "MATCH", "claims_summary": {"overall": "UNKNOWN"}, "rejected_facts": [{"field": "x"}],
        "claims": [{"verdict": "UNKNOWN", "evidence": {"quote": "made up", "verified": False}}], "extracted_terms": {"one_time_fees": []}, "decision": {},
    }
    a = normalize_fair(response)
    m = summarize([score_case(case, gold, a)])
    assert m["verdict_accuracy"]["hits"] == 1 and m["verdict_accuracy_before_checks"]["hits"] == 0
    assert m["verdicts_changed_by_checks"] == 1 and m["values_rejected_by_checks"] == 2
    assert summarize([score_case(case, gold, Normalized(verdict="UNKNOWN"))])["verdict_accuracy_before_checks"]["of"] == 0


def test_a_reader_cannot_get_a_draft_marked_independent_by_copying_it(tmp_path):
    copy = tmp_path / "labels.json"
    copy.write_bytes(V2_GOLD_PATH.read_bytes())
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(copy), "--confirm-paid-calls"), client) == 2
    assert client.usage_totals["requests"] == 0


def test_run_refuses_a_model_other_than_the_declared_one(tmp_path):
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True, model="other-model"), sdk_client=FakeSDK(output_text=DIRECT))
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 2
    assert client.usage_totals["requests"] == 0


def test_a_crash_on_one_case_stops_the_run_and_keeps_every_result(tmp_path, monkeypatch):
    real = run_comparison.CALLS["direct"]

    def flaky(client, case):
        if case["case_id"] == "CX-03":
            raise KeyError("unexpected")
        return real(client, case)

    monkeypatch.setitem(run_comparison.CALLS, "direct", flaky)
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 1
    assert len(client._sdk.calls) == 5
    folder = next(tmp_path.iterdir())
    report = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert report["stopped_on"] == "KeyError" and report["stop_detail"]["case_id"] == "CX-03" and report["stop_detail"]["system"] == "direct"
    assert report["results"]["direct"]["errors"] == 10 and report["results"]["direct"]["cases"] == 12
    assert len((folder / "outputs.jsonl").read_text(encoding="utf-8").splitlines()) == 24


def test_results_are_saved_with_budgets_code_hash_and_fair_visible_answer(tmp_path):
    fair = json.dumps({"verdict": "UNKNOWN", "verdict_evidence": None, "explanation": {"en": "x", "ar": "س"}, "extraction": {}, "claims": []})
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), fake_client(fair)) == 0
    folder = next(tmp_path.iterdir())
    report = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert report["max_output_tokens"] and report["timeout_seconds"] and report["sdk_retries"] == 0 and len(report["code_sha256"]) == 64
    first = json.loads((folder / "outputs.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["system"] == "fair" and "visible_response" in first["meta"]


def test_contested_cases_are_reported_both_ways(tmp_path):
    gold = json.loads(V2_GOLD_PATH.read_text(encoding="utf-8"))
    gold["annotations"][0]["contested"] = True
    gold["provenance"] = {"independent_review": True}
    path = tmp_path / "reviewed.json"
    path.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"
    assert run_comparison.main(["run", "--out", str(out), "--gold", str(path), "--confirm-paid-calls"], fake_client()) == 0
    report = json.loads((next(out.iterdir()) / "summary.json").read_text(encoding="utf-8"))
    assert report["contested_cases"] == ["CX-01"] and report["labels"].startswith("independently")
    assert report["results"]["fair"]["cases"] == 12 and report["results_without_contested"]["fair"]["cases"] == 11


def test_a_run_uses_two_requests_per_case_sends_no_labels_and_marks_a_draft(tmp_path):
    client = fake_client()
    sent = []
    create = client._sdk.responses.create
    client._sdk.responses.create = lambda **kw: (sent.append(kw["instructions"] + kw["input"]), create(**kw))[1]
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 0
    assert client.usage_totals["requests"] == 24 == len(sent)
    assert sum(BASELINE_PROMPT in s for s in sent) == 12
    for gold in GOLD.values():
        assert not any(gold["rationale"] in s or gold["focus"] in s for s in sent)
    folder = next(tmp_path.iterdir())
    report = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert report["labels"].startswith("AUTHOR DRAFT") and report["results"]["direct"]["cases"] == 12 == report["results"]["fair"]["cases"]
    assert len((folder / "outputs.jsonl").read_text(encoding="utf-8").splitlines()) == 24


# ---------------------------------------------------------------- the first failure ends the run


REQUEST = httpx.Request("POST", "https://api.meta.ai/v1/responses")


def http_error(kind, status):
    return kind("error", response=httpx.Response(status, request=REQUEST), body=None)


# Each one fails the same way whichever system's request it reaches.
FAILURES = {
    "timeout": (openai.APITimeoutError(request=REQUEST), "model_timeout"),
    "connection": (openai.APIConnectionError(request=REQUEST), "model_unavailable"),
    "http_400": (http_error(openai.BadRequestError, 400), "model_unavailable"),
    "http_401": (http_error(openai.AuthenticationError, 401), "model_auth_failed"),
    "http_403": (http_error(openai.PermissionDeniedError, 403), "model_auth_failed"),
    "http_404": (http_error(openai.NotFoundError, 404), "model_not_found"),
    "http_422": (http_error(openai.UnprocessableEntityError, 422), "model_unavailable"),
    "http_429": (http_error(openai.RateLimitError, 429), "model_rate_limited"),
    "http_500": (http_error(openai.InternalServerError, 500), "model_unavailable"),
    "http_503": (http_error(openai.InternalServerError, 503), "model_unavailable"),
    "not_json": (reply("not json"), "malformed_response"),
    "json_list": (reply("[1, 2]"), "malformed_response"),
    "invalid_verdict": (reply(json.dumps({"verdict": "MAYBE"})), "malformed_response"),
    "empty_text": (reply("   "), "malformed_response"),
    "no_text": (reply(None), "malformed_response"),
    "status_failed": (reply(DIRECT, status="failed"), "malformed_response"),
    "status_cancelled": (reply(DIRECT, status="cancelled"), "malformed_response"),
    "truncated_at_budget": (reply('{"verdict"', status="incomplete", reason="max_output_tokens"), "model_truncated"),
    "truncated_other": (reply('{"verdict"', status="incomplete", reason="content_filter"), "model_truncated"),
    "usage_missing": (reply(DIRECT, usage=None), "token_usage_missing"),
    "usage_partial": (reply(DIRECT, usage=SimpleNamespace(input_tokens=100, output_tokens=None, total_tokens=None, output_tokens_details=None)), "token_usage_missing"),
    "output_over_budget": (reply(DIRECT, usage=SimpleNamespace(input_tokens=100, output_tokens=8001, total_tokens=8101, output_tokens_details=None)), "output_budget_exceeded"),
    "input_over_limit": (reply(DIRECT, usage=SimpleNamespace(input_tokens=5001, output_tokens=100, total_tokens=5101, output_tokens_details=None)), "input_budget_exceeded"),
}
# An answer that came back complete is kept although the run stops; a failed one is an error.
ANSWER_KEPT = {"usage_missing", "usage_partial", "output_over_budget", "input_over_limit"}


def run_until(tmp_path, bad, at, output=DIRECT):
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True), sdk_client=ScriptedSDK(output, bad, at))
    code = run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client)
    folder = next(tmp_path.iterdir())
    report = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    lines = [json.loads(line) for line in (folder / "outputs.jsonl").read_text(encoding="utf-8").splitlines()]
    return code, client, report, lines


@pytest.mark.parametrize("name", FAILURES)
@pytest.mark.parametrize("at, system, case_id", [(1, "fair", "CX-01"), (2, "direct", "CX-01"), (7, "fair", "CX-04"), (24, "direct", "CX-12")])
def test_the_first_failure_sends_nothing_further_and_keeps_what_finished(tmp_path, name, at, system, case_id):
    bad, reason = FAILURES[name]
    code, client, report, lines = run_until(tmp_path, bad, at)

    assert code == 1
    assert len(client._sdk.calls) == at == client.usage_totals["requests"]
    assert report["stopped_on"] == reason
    assert report["stop_detail"]["case_id"] == case_id and report["stop_detail"]["system"] == system and report["stop_detail"]["request_number"] == at
    assert report["stop_detail"]["detail"]
    assert report["requests_by_system"] == {"fair": (at + 1) // 2, "direct": at // 2}

    assert len(lines) == 24
    assert all(r["answer"]["status"] == "ok" and r["requests_sent"] == 1 for r in lines[: at - 1])
    assert lines[at - 1]["answer"]["status"] == ("ok" if name in ANSWER_KEPT else "error")
    assert all(r["meta"]["status"] == "not_run" and r["requests_sent"] == 0 for r in lines[at:])
    assert report["results"]["fair"]["cases"] == 12 == report["results"]["direct"]["cases"]


def test_a_stop_saves_the_raw_output_and_the_tokens_of_the_request_that_breached(tmp_path):
    over = SimpleNamespace(input_tokens=100, output_tokens=8001, total_tokens=8101, output_tokens_details=None)
    _, _, report, lines = run_until(tmp_path, reply(DIRECT, usage=over), 2)
    assert lines[1]["raw_output"] == DIRECT and lines[1]["tokens"]["output_tokens"] == 8001
    assert report["token_usage"]["output_tokens"] == 100 + 8001
    assert report["cases_answered_by_both"] == ["CX-01"]
    assert report["cases_not_run"] == [c["case_id"] for c in INPUTS[1:]]


def test_a_failure_does_not_reuse_the_tokens_of_the_request_before_it(tmp_path):
    _, _, _, lines = run_until(tmp_path, FAILURES["timeout"][0], 2)
    assert lines[0]["tokens"]["input_tokens"] == 100 and lines[1]["tokens"] == {}


def test_a_fair_answer_with_an_unreadable_claim_stops_the_run(tmp_path):
    fair = json.dumps({"verdict": "UNKNOWN", "verdict_evidence": None, "explanation": {"en": "x", "ar": "س"}, "extraction": {}, "claims": [{"unexpected": True}]})
    code, client, report, lines = run_until(tmp_path, reply(fair), 1)
    assert code == 1 and len(client._sdk.calls) == 1
    assert report["stopped_on"] == "malformed_response" and "claim" in report["stop_detail"]["detail"]
    assert lines[0]["answer"]["status"] == "ok"


def test_a_request_slower_than_the_timeout_stops_the_run(tmp_path):
    client = fake_client(timeout_seconds=0.001)
    create = client._sdk.responses.create
    client._sdk.responses.create = lambda **kw: (time.sleep(0.02), create(**kw))[1]
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 1
    report = json.loads((next(tmp_path.iterdir()) / "summary.json").read_text(encoding="utf-8"))
    assert report["stopped_on"] == "timeout_exceeded" and len(client._sdk.calls) == 1


def test_a_wrong_verdict_is_a_result_and_never_stops_the_run(tmp_path):
    wrong = json.dumps({"verdict": "CONTRADICTION", "quotes": ["This sentence is not in the offer."], "total_12_months": "999"})
    code, client, report, _ = run_until(tmp_path, reply(wrong), 2)
    assert code == 0 and report["stopped_on"] is None and len(client._sdk.calls) == 24


def test_a_clean_run_reports_twelve_requests_per_system(tmp_path):
    code, client, report, lines = run_until(tmp_path, None, None)
    assert code == 0 and len(client._sdk.calls) == 24
    assert report["requests_by_system"] == {"fair": 12, "direct": 12}
    assert report["stop_detail"] is None and report["cases_not_run"] == []
    assert all(k["max_output_tokens"] == 8000 for k in client._sdk.calls)


def test_each_system_stops_at_its_own_cap():
    client = fake_client()
    cases = [dict(INPUTS[0], case_id=f"C{i}") for i in range(13)]
    records, stopped = run_comparison.run_all(client, cases)
    assert len(client._sdk.calls) == 24
    assert stopped["reason"] == "system_request_limit" and stopped["system"] == "fair" and stopped["case_id"] == "C12"
    assert [r["meta"]["status"] for r in records[-2:]] == ["not_run", "not_run"]


def test_a_call_that_sends_two_requests_stops_the_run(monkeypatch):
    client = fake_client()
    real = run_comparison.CALLS["fair"]

    def double(client, case):
        client.generate("a", "b")
        return real(client, case)

    monkeypatch.setitem(run_comparison.CALLS, "fair", double)
    records, stopped = run_comparison.run_all(client, INPUTS)
    assert stopped["reason"] == "unexpected_request_count" and len(client._sdk.calls) == 2


def test_the_global_cap_is_enforced_by_the_client_and_stops_the_run():
    client = fake_client()
    client.max_requests = 3
    _, stopped = run_comparison.run_all(client, INPUTS)
    assert stopped["reason"] == "request_limit_reached" and len(client._sdk.calls) == 3


def test_the_run_sets_the_global_cap(tmp_path):
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 0
    assert client.max_requests == 24


def test_run_refuses_more_cases_than_the_cap_before_any_call(tmp_path, monkeypatch):
    monkeypatch.setattr(run_comparison, "MAX_REQUESTS_PER_SYSTEM", 11)
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 2
    assert client._sdk.calls == []


def test_run_refuses_a_larger_output_budget_before_any_call(tmp_path):
    client = fake_client(max_output_tokens=8001)
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 2
    assert client._sdk.calls == []


def test_run_refuses_input_estimated_above_the_limit_before_any_call(tmp_path, monkeypatch):
    monkeypatch.setattr(run_comparison, "MAX_INPUT_CHARS", 500)
    client = fake_client()
    assert run_comparison.main(args(tmp_path, "--gold", str(V2_GOLD_PATH), "--allow-draft-gold", "--confirm-paid-calls"), client) == 2
    assert client._sdk.calls == []


def test_the_real_cases_are_within_the_input_estimate():
    from app.prompts import INSTRUCTIONS, build_input
    assert all(len(INSTRUCTIONS) + len(build_input(c["terms"], c["expectation"])) <= run_comparison.MAX_INPUT_CHARS for c in INPUTS)


def test_the_real_sdk_client_is_built_with_no_retries_and_the_timeout(monkeypatch):
    built = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: built.update(kw))
    MetaClient(Settings(api_key="k", live_calls_enabled=True))._client()
    assert built["max_retries"] == 0 and built["timeout"] == 45
