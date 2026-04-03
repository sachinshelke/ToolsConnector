"""Public type definitions for the ToolsConnector library.

This module re-exports every public type so that downstream code can
import directly from ``toolsconnector.types``::

    from toolsconnector.types import PaginatedList, FileRef, CredentialSet
"""

from __future__ import annotations

from toolsconnector.types.common import PageState
from toolsconnector.types.credentials import CredentialSet, OAuthConfig
from toolsconnector.types.file import (
    FileRef,
    InMemoryStorageBackend,
    LocalStorageBackend,
    StorageBackend,
)
from toolsconnector.types.paginated import PaginatedList

__all__ = [
    "CredentialSet",
    "FileRef",
    "InMemoryStorageBackend",
    "LocalStorageBackend",
    "OAuthConfig",
    "PageState",
    "PaginatedList",
    "StorageBackend",
]
