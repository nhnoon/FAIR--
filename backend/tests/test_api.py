import json

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_meta_client
from app.meta_client import MetaClient
from tests.conftest import FakeSDK
from tests.test_analyzer import TERMS, model_output

VALID = {"terms": TERMS, "expectation": "It is free forever.", "language": "en"}


@pytest.fixture
def client():
    from app.main import get_rate_limiter
    from app.ratelimit import RateLimiter

    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(0, 0)  # limits tested separately
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def use_fake(sdk, settings=None):
    settings = settings or Settings(api_key="test-key-not-real", live_calls_enabled=True)
    app.dependency_overrides[get_meta_client] = lambda: MetaClient(settings, sdk_client=sdk)


def test_health_ok_without_key(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "model": "muse-spark-1.3", "base_url": "https://api.meta.ai/v1",
                    "model_configured": False, "live_calls_enabled": False}


def test_health_never_exposes_key(client, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "super-secret-123")
    r = client.get("/api/health")
    assert r.json()["model_configured"] is True
    assert "super-secret-123" not in r.text


def test_analyze_without_key_returns_config_error(client):
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "model_not_configured"


def test_analyze_with_key_but_live_disabled_returns_config_error(client, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "super-secret-123")
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "live_calls_disabled"
    assert "super-secret-123" not in r.text


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"expectation": "x"}, "terms"),
        ({"terms": "x"}, "expectation"),
        ({"terms": "   ", "expectation": "x"}, "terms"),
        ({"terms": "x", "expectation": ""}, "expectation"),
        ({"terms": "x" * 20_001, "expectation": "x"}, "terms"),
        ({"terms": "x", "expectation": "x" * 2_001}, "expectation"),
        ({"terms": "x", "expectation": "x", "language": "fr"}, "language"),
        ({"terms": "x", "expectation": "x", "extra": 1}, "extra"),
        ({"terms": 123, "expectation": "x"}, "terms"),
    ],
)
def test_invalid_input_returns_422(client, payload, field):
    sdk = FakeSDK(output_text="{}")
    use_fake(sdk)
    r = client.post("/api/analyze", json=payload)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_request"
    assert any(d["field"].startswith(field) for d in err["details"])
    assert sdk.calls == []  # invalid input never reaches the model


def test_non_json_body_returns_422(client):
    r = client.post("/api/analyze", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_analyze_success_with_mocked_model(client):
    sdk = FakeSDK(output_text=json.dumps(model_output()))
    use_fake(sdk)
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "CONTRADICTION"
    assert body["verdict_evidence"]["verified"] is True
    assert body["cost"]["projections"][2]["total"] == "154.00"  # Decimal serialised as string
    assert body["model"] == "muse-spark-1.3"
    assert len(sdk.calls) == 1


def test_arabic_ui_language_accepted(client):
    use_fake(FakeSDK(output_text=json.dumps(model_output())))
    r = client.post("/api/analyze", json={**VALID, "language": "ar"})
    assert r.status_code == 200


_REQ = httpx.Request("POST", "https://api.meta.ai/v1/responses")


@pytest.mark.parametrize(
    "exc, status, code",
    [
        (openai.AuthenticationError("x", response=httpx.Response(401, request=_REQ), body=None), 502, "model_auth_failed"),
        (openai.RateLimitError("x", response=httpx.Response(429, request=_REQ), body=None), 503, "model_rate_limited"),
        (openai.InternalServerError("x", response=httpx.Response(500, request=_REQ), body=None), 502, "model_unavailable"),
        (openai.APITimeoutError(request=_REQ), 504, "model_timeout"),
        (openai.APIConnectionError(request=_REQ), 502, "model_unavailable"),
    ],
)
def test_upstream_failures_return_clear_errors(client, exc, status, code):
    use_fake(FakeSDK(exc=exc))
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    assert "test-key-not-real" not in r.text


def test_invalid_model_json_returns_502(client):
    use_fake(FakeSDK(output_text="Sorry, I cannot help."))
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "model_invalid_response"


def test_unexpected_exception_returns_generic_500(client):
    class Boom:
        responses = type("R", (), {"create": staticmethod(lambda **_: (_ for _ in ()).throw(RuntimeError("secret detail")))})

    use_fake(Boom())
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in r.text


def test_route_returns_deadline_fields_and_sends_budget_once(client):
    terms = ("Start with a 7-day free trial. Then USD 9.99 per month, renews automatically until you cancel. "
             "To avoid being charged, cancel at least 48 hours before the trial ends.")
    quote = "To avoid being charged, cancel at least 48 hours before the trial ends."
    price = "Then USD 9.99 per month, renews automatically until you cancel."
    output = {
        "extraction": {
            "currency": {"value": "USD", "evidence": price},
            "trial_days": {"value": 7, "evidence": "Start with a 7-day free trial."},
            "recurring_price": {"value": "9.99", "evidence": price},
            "billing_period": {"value": "monthly", "evidence": price},
            "auto_renewal": {"value": "yes", "evidence": price},
            "cancel_by": {"value": "trial_end", "evidence": quote},
            "cancel_notice": {"value": {"amount": 48, "unit": "hours"}, "evidence": quote},
        },
        "verdict": "UNKNOWN",
        "explanation": {"en": "x", "ar": "س"},
    }
    sdk = FakeSDK(output_text=json.dumps(output, ensure_ascii=False))
    use_fake(sdk)
    r = client.post("/api/analyze", json={"terms": terms, "expectation": "Can I cancel?", "language": "en"})
    assert r.status_code == 200
    assert len(sdk.calls) == 1 and sdk.calls[0]["max_output_tokens"] == 8000
    deadline = r.json()["decision"]["cancel_path"]["deadline"]
    assert (deadline["day"], deadline["last_safe_hour"]) == (7, 120)


def test_truncated_model_response_is_a_clean_error_not_a_result(client):
    from types import SimpleNamespace

    response = SimpleNamespace(output_text='{"verdict": "MATCH"', status="incomplete",
                               incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    use_fake(SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response)))
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "model_invalid_response"
