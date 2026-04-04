"""In-memory credential store backed by a plain dictionary.

Suitable for development, testing, and short-lived processes.  All data
is lost when the process exits.
"""

from __future__ import annotations

import time


class InMemoryKeyStore:
    """Dict-backed :class:`KeyStore` with optional per-key TTL.

    Internally each entry is stored as a ``(value, expiry)`` tuple where
    *expiry* is either a :func:`time.monotonic` deadline or ``None``
    (meaning the key never expires).  Expired entries are lazily pruned
    on :meth:`get` and :meth:`exists`.

    Example::

        store = InMemoryKeyStore()
        await store.set("slack:default:bot_token", "xoxb-...", ttl=3600)
        token = await store.get("slack:default:bot_token")
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    # -- helpers ----------------------------------------------------------

    def _is_expired(self, expiry: float | None) -> bool:
        """Return ``True`` if *expiry* is set and has passed."""
        return expiry is not None and time.monotonic() >= expiry

    def _prune(self, key: str) -> None:
        """Remove *key* if it has expired."""
        entry = self._data.get(key)
        if entry is not None and self._is_expired(entry[1]):
            del self._data[key]

    # -- KeyStore interface -----------------------------------------------

    async def get(self, key: str) -> str | None:
        """Retrieve a value by key.

        Returns ``None`` if the key is missing **or** has expired.  An
        expired entry is removed from the backing dict on access.

        Args:
            key: Composite key following the naming convention.

        Returns:
            The stored value, or ``None``.
        """
        self._prune(key)
        entry = self._data.get(key)
        if entry is None:
            return None
        return entry[0]

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a value with an optional TTL.

        Args:
            key: Composite key following the naming convention.
            value: The credential value to store.
            ttl: Time-to-live in seconds.  ``None`` means the key never
                expires.
        """
        expiry: float | None = None
        if ttl is not None:
            expiry = time.monotonic() + ttl
        self._data[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """Delete a key.

        No-op if the key does not exist.

        Args:
            key: Composite key following the naming convention.
        """
        self._data.pop(key, None)

    async def exists(self, key: str) -> bool:
        """Check if a key exists and has not expired.

        Args:
            key: Composite key following the naming convention.

        Returns:
            ``True`` if the key is present and valid.
        """
        self._prune(key)
        return key in self._data
