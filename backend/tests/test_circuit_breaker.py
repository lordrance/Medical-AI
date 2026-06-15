from __future__ import annotations

import time

import pytest

from app.llm.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


async def _ok() -> str:
    return "ok"


async def _fail() -> str:
    raise ValueError("simulated failure")


class TestCircuitBreaker:
    """Unit tests for the in-memory circuit breaker."""

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    async def test_initial_state(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.failure_count == 0

    async def test_success_keeps_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(10):
            await cb.call(_ok)
        assert cb.state == "closed"
        assert cb.failure_count == 0

    async def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            try:
                await cb.call(_fail)
            except ValueError:
                pass
        assert cb.state == "open"
        assert cb.failure_count == 2

    async def test_remains_closed_below_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(2):
            try:
                await cb.call(_fail)
            except ValueError:
                pass
        assert cb.state == "closed"
        assert cb.failure_count == 2

    async def test_rejects_in_open_state(self) -> None:
        cb = CircuitBreaker(failure_threshold=1)
        try:
            await cb.call(_fail)
        except ValueError:
            pass
        assert cb.state == "open"
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(_ok)

    async def test_success_resets_and_closes(self) -> None:
        cb = CircuitBreaker(failure_threshold=1)
        try:
            await cb.call(_fail)
        except ValueError:
            pass
        assert cb.state == "open"
        cb._state = type(cb._state).HALF_OPEN  # Force half-open for test
        cb._failure_count = 0
        await cb.call(_ok)
        assert cb.state == "closed"
        assert cb.failure_count == 0

    async def test_half_open_transition_after_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        try:
            await cb.call(_fail)
        except ValueError:
            pass
        assert cb.state == "open"
        time.sleep(0.02)
        assert cb.state == "half_open"
        await cb.call(_ok)
        assert cb.state == "closed"
        assert cb.failure_count == 0

    async def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        try:
            await cb.call(_fail)
        except ValueError:
            pass
        assert cb.state == "open"
        time.sleep(0.02)
        assert cb.state == "half_open"
        try:
            await cb.call(_fail)
        except ValueError:
            pass
        assert cb.state == "open"
        assert cb.failure_count >= 1
        # Still open — should reject
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(_ok)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    async def test_last_failure_time_is_set(self) -> None:
        cb = CircuitBreaker(failure_threshold=1)
        t0 = time.monotonic()
        try:
            await cb.call(_fail)
        except ValueError:
            pass
        assert cb.last_failure_time >= t0

    async def test_failure_count_property(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(3):
            try:
                await cb.call(_fail)
            except ValueError:
                pass
        assert cb.failure_count == 3
