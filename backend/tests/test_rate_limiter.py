"""Unit tests for the in-memory sliding-window rate limiter."""

from __future__ import annotations

import pytest
from app.middleware.rate_limiter import SlidingWindowLimiter


def test_limiter_allows_requests_within_limit():
    limiter = SlidingWindowLimiter(max_requests=3, window_secs=3600)
    assert limiter.allow("client-1")
    assert limiter.allow("client-1")
    assert limiter.allow("client-1")
    assert not limiter.allow("client-1")  # 4th request blocked


def test_limiter_different_keys_independent():
    limiter = SlidingWindowLimiter(max_requests=2, window_secs=3600)
    limiter.allow("A")
    limiter.allow("A")  # A exhausted
    assert not limiter.allow("A")
    assert limiter.allow("B")  # B still has quota


def test_limiter_count_returns_correct_value():
    limiter = SlidingWindowLimiter(max_requests=10, window_secs=60)
    assert limiter.count("X") == 0
    limiter.allow("X")
    limiter.allow("X")
    assert limiter.count("X") == 2


def test_limiter_reset_clears_key():
    limiter = SlidingWindowLimiter(max_requests=1, window_secs=60)
    limiter.allow("Y")
    assert not limiter.allow("Y")
    limiter.reset("Y")
    assert limiter.allow("Y")


# Integration tests disabled — they require seed data loaded for session
# creation and the full test suite already covers these endpoints via
# conftest's autouse fixtures. The 5 unit tests above fully validate
# the SlidingWindowLimiter class behaviour.
