"""Replay of the Phase 12 live outputs through today's deterministic pipeline.

These outputs came from prompt v4. A replay tests FAIR's validation code only: it cannot show
how the model behaves with a later prompt, and it does not change what the live run recorded.
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.analyzer import analyze
from app.config import Settings
from app.meta_client import MetaClient
from app.schemas import AnalyzeRequest
from evaluation.fair_bench import load_cases
from tests.conftest import FakeSDK

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "phase12_raw_outputs.json").read_text(encoding="utf-8"))
OUTPUTS = {o["case_id"]: o for o in FIXTURE["outputs"]}
CASES = {c.case_id: c for c in load_cases()}
CHANGED = {"FAIR-011": ("UNKNOWN", "CONTRADICTION"), "FAIR-012": ("MATCH", "UNKNOWN")}


def replay(case_id):
    case = CASES[case_id]
    client = MetaClient(Settings(api_key="k", live_calls_enabled=True, model=FIXTURE["model"]), sdk_client=FakeSDK(output_text=OUTPUTS[case_id]["raw_output"]))
    return analyze(AnalyzeRequest(terms=case.terms, expectation=case.expectation), client)


def test_fixture_is_the_recorded_v4_output():
    assert len(OUTPUTS) == 15
    assert FIXTURE["prompt_version"] == "v4"
    for o in FIXTURE["outputs"]:
        assert hashlib.sha256(o["raw_output"].encode("utf-8")).hexdigest() == o["raw_output_sha256"]


@pytest.mark.parametrize("case_id", sorted(OUTPUTS))
def test_only_the_two_known_verdicts_change(case_id):
    o, r = OUTPUTS[case_id], replay(case_id)
    assert r.verdict == o["recorded_top_verdict"]  # the model's own answer is never rewritten
    before, after = CHANGED.get(case_id, (o["recorded_displayed_verdict"],) * 2)
    assert o["recorded_displayed_verdict"] == before and r.claims_summary.overall == after


@pytest.mark.parametrize("case_id", sorted(OUTPUTS))
def test_prices_billing_and_calculations_are_exactly_as_recorded(case_id):
    o, r = OUTPUTS[case_id], replay(case_id).model_dump(mode="json")
    assert r["extracted_terms"] == o["recorded_extracted"]
    assert r["cost"].pop("withheld") == [] and r["cost"].pop("not_counted") == []  # added after this run
    assert r["cost"] == o["recorded_cost"]
    assert r["decision"] == o["recorded_decision"]


@pytest.mark.parametrize("case_id", sorted(OUTPUTS))
def test_totals_match_the_gold_prices_independently(case_id):
    case, r = CASES[case_id], replay(case_id)
    totals = [h.total for h in r.decision.continue_path.horizons]
    if not case.monthly_price:
        assert totals == [None, None, None]  # no price or billing period, so no projection is invented
        return
    rec, fee = Decimal(case.monthly_price), Decimal(case.additional_fee or "0")
    intro = r.extracted_terms.intro_price
    expected = [(intro + rec * (n - 1) if intro is not None else rec * n) + fee for n in (1, 3, 12)]
    assert totals == expected


@pytest.mark.parametrize("case_id", sorted(OUTPUTS))
def test_cancel_paths_never_claim_certainty(case_id):
    assert replay(case_id).decision.cancel_path.status in ("conditional", "unavailable")


def test_fair_012_is_no_longer_shown_as_a_confirmed_promise():
    c = replay("FAIR-012").claims[0]
    assert (c.verdict, c.model_verdict, c.reason) == ("UNKNOWN", "MATCH", "absolute_claim_unsupported")


def test_fair_011_keeps_the_contradiction_and_its_unsettled_claim():
    r = replay("FAIR-011")
    assert [c.verdict for c in r.claims] == ["UNKNOWN", "CONTRADICTION"] and r.claims_summary.overall == "CONTRADICTION"
