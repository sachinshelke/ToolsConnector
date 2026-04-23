"""Retry middleware with exponential backoff and jitter.

Automatically retries failed action calls when the error indicates that
a retry is eligible, using exponential backoff with random jitter to
avoid thundering-herd effects.
"""

from __future__ import annotations

import asyncio
import random

from toolsconnector.errors import (
    RateLimitError,
    ToolsConnectorError,
)
from toolsconnector.runtime.context import ActionContext
from toolsconnector.runtime.middleware.base import ActionResult, CallNext


class RetryMiddleware:
    """Exponential-backoff retry middleware.

    Only retries when the caught exception has ``retry_eligible=True``.
    If the error is a :class:`RateLimitError` with a
    ``retry_after_seconds`` value, that value is honoured as the
    minimum delay for the next attempt.

    Args:
        max_retries: Maximum number of retry attempts (excluding the
            initial call).  Defaults to ``3``.
        base_delay: Initial backoff delay in seconds.  Defaults to
            ``1.0``.
        max_delay: Upper bound on the computed delay in seconds.
            Defaults to ``60.0``.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> None:
        """Initialize retry parameters.

        Args:
            max_retries: Maximum retry attempts after the first call.
            base_delay: Base delay in seconds for exponential backoff.
            max_delay: Cap on computed delay.
        """
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def __call__(
        self,
        context: ActionContext,
        call_next: CallNext,
    ) -> ActionResult:
        """Execute with retries on eligible failures.

        Args:
            context: The current action execution context.
            call_next: Callback to the next middleware or handler.

        Returns:
            The action result from a successful attempt.

        Raises:
            ToolsConnectorError: Re-raised after all retry attempts
                are exhausted, or immediately if the error is not
                retry-eligible.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 2):  # 1-based, includes initial
            context.attempt = attempt
            try:
                return await call_next(context)
            except ToolsConnectorError as exc:
                last_error = exc

                if not exc.retry_eligible:
                    raise

                if attempt > self._max_retries:
                    raise

                delay = self._compute_delay(attempt, exc)
                await asyncio.sleep(delay)

        # Should not reach here, but satisfy type checker.
        assert last_error is not None  # noqa: S101
        raise last_error

    def _compute_delay(
        self,
        attempt: int,
        error: ToolsConnectorError,
    ) -> float:
        """Calculate the backoff delay for a given attempt.

        Applies exponential backoff with jitter.  If the error provides
        a ``retry_after_seconds`` hint (typical for
        :class:`RateLimitError`), that value is used as the minimum
        delay.

        Args:
            attempt: The 1-based attempt number that just failed.
            error: The exception that triggered the retry.

        Returns:
            Delay in seconds before the next attempt.
        """
        # Exponential backoff: base * 2^(attempt-1)
        exp_delay = self._base_delay * (2 ** (attempt - 1))

        # Honour retry_after_seconds from rate-limit responses.
        if isinstance(error, RateLimitError) and error.retry_after_seconds is not None:
            exp_delay = max(exp_delay, error.retry_after_seconds)

        # Cap at max_delay.
        exp_delay = min(exp_delay, self._max_delay)

        # Add jitter: uniform random in [0, 0.5 * delay].
        jitter = random.uniform(0, 0.5 * exp_delay)  # noqa: S311

        return float(exp_delay + jitter)
