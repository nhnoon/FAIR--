"""Offline tests for the evaluation runner. The model is always a mock here."""

import json
import socket

import httpx
import openai
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.meta_client import MetaClient, ModelAuthError, ModelUnavailableError, RequestLimitError
from evaluation import run_eval
from evaluation.fair_bench import (
    DATASET_PATH,
    DATASET_SHA256,
    OVERLAY_PATH,
    CaseResult,
    NoPredictionsError,
    audit_dataset,
    classification_metrics,
    compute_metrics,
    extraction_checks,
    file_sha256,
    load_cases,
    load_overlay,
    render_report,
    run_cases,
    save_run,
    select_cases,
    select_split,
)
from app.analyzer import analyze
from app.prompts import PROMPT_VERSION, build_input
from app.schemas import AnalyzeRequest
from tests.conftest import FakeSDK

LIVE = Settings(api_key="test-key-not-real", live_calls_enabled=True, model="mock-model")


def mock_output(case, *, label=None, evidence=None, price="gold"):
    """A synthetic model JSON for a case (tests only)."""
    return {
        "extraction": {
            "currency": {"value": case.currency, "evidence": case.terms},
            "trial_days": {"value": int(case.trial_days) if case.trial_days not in ("", "0") else None,
                           "evidence": case.terms},
            "recurring_price": {"value": case.monthly_price or None if price == "gold" else price, "evidence": case.terms},
            "billing_period": {"value": "monthly" if case.monthly_price else "unknown", "evidence": case.terms},
            "auto_renewal": {"value": {"Yes": "yes"}.get(case.auto_renewal, "not_stated"), "evidence": case.terms},
            "one_time_fees": [{"label": "fee", "amount": case.additional_fee, "evidence": case.terms}]
            if case.additional_fee not in ("", "0") else [],
        },
        "verdict": label or case.gold_label,
        "verdict_evidence": case.gold_evidence if evidence is None else evidence,
        "explanation": {"en": "x", "ar": "س"},
    }


def predictor(make_output):
    def predict(case):
        text = json.dumps(make_output(case), ensure_ascii=False)
        client = MetaClient(LIVE, sdk_client=FakeSDK(output_text=text))
        return analyze(AnalyzeRequest(terms=case.terms, expectation=case.expectation), client)
    return predict


@pytest.fixture(scope="module")
def cases():
    return load_cases()


# -------------------------------------------------------------- dataset


def test_dataset_hash_and_splits_are_separate(cases):
    assert file_sha256(DATASET_PATH) == DATASET_SHA256
    dev, val, test = (select_split(cases, s) for s in ("development", "validation", "test"))
    assert (len(dev), len(val), len(test)) == (15, 15, 30)
    ids = [c.case_id for c in dev] + [c.case_id for c in val] + [c.case_id for c in test]
    assert len(ids) == len(set(ids)) == 60


def test_audit_reports_measured_overlap(cases):
    a = audit_dataset(cases)
    assert a["distinct_terms_templates"] == 15
    assert a["test_terms_template_seen_in_dev_or_val"] == "10/30"
    assert a["test_terms_and_expectation_template_seen_in_dev_or_val"] == "5/30"
    assert a["gold_evidence_verbatim"] == "60/60"
    assert set(a["annotation_flags"]) == {"FAIR-014", "FAIR-029", "FAIR-044", "FAIR-059"}


# -------------------------------------------------------------- metrics


def test_classification_metrics_known_values():
    pairs = [("MATCH", "MATCH"), ("MATCH", "UNKNOWN"), ("CONTRADICTION", "CONTRADICTION"), ("UNKNOWN", "UNKNOWN")]
    m = classification_metrics(pairs)
    assert m["accuracy"] == 0.75
    # MATCH: P=1 R=.5 F1=2/3 ; CONTRADICTION: F1=1 ; UNKNOWN: P=.5 R=1 F1=2/3
    assert m["macro_f1"] == pytest.approx((2 / 3 + 1 + 2 / 3) / 3)
    assert m["confusion"]["MATCH"]["UNKNOWN"] == 1


def test_classification_metrics_empty():
    assert classification_metrics([]) == {"n": 0}


def test_extraction_checks_treat_blank_and_zero_consistently(cases):
    c = next(x for x in cases if x.case_id == "FAIR-005")  # missing details: blank price/trial/fee
    ok = {"recurring_price": None, "trial_days": None, "auto_renewal": "not_stated", "one_time_fees": [], "currency": "USD"}
    assert all(extraction_checks(c, ok).values())
    wrong = dict(ok, recurring_price="9.99")
    assert extraction_checks(c, wrong)["recurring_price"] is False


# ------------------------------------------------------------ run loop


