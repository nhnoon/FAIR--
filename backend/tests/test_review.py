"""The blind form and the label record. Fake reviewer answers only: no real review is in this file."""

import json
import re

import pytest

from app.prompts import INSTRUCTIONS
from evaluation import review
from evaluation.challenge import V2_GOLD_PATH, V2_INPUTS_PATH, file_sha256, load_gold, load_inputs

CASES = load_inputs(V2_INPUTS_PATH)
GOLD = load_gold(V2_GOLD_PATH)
FORM = review.build_form()
SHA = file_sha256(V2_INPUTS_PATH)


def visible_cases():
    return json.loads(re.search(r"var CASES = (\[.*?\]);\n", FORM, re.S)[1].replace("<\\/", "</"))


def test_the_form_holds_only_the_allowed_fields_for_every_case():
    shown = visible_cases()
    assert [set(c) for c in shown] == [{"case_id", "language", "terms", "expectation"}] * 12
    assert [(c["terms"], c["expectation"]) for c in shown] == [(c["terms"], c["expectation"]) for c in CASES]


def test_the_form_reveals_no_labels_purposes_or_rules():
    for gold in GOLD.values():
        for secret in (gold["rationale"], gold["focus"], gold["ambiguity"]):
            assert secret not in FORM
    for word in ("FAIR", "Muse", "Meta", "Prompt", "prompt", "gold", "draft", "trap", "baseline", "model", "AI model", "accepted_evidence", "false reassurance"):
        assert word not in FORM, word
    assert INSTRUCTIONS[:80] not in FORM
    assert "fetch(" not in FORM and "http" not in FORM  # it cannot send answers anywhere


def test_the_form_defines_all_three_answers_in_both_languages_without_filling_any():
    for text in ("MATCH", "CONTRADICTION", "UNKNOWN", "متوافق", "تعارض", "غير محسوم"):
        assert text in FORM
    assert "checked" not in FORM.split("<script>")[0]


QUICK = review.build_quick_form()


def test_quick_form_shows_only_offer_and_belief_and_reveals_no_labels():
    shown = json.loads(re.search(r"var CASES = (\[.*?\]);\n", QUICK, re.S)[1].replace("<\\/", "</"))
    assert [set(c) for c in shown] == [{"case_id", "terms", "expectation"}] * 12
    assert [(c["terms"], c["expectation"]) for c in shown] == [(c["terms"], c["expectation"]) for c in CASES]
    for gold in GOLD.values():
        for secret in (gold["rationale"], gold["focus"], gold["ambiguity"]):
            assert secret not in QUICK
    assert "fetch(" not in QUICK and "http" not in QUICK


def test_quick_form_marks_its_results_and_never_verifies_money():
    for text in ('review_type: "owner_reviewed"', "independently_validated: false", '"not_answered"', '"owner_entered_unverified"', '["UNSURE", "UNSURE"'):
        assert text in QUICK
    assert "verified" not in QUICK.replace("unverified", "").replace("not verified", "")


@pytest.mark.parametrize("review_type", ["owner_reviewed", "ai_assisted_owner_review"])
def test_an_owner_review_is_refused_as_an_independent_one(tmp_path, review_type):
    owner = tmp_path / "owner.json"
    owner.write_text(json.dumps({"review_type": review_type, "independently_validated": False, "inputs_sha256": SHA, "reviewer_code": "A", "answers": answers()}), encoding="utf-8")
    with pytest.raises(ValueError, match="owner review"):
        review.compare([owner, write(tmp_path, "B", answers())], tmp_path / "out")


def answers(verdict="UNKNOWN", **extra):
    base = {"verdict": verdict, "quote": "", "recurring_price": "10", "intro_price": "", "billing_period": "monthly", "one_time_fees": "", "total_status": "no", "total_amount": ""}
    return {c["case_id"]: {**base, **extra} for c in CASES}


def write(tmp_path, code, data, sha=SHA):
    path = tmp_path / f"in_{code}.json"
    path.write_text(json.dumps({"form": "offer-review-v2", "inputs_sha256": sha, "reviewer_code": code, "answers": data}, ensure_ascii=False), encoding="utf-8")
    return path


def test_full_agreement_needs_no_decisions_and_the_draft_stays_unchanged(tmp_path):
    before = file_sha256(V2_GOLD_PATH)
    folder = tmp_path / "out"
    report = review.compare([write(tmp_path, "A", answers()), write(tmp_path, "B", answers())], folder)
    assert report["verdict_agreement"]["same"] == 12 and report["disputed_cases"] == []
    target = review.finalize(folder, folder / review.RECORD_NAME)
    labels = json.loads(target.read_text(encoding="utf-8"))
    assert labels["provenance"]["independent_review"] is True and labels["provenance"]["decided_by_a_person"] == 0
    assert labels["annotations"][0]["cost"] == {"recurring_price": 10, "billing_period": "monthly", "intro_price": None, "one_time_fees": [], "total_12_months": None}
    assert load_gold(target)["CX-01"]["verdict"] == "UNKNOWN"
    assert file_sha256(V2_GOLD_PATH) == before


