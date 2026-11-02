"""Challenge set and comparison scorer. Offline: hand-written answers only, never a model."""

import inspect
import json
import re

import pytest

from app.evidence import normalize, verify_quote
from app.prompts import INSTRUCTIONS
from evaluation import challenge
from evaluation.challenge import (
    BASELINE_PROMPT,
    GOLD_PATH,
    INPUTS_PATH,
    MANIFEST_PATH,
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
from evaluation.fair_bench import load_cases

INPUTS = load_inputs()
GOLD = load_gold()
BY_ID = {c["case_id"]: c for c in INPUTS}
WORD = re.compile(r"[^\W\d_]+")


def words(text):
    return set(WORD.findall(normalize(text)))


def test_set_size_languages_and_ids():
    assert 8 <= len(INPUTS) <= 12
    assert {c["language"] for c in INPUTS} == {"English", "Arabic", "Mixed"}
    assert [c["case_id"] for c in INPUTS] == sorted(GOLD)


def test_inputs_hold_no_gold_material():
    raw = INPUTS_PATH.read_text(encoding="utf-8")
    for key in ('"verdict"', '"accepted_evidence"', '"rationale"', '"cost"', "MATCH", "CONTRADICTION", "UNKNOWN"):
        assert key not in raw
    for case in INPUTS:
        assert set(case) == {"case_id", "language", "focus", "terms", "expectation"}


def test_gold_is_marked_as_a_draft_and_never_as_independent():
    assert "NOT INDEPENDENT" in json.loads(GOLD_PATH.read_text(encoding="utf-8"))["status"]


def test_only_terms_and_belief_reach_a_model():
    for case in INPUTS:
        sent = BASELINE_PROMPT + baseline_input(case["terms"], case["expectation"])
        assert case["case_id"] not in sent and case["focus"] not in sent
        gold = GOLD[case["case_id"]]
        assert gold["rationale"] not in sent


def test_gold_passages_and_amounts_come_from_the_terms():
    for case in INPUTS:
        gold = GOLD[case["case_id"]]
        assert all(verify_quote(q, case["terms"]).verified for q in gold["accepted_evidence"]), case["case_id"]
        assert bool(gold["accepted_evidence"]) == (gold["verdict"] != "UNKNOWN"), case["case_id"]


def test_label_mix_covers_every_outcome():
    assert {g["verdict"] for g in GOLD.values()} == {"MATCH", "CONTRADICTION", "UNKNOWN"}


def test_cases_are_not_paraphrases_of_the_benchmark():
    bench = load_cases()
    for case in INPUTS:
        for b in bench:
            for mine, theirs in ((case["terms"], b.terms), (case["expectation"], b.expectation)):
                a, c = words(mine), words(theirs)
                assert len(a & c) / max(len(a | c), 1) < 0.5, (case["case_id"], b.case_id)


def test_manifest_freezes_inputs_gold_and_baseline_prompt():
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert m["inputs_sha256"] == file_sha256(INPUTS_PATH)
    assert m["gold_draft_sha256"] == file_sha256(GOLD_PATH)
    assert m["baseline_prompt_sha256"] == prompt_sha256()


def test_baseline_prompt_is_neutral_about_fair_rules():
    for rule in ("untrusted", "promise", "guarantee", "future", "contiguous", "Silence", "never", "absolute"):
        assert rule.lower() not in BASELINE_PROMPT.lower()
    assert BASELINE_PROMPT not in INSTRUCTIONS


def test_this_module_cannot_call_a_model():
    source = inspect.getsource(challenge)
    assert "openai" not in source and "MetaClient" not in source and ".create(" not in source


# ------------------------------------------------------------------ scoring, hand-written answers

CASE, GOLD_CASE = BY_ID["CH-10"], GOLD["CH-10"]
PRICE_RISE = "بعد ذلك يصبح السعر 40 SAR شهريًا."


def good():
    return Normalized(verdict="CONTRADICTION", quotes=[PRICE_RISE], recurring_price="40 SAR", billing_period="monthly", intro_price="25", one_time_fees=[], total_12_months="435")


def test_a_correct_answer_scores_on_every_measure():
    s = score_case(CASE, GOLD_CASE, good())
    assert s["correct"] and s["quote_hits_accepted"] and s["recurring_price_correct"] and s["billing_correct"]
    assert s["intro_price_correct"] and s["fees_correct"] and s["total_correct"]
    assert not s["false_reassurance"] and not s["decisive_without_verbatim_quote"] and s["invented_quotes"] == 0


def test_false_reassurance_is_a_match_on_anything_gold_does_not_match():
    a = good()
    a.verdict = "MATCH"
    s = score_case(CASE, GOLD_CASE, a)
    assert s["false_reassurance"] and not s["correct"]


def test_an_invented_quote_is_counted_and_gives_no_support():
    a = good()
    a.quotes = ["The price is locked at 25 SAR forever."]
    s = score_case(CASE, GOLD_CASE, a)
    assert s["invented_quotes"] == 1 and s["decisive_without_verbatim_quote"] and not s["quote_hits_accepted"]


def test_wrong_arithmetic_is_caught():
    a = good()
    a.total_12_months = "300"
    assert not score_case(CASE, GOLD_CASE, a)["total_correct"]


def test_a_total_where_none_is_established_is_unsupported():
    case, gold = BY_ID["CH-04"], GOLD["CH-04"]
    s = score_case(case, gold, Normalized(verdict="UNKNOWN", recurring_price="20", billing_period="monthly", total_12_months="240"))
    assert s["correct"] and s["total_unsupported"] and not s["total_correct"]
    assert score_case(case, gold, Normalized(verdict="UNKNOWN", recurring_price="20", billing_period="monthly"))["total_correct"]


def test_withholding_an_established_total_is_counted_against_the_system():
    a = good()
    a.total_12_months = None
    assert score_case(CASE, GOLD_CASE, a)["total_withheld_wrongly"]


def test_direct_output_is_read_exactly_and_bad_output_is_an_error():
    text = json.dumps({"verdict": "contradiction", "quotes": [PRICE_RISE], "recurring_price": "40", "billing_period": "monthly", "intro_price": "25", "one_time_fees": [], "total_12_months": "435"}, ensure_ascii=False)
    assert score_case(CASE, GOLD_CASE, normalize_direct(text))["correct"]
    for bad in ("I think it is fine.", '{"verdict": "MAYBE"}', '{"quotes": []}'):
        answer = normalize_direct(bad)
        assert answer.status == "error"
        s = score_case(CASE, GOLD_CASE, answer)
        assert not s["correct"] and not s["total_correct"]


def test_fair_is_scored_on_what_the_user_sees_not_its_top_level_answer():
    response = {
        "verdict": "MATCH",
        "claims_summary": {"overall": "UNKNOWN"},
        "claims": [{"verdict": "UNKNOWN", "evidence": {"quote": "x", "verified": True}}],
        "extracted_terms": {"recurring_price": "40", "billing_period": "monthly", "intro_price": "25", "one_time_fees": []},
        "decision": {"continue_path": {"horizons": [{"months": 12, "status": "conditional", "total": "435"}]}},
    }
    a = normalize_fair(response)
    assert a.verdict == "UNKNOWN" and a.quotes == [] and a.total_12_months == "435"


def test_summary_keeps_denominators_and_counts_errors_as_wrong():
    scores = [score_case(CASE, GOLD_CASE, good()), score_case(BY_ID["CH-12"], GOLD["CH-12"], Normalized(status="error"))]
    m = summarize(scores)
    assert m["cases"] == 2 and m["errors"] == 1
    assert m["verdict_accuracy"] == {"hits": 1, "of": 2, "rate": 0.5}
    assert m["false_reassurance"]["of"] == 2


@pytest.mark.parametrize("case_id", sorted(GOLD))
def test_a_perfect_answer_built_from_gold_scores_fully_on_every_case(case_id):
    case, gold = BY_ID[case_id], GOLD[case_id]
    cost = gold["cost"]
    answer = Normalized(verdict=gold["verdict"], quotes=gold["accepted_evidence"], recurring_price=cost["recurring_price"], billing_period=cost["billing_period"],
                        intro_price=cost["intro_price"], one_time_fees=cost["one_time_fees"], total_12_months=cost["total_12_months"])
    s = score_case(case, gold, answer)
    assert s["correct"] and s["recurring_price_correct"] and s["billing_correct"] and s["fees_correct"] and s["total_correct"]
