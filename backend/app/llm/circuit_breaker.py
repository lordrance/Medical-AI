"""In-memory circuit breaker for LLM provider calls.

Implements a classic three-state machine:
  CLOSED  — normal operation, calls pass through
  OPEN    — failures exceeded threshold, calls are rejected immediately
  HALF_OPEN — probe window: one call is allowed to test recovery

Thread safety note: asyncio is single-threaded, so no lock is needed.
Time checks use ``time.monotonic()`` which is safe against clock jumps.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is OPEN and rejects a call."""


class CircuitBreaker:
    """In-memory circuit breaker protecting external service calls.

    Parameters
    ----------
    failure_threshold:
        Number of consecutive failures in CLOSED state before tripping to OPEN.
    recovery_timeout:
        Seconds to wait in OPEN state before transitioning to HALF_OPEN.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 300.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float | None = None

    # ------------------------------------------------------------------
    # Public properties (monitoring / admin)
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def last_failure_time(self) -> float | None:
        return self._last_failure_time

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def recovery_timeout(self) -> float:
        return self._recovery_timeout

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def call(self, func):
        """Execute *func* (an async callable) if the circuit permits.

        Returns
        -------
        The return value of *func*.

        Raises
        ------
        CircuitBreakerOpenError
            If the circuit is OPEN and not yet ready for a probe.
        """
        self._maybe_transition_to_half_open()

        if self._state is CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN ({self._failure_count} failures, "
                f"last failure {self._last_failure_time})"
            )

        try:
            result = await func()
        except Exception:
            self._on_failure()
            raise

        self._on_success()
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """If enough time has passed in OPEN state, move to HALF_OPEN."""
        if self._state is not CircuitState.OPEN:
            return
        if self._last_failure_time is None:
            return
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._recovery_timeout:
            logger.info(
                "Circuit breaker transition OPEN -> HALF_OPEN "
                "(elapsed=%.1fs, threshold=%.1fs)",
                elapsed,
                self._recovery_timeout,
            )
            self._state = CircuitState.HALF_OPEN

    def _on_success(self) -> None:
        """Reset state after a successful call."""
        if self._state is CircuitState.HALF_OPEN:
            logger.info("Circuit breaker HALF_OPEN probe succeeded -> CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state is CircuitState.HALF_OPEN:
            logger.warning(
                "Circuit breaker HALF_OPEN probe failed -> OPEN (failures=%d)",
                self._failure_count,
            )
            self._state = CircuitState.OPEN
            return

        if self._failure_count >= self._failure_threshold:
            logger.warning(
                "Circuit breaker CLOSED -> OPEN (failures=%d/%d)",
                self._failure_count,
                self._failure_threshold,
            )
            self._state = CircuitState.OPEN

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.value}, "
            f"failures={self._failure_count}/{self._failure_threshold})"
        )
