"""Bearer token authentication provider.

Simple provider that places a static bearer token in the
``Authorization`` header.
"""

from __future__ import annotations

from toolsconnector.errors import InvalidCredentialsError
from toolsconnector.spec.auth import AuthType


class BearerTokenProvider:
    """Auth provider for static bearer-token authentication.

    Injects an ``Authorization: Bearer <token>`` header into every
    request.  This provider is intended for long-lived personal
    access tokens or pre-obtained OAuth tokens that the caller
    manages externally.

    Args:
        token: The bearer token string.

    Raises:
        InvalidCredentialsError: If *token* is empty or ``None``.

    Example::

        provider = BearerTokenProvider(token="ghp_xxxx")
    """

    auth_type: str = AuthType.BEARER_TOKEN.value

    def __init__(self, token: str) -> None:
        if not token:
            raise InvalidCredentialsError("Bearer token must not be empty.")
        self._token = token

    # ------------------------------------------------------------------
    # AuthProvider protocol
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> None:
        """Add the ``Authorization: Bearer`` header.

        Args:
            headers: Mutable HTTP headers dict.
            params: Mutable query-parameter dict (unused).
        """
        headers["Authorization"] = f"Bearer {self._token}"

    async def refresh(self) -> None:
        """No-op -- static bearer tokens cannot be refreshed."""

    def needs_refresh(self) -> bool:
        """Static bearer tokens never expire within the provider lifecycle.

        Returns:
            Always ``False``.
        """
        return False
