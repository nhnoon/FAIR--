"""The frontend's sample-preview fixtures must be exactly what the real pipeline produces."""

import json
from decimal import Decimal

from scripts.build_samples import OUT_PATH, SAMPLE_MODEL_LABEL, build, render


def by_id():
    return {s["id"]: s["response"] for s in build()}


def test_committed_fixture_matches_pipeline_output():
    assert OUT_PATH.exists(), "run: python -m scripts.build_samples"
    assert OUT_PATH.read_text(encoding="utf-8") == render()


def test_samples_never_claim_to_be_meta_output():
    for s in json.loads(render())["samples"]:
        assert s["response"]["model"] == SAMPLE_MODEL_LABEL


def test_evidence_guard_sample_is_downgraded_and_fee_rejected():
    r = by_id()["evidence-guard"]
    assert r["verdict"] == "UNKNOWN" and r["model_verdict"] == "MATCH" and r["verdict_downgraded"]
    assert r["verdict_evidence"]["verified"] is False
    assert r["extracted_terms"]["one_time_fees"] == []
    assert any(f["field"].startswith("one_time_fee") for f in r["rejected_facts"])


def test_sample_costs_come_from_engine():
    trial = by_id()["trial-autorenew"]["cost"]
    assert {p["months"]: Decimal(p["total"]) for p in trial["projections"]} == {
        1: Decimal("14.49"), 3: Decimal("38.47"), 12: Decimal("146.38")}
    missing = by_id()["missing-details"]["cost"]
    assert all(p["status"] == "unavailable" for p in missing["projections"])
    intro = by_id()["intro-price-ar"]["cost"]
    assert all(p["status"] == "conditional" for p in intro["projections"])
    assert all("intro_one_period" in p["assumption_codes"] for p in intro["projections"])


def test_all_sample_verified_offsets_point_into_terms():
    for s in build():
        r = s["response"]
        evidences = [f["evidence"] for f in r["facts"]] + [f["evidence"] for f in r["extracted_terms"]["one_time_fees"]]
        if r["verdict_evidence"]:
            evidences.append(r["verdict_evidence"])
        for e in evidences:
            if e["verified"]:
                assert 0 <= e["start"] < e["end"] <= len(s["terms"])
