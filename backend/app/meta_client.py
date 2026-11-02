"""Meta Model API client (OpenAI-compatible SDK, Responses API).

Follows https://dev.meta.ai/docs/quickstart: OpenAI SDK pointed at the Meta base
URL, key passed explicitly from MODEL_API_KEY.

Two gates must both pass before any network request is made:
  1. MODEL_API_KEY is set.
  2. MODEL_LIVE_CALLS_ENABLED=true (paid calls are opt-in).

Cost protection: one analysis is at most one request (no SDK retries), and each request
carries a max_output_tokens budget. Token counts are logged; text and keys never are.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import openai

from .config import Settings

log = logging.getLogger("fair.meta")


class ModelError(Exception):
    code = "model_error"
    http_status = 502

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ModelNotConfiguredError(ModelError):
    code, http_status = "model_not_configured", 503


class LiveCallsDisabledError(ModelError):
    code, http_status = "live_calls_disabled", 503


class ModelAuthError(ModelError):
    code, http_status = "model_auth_failed", 502


class ModelNotFoundError(ModelError):
    code, http_status = "model_not_found", 502


class ModelRateLimitedError(ModelError):
    code, http_status = "model_rate_limited", 503


class ModelTimeoutError(ModelError):
    code, http_status = "model_timeout", 504


class ModelUnavailableError(ModelError):
    code, http_status = "model_unavailable", 502


class ModelResponseError(ModelError):
    code, http_status = "model_invalid_response", 502


class ModelTruncatedError(ModelResponseError):
    """Same API error as any unusable response; the benchmark counts these separately."""


class RequestLimitError(ModelError):
    code, http_status = "request_limit_reached", 503


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse the model's text as one JSON object, tolerating ```json fences."""
    if not text or not text.strip():
        raise ModelResponseError("The model returned an empty response.")
    candidate = _FENCE.sub("", text.strip())
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ModelResponseError("The model response did not contain a JSON object.")
        candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ModelResponseError(f"The model response was not valid JSON ({exc.msg}).") from exc
    if not isinstance(data, dict):
        raise ModelResponseError("The model response JSON was not an object.")
    return data


class MetaClient:
    def __init__(self, settings: Settings, sdk_client: Any | None = None):
        self.settings = settings
        self._sdk = sdk_client  # injected only by tests
        # Running totals for this client. Requests include failed ones, which may also be billed.
        self.usage_totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
        self.last_usage: dict[str, Any] | None = None  # counts for the most recent request only
        self.last_call: dict[str, Any] | None = None  # status and unparsed text of that request
        self.max_requests: int | None = None  # hard cap on attempted requests; set by the evaluation runner

    @property
    def model(self) -> str:
        return self.settings.model

    def check_ready(self) -> None:
        if not self.settings.api_key_present:
            raise ModelNotConfiguredError(
                "MODEL_API_KEY is not set on the server. Add it to backend/.env to enable analysis."
            )
        if not self.settings.live_calls_enabled:
            raise LiveCallsDisabledError(
                "Live model calls are disabled. Set MODEL_LIVE_CALLS_ENABLED=true in backend/.env to enable them."
            )

    def _client(self) -> Any:
        if self._sdk is None:
            self._sdk = openai.OpenAI(
                base_url=self.settings.base_url,
                api_key=self.settings.api_key,
                timeout=self.settings.timeout_seconds,
                max_retries=0,  # a retry would silently bill a second request
            )
        return self._sdk

    def generate(self, instructions: str, user_input: str) -> str:
        """Send one request and return the model's text output."""
        self.check_ready()
        if self.max_requests is not None and self.usage_totals["requests"] >= self.max_requests:
            raise RequestLimitError(f"The limit of {self.max_requests} request(s) was reached. No request was sent.")
        self.usage_totals["requests"] += 1
        self.last_call = None
        self.last_usage = None
        try:
            response = self._client().responses.create(
                model=self.settings.model,
                instructions=instructions,
                input=user_input,
                max_output_tokens=self.settings.max_output_tokens,
            )
        except openai.AuthenticationError as exc:
            self._log(exc)
            raise ModelAuthError("The Meta API rejected the API key (401).") from exc
        except openai.PermissionDeniedError as exc:
            self._log(exc)
            raise ModelAuthError("The Meta API denied access for this key (403).") from exc
        except openai.NotFoundError as exc:
            self._log(exc)
            raise ModelNotFoundError(
                f"Model '{self.settings.model}' was not found. Check MODEL_NAME."
            ) from exc
        except openai.RateLimitError as exc:
            self._log(exc)
            raise ModelRateLimitedError("The Meta API rate limit or quota was reached. Try again later.") from exc
        except openai.APITimeoutError as exc:
            self._log(exc)
            raise ModelTimeoutError("The Meta API did not respond in time.") from exc
        except openai.APIConnectionError as exc:
            self._log(exc)
            raise ModelUnavailableError("Could not connect to the Meta API.") from exc
        except openai.APIStatusError as exc:
            self._log(exc)
            raise ModelUnavailableError(f"The Meta API returned HTTP {exc.status_code}.") from exc

        self._record_usage(response)
        status = getattr(response, "status", None)
        reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        self.last_call = {"status": status, "incomplete_reason": reason, "raw_output": getattr(response, "output_text", None)}
        if status == "incomplete":
            # A truncated answer is never parsed: partial JSON must not become a partial result.
            if reason == "max_output_tokens":
                raise ModelTruncatedError("The model reached its output token budget before finishing.")
            raise ModelTruncatedError("The model stopped before finishing its response.")
        if status in ("failed", "cancelled"):
            raise ModelResponseError("The model did not complete its response.")

        text = getattr(response, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            raise ModelResponseError("The model returned no text output.")
        return text

    def generate_json(self, instructions: str, user_input: str) -> dict[str, Any]:
        return parse_json_object(self.generate(instructions, user_input))

    def _record_usage(self, response: Any) -> None:
        # Token counts only; never the input, the output, or request headers.
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        details = getattr(usage, "output_tokens_details", None)
        counts = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "reasoning_tokens": getattr(details, "reasoning_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        self.last_usage = counts
        for name, value in counts.items():
            if isinstance(value, int):
                self.usage_totals[name] += value
        log.info(
            "Meta API usage model=%s status=%s input=%s output=%s reasoning=%s total=%s budget=%s",
            self.settings.model,
            getattr(response, "status", None),
            counts["input_tokens"],
            counts["output_tokens"],
            counts["reasoning_tokens"],
            counts["total_tokens"],
            self.settings.max_output_tokens,
        )

    @staticmethod
    def _log(exc: Exception) -> None:
        # Status and type only; never request headers or the key.
        status = getattr(exc, "status_code", None)
        log.warning("Meta API call failed: %s (status=%s)", type(exc).__name__, status)
