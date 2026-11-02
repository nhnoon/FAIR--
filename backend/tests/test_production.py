"""Production hardening: CORS on all responses, cost-protection limits, body size, config, logs."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, get_meta_client, get_rate_limiter
from app.meta_client import MetaClient
from app.ratelimit import DailyLimitReachedError, RateLimitedError, RateLimiter
from tests.conftest import FakeSDK
from tests.test_analyzer import TERMS, model_output

ORIGIN = "http://localhost:5173"  # in the default CORS allowlist
VALID = {"terms": TERMS, "expectation": "It is free forever.", "language": "en"}


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def use(sdk, limiter=None):
    settings = Settings(api_key="test-key-not-real", live_calls_enabled=True)
    app.dependency_overrides[get_meta_client] = lambda: MetaClient(settings, sdk_client=sdk)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter or RateLimiter(0, 0)


# ---------------------------------------------------------------- limiter unit


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_per_minute_limit_is_per_client_and_slides():
    clock = Clock()
    rl = RateLimiter(per_minute=2, per_day=0, clock=clock)
    rl.check("a")
    rl.check("a")
    with pytest.raises(RateLimitedError):
        rl.check("a")
    rl.check("b")  # other client unaffected
    clock.t = 60.0
    rl.check("a")  # window slid


def test_daily_limit_counts_allowed_requests_and_resets_next_day():
    day = {"d": "2026-11-01"}
    rl = RateLimiter(per_minute=0, per_day=2, today=lambda: day["d"])
    rl.check("a")
    rl.check("b")
    with pytest.raises(DailyLimitReachedError):
        rl.check("c")
    day["d"] = "2026-11-02"
    rl.check("c")


def test_zero_disables_limits():
    rl = RateLimiter(0, 0)
    for _ in range(100):
        rl.check("a")


# ------------------------------------------------------------------- endpoint


def test_rate_limited_request_returns_429_without_calling_model(client):
    sdk = FakeSDK(output_text=json.dumps(model_output()))
    use(sdk, RateLimiter(per_minute=1, per_day=0))
    assert client.post("/api/analyze", json=VALID).status_code == 200
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert len(sdk.calls) == 1


def test_daily_limit_returns_429(client):
    use(FakeSDK(output_text=json.dumps(model_output())), RateLimiter(per_minute=0, per_day=1))
    client.post("/api/analyze", json=VALID)
    r = client.post("/api/analyze", json=VALID)
    assert (r.status_code, r.json()["error"]["code"]) == (429, "daily_limit_reached")


def test_config_errors_are_not_counted_against_limits(client):
    limiter = RateLimiter(per_minute=1, per_day=1)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    for _ in range(3):  # no key configured -> 503 every time, never 429
        assert client.post("/api/analyze", json=VALID).status_code == 503


def test_oversized_body_rejected_with_413(client):
    use(FakeSDK(output_text="{}"))
    big = json.dumps({"terms": "x" * 200_000, "expectation": "y"})
    r = client.post("/api/analyze", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize(
    "setup, status",
    [
        (lambda: use(FakeSDK(output_text=json.dumps(model_output()))), 200),
        (lambda: None, 503),  # no key
        (lambda: use(FakeSDK(output_text="nope")), 502),
        (lambda: use(FakeSDK(exc=RuntimeError("boom"))), 500),
    ],
)
def test_cors_headers_present_on_success_and_every_error(client, setup, status):
    setup()
    r = client.post("/api/analyze", json=VALID, headers={"Origin": ORIGIN})
    assert r.status_code == status
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_cors_headers_on_413_and_422(client):
    r = client.post("/api/analyze", json={"terms": ""}, headers={"Origin": ORIGIN})
    assert r.status_code == 422 and r.headers.get("access-control-allow-origin") == ORIGIN
    big = json.dumps({"terms": "x" * 200_000, "expectation": "y"})
    r = client.post("/api/analyze", content=big, headers={"Origin": ORIGIN, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.headers.get("access-control-allow-origin") == ORIGIN


def test_cors_preflight_allowed_origin_and_blocked_origin(client):
    ok = client.options(
        "/api/analyze",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )
    assert ok.status_code == 200
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = client.options(
        "/api/analyze",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_unexpected_error_is_generic_and_logged_without_user_text(client, caplog):
    use(FakeSDK(exc=RuntimeError("internal secret detail")))
    with caplog.at_level(logging.INFO):
        r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "An unexpected server error occurred."}}
    assert "internal secret detail" not in r.text
    assert TERMS not in caplog.text


def test_success_log_contains_metadata_only(client, caplog):
    use(FakeSDK(output_text=json.dumps(model_output())))
    with caplog.at_level(logging.INFO, logger="fair.api"):
        assert client.post("/api/analyze", json=VALID).status_code == 200
    assert "analyze ok verdict=CONTRADICTION" in caplog.text
    assert TERMS not in caplog.text
    assert "free forever" not in caplog.text
    assert "test-key-not-real" not in caplog.text


# --------------------------------------------------------------------- config


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://fair.example, https://www.fair.example")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("DAILY_ANALYSIS_LIMIT", "0")
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    s = get_settings()
    assert s.cors_origins == ("https://fair.example", "https://www.fair.example")
    assert (s.rate_limit_per_minute, s.daily_analysis_limit, s.api_docs_enabled) == (5, 0, False)


@pytest.mark.parametrize("value", ["abc", "-1"])
def test_invalid_limit_config_fails_loudly(monkeypatch, value):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", value)
    with pytest.raises(ValueError):
        get_settings()


def test_health_needs_no_key_and_no_rate_limit(client):
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(per_minute=1, per_day=1)
    for _ in range(5):
        assert client.get("/api/health").status_code == 200
