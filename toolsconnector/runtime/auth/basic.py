"""HTTP Basic authentication provider.

Base64-encodes ``username:password`` and sets the ``Authorization:
Basic`` header per :rfc:`7617`.
"""

from __future__ import annotations

import base64

from toolsconnector.errors import InvalidCredentialsError
from toolsconnector.spec.auth import AuthType


class BasicAuthProvider:
    """Auth provider for HTTP Basic authentication.

    Encodes the *username* and *password* as a Base64 string and
    injects an ``Authorization: Basic <encoded>`` header.

    Args:
        username: The username (or client-id in some APIs).
        password: The password (or client-secret).

    Raises:
        InvalidCredentialsError: If either *username* or *password*
            is empty or ``None``.

    Example::

        provider = BasicAuthProvider(
            username="admin",
            password="s3cret",
        )
    """

    auth_type: str = AuthType.BASIC.value

    def __init__(self, username: str, password: str) -> None:
        if not username:
            raise InvalidCredentialsError("Username must not be empty.")
        if not password:
            raise InvalidCredentialsError("Password must not be empty.")
        self._username = username
        self._password = password
        # Pre-compute the encoded value since it never changes.
        raw = f"{self._username}:{self._password}".encode("utf-8")
        self._encoded = base64.b64encode(raw).decode("ascii")

    # ------------------------------------------------------------------
    # AuthProvider protocol
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> None:
        """Add the ``Authorization: Basic`` header.

        Args:
            headers: Mutable HTTP headers dict.
            params: Mutable query-parameter dict (unused).
        """
        headers["Authorization"] = f"Basic {self._encoded}"

    async def refresh(self) -> None:
        """No-op -- Basic auth credentials are static."""

    def needs_refresh(self) -> bool:
        """Basic credentials never expire within the provider lifecycle.

        Returns:
            Always ``False``.
        """
        return False
