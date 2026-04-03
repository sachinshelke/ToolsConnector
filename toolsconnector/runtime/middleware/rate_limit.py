"""Token-bucket rate-limiter middleware.

Throttles outgoing action calls to respect upstream API rate limits.
Uses a classic token-bucket algorithm with async-safe locking.
"""

from __future__ import annotations

import asyncio
import time

from toolsconnector.errors import RateLimitError
from toolsconnector.runtime.context import ActionContext
from toolsconnector.runtime.middleware.base import ActionResult, CallNext


class RateLimitMiddleware:
    """Token-bucket rate limiter.

    Each action call consumes one token.  Tokens are refilled at a
    constant ``rate`` (tokens per second) up to a ``burst`` ceiling.
    If no token is available the middleware blocks until one is
    replenished, raising :class:`RateLimitError` if the required wait
    would exceed a configurable ``timeout``.

    Args:
        rate: Sustained token refill rate (tokens per second).
        burst: Maximum number of tokens that can accumulate.
        timeout: Maximum seconds the middleware will wait for a token
            before raising.  Defaults to ``30.0``.
    """

    def __init__(
        self,
        rate: float,
        burst: int,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the token bucket.

        Args:
            rate: Tokens added per second.
            burst: Maximum token capacity.
            timeout: Max wait time in seconds before raising an error.
        """
        self._rate = rate
        self._burst = burst
        self._timeout = timeout

        self._tokens: float = float(burst)
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        context: ActionContext,
        call_next: CallNext,
    ) -> ActionResult:
        """Acquire a token and delegate to the next middleware.

        Args:
            context: The current action execution context.
            call_next: Callback to the next middleware or handler.

        Returns:
            The action result from downstream.

        Raises:
            RateLimitError: If a token cannot be acquired within
                *timeout* seconds.
        """
        await self._acquire(context)
        return await call_next(context)

    async def _acquire(self, context: ActionContext) -> None:
        """Wait until a token is available, or raise on timeout.

        Args:
            context: Used to populate error metadata on failure.

        Raises:
            RateLimitError: If the wait would exceed *timeout*.
        """
        async with self._lock:
            self._refill()

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Calculate how long we need to wait for one token.
            deficit = 1.0 - self._tokens
            wait_time = deficit / self._rate

            if wait_time > self._timeout:
                raise RateLimitError(
                    f"Rate limit wait ({wait_time:.1f}s) exceeds "
                    f"timeout ({self._timeout:.1f}s).",
                    connector=context.connector_name,
                    action=context.action_name,
                    retry_after_seconds=wait_time,
                )

        # Sleep outside the lock so other coroutines can proceed.
        await asyncio.sleep(wait_time)

        async with self._lock:
            self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        """Replenish tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        self._tokens = min(
            float(self._burst),
            self._tokens + elapsed * self._rate,
        )
