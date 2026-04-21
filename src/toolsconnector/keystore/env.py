"""Read-only credential store backed by environment variables.

Ideal for twelve-factor apps and CI environments where secrets are
injected through the process environment.
"""

from __future__ import annotations

import os


class EnvironmentKeyStore:
    """Read-only :class:`KeyStore` that maps keys to environment variables.

    Key transformation rules:

    1. Replace every ``':'`` with ``'_'``.
    2. Convert to uppercase.
    3. Prefix with ``TC_``.

    Examples::

        gmail:default:api_key   -> TC_GMAIL_DEFAULT_API_KEY
        slack:ws-1:bot_token    -> TC_SLACK_WS-1_BOT_TOKEN
        github:org-456:pat      -> TC_GITHUB_ORG-456_PAT

    Because environment variables are inherently read-only from the
    library's perspective, :meth:`set` and :meth:`delete` always raise
    :class:`NotImplementedError`.

    Example::

        store = EnvironmentKeyStore()
        # reads os.environ["TC_GMAIL_DEFAULT_API_KEY"]
        api_key = await store.get("gmail:default:api_key")
    """

    @staticmethod
    def _to_env_var(key: str) -> str:
        """Convert a composite key to the corresponding env var name.

        Args:
            key: Composite key following the naming convention.

        Returns:
            The environment variable name (e.g. ``TC_GMAIL_DEFAULT_API_KEY``).
        """
        return "TC_" + key.replace(":", "_").upper()

    # -- KeyStore interface -----------------------------------------------

    async def get(self, key: str) -> str | None:
        """Read a credential from the environment.

        Args:
            key: Composite key following the naming convention.

        Returns:
            The environment variable value, or ``None`` if unset.
        """
        return os.environ.get(self._to_env_var(key))

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Not supported -- environment store is read-only.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "EnvironmentKeyStore is read-only. Set credentials via environment variables instead."
        )

    async def delete(self, key: str) -> None:
        """Not supported -- environment store is read-only.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "EnvironmentKeyStore is read-only. Unset environment variables directly instead."
        )

    async def exists(self, key: str) -> bool:
        """Check whether the corresponding environment variable is set.

        Args:
            key: Composite key following the naming convention.

        Returns:
            ``True`` if the environment variable exists.
        """
        return self._to_env_var(key) in os.environ
