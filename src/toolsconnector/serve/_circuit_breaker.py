"""Per-connector circuit breaker pattern.

Prevents hammering dead APIs. Three states:
- CLOSED: Normal operation, calls go through.
- OPEN: Connector is failing, calls rejected immediately.
- HALF_OPEN: Testing recovery, one call allowed through.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for a single connector.

    Args:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before testing recovery (half-open).
        success_threshold: Consecutive successes in half-open to close again.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._last_error: Optional[str] = None

    @property
    def state(self) -> CircuitState:
        """Current circuit state, considering recovery timeout."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._reset()
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_error = str(error) if error else None

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open → back to open
            self._state = CircuitState.OPEN
        elif self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN

    def _reset(self) -> None:
        """Reset to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_error = None

    def status_dict(self) -> dict:
        """Return current status as a dict."""
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_error": self._last_error,
            "recovery_in_seconds": max(
                0, self._recovery_timeout - (time.monotonic() - self._last_failure_time)
            ) if self._state == CircuitState.OPEN else None,
        }
