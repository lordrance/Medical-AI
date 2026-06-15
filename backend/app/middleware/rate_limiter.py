"""In-memory sliding-window rate limiter.

No external dependencies (no Redis, no memcached) — a single Python dict
is more than enough for the HCI study's traffic profile (< 100 concurrent
participants). Restarting the backend resets counters, which is the safe
default for a short-term study.
"""

from __future__ import annotations

import time
from collections import defaultdict


class SlidingWindowLimiter:
    """Sliding-window rate limiter keyed by arbitrary string (e.g. client IP).

    Thread-safe within a single asyncio event loop because FastAPI runs
    handlers sequentially per event-loop iteration and we only mutate
    plain-Python data structures.

    Args:
        max_requests: max calls allowed in the window.
        window_secs: sliding window duration in seconds.
    """

    def __init__(self, max_requests: int, window_secs: float) -> None:
        self._max = max_requests
        self._window = window_secs
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        """Return True if the request is within the limit, False if rejected."""
        now = time.monotonic()
        # Evict expired timestamps
        cutoff = now - self._window
        times = self._buckets[key]
        while times and times[0] < cutoff:
            times.pop(0)

        if len(times) < self._max:
            times.append(now)
            return True
        return False

    def reset(self, key: str) -> None:
        """Remove all tracking for a key (useful for testing)."""
        self._buckets.pop(key, None)

    def count(self, key: str) -> int:
        """Number of requests counted in the current window for `key`."""
        now = time.monotonic()
        cutoff = now - self._window
        times = self._buckets[key]
        while times and times[0] < cutoff:
            times.pop(0)
        return len(times)


# Module-level instances — one for each rate-limit tier.
# Tuned for HCI study scale:
#   - 10 session creations / hour / IP (one real participant creates 1 session)
#   - 60 admin requests / minute / IP (dashboard + export usage)

_session_limiter = SlidingWindowLimiter(max_requests=10, window_secs=3600)
_admin_limiter = SlidingWindowLimiter(max_requests=60, window_secs=60)


def check_session_rate(key: str) -> bool:
    return _session_limiter.allow(key)


def check_admin_rate(key: str) -> bool:
    return _admin_limiter.allow(key)
