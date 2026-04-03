"""Base protocol for pluggable credential storage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KeyStore(Protocol):
    """Pluggable credential storage interface.

    All methods are async.  Implementations may back onto environment
    variables, in-memory dicts, encrypted vaults, Redis, databases, or
    any other storage backend.

    Key naming convention::

        {connector_name}:{tenant_id}:{credential_type}

    Examples::

        gmail:user-123:access_token
        slack:default:bot_token
        github:org-456:personal_access_token
    """

    async def get(self, key: str) -> str | None:
        """Retrieve a stored credential by key.

        Args:
            key: Composite key following the naming convention.

        Returns:
            The stored value, or ``None`` if the key does not exist or
            has expired.
        """
        ...

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a credential.

        Args:
            key: Composite key following the naming convention.
            value: The credential value to store.
            ttl: Optional time-to-live in seconds.  ``None`` means the
                value does not expire.
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove a credential by key.

        This is a no-op if the key does not exist.

        Args:
            key: Composite key following the naming convention.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check whether a key exists and has not expired.

        Args:
            key: Composite key following the naming convention.

        Returns:
            ``True`` if the key is present and valid, ``False`` otherwise.
        """
        ...
