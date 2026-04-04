"""API key authentication provider.

Supports placing the API key in an HTTP header, query parameter, or
request body with a configurable parameter name and optional prefix.
"""

from __future__ import annotations

from toolsconnector.errors import InvalidCredentialsError
from toolsconnector.spec.auth import AuthType


class APIKeyProvider:
    """Auth provider for API-key-based authentication.

    The provider injects a static API key into either the request
    headers, query parameters, or body depending on *location*.

    Args:
        api_key: The API key string.
        location: Where to place the key.  One of ``"header"``,
            ``"query"``, or ``"body"``.  Defaults to ``"header"``.
        param_name: Name of the header or query parameter.
            Defaults to ``"Authorization"``.
        prefix: Optional prefix prepended to the key value
            (e.g. ``"Bearer"``, ``"Token"``).  When set the
            transmitted value becomes ``"{prefix} {api_key}"``.

    Raises:
        InvalidCredentialsError: If *api_key* is empty or ``None``.

    Example::

        provider = APIKeyProvider(
            api_key="sk-abc123",
            location="header",
            param_name="X-API-Key",
        )
    """

    auth_type: str = AuthType.API_KEY.value

    def __init__(
        self,
        api_key: str,
        *,
        location: str = "header",
        param_name: str = "Authorization",
        prefix: str | None = None,
    ) -> None:
        if not api_key:
            raise InvalidCredentialsError("API key must not be empty.")
        self._api_key = api_key
        self._location = location.lower()
        self._param_name = param_name
        self._prefix = prefix

    # ------------------------------------------------------------------
    # AuthProvider protocol
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> None:
        """Inject the API key into *headers* or *params*.

        Args:
            headers: Mutable HTTP headers dict.
            params: Mutable query-parameter dict.
        """
        value = (
            f"{self._prefix} {self._api_key}" if self._prefix else self._api_key
        )

        if self._location == "header":
            headers[self._param_name] = value
        elif self._location == "query":
            params[self._param_name] = value
        elif self._location == "body":
            # Body placement is signalled through params; the transport
            # layer is responsible for moving body-type params into the
            # request payload.
            params[self._param_name] = value
        else:
            raise InvalidCredentialsError(
                f"Unsupported API key location: {self._location!r}. "
                "Expected 'header', 'query', or 'body'.",
            )

    async def refresh(self) -> None:
        """No-op -- API keys are static credentials."""

    def needs_refresh(self) -> bool:
        """API keys never expire within the provider lifecycle.

        Returns:
            Always ``False``.
        """
        return False
