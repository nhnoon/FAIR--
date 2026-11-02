"""Runtime configuration, read from environment variables only.

The API key is never logged, returned, or given a default value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"
# Counts visible output AND reasoning tokens. The API's minimum is 16.
DEFAULT_MAX_OUTPUT_TOKENS = 8000
MIN_OUTPUT_TOKENS = 16


def load_env_file() -> None:
    """Load backend/.env if present. Existing environment variables win.

    The test suite sets FAIR_DISABLE_DOTENV=1 so a real key can never leak into tests.
    """
    if _bool(os.getenv("FAIR_DISABLE_DOTENV")):
        return
    load_dotenv(BACKEND_DIR / ".env", override=False)


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 45.0
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    # Paid calls are off unless explicitly enabled.
    live_calls_enabled: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    # Cost protection for a public deployment. 0 disables a limit.
    rate_limit_per_minute: int = 10  # per client IP, /api/analyze only
    daily_analysis_limit: int = 300  # whole server, resets at 00:00 UTC
    max_body_bytes: int = 131_072
    api_docs_enabled: bool = True

    @property
    def api_key_present(self) -> bool:
        return bool(self.api_key)


def _int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def get_settings() -> Settings:
    api_key = (os.getenv("MODEL_API_KEY") or "").strip() or None
    origins = os.getenv("CORS_ORIGINS")
    docs = os.getenv("API_DOCS_ENABLED")
    max_output_tokens = _int("MODEL_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)
    if max_output_tokens < MIN_OUTPUT_TOKENS:  # this budget can never be disabled
        raise ValueError(f"MODEL_MAX_OUTPUT_TOKENS must be >= {MIN_OUTPUT_TOKENS}")
    return Settings(
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", Settings.rate_limit_per_minute),
        daily_analysis_limit=_int("DAILY_ANALYSIS_LIMIT", Settings.daily_analysis_limit),
        max_body_bytes=_int("MAX_BODY_BYTES", Settings.max_body_bytes),
        api_docs_enabled=True if docs is None else _bool(docs),
        api_key=api_key,
        base_url=(os.getenv("MODEL_BASE_URL") or DEFAULT_BASE_URL).strip(),
        model=(os.getenv("MODEL_NAME") or DEFAULT_MODEL).strip(),
        timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS") or 45),
        max_output_tokens=max_output_tokens,
        live_calls_enabled=_bool(os.getenv("MODEL_LIVE_CALLS_ENABLED")),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
        if origins
        else Settings.cors_origins,
    )
