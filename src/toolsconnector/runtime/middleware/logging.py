"""Structured logging middleware.

Emits structured log records at action start, completion, and failure
using Python's standard :mod:`logging` module.
"""

from __future__ import annotations

import logging
import time

from toolsconnector.runtime.context import ActionContext
from toolsconnector.runtime.middleware.base import ActionResult, CallNext


class LoggingMiddleware:
    """Middleware that logs action lifecycle events.

    Produces INFO-level records when an action starts and completes
    (including wall-clock duration), and an ERROR-level record if the
    action raises.  All log records include ``connector_name``,
    ``action_name``, ``request_id``, and ``attempt`` as extra fields
    for structured log consumers.

    Args:
        logger_name: Name passed to :func:`logging.getLogger`.
            Defaults to ``"toolsconnector"``.
    """

    def __init__(self, logger_name: str = "toolsconnector") -> None:
        """Initialize with a logger name.

        Args:
            logger_name: Logger name for :func:`logging.getLogger`.
        """
        self._logger = logging.getLogger(logger_name)

    async def __call__(
        self,
        context: ActionContext,
        call_next: CallNext,
    ) -> ActionResult:
        """Log action start, completion, and errors.

        Args:
            context: The current action execution context.
            call_next: Callback to the next middleware or handler.

        Returns:
            The action result from downstream.

        Raises:
            Exception: Re-raised after logging.
        """
        extra = self._build_extra(context)

        self._logger.info(
            "Action started: %s.%s",
            context.connector_name,
            context.action_name,
            extra=extra,
        )

        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as exc:
            duration = time.monotonic() - start
            self._logger.error(
                "Action failed: %s.%s after %.3fs - %s",
                context.connector_name,
                context.action_name,
                duration,
                exc,
                extra={**extra, "duration_seconds": duration},
                exc_info=True,
            )
            raise

        duration = time.monotonic() - start
        self._logger.info(
            "Action completed: %s.%s in %.3fs",
            context.connector_name,
            context.action_name,
            duration,
            extra={**extra, "duration_seconds": duration},
        )
        return result

    @staticmethod
    def _build_extra(context: ActionContext) -> dict[str, object]:
        """Build the extra dict attached to every log record.

        Args:
            context: The current action execution context.

        Returns:
            Dict with connector_name, action_name, request_id,
            and attempt.
        """
        return {
            "connector_name": context.connector_name,
            "action_name": context.action_name,
            "request_id": context.request_id,
            "attempt": context.attempt,
        }
