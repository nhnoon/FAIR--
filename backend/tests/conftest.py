"""Test isolation: no .env, no MODEL_* variables, no real SDK client, no network."""

import os

os.environ["FAIR_DISABLE_DOTENV"] = "1"  # must be set before app.main is imported

import socket  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from app.config import Settings  # noqa: E402

_ENV_VARS = (
    "MODEL_API_KEY",
    "MODEL_BASE_URL",
    "MODEL_NAME",
    "MODEL_TIMEOUT_SECONDS",
    "MODEL_MAX_OUTPUT_TOKENS",
    "MODEL_LIVE_CALLS_ENABLED",
    "CORS_ORIGINS",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    def _blocked(*_a, **_k):
        raise AssertionError("A real OpenAI/Meta SDK client must never be constructed in tests.")

    monkeypatch.setattr("openai.OpenAI", _blocked)

    # Only loopback survives: Windows event loops connect a local socket pair to themselves.
    real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo

    def _local(host) -> bool:
        return host in ("127.0.0.1", "::1", "localhost", None, "")

    def _connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
            raise AssertionError(f"Network access attempted in a test: {address[0]}")
        return real_connect(self, address)

    def _getaddrinfo(host, *args, **kwargs):
        if not _local(host):
            raise AssertionError(f"DNS lookup attempted in a test: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect)
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)


class FakeSDK:
    """Stands in for openai.OpenAI: records calls, returns text or raises."""

    def __init__(self, output_text: str | None = None, exc: Exception | None = None):
        self.calls: list[dict] = []
        self._text = output_text
        self._exc = exc
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(output_text=self._text)


@pytest.fixture
def live_settings() -> Settings:
    return Settings(api_key="test-key-not-real", live_calls_enabled=True)
