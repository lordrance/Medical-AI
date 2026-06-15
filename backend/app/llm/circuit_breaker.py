from __future__ import annotations

import time
from enum import Enum


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit is open and the request is rejected."""


class CircuitBreaker:
    """In-memory circuit breaker with CLOSED -> OPEN -> HALF_OPEN -> CLOSED state machine.

    Parameters
    ----------
    failure_threshold : int
        Consecutive failures before the circuit opens (default 3).
    recovery_timeout : float
        Seconds to wait in OPEN state before transitioning to HALF_OPEN (default 300).
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 300.0) -> None:
        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure = 0.0
        self._threshold = failure_threshold
        self._timeout = recovery_timeout

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Current state name (``"closed"`` | ``"open"`` | ``"half_open"``).

        Reading this property triggers automatic HALF_OPEN transition when the
        recovery timeout has elapsed.
        """
        if self._state is State.OPEN and time.monotonic() - self._last_failure >= self._timeout:
            self._state = State.HALF_OPEN
        return self._state.value

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def last_failure_time(self) -> float:
        return self._last_failure

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(self, func, /, *args, **kwargs):
        """Execute *func* (an awaitable) if the circuit is not OPEN.

        Raises
        ------
        CircuitBreakerOpenError
            When the circuit is in OPEN state and the recovery timeout has not
            elapsed.
        """
        if self.state == State.OPEN.value:
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN (failure_count={self._failure_count}, "
                f"threshold={self._threshold}); rejecting request."
            )

        try:
            result = await func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise

        self._on_success()
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_success(self) -> None:
        self._state = State.CLOSED
        self._failure_count = 0

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure = time.monotonic()
        if self._failure_count >= self._threshold:
            self._state = State.OPEN
