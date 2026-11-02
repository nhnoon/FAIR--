import logging
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import Settings, get_settings
from app.meta_client import (
    LiveCallsDisabledError,
    MetaClient,
    ModelAuthError,
    ModelNotConfiguredError,
    ModelNotFoundError,
    ModelRateLimitedError,
    ModelResponseError,
    ModelTimeoutError,
    ModelTruncatedError,
    ModelUnavailableError,
    parse_json_object,
)
from tests.conftest import FakeSDK

_REQ = httpx.Request("POST", "https://api.meta.ai/v1/responses")


def _status_error(cls, code):
    return cls(f"HTTP {code}", response=httpx.Response(code, request=_REQ), body=None)


def test_missing_key_raises_config_error_without_calling_sdk():
    sdk = FakeSDK(output_text="{}")
    client = MetaClient(Settings(api_key=None, live_calls_enabled=True), sdk_client=sdk)
    with pytest.raises(ModelNotConfiguredError):
        client.generate("i", "u")
    assert sdk.calls == []


def test_live_calls_disabled_by_default_without_calling_sdk():
    sdk = FakeSDK(output_text="{}")
    client = MetaClient(Settings(api_key="k"), sdk_client=sdk)
    with pytest.raises(LiveCallsDisabledError):
        client.generate("i", "u")
    assert sdk.calls == []


def test_request_uses_configured_model(live_settings):
    sdk = FakeSDK(output_text='{"ok": true}')
    client = MetaClient(live_settings, sdk_client=sdk)
    assert client.generate_json("sys", "user") == {"ok": True}
    assert sdk.calls == [{"model": "muse-spark-1.3", "instructions": "sys", "input": "user", "max_output_tokens": 8000}]


def test_settings_repr_hides_key():
    assert "secret-value" not in repr(Settings(api_key="secret-value"))


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_status_error(openai.AuthenticationError, 401), ModelAuthError),
        (_status_error(openai.PermissionDeniedError, 403), ModelAuthError),
        (_status_error(openai.NotFoundError, 404), ModelNotFoundError),
        (_status_error(openai.RateLimitError, 429), ModelRateLimitedError),
        (_status_error(openai.InternalServerError, 500), ModelUnavailableError),
        (openai.APITimeoutError(request=_REQ), ModelTimeoutError),
        (openai.APIConnectionError(request=_REQ), ModelUnavailableError),
    ],
)
def test_sdk_failures_map_to_clear_errors(live_settings, exc, expected):
    client = MetaClient(live_settings, sdk_client=FakeSDK(exc=exc))
    with pytest.raises(expected) as info:
        client.generate("i", "u")
    assert "test-key-not-real" not in info.value.message


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_output_is_response_error(live_settings, text):
    client = MetaClient(live_settings, sdk_client=FakeSDK(output_text=text))
    with pytest.raises(ModelResponseError):
        client.generate("i", "u")


def test_parse_json_plain_fenced_and_wrapped():
    assert parse_json_object('{"a": 1}') == {"a": 1}
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go: {"a": "١"} done') == {"a": "١"}


@pytest.mark.parametrize("text", ["not json", "{broken", "[1, 2]", "```json\n```"])
def test_parse_json_rejects_invalid(text):
    with pytest.raises(ModelResponseError):
        parse_json_object(text)


def test_real_sdk_client_built_lazily_from_settings(monkeypatch, live_settings):
    captured = {}

    class Recorder:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", Recorder)
    MetaClient(live_settings)._client()
    assert captured["base_url"] == "https://api.meta.ai/v1"
    assert captured["api_key"] == "test-key-not-real"
    assert captured["max_retries"] == 0  # a retry would bill a second request


class ResponseSDK:
    """Returns a fixed response object, as the real SDK does."""

    def __init__(self, **fields):
        self.response = SimpleNamespace(**fields)
        self.responses = SimpleNamespace(create=lambda **_: self.response)


USAGE = SimpleNamespace(input_tokens=1365, output_tokens=4470, total_tokens=5835,
                        output_tokens_details=SimpleNamespace(reasoning_tokens=3716))


def test_output_budget_is_configurable_and_cannot_be_disabled(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "1200")
    assert get_settings().max_output_tokens == 1200
    for bad in ("0", "15"):
        monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", bad)
        with pytest.raises(ValueError):
            get_settings()


def test_live_calls_stay_off_when_the_flag_is_absent(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "k")
    assert get_settings().live_calls_enabled is False


def test_usage_is_totalled_and_logged_without_content_or_key(live_settings, caplog):
    client = MetaClient(live_settings, sdk_client=ResponseSDK(output_text="SECRET-MODEL-TEXT", status="completed", usage=USAGE))
    with caplog.at_level(logging.INFO, logger="fair.meta"):
        client.generate("SECRET-INSTRUCTIONS", "SECRET-USER-TEXT")
        client.generate("i", "u")
    assert client.usage_totals == {"requests": 2, "input_tokens": 2730, "output_tokens": 8940,
                                   "reasoning_tokens": 7432, "total_tokens": 11670}
    assert "input=1365 output=4470 reasoning=3716 total=5835 budget=8000" in caplog.text
    for secret in ("SECRET-", "test-key-not-real"):
        assert secret not in caplog.text


def test_failed_request_is_still_counted(live_settings):
    client = MetaClient(live_settings, sdk_client=FakeSDK(exc=openai.APITimeoutError(request=_REQ)))
    with pytest.raises(ModelTimeoutError):
        client.generate("i", "u")
    assert client.usage_totals["requests"] == 1


def test_truncated_response_is_rejected_even_if_its_text_parses(live_settings):
    sdk = ResponseSDK(output_text='{"ok": true}', status="incomplete", usage=USAGE,
                      incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    client = MetaClient(live_settings, sdk_client=sdk)
    with pytest.raises(ModelTruncatedError, match="output token budget") as info:
        client.generate_json("i", "u")
    assert info.value.code == "model_invalid_response"
    assert client.last_usage["output_tokens"] == 4470
    assert client.usage_totals["output_tokens"] == 4470  # truncated output is still billed


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_uncompleted_status_is_rejected(live_settings, status):
    client = MetaClient(live_settings, sdk_client=ResponseSDK(output_text='{"ok": true}', status=status))
    with pytest.raises(ModelResponseError):
        client.generate("i", "u")
