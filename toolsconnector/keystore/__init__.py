"""Pluggable credential storage for ToolsConnector.

Provides a :class:`KeyStore` protocol and two stdlib-only
implementations:

* :class:`InMemoryKeyStore` -- dict-backed, supports TTL, ideal for
  development and testing.
* :class:`EnvironmentKeyStore` -- read-only, maps composite keys to
  ``TC_``-prefixed environment variables.
"""

from __future__ import annotations

from toolsconnector.keystore.base import KeyStore
from toolsconnector.keystore.env import EnvironmentKeyStore
from toolsconnector.keystore.memory import InMemoryKeyStore

__all__ = [
    "KeyStore",
    "InMemoryKeyStore",
    "EnvironmentKeyStore",
]
