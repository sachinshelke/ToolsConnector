"""Authentication middleware.

Injects authentication headers (and optionally query parameters) into the
action context before each request by delegating to an
:class:`~toolsconnector.runtime.auth.base.AuthProvider`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from toolsconnector.errors import AuthError
from toolsconnector.runtime.context import ActionContext
from toolsconnector.runtime.middleware.base import ActionResult, CallNext


@runtime_checkable
class AuthManager(Protocol):
    """Minimal protocol for an auth manager used by :class:`AuthMiddleware`.

    Any object that exposes ``get_auth_headers`` satisfies this protocol,
    making the middleware agnostic of the concrete auth strategy.
    """

    async def get_auth_headers(self) -> dict[str, str]:
        """Return headers that authenticate the request.

        Returns:
            A mapping of header names to values (e.g.
            ``{"Authorization": "Bearer ..."}``.

        Raises:
            AuthError: If credentials are unavailable or expired and
                cannot be refreshed.
        """
        ...


class AuthMiddleware:
    """Middleware that injects auth headers into :attr:`ActionContext.metadata`.

    On each invocation the middleware calls the configured
    :class:`AuthManager` to obtain fresh headers and stores them under
    ``context.metadata["auth_headers"]`` so that downstream transport
    layers can attach them to the outgoing HTTP request.

    Args:
        auth_manager: Provider of authentication headers.
    """

    def __init__(self, auth_manager: AuthManager) -> None:
        """Initialize with an auth manager.

        Args:
            auth_manager: Object satisfying the :class:`AuthManager`
                protocol.
        """
        self._auth_manager = auth_manager

    async def __call__(
        self,
        context: ActionContext,
        call_next: CallNext,
    ) -> ActionResult:
        """Inject auth headers and delegate to the next middleware.

        Args:
            context: The current action execution context.
            call_next: Callback to the next middleware or handler.

        Returns:
            The action result from downstream.

        Raises:
            AuthError: If the auth manager fails to produce valid
                credentials.
        """
        try:
            headers = await self._auth_manager.get_auth_headers()
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError(
                f"Failed to obtain auth headers: {exc}",
                connector=context.connector_name,
                action=context.action_name,
            ) from exc

        context.metadata["auth_headers"] = headers
        return await call_next(context)