def test_perfect_mock_scores_100_percent_on_development(cases):
    dev = select_split(cases, "development")
    results, aborted = run_cases(dev, predictor(mock_output))
    m = compute_metrics(results, dev)
    assert aborted is None
    assert m["coverage"] == {"n_cases": 15, "n_predictions": 15, "n_errors": 0, "error_codes": {}}
    assert m["classification"]["accuracy"] == 1.0
    assert m["classification"]["macro_f1"] == 1.0
    assert m["evidence"]["decisive_with_verified_quote_rate"] == 1.0
    assert m["evidence"]["downgraded_to_unknown_rate"] == 0.0
    assert m["evidence"]["verified_quote_overlaps_gold_rate"] == 1.0
    assert m["extraction"]["field_accuracy"]["recurring_price"] == 1.0
    assert m["extraction"]["field_accuracy"]["one_time_fee_total"] == 1.0
    assert set(m["per_language"]) == {"English"}


def test_fabricated_evidence_is_downgraded_and_scored_as_unknown(cases):
    dev = select_split(cases, "development")
    results, _ = run_cases(dev, predictor(lambda c: mock_output(c, evidence="This sentence is not in the terms.")))
    m = compute_metrics(results, dev)
    # Every decisive verdict loses its support -> UNKNOWN. Only gold-UNKNOWN cases stay correct.
    assert all(r.predicted == "UNKNOWN" for r in results)
    assert m["classification"]["accuracy"] == pytest.approx(5 / 15)
    assert m["evidence"]["decisive_with_verified_quote_rate"] == 0.0
    assert m["evidence"]["downgraded_to_unknown_rate"] == pytest.approx(10 / 15)


def test_invented_price_counts_against_extraction_not_classification(cases):
    dev = select_split(cases, "development")
    results, _ = run_cases(dev, predictor(lambda c: mock_output(c, price="123.45")))
    m = compute_metrics(results, dev)
    assert m["classification"]["accuracy"] == 1.0
    assert m["extraction"]["field_accuracy"]["recurring_price"] < 1.0
    assert m["evidence"]["rejected_claims_rate"] > 0


def test_failed_calls_are_errors_not_scores(cases):
    dev = select_split(cases, "development")
    good = predictor(mock_output)

    def flaky(case):
        if case.case_id in ("FAIR-001", "FAIR-002"):
            raise ModelUnavailableError("down")
        return good(case)

    results, aborted = run_cases(dev, flaky)
    m = compute_metrics(results, dev)
    assert aborted is None
    assert m["coverage"]["n_predictions"] == 13 and m["coverage"]["n_errors"] == 2
    assert m["coverage"]["error_codes"] == {"model_unavailable": 2}
    assert m["classification"]["n"] == 13 and m["classification"]["accuracy"] == 1.0
    assert m["strict_accuracy_errors_count_as_wrong"] == pytest.approx(13 / 15)
    assert all(r.predicted is None for r in results if r.status == "error")


def test_fatal_error_aborts_immediately(cases):
    calls = []

    def bad_key(case):
        calls.append(case.case_id)
        raise ModelAuthError("401")

    results, aborted = run_cases(select_split(cases, "development"), bad_key)
    assert len(calls) == 1 and "model_auth_failed" in aborted


def test_consecutive_errors_abort(cases):
    def down(case):
        raise ModelUnavailableError("down")

    results, aborted = run_cases(select_split(cases, "development"), down)
    assert len(results) == 5 and "consecutive" in aborted


# -------------------------------------------------------------- saving


def _manifest():
    return {"split": "development", "model": "mock-model", "prompt_version": "v1",
            "dataset_sha256": DATASET_SHA256, "started_at": "2026-10-30T00:00:00Z",
            "finished_at": "2026-10-30T00:01:00Z", "aborted": None}


def test_no_predictions_means_nothing_saved(tmp_path):
    results = [CaseResult("FAIR-001", "Development", "English", "Free Trial", "MATCH", "error", "model_timeout")]
    with pytest.raises(NoPredictionsError):
        save_run(tmp_path, _manifest(), results, {})
    assert list(tmp_path.iterdir()) == []