def test_a_disagreement_is_never_decided_by_this_code(tmp_path):
    a, b = answers(), answers()
    a["CX-02"]["verdict"], b["CX-02"]["verdict"] = "UNKNOWN", "CONTRADICTION"
    folder = tmp_path / "out"
    report = review.compare([write(tmp_path, "A", a), write(tmp_path, "B", b)], folder)
    assert report["disputed_cases"] == ["CX-02"] and report["verdict_agreement"]["same"] == 11
    record = folder / review.RECORD_NAME
    with pytest.raises(ValueError, match="not decided"):
        review.finalize(folder, record)
    assert not (folder / review.LABELS_NAME).exists()


@pytest.mark.parametrize("method, contested", [("discussion", False), ("third_reviewer", True)])
def test_a_persons_decision_is_kept_and_a_third_reviewer_marks_it_contested(tmp_path, method, contested):
    a, b = answers(), answers()
    a["CX-02"]["verdict"], b["CX-02"]["verdict"] = "UNKNOWN", "MATCH"
    b["CX-02"]["quote"] = "No contracts."
    folder = tmp_path / "out"
    review.compare([write(tmp_path, "A", a), write(tmp_path, "B", b)], folder)
    path = folder / review.RECORD_NAME
    record = json.loads(path.read_text(encoding="utf-8"))
    for item in record["items"]:
        item.update(decision="UNKNOWN", method=method, decided_by="reviewer C", reason="the offer does not address it")
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    labels = json.loads(review.finalize(folder, path).read_text(encoding="utf-8"))
    case = next(x for x in labels["annotations"] if x["case_id"] == "CX-02")
    assert case["verdict"] == "UNKNOWN" and case["contested"] is contested and case["accepted_evidence"] == []


def test_originals_are_kept_with_hashes_and_tampering_is_caught(tmp_path):
    folder = tmp_path / "out"
    a_path = write(tmp_path, "A", answers())
    report = review.compare([a_path, write(tmp_path, "B", answers())], folder)
    kept = folder / "originals" / "reviewer_A.json"
    assert kept.read_bytes() == a_path.read_bytes() and report["reviewers"][0]["sha256"]
    kept.write_text(kept.read_text(encoding="utf-8").replace("UNKNOWN", "MATCH"), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        review.finalize(folder, folder / review.RECORD_NAME)


def test_a_comparison_never_overwrites_an_earlier_one(tmp_path):
    folder = tmp_path / "out"
    paths = [write(tmp_path, "A", answers()), write(tmp_path, "B", answers())]
    review.compare(paths, folder)
    with pytest.raises(ValueError, match="never overwritten"):
        review.compare(paths, folder)


def test_a_quote_not_in_the_terms_goes_to_a_person(tmp_path):
    a, b = answers("CONTRADICTION", quote="Not in the offer at all."), answers("CONTRADICTION", quote="Not in the offer at all.")
    folder = tmp_path / "out"
    report = review.compare([write(tmp_path, "A", a), write(tmp_path, "B", b)], folder)
    assert len(report["disputed_cases"]) == 12 and report["agreed"]["CX-01"]["accepted_evidence"] == []


def test_files_from_other_cases_incomplete_or_same_code_are_refused(tmp_path):
    good = write(tmp_path, "A", answers())
    with pytest.raises(ValueError, match="different cases"):
        review.compare([good, write(tmp_path, "B", answers(), sha="0" * 64)], tmp_path / "x")
    short = answers()
    short.pop("CX-01")
    with pytest.raises(ValueError, match="exactly"):
        review.compare([good, write(tmp_path, "B", short)], tmp_path / "y")
    with pytest.raises(ValueError, match="same reviewer"):
        review.compare([good, good], tmp_path / "z")


def test_two_reviewers_unsure_about_a_total_go_to_a_person_not_to_no_total(tmp_path):
    a, b = answers(), answers()
    a["CX-05"]["total_status"] = b["CX-05"]["total_status"] = "unsure"
    folder = tmp_path / "out"
    assert review.compare([write(tmp_path, "A", a), write(tmp_path, "B", b)], folder)["disputed_cases"] == ["CX-05"]
    with pytest.raises(ValueError, match="not decided"):
        review.finalize(folder, folder / review.RECORD_NAME)


def test_an_answer_the_reviewer_could_not_give_goes_to_a_person(tmp_path):
    a, b = answers(), answers()
    a["CX-07"]["verdict"] = b["CX-07"]["verdict"] = "CANNOT_REVIEW"
    report = review.compare([write(tmp_path, "A", a), write(tmp_path, "B", b)], tmp_path / "out")
    assert report["disputed_cases"] == ["CX-07"]
