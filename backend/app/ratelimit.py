"""In-memory limits that protect paid model credits on a public deployment.

- Per-client sliding window (requests per minute).
- Global daily cap (resets at 00:00 UTC).

State lives in process memory: it resets on restart and is per worker. That is
enough for a single-instance hackathon deployment; it is not a distributed limiter.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable

from .meta_client import ModelError


class RateLimitedError(ModelError):
    code, http_status = "rate_limited", 429


class DailyLimitReachedError(ModelError):
    code, http_status = "daily_limit_reached", 429


class RateLimiter:
    def __init__(
        self,
        per_minute: int,
        per_day: int,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], str] = lambda: datetime.now(timezone.utc).date().isoformat(),
    ):
        self.per_minute = per_minute
        self.per_day = per_day
        self._clock = clock
        self._today = today
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self._day = ""
        self._day_count = 0

    def check(self, client_key: str) -> None:
        """Record one request or raise. Daily cap is checked first and only counts allowed requests."""
        with self._lock:
            now = self._clock()
            day = self._today()
            if day != self._day:
                self._day, self._day_count = day, 0
            if self.per_day and self._day_count >= self.per_day:
                raise DailyLimitReachedError("The daily analysis limit for this demo server has been reached.")
            if self.per_minute:
                window = self._hits.setdefault(client_key, deque())
                while window and now - window[0] >= 60:
                    window.popleft()
                if len(window) >= self.per_minute:
                    raise RateLimitedError("Too many analysis requests. Please wait a minute and try again.")
                window.append(now)
                if len(self._hits) > 10_000:  # bound memory: drop idle clients
                    for key in [k for k, w in self._hits.items() if not w or now - w[-1] >= 60]:
                        del self._hits[key]
            self._day_count += 1