def test_save_run_writes_reproducible_artifacts(tmp_path, cases):
    dev = select_split(cases, "development")[:3]
    results, _ = run_cases(dev, predictor(mock_output))
    run_dir = save_run(tmp_path, _manifest(), results, compute_metrics(results, dev))
    assert {p.name for p in run_dir.iterdir()} == {"manifest.json", "predictions.jsonl", "metrics.json", "report.md"}
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["dataset_sha256"] == DATASET_SHA256
    assert len((run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Limitations" in report and "synthetic" in report


# ------------------------------------------------------------------ CLI


def test_cli_refuses_test_split_without_confirmation(tmp_path):
    rc = run_eval.main(["run", "--split", "test", "--confirm-paid-calls", "--out", str(tmp_path)],
                       client=MetaClient(LIVE, sdk_client=FakeSDK(output_text="{}")))
    assert rc == 2 and list(tmp_path.iterdir()) == []


def test_cli_refuses_without_paid_call_confirmation(tmp_path):
    sdk = FakeSDK(output_text="{}")
    rc = run_eval.main(["run", "--split", "development", "--out", str(tmp_path)], client=MetaClient(LIVE, sdk_client=sdk))
    assert rc == 2 and sdk.calls == [] and list(tmp_path.iterdir()) == []


def test_cli_without_key_makes_no_calls_and_writes_nothing(tmp_path):
    rc = run_eval.main(["run", "--split", "development", "--confirm-paid-calls", "--out", str(tmp_path)])
    assert rc == 2 and list(tmp_path.iterdir()) == []


def test_cli_end_to_end_with_mock_client(tmp_path, cases):
    by_terms = {c.terms: c for c in cases}

    class EchoSDK(FakeSDK):
        def _create(self, **kwargs):
            self.calls.append(kwargs)
            terms = json.loads(kwargs["input"].split("\n")[1])
            from types import SimpleNamespace
            return SimpleNamespace(output_text=json.dumps(mock_output(by_terms[terms]), ensure_ascii=False))

    sdk = EchoSDK()
    rc = run_eval.main(["run", "--split", "validation", "--limit", "4", "--confirm-paid-calls", "--out", str(tmp_path)],
                       client=MetaClient(LIVE, sdk_client=sdk))
    assert rc == 0 and len(sdk.calls) == 4
    (run_dir,) = tmp_path.iterdir()
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["coverage"]["n_predictions"] == 4
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["split"] == "validation"


def test_cli_audit_runs_offline(capsys):
    assert run_eval.main(["audit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dataset_sha256_matches_expected"] is True


# ---------------------------------------------- Phase 9: selection, usage, displayed verdict


class ReplaySDK(FakeSDK):
    """Answers each case with its own mock output and reports token usage."""

    def __init__(self, cases_by_expectation, claims=None):
        super().__init__()
        self.by_expectation = cases_by_expectation
        self.claims = claims
        self.responses = SimpleNamespace(create=self._reply)

    def _reply(self, **kwargs):
        self.calls.append(kwargs)
        case = next(c for e, c in self.by_expectation.items() if json.dumps(e, ensure_ascii=False) in kwargs["input"])
        output = mock_output(case)
        if self.claims:
            output["claims"] = self.claims
        return SimpleNamespace(
            output_text=json.dumps(output, ensure_ascii=False),
            status="completed",
            usage=SimpleNamespace(input_tokens=100, output_tokens=200, total_tokens=300,
                                  output_tokens_details=SimpleNamespace(reasoning_tokens=150)),
        )


def test_selected_cases_run_with_usage_recorded_and_budget_sent(tmp_path, cases):
    sdk = ReplaySDK({c.expectation: c for c in cases})
    rc = run_eval.main(["run", "--split", "development", "--cases", "FAIR-003,FAIR-005,FAIR-007",
                        "--confirm-paid-calls", "--out", str(tmp_path)], client=MetaClient(LIVE, sdk_client=sdk))
    assert rc == 0
    assert len(sdk.calls) == 3 and all(c["max_output_tokens"] == 8000 for c in sdk.calls)
    run_dir = next(tmp_path.iterdir())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cases"] == "FAIR-003,FAIR-005,FAIR-007" and manifest["max_output_tokens"] == 8000
    assert manifest["token_usage"] == {"requests": 3, "input_tokens": 300, "output_tokens": 600,
                                       "reasoning_tokens": 450, "total_tokens": 900}
    rows = [json.loads(x) for x in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["case_id"] for r in rows] == ["FAIR-003", "FAIR-005", "FAIR-007"]
    assert "Tokens:" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_case_outside_the_split_makes_no_calls(tmp_path, cases):
    sdk = ReplaySDK({c.expectation: c for c in cases})
    rc = run_eval.main(["run", "--split", "development", "--cases", "FAIR-003,FAIR-031",
                        "--confirm-paid-calls", "--out", str(tmp_path)], client=MetaClient(LIVE, sdk_client=sdk))
    assert rc == 2 and sdk.calls == [] and not list(tmp_path.iterdir())


def test_displayed_verdict_is_scored_separately_from_the_top_level_verdict(cases):
    case = next(c for c in cases if c.case_id == "FAIR-001")  # gold CONTRADICTION
    # Top level says CONTRADICTION, but the only claim is unsettled: the UI headline shows UNKNOWN.
    output = mock_output(case)
    output["claims"] = [{"text": "This trial is free forever.", "topic": "trial", "verdict": "UNKNOWN", "explanation": {"en": "x", "ar": "س"}}]
    results, _ = run_cases([case], predictor(lambda _c: output))
    assert (results[0].predicted, results[0].displayed_verdict) == ("CONTRADICTION", "UNKNOWN")
    assert results[0].claims[0]["verdict"] == "UNKNOWN"
    metrics = compute_metrics(results, [case])
    assert metrics["classification"]["accuracy"] == 1.0
    assert metrics["classification_displayed"]["accuracy"] == 0.0
    assert metrics["displayed_differs_from_verdict"] == 1


# ---------------------------------------------- Phase 10: offline dry run, no CLI paid-call path

DRY_RUN_IDS = "FAIR-003,FAIR-005,FAIR-007"
TOKENS = SimpleNamespace(input_tokens=1400, output_tokens=4000, total_tokens=5400,
                         output_tokens_details=SimpleNamespace(reasoning_tokens=3300))


def scripted_client(replies, settings=LIVE):
    """SDK stand-in: each reply is a response object, consumed in order."""
    queue = list(replies)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return queue.pop(0)

    return MetaClient(settings, sdk_client=SimpleNamespace(responses=SimpleNamespace(create=create))), calls


def completed(output):
    return SimpleNamespace(output_text=json.dumps(output, ensure_ascii=False), status="completed", usage=TOKENS)


def predict_with(client):
    return lambda case: analyze(AnalyzeRequest(terms=case.terms, expectation=case.expectation), client)


@pytest.fixture
def three(cases):
    return select_cases(select_split(cases, "development"), DRY_RUN_IDS)


@pytest.fixture
def no_network(monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr("socket.socket.connect", blocked)


def test_select_cases_loads_the_expected_records(three):
    assert [(c.case_id, c.scenario, c.gold_label) for c in three] == [
        ("FAIR-003", "Cancellation", "CONTRADICTION"),
        ("FAIR-005", "Missing Details", "UNKNOWN"),
        ("FAIR-007", "Promotional Price", "MATCH"),
    ]


def test_select_cases_rejects_ids_outside_the_split(cases):
    with pytest.raises(ValueError, match="FAIR-031"):
        select_cases(select_split(cases, "development"), "FAIR-003,FAIR-031")


def test_gold_annotations_never_reach_the_model(three, no_network):
    client, calls = scripted_client([completed(mock_output(c)) for c in three])
    run_cases(three, predict_with(client))
    assert len(calls) == 3
    for case, call in zip(three, calls):
        assert set(call) == {"model", "instructions", "input", "max_output_tokens"}
        assert call["input"] == build_input(case.terms, case.expectation)
        sent = call["instructions"] + call["input"]
        assert case.case_id not in sent and "gold" not in sent.lower()


def test_dry_run_writes_manifest_tokens_and_per_claim_results(tmp_path, three, no_network):
    outputs = [mock_output(c) for c in three]
    outputs[0]["claims"] = [{"text": "I can cancel one hour before renewal.", "topic": "cancellation", "verdict": "CONTRADICTION",
                             "evidence": three[0].gold_evidence, "evidence_role": "contradicts", "explanation": {"en": "x", "ar": "س"}}]
    client, _ = scripted_client([completed(o) for o in outputs])
    results, aborted = run_cases(three, predict_with(client), get_usage=lambda: client.last_usage)
    metrics = compute_metrics(results, three)
    manifest = dict(_manifest(), token_usage=client.usage_totals, synthetic=True)
    run_dir = save_run(tmp_path, manifest, results, metrics)
    assert aborted is None and metrics["classification"]["accuracy"] == 1.0  # by construction: not model accuracy
    assert metrics["tokens"] == {"cases_recorded": 3, "peak_output": 4000, "peak_reasoning": 3300, "peak_total": 5400}
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["token_usage"]["total_tokens"] == 16200
    rows = [json.loads(x) for x in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["claims"][0]["evidence"]["quote"] == three[0].gold_evidence
    assert rows[0]["tokens"]["output_tokens"] == 4000
    assert "test-key-not-real" not in "".join(p.read_text(encoding="utf-8") for p in run_dir.iterdir())


def test_truncated_response_is_an_error_never_a_score(three, no_network):
    full = json.dumps(mock_output(three[0]), ensure_ascii=False)
    truncated = SimpleNamespace(output_text=full, status="incomplete", usage=TOKENS,  # text parses, still rejected
                                incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    client, _ = scripted_client([truncated])
    results, _ = run_cases(three[:1], predict_with(client), get_usage=lambda: client.last_usage)
    m = compute_metrics(results, three[:1])
    assert results[0].status == "error" and results[0].truncated and results[0].predicted is None
    assert results[0].tokens["output_tokens"] == 4000  # billed, so still counted
    assert m["truncated_responses"] == 1 and m["classification"] == {"n": 0}
    assert m["strict_accuracy_errors_count_as_wrong"] == 0.0
    assert m["strict_displayed_accuracy_errors_count_as_wrong"] == 0.0


@pytest.mark.parametrize("text", ["not json", '{"verdict": "MATCH"', '{"verdict": "MAYBE", "explanation": {"en": "x", "ar": "y"}}', "[]"])
def test_malformed_output_is_an_error_never_a_score(three, text, no_network):
    client, _ = scripted_client([SimpleNamespace(output_text=text, status="completed", usage=TOKENS)])
    results, _ = run_cases(three[:1], predict_with(client))
    assert results[0].status == "error" and results[0].error_code == "model_invalid_response" and results[0].predicted is None


def test_a_pipeline_crash_does_not_lose_the_run(three):
    good = predictor(mock_output)

    def crash_once(case):
        if case.case_id == "FAIR-003":
            raise RuntimeError("receipt lines diverged")
        return good(case)

    results, aborted = run_cases(three, crash_once)
    assert aborted is None
    assert [r.status for r in results] == ["error", "ok", "ok"]
    assert (results[0].error_code, results[0].error_message) == ("pipeline_error", "RuntimeError")


def test_missing_evidence_is_not_scored_as_a_correct_decisive_verdict(three, no_network):
    wrong = [dict(mock_output(c), verdict_evidence=None) for c in three]
    client, _ = scripted_client([completed(o) for o in wrong])
    results, _ = run_cases(three, predict_with(client))
    assert [r.predicted for r in results] == ["UNKNOWN", "UNKNOWN", "UNKNOWN"]
    assert [r.predicted == r.gold_label for r in results] == [False, True, False]


def test_each_label_can_be_scored_wrong(three):
    # A scorer that cannot produce a miss proves nothing.
    flip = {"MATCH": "CONTRADICTION", "CONTRADICTION": "UNKNOWN", "UNKNOWN": "MATCH"}


    def wrong(c):
        verdict = flip[c.gold_label]
        role = {"MATCH": "supports", "CONTRADICTION": "contradicts"}.get(verdict)
        out = mock_output(c, label=verdict, evidence=c.terms)
        out["claims"] = [{"text": c.terms, "topic": "other", "verdict": verdict, "evidence": c.terms, "evidence_role": role,
                          "explanation": {"en": "x", "ar": "س"}}]
        return out

    results, _ = run_cases(three, predictor(wrong))
    m = compute_metrics(results, three)
    assert m["classification"]["accuracy"] == 0.0 and m["classification_displayed"]["accuracy"] == 0.0


def test_quote_overlap_for_decisive_gold_ignores_unknown_gold_pointers(three):
    results, _ = run_cases(three, predictor(mock_output))
    m = compute_metrics(results, three)
    assert m["evidence"]["verified_quote_overlaps_gold_rate_decisive_gold_only"] == 1.0


# ---------------------------------------------- Phase 10.1: annotation overlay and offline guard


@pytest.fixture(scope="module")
def overlay(cases):
    return load_overlay(cases)


def by_id(cases, cid):
    return next(c for c in cases if c.case_id == cid)


def test_overlay_covers_exactly_the_documented_rows(cases, overlay):
    assert overlay["version"] == "1.0.0"
    assert file_sha256(DATASET_PATH) == DATASET_SHA256
    promo = {c.case_id for c in cases if c.scenario == "Promotional Price"}
    missing = {c.case_id for c in cases if c.scenario == "Missing Details"}
    entries = overlay["entries"]
    assert {k for k, e in entries.items() if "intro_price" in e.get("prices", {})} == promo
    assert {k for k, e in entries.items() if e.get("exclude_extraction")} == missing
    assert {k for k, e in entries.items() if e.get("evidence", {}).get("mode") == "all_parts"} == {"FAIR-007", "FAIR-022", "FAIR-037", "FAIR-052"}
    assert {k for k, e in entries.items() if e.get("evidence", {}).get("mode") == "any_of"} == {"FAIR-014", "FAIR-029", "FAIR-044", "FAIR-059"}
    assert all(c.gold_evidence in e["evidence"]["passages"] for c in cases for e in [entries.get(c.case_id, {})] if e.get("evidence"))


def test_overlay_does_not_change_gold_labels_or_dataset_loading(cases, overlay):
    before = [(c.case_id, c.gold_label, c.gold_evidence, c.monthly_price) for c in load_cases()]
    load_overlay(cases)
    assert before == [(c.case_id, c.gold_label, c.gold_evidence, c.monthly_price) for c in load_cases()]
    results, _ = run_cases(cases[:3], predictor(mock_output))
    assert compute_metrics(results, cases[:3], overlay)["classification"] == compute_metrics(results, cases[:3])["classification"]


@pytest.mark.parametrize(
    "tamper, message",
    [
        (lambda d: d["corrections"][0].update(gold_label="MATCH"), "unsupported overlay keys"),
        (lambda d: d.update(base_sha256="0" * 64), "different dataset"),
        (lambda d: d["corrections"][1]["evidence"]["passages"].append("Not in the terms at all."), "not verbatim"),
        (lambda d: d["corrections"][0].update(prices={"intro_price": "123.45"}), "not in the terms"),
        (lambda d: d["corrections"][0].update(rationales=[]), "documented rationale"),
        (lambda d: d["corrections"][0].update(rationales=["invented"]), "documented rationale"),
        (lambda d: d["corrections"][-1].update(exclude_extraction=["currency"]), "cannot be excluded"),
        (lambda d: d["corrections"].append(dict(d["corrections"][0])), "duplicate"),
    ],
)
def test_tampered_overlay_is_rejected(tmp_path, cases, tamper, message):
    data = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    tamper(data)
    path = tmp_path / "overlay.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_overlay(cases, path)


def test_ambiguous_price_is_excluded_rather_than_scored_wrong(cases, overlay):
    c = by_id(cases, "FAIR-005")
    extracted = {"recurring_price": "9.99", "trial_days": None, "auto_renewal": "not_stated", "one_time_fees": [], "currency": "USD"}
    assert extraction_checks(c, extracted)["recurring_price"] is False  # base behaviour is unchanged
    checks = extraction_checks(c, extracted, overlay["entries"]["FAIR-005"])
    assert "recurring_price" not in checks and all(checks.values())


def test_intro_recurring_and_one_time_prices_are_scored_separately(cases, overlay):
    c = by_id(cases, "FAIR-007")
    good = {"intro_price": "7.50", "recurring_price": "14.99", "trial_days": None, "auto_renewal": "yes", "one_time_fees": [], "currency": "USD"}
    assert all(extraction_checks(c, good, overlay["entries"]["FAIR-007"]).values())
    swapped = dict(good, intro_price="14.99", recurring_price="7.5")
    checks = extraction_checks(c, swapped, overlay["entries"]["FAIR-007"])
    assert not checks["intro_price"] and not checks["recurring_price"]
    as_fee = dict(good, intro_price=None, one_time_fees=[{"amount": "7.5"}])
    checks = extraction_checks(c, as_fee, overlay["entries"]["FAIR-007"])
    assert not checks["intro_price"] and not checks["one_time_fee_total"]


def _two_part_output(case, top_quote, claim_quotes):
    out = mock_output(case, evidence=top_quote)
    out["claims"] = [{"text": "A stated price.", "topic": "price", "verdict": "MATCH", "evidence": q, "evidence_role": "supports",
                      "explanation": {"en": "x", "ar": "س"}} for q in claim_quotes]
    return out


@pytest.mark.parametrize(
    "top_quote, claim_quotes, base_overlap, accepted, complete",
    [
        ("Introductory month: USD 7.5.", ["Introductory month: USD 7.5."], 0.0, 1.0, 0.0),
        ("From month two: USD 14.99/month.", ["From month two: USD 14.99/month."], 1.0, 1.0, 0.0),
        ("From month two: USD 14.99/month.", ["Introductory month: USD 7.5.", "From month two: USD 14.99/month."], 1.0, 1.0, 1.0),
    ],
)
def test_multi_part_evidence_is_scored_with_either_part_and_complete_only_with_both(cases, overlay, top_quote, claim_quotes, base_overlap, accepted, complete):
    case = by_id(cases, "FAIR-007")
    results, _ = run_cases([case], predictor(lambda c: _two_part_output(c, top_quote, claim_quotes)))
    m = compute_metrics(results, [case], overlay)
    assert m["evidence"]["verified_quote_overlaps_gold_rate"] == base_overlap
    assert m["overlay"]["evidence"]["verified_quote_overlaps_accepted_rate"] == accepted
    assert m["overlay"]["evidence"]["decisive_gold_evidence_complete_rate"] == complete


def test_more_relevant_quote_is_accepted_for_the_renewal_gap_rows(cases, overlay):
    case = by_id(cases, "FAIR-014")
    results, _ = run_cases([case], predictor(lambda c: mock_output(c, evidence="Renewal terms are not stated.")))
    m = compute_metrics(results, [case], overlay)
    assert m["evidence"]["verified_quote_overlaps_gold_rate"] == 0.0
    assert m["overlay"]["evidence"]["verified_quote_overlaps_accepted_rate"] == 1.0


def test_metrics_without_an_overlay_are_backward_compatible(cases):
    results, _ = run_cases(cases[:2], predictor(mock_output))
    assert "overlay" not in compute_metrics(results, cases[:2])
    assert "annotation overlay" not in render_report(_manifest(), compute_metrics(results, cases[:2]))


def test_report_names_the_overlay(cases, overlay):
    results, _ = run_cases(cases[:2], predictor(mock_output))
    assert "annotation overlay 1.0.0" in render_report(_manifest(), compute_metrics(results, cases[:2], overlay))


def test_overlay_never_reaches_the_model(cases, overlay):
    captured = []
    sdk = FakeSDK(output_text=json.dumps(mock_output(by_id(cases, "FAIR-012")), ensure_ascii=False))
    sdk.responses = SimpleNamespace(create=lambda **kw: (captured.append(kw), SimpleNamespace(output_text=sdk._text))[1])
    case = by_id(cases, "FAIR-012")  # its annotated introductory price also appears in the terms
    analyze(AnalyzeRequest(terms=case.terms, expectation=case.expectation), MetaClient(LIVE, sdk_client=sdk))
    assert captured[0]["input"] == build_input(case.terms, case.expectation)
    sent = captured[0]["instructions"] + captured[0]["input"]
    data = OVERLAY_PATH.read_text(encoding="utf-8")
    for key in json.loads(data)["rationales"]:
        assert key not in sent
    app_dir = OVERLAY_PATH.parents[1] / "backend" / "app"
    for source in app_dir.glob("*.py"):  # the application never imports the benchmark or its overlay
        text = source.read_text(encoding="utf-8")
        assert "overlay" not in text.lower() and "fair_bench" not in text


def test_network_guard_blocks_external_connections_but_not_loopback_pairs():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(AssertionError, match="Network access attempted"):
            s.connect(("203.0.113.1", 443))
    with pytest.raises(AssertionError, match="DNS lookup attempted"):
        socket.getaddrinfo("api.meta.ai", 443)
    a, b = socket.socketpair()
    a.close()
    b.close()


def test_cli_manifest_records_the_overlay_with_a_mock_client(tmp_path, cases):
    sdk = ReplaySDK({c.expectation: c for c in cases})
    rc = run_eval.main(["run", "--split", "development", "--cases", "FAIR-005,FAIR-007", "--confirm-paid-calls", "--out", str(tmp_path)],
                       client=MetaClient(LIVE, sdk_client=sdk))
    assert rc == 0
    (run_dir,) = tmp_path.iterdir()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["overlay_version"] == "1.0.0" and len(manifest["overlay_sha256"]) == 64
    assert json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))["overlay"]["cases_corrected"] == 2


# ---------------------------------------------- Phase 11: execution controls, mocks only

SMOKE = ["run", "--split", "development", "--cases", DRY_RUN_IDS, "--max-requests", "3", "--stop-on-anomaly", "--confirm-paid-calls"]
_REQ = httpx.Request("POST", "https://api.meta.ai/v1/responses")


def smoke_client(replies):
    queue, calls = list(replies), []

    def create(**kwargs):
        calls.append(kwargs)
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return MetaClient(LIVE, sdk_client=SimpleNamespace(responses=SimpleNamespace(create=create))), calls


def _bad_claim_output(case):
    return dict(mock_output(case), claims=[{"text": "x", "verdict": "MAYBE", "explanation": {"en": "x", "ar": "س"}}])


def _status(cls, code):
    return cls(f"HTTP {code}", response=httpx.Response(code, request=_REQ), body=None)


FIRST_REPLY_STOPS = {
    "parameter_rejected": lambda c: _status(openai.BadRequestError, 400),
    "rate_limited": lambda c: _status(openai.RateLimitError, 429),
    "auth_failed": lambda c: _status(openai.AuthenticationError, 401),
    "timeout": lambda c: openai.APITimeoutError(request=_REQ),
    "network": lambda c: openai.APIConnectionError(request=_REQ),
    "truncated": lambda c: SimpleNamespace(output_text="{", status="incomplete", usage=TOKENS, incomplete_details=SimpleNamespace(reason="max_output_tokens")),
    "malformed": lambda c: SimpleNamespace(output_text="not json", status="completed", usage=TOKENS),
    "schema": lambda c: SimpleNamespace(output_text='{"verdict": "MAYBE"}', status="completed", usage=TOKENS),
    "dropped_claim": lambda c: completed(_bad_claim_output(c)),
    "no_usage": lambda c: SimpleNamespace(output_text=json.dumps(mock_output(c), ensure_ascii=False), status="completed"),
    "input_anomaly": lambda c: SimpleNamespace(output_text=json.dumps(mock_output(c), ensure_ascii=False), status="completed",
                                               usage=SimpleNamespace(input_tokens=50000, output_tokens=10, total_tokens=50010)),
    "output_anomaly": lambda c: SimpleNamespace(output_text=json.dumps(mock_output(c), ensure_ascii=False), status="completed",
                                                usage=SimpleNamespace(input_tokens=10, output_tokens=9000, total_tokens=9010)),
}


@pytest.mark.parametrize("name", sorted(FIRST_REPLY_STOPS))
def test_smoke_run_stops_after_the_first_bad_request_with_no_retry(tmp_path, three, name):
    reply = FIRST_REPLY_STOPS[name](three[0])
    client, calls = smoke_client([reply, completed(mock_output(three[1])), completed(mock_output(three[2]))])
    assert run_eval.main(SMOKE + ["--out", str(tmp_path)], client=client) == 1
    assert len(calls) == 1  # never retried, never moved on
    assert client.usage_totals["requests"] == 1
    assert list(tmp_path.iterdir())  # the billed attempt is on record either way


def test_smoke_run_keeps_earlier_results_when_a_later_request_fails(tmp_path, three):
    client, calls = smoke_client([completed(mock_output(three[0])), _status(openai.RateLimitError, 429), completed(mock_output(three[2]))])
    assert run_eval.main(SMOKE + ["--out", str(tmp_path)], client=client) == 1
    assert len(calls) == 2
    (run_dir,) = tmp_path.iterdir()
    rows = [json.loads(x) for x in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in rows] == ["ok", "error"] and rows[1]["error_code"] == "model_rate_limited"
    assert "model_rate_limited" in json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["aborted"]


def test_wrong_verdicts_do_not_stop_a_smoke_run(tmp_path, three):
    flip = {"MATCH": "UNKNOWN", "CONTRADICTION": "UNKNOWN", "UNKNOWN": "MATCH"}
    client, calls = smoke_client([completed(mock_output(c, label=flip[c.gold_label], evidence=c.terms)) for c in three])
    assert run_eval.main(SMOKE + ["--out", str(tmp_path)], client=client) == 0
    assert len(calls) == 3


def test_smoke_run_stores_exact_raw_output_tokens_latency_and_prompt_hash(tmp_path, three):
    replies = [completed(mock_output(c)) for c in three]
    replies[0].output_text = "```json\n" + replies[0].output_text + "\n```"  # tolerated when parsed, kept as received
    client, calls = smoke_client(replies)
    assert run_eval.main(SMOKE + ["--out", str(tmp_path)], client=client) == 0
    assert len(calls) == 3 and all(c["max_output_tokens"] == 8000 for c in calls)
    (run_dir,) = tmp_path.iterdir()
    rows = [json.loads(x) for x in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["case_id"] for r in rows] == DRY_RUN_IDS.split(",")
    assert rows[0]["raw_output"] == replies[0].output_text and rows[0]["response_status"] == "completed"
    assert rows[0]["tokens"]["reasoning_tokens"] == 3300 and isinstance(rows[0]["latency_ms"], int)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prompt_version"] == PROMPT_VERSION and len(manifest["prompt_sha256"]) == 64
    assert manifest["max_requests"] == 3 and manifest["stop_on_anomaly"] is True and manifest["token_usage"]["requests"] == 3


@pytest.mark.parametrize(
    "ids, max_requests",
    [("FAIR-003,FAIR-005,FAIR-007,FAIR-001", "3"), ("FAIR-003,FAIR-003", "3"), ("FAIR-003,FAIR-999", "3")],
)
def test_selection_problems_are_refused_before_any_request(tmp_path, ids, max_requests):
    client, calls = smoke_client([])
    rc = run_eval.main(["run", "--split", "development", "--cases", ids, "--max-requests", max_requests, "--confirm-paid-calls", "--out", str(tmp_path)], client=client)
    assert rc == 2 and calls == [] and not list(tmp_path.iterdir())


def test_full_split_is_refused_under_a_three_request_cap(tmp_path):
    client, calls = smoke_client([])
    rc = run_eval.main(["run", "--split", "development", "--max-requests", "3", "--confirm-paid-calls", "--out", str(tmp_path)], client=client)
    assert rc == 2 and calls == []


def test_client_refuses_to_send_past_its_request_limit(three):
    client, calls = smoke_client([completed(mock_output(three[0]))])
    client.max_requests = 1
    client.generate("i", "u")
    with pytest.raises(RequestLimitError):
        client.generate("i", "u")
    assert len(calls) == 1 and client.usage_totals["requests"] == 1


# ---------------------------------------------- Phase 12: the exact command shape, mocks only

DEV_RUN = ["run", "--split", "development", "--max-requests", "15", "--stop-on-anomaly", "--confirm-paid-calls"]


def dev_replies(cases):
    return [completed(mock_output(c)) for c in select_split(cases, "development")]


def test_development_command_runs_each_of_the_15_cases_once_in_order(tmp_path, cases, capsys):
    client, calls = smoke_client(dev_replies(cases))
    assert run_eval.main(DEV_RUN + ["--out", str(tmp_path)], client=client) == 0
    assert len(calls) == 15 and all(c["max_output_tokens"] == 8000 for c in calls)
    (run_dir,) = tmp_path.iterdir()
    rows = [json.loads(x) for x in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["case_id"] for r in rows] == [f"FAIR-{i:03d}" for i in range(1, 16)]
    assert all(r["split"] == "Development" for r in rows)
    for row in rows:
        assert row["started_at"] and row["raw_output"] and row["tokens"]["total_tokens"] == 5400
        assert row["cost"] is not None and row["decision"] is not None and row["rejected_facts"] is not None
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["token_usage"]["requests"] == 15
    log = capsys.readouterr().err
    assert "cumulative requests=1 total_tokens=5400" in log and "cumulative requests=15 total_tokens=81000" in log


def test_development_command_stops_mid_run_and_keeps_partial_results(tmp_path, cases):
    replies = dev_replies(cases)
    replies[6] = openai.APITimeoutError(request=_REQ)
    client, calls = smoke_client(replies)
    assert run_eval.main(DEV_RUN + ["--out", str(tmp_path)], client=client) == 1
    assert len(calls) == 7
    (run_dir,) = tmp_path.iterdir()
    rows = [json.loads(x) for x in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 7 and rows[-1]["error_code"] == "model_timeout" and rows[-1]["started_at"]
    assert "model_timeout" in json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["aborted"]


def test_recording_fields_do_not_change_scores(cases):
    dev = select_split(cases, "development")
    results, _ = run_cases(dev, predictor(mock_output))
    assert compute_metrics(results, dev)["classification"]["accuracy"] == 1.0
