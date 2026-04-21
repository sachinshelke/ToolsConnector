"""Middleware pipeline for action execution.

Provides the :class:`Middleware` protocol and :class:`MiddlewarePipeline` that
chains middleware components around an action handler using an inside-out
composition pattern.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol
from collections.abc import Awaitable

from toolsconnector.runtime.context import ActionContext

# The result of calling an action.
ActionResult = Any

# Function signature for calling the next middleware in the chain.
CallNext = Callable[[ActionContext], Awaitable[ActionResult]]


class Middleware(Protocol):
    """Protocol for middleware components.

    Each middleware receives the current :class:`ActionContext` and a
    ``call_next`` callback that invokes the next middleware (or the
    final action handler).  Middleware may inspect/mutate the context
    before calling ``call_next``, and inspect/transform the result
    after.
    """

    async def __call__(
        self,
        context: ActionContext,
        call_next: CallNext,
    ) -> ActionResult:
        """Execute this middleware.

        Args:
            context: The current action execution context.
            call_next: Callback to invoke the next middleware or handler.

        Returns:
            The action result, potentially transformed by this middleware.
        """
        ...


class MiddlewarePipeline:
    """Executes a chain of middleware around an action call.

    Middleware is composed inside-out: the first middleware added is the
    outermost wrapper and sees the request first / response last.

    Example::

        pipeline = MiddlewarePipeline([auth_mw, retry_mw, logging_mw])
        result = await pipeline.execute(ctx, actual_handler)
    """

    def __init__(self, middlewares: list[Middleware] | None = None) -> None:
        """Initialize the pipeline.

        Args:
            middlewares: Optional ordered list of middleware to install.
                The first element wraps outermost.
        """
        self._middlewares: list[Middleware] = list(middlewares or [])

    def add(self, middleware: Middleware) -> None:
        """Append a middleware to the end of the chain.

        Args:
            middleware: Middleware instance to add.
        """
        self._middlewares.append(middleware)

    async def execute(
        self,
        context: ActionContext,
        handler: CallNext,
    ) -> ActionResult:
        """Execute the full middleware pipeline.

        Builds the chain from inside out so that ``self._middlewares[0]``
        is the outermost layer and ``handler`` is the innermost.

        Args:
            context: The action execution context.
            handler: The actual action function to invoke at the
                centre of the chain.

        Returns:
            The result produced by the handler (possibly transformed
            by middleware).
        """
        chain = handler

        for middleware in reversed(self._middlewares):
            # Capture current chain reference in the closure.
            chain = _wrap(middleware, chain)

        return await chain(context)


def _wrap(middleware: Middleware, next_fn: CallNext) -> CallNext:
    """Create a closure that calls *middleware* with *next_fn*.

    Args:
        middleware: The middleware to wrap.
        next_fn: The next callable in the chain.

    Returns:
        A new callable that invokes the middleware.
    """

    async def _call(ctx: ActionContext) -> ActionResult:
        return await middleware(ctx, next_fn)

    return _call
