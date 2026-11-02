"""Replay mode: saved outputs through the real route, clearly labelled, with no way to reach a model."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from scripts.demo_replay import OUTPUTS_PATH, REPLAY_MODEL, configure

FIXTURE = json.loads(OUTPUTS_PATH.read_text(encoding="utf-8"))
OUTPUTS = {o["case_id"]: o for o in FIXTURE["outputs"]}


@pytest.fixture
def client():
    configure(app)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def post(client, terms, expectation):
    return client.post("/api/analyze", json={"terms": terms, "expectation": expectation, "language": "en"})


def test_fixture_is_exact_prompt_v5_output():
    assert FIXTURE["prompt_version"] == "v5"
    for o in FIXTURE["outputs"]:
        assert hashlib.sha256(o["raw_output"].encode("utf-8")).hexdigest() == o["raw_output_sha256"]


def test_health_reports_replay_so_the_ui_cannot_show_live(client):
    body = client.get("/api/health").json()
    assert body["model"] == REPLAY_MODEL and REPLAY_MODEL.startswith("replay:")


@pytest.mark.parametrize(
    "case_id, verdict, totals",
    [("FAIR-011", "CONTRADICTION", ["19.99", "59.97", "239.88"]), ("FAIR-026", "CONTRADICTION", ["69", "207", "828"]), ("FAIR-012", "UNKNOWN", ["9.99", "49.97", "229.88"])],
)
def test_saved_cases_answer_with_a_replay_model_name(client, case_id, verdict, totals):
    o = OUTPUTS[case_id]
    r = post(client, o["terms"], o["expectation"])
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == REPLAY_MODEL
    assert body["claims_summary"]["overall"] == verdict
    assert [h["total"] for h in body["decision"]["continue_path"]["horizons"]] == totals


def test_any_other_input_is_an_error_not_a_result(client):
    r = post(client, "Some other offer costs USD 5/month.", "It is cheap.")
    assert r.status_code == 502 and "verdict" not in r.json()
