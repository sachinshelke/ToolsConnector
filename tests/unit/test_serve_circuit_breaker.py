"""Unit tests for toolsconnector.serve._circuit_breaker."""

from __future__ import annotations

import time

from toolsconnector.serve._circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    """Tests for the per-connector circuit breaker pattern."""

    def test_initial_state_closed(self) -> None:
        """Circuit breaker starts in the closed (normal) state."""
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False

    def test_opens_after_threshold(self) -> None:
        """Circuit opens after N consecutive failures."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        for i in range(3):
            cb.record_failure(RuntimeError(f"fail-{i}"))
        assert cb.state == CircuitState.OPEN
        assert cb.is_open is True

    def test_success_resets_count(self) -> None:
        """A success in the closed state resets the failure count."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure(RuntimeError("fail-1"))
        cb.record_failure(RuntimeError("fail-2"))
        cb.record_success()
        # After reset, need 3 more failures to open
        cb.record_failure(RuntimeError("fail-3"))
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery(self) -> None:
        """Circuit transitions to half_open after the recovery timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.5)
        cb.record_failure(RuntimeError("fail-1"))
        cb.record_failure(RuntimeError("fail-2"))
        assert cb.state == CircuitState.OPEN

        # Simulate the passage of time past the recovery window
        cb._last_failure_time = time.monotonic() - 1.0
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        """Enough successes in half_open close the circuit back to normal."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.0,
            success_threshold=2,
        )
        cb.record_failure(RuntimeError("fail-1"))
        cb.record_failure(RuntimeError("fail-2"))

        # Force transition to half_open by expired recovery
        cb._last_failure_time = time.monotonic() - 1.0
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        """A failure in half_open sends the circuit back to open."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        cb.record_failure(RuntimeError("fail-1"))
        cb.record_failure(RuntimeError("fail-2"))
        assert cb.state == CircuitState.OPEN

        # Force transition to half_open by pretending recovery elapsed
        cb._last_failure_time = time.monotonic() - 120.0
        assert cb.state == CircuitState.HALF_OPEN

        # A failure in half_open re-opens the circuit and updates the
        # last_failure_time to now, so the recovery timeout is fresh again.
        cb.record_failure(RuntimeError("fail-again"))
        assert cb._state == CircuitState.OPEN

    def test_status_dict(self) -> None:
        """status_dict returns a dict with expected keys and values."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        status = cb.status_dict()
        assert isinstance(status, dict)
        assert "state" in status
        assert "failure_count" in status
        assert "last_error" in status
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["last_error"] is None
